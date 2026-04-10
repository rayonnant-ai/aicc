"""
Blobby Tic-Tac-Toe Tournament Server.

Round-robin tournament with penalty-shootout matchups on irregular grid boards.
"""
import socket
import threading
import time
import random
import os
import itertools

HOST = 'localhost'
PORT = 7474
REGISTRATION_WINDOW = 10.0
MOVE_TIMEOUT = 2.0
MAX_REGULAR_ROUNDS = 5
MAX_SUDDEN_DEATH = 5  # up to 10 total
LOG_PATH = 'results.log'
WIN_TOURNAMENT_PTS = 3
DRAW_TOURNAMENT_PTS = 1


def rotate_log():
    if not os.path.exists(LOG_PATH):
        return
    n = 1
    while os.path.exists(f"{LOG_PATH}.{n}"):
        n += 1
    for i in range(n - 1, 0, -1):
        os.rename(f"{LOG_PATH}.{i}", f"{LOG_PATH}.{i+1}")
    os.rename(LOG_PATH, f"{LOG_PATH}.1")


# =============================================================================
# Board generation
# =============================================================================

def generate_board():
    """Generate a random blob-shaped board with at least one winning line."""
    for _ in range(1000):
        rows = random.randint(4, 10)
        cols = random.randint(4, 10)
        # Start with a seed cell near the center
        grid = [[False] * cols for _ in range(rows)]
        sr, sc = rows // 2, cols // 2
        grid[sr][sc] = True
        # Grow the blob
        n_cells = random.randint(8, min(rows * cols, 30))
        frontier = [(sr, sc)]
        count = 1
        while count < n_cells and frontier:
            r, c = random.choice(frontier)
            neighbors = []
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and not grid[nr][nc]:
                    neighbors.append((nr, nc))
            if not neighbors:
                frontier.remove((r, c))
                continue
            nr, nc = random.choice(neighbors)
            grid[nr][nc] = True
            frontier.append((nr, nc))
            count += 1

        # Trim empty border rows/cols
        grid, rows, cols = trim_board(grid, rows, cols)
        if rows < 4 or cols < 4:
            continue

        # Check for at least one winning line
        lines = find_winning_lines(grid, rows, cols)
        if lines:
            return grid, rows, cols
    # Fallback: simple 4x4 board
    grid = [[True] * 4 for _ in range(4)]
    return grid, 4, 4


def trim_board(grid, rows, cols):
    """Remove empty border rows and columns."""
    # Find bounds
    min_r = rows
    max_r = -1
    min_c = cols
    max_c = -1
    for r in range(rows):
        for c in range(cols):
            if grid[r][c]:
                min_r = min(min_r, r)
                max_r = max(max_r, r)
                min_c = min(min_c, c)
                max_c = max(max_c, c)
    if max_r < 0:
        return grid, rows, cols
    new_rows = max_r - min_r + 1
    new_cols = max_c - min_c + 1
    new_grid = []
    for r in range(min_r, max_r + 1):
        new_grid.append([grid[r][c] for c in range(min_c, max_c + 1)])
    return new_grid, new_rows, new_cols


def find_winning_lines(grid, rows, cols):
    """Find all possible 3-in-a-row lines on the board."""
    lines = []
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]  # horiz, vert, diag-down, diag-up
    for r in range(rows):
        for c in range(cols):
            if not grid[r][c]:
                continue
            for dr, dc in directions:
                cells = []
                valid = True
                for step in range(3):
                    nr = r + dr * step
                    nc = c + dc * step
                    if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc]:
                        cells.append((nr, nc))
                    else:
                        valid = False
                        break
                if valid and len(cells) == 3:
                    lines.append(tuple(cells))
    return lines


def board_to_str(grid, rows, cols, marks=None):
    """Convert board to string representation."""
    result = []
    for r in range(rows):
        row = ''
        for c in range(cols):
            if not grid[r][c]:
                row += '.'
            elif marks and (r, c) in marks:
                row += marks[(r, c)]
            else:
                row += '_'
        result.append(row)
    return '\n'.join(result)


# =============================================================================
# Game logic
# =============================================================================

