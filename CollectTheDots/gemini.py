# bot author: Gemini Pro 3.1
#!/usr/bin/env python3
# bot author: Gemini 3.1 Pro

import os
import sys
import socket
import time
import math
import random

# -------------------------------------------------------------------------
# Geometry and Optimization Helpers
# -------------------------------------------------------------------------

TOL = 5e-7  # Our internal safe tolerance (stricter than server's 1e-6)

def check_bounds(cx, cy, r, w, h):
    """Check if circle is safely inside the bounding box."""
    return (cx - r >= -TOL and cx + r <= w + TOL and
            cy - r >= -TOL and cy + r <= h + TOL)

def overlap(c1, c2):
    """Check if two circles overlap. We use a safety margin to guarantee no server-side overlap."""
    d = math.hypot(c1[0] - c2[0], c1[1] - c2[1])
    return d < c1[2] + c2[2] + 1e-7

def calc_circle(R):
    """Compute the exact enclosing circle for 0 to 3 boundary points."""
    if len(R) == 0:
        return (0.0, 0.0, 0.0)
    if len(R) == 1:
        return (float(R[0][0]), float(R[0][1]), 0.0)
    if len(R) == 2:
        cx = (R[0][0] + R[1][0]) / 2.0
        cy = (R[0][1] + R[1][1]) / 2.0
        r = math.hypot(R[0][0] - R[1][0], R[0][1] - R[1][1]) / 2.0
        return (cx, cy, r)
    
    # 3 points
    p1, p2, p3 = R
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    D = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    
    if abs(D) < 1e-9:
        # Points are collinear, fallback to bounding circle of the two furthest points
        d12 = math.hypot(ax - bx, ay - by)
        d13 = math.hypot(ax - cx, ay - cy)
        d23 = math.hypot(bx - cx, by - cy)
        if d12 >= d13 and d12 >= d23: return ((ax + bx) / 2.0, (ay + by) / 2.0, d12 / 2.0)
        if d13 >= d12 and d13 >= d23: return ((ax + cx) / 2.0, (ay + cy) / 2.0, d13 / 2.0)
        return ((bx + cx) / 2.0, (by + cy) / 2.0, d23 / 2.0)

    ux = ((ax*ax + ay*ay)*(by - cy) + (bx*bx + by*by)*(cy - ay) + (cx*cx + cy*cy)*(ay - by)) / D
    uy = ((ax*ax + ay*ay)*(cx - bx) + (bx*bx + by*by)*(ax - cx) + (cx*cx + cy*cy)*(bx - ax)) / D
    r = math.hypot(ax - ux, ay - uy)
    return (ux, uy, r)

def b_minidisk(P, R):
    """Recursive helper for Welzl's algorithm."""
    if not P or len(R) == 3:
        return calc_circle(R)
    
    p = P.pop()
    c = b_minidisk(P, R)
    
    if c is not None and math.hypot(p[0] - c[0], p[1] - c[1]) <= c[2] + 1e-7:
        P.append(p)
        return c
    
    c = b_minidisk(P, R + [p])
    P.append(p)
    return c

def welzl_mec(S):
    """Welzl's algorithm for Minimum Enclosing Circle in O(N)."""
    P_copy = S[:]
    random.shuffle(P_copy)
    return b_minidisk(P_copy, [])

def optimize_center(S, w, h):
    """
    Find a valid enclosing circle for a set of points S that respects the bounds.
    Returns (cx, cy, r) or None if no suitable circle is found.
    """
    if not S:
        return None
    if len(S) == 1:
        # A single dot is always fully covered by a tiny circle
        return (float(S[0][0]), float(S[0][1]), 5e-7)

    # 1. Try Welzl's exact minimum enclosing circle
    cx, cy, r = welzl_mec(S)
    r += 1e-7  # Add safety padding for coverage
    if check_bounds(cx, cy, r, w, h):
        return (cx, cy, r)

    # 2. If Welzl's MEC goes out of bounds, use a mini-hill climber
    # to find a valid shifted center, heavily penalizing boundary violations.
    best_cx, best_cy = cx, cy
    
    def cost(x, y):
        cr = max(math.hypot(p[0]-x, p[1]-y) for p in S)
        v1 = max(0.0, -(x - cr))
        v2 = max(0.0, (x + cr) - w)
        v3 = max(0.0, -(y - cr))
        v4 = max(0.0, (y + cr) - h)
        viol = v1 + v2 + v3 + v4
        return cr + 10000.0 * viol

    best_cost = cost(best_cx, best_cy)
    step = max(w, h) / 4.0

    while step > 1e-6:
        improved = False
        for dx, dy in [(0,1), (0,-1), (1,0), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]:
            nx = best_cx + dx * step
            ny = best_cy + dy * step
            nx = max(0.0, min(float(w), nx))
            ny = max(0.0, min(float(h), ny))
            c = cost(nx, ny)
            if c < best_cost:
                best_cost = c
                best_cx, best_cy = nx, ny
                improved = True
        if not improved:
            step /= 2.0

    final_r = max(math.hypot(p[0]-best_cx, p[1]-best_cy) for p in S) + 1e-7
    if check_bounds(best_cx, best_cy, final_r, w, h):
        return (best_cx, best_cy, final_r)

    return None

