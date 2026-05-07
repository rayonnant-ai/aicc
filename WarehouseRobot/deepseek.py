# bot author: DeepSeek V4-Pro (deepseek/deepseek-v4-pro via OpenRouter)
# bot author: WarehouseBot-v1
import os
import sys
import socket
import time
import random
import math

def trip_time(seq, dist, weights, depot):
    if not seq:
        return 0.0
    load = 0
    t = 0.0
    prev = depot
    for idx in seq:
        d = dist[prev][idx]
        if d > 0:
            speed = 10 - (load // 10)
            if speed <= 0:
                return float('inf')
            t += d / speed
        load += weights[idx]
        prev = idx
    d = dist[prev][depot]
    if d > 0:
        speed = 10 - (load // 10)
        if speed <= 0:
            return float('inf')
        t += d / speed
    return t

def two_opt(seq, trip_time_func):
    best_time = trip_time_func(seq)
    improved = True
    while improved:
        improved = False
        for i in range(len(seq)-1):
            for j in range(i+2, len(seq)):
                new_seq = seq[:i+1] + seq[i+1:j+1][::-1] + seq[j+1:]
                new_time = trip_time_func(new_seq)
                if new_time < best_time - 1e-9:
                    seq = new_seq
                    best_time = new_time
                    improved = True
                    break
            if improved:
                break
    return seq

def improve_solution(trips, dist, weights, depot):
    def tt(seq):
        return trip_time(seq, dist, weights, depot)
    for t in range(len(trips)):
        trips[t] = two_opt(trips[t], tt)
    improved = True
    while improved:
        improved = False
        trip_weights = [sum(weights[i] for i in trip) for trip in trips]
        for t_from in range(len(trips)):
            trip_from = trips[t_from]
            for pos_from in range(len(trip_from)):
                item = trip_from[pos_from]
                w = weights[item]
                new_trip_from = trip_from[:pos_from] + trip_from[pos_from+1:]
                time_from_without = tt(new_trip_from) if new_trip_from else 0.0
                time_from_with = tt(trip_from)
                for t_to in range(len(trips)):
                    if t_to == t_from:
                        continue
                    if trip_weights[t_to] + w > 99:
                        continue
                    trip_to = trips[t_to]
                    best_pos = None
                    best_new_time_to = float('inf')
                    for pos_to in range(len(trip_to)+1):
                        new_trip_to = trip_to[:pos_to] + [item] + trip_to[pos_to:]
                        new_time_to = tt(new_trip_to)
                        if new_time_to < best_new_time_to:
                            best_new_time_to = new_time_to
                            best_pos = pos_to
                    delta = (time_from_without - time_from_with) + (best_new_time_to - tt(trip_to))
                    if delta < -1e-9:
                        new_trip_to = trip_to[:best_pos] + [item] + trip_to[best_pos:]
                        trips[t_to] = new_trip_to
                        if new_trip_from:
                            trips[t_from] = new_trip_from
                        else:
                            del trips[t_from]
                        improved = True
                        break
                if improved:
                    break
                new_trip_new = [item]
                time_new = tt(new_trip_new)
                delta = (time_from_without - time_from_with) + time_new
                if delta < -1e-9:
                    if new_trip_from:
                        trips[t_from] = new_trip_from
                    else:
                        del trips[t_from]
                    trips.append(new_trip_new)
                    improved = True
                    break
            if improved:
                break
    return trips

def solve_round(items, wm, hm, time_limit):
    N = len(items)
    weights = [w for (x,y,w) in items]
    coords = [(x,y) for (x,y,w) in items]
    depot = N
    dist = [[0]*(N+1) for _ in range(N+1)]
    for i in range(N):
        xi, yi = coords[i]
        d = abs(xi) + abs(yi)
        dist[i][depot] = d
        dist[depot][i] = d
        for j in range(i+1, N):
            xj, yj = coords[j]
            d = abs(xi-xj) + abs(yi-yj)
            dist[i][j] = d
            dist[j][i] = d
    dist[depot][depot] = 0

    def tt(seq):
        return trip_time(seq, dist, weights, depot)

    best_trips = None
    best_total_time = float('inf')
    start_time = time.perf_counter()

    orders = [
        sorted(range(N), key=lambda i: weights[i], reverse=True),
        sorted(range(N), key=lambda i: weights[i]),
        sorted(range(N), key=lambda i: abs(coords[i][0])+abs(coords[i][1]), reverse=True),
        sorted(range(N), key=lambda i: abs(coords[i][0])+abs(coords[i][1])),
    ]
    for order in orders:
        if time.perf_counter() - start_time >= time_limit:
            break
        trips = []
        trip_weights = []
        for idx in order:
            w = weights[idx]
            best_insertion = None
            best_time_increase = float('inf')
            for t_idx, trip in enumerate(trips):
                if trip_weights[t_idx] + w > 99:
                    continue
                for pos in range(len(trip)+1):
                    new_trip = trip[:pos] + [idx] + trip[pos:]
                    new_time = tt(new_trip)
                    old_time = tt(trip) if trip else 0.0
                    increase = new_time - old_time
                    if increase < best_time_increase:
                        best_time_increase = increase
                        best_insertion = (t_idx, pos, new_trip, new_time)
            new_trip = [idx]
            new_time = tt(new_trip)
            increase = new_time
            if increase < best_time_increase:
                best_time_increase = increase
                best_insertion = (-1, None, new_trip, new_time)
            if best_insertion[0] == -1:
                trips.append(best_insertion[2])
                trip_weights.append(w)
            else:
                t_idx, pos, new_trip, new_time = best_insertion
                trips[t_idx] = new_trip
                trip_weights[t_idx] += w
        trips = improve_solution(trips, dist, weights, depot)
        total_time = sum(tt(trip) for trip in trips)
        if total_time < best_total_time:
            best_total_time = total_time
            best_trips = [trip[:] for trip in trips]

    while time.perf_counter() - start_time < time_limit:
        order = list(range(N))
        random.shuffle(order)
        trips = []
        trip_weights = []
        for idx in order:
            w = weights[idx]
            best_insertion = None
            best_time_increase = float('inf')
            for t_idx, trip in enumerate(trips):
                if trip_weights[t_idx] + w > 99:
                    continue
                for pos in range(len(trip)+1):
                    new_trip = trip[:pos] + [idx] + trip[pos:]
                    new_time = tt(new_trip)
                    old_time = tt(trip) if trip else 0.0
                    increase = new_time - old_time
                    if increase < best_time_increase:
                        best_time_increase = increase
                        best_insertion = (t_idx, pos, new_trip, new_time)
            new_trip = [idx]
            new_time = tt(new_trip)
            increase = new_time
            if increase < best_time_increase:
                best_time_increase = increase
                best_insertion = (-1, None, new_trip, new_time)
            if best_insertion[0] == -1:
                trips.append(best_insertion[2])
                trip_weights.append(w)
            else:
                t_idx, pos, new_trip, new_time = best_insertion
                trips[t_idx] = new_trip
                trip_weights[t_idx] += w
        trips = improve_solution(trips, dist, weights, depot)
        total_time = sum(tt(trip) for trip in trips)
        if total_time < best_total_time:
            best_total_time = total_time
            best_trips = [trip[:] for trip in trips]

    return best_trips

def main():
    botname = os.environ.get('BOTNAME', '').strip()
    if not botname:
        print("BOTNAME not set", file=sys.stderr)
        sys.exit(1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock_file = sock.makefile('rw', buffering=1)
    sock_file.write(botname + '\n')
    sock_file.flush()
    while True:
        line = sock_file.readline()
        if not line:
            break
        line = line.strip()
        if line.startswith('ROUND'):
            parts = line.split()
            round_num = int(parts[1])
            wm = int(parts[2])
            hm = int(parts[3])
            N = int(parts[4])
            items = []
            for _ in range(N):
                item_line = sock_file.readline().strip()
                iparts = item_line.split()
                x = int(iparts[2])
                y = int(iparts[3])
                w = int(iparts[4])
                items.append((x, y, w))
            start = time.perf_counter()
            time_limit = 28.0
            trips = solve_round(items, wm, hm, time_limit)
            for trip in trips:
                trip_str = 'TRIP ' + ' '.join(str(i) for i in trip)
                sock_file.write(trip_str + '\n')
            sock_file.write('END\n')
            sock_file.flush()
            resp = sock_file.readline().strip()
            end_round = sock_file.readline().strip()
        elif line.startswith('TOURNAMENT_END'):
            break
    sock.close()

if __name__ == '__main__':
    main()
