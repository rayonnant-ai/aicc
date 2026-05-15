"""
CollectTheDots Tournament Server.

10 solo rounds. Each round, the server generates a w × h rectangle with N
clustered dots at integer coordinates, broadcasts the layout, and reads each
bot's circle covering within a 30-second wall-clock budget. The bot's
submission is valid if every dot is covered by at least one circle, every
circle lies inside the rectangle, and no two circles overlap. The round
score is the number of circles; lower is better.

Per-round ranking → points: 1st=10, 2nd=7, 3rd=5, 4th=3, 5th=1, 6th+=0.
Ties on circle count break by earliest submission timestamp.
"""
import math
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
ROUND_BUDGET = 30.0
N_ROUNDS = 10
LOG_PATH = 'results.log'

# (w, h, n_dots, n_clusters, cluster_sigma) per round. Internal-only — bots
# see only the per-round dimensions at round start.
ROUND_PLAN = [
    (120,  80,  50,  5,  5.0),
    (100, 150,  60,  6,  6.0),
    (180, 110,  70,  7,  6.5),
    (130, 200,  80,  8,  7.5),
    (240, 140,  85,  9,  8.5),
    (160, 250,  90, 10,  9.5),
    (270, 170,  95, 11, 10.0),
    (190, 280, 100, 12, 10.5),
    (290, 200, 100, 14, 11.0),
    (220, 300, 100, 16, 11.5),
]
assert len(ROUND_PLAN) == N_ROUNDS
for w, h, n, k, _ in ROUND_PLAN:
    assert 30 <= w <= 300 and 30 <= h <= 300 and 5 <= n <= 100, \
        f"round ({w},{h},N={n}) outside the bounds advertised in prompt.md §2"
    assert 1 <= k <= n

POINTS_BY_RANK = (10, 7, 5, 3, 1)

EPSILON = 1e-6


# ── Round generation ─────────────────────────────────────────────────────────

def generate_round(w, h, n, k, sigma, seed):
    """Generate n dots in [1, w-1] × [1, h-1] arranged into k Gaussian clusters.
    Returns list of (x, y) tuples (integer coordinates)."""
    rng = random.Random(seed)
    margin = 3
    centers = []
    for _ in range(k):
        cx = rng.uniform(margin + sigma, w - margin - sigma)
        cy = rng.uniform(margin + sigma, h - margin - sigma)
        centers.append((cx, cy))

    dots = []
    while len(dots) < n:
        # Round-robin assignment with jitter so clusters are roughly balanced.
        cx, cy = centers[len(dots) % k]
        x = int(round(rng.gauss(cx, sigma)))
        y = int(round(rng.gauss(cy, sigma)))
        x = max(1, min(w - 1, x))
        y = max(1, min(h - 1, y))
        dots.append((x, y))
    return dots


# ── Validation ───────────────────────────────────────────────────────────────

NUM_RE = r'-?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?'
CIRCLE_LINE_RE = re.compile(rf'^CIRCLE ({NUM_RE}) ({NUM_RE}) ({NUM_RE})$')


def parse_circle_line(line):
    """Return (cx, cy, r) or None on malformed."""
    s = line.rstrip('\n')
    m = CIRCLE_LINE_RE.match(s)
    if not m:
        return None
    try:
        cx = float(m.group(1))
        cy = float(m.group(2))
        r = float(m.group(3))
    except ValueError:
        return None
    return (cx, cy, r)


