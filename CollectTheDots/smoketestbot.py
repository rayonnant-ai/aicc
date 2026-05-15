#!/usr/bin/env python3
"""
Dumb baseline bot for CollectTheDots.

Strategy: one circle per unique dot coordinate. For each unique coord, the
circle's radius is min(distance to rectangle edges, half-distance to nearest
other unique coord), minus a small safety margin. This guarantees:
- circle lies inside the rectangle,
- circles don't overlap (each radius ≤ half the distance to its nearest
  neighbour, so neighbour-pair radii sum ≤ that distance),
- every dot (including coincident dots) is covered (each unique coord has
  a circle centred on it).
"""
import math
import os
import socket
import sys

HOST = 'localhost'
PORT = 7474
EPSILON_MARGIN = 1e-4


def covering(dots, w, h):
    """Return a list of (cx, cy, r) circles covering every dot."""
    unique = sorted(set(dots))
    circles = []
    for (x, y) in unique:
        edge = min(x, w - x, y, h - y)
        if len(unique) > 1:
            nearest = min(
                math.hypot(x - ox, y - oy)
                for (ox, oy) in unique if (ox, oy) != (x, y)
            )
        else:
            nearest = float('inf')
        r = min(edge, nearest / 2.0) - EPSILON_MARGIN
        if r <= 0:
            r = EPSILON_MARGIN
        circles.append((float(x), float(y), r))
    return circles


def main():
    botname = os.environ.get('BOTNAME')
    if not botname:
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    sock.sendall((botname + '\n').encode('ascii'))

    f = sock.makefile('r', encoding='ascii', newline='\n')
    while True:
        line = f.readline()
        if not line:
            break
        line = line.rstrip('\n\r')
        if not line:
            continue
        if line.startswith('ROUND'):
            parts = line.split()
            w = int(parts[2])
            h = int(parts[3])
            n = int(parts[4])
            dots = []
            for _ in range(n):
                dot_line = f.readline().rstrip('\n\r')
                dp = dot_line.split()
                # DOT <idx> <x> <y>
                dots.append((int(dp[2]), int(dp[3])))
            circles = covering(dots, w, h)
            payload = ''.join(
                f"CIRCLE {cx} {cy} {r}\n" for (cx, cy, r) in circles
            ) + "END\n"
            sock.sendall(payload.encode('ascii'))
        elif line.startswith('OK') or line.startswith('INVALID'):
            continue
        elif line.startswith('END_ROUND'):
            continue
        elif line == 'TOURNAMENT_END':
            break

    try:
        sock.close()
    except OSError:
        pass


if __name__ == '__main__':
    main()
