"""
WarehouseRobot Tournament Server.

10 solo rounds. Each round, the server generates a random warehouse layout
of size w×h meters with N items at random integer (x, y) bin locations
(none at the depot (0,0)) and random integer weights, broadcasts the
layout, and reads each bot's offline trip plan within a 30-second
wall-clock budget.

Speed function (per the spec): max(0, 10 - load_kg // 10) m/min, with
≥ 100 kg meaning stuck. The robot starts every trip at (0, 0) with
load 0, visits items in TRIP order, and returns to (0, 0) to unload.

Per-round score = total time across all trips (lower better). Ranking
points 10/7/5/3/1/0 to top 6.
"""
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

# (warehouse_w, warehouse_h, n_items) per round. Internal-only — the bot
# is told the per-round dimensions at round start, never the full schedule.
ROUND_PLAN = [
    (30,  30,    20),
    (50,  50,    30),
    (70,  70,    45),
    (90,  90,    65),
    (110, 110,   90),
    (130, 130,  120),
    (150, 150,  150),
    (170, 170,  180),
    (190, 190,  215),
    (200, 200,  250),
]
assert len(ROUND_PLAN) == N_ROUNDS
for w, h, n in ROUND_PLAN:
    assert 30 <= w <= 200 and 30 <= h <= 200 and 1 <= n <= 300, \
        f"round ({w}, {h}, {n}) outside the bounds advertised in prompt.md §2"

POINTS_BY_RANK = (10, 7, 5, 3, 1)

WEIGHT_MIN_KG = 1
WEIGHT_MAX_KG = 25


# ── Speed function ───────────────────────────────────────────────────────────