def validate_submission(circle_lines, dots, w, h):
    """Parse and validate. Returns (ok, info).
    On success info is the integer circle count.
    On failure info is the INVALID reason token."""
    circles = []  # list of (cx, cy, r)
    for i, line in enumerate(circle_lines):
        parsed = parse_circle_line(line)
        if parsed is None:
            return False, f"malformed_circle_{i}"
        cx, cy, r = parsed
        if r <= 0:
            return False, f"bad_radius_{i}"
        if (cx - r < -EPSILON or cx + r > w + EPSILON or
                cy - r < -EPSILON or cy + r > h + EPSILON):
            return False, f"out_of_bounds_{i}"
        circles.append((cx, cy, r))

    if not circles:
        return False, "empty_submission"

    # Pairwise non-overlap check.
    for i in range(len(circles)):
        for j in range(i + 1, len(circles)):
            cx_i, cy_i, r_i = circles[i]
            cx_j, cy_j, r_j = circles[j]
            dx = cx_i - cx_j
            dy = cy_i - cy_j
            dist = math.hypot(dx, dy)
            if dist < r_i + r_j - EPSILON:
                return False, f"overlap_{i}_{j}"

    # Every dot covered.
    for idx, (x, y) in enumerate(dots):
        covered = False
        for (cx, cy, r) in circles:
            if math.hypot(x - cx, y - cy) <= r + EPSILON:
                covered = True
                break
        if not covered:
            return False, f"uncovered_dot_{idx}"

    return True, len(circles)


# ── Client wrapper ───────────────────────────────────────────────────────────

class Client:
    def __init__(self, sock, name, f=None):
        self.sock = sock
        self.name = name
        if f is None:
            f = sock.makefile('r', encoding='utf-8', errors='replace',
                              newline='')
        self.f = f
        self.points = 0
        self.round_counts = []   # circle count per round (None if INVALID)
        self.first_place_count = 0
        self.total_correct_time = 0.0

    def send(self, data):
        try:
            self.sock.sendall(data.encode('utf-8'))
        except OSError:
            pass

    def readline(self, timeout):
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


# ── Round driver ─────────────────────────────────────────────────────────────

def collect_submission(client, deadline):
    """Read CIRCLE lines until END or deadline. Returns
    (circle_lines, end_ts, error_or_None)."""
    circle_lines = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, time.monotonic(), "timeout"
        try:
            line = client.readline(timeout=remaining)
        except (socket.timeout, OSError):
            return None, time.monotonic(), "timeout"
        if line is None or line == '':
            return None, time.monotonic(), "timeout"
        s = line.rstrip('\n')
        if s == 'END':
            return circle_lines, time.monotonic(), None
        circle_lines.append(s)


