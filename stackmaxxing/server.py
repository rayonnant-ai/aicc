"""
StackMaxxing Tournament Server.

Bots drop polyomino shapes into a 2D rectangular tank using Tetris-style
rigid-piece gravity (no line clearing, no horizontal nudge, no rotation
after drop). Per-bot per-round scoring: pieces successfully placed before
an invalid placement / malformed response / time-budget overrun.

Each bot's round runs on its own thread, in parallel with the others,
against the same piece sequence. After all bots finish their round, points
are awarded by rank.
"""
import itertools
import os
import random
import re
import socket
import threading
import time

# ── Tournament configuration ─────────────────────────────────────────────────
HOST = 'localhost'
PORT = 7474
REGISTRATION_WINDOW = 10.0
ROUND_BUDGET = 10.0          # seconds of cumulative wait time per bot per round
SEQUENCE_LENGTH = 500        # pieces per round; far more than will fit anywhere
LOG_PATH = 'results.log'
POINTS_BY_RANK = [10, 7, 5, 3, 1, 0]

# (n_cols, n_rows) per round.
ROUND_DIMS = [
    (6, 8),
    (7, 10),
    (8, 12),
    (10, 12),
    (12, 14),
    (12, 16),
    (14, 16),
    (14, 18),
    (16, 20),
    (18, 20),
]
MAX_ROUNDS = len(ROUND_DIMS)

# Strict response grammar from the spec.
RESPONSE_RE = re.compile(r'^([0-3]) (0|[1-9][0-9]*)$')


# ── Polyomino generation ─────────────────────────────────────────────────────

def normalize(cells):
    mx = min(x for x, _ in cells)
    my = min(y for _, y in cells)
    return tuple(sorted((x - mx, y - my) for x, y in cells))


def rotate_ccw(cells):
    """Apply (x,y) → (-y, x) to every cell."""
    return [(-y, x) for x, y in cells]


def all_rotations(cells):
    """All four rotations of `cells`, each individually normalized."""
    rots = [normalize(cells)]
    cur = list(cells)
    for _ in range(3):
        cur = rotate_ccw(cur)
        rots.append(normalize(cur))
    return rots


def canonical(cells):
    """One-sided canonical form: lexicographic min over the 4 rotations."""
    return min(all_rotations(cells))


def generate_shapes(max_size):
    """All one-sided polyominoes of sizes 1..max_size, each in some normalized form."""
    monomino = normalize([(0, 0)])
    by_size = {1: [monomino]}
    seen = {canonical(monomino)}

    for size in range(2, max_size + 1):
        new_shapes = []
        for prev in by_size[size - 1]:
            for (x, y) in prev:
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nc = (x + dx, y + dy)
                    if nc in prev:
                        continue
                    candidate = normalize(list(prev) + [nc])
                    canon = canonical(candidate)
                    if canon not in seen:
                        seen.add(canon)
                        new_shapes.append(candidate)
        by_size[size] = new_shapes

    flat = []
    for size in sorted(by_size.keys()):
        flat.extend(by_size[size])
    return flat


# Named seeds for the 6 hardest pentominoes. We sample only from these
# six, weighted (see _WEIGHTS below). The prompt allows "samples them with
# replacement from a fixed catalogue" without specifying a uniform
# distribution, so a biased catalogue is within the locked spec bounds.
_HARD_PENTOMINOES = {
    'X':  [(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)],   # plus / cross — guaranteed 4 corner holes per landing
    'F':  [(0, 0), (0, 1), (1, 1), (1, 2), (2, 1)],   # F-pentomino — irregular
    "F'": [(0, 1), (0, 2), (1, 0), (1, 1), (2, 1)],   # mirror of F
    'W':  [(0, 0), (0, 1), (1, 1), (1, 2), (2, 2)],   # staircase — forces zigzag stacks
    'U':  [(0, 0), (0, 1), (1, 1), (2, 0), (2, 1)],   # slot — traps unfillable cell if placed wrong
    'T':  [(0, 0), (0, 1), (0, 2), (1, 1), (2, 1)],   # T-pentomino — column of 3 with perpendicular arm
}

