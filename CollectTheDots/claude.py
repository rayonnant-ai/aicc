#!/usr/bin/env python3
# bot author: Claude Opus 4.7
"""CollectTheDots tournament bot.

Strategy: bottom-up hierarchical clustering with multiple restarts.

Start with one tiny circle per unique dot position. Repeatedly try to merge
pairs of clusters whose combined minimum enclosing circle (MEC):
  - fits inside the rectangle, and
  - does not overlap any other cluster's circle.
Merge whichever pair scores best under the current strategy.

We run multiple strategies (closest-first, smallest-resulting-radius,
smallest-growth, random) and keep the best result across attempts.

A known-valid trivial solution (one tiny circle per unique position) is
always carried as a fallback so that even an unexpected exception in the
solver still produces a valid submission.
"""

import math
import os
import random
import socket
import sys
import time


SERVER_HOST = 'localhost'
SERVER_PORT = 7474
EPS_SERVER = 1e-6
# Per-round budget. The server gives 30s wall-clock from the last DOT line
# to receiving our END line; we leave a comfortable margin for transmission.
ROUND_TIME_BUDGET = 26.0


# --------------------------- MEC (Welzl's) ---------------------------

def _circle_from_two(a, b):
    cx = (a[0] + b[0]) / 2.0
    cy = (a[1] + b[1]) / 2.0
    r = math.hypot(a[0] - b[0], a[1] - b[1]) / 2.0
    return (cx, cy, r)


