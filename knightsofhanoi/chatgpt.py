#!/usr/bin/env python3
import socket
from collections import deque

HOST = "localhost"
PORT = 7474
BOT_NAME = "gpt55_bot"

BOARD = 8
NSQ = 64
NO_BAN = 64
MAX_N = 12
INF = 10**9

KNIGHT_DELTAS = [
    (1, 2), (2, 1), (-1, 2), (-2, 1),
    (1, -2), (2, -1), (-1, -2), (-2, -1),
]


def idx(x, y):
    return y * BOARD + x


def xy(i):
    return i % BOARD, i // BOARD


def sq_name(i):
    x, y = xy(i)
    return chr(ord("A") + x) + str(y + 1)


START = idx(0, 0)  # A1
GOAL = idx(7, 7)   # H8


def build_graph():
    g = [[] for _ in range(NSQ)]
    for i in range(NSQ):
        x, y = xy(i)
        for dx, dy in KNIGHT_DELTAS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < BOARD and 0 <= ny < BOARD:
                g[i].append(idx(nx, ny))
    return g


GRAPH = build_graph()


def bfs_with_ban(banned):
    """
    Compute shortest-path distance and next-hop tables between all pairs,
    avoiding one banned square. If banned == NO_BAN, no square is banned.
    """
    dist = [[INF] * NSQ for _ in range(NSQ)]
    nxt = [[-1] * NSQ for _ in range(NSQ)]

    for s in range(NSQ):
        if s == banned:
            continue

        q = deque([s])
        dist[s][s] = 0

        while q:
            u = q.popleft()
            for v in GRAPH[u]:
                if v == banned:
                    continue
                if dist[s][v] == INF:
                    dist[s][v] = dist[s][u] + 1
                    nxt[s][v] = v if u == s else nxt[s][u]
                    q.append(v)

    return dist, nxt


def precompute():
    """
    DP idea:

    solve(k, s, t):
      move k-1 disks from s to buffer b
      move disk k from s to t along a shortest knight path avoiding b
      move k-1 disks from b to t

    We choose b to minimize total move count.
    """
    all_dist = []
    all_next = []

    for banned in range(NSQ + 1):
        real_ban = banned if banned < NSQ else NO_BAN
        d, n = bfs_with_ban(real_ban)
        all_dist.append(d)
        all_next.append(n)

    cost = [None] * (MAX_N + 1)
    choice = [None] * (MAX_N + 1)

    cost[0] = [[0] * NSQ for _ in range(NSQ)]

    cost[1] = [[all_dist[NO_BAN][s][t] for t in range(NSQ)] for s in range(NSQ)]
    choice[1] = [[None] * NSQ for _ in range(NSQ)]

    for k in range(2, MAX_N + 1):
        cur = [[0] * NSQ for _ in range(NSQ)]
        ch = [[None] * NSQ for _ in range(NSQ)]
        prev = cost[k - 1]

        for s in range(NSQ):
            for t in range(NSQ):
                if s == t:
                    cur[s][t] = 0
                    ch[s][t] = s
                    continue

                best = INF
                best_b = None

                for b in range(NSQ):
                    if b == s or b == t:
                        continue

                    direct = all_dist[b][s][t]
                    if direct == INF:
                        continue

                    val = prev[s][b] + direct + prev[b][t]
                    if val < best:
                        best = val
                        best_b = b

                cur[s][t] = best
                ch[s][t] = best_b

        cost[k] = cur
        choice[k] = ch

    return all_dist, all_next, cost, choice


ALL_DIST, ALL_NEXT, COST, CHOICE = precompute()


def shortest_path(s, t, banned=NO_BAN):
    if s == t:
        return [s]

    path = [s]
    u = s

    while u != t:
        u = ALL_NEXT[banned][u][t]
        if u < 0:
            raise RuntimeError(f"No knight path from {sq_name(s)} to {sq_name(t)}")
        path.append(u)

    return path


def emit_stack_moves(k, s, t, out):
    if k == 0 or s == t:
        return

    if k == 1:
        p = shortest_path(s, t, NO_BAN)
        for a, b in zip(p, p[1:]):
            out.append(sq_name(a) + sq_name(b))
        return

    b = CHOICE[k][s][t]
    if b is None:
        raise RuntimeError(f"No buffer for k={k}, {sq_name(s)}->{sq_name(t)}")

    emit_stack_moves(k - 1, s, b, out)

    p = shortest_path(s, t, b)
    for a, c in zip(p, p[1:]):
        out.append(sq_name(a) + sq_name(c))

    emit_stack_moves(k - 1, b, t, out)


def solve_round(n):
    moves = []
    emit_stack_moves(n, START, GOAL, moves)
    return ",".join(moves)


def main():
    with socket.create_connection((HOST, PORT), timeout=5) as sock:
        f = sock.makefile("rwb", buffering=0)

        f.write((BOT_NAME + "\n").encode("ascii"))

        while True:
            line = f.readline()
            if not line:
                break

            line = line.decode("ascii", errors="replace").strip()

            if line == "END":
                break

            if not line:
                continue

            if not line.startswith("ROUND "):
                # Ignore unexpected lines defensively.
                continue

            parts = line.split()
            if len(parts) != 3:
                break

            n = int(parts[2])
            answer = solve_round(n)
            f.write((answer + "\n").encode("ascii"))

            verdict = f.readline()
            if not verdict:
                break

            # Important: consume VALID / INVALID / TIMEOUT before next ROUND.
            # No stdout needed for tournament play, but stderr is useful locally.
            # print(verdict.decode().strip(), file=sys.stderr)


if __name__ == "__main__":
    main()