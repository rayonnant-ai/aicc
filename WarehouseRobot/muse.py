# bot author: Meta Muse Spark
# bot author: Muse Spark
# WarehouseRobot tournament client – Python 3.10, stdlib only
import os
import sys
import socket
import math

HOST = 'localhost'
PORT = 7474
MAX_LOAD = 79 # keep speed >=3 m/min; heavier trips are slower than splitting

def trip_time(order, items):
    """total minutes for a given visit order"""
    load = 0
    px = py = 0
    total = 0.0
    for idx in order:
        x, y, w = items[idx]
        d = abs(x - px) + abs(y - py)
        if d:
            speed = 10 - (load // 10)
            if speed <= 0:
                return float('inf')
            total += d / speed
        px, py = x, y
        load += w
    d = px + py
    if d:
        speed = 10 - (load // 10)
        if speed <= 0:
            return float('inf')
        total += d / speed
    return total

def build_order(trip, items):
    """nearest-neighbour starting at farthest bin"""
    remaining = set(trip)
    start = max(remaining, key=lambda i: items[i][0] + items[i][1])
    order = [start]
    remaining.remove(start)
    cur = start
    while remaining:
        nxt = min(
            remaining,
            key=lambda i: (
                abs(items[i][0] - items[cur][0]) + abs(items[i][1] - items[cur][1]),
                -(items[i][0] + items[i][1])
            )
        )
        order.append(nxt)
        remaining.remove(nxt)
        cur = nxt
    return order

def plan_trips(items):
    n = len(items)
    entries = []
    for idx, (x, y, w) in enumerate(items):
        angle = math.atan2(y, x)
        dist = x + y
        entries.append((idx, angle, dist, w))
    entries.sort(key=lambda e: (e[1], -e[2]))

    trips = []
    cur = []
    cur_w = 0
    for idx, _, _, w in entries:
        if cur_w + w > MAX_LOAD and cur:
            trips.append(cur)
            cur = []
            cur_w = 0
        cur.append(idx)
        cur_w += w
    if cur:
        trips.append(cur)

    optimized = []
    for trip in trips:
        order = build_order(trip, items)
        if len(order) <= 10:
            best = order[:]
            best_t = trip_time(best, items)
            for _ in range(3):
                improved = False
                for i in range(len(best)):
                    for j in range(i + 1, len(best)):
                        best[i], best[j] = best[j], best[i]
                        t = trip_time(best, items)
                        if t < best_t - 1e-9:
                            best_t = t
                            improved = True
                        else:
                            best[i], best[j] = best[j], best[i]
                if not improved:
                    break
            order = best
        optimized.append(order)
    return optimized

def main():
    botname = os.environ.get('BOTNAME', '').strip()
    if not botname or not (1 <= len(botname) <= 32) or not all(c.isalnum() or c in '_-' for c in botname):
        sys.exit(1)

    sock = socket.create_connection((HOST, PORT))
    rf = sock.makefile('r', encoding='ascii', newline='\n')
    sock.sendall((botname + '\n').encode('ascii'))

    while True:
        line = rf.readline()
        if not line:
            break
        line = line.rstrip('\n')
        if line.startswith('ROUND'):
            _, _, wm, hm, N = line.split()
            N = int(N)
            items = []
            for _ in range(N):
                iline = rf.readline()
                parts = iline.split()
                x = int(parts[2]); y = int(parts[3]); w = int(parts[4])
                items.append((x, y, w))
            trips = plan_trips(items)
            for trip in trips:
                sock.sendall(('TRIP ' + ' '.join(str(i) for i in trip) + '\n').encode('ascii'))
            sock.sendall(b'END\n')
        elif line == 'TOURNAMENT_END':
            break
        else:
            # OK, INVALID, END_ROUND – just continue waiting
            continue

    try:
        rf.close()
        sock.close()
    except:
        pass

if __name__ == '__main__':
    main()