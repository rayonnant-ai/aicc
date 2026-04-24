"""
Knights of Hanoi Tournament Server.

Each round: bot receives `ROUND {round_num} {n}` and must reply with a
comma-separated list of knight-jump moves (e.g. `A1C2,A1B3,...`) that
transports n disks from A1 to H8 under Towers-of-Hanoi placement rules.
Shortest valid solution wins; ties broken by server-receive time.
"""
import itertools
import os
import socket
import sys
import threading
import time

HOST = 'localhost'
PORT = 7474
REGISTRATION_WINDOW = 10.0
ROUND_TIMEOUT = 10.0
LOG_PATH = 'results.log'
MAX_RESPONSE_BYTES = 2 * 1024 * 1024   # 2 MB cap on a single response line
POINTS_BY_RANK = [10, 7, 5, 3, 1, 0]

# Round schedule: (round_num, n_disks). 10 rounds, n from 3..12.
ROUND_SCHEDULE = [(r, r + 2) for r in range(1, 11)]

# Board constants
START_SQ = (0, 0)   # A1 = row 0, col 0
GOAL_SQ = (7, 7)    # H8 = row 7, col 7

KNIGHT_DELTAS = {(-2, -1), (-2, 1), (-1, -2), (-1, 2),
                 (1, -2), (1, 2), (2, -1), (2, 1)}


# ─── Parsing & validation ────────────────────────────────────────────────────

def square_to_coord(s):
    """'A1'/'a1' → (row, col). None if invalid."""
    if len(s) != 2:
        return None
    f, r = s[0], s[1]
    if 'A' <= f <= 'H':
        col = ord(f) - ord('A')
    elif 'a' <= f <= 'h':
        col = ord(f) - ord('a')
    else:
        return None
    if r < '1' or r > '8':
        return None
    return (int(r) - 1, col)


def coord_to_square(sq):
    row, col = sq
    return f"{'ABCDEFGH'[col]}{row + 1}"


def parse_response(line):
    """
    Strict parser for the response line. Returns (moves, error_msg).
    moves is a list of ((from_row, from_col), (to_row, to_col)).
    Any deviation from the exact format yields an error.
    """
    if line is None:
        return None, "no response"
    if line == "":
        return None, "empty response"
    for ch in line:
        if ch.isspace():
            return None, "whitespace in response"
    if ',' in line and (line.startswith(',') or line.endswith(',')):
        return None, "leading or trailing comma"

    tokens = line.split(',')
    moves = []
    for idx, tok in enumerate(tokens):
        if len(tok) != 4:
            return None, f"move {idx + 1}: expected 4 chars, got '{tok}'"
        src = square_to_coord(tok[:2])
        if src is None:
            return None, f"move {idx + 1}: invalid source '{tok[:2]}'"
        dst = square_to_coord(tok[2:])
        if dst is None:
            return None, f"move {idx + 1}: invalid destination '{tok[2:]}'"
        moves.append((src, dst))
    return moves, None


def simulate(moves, n):
    """
    Replay moves on a board initialised with n disks stacked on A1.
    Returns (num_moves, None) on success, (None, error_msg) on failure.
    """
    board = {START_SQ: list(range(n, 0, -1))}   # bottom = n, top = 1

    for idx, (src, dst) in enumerate(moves):
        stack_src = board.get(src, [])
        if not stack_src:
            return None, f"move {idx + 1} ({coord_to_square(src)}→{coord_to_square(dst)}): source empty"

        dr = dst[0] - src[0]
        dc = dst[1] - src[1]
        if (dr, dc) not in KNIGHT_DELTAS:
            return None, f"move {idx + 1} ({coord_to_square(src)}→{coord_to_square(dst)}): not a knight move"

        disk = stack_src[-1]
        stack_dst = board.get(dst, [])
        if stack_dst and stack_dst[-1] < disk:
            return None, (f"move {idx + 1}: cannot place disk {disk} on smaller "
                          f"disk {stack_dst[-1]} at {coord_to_square(dst)}")

        stack_src.pop()
        stack_dst.append(disk)
        board[src] = stack_src
        board[dst] = stack_dst

    expected = list(range(n, 0, -1))
    goal_stack = board.get(GOAL_SQ, [])
    if goal_stack != expected:
        return None, f"final H8 stack is {goal_stack}, expected {expected}"
    for sq, stack in board.items():
        if sq != GOAL_SQ and stack:
            return None, f"stray disks at {coord_to_square(sq)}: {stack}"

    return len(moves), None