class Game:
    def __init__(self, grid, rows, cols, player_x, player_o):
        self.grid = grid
        self.rows = rows
        self.cols = cols
        self.player_x = player_x  # Client who plays X
        self.player_o = player_o  # Client who plays O
        self.marks = {}  # (r, c) -> 'X' or 'O'
        self.turn = 'X'  # X always goes first
        self.winner = None  # 'X', 'O', or 'DRAW'
        self.lines = find_winning_lines(grid, rows, cols)
        self.valid_cells = set()
        for r in range(rows):
            for c in range(cols):
                if grid[r][c]:
                    self.valid_cells.add((r, c))
        self.move_history = []  # list of (player_mark, row, col)

    def is_over(self):
        return self.winner is not None

    def current_player(self):
        if self.turn == 'X':
            return self.player_x
        return self.player_o

    def other_player(self):
        if self.turn == 'X':
            return self.player_o
        return self.player_x

    def make_move(self, r, c):
        """Attempt a move. Returns True if valid."""
        if (r, c) not in self.valid_cells:
            return False
        if (r, c) in self.marks:
            return False
        self.marks[(r, c)] = self.turn
        self.move_history.append((self.turn, r, c))
        # Check win
        for line in self.lines:
            if all(self.marks.get(cell) == self.turn for cell in line):
                self.winner = self.turn
                return True
        # Check draw
        if len(self.marks) == len(self.valid_cells):
            self.winner = 'DRAW'
        # Switch turn
        self.turn = 'O' if self.turn == 'X' else 'X'
        return True

    def forfeit(self, player):
        """Player forfeits. Other player wins."""
        if player == self.player_x:
            self.winner = 'O'
        else:
            self.winner = 'X'


# =============================================================================
# Client handling
# =============================================================================

class Client:
    def __init__(self, sock, name):
        self.sock = sock
        self.name = name
        self.tournament_pts = 0
        self.f = sock.makefile('r', encoding='utf-8')

    def send(self, data):
        try:
            self.sock.sendall(data.encode('utf-8'))
        except OSError:
            pass

    def readline(self, timeout=None):
        if timeout:
            self.sock.settimeout(timeout)
        try:
            line = self.f.readline()
            if not line:
                return None
            return line.strip()
        except (OSError, socket.timeout):
            return None
        finally:
            if timeout:
                self.sock.settimeout(None)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# =============================================================================
# Matchup logic
# =============================================================================

def parse_move(resp):
    """Parse a move response. Returns (row, col) or None."""
    if resp is None:
        return None
    try:
        parts = resp.split()
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None


def apply_move(game, game_num, player, resp, log):
    """Apply a player's move to a game. Returns (row, col) if valid, None if forfeit."""
    move = parse_move(resp)
    if resp is None:
        log.write(f"    {player.name} timed out in game {game_num}\n")
        game.forfeit(player)
        return None
    if move is None:
        log.write(f"    {player.name} malformed move '{resp}' in game {game_num}\n")
        game.forfeit(player)
        return None
    r, c = move
    if not game.make_move(r, c):
        log.write(f"    {player.name} invalid move {r},{c} in game {game_num}\n")
        game.forfeit(player)
        return None
    log.write(f"    {player.name} plays {r},{c} in game {game_num}\n")
    return (r, c)


