# bot author: Meta Muse Spark
# bot author: Muse Spark
import os, sys, socket, math

def solve_round(w, h, points):
    # merge coincident dots
    uniq = {}
    for x, y in points:
        uniq[(x, y)] = uniq.get((x, y), 0) + 1
    uniq_pts = list(uniq.keys())

    best_total = len(uniq_pts)
    best_large = []
    best_uncovered = uniq_pts

    configs = []

    # single centered
    r1 = min(w, h) / 2 * 0.8
    if r1 > 0.5:
        configs.append([(w/2, h/2, r1)])

    # two horizontal
    r2h = min(w/2, h) / 2 * 0.8
    if r2h > 0.5:
        configs.append([(w*0.25, h/2, r2h), (w*0.75, h/2, r2h)])

    # two vertical
    r2v = min(w, h/2) / 2 * 0.8
    if r2v > 0.5:
        configs.append([(w/2, h*0.25, r2v), (w/2, h*0.75, r2v)])

    # 2x2 grid
    r4 = min(w/2, h/2) / 2 * 0.8
    if r4 > 0.5:
        configs.append([
            (w*0.25, h*0.25, r4), (w*0.75, h*0.25, r4),
            (w*0.25, h*0.75, r4), (w*0.75, h*0.75, r4)
        ])

    # small grids 1..3
    for gx in range(1, 4):
        for gy in range(1, 4):
            if gx == 1 and gy == 1:
                continue
            cell_w = w / gx
            cell_h = h / gy
            r = min(cell_w, cell_h) / 2 * 0.7
            if r < 1.0:
                continue
            circles = []
            for iy in range(gy):
                for ix in range(gx):
                    cx = (ix + 0.5) * cell_w
                    cy = (iy + 0.5) * cell_h
                    circles.append((cx, cy, r))
            configs.append(circles)

    for circles in configs:
        uncovered = []
        ok = True
        for x, y in uniq_pts:
            covered = False
            min_gap = float('inf')
            for cx, cy, r in circles:
                d = math.hypot(x - cx, y - cy)
                if d <= r - 1e-4:
                    covered = True
                    break
                gap = d - r
                if gap < min_gap:
                    min_gap = gap
            if covered:
                continue
            if min_gap < 0.05:  # too close, tiny would overlap
                ok = False
                break
            uncovered.append((x, y))
        if not ok:
            continue
        total = len(circles) + len(uncovered)
        if total < best_total:
            best_total = total
            best_large = circles
            best_uncovered = uncovered

    result = []
    for cx, cy, r in best_large:
        result.append((cx, cy, r))
    for x, y in best_uncovered:
        result.append((float(x), float(y), 0.000001))
    return result

def main():
    botname = os.environ.get('BOTNAME')
    if not botname:
        sys.exit(1)

    s = socket.create_connection(('localhost', 7474))
    f = s.makefile('rwb', buffering=0)
    f.write((botname + '\n').encode())

    while True:
        line = f.readline()
        if not line:
            break
        line = line.decode().strip()
        if line.startswith('ROUND'):
            _, round_num, w, h, N = line.split()
            w = int(w); h = int(h); N = int(N)
            pts = []
            for _ in range(N):
                dot = f.readline().decode().strip()
                _, idx, x, y = dot.split()
                pts.append((int(x), int(y)))
            circles = solve_round(w, h, pts)
            for cx, cy, r in circles:
                f.write(f'CIRCLE {cx:.6f} {cy:.6f} {r:.6f}\n'.encode())
            f.write(b'END\n')
            # consume OK/INVALID and END_ROUND
            f.readline()
            f.readline()
        elif line == 'TOURNAMENT_END':
            break

    f.close()
    s.close()

if __name__ == '__main__':
    main()