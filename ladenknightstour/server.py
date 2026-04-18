"""
Laden Knight's Tour Tournament Server.

Generates weighted boards of increasing size, sends them to bots over TCP,
validates tours, scores by total elapsed time (lowest wins, ties broken
by submission order).
"""
import socket
import threading
import time
import random
import json
import os

HOST = 'localhost'
PORT = 7474
REGISTRATION_WINDOW = 10.0
ROUND_TIMEOUT = 10.0
LOG_PATH = 'results.log'

# Round-by-round board dimensions. Every entry satisfies the solvability
# conditions: (m <= n), no (m=1 or 2), no (m=3 with n in {3,5,6}),
# no (m=4 with n=4).
BOARD_SIZES = [
    (3, 4),   # round  1: 12 squares
    (4, 5),   # round  2: 20
    (4, 6),   # round  3: 24
    (5, 5),   # round  4: 25
    (5, 6),   # round  5: 30
    (6, 6),   # round  6: 36
    (6, 7),   # round  7: 42
    (7, 7),   # round  8: 49
    (7, 8),   # round  9: 56
    (8, 8),   # round 10: 64
]
MAX_ROUNDS = len(BOARD_SIZES)

POINTS_BY_RANK = [10, 7, 5, 3, 1, 0]

# Heavy-tailed weight distribution: mostly light squares with occasional spikes.
LIGHT_PROB = 0.80
LIGHT_RANGE = (1, 3)
HEAVY_RANGE = (10, 50)

KNIGHT_DELTAS = [(-2, -1), (-2, 1), (-1, -2), (-1, 2),
                 (1, -2), (1, 2), (2, -1), (2, 1)]


# ─── Board Generation ────────────────────────────────────────────────────────

def generate_weights(rows, cols):
    weights = []
    for _ in range(rows):
        row = []
        for _ in range(cols):
            if random.random() < LIGHT_PROB:
                w = random.randint(*LIGHT_RANGE)
            else:
                w = random.randint(*HEAVY_RANGE)
            row.append(w)
        weights.append(row)
    return weights


# ─── Tour Validation ─────────────────────────────────────────────────────────

def validate_tour(tour, rows, cols):
    expected = rows * cols
    if not isinstance(tour, list):
        return False, "tour field is not a list"
    if len(tour) != expected:
        return False, f"tour has {len(tour)} squares, expected {expected}"
    seen = set()
    prev = None
    for i, pos in enumerate(tour):
        if not isinstance(pos, (list, tuple)) or len(pos) != 2:
            return False, f"malformed entry at index {i}"
        try:
            r = int(pos[0])
            c = int(pos[1])
        except (ValueError, TypeError):
            return False, f"non-integer coordinates at index {i}"
        if not (0 <= r < rows and 0 <= c < cols):
            return False, f"square ({r},{c}) off the {rows}x{cols} board"
        if (r, c) in seen:
            return False, f"square ({r},{c}) visited more than once"
        seen.add((r, c))
        if prev is not None:
            pr, pc = prev
            dr = abs(r - pr)
            dc = abs(c - pc)
            if sorted((dr, dc)) != [1, 2]:
                return False, f"illegal move from ({pr},{pc}) to ({r},{c})"
        prev = (r, c)
    return True, "OK"


def compute_tour_time(tour, weights):
    total = 0
    load = 0
    n = len(tour)
    for i, pos in enumerate(tour):
        r, c = int(pos[0]), int(pos[1])
        load += weights[r][c]
        if i < n - 1:
            total += load
    return total


# ─── Client Handling ─────────────────────────────────────────────────────────

class Client:
    def __init__(self, sock, name):
        self.sock = sock
        self.name = name
        self.score = 0
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