def play_round(game1, game2, log):
    """Play two simultaneous games. Returns when both are done."""
    # game1: client_a=X, client_b=O
    # game2: client_b=X, client_a=O
    # On simultaneous turns, each bot moves in one game while the other bot
    # moves in the other game. Moves are collected before either is revealed.

    while not (game1.is_over() and game2.is_over()):
        g1_active = not game1.is_over()
        g2_active = not game2.is_over()

        if g1_active and g2_active:
            # Both games active: simultaneous moves
            p1 = game1.current_player()  # moves in game 1
            p2 = game2.current_player()  # moves in game 2

            p1.send("YOURTURN 1\n")
            p2.send("YOURTURN 2\n")

            # Collect both moves simultaneously
            responses = {}
            lock = threading.Lock()

            def get_move(player, game_num):
                resp = player.readline(timeout=MOVE_TIMEOUT)
                with lock:
                    responses[game_num] = resp

            t1 = threading.Thread(target=get_move, args=(p1, 1), daemon=True)
            t2 = threading.Thread(target=get_move, args=(p2, 2), daemon=True)
            t1.start()
            t2.start()
            t1.join(timeout=MOVE_TIMEOUT + 1)
            t2.join(timeout=MOVE_TIMEOUT + 1)

            # Apply moves
            move1 = apply_move(game1, 1, p1, responses.get(1), log)
            move2 = apply_move(game2, 2, p2, responses.get(2), log)

            # Relay opponent moves for games that are still active
            # p2 needs to see p1's move in game 1 (where p2 is the other player)
            # p1 needs to see p2's move in game 2 (where p1 is the other player)
            if move1 is not None and not game1.is_over():
                p2.send(f"OPPONENT 1 {move1[0]} {move1[1]}\n")
            if move2 is not None and not game2.is_over():
                p1.send(f"OPPONENT 2 {move2[0]} {move2[1]}\n")

            # Send results for games that just ended
            send_game_results(game1, 1)
            send_game_results(game2, 2)

        else:
            # Only one game active: sequential play
            game = game1 if g1_active else game2
            game_num = 1 if g1_active else 2
            player = game.current_player()
            opponent = game.other_player()

            player.send(f"YOURTURN {game_num}\n")
            resp = player.readline(timeout=MOVE_TIMEOUT)

            move = apply_move(game, game_num, player, resp, log)
            if move is not None and not game.is_over():
                opponent.send(f"OPPONENT {game_num} {move[0]} {move[1]}\n")

            send_game_results(game, game_num)


def send_game_results(game, game_num):
    """Send RESULT if game just ended."""
    if not game.is_over():
        return
    if hasattr(game, f'_result_sent_{game_num}'):
        return
    setattr(game, f'_result_sent_{game_num}', True)

    if game.winner == 'DRAW':
        game.player_x.send(f"RESULT GAME{game_num} DRAW\n")
        game.player_o.send(f"RESULT GAME{game_num} DRAW\n")
    elif game.winner == 'X':
        game.player_x.send(f"RESULT GAME{game_num} WIN\n")
        game.player_o.send(f"RESULT GAME{game_num} LOSS\n")
    else:  # O wins
        game.player_x.send(f"RESULT GAME{game_num} LOSS\n")
        game.player_o.send(f"RESULT GAME{game_num} WIN\n")


