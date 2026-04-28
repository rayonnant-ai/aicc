#!/usr/bin/env python3
"""
Word Gem Puzzle bot — static-grid strategy.

Strategy
--------
- Read each round's grid; do not slide.
- Find every length-7+ dictionary word that appears as a contiguous run
  (across or down) on the initial grid, with no blank cell crossing the run.
- Pipeline-fire all claims in a single sendall, longest-first (highest score
  first; alphabetical tiebreak for determinism).
- Drain server responses (OK / DUP / TAKEN / DQ / ...) until ROUND_END.

Rationale
---------
- Scoring is len(word) - 6, so only length-7+ words give positive points.
  Length-6 claims (0 points) and shorter (negative) only burn round time.
  Denying the opponent a 0-point word does not help us — they would have
  scored 0 too.
- Sliding mostly destroys existing words on your own grid and rarely creates
  new high-value ones inside the 10s budget. The risk (off-board slide -> DQ;
  out-of-sync local grid -> DQ on a stale claim) outweighs the upside,
  especially against a similarly static opponent where the round is decided
  by who wins the most 7+ races.
- A reader thread drains responses concurrently with our send, so a large
  pipelined batch cannot deadlock against kernel TCP buffers (us blocked on
  send while the server is blocked on send into our full recv buffer).
- Every claim line is constructed from a real contiguous run on the grid and
  filtered through the dictionary, so the bot has no DQ path under nominal
  conditions.

Run
---
    BOTNAME=my_bot_name python3 word_gem_bot.py

Expects dictionary.txt in the working directory and the server reachable at
localhost:7474. Stdlib only, Python 3.10+.
"""

import os
import socket
import sys
import threading
import queue

HOST = 'localhost'
PORT = 7474
DICT_PATH = 'dictionary.txt'
MIN_LEN = 7  # claim only words that score positive: len(word) - 6 > 0


def load_dictionary(path):
    """Return a set of dictionary words with len >= MIN_LEN, lowercase ASCII."""
    words = set()
    try:
        with open(path, 'r', encoding='ascii', errors='replace') as f:
            for line in f:
                w = line.rstrip('\r\n')
                if len(w) >= MIN_LEN and w.isalpha() and w.islower():
                    words.add(w)
    except OSError as e:
        sys.stderr.write(f'failed to open {path}: {e}\n')
        sys.exit(1)
    return words


def find_claims(grid, w, h, dictionary):
    """
    Return a list of (orient, row, col, word) for every length>=MIN_LEN
    dictionary word that appears as a contiguous letter run (across or down)
    on the grid. Runs are split by the blank '_', so by construction no
    placement crosses a blank cell.
    """
    claims = []

    # Across runs (left -> right) on each row.
    for r in range(h):
        row = grid[r]
        c = 0
        while c < w:
            if row[c] == '_':
                c += 1
                continue
            run_start = c
            while c < w and row[c] != '_':
                c += 1
            run = row[run_start:c]
            n = len(run)
            for L in range(MIN_LEN, n + 1):
                for s in range(n - L + 1):
                    word = run[s:s + L]
                    if word in dictionary:
                        claims.append(('A', r, run_start + s, word))

    # Down runs (top -> bottom) on each column.
    for col in range(w):
        column = ''.join(grid[r][col] for r in range(h))
        r = 0
        while r < h:
            if column[r] == '_':
                r += 1
                continue
            run_start = r
            while r < h and column[r] != '_':
                r += 1
            run = column[run_start:r]
            n = len(run)
            for L in range(MIN_LEN, n + 1):
                for s in range(n - L + 1):
                    word = run[s:s + L]
                    if word in dictionary:
                        claims.append(('D', run_start + s, col, word))

    return claims


class LineReader:
    """Buffered line reader over a TCP socket. Lines terminated by '\\n'."""

    def __init__(self, sock):
        self.sock = sock
        self.buf = b''

    def readline(self):
        while b'\n' not in self.buf:
            try:
                chunk = self.sock.recv(65536)
            except OSError:
                return None
            if not chunk:
                return None
            self.buf += chunk
        line, _, self.buf = self.buf.partition(b'\n')
        return line.decode('ascii', errors='replace')