def run_round(round_idx, w, h, n, k, sigma, clients, log, log_lock):
    seed = round_idx * 1000003
    dots = generate_round(w, h, n, k, sigma, seed)

    with log_lock:
        log.write(f"\n========== ROUND {round_idx} "
                  f"({w}×{h}, N={n}, {k} clusters, σ={sigma}) ==========\n")
        log.write(f"seed={seed}\n")
        log.write("dots: ")
        log.write(', '.join(f"{i}=({x},{y})"
                            for i, (x, y) in enumerate(dots)) + "\n")
        log.flush()
    print(f"\n[*] Round {round_idx}: {w}×{h}, N={n}, "
          f"k={k} clusters, σ={sigma:.1f}, seed={seed}.")

    for c in clients:
        c.send(f"ROUND {round_idx} {w} {h} {n}\n")
        for i, (x, y) in enumerate(dots):
            c.send(f"DOT {i} {x} {y}\n")
    t_round_start = time.monotonic()

    results = {}
    results_lock = threading.Lock()

    def worker(c):
        deadline = t_round_start + ROUND_BUDGET
        circle_lines, end_ts, err = collect_submission(c, deadline)
        if err is not None:
            with results_lock:
                results[c] = (False, err, end_ts, None)
            return
        ok, info = validate_submission(circle_lines, dots, w, h)
        with results_lock:
            results[c] = (ok, info, end_ts, circle_lines)

    threads = [threading.Thread(target=worker, args=(c,), daemon=True)
               for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=ROUND_BUDGET + 5.0)

    log_lines = []
    valid_pairs = []  # (client, circle_count, end_ts, raw_lines)
    for c in clients:
        ok, info, end_ts, raw = results.get(
            c, (False, "no_response", time.monotonic(), None))
        elapsed = end_ts - t_round_start
        if ok:
            circle_count = info
            valid_pairs.append((c, circle_count, end_ts, raw))
            c.send(f"OK {circle_count}\n")
            c.round_counts.append(circle_count)
            c.total_correct_time += elapsed
            log_lines.append(
                f"  {c.name:<36} t={elapsed:6.3f}s  OK  "
                f"circles={circle_count}")
            if raw:
                for cl in raw:
                    log_lines.append(f"      {cl}")
        else:
            c.send(f"INVALID {info}\n")
            c.round_counts.append(None)
            log_lines.append(
                f"  {c.name:<36} t={elapsed:6.3f}s  INVALID  {info}")
            if raw:
                for cl in raw[:3]:
                    log_lines.append(f"      {cl}")

    for c in clients:
        c.send(f"END_ROUND {round_idx}\n")

    # Rank by circle_count ascending; tie-break by earliest end_ts.
    valid_pairs.sort(key=lambda x: (x[1], x[2]))
    rank_log = []
    for slot, (c, cc, end_ts, _) in enumerate(valid_pairs):
        rank = slot + 1
        pts = POINTS_BY_RANK[slot] if slot < len(POINTS_BY_RANK) else 0
        c.points += pts
        if rank == 1:
            c.first_place_count += 1
        rank_log.append(f"    #{rank}  {c.name}  circles={cc}  "
                        f"t={end_ts - t_round_start:6.3f}s  +{pts} pts")

    with log_lock:
        for line in log_lines:
            log.write(line + "\n")
        log.write("  results:\n")
        for line in rank_log:
            log.write(line + "\n")
        log.flush()

    print("  results:")
    for line in rank_log:
        print(line)


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
    log_lock = threading.Lock()

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(32)
    server_sock.settimeout(1.0)

    clients = []
    print(f"[*] CollectTheDots server live on {HOST}:{PORT}. "
          f"Registration window: {REGISTRATION_WINDOW}s")

    name_re = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
    start_reg = time.time()
    while time.time() - start_reg < REGISTRATION_WINDOW:
        try:
            conn, addr = server_sock.accept()
            conn.settimeout(None)
            f = conn.makefile('r', encoding='utf-8', errors='replace',
                              newline='')
            raw = f.readline()
            name = raw[:-1] if raw.endswith('\n') else raw
            if not name_re.match(name):
                print(f"[!] Rejected name {name!r} from {addr}; closing.")
                try:
                    conn.close()
                except OSError:
                    pass
                continue
            c = Client(conn, name, f=f)
            clients.append(c)
            print(f"[*] Bot '{name}' joined.")
        except socket.timeout:
            continue

    if len(clients) < 1:
        print("[!] No bots registered.")
        log.close()
        server_sock.close()
        return

    print(f"[*] {len(clients)} bots registered.")
    log.write(f"Tournament: {len(clients)} bots, {N_ROUNDS} rounds.\n")
    log.write(f"Bots: {', '.join(c.name for c in clients)}\n")
    log.write(f"Plan: {ROUND_PLAN}\n\n")
    log.flush()

    for round_idx, (w, h, n, k, sigma) in enumerate(ROUND_PLAN, 1):
        run_round(round_idx, w, h, n, k, sigma, clients, log, log_lock)

    print("\n[*] Tournament complete. Sending TOURNAMENT_END.")
    for c in clients:
        c.send("TOURNAMENT_END\n")

    log.write("\n========== FINAL STANDINGS ==========\n")
    final = sorted(
        clients,
        key=lambda c: (-c.points, -c.first_place_count, c.total_correct_time),
    )
    header = "  rank  bot                            pts   1sts  correct  total_t"
    print(header)
    log.write(header + "\n")
    for rank, c in enumerate(final, 1):
        n_correct = sum(1 for r in c.round_counts if r is not None)
        line = (f"  #{rank:<3}  {c.name:<30}  {c.points:>3}    "
                f"{c.first_place_count:>3}    "
                f"{n_correct:>3}/{N_ROUNDS}    "
                f"{c.total_correct_time:>7.2f}s")
        print(line)
        log.write(line + "\n")

    log.write("\n========== PER-BOT ROUND CIRCLES ==========\n")
    for c in clients:
        cells = ', '.join('--' if r is None else str(r)
                          for r in c.round_counts)
        log.write(f"  {c.name:<36}  [{cells}]\n")

    log.close()
    for c in clients:
        c.close()
    server_sock.close()


if __name__ == '__main__':
    run_tournament()
