#!/usr/bin/env python3
"""
Robot Word Racer — competitive grid word-finding bot.

Strategy:
  • Dictionary stored as a sorted list of bytes objects.  Build time: <1 s for
    1 M words (vs 15+ s for a Python trie).
  • Prefix pruning via bisect: at each DFS step, the remaining candidate range
    [lo, hi) is narrowed with two bisect_left calls — no trie nodes needed.
  • Iterative DFS with an explicit stack avoids recursion-limit issues.
  • Three-thread pipeline (Solver → Sender → Receiver) so word submission is
    pipelined: sending never blocks on server ACKs.
  • Words are emitted longest-first (PriorityQueue keyed on -len) because
    scoring = len − 6; only words ≥ 7 letters are submitted.
"""

import bisect
import socket
import sys
import threading
import queue

# ── Configuration ────────────────────────────────────────────────────────────
GRID_SIZE       = 15
MIN_SUBMIT_LEN  = 7
HOST, PORT      = 'localhost', 7474
BOT_NAME        = 'ClaudeBot'
DICT_PATH       = 'dictionary.txt'
SEND_BATCH      = 30

DIRECTIONS = ((-1, -1), (-1, 0), (-1, 1),
              ( 0, -1),          ( 0, 1),
              ( 1, -1), ( 1, 0), ( 1, 1))


# ── Dictionary Loading ───────────────────────────────────────────────────────

def load_dictionary(path: str) -> tuple[list[bytes], frozenset[bytes]]:
    """
    Return (sorted_words, word_set) where each word is an uppercase ASCII
    bytes object of length ≥ MIN_SUBMIT_LEN.
    """
    words: list[bytes] = []
    with open(path, 'rb') as fh:
        for raw in fh:
            w = raw.strip().upper()
            if len(w) >= MIN_SUBMIT_LEN and w.isalpha():
                words.append(w)
    words.sort()
    return words, frozenset(words)


# ── Grid Solver ──────────────────────────────────────────────────────────────

def solve(grid_bytes: bytes, words_sorted: list[bytes],
          word_set: frozenset[bytes], out_q: queue.PriorityQueue,
          stop: threading.Event) -> None:
    """
    Iterative DFS from every cell.  Prefix pruning is done by maintaining a
    bisect range [lo, hi) into the sorted word list.  Each DFS step narrows
    the range with two O(log n) bisect calls.
    """
    G   = GRID_SIZE
    G2  = G * G
    n_words = len(words_sorted)
    found: set[bytes] = set()
    vis = bytearray(G2)

    # Pre-compute flat-index neighbour lists
    adj: list[list[int]] = [[] for _ in range(G2)]
    for r in range(G):
        for c in range(G):
            idx = r * G + c
            for dr, dc in DIRECTIONS:
                nr, nc = r + dr, c + dc
                if 0 <= nr < G and 0 <= nc < G:
                    adj[idx].append(nr * G + nc)

    # Working prefix buffer (bytearray — mutable, avoids allocations)
    prefix = bytearray()

    # Stack frame: (cell, lo, hi, neighbour_cursor)
    # We keep `prefix` and `vis` in sync via push/pop discipline.

    for start in range(G2):
        if stop.is_set():
            break

        ch = grid_bytes[start]

        # Initial range: words starting with ch
        prefix.clear()
        prefix.append(ch)

        lo = bisect.bisect_left(words_sorted, prefix)
        if ch < 90:                          # ord('Z') == 90
            prefix[0] = ch + 1
            hi = bisect.bisect_left(words_sorted, prefix)
            prefix[0] = ch
        else:
            hi = n_words

        if lo >= hi:
            continue

        vis[start] = 1

        # Check if prefix itself is a word (unlikely at len 1)
        if len(prefix) >= MIN_SUBMIT_LEN:
            bword = bytes(prefix)
            if bword in word_set and bword not in found:
                found.add(bword)
                out_q.put((-len(bword), bword.decode('ascii')))

        # Iterative DFS
        stack: list[tuple[int, int, int, int]] = [(start, lo, hi, 0)]

        while stack:
            if stop.is_set():
                break

            cell, s_lo, s_hi, cursor = stack[-1]
            neighbours = adj[cell]
            nlen = len(neighbours)
            advanced = False

            while cursor < nlen:
                ni = neighbours[cursor]
                cursor += 1
                if vis[ni]:
                    continue

                nch = grid_bytes[ni]

                # Narrow bisect range for prefix + nch
                prefix.append(nch)
                new_lo = bisect.bisect_left(words_sorted, prefix, s_lo, s_hi)

                if nch < 90:
                    prefix[-1] = nch + 1
                    new_hi = bisect.bisect_left(words_sorted, prefix, new_lo, s_hi)
                    prefix[-1] = nch
                else:
                    new_hi = s_hi

                if new_lo >= new_hi:
                    prefix.pop()
                    continue

                # Valid prefix — descend
                stack[-1] = (cell, s_lo, s_hi, cursor)
                vis[ni] = 1
                plen = len(prefix)

                if plen >= MIN_SUBMIT_LEN:
                    bword = bytes(prefix)
                    if bword in word_set and bword not in found:
                        found.add(bword)
                        out_q.put((-plen, bword.decode('ascii')))

                stack.append((ni, new_lo, new_hi, 0))
                advanced = True
                break

            if not advanced:
                stack.pop()
                if prefix:
                    vis[cell] = 0
                    prefix.pop()

        # Clean up for this start cell
        vis[start] = 0
        prefix.clear()

    out_q.put((0, ''))       # sentinel


