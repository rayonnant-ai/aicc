import socket
import threading
import time
import random
from collections import deque

# Configuration
HOST = 'localhost'
PORT = 7474
MAX_ROUNDS = 100
REGISTRATION_WINDOW = 10.0
MOVE_TIMEOUT = 1.0       # seconds per move
MAX_MOVES = 500          # moves before elimination
LOG_FILE = "results.log"

MOVE_DELTAS = {
    'U': (-1,  0),
    'D': ( 1,  0),
    'L': ( 0, -1),
    'R': ( 0,  1),
}


class MazeServer:
    def __init__(self):
        self.clients = []   # [socket, name, score, alive]
        self.lock = threading.Lock()
        self.all_time_scores = {}  # name -> score, persists across eliminations

        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"TOURNAMENT START: {time.ctime()}\n")
            f.write("=" * 50 + "\n")

    def log(self, text):
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")

    # ------------------------------------------------------------------ #
    #  Maze generation (unchanged from previous server)                   #
    # ------------------------------------------------------------------ #

    def _bfs_distances(self, grid, h, w, src):
        dist = {src: 0}
        q = deque([src])
        while q:
            r, c = q.popleft()
            for dr, dc in [(0,1),(0,-1),(1,0),(-1,0)]:
                nr, nc = r+dr, c+dc
                if 0 <= nr < h and 0 <= nc < w and (nr,nc) not in dist and grid[nr][nc] != '#':
                    dist[(nr,nc)] = dist[(r,c)] + 1
                    q.append((nr,nc))
        return dist

    def generate_maze(self, h=31, w=31):
        grid = [['#'] * w for _ in range(h)]

        # Iterative backtracker
        stack = [(1, 1)]
        grid[1][1] = ' '
        while stack:
            r, c = stack[-1]
            dirs = [(0,2),(0,-2),(2,0),(-2,0)]
            random.shuffle(dirs)
            moved = False
            for dr, dc in dirs:
                nr, nc = r+dr, c+dc
                if 0 < nr < h-1 and 0 < nc < w-1 and grid[nr][nc] == '#':
                    grid[r+dr//2][c+dc//2] = ' '
                    grid[nr][nc] = ' '
                    stack.append((nr, nc))
                    moved = True
                    break
            if not moved:
                stack.pop()

        # Add cycles (~15% wall removal)
        walls = [
            (r, c) for r in range(1, h-1) for c in range(1, w-1)
            if grid[r][c] == '#' and (
                (grid[r-1][c] == ' ' and grid[r+1][c] == ' ') or
                (grid[r][c-1] == ' ' and grid[r][c+1] == ' ')
            )
        ]
        for wall in random.sample(walls, max(1, len(walls) * 15 // 100)):
            grid[wall[0]][wall[1]] = ' '

        start, end = (1, 1), (h-2, w-2)
        dist_s = self._bfs_distances(grid, h, w, start)
        dist_e = self._bfs_distances(grid, h, w, end)
        baseline = dist_s.get(end, 0)

        grid[1][1] = '>'
        grid[h-2][w-2] = '<'

        # Strategic portal placement
        min_dist = max(3, baseline // 5)
        candidates = [
            (r, c) for r in range(h) for c in range(w)
            if grid[r][c] == ' '
            and dist_s.get((r,c), 0) >= min_dist
            and dist_e.get((r,c), 0) >= min_dist
        ]
        min_saving = max(4, baseline // 8)
        pairs = []
        for i, p1 in enumerate(candidates):
            for p2 in candidates[i+1:]:
                via = min(
                    dist_s.get(p1,9999) + 1 + dist_e.get(p2,9999),
                    dist_s.get(p2,9999) + 1 + dist_e.get(p1,9999),
                )
                saving = baseline - via
                if saving >= min_saving:
                    pairs.append((saving, p1, p2))
        pairs.sort(reverse=True)

        used, n = set(), 0
        portal_pairs = {}   # letter -> (cell1, cell2)
        for saving, p1, p2 in pairs:
            if n >= 4: break
            if p1 in used or p2 in used: continue
            letter = chr(ord('A') + n)
            grid[p1[0]][p1[1]] = letter
            grid[p2[0]][p2[1]] = letter
            portal_pairs[letter] = (p1, p2)
            used |= {p1, p2}
            n += 1

        # Build flat portal_map: cell -> partner cell
        portal_map = {}
        for letter, (c1, c2) in portal_pairs.items():
            portal_map[c1] = c2
            portal_map[c2] = c1

        return ["".join(row) for row in grid], portal_map

    # ------------------------------------------------------------------ #
    #  Fog-of-war view                                                    #
    # ------------------------------------------------------------------ #

    def get_view(self, grid, h, w, pos, revealed):
        """
        Return a 5x5 view centred on pos.
        Cells in `revealed` show their true character.
        Cells outside revealed show '?'.
        Cells outside the maze boundary show '#'.
        """
        r, c = pos
        lines = []
        for dr in range(-2, 3):
            row = []
            for dc in range(-2, 3):
                nr, nc = r+dr, c+dc
                if not (0 <= nr < h and 0 <= nc < w):
                    row.append('#')
                elif (nr, nc) in revealed:
                    row.append(grid[nr][nc])
                else:
                    row.append('?')
            lines.append("".join(row))
        return lines

    def reveal_around(self, pos, h, w, revealed):
        """Mark all cells in the 5x5 window around pos as revealed."""
        r, c = pos
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                nr, nc = r+dr, c+dc
                if 0 <= nr < h and 0 <= nc < w:
                    revealed.add((nr, nc))

    def send_view(self, conn, view_lines):
        payload = "".join(line + "\n" for line in view_lines)
        conn.sendall(payload.encode('utf-8'))

    # ------------------------------------------------------------------ #
    #  Per-client round handler                                           #
    # ------------------------------------------------------------------ #

    def handle_client_round(self, client_index, r_num, grid, h, w, portal_map, round_results):
        conn, name, _, _ = self.clients[client_index]
        steps = 0
        finish_time = None
        eliminated = False
        eliminated_reason = None
        result_steps = None
        move_log = []   # list of strings recorded as the round progresses

        try:
            conn.settimeout(MOVE_TIMEOUT)

            # Send round header
            conn.sendall(f"ROUND {r_num}\n".encode('utf-8'))

            # Initial position and revealed set
            pos = (1, 1)
            revealed = set()
            self.reveal_around(pos, h, w, revealed)

            # Send initial view
            self.send_view(conn, self.get_view(grid, h, w, pos, revealed))

            while steps < MAX_MOVES:
                # Read one move
                try:
                    move = self._recv_line(conn).strip().upper()
                except socket.timeout:
                    conn.sendall(b"ELIMINATED\n")
                    eliminated = True
                    eliminated_reason = f"TIMEOUT waiting for move after step {steps}"
                    move_log.append(f"  step {steps+1:>3}: [NO RESPONSE — timeout after {MOVE_TIMEOUT}s]")
                    break
                except ConnectionError as e:
                    eliminated = True
                    eliminated_reason = f"CONNECTION LOST after step {steps}: {e}"
                    move_log.append(f"  step {steps+1:>3}: [CONNECTION CLOSED]")
                    break

                if move not in MOVE_DELTAS:
                    conn.sendall(b"ELIMINATED\n")
                    eliminated = True
                    eliminated_reason = f"INVALID move {move!r} at step {steps}"
                    move_log.append(f"  step {steps+1:>3}: sent={move!r}  -> INVALID (eliminated)")
                    break

                dr, dc = MOVE_DELTAS[move]
                nr, nc = pos[0]+dr, pos[1]+dc

                # Boundary / wall check
                if not (0 <= nr < h and 0 <= nc < w) or grid[nr][nc] == '#':
                    conn.sendall(b"WALL\n")
                    move_log.append(f"  step {steps+1:>3}: sent={move}  pos={pos}  -> WALL")
                    continue  # WALL does not count as a step

                # Valid move
                steps += 1
                old_pos = pos
                pos = (nr, nc)
                self.reveal_around(pos, h, w, revealed)

                # Portal?
                if pos in portal_map:
                    dest = portal_map[pos]
                    pos = dest
                    self.reveal_around(pos, h, w, revealed)
                    conn.sendall(f"TELEPORT {pos[0]} {pos[1]}\n".encode('utf-8'))
                    move_log.append(f"  step {steps:>3}: sent={move}  {old_pos}->{nr,nc}  TELEPORT->{pos}")
                else:
                    move_log.append(f"  step {steps:>3}: sent={move}  {old_pos}->{pos}")

                # Reached exit?
                if grid[pos[0]][pos[1]] == '<':
                    finish_time = time.time()
                    result_steps = steps
                    conn.sendall(f"DONE {steps}\n".encode('utf-8'))
                    move_log.append(f"  EXIT reached in {steps} steps")
                    break

                # Send new view
                self.send_view(conn, self.get_view(grid, h, w, pos, revealed))

            else:
                # Exceeded MAX_MOVES
                conn.sendall(b"ELIMINATED\n")
                eliminated = True
                eliminated_reason = f"EXCEEDED {MAX_MOVES} moves without reaching exit"
                move_log.append(f"  [ELIMINATED — exceeded {MAX_MOVES} move limit]")

        except Exception as e:
            eliminated = True
            eliminated_reason = f"EXCEPTION: {e}"
            move_log.append(f"  [ELIMINATED — unexpected exception: {e}]")

        # Write the full move log to file
        log_lines = [f"BOT: {name}  ROUND: {r_num}"]
        if result_steps is not None:
            log_lines.append(f"  RESULT: FINISHED in {result_steps} steps")
        elif eliminated:
            log_lines.append(f"  RESULT: ELIMINATED — {eliminated_reason}")
        else:
            log_lines.append(f"  RESULT: DID NOT FINISH ({steps} moves used)")
        log_lines.append(f"  MOVES ({len(move_log)} entries):")
        log_lines.extend(move_log)
        self.log("\n".join(log_lines))

        with self.lock:
            round_results[client_index] = {
                'name': name,
                'steps': result_steps,
                'finish_time': finish_time or time.time(),
                'eliminated': eliminated,
                'eliminated_reason': eliminated_reason,
                'idx': client_index,
            }

    # ------------------------------------------------------------------ #
    #  Socket helpers                                                     #
    # ------------------------------------------------------------------ #

    def _recv_line(self, conn):
        buf = b''
        while True:
            byte = conn.recv(1)
            if not byte:
                raise ConnectionError("Connection closed")
            if byte == b'\n':
                return buf.decode('utf-8').rstrip('\r')
            buf += byte

    # ------------------------------------------------------------------ #
    #  Tournament loop                                                    #
    # ------------------------------------------------------------------ #

    def _print_results(self, r_num, round_results, all_clients_snapshot):
        finished = [r for r in round_results.values() if r['steps'] is not None]
        finished.sort(key=lambda x: (x['steps'], x['finish_time']))

        winner = finished[0] if finished else None
        winner_idx = winner['idx'] if winner else -1

        print(f"\n{'─'*50}")
        print(f"  ROUND {r_num} RESULT")
        print(f"{'─'*50}")
        if winner:
            print(f"  Winner : {winner['name']}")
            print(f"      Steps  : {winner['steps']}")
        else:
            print("  ⚠️   No bot reached the exit this round.")

        print()
        for r in sorted(round_results.values(),
                        key=lambda x: (x['steps'] is None, x['steps'] or 9999, x['finish_time'])):
            if r['steps'] is None:
                icon, detail = "✗", "ELIMINATED" if r['eliminated'] else "DID NOT FINISH"
            elif r['idx'] == winner_idx:
                icon, detail = "★", f"{r['steps']} steps  WINNER"
            else:
                icon, detail = "·", f"{r['steps']} steps"
            print(f"  {icon}  {r['name']:<20}  {detail}")

        print()
        print("  STANDINGS")
        print(f"  {'Bot':<22} {'Score':>5}  {'Status':>11}")
        print(f"  {'─'*22} {'─'*5}  {'─'*11}")
        active_names = {c[1] for c in self.clients}
        for name, score in sorted(
            {c[1]: c[2] for c in all_clients_snapshot}.items(),
            key=lambda x: -x[1]
        ):
            status = "active" if name in active_names else "ELIMINATED"
            marker = "►" if name in active_names else " "
            print(f"  {marker} {name:<21} {score:>5}  {status:>11}")
        print(f"{'─'*50}")

    def run_tournament(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((HOST, PORT))
        server_sock.listen(10)
        server_sock.settimeout(1.0)

        print(f"MAZE SERVER: Waiting {REGISTRATION_WINDOW}s for bots to connect...")
        reg_end = time.time() + REGISTRATION_WINDOW
        while time.time() < reg_end:
            try:
                conn, addr = server_sock.accept()
                conn.settimeout(REGISTRATION_WINDOW)
                name = self._recv_line(conn).strip()
                self.clients.append([conn, name, 0, True])
                self.all_time_scores.setdefault(name, 0)
                print(f"  Registered: {name}")
            except:
                continue

        if not self.clients:
            print("No bots connected. Exiting.")
            return

        print(f"\n{len(self.clients)} bot(s) registered. Starting tournament.\n")

        MAZE_MIN = 5    # starting grid size (odd)
        MAZE_MAX = 31   # ending grid size (odd)

        for r_num in range(1, MAX_ROUNDS + 1):
            if not self.clients:
                break

            # Linear ramp from MAZE_MIN to MAZE_MAX over MAX_ROUNDS.
            # Always keep dimensions odd (required by the backtracker).
            t = (r_num - 1) / max(MAX_ROUNDS - 1, 1)
            raw = MAZE_MIN + t * (MAZE_MAX - MAZE_MIN)
            size = int(raw)
            if size % 2 == 0:
                size += 1
            size = max(MAZE_MIN, min(MAZE_MAX, size))
            h, w = size, size

            grid_list, portal_map = self.generate_maze(h, w)

            self.log(f"\n{'='*20} ROUND {r_num} {'='*20}")
            self.log("MAZE:\n" + "\n".join(grid_list))
            self.log(f"PORTALS: {portal_map}")
            self.log("-" * 50)

            round_results = {}  # client_index -> result dict
            threads = []

            for i in range(len(self.clients)):
                t = threading.Thread(
                    target=self.handle_client_round,
                    args=(i, r_num, grid_list, h, w, portal_map, round_results),
                    daemon=True,
                )
                threads.append(t)
                t.start()

            # Wait for all bots to finish (each is bounded by MAX_MOVES * MOVE_TIMEOUT)
            max_wait = MAX_MOVES * MOVE_TIMEOUT + 5
            for t in threads:
                t.join(timeout=max_wait)

            with self.lock:
                finished = [r for r in round_results.values() if r['steps'] is not None]
                finished.sort(key=lambda x: (x['steps'], x['finish_time']))

                winner_idx = finished[0]['idx'] if finished else -1
                if winner_idx != -1:
                    self.clients[winner_idx][2] += 1
                    self.all_time_scores[self.clients[winner_idx][1]] += 1

                # Log results
                for r in round_results.values():
                    status = "WINNER" if r['idx'] == winner_idx else (
                        "ELIMINATED" if r['eliminated'] else "SURVIVED"
                    )
                    self.log(f"BOT: {r['name']}  STATUS: {status}  STEPS: {r['steps']}")

                all_clients_snapshot = [c[:] for c in self.clients]
                self._print_results(r_num, round_results, all_clients_snapshot)

                # Eliminate bots that didn't finish
                survivor_indices = {r['idx'] for r in round_results.values() if r['steps'] is not None}
                next_clients = []
                for i, client in enumerate(self.clients):
                    if i in survivor_indices:
                        next_clients.append(client)
                    else:
                        try:
                            client[0].close()
                        except:
                            pass

                self.clients = next_clients

            time.sleep(1)

        print(f"\n{'═'*50}")
        print(f"  TOURNAMENT OVER — FINAL STANDINGS")
        print(f"{'═'*50}")
        if self.all_time_scores:
            ranked = sorted(self.all_time_scores.items(), key=lambda x: -x[1])
            for rank, (name, score) in enumerate(ranked, 1):
                still_active = any(c[1] == name for c in self.clients)
                status = "active" if still_active else "eliminated"
                crown = f"#{rank} "
                print(f"  {crown}  {name:<22} {score:>3} point{'s' if score != 1 else '':<7}  {status}")
        else:
            print("  No scores recorded.")
        print(f"{'═'*50}")
        print("\nFull audit in results.log.")


if __name__ == "__main__":
    MazeServer().run_tournament()