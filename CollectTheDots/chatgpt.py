# bot author: ChatGPT GPT 5.5
# bot author: GPT-5.5 Thinking
#
# CollectTheDots tournament client.
# Python 3.10, standard library only.

import math
import os
import random
import socket
import sys
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional


HOST = "localhost"
PORT = 7474

# Server tolerance is 1e-6. We use tiny singleton circles that are safely valid
# even for edge/corner dots under the stated tolerance.
TINY_R = 1e-7

# Stop heuristic search before the round deadline.
ROUND_TIME_LIMIT = 28.0


Point = Tuple[float, float]


@dataclass
class Circle:
    cx: float
    cy: float
    r: float


@dataclass
class Cluster:
    points: List[Point]
    circle: Circle


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def circle_contains(c: Circle, p: Point, eps: float = 1e-9) -> bool:
    return math.hypot(p[0] - c.cx, p[1] - c.cy) <= c.r + eps


def circle_from_two(a: Point, b: Point) -> Circle:
    cx = (a[0] + b[0]) / 2.0
    cy = (a[1] + b[1]) / 2.0
    r = dist(a, b) / 2.0
    return Circle(cx, cy, r)


def circle_from_three(a: Point, b: Point, c: Point) -> Optional[Circle]:
    ax, ay = a
    bx, by = b
    cx, cy = c

    d = 2.0 * (
        ax * (by - cy)
        + bx * (cy - ay)
        + cx * (ay - by)
    )

    if abs(d) < 1e-12:
        return None

    ax2ay2 = ax * ax + ay * ay
    bx2by2 = bx * bx + by * by
    cx2cy2 = cx * cx + cy * cy

    ux = (
        ax2ay2 * (by - cy)
        + bx2by2 * (cy - ay)
        + cx2cy2 * (ay - by)
    ) / d

    uy = (
        ax2ay2 * (cx - bx)
        + bx2by2 * (ax - cx)
        + cx2cy2 * (bx - ax)
    ) / d

    r = math.hypot(ux - ax, uy - ay)
    return Circle(ux, uy, r)


def minimum_enclosing_circle(points: List[Point]) -> Circle:
    """
    Randomized incremental minimum enclosing circle.

    The points are small in number, so this is fast enough for repeated
    greedy merge attempts.
    """
    pts = points[:]
    random.shuffle(pts)

    c: Optional[Circle] = None

    for i, p in enumerate(pts):
        if c is not None and circle_contains(c, p):
            continue

        c = Circle(p[0], p[1], 0.0)

        for j in range(i):
            q = pts[j]
            if circle_contains(c, q):
                continue

            c = circle_from_two(p, q)

            for k in range(j):
                r = pts[k]
                if circle_contains(c, r):
                    continue

                cc = circle_from_three(p, q, r)
                if cc is not None:
                    c = cc
                else:
                    # Collinear fallback: use the widest pair among p, q, r.
                    pairs = [
                        (dist(p, q), p, q),
                        (dist(p, r), p, r),
                        (dist(q, r), q, r),
                    ]
                    _, u, v = max(pairs, key=lambda x: x[0])
                    c = circle_from_two(u, v)

    if c is None:
        # Should not happen for generated rounds, because N >= 5.
        return Circle(0.0, 0.0, TINY_R)

    # Add a minuscule cushion for floating point MEC construction.
    # The server allows 1e-6, so this is conservative.
    return Circle(c.cx, c.cy, max(c.r, 0.0) + 1e-10)


def singleton_circle(p: Point, w: int, h: int) -> Circle:
    """
    Always-valid fallback circle for one coordinate.

    For interior and edge dots this is exactly valid. For true corner dots,
    exact positive-radius containment is geometrically impossible under the
    spec's strict model, but the server tolerance makes this tiny inward circle
    cover the corner while remaining inside the rectangle.
    """
    x, y = p
    r = TINY_R
    cx = min(max(x, r), w - r)
    cy = min(max(y, r), h - r)
    return Circle(cx, cy, r)


def circle_inside_rect(c: Circle, w: int, h: int) -> bool:
    # Allow a tiny numerical slack, far below server tolerance.
    slack = 1e-8
    return (
        c.r > 0.0
        and c.cx - c.r >= -slack
        and c.cx + c.r <= w + slack
        and c.cy - c.r >= -slack
        and c.cy + c.r <= h + slack
    )


def circles_nonoverlap(a: Circle, b: Circle) -> bool:
    # Require almost exact non-overlap. We do not intentionally exploit
    # the server's overlap tolerance.
    return math.hypot(a.cx - b.cx, a.cy - b.cy) + 1e-9 >= a.r + b.r


def valid_merge_circle(points: List[Point], w: int, h: int) -> Optional[Circle]:
    if len(points) == 1:
        return singleton_circle(points[0], w, h)

    c = minimum_enclosing_circle(points)

    if not circle_inside_rect(c, w, h):
        return None

    for p in points:
        if not circle_contains(c, p, eps=1e-7):
            return None

    return c


def initial_clusters(raw_points: List[Tuple[int, int]], w: int, h: int) -> List[Cluster]:
    # Coincident dots can and should be covered by one circle.
    unique = sorted(set((float(x), float(y)) for x, y in raw_points))

    clusters: List[Cluster] = []
    for p in unique:
        clusters.append(Cluster([p], singleton_circle(p, w, h)))

    return clusters