# ── Network Threads ──────────────────────────────────────────────────────────

def sender_thread(sock: socket.socket, wq: queue.PriorityQueue,
                  stop: threading.Event, stats: dict) -> None:
    buf: list[str] = []

    def flush():
        if not buf:
            return
        try:
            sock.sendall(''.join(buf).encode('utf-8'))
            stats['sent'] += len(buf)
        except OSError:
            stop.set()
        buf.clear()

    solver_done = False
    while not stop.is_set():
        try:
            item = wq.get(timeout=0.15)
        except queue.Empty:
            flush()
            if solver_done:
                return
            continue

        if item[1] == '':
            solver_done = True
            while True:
                try:
                    item = wq.get_nowait()
                    if item[1] != '':
                        buf.append(item[1] + '\n')
                except queue.Empty:
                    break
            flush()
            return

        buf.append(item[1] + '\n')
        while len(buf) < SEND_BATCH:
            try:
                item = wq.get_nowait()
                if item[1] == '':
                    solver_done = True
                    break
                buf.append(item[1] + '\n')
            except queue.Empty:
                break
        flush()


def receiver_thread(rf, stop: threading.Event, stats: dict) -> None:
    while not stop.is_set():
        try:
            line = rf.readline()
            if not line:
                stop.set()
                return
            if line.strip() == b'1':
                stop.set()
                return
            stats['acked'] += 1
        except OSError:
            stop.set()
            return


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print('[*] Loading dictionary...', flush=True)
    words_sorted, word_set = load_dictionary(DICT_PATH)
    print(f'[*] Dictionary ready: {len(words_sorted)} scoring words.', flush=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
    try:
        sock.connect((HOST, PORT))
    except ConnectionRefusedError:
        print(f'[!] Cannot connect to {HOST}:{PORT}', file=sys.stderr)
        sys.exit(1)

    rf = sock.makefile('rb')
    sock.sendall(f'{BOT_NAME}\n'.encode('utf-8'))
    print(f'[*] Identified as "{BOT_NAME}"', flush=True)

    raw = rf.readline().decode('utf-8').strip().upper()
    expected = GRID_SIZE * GRID_SIZE
    if len(raw) != expected:
        print(f'[!] Bad grid length: {len(raw)} (expected {expected})',
              file=sys.stderr)
        sock.close()
        sys.exit(1)

    grid_bytes = raw.encode('ascii')
    print('[*] Grid received. Solving & submitting...', flush=True)
    for i in range(GRID_SIZE):
        print('    ' + ' '.join(raw[i * GRID_SIZE:(i + 1) * GRID_SIZE]))

    stop  = threading.Event()
    wq    = queue.PriorityQueue()
    stats = {'sent': 0, 'acked': 0}

    threads = [
        threading.Thread(target=solve, name='solver',
                         args=(grid_bytes, words_sorted, word_set, wq, stop),
                         daemon=True),
        threading.Thread(target=sender_thread, name='sender',
                         args=(sock, wq, stop, stats), daemon=True),
        threading.Thread(target=receiver_thread, name='receiver',
                         args=(rf, stop, stats), daemon=True),
    ]
    for t in threads:
        t.start()

    threads[0].join()
    threads[1].join(timeout=15)

    if not stop.is_set():
        stop.wait(timeout=2)
    stop.set()

    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()

    print(f'[*] Done. Sent {stats["sent"]}, acked {stats["acked"]}.', flush=True)


if __name__ == '__main__':
    main()