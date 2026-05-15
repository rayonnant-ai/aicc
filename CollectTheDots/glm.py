# bot author: GLM 5.1 (z-ai/glm-5.1 via OpenRouter)
# bot author: Claude 3.5 Sonnet

import os
import sys
import socket
import math
import random

sys.setrecursionlimit(10000)

def mec(points):
    n = len(points)
    if n == 0:
        return (0.0, 0.0, 0.0)
    if n == 1:
        return (float(points[0][0]), float(points[0][1]), 0.0)
    pts = list(points)
    random.shuffle(pts)
    def c2(p1, p2):
        cx = (p1[0] + p2[0]) / 2.0
        cy = (p1[1] + p2[1]) / 2.0
        r = math.hypot(p1[0] - p2[0], p1[1] - p2[1]) / 2.0
        return (cx, cy, r)
    def c3(p1, p2, p3):
        ax, ay = float(p1[0]), float(p1[1])
        bx, by = float(p2[0]), float(p2[1])
        cx, cy = float(p3[0]), float(p3[1])
        d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(d) < 1e-12:
            d12 = (ax - bx)**2 + (ay - by)**2
            d13 = (ax - cx)**2 + (ay - cy)**2
            d23 = (bx - cx)**2 + (by - cy)**2
            if d12 >= d13 and d12 >= d23:
                return c2(p1, p2)
            elif d13 >= d23:
                return c2(p1, p3)
            else:
                return c2(p2, p3)
        ux = ((ax*ax+ay*ay)*(by-cy)+(bx*bx+by*by)*(cy-ay)+(cx*cx+cy*cy)*(ay-by)) / d
        uy = ((ax*ax+ay*ay)*(cx-bx)+(bx*bx+by*by)*(ax-cx)+(cx*cx+cy*cy)*(bx-ax)) / d
        r = math.hypot(ax - ux, ay - uy)
        return (ux, uy, r)
    def in_c(p, c):
        return (p[0] - c[0])**2 + (p[1] - c[1])**2 <= c[2]**2 + 1e-9
    def wlz(P, R):
        if not P or len(R) == 3:
            if not R:
                return (0.0, 0.0, 0.0)
            if len(R) == 1:
                return (float(R[0][0]), float(R[0][1]), 0.0)
            if len(R) == 2:
                return c2(R[0], R[1])
            return c3(R[0], R[1], R[2])
        p = P[-1]
        D = wlz(P[:-1], R)
        if in_c(p, D):
            return D
        return wlz(P[:-1], R + [p])
    return wlz(pts, [])

def fits(cx, cy, r, w, h):
    e = 1e-6
    return cx - r >= -e and cx + r <= w + e and cy - r >= -e and cy + r <= h + e

def overlaps(c1, c2):
    e = 1e-6
    d = math.hypot(c1[0] - c2[0], c1[1] - c2[1])
    return d < c1[2] + c2[2] - e

def find_circle(pts, w, h):
    if not pts:
        return None
    mc = mec(pts)
    cx, cy, r = mc
    if r < 1e-9:
        r = 1e-7
    if fits(cx, cy, r, w, h):
        return (cx, cy, r)
    best = None
    best_r = float('inf')
    starts = [(cx, cy), (w / 2.0, h / 2.0)]
    ax = sum(p[0] for p in pts) / len(pts)
    ay = sum(p[1] for p in pts) / len(pts)
    starts.append((ax, ay))
    for p in pts[:15]:
        starts.append((float(p[0]), float(p[1])))
    for i in range(min(len(pts), 10)):
        for j in range(i + 1, min(len(pts), 10)):
            starts.append(((pts[i][0] + pts[j][0]) / 2.0, (pts[i][1] + pts[j][1]) / 2.0))
    for sx, sy in starts:
        px, py = sx, sy
        for _ in range(80):
            pr = max(math.hypot(px - p[0], py - p[1]) for p in pts)
            if pr < 1e-9:
                pr = 1e-7
            nx = max(pr, min(w - pr, px))
            ny = max(pr, min(h - pr, py))
            if abs(nx - px) < 1e-12 and abs(ny - py) < 1e-12:
                break
            px, py = nx, ny
        pr = max(math.hypot(px - p[0], py - p[1]) for p in pts)
        if pr < 1e-9:
            pr = 1e-7
        if fits(px, py, pr, w, h) and pr < best_r:
            best_r = pr
            best = (px, py, pr)
    return best

def solve(w, h, dots):
    N = len(dots)
    if N == 0:
        return []
    mc = mec(dots)
    cx, cy, r = mc
    if r < 1e-9:
        r = 1e-7
    if fits(cx, cy, r, w, h):
        return [(cx, cy, r)]
    fc = find_circle(dots, w, h)
    if fc is not None:
        return [fc]
    clusters = [[i] for i in range(N)]
    circles = [(float(dots[i][0]), float(dots[i][1]), 1e-7) for i in range(N)]
    while len(clusters) > 1:
        best = None
        best_r = float('inf')
        nc = len(clusters)
        for i in range(nc):
            for j in range(i + 1, nc):
                mpts = [dots[k] for k in clusters[i]] + [dots[k] for k in clusters[j]]
                mc2 = mec(mpts)
                ccx, ccy, rr = mc2
                if rr < 1e-9:
                    rr = 1e-7
                if not fits(ccx, ccy, rr, w, h):
                    fc2 = find_circle(mpts, w, h)
                    if fc2 is None:
                        continue
                    ccx, ccy, rr = fc2
                ok = True
                for k in range(nc):
                    if k == i or k == j:
                        continue
                    if overlaps((ccx, ccy, rr), circles[k]):
                        ok = False
                        break
                if ok and rr < best_r:
                    best_r = rr
                    best = (i, j, ccx, ccy, rr)
        if best is None:
            break
        i, j, ccx, ccy, rr = best
        clusters[i] = clusters[i] + clusters[j]
        circles[i] = (ccx, ccy, rr)
        clusters.pop(j)
        circles.pop(j)
    return circles

def main():
    botname = os.environ.get('BOTNAME', '')
    if not botname:
        sys.exit(1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    buf = b''
    def readline():
        nonlocal buf
        while b'\n' not in buf:
            data = sock.recv(4096)
            if not data:
                return None
            buf += data
        i = buf.index(b'\n')
        line = buf[:i].decode('ascii')
        buf = buf[i + 1:]
        return line
    def sendline(s):
        sock.sendall((s + '\n').encode('ascii'))
    sendline(botname)
    while True:
        line = readline()
        if line is None or line == 'TOURNAMENT_END':
            break
        parts = line.split()
        if parts[0] != 'ROUND':
            continue
        w = int(parts[2])
        h = int(parts[3])
        N = int(parts[4])
        dots = []
        for _ in range(N):
            dl = readline()
            dp = dl.split()
            dots.append((int(dp[2]), int(dp[3])))
        result = solve(w, h, dots)
        for ccx, ccy, rr in result:
            sendline(f"CIRCLE {ccx:.10g} {ccy:.10g} {rr:.10g}")
        sendline("END")
        readline()
        readline()
    sock.close()

if __name__ == '__main__':
    main()