def _circle_from_three(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        # Nearly collinear: use the diameter of the farthest pair.
        cands = ((a, b), (a, c), (b, c))
        best = max(cands, key=lambda pq: (pq[0][0] - pq[1][0]) ** 2 + (pq[0][1] - pq[1][1]) ** 2)
        return _circle_from_two(*best)
    aa = ax * ax + ay * ay
    bb = bx * bx + by * by
    cc = cx * cx + cy * cy
    ux = (aa * (by - cy) + bb * (cy - ay) + cc * (ay - by)) / d
    uy = (aa * (cx - bx) + bb * (ax - cx) + cc * (bx - ax)) / d
    r = math.hypot(ux - ax, uy - ay)
    return (ux, uy, r)


def _in_circle(p, c, eps=1e-10):
    dx = p[0] - c[0]
    dy = p[1] - c[1]
    return dx * dx + dy * dy <= c[2] * c[2] + eps


def mec(points):
    """Randomized incremental minimum enclosing circle (expected O(n))."""
    pts = [(float(p[0]), float(p[1])) for p in points]
    n = len(pts)
    if n == 0:
        return (0.0, 0.0, 0.0)
    random.shuffle(pts)
    c = (pts[0][0], pts[0][1], 0.0)
    for i in range(1, n):
        if not _in_circle(pts[i], c):
            c = (pts[i][0], pts[i][1], 0.0)
            for j in range(i):
                if not _in_circle(pts[j], c):
                    c = _circle_from_two(pts[i], pts[j])
                    for k in range(j):
                        if not _in_circle(pts[k], c):
                            c = _circle_from_three(pts[i], pts[j], pts[k])
    # Tighten the radius so every point is exactly inside, guarding against
    # float drift accumulated in the in-circle test.
    max_d_sq = 0.0
    for p in pts:
        dsq = (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2
        if dsq > max_d_sq:
            max_d_sq = dsq
    final_r = math.sqrt(max_d_sq)
    if final_r > c[2]:
        c = (c[0], c[1], final_r)
    return c


# --------------------------- Geometry helpers ---------------------------

def fits_rect(circle, w, h, margin=0.0):
    cx, cy, r = circle
    return (cx - r >= -margin and cx + r <= w + margin and
            cy - r >= -margin and cy + r <= h + margin)


def circles_overlap_sq(c1, c2, margin=0.0):
    """Squared-distance overlap test (one fewer sqrt than math.hypot)."""
    s = c1[2] + c2[2] - margin
    if s <= 0:
        return False
    dx = c1[0] - c2[0]
    dy = c1[1] - c2[1]
    return dx * dx + dy * dy < s * s


# --------------------------- Circle construction ---------------------------

def construct_circle(points, w, h):
    """Return a valid (cx, cy, r) covering all `points` inside the rectangle.

    May return a circle whose extent is up to ~5e-7 outside the rectangle,
    which is comfortably inside the server's 1e-6 tolerance. Returns None
    if the cluster is geometrically infeasible (i.e., no single rectangle-
    bounded circle can cover all of `points`).
    """
    if not points:
        return None
    # Coincident-only points (including singletons) always admit a valid tiny
    # covering under the server's tolerance, even at rectangle corners.
    px, py = points[0]
    if all(p[0] == px and p[1] == py for p in points):
        return (float(px), float(py), 1e-7)
    cx, cy, r = mec(points)
    r = max(r, 1e-9)  # enforce r > 0

    # If the MEC already fits (with a tiny safety margin), use it.
    if fits_rect((cx, cy, r), w, h, margin=-EPS_SERVER * 0.1):
        return (cx, cy, r)

    # MEC extends outside the rectangle. Iteratively shift the center inside
    # the rectangle and re-tighten the radius. If the radius keeps growing
    # past min(w, h)/2, the cluster cannot fit inside any rectangle-bounded
    # covering circle.
    prev_r = -1.0
    for _ in range(50):
        if 2 * r > w + EPS_SERVER * 0.1 or 2 * r > h + EPS_SERVER * 0.1:
            return None
        new_cx = max(r, min(w - r, cx))
        new_cy = max(r, min(h - r, cy))
        max_d_sq = 0.0
        for x, y in points:
            dsq = (x - new_cx) ** 2 + (y - new_cy) ** 2
            if dsq > max_d_sq:
                max_d_sq = dsq
        new_r = max(math.sqrt(max_d_sq), 1e-9)
        cx, cy, r = new_cx, new_cy, new_r
        if abs(r - prev_r) < 1e-12:
            break
        prev_r = r

    if 2 * r > w + EPS_SERVER * 0.1 or 2 * r > h + EPS_SERVER * 0.1:
        return None
    if fits_rect((cx, cy, r), w, h, margin=EPS_SERVER * 0.5):
        return (cx, cy, r)
    return None


def tiny_circle_at(pos):
    """A guaranteed-valid tiny circle at a single dot position.

    Uses r = 1e-7 (within the server's 1e-6 tolerance) so dots on rectangle
    edges and corners are still legally covered.
    """
    return (float(pos[0]), float(pos[1]), 1e-7)


# --------------------------- Solver ---------------------------

def trivial_solution(dots):
    """One tiny circle per unique dot position. Always valid."""
    seen = set()
    out = []
    for x, y in dots:
        key = (x, y)
        if key in seen:
            continue
        seen.add(key)
        out.append(tiny_circle_at(key))
    return out


def _initial_state(dots, w, h):
    """Group coincident dots; return (clusters, circles) for the starting state."""
    pos_to_indices = {}
    for i, (x, y) in enumerate(dots):
        pos_to_indices.setdefault((x, y), []).append(i)
    clusters = [list(idxs) for idxs in pos_to_indices.values()]
    circles = []
    for cluster in clusters:
        pts = [dots[i] for i in cluster]
        c = construct_circle(pts, w, h)
        if c is None:
            # Singleton at a position can always be covered by a tiny circle.
            c = tiny_circle_at(dots[cluster[0]])
        circles.append(c)
    return clusters, circles


def _try_merge(c_i, c_j, cluster_i, cluster_j, circles, n, i, j, dots, w, h):
    """Try to merge clusters i and j; return new circle or None."""
    merged_idx = cluster_i + cluster_j
    pts = [dots[k] for k in merged_idx]
    c = construct_circle(pts, w, h)
    if c is None:
        return None, None
    for k in range(n):
        if k == i or k == j:
            continue
        if circles_overlap_sq(c, circles[k], margin=EPS_SERVER * 0.5):
            return None, None
    return c, merged_idx


def _apply_merge(clusters, circles, i, j, merged_idx, merged_circle):
    n = len(clusters)
    new_clusters = []
    new_circles = []
    for k in range(n):
        if k == i or k == j:
            continue
        new_clusters.append(clusters[k])
        new_circles.append(circles[k])
    new_clusters.append(merged_idx)
    new_circles.append(merged_circle)
    return new_clusters, new_circles


def _hierarchical_merge(initial_clusters, initial_circles, w, h, dots, deadline, mode):
    """One greedy run.

    mode = 'distance'  : pick the closest valid pair each pass (first match wins)
    mode = 'random'    : try pairs in random order, first valid wins
    mode = 'best_radius': pick the pair whose merged circle has smallest radius
    mode = 'best_growth': pick the pair with smallest radius growth over max(r_i, r_j)

    Returns (clusters, circles).
    """
    clusters = [list(c) for c in initial_clusters]
    circles = list(initial_circles)

    while time.time() < deadline:
        n = len(clusters)
        if n <= 1:
            break

        if mode in ('distance', 'random'):
            pairs = []
            for i in range(n):
                ci = circles[i]
                for j in range(i + 1, n):
                    cj = circles[j]
                    d_sq = (ci[0] - cj[0]) ** 2 + (ci[1] - cj[1]) ** 2
                    pairs.append((d_sq, i, j))
            if mode == 'random':
                random.shuffle(pairs)
            else:
                pairs.sort(key=lambda x: x[0])

            merged_any = False
            for _, i, j in pairs:
                if time.time() >= deadline:
                    return clusters, circles
                merged_circle, merged_idx = _try_merge(
                    circles[i], circles[j], clusters[i], clusters[j],
                    circles, n, i, j, dots, w, h
                )
                if merged_circle is None:
                    continue
                clusters, circles = _apply_merge(clusters, circles, i, j, merged_idx, merged_circle)
                merged_any = True
                break

            if not merged_any:
                break

        else:  # best_radius or best_growth
            best_score = float('inf')
            best = None
            for i in range(n):
                if time.time() >= deadline:
                    return clusters, circles
                ci = circles[i]
                for j in range(i + 1, n):
                    cj = circles[j]
                    merged_circle, merged_idx = _try_merge(
                        ci, cj, clusters[i], clusters[j],
                        circles, n, i, j, dots, w, h
                    )
                    if merged_circle is None:
                        continue
                    if mode == 'best_radius':
                        score = merged_circle[2]
                    else:  # best_growth
                        score = merged_circle[2] - max(ci[2], cj[2])
                    if score < best_score:
                        best_score = score
                        best = (i, j, merged_circle, merged_idx)

            if best is None:
                break
            i, j, mc, mi = best
            clusters, circles = _apply_merge(clusters, circles, i, j, mi, mc)

    return clusters, circles


def _verify(circles, w, h, dots):
    """Self-check a candidate solution against the server's rules.

    Uses a stricter margin (5e-7) than the server's 1e-6 so accepted
    solutions have headroom against any final float jitter.
    """
    for cx, cy, r in circles:
        if r <= 0:
            return False
        if not (cx - r >= -EPS_SERVER * 0.5 and cx + r <= w + EPS_SERVER * 0.5 and
                cy - r >= -EPS_SERVER * 0.5 and cy + r <= h + EPS_SERVER * 0.5):
            return False
    n = len(circles)
    for i in range(n):
        for j in range(i + 1, n):
            if circles_overlap_sq(circles[i], circles[j], margin=EPS_SERVER * 0.5):
                return False
    for x, y in dots:
        covered = False
        for cx, cy, r in circles:
            dx = x - cx
            dy = y - cy
            slack = r + EPS_SERVER * 0.5
            if dx * dx + dy * dy <= slack * slack:
                covered = True
                break
        if not covered:
            return False
    return True


def _perturb_clusters(clusters, circles, dots, w, h, n_splits):
    """Split `n_splits` clusters into singletons. Returns new (clusters, circles)."""
    indices_to_split = [k for k in range(len(clusters)) if len(clusters[k]) > 1]
    if not indices_to_split:
        return clusters, circles
    n_splits = min(n_splits, len(indices_to_split))
    chosen = random.sample(indices_to_split, n_splits)
    chosen_set = set(chosen)
    new_clusters = []
    new_circles = []
    for k in range(len(clusters)):
        if k in chosen_set:
            for d_idx in clusters[k]:
                pts = [dots[d_idx]]
                c = construct_circle(pts, w, h)
                if c is None:
                    c = tiny_circle_at(dots[d_idx])
                new_clusters.append([d_idx])
                new_circles.append(c)
        else:
            new_clusters.append(clusters[k])
            new_circles.append(circles[k])
    return new_clusters, new_circles


def solve_round(w, h, dots, deadline):
    """Solve one round; return list of (cx, cy, r) circles."""
    # Always have a known-valid fallback.
    best = trivial_solution(dots)

    initial_clusters, initial_circles = _initial_state(dots, w, h)

    if len(initial_circles) < len(best) and _verify(initial_circles, w, h, dots):
        best = initial_circles

    best_clusters_for_perturb = None  # track clusters of the best solution

    # Try several greedy strategies in a fixed order.
    strategies = ['distance', 'best_radius', 'best_growth']
    for strategy in strategies:
        if time.time() >= deadline:
            break
        try:
            cands_clusters, cands_circles = _hierarchical_merge(
                initial_clusters, initial_circles, w, h, dots, deadline, strategy
            )
        except Exception:
            continue
        if cands_circles is not None and len(cands_circles) < len(best) and _verify(cands_circles, w, h, dots):
            best = cands_circles
            best_clusters_for_perturb = cands_clusters

    # Random restarts and perturbation-based restarts.
    attempts = 0
    while time.time() < deadline and attempts < 500:
        attempts += 1
        try:
            if (attempts % 3 == 0 and best_clusters_for_perturb is not None
                    and len(best_clusters_for_perturb) > 1):
                # Perturb: split 1-2 random clusters, then re-greedy.
                n_splits = random.randint(1, 2)
                seed_circles = _circles_for_clusters(best_clusters_for_perturb, dots, w, h)
                seed_clusters, seed_circles = _perturb_clusters(
                    best_clusters_for_perturb, seed_circles, dots, w, h, n_splits
                )
                mode = random.choice(['distance', 'random', 'best_radius'])
            else:
                seed_clusters = initial_clusters
                seed_circles = initial_circles
                mode = 'random'
            cands_clusters, cands_circles = _hierarchical_merge(
                seed_clusters, seed_circles, w, h, dots, deadline, mode
            )
        except Exception:
            continue
        if (cands_circles is not None and len(cands_circles) < len(best)
                and _verify(cands_circles, w, h, dots)):
            best = cands_circles
            best_clusters_for_perturb = cands_clusters

    return best


def _circles_for_clusters(clusters, dots, w, h):
    """Compute (or fall back) a valid circle for each cluster."""
    out = []
    for cluster in clusters:
        pts = [dots[i] for i in cluster]
        c = construct_circle(pts, w, h)
        if c is None:
            c = tiny_circle_at(dots[cluster[0]])
        out.append(c)
    return out


# --------------------------- Wire protocol ---------------------------

def _format_float(f):
    """Format a float for the wire. repr() round-trips and matches the server regex."""
    return repr(f)


def _run_tournament(sock):
    # Buffered reader; we write directly via sock.sendall.
    reader = sock.makefile('r', encoding='ascii', newline='\n', buffering=8192)

    def readline():
        s = reader.readline()
        if not s:
            return None
        return s.rstrip('\n')

    def send(text):
        sock.sendall(text.encode('ascii'))

    while True:
        line = readline()
        if line is None or line == 'TOURNAMENT_END':
            return
        if not line.startswith('ROUND '):
            continue  # ignore unexpected line
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            _round_num = int(parts[1])
            w = int(parts[2])
            h = int(parts[3])
            n = int(parts[4])
        except ValueError:
            continue

        dots = []
        for _ in range(n):
            dl = readline()
            if dl is None:
                return
            dp = dl.split()
            if len(dp) < 4:
                continue
            try:
                x = int(dp[2])
                y = int(dp[3])
            except ValueError:
                continue
            dots.append((x, y))

        deadline = time.time() + ROUND_TIME_BUDGET
        try:
            circles = solve_round(w, h, dots, deadline)
            if not circles or not _verify(circles, w, h, dots):
                circles = trivial_solution(dots)
        except Exception:
            circles = trivial_solution(dots)

        out_lines = []
        for (cx, cy, r) in circles:
            out_lines.append(
                'CIRCLE ' + _format_float(cx) + ' ' + _format_float(cy) + ' ' + _format_float(r)
            )
        out_lines.append('END')
        send('\n'.join(out_lines) + '\n')

        # Per spec, after END the server sends one result line then END_ROUND.
        result_line = readline()
        if result_line is None:
            return
        end_round_line = readline()
        if end_round_line is None:
            return


def main():
    botname = os.environ.get('BOTNAME', '')
    if not botname:
        sys.stderr.write('BOTNAME env var missing or empty\n')
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((SERVER_HOST, SERVER_PORT))
        sock.sendall((botname + '\n').encode('ascii'))
        _run_tournament(sock)
    finally:
        try:
            sock.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()