# ─── Client handling ─────────────────────────────────────────────────────────

class Client:
    def __init__(self, sock, name):
        self.sock = sock
        self.name = name
        self.score = 0
        self.f = sock.makefile('r', encoding='utf-8', errors='replace')

    def send(self, data):
        try:
            self.sock.sendall(data.encode('utf-8'))
        except OSError:
            pass

    def read_response_line(self, timeout):
        """
        Read one line from the client with the given timeout. Returns the
        line content (as a str) with at most one trailing '\r' and '\n'
        stripped — anything else embedded in the line is preserved so the
        strict parser can reject it. Returns None on timeout/EOF.
        """
        self.sock.settimeout(timeout)
        try:
            line = self.f.readline(MAX_RESPONSE_BYTES)
            if not line:
                return None
            if line.endswith('\n'):
                line = line[:-1]
            if line.endswith('\r'):
                line = line[:-1]
            return line
        except (OSError, socket.timeout):
            return None
        finally:
            self.sock.settimeout(None)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ─── Log rotation ────────────────────────────────────────────────────────────

def rotate_log():
    if not os.path.exists(LOG_PATH):
        return
    n = 1
    while os.path.exists(f"{LOG_PATH}.{n}"):
        n += 1
    for i in range(n - 1, 0, -1):
        os.rename(f"{LOG_PATH}.{i}", f"{LOG_PATH}.{i + 1}")
    os.rename(LOG_PATH, f"{LOG_PATH}.1")


# ─── Tournament loop ─────────────────────────────────────────────────────────