def merge_is_compatible(
    new_circle: Circle,
    clusters: List[Cluster],
    i: int,
    j: int,
) -> bool:
    for k, cl in enumerate(clusters):
        if k == i or k == j:
            continue
        if not circles_nonoverlap(new_circle, cl.circle):
            return False
    return True


def cluster_score(points: List[Point], c: Circle) -> float:
    """
    Lower is better. Prefer compact circles that cover many points.
    """
    n = len(points)
    return c.r / max(1, n - 1)


def improve_clusters(clusters: List[Cluster], w: int, h: int, deadline: float) -> List[Cluster]:
    """
    Greedy agglomerative merging.

    At each step, try all pairwise cluster merges and choose the best valid,
    non-overlapping merge. This is deliberately conservative: validity beats
    cleverness, because an invalid submission scores zero.
    """
    while time.monotonic() < deadline and len(clusters) > 1:
        best = None

        m = len(clusters)
        for i in range(m):
            if time.monotonic() >= deadline:
                break

            for j in range(i + 1, m):
                pts = clusters[i].points + clusters[j].points

                c = valid_merge_circle(pts, w, h)
                if c is None:
                    continue

                if not merge_is_compatible(c, clusters, i, j):
                    continue

                score = cluster_score(pts, c)

                # Tie-break toward merging more points, then smaller radius.
                candidate = (score, -len(pts), c.r, i, j, c, pts)
                if best is None or candidate < best:
                    best = candidate

        if best is None:
            break

        _, _, _, i, j, c, pts = best

        new_clusters: List[Cluster] = []
        for k, cl in enumerate(clusters):
            if k != i and k != j:
                new_clusters.append(cl)
        new_clusters.append(Cluster(pts, c))
        clusters = new_clusters

    return clusters


def repair_if_needed(clusters: List[Cluster], raw_points: List[Tuple[int, int]], w: int, h: int) -> List[Cluster]:
    """
    Defensive final validation. If anything suspicious is found, fall back to
    one tiny circle per unique coordinate, which is the safest valid covering.
    """
    circles = [cl.circle for cl in clusters]

    for c in circles:
        if not circle_inside_rect(c, w, h):
            return initial_clusters(raw_points, w, h)

    for i in range(len(circles)):
        for j in range(i + 1, len(circles)):
            if not circles_nonoverlap(circles[i], circles[j]):
                return initial_clusters(raw_points, w, h)

    for x, y in raw_points:
        p = (float(x), float(y))
        covered = False
        for c in circles:
            if math.hypot(p[0] - c.cx, p[1] - c.cy) <= c.r + 5e-7:
                covered = True
                break
        if not covered:
            return initial_clusters(raw_points, w, h)

    return clusters


def solve_round(w: int, h: int, points: List[Tuple[int, int]]) -> List[Circle]:
    start = time.monotonic()
    deadline = start + ROUND_TIME_LIMIT

    clusters = initial_clusters(points, w, h)

    # Deterministic-enough randomization while still varying between rounds.
    random.seed((w, h, len(points), tuple(points)))

    clusters = improve_clusters(clusters, w, h, deadline)
    clusters = repair_if_needed(clusters, points, w, h)

    return [cl.circle for cl in clusters]


def fmt_float(x: float) -> str:
    """
    Server regex accepts ordinary decimal floats. Avoid '+', uppercase E,
    NaN/inf, and bare '.5' forms.
    """
    if abs(x) < 0.0000000000005:
        x = 0.0
    return f"{x:.12f}"


def submission_lines(circles: List[Circle]) -> List[str]:
    lines = []
    for c in circles:
        lines.append(
            "CIRCLE "
            + fmt_float(c.cx)
            + " "
            + fmt_float(c.cy)
            + " "
            + fmt_float(c.r)
        )
    lines.append("END")
    return lines


def read_line(f) -> Optional[str]:
    line = f.readline()
    if line == "":
        return None
    if line.endswith("\n"):
        line = line[:-1]
    return line


def main() -> int:
    botname = os.environ.get("BOTNAME")
    if not botname:
        return 2

    try:
        sock = socket.create_connection((HOST, PORT))
    except OSError:
        return 3

    with sock:
        f = sock.makefile("r", encoding="ascii", newline="\n")

        # Registration must be first and must happen immediately.
        sock.sendall((botname + "\n").encode("ascii"))

        while True:
            line = read_line(f)
            if line is None:
                return 0

            if line == "TOURNAMENT_END":
                return 0

            if not line:
                continue

            parts = line.split(" ")
            if parts[0] != "ROUND":
                # Ignore result/end lines if any unexpected server chatter appears.
                continue

            if len(parts) != 5:
                return 4

            round_num = int(parts[1])
            w = int(parts[2])
            h = int(parts[3])
            n = int(parts[4])

            points: List[Tuple[int, int]] = []

            for _ in range(n):
                dot_line = read_line(f)
                if dot_line is None:
                    return 0

                dp = dot_line.split(" ")
                if len(dp) != 4 or dp[0] != "DOT":
                    return 5

                idx = int(dp[1])
                x = int(dp[2])
                y = int(dp[3])

                # Preserve index order if the server sends as specified.
                # If not, still collect all dots.
                points.append((x, y))

            circles = solve_round(w, h, points)
            out = "\n".join(submission_lines(circles)) + "\n"
            sock.sendall(out.encode("ascii"))

            # Must read both lines to avoid desync.
            result = read_line(f)
            if result is None:
                return 0

            end_round = read_line(f)
            if end_round is None:
                return 0

            # Continue regardless of OK/INVALID.
            _ = round_num

    return 0


if __name__ == "__main__":
    sys.exit(main())