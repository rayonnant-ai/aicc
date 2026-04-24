#!/usr/bin/env python3
"""Knights of Hanoi solver client."""

import socket
import sys
from collections import deque

# ── Constants ─────────────────────────────────────────────────────────
HOST = "localhost"
PORT = 7474
BOT_NAME = "kimi_bot"

START = (0, 0)   # A1
GOAL = (7, 7)    # H8

# ── Knight graph ──────────────────────────────────────────────────────
def knight_moves(f, r):
    deltas = [(2, 1), (2, -1), (-2, 1), (-2, -1),
              (1, 2), (1, -2), (-1, 2), (-1, -2)]
    res = []
    for df, dr in deltas:
        nf, nr = f + df, r + dr
        if 0 <= nf <= 7 and 0 <= nr <= 7:
            res.append((nf, nr))
    return res

ADJ = {}
NEIGHBOR_COUNT = {}
ALL_SQUARES = []
for f in range(8):
    for r in range(8):
        sq = (f, r)
        ALL_SQUARES.append(sq)
        ADJ[sq] = knight_moves(f, r)
        NEIGHBOR_COUNT[sq] = len(ADJ[sq])

# ── Helpers ───────────────────────────────────────────────────────────
def sq_to_coords(s):
    return (ord(s[0].upper()) - ord('A'), int(s[1]) - 1)

def coords_to_sq(c):
    return chr(ord('A') + c[0]) + str(c[1] + 1)

def path_to_moves(path):
    return [coords_to_sq(path[i]) + coords_to_sq(path[i + 1])
            for i in range(len(path) - 1)]

def bfs_path(start, end, blocked):
    """Shortest path avoiding blocked squares. Returns list of coords or None."""
    blocked = set(blocked)
    if start == end:
        return [start]
    q = deque([(start, [start])])
    visited = {start}
    while q:
        pos, path = q.popleft()
        for nxt in ADJ[pos]:
            if nxt in visited or nxt in blocked:
                continue
            new_path = path + [nxt]
            if nxt == end:
                return new_path
            visited.add(nxt)
            q.append((nxt, new_path))
    return None

def has_free_neighbor(source, blocked_set, exclude):
    for nb in ADJ[source]:
        if nb not in blocked_set and nb != exclude:
            return True
    return False

# ── Solver ────────────────────────────────────────────────────────────
def solve(n, source, dest, blocked, max_candidates=5):
    """Recursive Hanoi solver with backtracking."""
    blocked = set(blocked)

    if n == 0:
        return []

    if n == 1:
        path = bfs_path(source, dest, blocked)
        if path is None:
            raise ValueError("no path")
        return path_to_moves(path)

    # dest must have at least one free neighbour for the recursive step
    if n >= 2:
        if not has_free_neighbor(dest, blocked, source):
            raise ValueError("dest trapped")

    candidates = []
    for sq in ALL_SQUARES:
        if sq == source or sq == dest or sq in blocked:
            continue
        if NEIGHBOR_COUNT[sq] < (3 if n >= 3 else 2):
            continue
        if n >= 2 and not has_free_neighbor(source, blocked | {dest}, sq):
            continue

        p1 = bfs_path(source, sq, blocked | {dest})
        p2 = bfs_path(sq, dest, blocked | {source})
        p3 = bfs_path(source, dest, blocked | {sq})
        if p1 and p2 and p3:
            score = len(p1) + len(p2) + len(p3)
            candidates.append((score, sq))

    if not candidates:
        raise ValueError("no temp")

    candidates.sort()

    for _, temp in candidates[:max_candidates]:
        try:
            # move n-1 disks source -> temp
            moves = solve(n - 1, source, temp, blocked | {dest}, max_candidates)
            # move disk n source -> dest
            path = bfs_path(source, dest, blocked | {temp})
            if path is None:
                continue
            moves += path_to_moves(path)
            # move n-1 disks temp -> dest
            moves += solve(n - 1, temp, dest, blocked | {source}, max_candidates)
            return moves
        except ValueError:
            continue

    raise ValueError("all candidates failed")

# ── Validation (local sanity check) ───────────────────────────────────
def validate(n, moves):
    board = {"A1": list(range(n, 0, -1))}
    for mv in moves:
        src = mv[:2]
        dst = mv[2:]
        sf, sr = sq_to_coords(src)
        df, dr = sq_to_coords(dst)
        if (abs(sf - df), abs(sr - dr)) not in ((1, 2), (2, 1)):
            return False, f"not a knight move: {mv}"
        if src not in board or not board[src]:
            return False, f"empty source: {mv}"
        disk = board[src].pop()
        if dst in board and board[dst]:
            if disk >= board[dst][-1]:
                return False, f"Hanoi violation: {disk} on {board[dst][-1]}"
        board.setdefault(dst, []).append(disk)
    if board.get("H8") != list(range(n, 0, -1)):
        return False, "wrong final state"
    return True, "ok"

# ── Main client loop ──────────────────────────────────────────────────
def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    sock.settimeout(15.0)

    # registration
    sock.sendall((BOT_NAME + "\n").encode())

    buf = b""
    while True:
        try:
            data = sock.recv(4096)
            if not data:
                break
            buf += data
        except socket.timeout:
            break

        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.decode().strip()
            if not line:
                continue

            if line.startswith("ROUND"):
                parts = line.split()
                round_num = int(parts[1])
                n = int(parts[2])

                # compute solution
                moves = solve(n, START, GOAL, set())
                response = ",".join(moves) + "\n"
                sock.sendall(response.encode())

            elif line.startswith("VALID"):
                print(line, flush=True)
            elif line.startswith("INVALID"):
                print(line, flush=True)
            elif line == "TIMEOUT":
                print(line, flush=True)
            elif line == "END":
                return
            else:
                print(f"unknown: {line}", flush=True)

if __name__ == "__main__":
    main()