# ─── Tournament ──────────────────────────────────────────────────────────────

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

    if not clients:
        print("[!] No participants.")
        log.close()
        return

    print(f"[*] {len(clients)} bots registered. Starting tournament.\n")

    for round_num in range(1, MAX_ROUNDS + 1):
        rows, cols = BOARD_SIZES[round_num - 1]
        weights = generate_weights(rows, cols)

        payload = json.dumps({"rows": rows, "cols": cols, "weights": weights})
        payload_bytes = len(payload.encode('utf-8'))

        header = f"--- ROUND {round_num}: {rows}x{cols} ({rows * cols} squares) ---"
        print(header)
        log.write(header + "\n")
        log.write("WEIGHTS:\n")
        for row in weights:
            log.write("  " + " ".join(f"{w:>3}" for w in row) + "\n")
        log.write("\n")

        round_start = time.monotonic()

        for client in clients:
            client.send(f"ROUND {round_num}\n")
            client.send(f"SIZE {payload_bytes}\n")
            client.send(payload)

        results = {}    # name -> (total_time, elapsed_ms, status)
        solutions = {}  # name -> tour
        result_lock = threading.Lock()

        def collect_response(client):
            response = client.readline(timeout=ROUND_TIMEOUT)
            elapsed = (time.monotonic() - round_start) * 1000

            if response is None:
                status = "TIMEOUT"
                with result_lock:
                    results[client.name] = (None, elapsed, status)
                try:
                    client.send(f"{status}\n")
                except OSError:
                    pass
                return

            try:
                answer = json.loads(response)
                tour = answer.get("tour", [])
                valid, msg = validate_tour(tour, rows, cols)
                if valid:
                    total = compute_tour_time(tour, weights)
                    with result_lock:
                        results[client.name] = (total, elapsed, "VALID")
                        solutions[client.name] = tour
                    client.send(f"VALID {total}\n")
                else:
                    with result_lock:
                        results[client.name] = (None, elapsed, f"INVALID: {msg}")
                        solutions[client.name] = tour
                    client.send(f"INVALID {msg}\n")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                with result_lock:
                    results[client.name] = (None, elapsed, f"INVALID: parse error: {e}")
                client.send("INVALID parse error\n")

        threads = []
        for client in clients:
            t = threading.Thread(target=collect_response, args=(client,), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=ROUND_TIMEOUT + 5)

        # Rank valid responses by (total_time, elapsed_ms).
        valid_results = [(name, tt, ms) for name, (tt, ms, _) in results.items()
                         if tt is not None]
        valid_results.sort(key=lambda x: (x[1], x[2]))

        for rank, (name, tt, ms) in enumerate(valid_results):
            pts = POINTS_BY_RANK[rank] if rank < len(POINTS_BY_RANK) else 0
            for c in clients:
                if c.name == name:
                    c.score += pts

        # Log sorted by (time, then submission ms).
        def sort_key(item):
            _, (tt, ms, _) = item
            return (tt if tt is not None else float('inf'), ms)

        for name, (tt, ms, status) in sorted(results.items(), key=sort_key):
            client_score = next(c.score for c in clients if c.name == name)
            if tt is not None:
                rank = next((i + 1 for i, (n, _, _) in enumerate(valid_results) if n == name), 0)
                pts = POINTS_BY_RANK[rank - 1] if rank <= len(POINTS_BY_RANK) else 0
                line = f"  {name:<20} | time={tt:>7} | {ms:>7.0f}ms | +{pts:>2} | total: {client_score}"
            else:
                line = f"  {name:<20} | {status:<40} | {ms:>7.0f}ms | + 0 | total: {client_score}"
            print(line)
            log.write(line + "\n")

        log.write("\nTOURS:\n")
        for name in sorted(solutions.keys()):
            tt = results[name][0]
            status = "VALID" if tt is not None else results[name][2]
            tour = solutions[name]
            suffix = f", time={tt}" if tt is not None else ""
            log.write(f"  {name} ({status}{suffix}):\n")
            log.write(f"    {json.dumps(tour)}\n")
        log.write("\n")
        log.flush()
        time.sleep(1)

    banner = "=" * 60 + "\nFINAL TOURNAMENT RESULTS\n" + "=" * 60
    print("\n" + banner)
    log.write("\n" + banner + "\n")

    for i, client in enumerate(sorted(clients, key=lambda c: -c.score)):
        line = f"  #{i + 1}  {client.name:<20} {client.score:>3} points"
        print(line)
        log.write(line + "\n")

    log.close()
    server_sock.close()
    for c in clients:
        c.close()


if __name__ == "__main__":
    run_tournament()
