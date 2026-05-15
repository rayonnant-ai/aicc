# bot author: Kimi K2.6 (moonshotai/kimi-k2.6 via OpenRouter)
# bot author: assistant
import os
import sys
import socket
import math
import random
import time
from collections import defaultdict

EPS = 1e-9

def mec(points, rng):
    if not points:
        return (0.0, 0.0, 0.0)
    pts = list(points)
    rng.shuffle(pts)
    n = len(pts)
    if n == 1:
        return (pts[0][0], pts[0][1], 0.0)

    def circle1(a):
        return (a[0], a[1], 0.0)

    def circle2(a, b):
        cx = (a[0] + b[0]) * 0.5
        cy = (a[1] + b[1]) * 0.5
        r = math.hypot(a[0] - b[0], a[1] - b[1]) * 0.5
        return (cx, cy, r)

    def circle3(a, b, c):
        ax, ay = a
        bx, by = b
        cx_, cy_ = c
        d = 2.0 * (ax * (by - cy_) + bx * (cy_ - ay) + cx_ * (ay - by))
        if abs(d) < 1e-12:
            ca = circle2(a, b)
            cb = circle2(a, c)
            cc = circle2(b, c)
            for cand in (ca, cb, cc):
                dx1 = a[0] - cand[0]
                dy1 = a[1] - cand[1]
                dx2 = b[0] - cand[0]
                dy2 = b[1] - cand[1]
                dx3 = c[0] - cand[0]
                dy3 = c[1] - cand[1]
                rr = cand[2] + 1e-9
                if (dx1 * dx1 + dy1 * dy1 <= rr * rr and
                        dx2 * dx2 + dy2 * dy2 <= rr * rr and
                        dx3 * dx3 + dy3 * dy3 <= rr * rr):
                    return cand
            return ca
        ux = ((ax * ax + ay * ay) * (by - cy_) +
              (bx * bx + by * by) * (cy_ - ay) +
              (cx_ * cx_ + cy_ * cy_) * (ay - by)) / d
        uy = ((ax * ax + ay * ay) * (cx_ - bx) +
              (bx * bx + by * by) * (ax - cx_) +
              (cx_ * cx_ + cy_ * cy_) * (bx - ax)) / d
        r = math.hypot(ux - ax, uy - ay)
        return (ux, uy, r)

    def contains(c, p):
        dx = p[0] - c[0]
        dy = p[1] - c[1]
        return dx * dx + dy * dy <= (c[2] + 1e-9) * (c[2] + 1e-9)

    def welzl(i, boundary):
        if i == 0 or len(boundary) == 3:
            if len(boundary) == 0:
                return (0.0, 0.0, 0.0)
            elif len(boundary) == 1:
                return circle1(boundary[0])
            elif len(boundary) == 2:
                return circle2(boundary[0], boundary[1])
            else:
                return circle3(boundary[0], boundary[1], boundary[2])
        p = pts[i - 1]
        c = welzl(i - 1, boundary)
        if contains(c, p):
            return c
        boundary.append(p)
        c = welzl(i - 1, boundary)
        boundary.pop()
        return c

    if n == 2:
        return circle2(pts[0], pts[1])
    return welzl(n, [])

