# bot author: Grok (xAI) - heuristic greedy pair+single circle covering
import os
import socket
import sys
import math
from typing import List, Tuple

EPS = 1e-6

def dist(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

class Circle:
    def __init__(self, cx: float, cy: float, r: float, covered: List[int]):
        self.cx = cx
        self.cy = cy
        self.r = r
        self.covered = covered  # list of dot indices

def circle_inside(cx: float, cy: float, r: float, w: float, h: float) -> bool:
    return (cx - r >= -EPS) and (cx + r <= w + EPS) and (cy - r >= -EPS) and (cy + r <= h + EPS)

def circles_overlap(c1: Circle, c2: Circle) -> bool:
    d = dist((c1.cx, c1.cy), (c2.cx, c2.cy))
    return d < c1.r + c2.r - EPS

def covers_dot(cx: float, cy: float, r: float, px: float, py: float) -> bool:
    return dist((cx, cy), (px, py)) <= r + EPS

def main():
    try:
        botname = os.environ['BOTNAME']
        if not botname or not all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in botname) or len(botname) > 32:
            sys.exit(1)
    except KeyError:
        sys.exit(1)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 7474))
    s.sendall((botname + '\n').encode('ascii'))
    rfile = s.makefile('r', encoding='ascii', newline='\n')

    # Main loop
    while True:
        line = rfile.readline()
        if not line:
            break
        line = line.rstrip('\n\r')
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue

        if parts[0] == 'ROUND':
            round_num = int(parts[1])
            w = float(parts[2])
            h = float(parts[3])
            N = int(parts[4])

            dots = []
            for _ in range(N):
                dline = rfile.readline().rstrip('\n\r')
                dparts = dline.split()
                if dparts[0] == 'DOT':
                    idx = int(dparts[1])
                    x = float(dparts[2])
                    y = float(dparts[3])
                    dots.append((x, y, idx))

            # Now compute solution
            # Generate candidate circles: singles + pair diameters
            candidates: List[Circle] = []

            # Singles
            for i in range(N):
                x, y, idx = dots[i]
                max_r = min(x, w - x, y, h - y)
                if max_r > 0:
                    r = max(0.1, max_r * 0.95)  # safe
                    candidates.append(Circle(x, y, r, [idx]))

            # Pairs
            for i in range(N):
                for j in range(i + 1, N):
                    x1, y1, _ = dots[i]
                    x2, y2, _ = dots[j]
                    d = dist((x1, y1), (x2, y2))
                    if d < 1e-9:  # coincident
                        continue
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    r = d / 2 + 1e-9
                    if circle_inside(cx, cy, r, w, h):
                        covered = []
                        for k in range(N):
                            if covers_dot(cx, cy, r, dots[k][0], dots[k][1]):
                                covered.append(dots[k][2])
                        if len(covered) >= 2:
                            candidates.append(Circle(cx, cy, r, covered))

            # Greedy selection with non-overlap
            selected: List[Circle] = []
            covered_dots = set()
            remaining_dots = set(range(N))  # use indices in dots list? Wait, use dot idx

            dot_idx_to_list_idx = {dots[k][2]: k for k in range(N)}

            while len(covered_dots) < N:
                best_cand = None
                best_new = 0
                for cand in candidates:
                    if any(circles_overlap(cand, sel) for sel in selected):
                        continue
                    new_covered = [idx for idx in cand.covered if idx not in covered_dots]
                    if len(new_covered) > best_new:
                        best_new = len(new_covered)
                        best_cand = cand
                if best_cand is None or best_new == 0:
                    # Fallback: add singles for remaining
                    for i in range(N):
                        if dots[i][2] not in covered_dots:
                            x, y, idx = dots[i]
                            max_r = min(x, w - x, y, h - y)
                            r = max(0.1, max_r * 0.9)
                            fallback_c = Circle(x, y, r, [idx])
                            selected.append(fallback_c)
                            covered_dots.add(idx)
                            break
                    continue
                selected.append(best_cand)
                for idx in best_cand.covered:
                    covered_dots.add(idx)

            # Output
            payload = ''.join(
                f"CIRCLE {c.cx:.10f} {c.cy:.10f} {c.r:.10f}\n"
                for c in selected
            ) + "END\n"
            s.sendall(payload.encode('ascii'))

            # Read OK/INVALID and END_ROUND
            for _ in range(2):
                resp = rfile.readline()
                if not resp:
                    break

        elif parts[0] == 'TOURNAMENT_END':
            break
        elif parts[0] == 'OK' or parts[0] == 'INVALID' or parts[0] == 'END_ROUND':
            continue

    s.close()

if __name__ == "__main__":
    main()