#!/usr/bin/env python3
"""Smoke-test client for the crossword-style Word Gem Puzzle protocol.
Connects, sends name, then for each round scans the starting grid for any
across/down dictionary words and submits them with the new
`W <word> <A|D> <r>,<c>` syntax."""
import socket
import sys

HOST = 'localhost'
PORT = 7474
NAME = sys.argv[1] if len(sys.argv) > 1 else 'probe_bot'

print(f"[probe] loading dictionary...", flush=True)
with open('dictionary.txt') as f:
    DICT = {ln.strip() for ln in f if ln.strip().isalpha() and len(ln.strip()) >= 3}
print(f"[probe] {len(DICT)} words.", flush=True)


def find_runs(rows, h, w):
    """Yield ('A', r, c, run) for every contiguous all-letter run on row r,
    and ('D', r, c, run) for every contiguous all-letter run in column c.
    A 'run' is a tuple of letters; we'll later check substrings against
    the dictionary."""
    for r in range(h):
        i = 0
        while i < w:
            j = i
            while j < w and rows[r][j] != '_':
                j += 1
            if j - i >= 3:
                yield ('A', r, i, ''.join(rows[r][i:j]))
            i = j + 1 if j < w else w
    for c in range(w):
        i = 0
        while i < h:
            j = i
            while j < h and rows[j][c] != '_':
                j += 1
            if j - i >= 3:
                yield ('D', i, c, ''.join(rows[k][c] for k in range(i, j)))
            i = j + 1 if j < h else h


def find_claims(rows, h, w):
    claims = []
    for orient, r, c, run in find_runs(rows, h, w):
        for length in range(3, len(run) + 1):
            for offset in range(len(run) - length + 1):
                word = run[offset:offset + length]
                if word in DICT:
                    if orient == 'A':
                        claims.append((word, 'A', r, c + offset))
                    else:
                        claims.append((word, 'D', r + offset, c))
    return claims


def main():
    s = socket.socket()
    s.connect((HOST, PORT))
    s.sendall(f"{NAME}\n".encode())
    f = s.makefile('r', encoding='utf-8', newline='')

    while True:
        header = f.readline()
        if not header:
            break
        header = header.rstrip('\n')
        print(f"<- {header}", flush=True)
        if header == 'TOURNAMENT_END':
            break
        if not header.startswith('ROUND '):
            continue
        _, n, w, h = header.split()
        n, w, h = int(n), int(w), int(h)
        rows = [list(f.readline().rstrip('\n')) for _ in range(h)]
        for r in rows:
            print(f"<- {''.join(r)}", flush=True)
        start = f.readline().rstrip('\n')
        print(f"<- {start}", flush=True)

        # Find candidate claims and submit them, longest first.
        claims = sorted(set(find_claims(rows, h, w)),
                        key=lambda c: (-len(c[0]), c[0]))
        sent = 0
        for word, orient, r, c in claims:
            line = f"W {word} {orient} {r},{c}\n"
            s.sendall(line.encode())
            resp = f.readline().rstrip('\n')
            print(f"-> {line.rstrip()}  <-  {resp}", flush=True)
            sent += 1
            if resp.startswith('DQ') or resp.startswith('ROUND_END') or sent >= 12:
                break
        # Drain to ROUND_END
        while True:
            line = f.readline()
            if not line:
                return
            line = line.rstrip('\n')
            print(f"<- {line}", flush=True)
            if line.startswith('ROUND_END'):
                break
            if line == 'TOURNAMENT_END':
                return


if __name__ == '__main__':
    main()
