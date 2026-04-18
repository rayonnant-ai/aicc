#!/usr/bin/env python3
import json
import socket
import sys
import time
from typing import List, Tuple, Optional

MOVES = ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2))


def knight_neighbors(rows: int, cols: int):
    nbrs = []
    for r in range(rows):
        row = []
        for c in range(cols):
            cur = []
            for dr, dc in MOVES:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    cur.append((nr, nc))
            row.append(cur)
        nbrs.append(row)
    return nbrs


def onward_unvisited_count(nbrs, used, r, c):
    s = 0
    for nr, nc in nbrs[r][c]:
        if not used[nr][nc]:
            s += 1
    return s


def tour_cost(tour: List[Tuple[int, int]], weights: List[List[int]]) -> int:
    load = 0
    total = 0
    for i, (r, c) in enumerate(tour):
        load += weights[r][c]
        if i + 1 < len(tour):
            total += load
    return total


def build_tour(rows: int, cols: int, weights: List[List[int]], time_limit: float) -> Optional[List[Tuple[int, int]]]:
    nbrs = knight_neighbors(rows, cols)
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    cells.sort(key=lambda rc: (weights[rc[0]][rc[1]], len(nbrs[rc[0]][rc[1]]), rc[0], rc[1]))
    starts = []
    starts.extend(cells[: min(len(cells), 12)])
    corners = [(0, 0), (0, cols - 1), (rows - 1, 0), (rows - 1, cols - 1)]
    for s in corners:
        if 0 <= s[0] < rows and 0 <= s[1] < cols:
            starts.append(s)
    seen = set()
    starts = [s for s in starts if not (s in seen or seen.add(s))]

    best = None
    best_sig = None

    for idx, start in enumerate(starts):
        if time.perf_counter() > time_limit:
            break
        used = [[False] * cols for _ in range(rows)]
        tour = [start]
        used[start[0]][start[1]] = True
        load = weights[start[0]][start[1]]
        ok = True
        for step in range(1, rows * cols):
            r, c = tour[-1]
            cand = []
            for nr, nc in nbrs[r][c]:
                if used[nr][nc]:
                    continue
                onward = onward_unvisited_count(nbrs, used, nr, nc)
                w = weights[nr][nc]
                future = len(nbrs[nr][nc])
                edge_bias = min(nr, rows - 1 - nr, nc, cols - 1 - nc)
                score = (onward, w, -future, edge_bias)
                cand.append((score, (nr, nc)))
            if not cand:
                ok = False
                break
            cand.sort(key=lambda x: x[0])
            chosen = cand[0][1]
            if len(cand) > 1:
                best_delta = None
                for rank, (_, pos) in enumerate(cand[:4]):
                    nr, nc = pos
                    delta = weights[nr][nc] * (rows * cols - 1 - step)
                    tie = (rank,)
                    key = (delta, tie)
                    if best_delta is None or key < best_delta[0]:
                        best_delta = (key, pos)
                chosen = best_delta[1]
            used[chosen[0]][chosen[1]] = True
            tour.append(chosen)
            load += weights[chosen[0]][chosen[1]]
        if ok and len(tour) == rows * cols:
            sig = sum(weights[r][c] * (rows * cols - 1 - i) for i, (r, c) in enumerate(tour))
            if best is None or sig < best_sig:
                best = tour
                best_sig = sig
    return best


def improve_tail_swaps(tour: List[Tuple[int, int]], weights: List[List[int]], time_limit: float) -> List[Tuple[int, int]]:
    n = len(tour)
    pos = {p: i for i, p in enumerate(tour)}
    move_set = set()
    for i in range(n - 1):
        a, b = tour[i], tour[i + 1]
        move_set.add((a, b))
    improved = True
    while improved and time.perf_counter() < time_limit:
        improved = False
        for i in range(max(1, n - 28), n - 2):
            if time.perf_counter() >= time_limit:
                break
            prev = tour[i - 1]
            for j in range(i + 1, n):
                cand = tour[j]
                if (prev, cand) not in move_set:
                    continue
                if j == n - 1:
                    new_tour = tour[:i] + [tour[j]] + tour[i:j]
                    if weights[new_tour[i][0]][new_tour[i][1]] < weights[tour[i][0]][tour[i][1]]:
                        tour = new_tour
                        move_set = set((tour[k], tour[k + 1]) for k in range(n - 1))
                        improved = True
                        break
                else:
                    after = tour[j + 1]
                    tail = tour[i:j + 1]
                    rev = list(reversed(tail))
                    if (rev[-1], after) in move_set and (prev, rev[0]) in move_set:
                        old_score = sum(weights[tour[k][0]][tour[k][1]] * (n - 1 - k) for k in range(i, j + 1))
                        new_tour = tour[:i] + rev + tour[j + 1:]
                        new_score = sum(weights[new_tour[k][0]][new_tour[k][1]] * (n - 1 - k) for k in range(i, j + 1))
                        if new_score < old_score:
                            tour = new_tour
                            move_set = set((tour[k], tour[k + 1]) for k in range(n - 1))
                            improved = True
                            break
            if improved:
                break
    return tour


def solve_board(rows: int, cols: int, weights: List[List[int]], budget: float = 9.4) -> List[Tuple[int, int]]:
    deadline = time.perf_counter() + budget
    tour = build_tour(rows, cols, weights, deadline - 0.4)
    if tour is None:
        raise RuntimeError('failed to find tour')
    tour = improve_tail_swaps(tour, weights, deadline - 0.05)
    return tour


def recv_line(f) -> str:
    line = f.readline()
    if not line:
        raise EOFError('connection closed')
    return line.decode().rstrip('\n')


def main():
    host = 'localhost'
    port = 7474
    bot_name = 'chat_gpt_bot\n'
    if len(sys.argv) >= 2:
        bot_name = sys.argv[1].rstrip('\n') + '\n'
    with socket.create_connection((host, port)) as sock:
        sock.sendall(bot_name.encode())
        f = sock.makefile('rb')
        while True:
            try:
                line = recv_line(f)
            except EOFError:
                break
            if not line:
                continue
            if not line.startswith('ROUND '):
                continue
            size_line = recv_line(f)
            if not size_line.startswith('SIZE '):
                raise RuntimeError(f'unexpected line: {size_line}')
            size = int(size_line.split()[1])
            payload = f.read(size)
            board = json.loads(payload.decode())
            rows = board['rows']
            cols = board['cols']
            weights = board['weights']
            tour = solve_board(rows, cols, weights)
            msg = json.dumps({'tour': [[r, c] for r, c in tour]}, separators=(',', ':')) + '\n'
            sock.sendall(msg.encode())
            result = recv_line(f)
            print(result, flush=True)
            if result.startswith('TIMEOUT'):
                continue


if __name__ == '__main__':
    main()