def run_matchup(client_a, client_b, log):
    """Run a full penalty-shootout matchup between two clients."""
    score_a = 0  # match points
    score_b = 0
    max_rounds = MAX_REGULAR_ROUNDS + MAX_SUDDEN_DEATH
    round_num = 0

    while round_num < max_rounds:
        round_num += 1

        # Check early termination
        rounds_left = MAX_REGULAR_ROUNDS - round_num + 1 if round_num <= MAX_REGULAR_ROUNDS else 1
        max_catchup = rounds_left * 2  # 2 games per round
        if round_num > 1:
            if score_a - score_b > max_catchup or score_b - score_a > max_catchup:
                break
            # After regular rounds, check sudden death condition
            if round_num > MAX_REGULAR_ROUNDS and score_a != score_b:
                break

        # Generate board
        grid, rows, cols = generate_board()
        board_str = board_to_str(grid, rows, cols)

        n_cells = sum(grid[r][c] for r in range(rows) for c in range(cols))
        n_lines = len(find_winning_lines(grid, rows, cols))
        log.write(f"  Round {round_num}: {rows}x{cols} board, {n_cells} cells, {n_lines} winning lines\n")
        log.write(f"  Board:\n")
        for row in board_str.split('\n'):
            log.write(f"    {row}\n")

        # Send board to both players
        for client in [client_a, client_b]:
            client.send(f"ROUND {round_num}\n")
            client.send(f"BOARD\n{board_str}\nEND\n")

        # Game 1: A=X, B=O. Game 2: A=O, B=X.
        game1 = Game(grid, rows, cols, client_a, client_b)
        game2 = Game(grid, rows, cols, client_b, client_a)

        # Tell players their roles
        client_a.send("GAME1 X\nGAME2 O\n")
        client_b.send("GAME1 O\nGAME2 X\n")

        # Play
        play_round(game1, game2, log)

        # Score
        round_a = 0
        round_b = 0
        # Game 1: A is X, B is O
        if game1.winner == 'X':
            round_a += 1
        elif game1.winner == 'O':
            round_b += 1
        # Game 2: B is X, A is O
        if game2.winner == 'X':
            round_b += 1
        elif game2.winner == 'O':
            round_a += 1

        score_a += round_a
        score_b += round_b

        # Log game replays
        for gnum, game, x_player, o_player in [
            (1, game1, client_a.name, client_b.name),
            (2, game2, client_b.name, client_a.name),
        ]:
            log.write(f"  Game {gnum} (X={x_player}, O={o_player}): {game.winner}\n")
            for mark, r, c in game.move_history:
                who = x_player if mark == 'X' else o_player
                log.write(f"    {mark} {who} {r} {c}\n")
            log.write(f"  Final board:\n")
            final = board_to_str(grid, rows, cols, game.marks)
            for row in final.split('\n'):
                log.write(f"    {row}\n")

        log.write(f"  Round {round_num} result: {client_a.name} +{round_a}, "
                  f"{client_b.name} +{round_b} (total: {score_a}-{score_b})\n")

        # Send round scores
        client_a.send(f"ROUND_SCORE {round_a} {round_b}\n")
        client_b.send(f"ROUND_SCORE {round_b} {round_a}\n")

    # Matchup result
    if score_a > score_b:
        client_a.send(f"MATCHUP WIN {score_a} {score_b}\n")
        client_b.send(f"MATCHUP LOSS {score_b} {score_a}\n")
        client_a.tournament_pts += WIN_TOURNAMENT_PTS
        result = f"{client_a.name} wins"
    elif score_b > score_a:
        client_b.send(f"MATCHUP WIN {score_b} {score_a}\n")
        client_a.send(f"MATCHUP LOSS {score_a} {score_b}\n")
        client_b.tournament_pts += WIN_TOURNAMENT_PTS
        result = f"{client_b.name} wins"
    else:
        client_a.send(f"MATCHUP DRAW {score_a} {score_b}\n")
        client_b.send(f"MATCHUP DRAW {score_b} {score_a}\n")
        client_a.tournament_pts += DRAW_TOURNAMENT_PTS
        client_b.tournament_pts += DRAW_TOURNAMENT_PTS
        result = "draw"

    log.write(f"  Matchup result: {result} ({score_a}-{score_b})\n\n")
    return result, score_a, score_b


# =============================================================================
# Tournament
# =============================================================================

def run_tournament():
    rotate_log()
    log = open(LOG_PATH, 'w', encoding='utf-8')

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(10)
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
                client = Client(conn, name_line)
                clients.append(client)
                print(f"[*] Bot '{name_line}' joined.")
        except socket.timeout:
            continue

    if len(clients) < 2:
        print("[!] Need at least 2 participants.")
        log.close()
        return

    print(f"[*] {len(clients)} bots registered. Starting round-robin tournament.\n")
    log.write(f"Tournament: {len(clients)} bots\n")
    log.write(f"Bots: {', '.join(c.name for c in clients)}\n\n")

    # Round robin: every pair plays
    matchups = list(itertools.combinations(range(len(clients)), 2))
    random.shuffle(matchups)

    for mi, (i, j) in enumerate(matchups):
        a, b = clients[i], clients[j]
        header = f"=== MATCHUP {mi+1}/{len(matchups)}: {a.name} vs {b.name} ==="
        print(header)
        log.write(header + "\n")

        result, sa, sb = run_matchup(a, b, log)
        log.flush()

        print(f"  Result: {result} ({sa}-{sb})")
        print(f"  Standings: {a.name} {a.tournament_pts} pts, {b.name} {b.tournament_pts} pts")

    # Final standings
    header = "\n" + "=" * 60 + "\nFINAL TOURNAMENT RESULTS\n" + "=" * 60
    print(header)
    log.write(header + "\n")

    sorted_clients = sorted(clients, key=lambda c: -c.tournament_pts)
    for i, client in enumerate(sorted_clients):
        line = f"  #{i+1}  {client.name:<20} {client.tournament_pts:>4} tournament points"
        print(line)
        log.write(line + "\n")

    log.close()
    server_sock.close()
    for c in clients:
        c.close()


if __name__ == "__main__":
    run_tournament()
