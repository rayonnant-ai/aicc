#!/usr/bin/env python3
import socket, json, time, sys

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall(b'MiMo_bot\n')
    buf = b''
    while True:
        data = sock.recv(65536)
        if not data:
            break
        buf += data
        while b'\n' in buf:
            line, buf = buf.split(b'\n', 1)
            if line.startswith(b'ROUND'):
                while b'\n' not in buf:
                    d = sock.recv(65536)
                    if not d:
                        return
                    buf += d
                sz_line, buf = buf.split(b'\n', 1)
                size = int(sz_line.split(b' ')[1])
                while len(buf) < size:
                    d = sock.recv(65536)
                    if not d:
                        return
                    buf += d
                payload = buf[:size]
                buf = buf[size:]
                data = json.loads(payload)
                tour = solve(data['rows'], data['cols'], data['weights'])
                sock.sendall(json.dumps({'tour': tour}).encode() + b'\n')
    sock.close()

KNIGHT_OFFSETS = [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]

def get_nm(r, c, R, C):
    return [(r+dr,c+dc) for dr,dc in KNIGHT_OFFSETS if 0<=r+dr<R and 0<=c+dc<C]

def heuristic_tour(sr, sc, R, C, W, tb):
    N = R * C
    vis = set()
    tour = [(sr, sc)]
    vis.add((sr, sc))
    for _ in range(N - 1):
        r, c = tour[-1]
        best, bs = None, None
        for nr, nc in get_nm(r, c, R, C):
            if (nr, nc) not in vis:
                s = len([1 for nn in get_nm(nr, nc, R, C) if nn not in vis])
                if best is None or s < bs or (s == bs and (
                        (tb == 'w' and W[nr][nc] < W[best[0]][best[1]]) or
                        (tb == 'W' and W[nr][nc] > W[best[0]][best[1]]))):
                    best, bs = (nr, nc), s
        if best is None:
            return None
        tour.append(best)
        vis.add(best)
    return tour

def eval_tour(tour, W):
    tot, run = 0, 0
    for i in range(len(tour) - 1):
        run += W[tour[i][0]][tour[i][1]]
        tot += run
    return tot

def solve(R, C, W):
    N = R * C
    t0 = time.time()
    best, best_c = None, float('inf')
    sq = sorted([(W[r][c],r,c) for r in range(R) for c in range(C)])

    for _, sr, sc in sq[:20]:
        if time.time()-t0 > 8.5:
            break
        for tb in ('w', 'W', 'x'):
            t = heuristic_tour(sr, sc, R, C, W, tb)
            if t and len(t)==N:
                c = eval_tour(t, W)
                if c < best_c:
                    best_c, best = c, t

    if best is None or N <= 36:
        bt = backtrack(R, C, W, t0)
        if bt and len(bt)==N:
            c = eval_tour(bt, W)
            if c < best_c:
                best_c, best = c, bt

    return best

def backtrack(R, C, W, t0):
    N = R * C
    sq = sorted([(W[r][c],r,c) for r in range(R) for c in range(C)])
    for _, sr, sc in sq[:12]:
        if time.time()-t0 > 8.5:
            break
        vis = set([(sr,sc)])
        tour = [(sr,sc)]
        if _bt(tour, vis, N, R, C, W):
            return tour
    return None

def _bt(tour, vis, N, R, C, W):
    if len(tour)==N:
        return True
    if time.time()-_bt.t0 > 9:
        return False
    r, c = tour[-1]
    mvs = [(nr,nc) for nr,nc in get_nm(r,c,R,C) if (nr,nc) not in vis]
    mvs.sort(key=lambda p: sum(1 for nn in get_nm(p[0],p[1],R,C) if nn not in vis))
    for nr, nc in mvs:
        tour.append((nr,nc))
        vis.add((nr,nc))
        if _bt(tour, vis, N, R, C, W):
            return True
        tour.pop()
        vis.remove((nr,nc))
    return False
_bt.t0 = 0

main()