def run_tournament():
    rotate_log()
    log = open(LOG_PATH, 'w', encoding='utf-8')

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(16)
    server_sock.settimeout(1.0)

    clients = []
    print(f"[*] Server live on {HOST}:{PORT}. Registration: {REGISTRATION_WINDOW}s")
    start_reg = time.time()
    while time.time() - start_reg < REGISTRATION_WINDOW:
        try:
            conn, addr = server_sock.accept()
            conn.settimeout(None)
            name_line = conn.makefile('r').readline().strip()
            if name_line:
                c = Client(conn, name_line)
                clients.append(c)
                print(f"[*] Bot '{name_line}' joined.")
        except socket.timeout:
            continue

    if not clients:
        print("[!] No participants.")
        log.close()
        return

    print(f"[*] {len(clients)} bots registered. Starting tournament.\n")
    log.write(f"Tournament: {len(clients)} bots\n")
    log.write(f"Bots: {', '.join(c.name for c in clients)}\n\n")

    final_round_num = ROUND_SCHEDULE[-1][0]

    for round_num, n in ROUND_SCHEDULE:
        header = f"--- ROUND {round_num}: n={n} disks ---"
        print(header)
        log.write(header + "\n")

        round_start = time.monotonic()
        for c in clients:
            c.send(f"ROUND {round_num} {n}\n")

        # Collect responses in parallel.
        results = {}     # name -> dict(moves=int|None, elapsed_ms, status, detail, raw)
        lock = threading.Lock()

        def collect(client):
            raw = client.read_response_line(timeout=ROUND_TIMEOUT)
            elapsed_ms = (time.monotonic() - round_start) * 1000
            if raw is None:
                with lock:
                    results[client.name] = dict(
                        moves=None, elapsed_ms=elapsed_ms,
                        status="TIMEOUT", detail="no response", raw=None,
                    )
                return
            parsed, err = parse_response(raw)
            if parsed is None:
                with lock:
                    results[client.name] = dict(
                        moves=None, elapsed_ms=elapsed_ms,
                        status="INVALID", detail=err, raw=raw,
                    )
                return
            count, sim_err = simulate(parsed, n)
            if count is None:
                with lock:
                    results[client.name] = dict(
                        moves=None, elapsed_ms=elapsed_ms,
                        status="INVALID", detail=sim_err, raw=raw,
                    )
            else:
                with lock:
                    results[client.name] = dict(
                        moves=count, elapsed_ms=elapsed_ms,
                        status="VALID", detail=None, raw=raw,
                    )

        threads = [threading.Thread(target=collect, args=(c,), daemon=True)
                   for c in clients]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=ROUND_TIMEOUT + 2)

        # Rank valid results by (moves, elapsed_ms).
        valid = [(name, r['moves'], r['elapsed_ms'])
                 for name, r in results.items() if r['moves'] is not None]
        valid.sort(key=lambda x: (x[1], x[2]))

        for rank, (name, _, _) in enumerate(valid):
            pts = POINTS_BY_RANK[rank] if rank < len(POINTS_BY_RANK) else 0
            for c in clients:
                if c.name == name:
                    c.score += pts

        # Reply to each client.
        for c in clients:
            r = results.get(c.name)
            if r is None:
                c.send("TIMEOUT\n")
                continue
            if r['status'] == "VALID":
                c.send(f"VALID {r['moves']}\n")
            elif r['status'] == "INVALID":
                c.send(f"INVALID {r['detail']}\n")
            else:
                c.send("TIMEOUT\n")

        # Log rows sorted: valid (by moves) first, then invalid/timeout.
        def sort_key(item):
            r = item[1]
            return (r['moves'] if r['moves'] is not None else float('inf'),
                    r['elapsed_ms'])

        for name, r in sorted(results.items(), key=sort_key):
            rank_idx = next((i for i, (nm, _, _) in enumerate(valid)
                             if nm == name), None)
            pts = (POINTS_BY_RANK[rank_idx]
                   if rank_idx is not None and rank_idx < len(POINTS_BY_RANK)
                   else 0)
            total = next(c.score for c in clients if c.name == name)
            if r['status'] == "VALID":
                line = (f"  {name:<28} | {r['moves']:>7} moves | "
                        f"{r['elapsed_ms']:>8.1f}ms | +{pts:>2} | total: {total}")
            else:
                label = f"{r['status']}: {r['detail']}"
                line = (f"  {name:<28} | {label:<50} | "
                        f"{r['elapsed_ms']:>8.1f}ms | + 0 | total: {total}")
            print(line)
            log.write(line + "\n")

        # Log raw solutions (truncated for large ones).
        log.write("\nSOLUTIONS:\n")
        for name in sorted(results.keys()):
            r = results[name]
            raw = r.get('raw')
            if raw is None:
                log.write(f"  {name}: <no response>\n")
                continue
            if len(raw) > 500:
                log.write(f"  {name} ({len(raw)} chars): {raw[:400]}...[TRUNCATED]...{raw[-80:]}\n")
            else:
                log.write(f"  {name}: {raw}\n")
        log.write("\n")
        log.flush()
        time.sleep(0.5)

    # After final round: send END and close.
    print("\n[*] Sending END.")
    for c in clients:
        c.send("END\n")

    banner = "=" * 60 + "\nFINAL TOURNAMENT RESULTS\n" + "=" * 60
    print("\n" + banner)
    log.write("\n" + banner + "\n")
    for i, c in enumerate(sorted(clients, key=lambda c: -c.score)):
        line = f"  #{i + 1}  {c.name:<28} {c.score:>4} points"
        print(line)
        log.write(line + "\n")

    log.close()
    server_sock.close()
    for c in clients:
        c.close()


if __name__ == "__main__":
    run_tournament()