# -------------------------------------------------------------------------
# Core Solver
# -------------------------------------------------------------------------

def solve_round(w, h, dots_list, time_limit=28.5):
    """
    Heuristically groups dots into valid, non-overlapping circles.
    Utilizes a randomized multi-start greedy agglomerative clustering.
    Runs until slightly before the timeout.
    """
    start_t = time.time()
    
    # Remove coincident duplicate dots (they are implicitly covered together)
    unique_dots = list(set(dots_list))
    if not unique_dots:
        return []

    best_circles = None
    iteration = 0

    while time.time() - start_t < time_limit:
        iteration += 1
        
        # Start with each distinct dot in its own cluster
        clusters = [ [p] for p in unique_dots ]
        circles = { i: optimize_center(clusters[i], w, h) for i in range(len(clusters)) }

        changed = True
        while changed and (time.time() - start_t < time_limit):
            changed = False
            
            # Evaluate pairs for potential merges
            pairs = []
            active_ids = list(circles.keys())
            for idx1 in range(len(active_ids)):
                i = active_ids[idx1]
                for idx2 in range(idx1 + 1, len(active_ids)):
                    j = active_ids[idx2]
                    
                    c1, c2 = circles[i], circles[j]
                    dist = math.hypot(c1[0] - c2[0], c1[1] - c2[1])
                    boundary_dist = dist - c1[2] - c2[2]
                    
                    # Alternate between pure greedy and noise-injected runs
                    if iteration % 2 == 0:
                        noise = random.uniform(0, 2.0)
                        pairs.append((boundary_dist + noise, i, j))
                    else:
                        pairs.append((boundary_dist, i, j))

            pairs.sort(key=lambda x: x[0])

            # Attempt merges
            for _, i, j in pairs:
                if i not in circles or j not in circles:
                    continue

                S_new = clusters[i] + clusters[j]
                C_new = optimize_center(S_new, w, h)
                
                if C_new is not None:
                    # Check for overlaps with all other existing clusters
                    has_overlap = False
                    for k, ck in circles.items():
                        if k == i or k == j:
                            continue
                        if overlap(C_new, ck):
                            has_overlap = True
                            break
                            
                    if not has_overlap:
                        # Approve the merge
                        clusters[i] = S_new
                        circles[i] = C_new
                        del clusters[j]
                        del circles[j]
                        changed = True
                        break # Break loop to recalculate distances among new clusters

        current_solution = list(circles.values())
        if best_circles is None or len(current_solution) < len(best_circles):
            best_circles = current_solution
            if len(best_circles) == 1:
                break # Can't do better than 1 circle

    return best_circles

# -------------------------------------------------------------------------
# Network/Protocol Protocol
# -------------------------------------------------------------------------

def read_line(sock, buffer):
    """Buffered read to get exactly one \n terminated line."""
    while b'\n' not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            return None, buffer
        buffer += chunk
    line_bytes, buffer = buffer.split(b'\n', 1)
    return line_bytes.decode('ascii'), buffer

def main():
    bot_name = os.environ.get('BOTNAME')
    if not bot_name:
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(('127.0.0.1', 7474))
    except Exception as e:
        sys.exit(1)

    # 1. Send BOTNAME handshake
    sock.sendall(f"{bot_name}\n".encode('ascii'))

    buffer = b""

    # 2. Main protocol loop
    while True:
        line, buffer = read_line(sock, buffer)
        if line is None:
            break
            
        if line == "TOURNAMENT_END":
            break

        if line.startswith("ROUND"):
            parts = line.split()
            round_num = int(parts[1])
            w = int(parts[2])
            h = int(parts[3])
            N = int(parts[4])

            dots = []
            for _ in range(N):
                dot_line, buffer = read_line(sock, buffer)
                d_parts = dot_line.split()
                # d_parts format: DOT <idx> <x> <y>
                dots.append((int(d_parts[2]), int(d_parts[3])))

            # Solve the round (Time budget starts precisely here)
            circles = solve_round(w, h, dots, time_limit=28.5)

            # Transmit Submission
            submission = []
            for cx, cy, r in circles:
                submission.append(f"CIRCLE {cx} {cy} {r}\n")
            submission.append("END\n")
            
            sock.sendall("".join(submission).encode('ascii'))

            # Wait for Result Result
            ok_invalid_line, buffer = read_line(sock, buffer)
            end_round_line, buffer = read_line(sock, buffer)
            
            if not end_round_line.startswith("END_ROUND"):
                # Protocol desync safeguard
                pass

    sock.close()
    sys.exit(0)

if __name__ == "__main__":
    main()