# bot author: Kimi K2.6 (moonshotai/kimi-k2.6 via OpenRouter)
# bot author: WarehouseRobot-v1
import os
import socket
import math
import time

def speed(load):
    if load >= 100:
        return 0
    return 10 - (load // 10)

def trip_cost(order, weights, dist_origin, dist_matrix):
    if not order:
        return 0.0
    t = 0.0
    load = 0
    prev = -1
    for idx in order:
        d = dist_origin[idx] if prev == -1 else dist_matrix[prev][idx]
        if d > 0:
            s = speed(load)
            if s <= 0:
                return float('inf')
            t += d / s
        load += weights[idx]
        prev = idx
    d = dist_origin[prev]
    if d > 0:
        s = speed(load)
        if s <= 0:
            return float('inf')
        t += d / s
    return t

def solve_tsp_exact(trip_items, weights, dist_origin, dist_matrix):
    k = len(trip_items)
    if k == 0:
        return []
    if k == 1:
        return list(trip_items)
    loc = list(trip_items)
    w = [weights[i] for i in loc]
    d0 = [dist_origin[i] for i in loc]
    dm = [[dist_matrix[loc[i]][loc[j]] for j in range(k)] for i in range(k)]

    load = [0] * (1 << k)
    for mask in range(1, 1 << k):
        lsb = mask & -mask
        bit = (lsb.bit_length() - 1)
        load[mask] = load[mask ^ lsb] + w[bit]

    INF = float('inf')
    dp = [[INF] * k for _ in range(1 << k)]
    par = [[-1] * k for _ in range(1 << k)]

    for j in range(k):
        dp[1 << j][j] = d0[j] / 10.0

    for mask in range(1, 1 << k):
        s = speed(load[mask])
        if s <= 0:
            continue
        for last in range(k):
            if not (mask & (1 << last)):
                continue
            cur = dp[mask][last]
            if cur == INF:
                continue
            for nxt in range(k):
                if mask & (1 << nxt):
                    continue
                d = dm[last][nxt]
                nmask = mask | (1 << nxt)
                cost = cur + (d / s if d > 0 else 0)
                if cost < dp[nmask][nxt]:
                    dp[nmask][nxt] = cost
                    par[nmask][nxt] = last

    full = (1 << k) - 1
    s_ret = speed(load[full])
    best = INF
    best_last = -1
    for last in range(k):
        if dp[full][last] == INF:
            continue
        d = d0[last]
        cost = dp[full][last] + (d / s_ret if d > 0 else 0)
        if cost < best:
            best = cost
            best_last = last

    seq = []
    mask = full
    last = best_last
    while last != -1:
        seq.append(loc[last])
        p = par[mask][last]
        mask ^= (1 << last)
        last = p
    seq.reverse()
    return seq

def improve_trip(order, weights, dist_origin, dist_matrix):
    if len(order) <= 2:
        return order
    improved = True
    while improved:
        improved = False
        best = trip_cost(order, weights, dist_origin, dist_matrix)
        for i in range(len(order) - 1):
            new_order = order[:]
            new_order[i], new_order[i + 1] = new_order[i + 1], new_order[i]
            cost = trip_cost(new_order, weights, dist_origin, dist_matrix)
            if cost < best - 1e-9:
                order = new_order
                improved = True
                break
    return order

def optimize_trip_insertion(trip_items, weights, dist_origin, dist_matrix, angles):
    if len(trip_items) <= 1:
        return list(trip_items)
    candidates = []
    candidates.append(sorted(trip_items, key=lambda i: -dist_origin[i]))
    candidates.append(sorted(trip_items, key=lambda i: -weights[i]))
    candidates.append(sorted(trip_items, key=lambda i: -(dist_origin[i] * weights[i])))
    candidates.append(sorted(trip_items, key=lambda i: angles[i]))

    best_seq = None
    best_cost = float('inf')
    for cand in candidates:
        seq = []
        for idx in cand:
            best_pos = 0
            best_pos_cost = float('inf')
            for pos in range(len(seq) + 1):
                trial = seq[:pos] + [idx] + seq[pos:]
                cost = trip_cost(trial, weights, dist_origin, dist_matrix)
                if cost < best_pos_cost:
                    best_pos_cost = cost
                    best_pos = pos
            seq.insert(best_pos, idx)
        cost = trip_cost(seq, weights, dist_origin, dist_matrix)
        if cost < best_cost:
            best_cost = cost
            best_seq = seq
    return best_seq

def build_trips_from_order(order, weights):
    trips = []
    cur = []
    wsum = 0
    for idx in order:
        if wsum + weights[idx] < 100:
            cur.append(idx)
            wsum += weights[idx]
        else:
            trips.append(cur)
            cur = [idx]
            wsum = weights[idx]
    if cur:
        trips.append(cur)
    return trips

def solve(items, deadline):
    N = len(items)
    weights = [it[2] for it in items]
    dist_origin = [it[0] + it[1] for it in items]
    dist_matrix = [[abs(items[i][0] - items[j][0]) + abs(items[i][1] - items[j][1]) for j in range(N)] for i in range(N)]
    angles = [math.atan2(it[1], it[0]) for it in items]

    circular = sorted(range(N), key=lambda i: angles[i])
    best_trips = None
    best_cost = float('inf')

    offsets = [0]
    if N >= 4:
        offsets = [0, N // 4, N // 2, (3 * N) // 4]

    for off in offsets:
        if time.time() > deadline:
            break
        order = circular[off:] + circular[:off]
        trips = build_trips_from_order(order, weights)
        opt_trips = []
        total = 0.0
        for trip in trips:
            if len(trip) <= 12:
                opt = solve_tsp_exact(trip, weights, dist_origin, dist_matrix)
            else:
                opt = optimize_trip_insertion(trip, weights, dist_origin, dist_matrix, angles)
                opt = improve_trip(opt, weights, dist_origin, dist_matrix)
            opt_trips.append(opt)
            total += trip_cost(opt, weights, dist_origin, dist_matrix)
        if total < best_cost:
            best_cost = total
            best_trips = opt_trips

    opt_trips = best_trips

    improved = True
    while improved and time.time() < deadline:
        improved = False
        for i in range(len(opt_trips)):
            if improved:
                break
            if len(opt_trips[i]) <= 1:
                continue
            if i + 1 < len(opt_trips):
                item = opt_trips[i][-1]
                if sum(weights[x] for x in opt_trips[i + 1]) + weights[item] < 100:
                    new_i = opt_trips[i][:-1]
                    new_j = opt_trips[i + 1] + [item]
                    c_old = trip_cost(opt_trips[i], weights, dist_origin, dist_matrix) + trip_cost(opt_trips[i + 1], weights, dist_origin, dist_matrix)
                    opt_new_i = solve_tsp_exact(new_i, weights, dist_origin, dist_matrix) if len(new_i) <= 12 else optimize_trip_insertion(new_i, weights, dist_origin, dist_matrix, angles)
                    if len(new_i) > 12:
                        opt_new_i = improve_trip(opt_new_i, weights, dist_origin, dist_matrix)
                    opt_new_j = solve_tsp_exact(new_j, weights, dist_origin, dist_matrix) if len(new_j) <= 12 else optimize_trip_insertion(new_j, weights, dist_origin, dist_matrix, angles)
                    if len(new_j) > 12:
                        opt_new_j = improve_trip(opt_new_j, weights, dist_origin, dist_matrix)
                    c_new = trip_cost(opt_new_i, weights, dist_origin, dist_matrix) + trip_cost(opt_new_j, weights, dist_origin, dist_matrix)
                    if c_new < c_old - 1e-9:
                        opt_trips[i] = opt_new_i
                        opt_trips[i + 1] = opt_new_j
                        improved = True
                        break
            if i > 0 and not improved:
                item = opt_trips[i][0]
                if sum(weights[x] for x in opt_trips[i - 1]) + weights[item] < 100:
                    new_i = opt_trips[i][1:]
                    new_j = opt_trips[i - 1] + [item]
                    c_old = trip_cost(opt_trips[i], weights, dist_origin, dist_matrix) + trip_cost(opt_trips[i - 1], weights, dist_origin, dist_matrix)
                    opt_new_i = solve_tsp_exact(new_i, weights, dist_origin, dist_matrix) if len(new_i) <= 12 else optimize_trip_insertion(new_i, weights, dist_origin, dist_matrix, angles)
                    if len(new_i) > 12:
                        opt_new_i = improve_trip(opt_new_i, weights, dist_origin, dist_matrix)
                    opt_new_j = solve_tsp_exact(new_j, weights, dist_origin, dist_matrix) if len(new_j) <= 12 else optimize_trip_insertion(new_j, weights, dist_origin, dist_matrix, angles)
                    if len(new_j) > 12:
                        opt_new_j = improve_trip(opt_new_j, weights, dist_origin, dist_matrix)
                    c_new = trip_cost(opt_new_i, weights, dist_origin, dist_matrix) + trip_cost(opt_new_j, weights, dist_origin, dist_matrix)
                    if c_new < c_old - 1e-9:
                        opt_trips[i] = opt_new_i
                        opt_trips[i - 1] = opt_new_j
                        improved = True
                        break
            if i + 1 < len(opt_trips) and not improved and len(opt_trips[i]) >= 1 and len(opt_trips[i + 1]) >= 1:
                a = opt_trips[i][-1]
                b = opt_trips[i + 1][0]
                new_i = opt_trips[i][:-1] + [b]
                new_j = [a] + opt_trips[i + 1][1:]
                if sum(weights[x] for x in new_i) < 100 and sum(weights[x] for x in new_j) < 100:
                    c_old = trip_cost(opt_trips[i], weights, dist_origin, dist_matrix) + trip_cost(opt_trips[i + 1], weights, dist_origin, dist_matrix)
                    opt_new_i = solve_tsp_exact(new_i, weights, dist_origin, dist_matrix) if len(new_i) <= 12 else optimize_trip_insertion(new_i, weights, dist_origin, dist_matrix, angles)
                    if len(new_i) > 12:
                        opt_new_i = improve_trip(opt_new_i, weights, dist_origin, dist_matrix)
                    opt_new_j = solve_tsp_exact(new_j, weights, dist_origin, dist_matrix) if len(new_j) <= 12 else optimize_trip_insertion(new_j, weights, dist_origin, dist_matrix, angles)
                    if len(new_j) > 12:
                        opt_new_j = improve_trip(opt_new_j, weights, dist_origin, dist_matrix)
                    c_new = trip_cost(opt_new_i, weights, dist_origin, dist_matrix) + trip_cost(opt_new_j, weights, dist_origin, dist_matrix)
                    if c_new < c_old - 1e-9:
                        opt_trips[i] = opt_new_i
                        opt_trips[i + 1] = opt_new_j
                        improved = True
                        break

    return opt_trips

def main():
    botname = os.environ.get('BOTNAME', '').strip()
    if not botname:
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))

    def send(line):
        sock.sendall((line + '\n').encode('ascii'))

    send(botname)

    reader = sock.makefile('rb')

    while True:
        line = reader.readline()
        if not line:
            break
        line = line.decode('ascii').strip()
        if not line:
            continue
        if line.startswith('ROUND'):
            parts = line.split()
            N = int(parts[4])
            items = []
            for _ in range(N):
                iline = reader.readline().decode('ascii').strip()
                ip = iline.split()
                x = int(ip[2])
                y = int(ip[3])
                w = int(ip[4])
                items.append((x, y, w))
            deadline = time.time() + 25.0
            trips = solve(items, deadline)
            for trip in trips:
                send('TRIP ' + ' '.join(str(i) for i in trip))
            send('END')
        elif line.startswith('OK'):
            pass
        elif line.startswith('INVALID'):
            pass
        elif line.startswith('END_ROUND'):
            pass
        elif line.startswith('TOURNAMENT_END'):
            break

    try:
        sock.close()
    except Exception:
        pass

if __name__ == '__main__':
    main()