# X-heavy weights. Distribution: X=5/12, F=2/12, F'=2/12, W=U=T=1/12 each.
# Picked so X arrives every other piece on average, forcing top-tier bots
# to consistently solve the hardest placement and amplifying differentiation
# on small boards where uniform sampling would let lazy heuristics tie.
_WEIGHTS = {
    'X': 5,
    'F': 2,
    "F'": 2,
    'W': 1,
    'U': 1,
    'T': 1,
}

# Match each named seed against the generator's canonical catalogue so the
# normalized representation matches what `apply_rotation` and `settle` expect.
_canonical_to_named = {canonical(seed): name for name, seed in _HARD_PENTOMINOES.items()}
_named_to_shape = {}
for _s in generate_shapes(5):
    if len(_s) != 5:
        continue
    _name = _canonical_to_named.get(canonical(_s))
    if _name is not None and _name not in _named_to_shape:
        _named_to_shape[_name] = _s

SHAPES = []
for _name, _weight in _WEIGHTS.items():
    SHAPES.extend([_named_to_shape[_name]] * _weight)
# `SHAPES` now has 12 entries (with X repeated 5 times etc.) so a uniform
# rng.choice(SHAPES) yields the X-heavy distribution.


# ── Wire format ──────────────────────────────────────────────────────────────

def cells_to_str(cells):
    """Render cells as 'x,y x,y ...' (space-separated, comma-joined coords)."""
    return ' '.join(f'{x},{y}' for x, y in cells)


def apply_rotation(cells, k):
    """Apply rotate_ccw exactly k times then normalize once."""
    cur = list(cells)
    for _ in range(k):
        cur = rotate_ccw(cur)
    return normalize(cur)


# ── Drop resolution ──────────────────────────────────────────────────────────

def settle(rotated_cells, column, board, n_cols, n_rows):
    """
    Compute the resting `settle_y` for `rotated_cells` placed at `column`
    on `board` (a set of occupied (x,y) tuples). Returns (settle_y, error)
    where error is None on success or one of:
      'horiz_oob' — rotated piece doesn't fit horizontally
      'top_oob'   — piece can't settle without a cell at y >= n_rows
    """
    w = max(x for x, _ in rotated_cells) + 1
    if column < 0 or column + w > n_cols:
        return None, 'horiz_oob'

    # Find the smallest non-negative dy such that placing each cell at
    # (column + rx, dy + ry) collides with nothing on the board. Since we
    # search dy = 0, 1, 2, ... in order, the first non-colliding dy is by
    # construction the lowest valid one (settle_y - 1 was rejected for
    # collision, or settle_y == 0).
    for dy in range(0, n_rows + 5):  # bounded; can land at most a few rows above n_rows-1
        cells_at = [(column + rx, dy + ry) for rx, ry in rotated_cells]
        if any(c in board for c in cells_at):
            continue
        max_y = max(y for _, y in cells_at)
        if max_y >= n_rows:
            return dy, 'top_oob'
        return dy, None

    return None, 'top_oob'


# ── Client ───────────────────────────────────────────────────────────────────

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

    def readline(self, timeout):
        """Read one line, raising socket.timeout on overrun. Returns the
        line (with trailing '\\n' if present) or '' on EOF."""
        self.sock.settimeout(timeout)
        try:
            return self.f.readline()
        finally:
            try:
                self.sock.settimeout(None)
            except OSError:
                pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ── Per-bot round runner ─────────────────────────────────────────────────────

