# bot author: GLM 5.1 (z-ai/glm-5.1 via OpenRouter)
# bot author: Claude 3.5 Sonnet

import os
import sys
import socket
import math
import time
from itertools import permutations


def speed(load):
    if load >= 100:
        return 0
    return 10 - (load // 10)


def trip_time(items, item_data):
    if not items:
        return 0.0
    total = 0.0
    load = 0
    px, py = 0, 0
    for idx in items:
        x, y, w = item_data[idx]
        d = abs(x - px) + abs(y - py)
        if d > 0:
            s = speed(load)
            if s == 0:
                return float('inf')
            total += d / s
        load += w
        px, py = x, y
    d = abs(px) + abs(py)
    if d > 0:
        s = speed(load)
        if s == 0:
            return float('inf')
        total += d / s
    return total


def total_time(trips, item_data):
    return sum(trip_time(t, item_data) for t in trips)


def _brute_force(items, item_data):
    best_time = float('inf')
    best_order = list(items)
    for perm in permutations(items):
        t = trip_time(perm, item_data)
        if t < best_time:
            best_time = t
            best_order = list(perm)
    return best_order


def _nearest_neighbor(items, item_data):
    remaining = list(items)
    order = []
    px, py = 0, 0
    load = 0
    while remaining:
        best_item = None
        best_cost = float('inf')
        for item in remaining:
            x, y, w = item_data[item]
            d = abs(x - px) + abs(y - py)
            s = speed(load)
            if s == 0:
                continue
            cost = d / s
            if cost < best_cost:
                best_cost = cost
                best_item = item
        if best_item is None:
            best_item = remaining[0]
        remaining.remove(best_item)
        order.append(best_item)
        x, y, w = item_data[best_item]
        load += w
        px, py = x, y
    return order


def _two_opt(order, item_data):
    improved = True
    while improved:
        improved = False
        best_time = trip_time(order, item_data)
        n = len(order)
        for i in range(n - 1):
            for j in range(i + 1, n):
                new_order = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                new_time = trip_time(new_order, item_data)
                if new_time < best_time - 1e-12:
                    order = new_order
                    best_time = new_time
                    improved = True
                    break
            if improved:
                break
    return order


def _or_opt(order, item_data):
    improved = True
    while improved:
        improved = False
        best_time = trip_time(order, item_data)
        n = len(order)
        for seg_len in range(1, min(4, n + 1)):
            for i in range(n - seg_len + 1):
                segment = order[i:i + seg_len]
                rest = order[:i] + order[i + seg_len:]
                for j in range(len(rest) + 1):
                    new_order = rest[:j] + segment + rest[j:]
                    new_time = trip_time(new_order, item_data)
                    if new_time < best_time - 1e-12:
                        order = new_order
                        best_time = new_time
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
    return order


def optimize_trip(items, item_data, brute_limit=8):
    n = len(items)
    if n <= 1:
        return list(items)
    if n <= brute_limit:
        return _brute_force(items, item_data)
    candidates = []
    order = _nearest_neighbor(items, item_data)
    order = _two_opt(order, item_data)
    candidates.append((trip_time(order, item_data), order))
    order2 = sorted(items, key=lambda i: item_data[i][2])
    order2 = _two_opt(order2, item_data)
    candidates.append((trip_time(order2, item_data), order2))
    order3 = sorted(items, key=lambda i: item_data[i][0] + item_data[i][1])
    order3 = _two_opt(order3, item_data)
    candidates.append((trip_time(order3, item_data), order3))
    candidates.sort()
    best = candidates[0][1]
    best = _or_opt(best, item_data)
    return best


def form_trips_angle(item_data):
    N = len(item_data)
    if N == 0:
        return []
    items_with_angle = []
    for i in range(N):
        x, y, w = item_data[i]
        angle = math.atan2(y, x)
        items_with_angle.append((angle, i))
    items_with_angle.sort()
    sorted_items = [i for _, i in items_with_angle]
    trips = []
    current_trip = []
    current_weight = 0
    for item in sorted_items:
        w = item_data[item][2]
        if current_trip and current_weight + w >= 100:
            trips.append(current_trip)
            current_trip = [item]
            current_weight = w
        else:
            current_trip.append(item)
            current_weight += w
    if current_trip:
        trips.append(current_trip)
    return trips


def form_trips_nn(item_data):
    N = len(item_data)
    if N == 0:
        return []
    bin_items = {}
    for i in range(N):
        x, y, w = item_data[i]
        key = (x, y)
        if key not in bin_items:
            bin_items[key] = []
        bin_items[key].append(i)
    unassigned = set(range(N))
    trips = []
    while unassigned:
        best_start = min(unassigned, key=lambda i: item_data[i][0] + item_data[i][1])
        current_trip = [best_start]
        current_weight = item_data[best_start][2]
        unassigned.remove(best_start)
        bx, by, _ = item_data[best_start]
        for itm in bin_items.get((bx, by), []):
            if itm in unassigned and current_weight + item_data[itm][2] < 100:
                current_trip.append(itm)
                current_weight += item_data[itm][2]
                unassigned.remove(itm)
        px, py = bx, by
        while unassigned:
            best_next = None
            best_dist = float('inf')
            for itm in unassigned:
                x, y, w = item_data[itm]
                if current_weight + w >= 100:
                    continue
                d = abs(x - px) + abs(y - py)
                if d < best_dist:
                    best_dist = d
                    best_next = itm
            if best_next is None:
                break
            current_trip.append(best_next)
            current_weight += item_data[best_next][2]
            unassigned.remove(best_next)
            px, py = item_data[best_next][0], item_data[best_next][1]
            for itm in bin_items.get((px, py), []):
                if itm in unassigned and current_weight + item_data[itm][2] < 100:
                    current_trip.append(itm)
                    current_weight += item_data[itm][2]
                    unassigned.remove(itm)
        trips.append(current_trip)
    return trips


def form_trips_savings(item_data):
    N = len(item_data)
    if N == 0:
        return []
    savings_list = []
    for i in range(N):
        xi, yi, wi = item_data[i]
        di = xi + yi
        for j in range(i + 1, N):
            xj, yj, wj = item_data[j]
            if wi + wj >= 100:
                continue
            dj = xj + yj
            dij = abs(xi - xj) + abs(yi - yj)
            cost_sep = di / 10 + di / speed(wi) + dj / 10 + dj / speed(wj)
            cost_ij = di / 10 + dij / speed(wi) + dj / speed(wi + wj)
            cost_ji = dj / 10 + dij / speed(wj) + di / speed(wi + wj)
            cost_merged = min(cost_ij, cost_ji)
            saving = cost_sep - cost_merged
            if saving > 0:
                savings_list.append((-saving, i, j))
    savings_list.sort()
    parent = list(range(N))
    trip_weight = [item_data[i][2] for i in range(N)]
    trip_items = [[i] for i in range(N)]

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for neg_saving, i, j in savings_list:
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        if trip_weight[ri] + trip_weight[rj] >= 100:
            continue
        if len(trip_items[ri]) < len(trip_items[rj]):
            ri, rj = rj, ri
        parent[rj] = ri
        trip_weight[ri] += trip_weight[rj]
        trip_items[ri] = trip_items[ri] + trip_items[rj]
        trip_items[rj] = []
    seen = set()
    trips = []
    for i in range(N):
        r = find(i)
        if r not in seen:
            seen.add(r)
            if trip_items[r]:
                trips.append(trip_items[r])
    return trips


def form_trips_insertion(item_data):
    N = len(item_data)
    if N == 0:
        return []
    items_sorted = sorted(range(N), key=lambda i: item_data[i][0] + item_data[i][1], reverse=True)
    trips = []
    trip_weights = []
    for item in items_sorted:
        w = item_data[item][2]
        best_trip_idx = -1
        best_cost_inc = float('inf')
        best_pos = 0
        for t in range(len(trips)):
            if trip_weights[t] + w >= 100:
                continue
            old_time = trip_time(trips[t], item_data)
            for pos in range(len(trips[t]) + 1):
                nt = trips[t][:pos] + [item] + trips[t][pos:]
                nt_time = trip_time(nt, item_data)
                inc = nt_time - old_time
                if inc < best_cost_inc:
                    best_cost_inc = inc
                    best_trip_idx = t
                    best_pos = pos
        new_trip_time = trip_time([item], item_data)
        if best_trip_idx >= 0 and best_cost_inc < new_trip_time:
            trips[best_trip_idx] = trips[best_trip_idx][:best_pos] + [item] + trips[best_trip_idx][best_pos:]
            trip_weights[best_trip_idx] += w
        else:
            trips.append([item])
            trip_weights.append(w)
    return trips


def local_search(trips, item_data, time_limit):
    start = time.time()
    trip_w = [sum(item_data[idx][2] for idx in trip) for trip in trips]
    improved = True
    while improved:
        improved = False
        if time.time() - start > time_limit * 0.65:
            break
        n = len(trips)
        for i in range(n):
            if time.time() - start > time_limit * 0.65:
                break
            for ip in range(len(trips[i])):
                if time.time() - start > time_limit * 0.65:
                    break
                item = trips[i][ip]
                w = item_data[item][2]
                new_trip_i = trips[i][:ip] + trips[i][ip + 1:]
                old_time_i = trip_time(trips[i], item_data)
                new_time_i = trip_time(new_trip_i, item_data) if new_trip_i else 0.0
                best_j = -1
                best_pos = 0
                best_new_time_j = float('inf')
                best_old_time_j = 0.0
                for j in range(n):
                    if i == j:
                        continue
                    if trip_w[j] + w >= 100:
                        continue
                    old_time_j = trip_time(trips[j], item_data)
                    for pos in range(len(trips[j]) + 1):
                        nt = trips[j][:pos] + [item] + trips[j][pos:]
                        nt_time = trip_time(nt, item_data)
                        if nt_time < best_new_time_j:
                            best_new_time_j = nt_time
                            best_j = j
                            best_pos = pos
                            best_old_time_j = old_time_j
                if best_j >= 0:
                    if not new_trip_i:
                        if best_new_time_j < old_time_i + best_old_time_j - 1e-10:
                            trips[best_j] = trips[best_j][:best_pos] + [item] + trips[best_j][best_pos:]
                            trip_w[best_j] += w
                            trips.pop(i)
                            trip_w.pop(i)
                            improved = True
                            break
                    else:
                        if new_time_i + best_new_time_j < old_time_i + best_old_time_j - 1e-10:
                            trips[i] = new_trip_i
                            trip_w[i] -= w
                            trips[best_j] = trips[best_j][:best_pos] + [item] + trips[best_j][best_pos:]
                            trip_w[best_j] += w
                            improved = True
                            break
            if improved:
                break
    improved = True
    while improved:
        improved = False
        if time.time() - start > time_limit * 0.9:
            break
        n = len(trips)
        for i in range(n):
            if time.time() - start > time_limit * 0.9:
                break
            for ip in range(len(trips[i])):
                if time.time() - start > time_limit * 0.9:
                    break
                item_i = trips[i][ip]
                w_i = item_data[item_i][2]
                for j in range(i + 1, n):
                    if time.time() - start > time_limit * 0.9:
                        break
                    for jp in range(len(trips[j])):
                        item_j = trips[j][jp]
                        w_j = item_data[item_j][2]
                        new_wi = trip_w[i] - w_i + w_j
                        new_wj = trip_w[j] - w_j + w_i
                        if new_wi >= 100 or new_wj >= 100:
                            continue
                        old_time = trip_time(trips[i], item_data) + trip_time(trips[j], item_data)
                        new_trip_i = trips[i][:ip] + [item_j] + trips[i][ip + 1:]
                        new_trip_j = trips[j][:jp] + [item_i] + trips[j][jp + 1:]
                        new_time = trip_time(new_trip_i, item_data) + trip_time(new_trip_j, item_data)
                        if new_time < old_time - 1e-10:
                            trips[i] = new_trip_i
                            trip_w[i] = new_wi
                            trips[j] = new_trip_j
                            trip_w[j] = new_wj
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
    return trips


def solve(item_data, wm, hm):
    N = len(item_data)
    if N == 0:
        return []
    start_time = time.time()
    time_budget = 25.0
    brute_limit = 8 if N > 100 else 9
    candidates = []
    trips1 = form_trips_angle(item_data)
    trips1 = [optimize_trip(t, item_data, brute_limit) for t in trips1]
    candidates.append((total_time(trips1, item_data), trips1))
    trips2 = form_trips_nn(item_data)
    trips2 = [optimize_trip(t, item_data, brute_limit) for t in trips2]
    candidates.append((total_time(trips2, item_data), trips2))
    elapsed = time.time() - start_time
    if elapsed < time_budget * 0.25 and N <= 200:
        trips3 = form_trips_savings(item_data)
        trips3 = [optimize_trip(t, item_data, brute_limit) for t in trips3]
        candidates.append((total_time(trips3, item_data), trips3))
    elapsed = time.time() - start_time
    if elapsed < time_budget * 0.35 and N <= 100:
        trips4 = form_trips_insertion(item_data)
        trips4 = [optimize_trip(t, item_data, brute_limit) for t in trips4]
        candidates.append((total_time(trips4, item_data), trips4))
    candidates.sort()
    best_trips = [list(t) for t in candidates[0][1]]
    elapsed = time.time() - start_time
    remaining = time_budget - elapsed
    if remaining > 2:
        best_trips = local_search(best_trips, item_data, remaining * 0.7)
    best_trips = [optimize_trip(t, item_data, brute_limit) for t in best_trips]
    return best_trips


def main():
    botname = os.environ.get('BOTNAME', '')
    if not botname:
        sys.exit(1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode())
    buf = b''

    def read_line():
        nonlocal buf
        while b'\n' not in buf:
            data = sock.recv(4096)
            if not data:
                return None
            buf += data
        idx = buf.index(b'\n')
        line = buf[:idx].decode()
        buf = buf[idx + 1:]
        return line

    while True:
        line = read_line()
        if line is None:
            break
        if line == 'TOURNAMENT_END':
            break
        if line.startswith('ROUND'):
            parts = line.split()
            round_num = int(parts[1])
            wm = int(parts[2])
            hm = int(parts[3])
            N = int(parts[4])
            item_data = []
            for _ in range(N):
                item_line = read_line()
                if item_line is None:
                    break
                item_parts = item_line.split()
                x = int(item_parts[2])
                y = int(item_parts[3])
                w = int(item_parts[4])
                item_data.append((x, y, w))
            trips = solve(item_data, wm, hm)
            for trip in trips:
                trip_str = ' '.join(str(idx) for idx in trip)
                sock.sendall(('TRIP ' + trip_str + '\n').encode())
            sock.sendall(b'END\n')
            response = read_line()
            if response is None:
                break
            end_round = read_line()
            if end_round is None:
                break
    sock.close()


if __name__ == '__main__':
    main()
