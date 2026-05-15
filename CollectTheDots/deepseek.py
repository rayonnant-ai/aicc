# bot author: DeepSeek V4-Pro (deepseek/deepseek-v4-pro via OpenRouter)
# bot author: Assistant-v1
import os
import sys
import socket
import math
import time

def clamp_point(px, py, w, h, r0=0.49):
    """Return a safe circle center for point (px,py) with small radius r0, inside rectangle.
    Returns None if impossible (corner case)."""
    cx = max(r0, min(w - r0, px))
    cy = max(r0, min(h - r0, py))
    if math.hypot(px - cx, py - cy) <= r0 + 1e-9:
        return (cx, cy)
    return None

def solve_round(w, h, dots):
    points = list(dots)  # keep duplicates as separate coverage targets
    N = len(points)
    if N == 0:
        return []  # shouldn't happen

    # group unique coordinates for trivial fallback
    unique_coords = set()
    for x, y in points:
        unique_coords.add((x, y))

    # compute a trivial solution: one circle per unique coordinate (covers coincident dots)
    trivial_circles = []
    for (x, y) in unique_coords:
        center = clamp_point(x, y, w, h)
        if center is None:
            continue  # skip corner dots (should not occur)
        cx, cy = center
        trivial_circles.append((cx, cy, 0.49))

    start_time = time.perf_counter()
    time_limit = 25.0  # seconds for heuristic improvement

    # candidate centers for greedy covering
    candidates = set()
    step = max(5, int(min(w, h) // 10))
    for gx in range(0, w + 1, step):
        for gy in range(0, h + 1, step):
            candidates.add((float(gx), float(gy)))
    for (x, y) in unique_coords:
        c = clamp_point(x, y, w, h)
        if c:
            candidates.add(c)
    for (x, y) in points:
        candidates.add((float(x), float(y)))

    uncovered = set(range(N))
    placed = []

    while uncovered and (time.perf_counter() - start_time) < time_limit:
        best_cov = -1
        best_r = 0.0
        best_cx, best_cy = None, None

        for cx, cy in candidates:
            # maximum allowable radius considering rectangle bounds
            rmax = min(cx, w - cx, cy, h - cy)
            if rmax <= 0:
                continue
            # shrink due to existing circles
            for pcx, pcy, pr in placed:
                d = math.hypot(cx - pcx, cy - pcy)
                allowed = d - pr
                if allowed < rmax:
                    rmax = allowed
                    if rmax <= 0:
                        break
            if rmax <= 0:
                continue

            # count covered currently uncovered points
            cov = 0
            for idx in uncovered:
                px, py = points[idx]
                if math.hypot(cx - px, cy - py) <= rmax + 1e-9:
                    cov += 1
            if cov > best_cov or (cov == best_cov and rmax > best_r):
                best_cov = cov
                best_r = rmax
                best_cx, best_cy = cx, cy

        if best_cov == 0:
            break  # cannot cover any more points with the current candidates

        # place the best circle
        placed.append((best_cx, best_cy, best_r))
        # remove covered points
        covered_now = []
        for idx in list(uncovered):
            px, py = points[idx]
            if math.hypot(best_cx - px, best_cy - py) <= best_r + 1e-9:
                covered_now.append(idx)
        uncovered.difference_update(covered_now)

    # If time ran out, fallback to trivial
    if time.perf_counter() - start_time >= time_limit:
        return trivial_circles

    # If any point still uncovered, try to add tiny safe circles
    if uncovered:
        for idx in list(uncovered):
            px, py = points[idx]
            # try the clamped center first (updated with current placed circles)
            c = clamp_point(px, py, w, h)
            if c:
                cx, cy = c
                rmax = min(cx, w - cx, cy, h - cy)
                for pcx, pcy, pr in placed:
                    d = math.hypot(cx - pcx, cy - pcy)
                    allowed = d - pr
                    if allowed < rmax:
                        rmax = allowed
                if rmax > 0 and math.hypot(cx - px, cy - py) <= rmax + 1e-9:
                    placed.append((cx, cy, rmax))
                    uncovered.remove(idx)
                    continue
            # local search around the point
            found = False
            for dx in (0.0, 0.1, -0.1, 0.2, -0.2, 0.3, -0.3, 0.4, -0.4, 0.5, -0.5):
                for dy in (0.0, 0.1, -0.1, 0.2, -0.2, 0.3, -0.3, 0.4, -0.4, 0.5, -0.5):
                    nx, ny = px + dx, py + dy
                    if nx < 0 or nx > w or ny < 0 or ny > h:
                        continue
                    rmax = min(nx, w - nx, ny, h - ny)
                    for pcx, pcy, pr in placed:
                        d = math.hypot(nx - pcx, ny - pcy)
                        allowed = d - pr
                        if allowed < rmax:
                            rmax = allowed
                    if rmax > 0 and math.hypot(nx - px, ny - py) <= rmax + 1e-9:
                        placed.append((nx, ny, rmax))
                        uncovered.remove(idx)
                        found = True
                        break
                if found:
                    break
            if not found:
                # last resort: use the original trivial circle (might be invalid, but fallback)
                # This should not happen for well-formed puzzles
                pass

    # select the better between placed and trivial
    if len(placed) < len(trivial_circles):
        best = placed
    else:
        best = trivial_circles

    # ensure radii > 0
    final = []
    for cx, cy, r in best:
        if r <= 0:
            r = 1e-6
        final.append((cx, cy, r))
    return final

def main():
    botname = os.environ.get('BOTNAME')
    if not botname:
        sys.exit(1)
    if not (1 <= len(botname) <= 32 and all(c.isalnum() or c in '_-' for c in botname)):
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(('localhost', 7474))
    except Exception:
        sys.exit(1)

    sock.sendall(f"{botname}\n".encode('ascii'))
    f = sock.makefile('r', buffering=1, encoding='ascii')

    try:
        while True:
            line = f.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith('ROUND'):
                parts = line.split()
                # parts: ROUND round_num w h N
                round_num = parts[1]  # not needed
                w = int(parts[2])
                h = int(parts[3])
                n = int(parts[4])
                dots = []
                for _ in range(n):
                    dot_line = f.readline().strip()
                    _, idx, xs, ys = dot_line.split()
                    dots.append((int(xs), int(ys)))
                circles = solve_round(w, h, dots)
                for cx, cy, r in circles:
                    sock.sendall(f"CIRCLE {cx:.8f} {cy:.8f} {r:.8f}\n".encode('ascii'))
                sock.sendall(b"END\n")
                # Read result and END_ROUND
                res = f.readline()  # OK / INVALID
                end_round = f.readline()
            elif line == 'TOURNAMENT_END':
                break
    finally:
        sock.close()

if __name__ == '__main__':
    main()