def run_bot_round(client, sequence, n_cols, n_rows, results, results_lock):
    """Run one bot's round to completion. Updates results[client.name] when done.

    The per-move list (rotation, column, settle_y) is captured in `moves_log`
    and stored in results[client.name]['moves']; the main thread writes them
    to results.log after the round so visualizations can replay each bot's run.
    """
    board = set()              # occupied (x, y)
    pieces_placed = 0
    cells_filled = 0
    elapsed = 0.0
    cause = 'unknown'
    last_resp_at = time.monotonic()
    last_resp_raw = None

    moves_log = []

    n = len(sequence)
    for idx in range(n):
        current = sequence[idx]
        next1 = sequence[idx + 1] if idx + 1 < n else None
        next2 = sequence[idx + 2] if idx + 2 < n else None

        next1_str = cells_to_str(next1) if next1 is not None else 'END'
        next2_str = cells_to_str(next2) if next2 is not None else 'END'
        prompt = (
            "PIECE\n"
            f"CURRENT {cells_to_str(current)}\n"
            f"NEXT {next1_str}\n"
            f"NEXT {next2_str}\n"
        )
        client.send(prompt)

        budget_left = ROUND_BUDGET - elapsed
        if budget_left <= 0:
            cause = 'timeout (budget exhausted)'
            break

        t0 = time.monotonic()
        try:
            line = client.readline(budget_left)
        except (socket.timeout, OSError):
            line = None
        t1 = time.monotonic()
        elapsed += (t1 - t0)
        last_resp_at = t1

        if line is None:
            cause = 'timeout (budget overrun)'
            break
        if not line.endswith('\n'):
            cause = 'malformed (no LF / EOF mid-line)'
            last_resp_raw = repr(line)
            break

        resp = line[:-1]   # strip exactly one trailing LF
        last_resp_raw = resp

        m = RESPONSE_RE.match(resp)
        if not m:
            cause = f'malformed response: {resp!r}'
            break
        rotation = int(m.group(1))
        column = int(m.group(2))

        rotated = apply_rotation(current, rotation)
        settle_y, err = settle(rotated, column, board, n_cols, n_rows)
        if err is not None:
            cause = f'invalid placement ({err}) rot={rotation} col={column}'
            break

        cells_at = [(column + rx, settle_y + ry) for rx, ry in rotated]
        for c in cells_at:
            board.add(c)
        bottom_y = min(y for _, y in cells_at)
        pieces_placed += 1
        cells_filled = len(board)
        moves_log.append((rotation, column, settle_y))

        client.send(f"OK {bottom_y}\n")

        if idx == n - 1:
            cause = 'sequence exhausted'
            break

    # Always finish with ROUND_END.
    client.send(f"ROUND_END {pieces_placed} {cells_filled}\n")

    with results_lock:
        results[client.name] = {
            'pieces_placed': pieces_placed,
            'cells_filled': cells_filled,
            'elapsed': elapsed,
            'cause': cause,
            'last_resp_at': last_resp_at,
            'last_resp_raw': last_resp_raw,
            'moves': moves_log,    # list of (rotation, column, settle_y)
        }


# ── Tournament harness ───────────────────────────────────────────────────────

def rotate_log():
    if not os.path.exists(LOG_PATH):
        return
    n = 1
    while os.path.exists(f"{LOG_PATH}.{n}"):
        n += 1
    for i in range(n - 1, 0, -1):
        os.rename(f"{LOG_PATH}.{i}", f"{LOG_PATH}.{i + 1}")
    os.rename(LOG_PATH, f"{LOG_PATH}.1")


