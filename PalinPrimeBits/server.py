"""
PalinPrimeBits Tournament Server.

10 solo rounds. Each round, the server picks a 1-indexed integer n (per the
schedule below) and broadcasts `ROUND <round_num> <n>`. Each bot has 30 s
wall-clock to reply with `ANSWER <k>` where k is the length of the longest
contiguous block of binary 1 digits in p(n), the n-th palindromic prime.

The server does not enumerate palindromic primes at runtime. Answers are
precomputed offline (by compute_palprimes.py) and loaded from answers.txt.

Per-round ranking → points: 1st=10, 2nd=7, 3rd=5, 4th=3, 5th=1, 6th+=0.
Among correct submissions, rank by earliest end_ts (submission timestamp).
Wrong / malformed / timeout submissions score 0.
"""
import os
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
ANSWERS_PATH = 'answers.txt'

# Per-round n. Must match the n values precomputed in answers.txt.
ROUND_SCHEDULE = [5000, 10000, 20000, 30000, 50000, 75000, 100000, 250000, 500000, 1000000]
assert len(ROUND_SCHEDULE) == N_ROUNDS
for n in ROUND_SCHEDULE:
    assert 1 <= n <= 1_000_000, \
        f"round n={n} outside the bound advertised in prompt.md §2"

POINTS_BY_RANK = (10, 7, 5, 3, 1)


# ── Answer loading ───────────────────────────────────────────────────────────

def load_answers(path):
    """Parse answers.txt: one line per scheduled n, `<n> <p(n)> <longest_1_run>`.
    Returns dict n → (p, longest_1_run)."""
    answers = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            parts = line.split()
            if len(parts) != 3:
                continue
            n, p, k = int(parts[0]), int(parts[1]), int(parts[2])
            answers[n] = (p, k)
    return answers


# ── Submission parsing & validation ──────────────────────────────────────────

ANSWER_LINE_RE = re.compile(r'^ANSWER (0|[1-9][0-9]*)$')


def validate_submission(line, correct_k):
    """Parse and check the bot's ANSWER line.
    Returns (ok, info). On success info is (k, correct_k). On failure
    info is the INVALID reason token ('malformed' or 'wrong')."""
    s = line.rstrip('\n') if line is not None else ''
    m = ANSWER_LINE_RE.match(s)
    if not m:
        return False, "malformed"
    k = int(m.group(1))
    if k != correct_k:
        return False, "wrong"
    return True, (k, correct_k)


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
        self.round_results = []   # per-round (ok, info_or_reason, elapsed)
        self.first_place_count = 0
        self.total_correct_time = 0.0   # sum of elapsed across correct rounds

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
    """Read a single line from the client by deadline. Returns
    (line, end_ts, error_or_None). On timeout returns (None, end_ts, 'timeout')."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None, time.monotonic(), "timeout"
    try:
        line = client.readline(timeout=remaining)
    except (socket.timeout, OSError):
        return None, time.monotonic(), "timeout"
    if line is None or line == '':
        return None, time.monotonic(), "timeout"
    return line, time.monotonic(), None


def run_round(round_idx, n_value, correct_k, p_value, clients, log, log_lock):
    with log_lock:
        log.write(f"\n========== ROUND {round_idx} (n={n_value}) ==========\n")
        log.write(f"p({n_value})={p_value}  binary={bin(p_value)[2:]}  "
                  f"longest_1_run={correct_k}\n")
        log.flush()
    print(f"\n[*] Round {round_idx}: n={n_value}, "
          f"p={p_value} ({p_value.bit_length()} bits), correct_k={correct_k}, "
          f"sending to {len(clients)} bots.")

    for c in clients:
        c.send(f"ROUND {round_idx} {n_value}\n")
    t_round_start = time.monotonic()

    results = {}
    results_lock = threading.Lock()

    def worker(c):
        deadline = t_round_start + ROUND_BUDGET
        line, end_ts, err = collect_submission(c, deadline)
        if err is not None:
            with results_lock:
                results[c] = (False, err, end_ts, None)
            return
        ok, info = validate_submission(line, correct_k)
        with results_lock:
            results[c] = (ok, info, end_ts, line.rstrip('\n'))

    threads = [threading.Thread(target=worker, args=(c,), daemon=True)
               for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=ROUND_BUDGET + 5.0)

    log_lines = []
    valid_pairs = []   # (client, end_ts, raw_line)
    for c in clients:
        ok, info, end_ts, raw = results.get(
            c, (False, "no_response", time.monotonic(), None))
        elapsed = end_ts - t_round_start
        if ok:
            k_submitted, _ = info
            valid_pairs.append((c, end_ts, raw))
            c.send(f"OK {correct_k}\n")
            c.round_results.append((True, k_submitted, elapsed))
            c.total_correct_time += elapsed
            log_lines.append(
                f"  {c.name:<32} t={elapsed:6.3f}s  OK    k={k_submitted}")
        else:
            c.send(f"INVALID {info}\n")
            c.round_results.append((False, info, elapsed))
            raw_repr = '' if raw is None else raw
            log_lines.append(
                f"  {c.name:<32} t={elapsed:6.3f}s  INVALID  {info}  "
                f"raw={raw_repr!r}")

    for c in clients:
        c.send(f"END_ROUND {round_idx}\n")

    # Rank among correct submissions by earliest end_ts.
    valid_pairs.sort(key=lambda x: x[1])
    rank_log = []
    for slot, (c, end_ts, _) in enumerate(valid_pairs):
        rank = slot + 1
        pts = POINTS_BY_RANK[slot] if slot < len(POINTS_BY_RANK) else 0
        c.points += pts
        if rank == 1:
            c.first_place_count += 1
        rank_log.append(f"    #{rank}  {c.name}  "
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

    answers_path = ANSWERS_PATH
    if not os.path.isabs(answers_path):
        answers_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), answers_path)
    print(f"[*] Loading answers from {answers_path}")
    answers = load_answers(answers_path)
    for n in ROUND_SCHEDULE:
        if n not in answers:
            print(f"[!] answers.txt is missing n={n}. "
                  f"Run compute_palprimes.py first.")
            log.close()
            return
    print(f"[*] Loaded {len(answers)} precomputed answers.")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(32)
    server_sock.settimeout(1.0)

    clients = []
    print(f"[*] PalinPrimeBits server live on {HOST}:{PORT}. "
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
    log.write(f"Schedule: {ROUND_SCHEDULE}\n\n")
    log.flush()

    for round_idx, n_value in enumerate(ROUND_SCHEDULE, 1):
        p_value, correct_k = answers[n_value]
        run_round(round_idx, n_value, correct_k, p_value, clients, log, log_lock)

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
        n_correct = sum(1 for r in c.round_results if r[0])
        line = (f"  #{rank:<3}  {c.name:<30}  {c.points:>3}    "
                f"{c.first_place_count:>3}    "
                f"{n_correct:>3}/{N_ROUNDS}    "
                f"{c.total_correct_time:>7.3f}s")
        print(line)
        log.write(line + "\n")

    log.write("\n========== PER-BOT ROUND DETAIL ==========\n")
    for c in clients:
        cells = []
        for ok, info, elapsed in c.round_results:
            if ok:
                cells.append(f"OK({info},{elapsed:.2f}s)")
            else:
                cells.append(f"{info}({elapsed:.2f}s)")
        log.write(f"  {c.name:<32}  [{', '.join(cells)}]\n")

    log.close()
    for c in clients:
        c.close()
    server_sock.close()


if __name__ == '__main__':
    run_tournament()