def reader_loop(reader, q):
    """Background thread: feed every server line into the queue. None on EOF."""
    while True:
        line = reader.readline()
        q.put(line)
        if line is None:
            return


def play_round(sock, q, w, h, grid, dictionary, bot_name):
    claims = find_claims(grid, w, h, dictionary)

    # Highest-scoring first; alphabetical tiebreak for determinism.
    claims.sort(key=lambda c: (-len(c[3]), c[3]))

    # Each unique word can OK at most once per round; only submit one
    # placement per word (the first, which after sorting is fine).
    seen = set()
    deduped = []
    for c in claims:
        if c[3] not in seen:
            seen.add(c[3])
            deduped.append(c)

    sys.stderr.write(
        f'{bot_name}: w={w} h={h} candidates={len(claims)} unique={len(deduped)}\n'
    )
    sys.stderr.flush()

    if deduped:
        payload = ''.join(
            f'W {word} {orient} {r},{col}\n'
            for orient, r, col, word in deduped
        )
        try:
            sock.sendall(payload.encode('ascii'))
        except OSError:
            # Server may have closed or the round force-ended mid-send;
            # ROUND_END will arrive (or the socket EOFs) and we'll exit below.
            pass

    # Tally OK points (informational only) and drain to ROUND_END.
    pts = 0
    ok_count = taken_count = dup_count = 0
    while True:
        line = q.get()
        if line is None:
            return  # connection closed
        if line.startswith('ROUND_END'):
            sys.stderr.write(
                f'{bot_name}: ROUND_END server={line.split()[1] if len(line.split())>1 else "?"}'
                f' local_tally={pts} ok={ok_count} taken={taken_count} dup={dup_count}\n'
            )
            sys.stderr.flush()
            return
        if line.startswith('OK '):
            ok_count += 1
            try:
                pts += int(line.split()[1])
            except (IndexError, ValueError):
                pass
        elif line == 'TAKEN':
            taken_count += 1
        elif line == 'DUP':
            dup_count += 1
        # MOVED / DQ / others: nothing to do; on DQ the server immediately
        # sends ROUND_END which we'll catch on the next iteration.


def main():
    # Per spec: take BOTNAME from env verbatim, only stripping a trailing \n.
    bot_name = os.environ.get('BOTNAME', '')
    if bot_name.endswith('\n'):
        bot_name = bot_name[:-1]
    if not bot_name:
        sys.stderr.write('BOTNAME env var is required and must be non-empty\n')
        sys.exit(1)

    dictionary = load_dictionary(DICT_PATH)
    sys.stderr.write(
        f'{bot_name}: dict loaded, {len(dictionary)} words of length >= {MIN_LEN}\n'
    )
    sys.stderr.flush()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
    except OSError as e:
        sys.stderr.write(f'connect to {HOST}:{PORT} failed: {e}\n')
        sys.exit(1)

    # Identify ourselves on the very first line.
    sock.sendall((bot_name + '\n').encode('ascii'))

    reader = LineReader(sock)
    q = queue.Queue()
    threading.Thread(target=reader_loop, args=(reader, q), daemon=True).start()

    # Main protocol loop: wait for ROUND headers, ignore everything else
    # (silent inter-match windows are normal and may be many minutes long).
    while True:
        line = q.get()
        if line is None:
            return  # server closed
        if line == 'TOURNAMENT_END':
            return
        if line.startswith('ROUND '):
            parts = line.split()
            try:
                # ROUND <n> <w> <h>
                w = int(parts[2])
                h = int(parts[3])
            except (IndexError, ValueError):
                sys.stderr.write(f'{bot_name}: malformed ROUND line: {line!r}\n')
                continue
            grid = []
            for _ in range(h):
                row_line = q.get()
                if row_line is None:
                    return
                grid.append(row_line)
            start_line = q.get()
            if start_line is None:
                return
            # start_line should be exactly 'START' per the spec.
            play_round(sock, q, w, h, grid, dictionary, bot_name)
        # Other lines outside a round: ignore.


if __name__ == '__main__':
    main()