def greedy_solve(dots, w, h, seed=0, mode='best'):
    rng = random.Random(seed)
    pos_map = {}
    clusters = []
    for idx, x, y in dots:
        key = (x, y)
        if key not in pos_map:
            pos_map[key] = len(clusters)
            clusters.append({
                'indices': [idx],
                'pts': [(float(x), float(y))],
            })
        else:
            clusters[pos_map[key]]['indices'].append(idx)

    for c in clusters:
        if len(c['pts']) == 1:
            c['mec'] = (c['pts'][0][0], c['pts'][0][1], 0.0)
        else:
            c['mec'] = mec(c['pts'], rng)

    max_r = min(w, h) * 0.5 + 1e-7

    def fits(cx, cy, r):
        return (cx - r >= -1e-7 and cx + r <= w + 1e-7 and
                cy - r >= -1e-7 and cy + r <= h + 1e-7)

    def overlap(m1, m2):
        dx = m1[0] - m2[0]
        dy = m1[1] - m2[1]
        dist_sq = dx * dx + dy * dy
        rsum = m1[2] + m2[2] - 1e-7
        if rsum <= 0:
            return False
        return dist_sq < rsum * rsum

    while True:
        n = len(clusters)
        if n <= 1:
            break
        best_i = -1
        best_j = -1
        best_r = float('inf')
        best_mec = None
        idxs = list(range(n))
        rng.shuffle(idxs)
        found = False

        for a in range(n):
            i = idxs[a]
            ci = clusters[i]['mec']
            pts_i = clusters[i]['pts']
            for b in range(a + 1, n):
                j = idxs[b]
                cj = clusters[j]['mec']
                pts_j = clusters[j]['pts']

                dx = ci[0] - cj[0]
                dy = ci[1] - cj[1]
                dist_sq = dx * dx + dy * dy
                threshold = 2.0 * max_r + ci[2] + cj[2]
                if dist_sq > threshold * threshold:
                    continue

                d = math.sqrt(dist_sq)
                if d + cj[2] <= ci[2] + 1e-9:
                    cx, cy, r = ci
                elif d + ci[2] <= cj[2] + 1e-9:
                    cx, cy, r = cj
                elif len(pts_i) == 1 and len(pts_j) == 1:
                    p1 = pts_i[0]
                    p2 = pts_j[0]
                    cx = (p1[0] + p2[0]) * 0.5
                    cy = (p1[1] + p2[1]) * 0.5
                    r = math.hypot(p1[0] - p2[0], p1[1] - p2[1]) * 0.5
                elif len(pts_i) == 1:
                    p = pts_i[0]
                    dxp = p[0] - cj[0]
                    dyp = p[1] - cj[1]
                    if dxp * dxp + dyp * dyp <= (cj[2] + 1e-9) * (cj[2] + 1e-9):
                        cx, cy, r = cj
                    else:
                        cx, cy, r = mec(pts_i + pts_j, rng)
                elif len(pts_j) == 1:
                    p = pts_j[0]
                    dxp = p[0] - ci[0]
                    dyp = p[1] - ci[1]
                    if dxp * dxp + dyp * dyp <= (ci[2] + 1e-9) * (ci[2] + 1e-9):
                        cx, cy, r = ci
                    else:
                        cx, cy, r = mec(pts_i + pts_j, rng)
                else:
                    cx, cy, r = mec(pts_i + pts_j, rng)

                if r > max_r or not fits(cx, cy, r):
                    continue

                valid = True
                for k in range(n):
                    if k == i or k == j:
                        continue
                    if overlap((cx, cy, r), clusters[k]['mec']):
                        valid = False
                        break
                if not valid:
                    continue

                if mode == 'first':
                    best_i, best_j, best_mec = i, j, (cx, cy, r)
                    found = True
                    break
                else:
                    score = r
                    if mode == 'random':
                        score = r + rng.random() * 5.0
                    if score < best_r:
                        best_r = score
                        best_i, best_j, best_mec = i, j, (cx, cy, r)
            if found:
                break

        if best_i == -1:
            break

        clusters[best_i]['indices'].extend(clusters[best_j]['indices'])
        clusters[best_i]['pts'].extend(clusters[best_j]['pts'])
        clusters[best_i]['mec'] = best_mec
        clusters.pop(best_j)

    return clusters

