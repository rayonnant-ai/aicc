"""
Word Gem Puzzle Tournament Server.

Bots receive a w x h sliding-puzzle board with letters and one blank slot.
For 10 seconds of wall-clock time per round they may slide tiles into
the blank (4-directional) and claim words formed by adjacent (8-directional)
chains of distinct letter tiles on their personal copy of the board.

Each bot has an independent grid. Words are independent: every bot can score
the same word. Per-word: points = len(word) - 6.

Per-round rank awards 10/7/5/3/1/0 tournament points. Tournament total
decides the overall winner.

The server log records the starting grid for each round and every bot's
move + claim sequence so a visualizer can replay each bot's run.
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
ROUND_DURATION = 10.0   # wall-clock seconds per round, fixed
LOG_PATH = 'results.log'
DICT_PATH = 'dictionary.txt'

# Round-robin: every pair of registered bots plays one match. Each match is
# `MATCH_ROUNDS` rounds long; round dimensions cycle through MATCH_ROUND_DIMS.
MATCH_ROUNDS = 5
MATCH_ROUND_DIMS = [
    (10, 10),
    (15, 15),
    (20, 20),
    (25, 25),
    (30, 30)
]
MATCH_WIN_PTS = 3
MATCH_DRAW_PTS = 1

# (w, h) per round. Legacy from the all-vs-all format; kept here for
# reference but unused by the round-robin harness.
ROUND_DIMS = [
    (10, 10),
    (11, 10),
    (12, 10),
    (12, 11),
    (13, 11),
    (14, 12),
    (15, 12),
    (16, 13),
    (17, 13),
    (18, 14),
    (19, 15),
    (20, 15),
    (21, 16),
    (22, 17),
    (23, 17),
    (24, 18),
    (25, 19),
    (26, 20),
    (27, 21),
    (28, 22),
    (28, 23),
    (29, 24),
    (29, 26),
    (30, 28),
    (30, 30),
]
MAX_ROUNDS = len(ROUND_DIMS)

# Scrabble-tile-bag distribution (English, 100 tiles).
LETTER_FREQ = {
    'a': 9, 'b': 2, 'c': 2, 'd': 4, 'e': 12, 'f': 2, 'g': 3, 'h': 2,
    'i': 9, 'j': 1, 'k': 1, 'l': 4, 'm': 2, 'n': 6, 'o': 8, 'p': 2,
    'q': 1, 'r': 6, 's': 4, 't': 6, 'u': 4, 'v': 2, 'w': 2, 'x': 1,
    'y': 2, 'z': 1,
}
LETTER_POOL = list(LETTER_FREQ.keys())
LETTER_WEIGHTS = list(LETTER_FREQ.values())

# Strict bot-message grammars.
SLIDE_RE = re.compile(r'^S ([UDLR])$')
# Claim: 'W <word> <O> <r>,<c>'. Orientation is 'A' (across) or 'D' (down).
# (r,c) is the start cell of the word. Length is implicit from the word.
CLAIM_RE = re.compile(
    r'^W ([a-z]+) ([AD]) (0|[1-9][0-9]*),(0|[1-9][0-9]*)$'
)


# ── Dictionary ────────────────────────────────────────────────────────────────

def load_dictionary(path=DICT_PATH):
    if not os.path.exists(path):
        raise SystemExit(f"Dictionary not found: {path}")
    words = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            w = line.strip().lower()
            if w and w.isalpha() and len(w) >= 3:
                words.add(w)
    return words


# ── Grid generation ──────────────────────────────────────────────────────────

# Lazy cache: dictionary indexed by length, used for crossword pre-seeding.
_DICT_BY_LEN = None


def _build_dict_index(dictionary):
    by_len = {}
    for word in dictionary:
        n = len(word)
        if 4 <= n <= 30:
            by_len.setdefault(n, []).append(word)
    return by_len


def generate_grid(w, h, rng, dictionary):
    """Return (grid, blank_rc).

    Letters in the grid still follow an English-frequency distribution, but
    instead of being shuffled iid into random cells, they're placed as
    crossword fill: random across/down dictionary-word placements that
    overlap consistently. Any cells not covered by a placement are filled
    with letters sampled from the same English-frequency tile bag, then a
    random cell becomes the blank.

    Both placement-sourced and tile-bag-sourced letters preserve English
    letter proportions, so the spec's "English-frequency distribution"
    constraint is honored. The arrangement is no longer iid by cell, but
    the prompt only constrains the marginal distribution.
    """
    global _DICT_BY_LEN
    if _DICT_BY_LEN is None:
        _DICT_BY_LEN = _build_dict_index(dictionary)

    grid = [[None] * w for _ in range(h)]

    # Target ~half of cells to be part of a seeded word. With average word
    # length ~6 and intersections, target placements ≈ (w*h) // 12.
    target = max(5, (w * h) // 12)
    max_attempts = target * 8
    placed = 0
    max_word_len = min(w, h, 12)
    length_choices = [L for L in range(4, max_word_len + 1)
                      if L in _DICT_BY_LEN]

    if length_choices:
        for _ in range(max_attempts):
            if placed >= target:
                break
            orient = rng.choice(['A', 'D'])
            max_len = w if orient == 'A' else h
            usable = [L for L in length_choices if L <= max_len]
            if not usable:
                continue
            L = rng.choice(usable)
            word = rng.choice(_DICT_BY_LEN[L])
            if orient == 'A':
                r = rng.randrange(h)
                c = rng.randrange(w - L + 1)
            else:
                r = rng.randrange(h - L + 1)
                c = rng.randrange(w)
            cells = ([(r, c + i) for i in range(L)] if orient == 'A'
                     else [(r + i, c) for i in range(L)])
            ok = True
            for (rr, cc), letter in zip(cells, word):
                ex = grid[rr][cc]
                if ex is not None and ex != letter:
                    ok = False
                    break
            if not ok:
                continue
            for (rr, cc), letter in zip(cells, word):
                grid[rr][cc] = letter
            placed += 1

    # Fill any remaining empty cells with English-frequency letters.
    for r in range(h):
        for c in range(w):
            if grid[r][c] is None:
                grid[r][c] = rng.choices(LETTER_POOL, weights=LETTER_WEIGHTS)[0]

    # Place the blank at the center. Whatever letter the seed-fill put
    # there is overwritten.
    center_r, center_c = h // 2, w // 2
    blank_r, blank_c = center_r, center_c
    grid[blank_r][blank_c] = '_'

    # Scrambling:
    #   - max(w, h) < 20: X over the whole grid — visit each of the 4
    #     corners and return to center between visits.
    #   - max(w, h) >= 20: split the grid into 4 equal quadrants and run
    #     an X within each quadrant in turn. This pushes the scramble
    #     into the interior of the big grids (where pre-seeded words
    #     live), instead of just cycling letters along the outer edges.
    def _slide_to(blank_rc, target_rc):
        br, bc = blank_rc
        tr, tc = target_rc
        nonlocal grid
        while br != tr:
            nr = br + (1 if tr > br else -1)
            nc = bc
            grid[br][bc] = grid[nr][nc]
            grid[nr][nc] = '_'
            br, bc = nr, nc
        while bc != tc:
            nr = br
            nc = bc + (1 if tc > bc else -1)
            grid[br][bc] = grid[nr][nc]
            grid[nr][nc] = '_'
            br, bc = nr, nc
        return (br, bc)

    if max(w, h) < 20:
        for corner in [(0, 0), (h - 1, w - 1), (0, w - 1), (h - 1, 0)]:
            blank_r, blank_c = _slide_to((blank_r, blank_c), corner)
            blank_r, blank_c = _slide_to((blank_r, blank_c),
                                         (center_r, center_c))
    else:
        # Split into TL/TR/BL/BR quadrants and X-scramble each.
        half_h = h // 2
        half_w = w // 2
        quadrants = [
            (0, 0, half_h, half_w),                 # TL
            (0, half_w, half_h, w),                 # TR
            (half_h, 0, h, half_w),                 # BL
            (half_h, half_w, h, w),                 # BR
        ]
        for r0, c0, r1, c1 in quadrants:
            qcr = (r0 + r1 - 1) // 2
            qcc = (c0 + c1 - 1) // 2
            q_corners = [(r0, c0), (r0, c1 - 1),
                         (r1 - 1, c0), (r1 - 1, c1 - 1)]
            blank_r, blank_c = _slide_to((blank_r, blank_c), (qcr, qcc))
            for q_corner in q_corners:
                blank_r, blank_c = _slide_to((blank_r, blank_c), q_corner)
                blank_r, blank_c = _slide_to((blank_r, blank_c), (qcr, qcc))

    return grid, (blank_r, blank_c)


def grid_to_lines(grid):
    return '\n'.join(''.join(row) for row in grid)


# ── Slide ────────────────────────────────────────────────────────────────────

DIR_DELTAS = {'U': (-1, 0), 'D': (1, 0), 'L': (0, -1), 'R': (0, 1)}


def apply_slide(grid, blank_rc, direction, h, w):
    """Apply slide where `direction` is the way the blank moves.
    Returns (new_blank_rc, ok). If invalid, returns (blank_rc, False)."""
    dr, dc = DIR_DELTAS[direction]
    br, bc = blank_rc
    nr, nc = br + dr, bc + dc
    if not (0 <= nr < h and 0 <= nc < w):
        return blank_rc, False
    grid[br][bc], grid[nr][nc] = grid[nr][nc], grid[br][bc]
    return (nr, nc), True


# ── Word claim validation ────────────────────────────────────────────────────

def verify_placement(word, orient, r, c, grid, h, w):
    """Verify a crossword-style placement of `word` at orientation
    `orient` ∈ {'A','D'} starting at `(r, c)` on `grid`.

    Returns (ok, reason). On ok, reason is None.

    Failure precedence (matches prompt §5 closed table):
      oob_start → oob_end → cell_is_blank → letter_mismatch
    """
    if not (0 <= r < h and 0 <= c < w):
        return False, f'oob_start_{r},{c}'
    n = len(word)
    if orient == 'A':
        if c + n - 1 >= w:
            return False, f'oob_end_A_{r},{c}'
        for i in range(n):
            cell_r, cell_c = r, c + i
            ch = grid[cell_r][cell_c]
            if ch == '_':
                return False, f'cell_is_blank_{cell_r},{cell_c}'
            if ch != word[i]:
                return False, f'letter_mismatch_at_{cell_r},{cell_c}'
    elif orient == 'D':
        if r + n - 1 >= h:
            return False, f'oob_end_D_{r},{c}'
        for i in range(n):
            cell_r, cell_c = r + i, c
            ch = grid[cell_r][cell_c]
            if ch == '_':
                return False, f'cell_is_blank_{cell_r},{cell_c}'
            if ch != word[i]:
                return False, f'letter_mismatch_at_{cell_r},{cell_c}'
    else:
        return False, 'malformed'
    return True, None


def placement_cells(word, orient, r, c):
    """Return the list of (r, c) cells the placement occupies."""
    n = len(word)
    if orient == 'A':
        return [(r, c + i) for i in range(n)]
    return [(r + i, c) for i in range(n)]


# ── Client ───────────────────────────────────────────────────────────────────

class Client:
    def __init__(self, sock, name, f=None):
        self.sock = sock
        self.name = name
        self.score = 0
        # newline='' preserves \r\n so CRLF lines fail the strict regex match
        # and result in DQ malformed (per spec §2: "CRLF is invalid"). If a
        # makefile already exists from registration we reuse it to avoid
        # losing any prefetched bytes.
        if f is None:
            f = sock.makefile('r', encoding='utf-8', errors='replace',
                              newline='')
        self.f = f

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

    def drain(self):
        """Discard all pending input on this socket: any bytes already in the
        makefile's user-space buffer plus any bytes sitting in the kernel
        buffer. Called between rounds so that pipelined leftovers from
        the previous round (and any inter-round bytes the bot may have sent)
        do not leak into the next round (spec §8).
        """
        # Recreate makefile to drop any prefetched bytes from its internal
        # buffer.
        try:
            self.f.close()
        except OSError:
            pass
        # Drain whatever is sitting in the kernel buffer right now.
        try:
            self.sock.setblocking(False)
            while True:
                try:
                    chunk = self.sock.recv(65536)
                except (BlockingIOError, OSError):
                    break
                if not chunk:
                    break
        finally:
            try:
                self.sock.setblocking(True)
            except OSError:
                pass
        # Fresh makefile for the next round.
        self.f = self.sock.makefile('r', encoding='utf-8', errors='replace',
                                    newline='')


# ── Per-bot round runner ─────────────────────────────────────────────────────

def run_bot_round(client, w, h, start_grid, start_blank, dictionary,
                  taken_words, taken_lock,
                  results, results_lock):
    grid = [row[:] for row in start_grid]
    blank_rc = start_blank
    score = 0
    elapsed = 0.0
    cause = 'round_end (timer expired)'
    self_claimed = set()
    actions = []   # list of action strings for replay log
    dq = False

    deadline = time.monotonic() + ROUND_DURATION

    while True:
        time_left = deadline - time.monotonic()
        if time_left <= 0:
            cause = 'round_end (timer expired)'
            break

        t0 = time.monotonic()
        try:
            line = client.readline(time_left)
        except (socket.timeout, OSError):
            line = None
        t1 = time.monotonic()
        elapsed += (t1 - t0)

        if line is None:
            cause = 'round_end (timer expired)'
            break
        if not line.endswith('\n'):
            cause = 'malformed (no LF / EOF mid-line)'
            break
        # Reject CRLF: with newline='' the makefile preserves \r\n. We strip
        # the LF, so any leftover \r will fail the strict regex match below
        # and be DQ'd as malformed. We also explicitly DQ '\r' so the reason
        # is unambiguous in the log.
        if line.endswith('\r\n'):
            client.send("DQ malformed_crlf\n")
            actions.append("?CRLF")
            dq = True
            cause = 'DQ malformed_crlf'
            break

        resp = line[:-1]

        m_slide = SLIDE_RE.match(resp)
        m_claim = CLAIM_RE.match(resp)

        if m_slide:
            direction = m_slide.group(1)
            new_blank, ok = apply_slide(grid, blank_rc, direction, h, w)
            if not ok:
                client.send(f"DQ invalid_slide_{direction}\n")
                actions.append(f"S{direction}!")
                dq = True
                cause = f'DQ invalid_slide_{direction}'
                break
            blank_rc = new_blank
            actions.append(f"S{direction}")
            client.send("MOVED\n")

        elif m_claim:
            word = m_claim.group(1)
            orient = m_claim.group(2)
            r = int(m_claim.group(3))
            c = int(m_claim.group(4))

            if len(word) < 3:
                client.send("DQ short_word\n")
                actions.append(f"W{word}!short")
                dq = True
                cause = 'DQ short_word'
                break
            if word in self_claimed:
                client.send("DUP\n")
                actions.append(f"W{word}={orient}{r},{c}=DUP")
                continue
            if word not in dictionary:
                client.send("DQ not_in_dictionary\n")
                actions.append(f"W{word}!dict")
                dq = True
                cause = f'DQ not_in_dictionary ({word})'
                break
            ok, reason = verify_placement(word, orient, r, c, grid, h, w)
            if not ok:
                client.send(f"DQ {reason}\n")
                actions.append(f"W{word}!{reason}")
                dq = True
                cause = f'DQ {reason} ({word})'
                break
            # Race: try to claim the word globally for this round.
            with taken_lock:
                already = word in taken_words
                if not already:
                    taken_words.add(word)
            if already:
                client.send("TAKEN\n")
                actions.append(f"W{word}={orient}{r},{c}=TAKEN")
                continue
            pts = len(word) - 6
            score += pts
            self_claimed.add(word)
            actions.append(f"W{word}={orient}{r},{c}={pts:+d}")
            client.send(f"OK {pts}\n")

        else:
            client.send(f"DQ malformed\n")
            actions.append(f"?{resp}")
            dq = True
            cause = f'DQ malformed: {resp!r}'
            break

    # Always finish with ROUND_END.
    client.send(f"ROUND_END {score}\n")

    with results_lock:
        results[client.name] = {
            'score': score,
            'elapsed': elapsed,
            'cause': cause,
            'claimed': sorted(self_claimed),
            'n_actions': len(actions),
            'actions': actions,
            'dq': dq,
        }


# ── Tournament harness ───────────────────────────────────────────────────────

def round_robin_schedule(n_bots):
    """Circle-method round-robin schedule.

    Returns a list of "rotation rounds", each a list of (i, j) pairs of bot
    indices to play in parallel during that rotation round. Every pair of
    distinct bots appears in exactly one rotation round, total pairs =
    n_bots * (n_bots - 1) / 2. Within a rotation round, all pairs are
    disjoint (no bot appears twice), so the matches in that rotation round
    can run concurrently.

    For odd n_bots, one bot sits out per rotation round (a "bye").
    """
    bots = list(range(n_bots))
    if n_bots % 2 == 1:
        bots.append(None)
    n = len(bots)

    schedule = []
    for _ in range(n - 1):
        rr = []
        for i in range(n // 2):
            a = bots[i]
            b = bots[n - 1 - i]
            if a is not None and b is not None:
                rr.append((a, b))
        schedule.append(rr)
        # Rotate: keep bots[0] fixed, shift the rest by one slot.
        bots = [bots[0]] + [bots[-1]] + bots[1:-1]
    return schedule


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

    print("[*] Loading dictionary...", end=' ', flush=True)
    dictionary = load_dictionary()
    print(f"{len(dictionary)} words.")
    log.write(f"Dictionary: {len(dictionary)} words from {DICT_PATH}\n")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(32)
    server_sock.settimeout(1.0)

    clients = []
    print(f"[*] Server live on {HOST}:{PORT}. Registration: {REGISTRATION_WINDOW}s")

    name_re = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
    start_reg = time.time()
    while time.time() - start_reg < REGISTRATION_WINDOW:
        try:
            conn, addr = server_sock.accept()
            conn.settimeout(None)
            # Read exactly one LF-terminated line. With newline='' we preserve
            # CRLF and reject it via the regex (no trailing \r allowed).
            f = conn.makefile('r', encoding='utf-8', errors='replace', newline='')
            raw = f.readline()
            # Strip exactly one trailing LF; if CRLF was sent, the \r remains
            # and the regex will reject it.
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

    if not clients:
        print("[!] No participants.")
        log.close()
        return

    if len(clients) < 2:
        print("[!] Need at least 2 bots for round-robin.")
        log.close()
        return

    # Build a round-robin schedule via the circle method. Schedule is a list
    # of "rounds" (rotation rounds, distinct from puzzle-rounds-within-a-
    # match), each round containing disjoint pairs that can run in parallel.
    schedule = round_robin_schedule(len(clients))
    n_matches = sum(len(rr) for rr in schedule)
    max_concurrent = max(len(rr) for rr in schedule)
    print(f"[*] {len(clients)} bots registered. {n_matches} matches "
          f"× {MATCH_ROUNDS} rounds in {len(schedule)} rotation-rounds "
          f"(up to {max_concurrent} matches in parallel).\n")
    log.write(f"Tournament: {len(clients)} bots, round-robin\n")
    log.write(f"Bots: {', '.join(c.name for c in clients)}\n")
    log.write(f"Matches: {n_matches}, rounds per match: {MATCH_ROUNDS}, "
              f"max concurrent: {max_concurrent}\n\n")

    # Per-bot tournament-tracking state.
    for c in clients:
        c.match_pts = 0
        c.match_w = 0
        c.match_d = 0
        c.match_l = 0
        c.round_wins = 0
        c.cum_score = 0

    log_lock = threading.Lock()

    def emit(line):
        """Thread-safe print + log line."""
        with log_lock:
            print(line)
            log.write(line + "\n")
            log.flush()

    match_counter = [0]
    match_counter_lock = threading.Lock()

    def run_match(c_a, c_b):
        with match_counter_lock:
            match_counter[0] += 1
            match_idx = match_counter[0]

        prefix = f"[M{match_idx:02d}]"
        emit(f"{prefix} === START: {c_a.name} vs {c_b.name} ===")

        a_round_wins = 0
        b_round_wins = 0
        a_match_score = 0
        b_match_score = 0

        for round_num, (w, h) in enumerate(MATCH_ROUND_DIMS[:MATCH_ROUNDS], 1):
            rng = random.Random(0xC0DE * (match_idx * 100 + round_num) + 0xACE0)
            start_grid, start_blank = generate_grid(w, h, rng, dictionary)

            grid_line = '/'.join(''.join(row) for row in start_grid)
            with log_lock:
                log.write(f"{prefix} --- ROUND {round_num} ({w}×{h}) ---\n")
                log.write(f"{prefix} GRID {w}x{h} "
                          f"blank={start_blank[0]},{start_blank[1]} "
                          f"{grid_line}\n")

            # Drain only this match's bots; everyone else stays silent.
            for c in (c_a, c_b):
                c.drain()
            for c in (c_a, c_b):
                c.send(f"ROUND {round_num} {w} {h}\n")
                c.send(grid_to_lines(start_grid) + "\n")
                c.send("START\n")

            results = {}
            results_lock = threading.Lock()
            taken_words = set()
            taken_lock = threading.Lock()

            threads = [
                threading.Thread(
                    target=run_bot_round,
                    args=(c, w, h, start_grid, start_blank, dictionary,
                          taken_words, taken_lock,
                          results, results_lock),
                    daemon=True,
                )
                for c in (c_a, c_b)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=ROUND_DURATION + 5)

            def _empty():
                return {'score': 0, 'elapsed': ROUND_DURATION + 5,
                        'cause': 'thread hung', 'claimed': [],
                        'n_actions': 0, 'actions': [], 'dq': False}
            r_a = results.get(c_a.name) or _empty()
            r_b = results.get(c_b.name) or _empty()

            a_match_score += r_a['score']
            b_match_score += r_b['score']
            c_a.cum_score += r_a['score']
            c_b.cum_score += r_b['score']

            if r_a['score'] > r_b['score']:
                a_round_wins += 1
                c_a.round_wins += 1
                outcome = f"{c_a.name} wins"
            elif r_b['score'] > r_a['score']:
                b_round_wins += 1
                c_b.round_wins += 1
                outcome = f"{c_b.name} wins"
            else:
                outcome = "draw"

            with log_lock:
                for c, r in ((c_a, r_a), (c_b, r_b)):
                    line = (f"{prefix}   {c.name:<28} | score={r['score']:>5}"
                            f" | claims={len(r['claimed']):>4}"
                            f" | actions={r['n_actions']:>5}"
                            f" | elapsed={r['elapsed']:6.2f}s"
                            f" | {r['cause']}")
                    print(line)
                    log.write(line + "\n")
                outcome_line = f"{prefix}   → R{round_num} outcome: {outcome}"
                print(outcome_line)
                log.write(outcome_line + "\n")
                log.write(f"{prefix}   ACTIONS {c_a.name}: "
                          f"{' '.join(r_a['actions'])}\n")
                log.write(f"{prefix}   ACTIONS {c_b.name}: "
                          f"{' '.join(r_b['actions'])}\n")
                log.flush()

        if a_round_wins > b_round_wins:
            c_a.match_pts += MATCH_WIN_PTS
            c_a.match_w += 1
            c_b.match_l += 1
            verdict = f"{c_a.name} wins match {a_round_wins}-{b_round_wins}"
        elif b_round_wins > a_round_wins:
            c_b.match_pts += MATCH_WIN_PTS
            c_b.match_w += 1
            c_a.match_l += 1
            verdict = f"{c_b.name} wins match {b_round_wins}-{a_round_wins}"
        else:
            c_a.match_pts += MATCH_DRAW_PTS
            c_b.match_pts += MATCH_DRAW_PTS
            c_a.match_d += 1
            c_b.match_d += 1
            verdict = f"draw {a_round_wins}-{b_round_wins}"

        emit(f"{prefix} === VERDICT: {verdict} "
             f"(scores {c_a.name}={a_match_score} "
             f"{c_b.name}={b_match_score}) ===")

    for rr_idx, match_round in enumerate(schedule, 1):
        rr_header = (f"\n========== ROTATION-ROUND {rr_idx}/{len(schedule)} "
                     f"({len(match_round)} matches in parallel) ==========")
        emit(rr_header)

        threads = []
        for (i, j) in match_round:
            t = threading.Thread(
                target=run_match,
                args=(clients[i], clients[j]),
                daemon=True,
            )
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=MATCH_ROUNDS * (ROUND_DURATION + 5) + 30)

        time.sleep(0.5)

    print("\n[*] Tournament complete. Sending TOURNAMENT_END.")
    for c in clients:
        c.send("TOURNAMENT_END\n")

    log.write("\n========== FINAL STANDINGS ==========\n")
    final = sorted(clients,
                   key=lambda c: (-c.match_pts, -c.round_wins, -c.cum_score))
    header = (f"  rank  bot                          match_pts  W-D-L      "
              f"round_wins  cum_score")
    print(header)
    log.write(header + "\n")
    for rank, c in enumerate(final, 1):
        line = (f"  #{rank:<3}  {c.name:<28}  {c.match_pts:>9}  "
                f"{c.match_w}-{c.match_d}-{c.match_l:<6}  "
                f"{c.round_wins:>10}  {c.cum_score:>9}")
        print(line)
        log.write(line + "\n")

    log.close()
    for c in clients:
        c.close()
    server_sock.close()


if __name__ == '__main__':
    run_tournament()