def run_tournament():
    rotate_log()
    log = open(LOG_PATH, 'w', encoding='utf-8')

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(32)
    server_sock.settimeout(1.0)

    clients = []
    print(f"[*] Server live on {HOST}:{PORT}. Registration: {REGISTRATION_WINDOW}s")
    log.write(f"[*] Server live on {HOST}:{PORT}.\n")
    distinct = len(set(map(tuple, SHAPES)))
    log.write(f"[*] X-heavy gnarly-pentomino catalog: {distinct} distinct shapes "
              f"(X×5, F×2, F'×2, W×1, U×1, T×1) sampled from a 12-slot weighted pool.\n\n")

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

    for round_num, (n_cols, n_rows) in enumerate(ROUND_DIMS, 1):
        # Deterministic per-round sequence so the log is reproducible.
        rng = random.Random(0xACE0 * round_num + 0x57AC)
        sequence = [rng.choice(SHAPES) for _ in range(SEQUENCE_LENGTH)]

        header = f"--- ROUND {round_num}: {n_cols} cols × {n_rows} rows ---"
        print(header)
        log.write(header + "\n")

        # Log the full piece sequence for the round so the moves can be
        # replayed offline. Format: SEQUENCE <piece1>;<piece2>;... where each
        # piece is its base-orientation cells joined by '|', e.g.
        # SEQUENCE 0,0|1,0;0,0|0,1|1,0;...
        sequence_str = ';'.join(
            '|'.join(f'{x},{y}' for x, y in shape) for shape in sequence
        )
        log.write(f"SEQUENCE {len(sequence)} {sequence_str}\n")

        # Send round start.
        for c in clients:
            c.send(f"ROUND {round_num} {n_cols} {n_rows}\n")

        # Run bot rounds in parallel.
        results = {}
        results_lock = threading.Lock()

        threads = [
            threading.Thread(
                target=run_bot_round,
                args=(c, sequence, n_cols, n_rows,
                      results, results_lock),
                daemon=True,
            )
            for c in clients
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=ROUND_BUDGET + 5)

        # Rank by (pieces desc, cells desc, last_resp_at asc).
        bot_results = []
        for c in clients:
            r = results.get(c.name)
            if r is None:
                # Round thread hung past join timeout — treat as no submission.
                r = {
                    'pieces_placed': 0, 'cells_filled': 0, 'elapsed': ROUND_BUDGET + 5,
                    'cause': 'thread hung', 'last_resp_at': float('inf'),
                    'last_resp_raw': None,
                }
                results[c.name] = r
            bot_results.append((c, r))

        bot_results.sort(key=lambda kv: (
            -kv[1]['pieces_placed'],
            -kv[1]['cells_filled'],
            kv[1]['last_resp_at'],
        ))

        for rank, (c, r) in enumerate(bot_results):
            pts = POINTS_BY_RANK[rank] if rank < len(POINTS_BY_RANK) else 0
            c.score += pts

        # Print + log per-round table.
        for rank, (c, r) in enumerate(bot_results):
            pts = POINTS_BY_RANK[rank] if rank < len(POINTS_BY_RANK) else 0
            line = (f"  #{rank + 1}  {c.name:<24} | placed={r['pieces_placed']:>3}"
                    f" | filled={r['cells_filled']:>4}"
                    f" | elapsed={r['elapsed']:6.2f}s"
                    f" | +{pts:>2} | total: {c.score}"
                    f" | {r['cause']}")
            print(line)
            log.write(line + "\n")

        # Log per-bot move trace for offline visualization. Each entry is
        # rotation,column,settle_y; entries are space-separated.
        for c, r in bot_results:
            moves = r.get('moves', [])
            moves_str = ' '.join(f'{rot},{col},{sy}' for rot, col, sy in moves)
            log.write(f"  MOVES {c.name}: {moves_str}\n")

        log.write("\n")
        log.flush()
        time.sleep(0.5)

    # End of tournament.
    print("\n[*] Sending END.")
    for c in clients:
        c.send("END\n")

    banner = "=" * 60 + "\nFINAL TOURNAMENT RESULTS\n" + "=" * 60
    print("\n" + banner)
    log.write("\n" + banner + "\n")
    for i, c in enumerate(sorted(clients, key=lambda c: -c.score)):
        line = f"  #{i + 1}  {c.name:<24} {c.score:>4} points"
        print(line)
        log.write(line + "\n")

    log.close()
    server_sock.close()
    for c in clients:
        c.close()


if __name__ == "__main__":
    run_tournament()