def try_triple_merges(clusters, w, h):
    rng = random.Random(42)
    max_r = min(w, h) * 0.5 + 1e-7

    def fits(cx, cy, r):
        return (cx - r >= -1e-7 and cx + r <= w + 1e-7 and
                cy - r >= -1e-7 and cy + r <= h + 1e-7)

    def overlap(m1, m2):
        dx = m1[0] - m2[0]
        dy = m1[1] - m2[1]
        dist_sq = dx * dx + dy * dy
        rsum = m1[2] + m2[2] - 1e-7
        if rsum <= 0:
            return False
        return dist_sq < rsum * rsum

    changed = True
    while changed:
        changed = False
        n = len(clusters)
        best = None
        best_r = float('inf')
        for i in range(n):
            for j in range(i + 1, n):
                for k in range(j + 1, n):
                    pts = clusters[i]['pts'] + clusters[j]['pts'] + clusters[k]['pts']
                    cx, cy, r = mec(pts, rng)
                    if not fits(cx, cy, r):
                        continue
                    valid = True
                    for l in range(n):
                        if l in (i, j, k):
                            continue
                        if overlap((cx, cy, r), clusters[l]['mec']):
                            valid = False
                            break
                    if valid and r < best_r:
                        best_r = r
                        best = (i, j, k, cx, cy, r)
        if best is not None:
            i, j, k, cx, cy, r = best
            clusters[i]['indices'].extend(clusters[j]['indices'])
            clusters[i]['indices'].extend(clusters[k]['indices'])
            clusters[i]['pts'].extend(clusters[j]['pts'])
            clusters[i]['pts'].extend(clusters[k]['pts'])
            clusters[i]['mec'] = (cx, cy, r)
            clusters.pop(k)
            clusters.pop(j)
            changed = True
    return clusters

def solve_round(dots, w, h):
    start = time.time()
    best_clusters = None
    best_k = len(dots) + 1

    clusters = greedy_solve(dots, w, h, seed=0, mode='best')
    if len(clusters) <= 20:
        clusters = try_triple_merges(clusters, w, h)
    if len(clusters) < best_k:
        best_k = len(clusters)
        best_clusters = clusters

    iteration = 1
    while time.time() - start < 25.0:
        if iteration % 4 == 0:
            mode = 'first'
        elif iteration % 2 == 1:
            mode = 'random'
        else:
            mode = 'best'
        clusters = greedy_solve(dots, w, h, seed=iteration, mode=mode)
        if len(clusters) <= 20:
            clusters = try_triple_merges(clusters, w, h)
        if len(clusters) < best_k:
            best_k = len(clusters)
            best_clusters = clusters
            if best_k == 1:
                break
        iteration += 1
        if iteration > 1000:
            break

    return best_clusters

def read_line(sock, buf):
    while b'\n' not in buf:
        data = sock.recv(4096)
        if not data:
            return None, buf
        buf += data
    idx = buf.index(b'\n')
    line = buf[:idx].decode('ascii')
    buf = buf[idx + 1:]
    return line, buf

def main():
    botname = os.environ.get('BOTNAME', '')
    if not botname:
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode('ascii'))

    buf = b''
    while True:
        line, buf = read_line(sock, buf)
        if line is None:
            break
        if line.startswith('ROUND'):
            parts = line.split()
            round_num = int(parts[1])
            w = int(parts[2])
            h = int(parts[3])
            N = int(parts[4])
            dots = []
            for _ in range(N):
                line, buf = read_line(sock, buf)
                if line is None:
                    return
                dp = line.split()
                idx = int(dp[1])
                x = int(dp[2])
                y = int(dp[3])
                dots.append((idx, x, y))

            clusters = solve_round(dots, w, h)

            out = []
            for c in clusters:
                cx, cy, r = c['mec']
                if r < 1e-7:
                    r = 1e-7
                out.append(f"CIRCLE {cx:.12g} {cy:.12g} {r:.12g}\n")
            out.append("END\n")
            sock.sendall(''.join(out).encode('ascii'))

            line, buf = read_line(sock, buf)
            if line is None:
                break
            line, buf = read_line(sock, buf)
            if line is None:
                break
        elif line.startswith('TOURNAMENT_END'):
            break

    sock.close()

if __name__ == '__main__':
    main()