def speed_for_load(load_kg):
    """m/min as a function of carried weight. 0 means stuck."""
    if load_kg >= 100:
        return 0
    return 10 - (load_kg // 10)


# ── Round generation ─────────────────────────────────────────────────────────

def generate_round(round_idx, w, h, n, seed):
    """Generate N items at random integer (x, y) in [0, w] × [0, h] with
    integer weights in [WEIGHT_MIN_KG, WEIGHT_MAX_KG]. Excludes the depot
    at (0, 0). Multiple items can share a bin (same x, y).
    Returns list of (x, y, weight)."""
    rng = random.Random(seed)
    items = []
    while len(items) < n:
        x = rng.randint(0, w)
        y = rng.randint(0, h)
        if x == 0 and y == 0:
            continue   # forbidden: items at depot
        wt = rng.randint(WEIGHT_MIN_KG, WEIGHT_MAX_KG)
        items.append((x, y, wt))
    return items


# ── Simulation ───────────────────────────────────────────────────────────────

def simulate_trip(trip_indices, items):
    """Simulate one trip: robot visits items in order, returns to (0, 0).
    Returns (ok, time_minutes_or_reason). Reason format on failure is a
    suffix; the caller prepends `_at_trip_<i>`.
    """
    pos_x, pos_y = 0, 0
    load = 0
    t = 0.0
    for slot, idx in enumerate(trip_indices):
        ix, iy, iw = items[idx]
        d = abs(ix - pos_x) + abs(iy - pos_y)
        if d > 0:
            sp = speed_for_load(load)
            if sp <= 0:
                return False, f"leg_{slot}_load_{load}"
            t += d / sp
        pos_x, pos_y = ix, iy
        load += iw
    # Return to origin.
    d = abs(pos_x) + abs(pos_y)
    if d > 0:
        sp = speed_for_load(load)
        if sp <= 0:
            return False, f"leg_return_load_{load}"
        t += d / sp
    return True, t


def simulate_submission(trips, items):
    """Run all trips. Returns (ok, total_time_or_reason)."""
    total = 0.0
    for ti, trip in enumerate(trips):
        ok, info = simulate_trip(trip, items)
        if not ok:
            return False, f"stuck_at_trip_{ti}_{info}"
        total += info
    return True, total


# ── Submission parsing & validation ──────────────────────────────────────────

# Each item index is a non-negative decimal int with no leading zeros (except '0').
TRIP_LINE_RE = re.compile(r'^TRIP((?: (?:0|[1-9][0-9]*))+)$')


def parse_trip_line(line):
    """Return list[int] or None on malformed."""
    s = line.rstrip('\n')
    if s == 'TRIP' or s.startswith('TRIP '):
        m = TRIP_LINE_RE.match(s)
        if not m:
            # Distinguish "TRIP " with no indices (empty_trip) from malformed.
            if s == 'TRIP' or s.rstrip() == 'TRIP':
                return 'empty'
            return None
        return [int(t) for t in m.group(1).split()]
    return None


def validate_submission(trip_lines, items):
    """Parse trip lines, check coverage, simulate. Returns (ok, info)."""
    n_items = len(items)
    trips = []
    seen = set()
    for ti, line in enumerate(trip_lines):
        parsed = parse_trip_line(line)
        if parsed is None:
            return False, f"malformed_trip_{ti}"
        if parsed == 'empty':
            return False, f"empty_trip_{ti}"
        for slot, idx in enumerate(parsed):
            if idx < 0 or idx >= n_items:
                return False, f"bad_item_{ti}_{slot}"
            if idx in seen:
                return False, f"duplicate_item_{idx}"
            seen.add(idx)
        trips.append(parsed)
    if len(seen) != n_items:
        missing = sorted(set(range(n_items)) - seen)
        return False, f"missing_item_{missing[0]}"
    return simulate_submission(trips, items)


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
        self.round_times = []          # per-round time or None if INVALID
        self.first_place_count = 0

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
    """Read TRIP lines until END. Returns (trip_lines, end_ts, error)."""
    trip_lines = []
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
            return trip_lines, time.monotonic(), None
        trip_lines.append(s)


def run_round(round_idx, w, h, n, clients, log, log_lock):
    seed = round_idx * 1000003
    items = generate_round(round_idx, w, h, n, seed)
    total_weight = sum(it[2] for it in items)

    with log_lock:
        log.write(f"\n========== ROUND {round_idx} ({w}×{h} m, "
                  f"N={n} items, total_weight={total_weight} kg) ==========\n")
        log.write(f"seed={seed}\n")
        log.write("items: ")
        log.write(', '.join(f"{i}=({x},{y},{wt}kg)"
                            for i, (x, y, wt) in enumerate(items)) + "\n")
        log.flush()
    print(f"\n[*] Round {round_idx}: {w}×{h}, {n} items, "
          f"total={total_weight} kg, seed={seed}.")

    # Send ROUND header + ITEM lines, *then* start the round-budget timer
    # (the spec measures the budget from "the moment the server has
    # finished sending all ITEM lines").
    for c in clients:
        c.send(f"ROUND {round_idx} {w} {h} {n}\n")
        for i, (x, y, wt) in enumerate(items):
            c.send(f"ITEM {i} {x} {y} {wt}\n")
    t_round_start = time.monotonic()

    results = {}
    results_lock = threading.Lock()

    def worker(c):
        deadline = t_round_start + ROUND_BUDGET
        trip_lines, end_ts, err = collect_submission(c, deadline)
        if err is not None:
            with results_lock:
                results[c] = (False, err, end_ts, None)
            return
        ok, info = validate_submission(trip_lines, items)
        with results_lock:
            results[c] = (ok, info, end_ts, trip_lines)

    threads = [threading.Thread(target=worker, args=(c,), daemon=True)
               for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=ROUND_BUDGET + 5.0)

    log_lines = []
    valid_pairs = []   # (client, time, end_ts, n_trips, raw_lines)
    for c in clients:
        ok, info, end_ts, raw = results.get(
            c, (False, "no_response", time.monotonic(), None))
        elapsed = end_ts - t_round_start
        if ok:
            total_time = info
            n_trips = len(raw) if raw else 0
            valid_pairs.append((c, total_time, end_ts, n_trips, raw))
            c.send(f"OK {total_time:.4f} {n_trips}\n")
            c.round_times.append(total_time)
            log_lines.append(
                f"  {c.name:<32} t={elapsed:5.2f}s  OK  "
                f"time={total_time:>9.4f}m  trips={n_trips}")
            for trip_line in raw:
                log_lines.append(f"      {trip_line}")
        else:
            c.send(f"INVALID {info}\n")
            c.round_times.append(None)
            log_lines.append(
                f"  {c.name:<32} t={elapsed:5.2f}s  INVALID  {info}")
            if raw:
                for trip_line in raw[:3]:
                    log_lines.append(f"      {trip_line}")

    for c in clients:
        c.send(f"END_ROUND {round_idx}\n")

    # Rank by total_time ascending; tie-break by earliest end_ts.
    valid_pairs.sort(key=lambda x: (x[1], x[2]))
    rank_log = []
    for slot, (c, t, end_ts, n_trips, _) in enumerate(valid_pairs):
        rank = slot + 1
        pts = POINTS_BY_RANK[slot] if slot < len(POINTS_BY_RANK) else 0
        c.points += pts
        if rank == 1:
            c.first_place_count += 1
        rank_log.append(f"    #{rank}  {c.name}  time={t:.4f}m  "
                        f"trips={n_trips}  t={end_ts - t_round_start:5.2f}s  "
                        f"+{pts} pts")

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
    print(f"[*] WarehouseRobot server live on {HOST}:{PORT}. "
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

    for round_idx, (w, h, n) in enumerate(ROUND_PLAN, 1):
        run_round(round_idx, w, h, n, clients, log, log_lock)

    print("\n[*] Tournament complete. Sending TOURNAMENT_END.")
    for c in clients:
        c.send("TOURNAMENT_END\n")

    log.write("\n========== FINAL STANDINGS ==========\n")
    final = sorted(
        clients,
        key=lambda c: (-c.points, -c.first_place_count,
                       sum((t for t in c.round_times if t is not None),
                           start=0.0)),
    )
    header = "  rank  bot                            pts   1sts  total_time"
    print(header)
    log.write(header + "\n")
    for rank, c in enumerate(final, 1):
        total = sum((t for t in c.round_times if t is not None), start=0.0)
        line = (f"  #{rank:<3}  {c.name:<30}  {c.points:>3}    "
                f"{c.first_place_count:>3}    {total:>9.2f}m")
        print(line)
        log.write(line + "\n")

    log.write("\n========== PER-BOT ROUND TIMES ==========\n")
    for c in clients:
        times = ', '.join('--' if t is None else f"{t:.2f}"
                          for t in c.round_times)
        log.write(f"  {c.name:<32}  [{times}]\n")

    log.close()
    for c in clients:
        c.close()
    server_sock.close()


if __name__ == '__main__':
    run_tournament()
