# bot author: Grok Expert 4.20
#!/usr/bin/env python3
# CollectTheDots bot - greedy largest-first non-overlapping circle cover
# Uses all pair diameter circles + triple circumcircles that fit inside rectangle
# Greedy selection by coverage size, then tiny circles for leftovers
# bot author: Grok (xAI)

import socket
import os
import sys
import math

def circle_from_two(p1, p2):
    x1, y1 = p1
    x2, y2 = p2
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    r = math.hypot(x1 - x2, y1 - y2) / 2.0
    return (cx, cy, r)

def circle_from_three(p1, p2, p3):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        d12 = math.hypot(x1 - x2, y1 - y2)
        d13 = math.hypot(x1 - x3, y1 - y3)
        d23 = math.hypot(x2 - x3, y2 - y3)
        if d12 >= d13 and d12 >= d23:
            return circle_from_two(p1, p2)
        elif d13 >= d12 and d13 >= d23:
            return circle_from_two(p1, p3)
        else:
            return circle_from_two(p2, p3)
    ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    r = math.hypot(ux - x1, uy - y1)
    return (ux, uy, r)

def is_valid_circle(circ, w, h):
    cx, cy, r = circ
    eps = 1e-6
    return (r > 0 and
            cx - r >= -eps and cx + r <= w + eps and
            cy - r >= -eps and cy + r <= h + eps)

def point_in_circle(p, circ):
    px, py = p
    cx, cy, r = circ
    return math.hypot(px - cx, py - cy) <= r + 1e-9

def get_circles(points, w, h):
    N = len(points)
    if N == 0:
        return []
    possible = []
    # All pairs (diameter circles)
    for i in range(N):
        for j in range(i + 1, N):
            circ = circle_from_two(points[i], points[j])
            if is_valid_circle(circ, w, h):
                covered = [k for k in range(N) if point_in_circle(points[k], circ)]
                if len(covered) >= 2:
                    possible.append((circ, covered))
    # All triples (circumcircles, fallback to diameter if collinear)
    for i in range(N):
        for j in range(i + 1, N):
            for k in range(j + 1, N):
                circ = circle_from_three(points[i], points[j], points[k])
                if is_valid_circle(circ, w, h) and circ[2] > 1e-12:
                    covered = [m for m in range(N) if point_in_circle(points[m], circ)]
                    if len(covered) >= 3:
                        possible.append((circ, covered))
    # Sort by number of points covered (largest first)
    possible.sort(key=lambda item: len(item[1]), reverse=True)
    selected = []
    uncovered = set(range(N))
    for circ, cov_list in possible:
        if len(uncovered) == 0:
            break
        cov_set = set(cov_list)
        new_cov = cov_set & uncovered
        if len(new_cov) == 0:
            continue
        # Check non-overlap with already selected
        cx, cy, r = circ
        overlaps = False
        for sel in selected:
            sx, sy, sr = sel
            d = math.hypot(cx - sx, cy - sy)
            if d < r + sr - 1e-9:
                overlaps = True
                break
        if not overlaps:
            selected.append(circ)
            uncovered -= new_cov
    # Tiny circles for any remaining points (always valid with tolerance)
    for i in uncovered:
        x, y = points[i]
        selected.append((float(x), float(y), 1e-6))
    return selected

def main():
    botname = os.environ.get('BOTNAME')
    if not botname:
        print("ERROR: BOTNAME environment variable not set", file=sys.stderr)
        sys.exit(1)
    HOST = 'localhost'
    PORT = 7474
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            s.sendall((botname + '\n').encode('ascii'))
            f = s.makefile('r', encoding='ascii', newline='\n')
            w = h = N = round_num = None
            points = []
            while True:
                line = f.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                if line.startswith('ROUND '):
                    parts = line.split()
                    round_num = int(parts[1])
                    w = int(parts[2])
                    h = int(parts[3])
                    N = int(parts[4])
                    points = []
                elif line.startswith('DOT '):
                    parts = line.split()
                    # idx = int(parts[1])  # not needed, order matches
                    x = int(parts[2])
                    y = int(parts[3])
                    points.append((x, y))
                    if len(points) == N and N > 0:
                        # All dots received - compute and submit
                        circles = get_circles(points, w, h)
                        for cx, cy, r in circles:
                            msg = f"CIRCLE {cx:.10f} {cy:.10f} {r:.10f}\n"
                            s.sendall(msg.encode('ascii'))
                        s.sendall(b"END\n")
                elif line.startswith('TOURNAMENT_END'):
                    break
                # OK, INVALID, END_ROUND are consumed automatically; no action needed
    except Exception as e:
        print(f"Connection error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()