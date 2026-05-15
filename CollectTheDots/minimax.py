# bot author: MiniMax M2.7 (minimax/minimax-m2.7 via OpenRouter)
# bot author: <model name and version>

import sys
import socket
import os
import math

EPS = 1e-6

def solve(w, h, points):
    """
    Greedy covering: at each step pick the best uncovered point as center
    (maximising coverage while respecting rectangle and non‑overlap constraints)
    and place a circle as large as possible there.
    """
    n = len(points)
    covered = [False] * n
    placed = []  # list of (cx, cy, r)

    # Helper to compute squared distance
    def sq_dist(x1, y1, x2, y2):
        dx = x1 - x2
        dy = y1 - y2
        return dx * dx + dy * dy

    while True:
        # Find list of uncovered indices
        uncovered = [i for i in range(n) if not covered[i]]
        if not uncovered:
            break

        best_cx = best_cy = None
        best_r = -1.0
        best_cnt = -1

        # Try each uncovered point as a candidate centre
        for i in uncovered:
            cx, cy = points[i]

            # Maximum radius limited by rectangle edges (with tolerance)
            r_edge = min(cx, w - cx, cy, h - cy) + EPS

            # Further limit by existing circles to avoid overlap
            r_max = r_edge
            for (pcx, pcy, pr) in placed:
                dx = cx - pcx
                dy = cy - pcy
                dist = math.hypot(dx, dy)
                allowed = dist - pr - EPS
                if allowed < r_max:
                    r_max = allowed

            if r_max < EPS:
                continue

            # Count how many uncovered points would be covered by this radius
            threshold = r_max + EPS
            threshold_sq = threshold * threshold
            cnt = 0
            for j in uncovered:
                if sq_dist(cx, cy, points[j][0], points[j][1]) <= threshold_sq:
                    cnt += 1

            # Choose the candidate covering the most points; break ties by larger radius
            if cnt > best_cnt or (cnt == best_cnt and r_max > best_r):
                best_cx, best_cy = cx, cy
                best_r = r_max
                best_cnt = cnt

        # If no candidate gave a positive radius (should not happen), fall back to a tiny circle
        if best_cx is None:
            i = uncovered[0]
            cx, cy = points[i]
            r_edge = min(cx, w - cx, cy, h - cy) + EPS
            r_max = r_edge
            for (pcx, pcy, pr) in placed:
                dx = cx - pcx
                dy = cy - pcy
                dist = math.hypot(dx, dy)
                allowed = dist - pr - EPS
                if allowed < r_max:
                    r_max = allowed
            if r_max < EPS:
                r_max = EPS
            best_cx, best_cy, best_r = cx, cy, r_max

        # Place the chosen circle
        placed.append((best_cx, best_cy, best_r))

        # Mark all points (including the centre) that fall inside the new circle
        threshold = best_r + EPS
        threshold_sq = threshold * threshold
        for i in range(n):
            if not covered[i] and sq_dist(best_cx, best_cy, points[i][0], points[i][1]) <= threshold_sq:
                covered[i] = True

    return placed

def main():
    bot_name = os.environ.get('BOTNAME')
    if not bot_name:
        sys.stderr.write("BOTNAME environment variable not set\n")
        sys.exit(1)

    # Connect to tournament server
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', 7474))
    except Exception as e:
        sys.stderr.write(f"Failed to connect: {e}\n")
        sys.exit(1)

    # Send bot name
    sock.sendall((bot_name + "\n").encode())

    # Helper to receive a line (strip trailing newline)
    def recv_line():
        data = b''
        while True:
            ch = sock.recv(1)
            if not ch:
                raise EOFError("Connection closed")
            if ch == b'\n':
                break
            data += ch
        return data.decode()

    # Helper to send a line
    def send_line(line):
        sock.sendall((line + "\n").encode())

    # Main tournament loop
    while True:
        line = recv_line()
        if line.startswith("ROUND"):
            parts = line.split()
            round_num = int(parts[1])
            w = int(parts[2])
            h = int(parts[3])
            n = int(parts[4])
            points = []
            for _ in range(n):
                dot_line = recv_line()
                _, idx, x, y = dot_line.split()
                points.append((int(x), int(y)))
            # Compute covering
            circles = solve(w, h, points)
            # Send submission
            for (cx, cy, r) in circles:
                send_line(f"CIRCLE {cx:.10f} {cy:.10f} {r:.10f}")
            send_line("END")
            # Read result
            result_line = recv_line()  # either OK or INVALID
            end_round_line = recv_line()  # END_ROUND ...
            # Continue to next round
        elif line == "TOURNAMENT_END":
            break
        else:
            # Ignore any other messages (should not happen)
            pass

    sock.close()

if __name__ == "__main__":
    main()
