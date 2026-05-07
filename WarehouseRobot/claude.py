# bot author: Claude Opus 4.7
#!/usr/bin/env python3
# bot author: Claude Opus 4.7
"""WarehouseRobot tournament bot.

Strategy:
  - Initial trips: Clarke-Wright savings algorithm (capacity = 99 kg).
  - Intra-trip ordering: Held-Karp DP (optimal) for k <= 11; NN + 2-opt + or-opt
    for larger trips.
  - Inter-trip local search: relocate, swap, extract-to-new-trip, merge.
  - Hard fallback: one trip per item (always valid since item weight <= 25).
"""

import os
import sys
import socket
import time

CAPACITY = 99  # max trip total weight (must be strictly < 100)


# ---------- core simulation primitives ----------

def speed_at(load):
    if load >= 100:
        return 0
    return 10 - (load // 10)


def trip_time(trip, items):
    """Total elapsed minutes for a trip visited in given order (returns to origin)."""
    if not trip:
        return 0.0
    cx = cy = 0
    load = 0
    total = 0.0
    for idx in trip:
        x, y, w = items[idx]
        d = abs(x - cx) + abs(y - cy)
        if d > 0:
            s = speed_at(load)
            if s <= 0:
                return float('inf')
            total += d / s
        cx, cy = x, y
        load += w
    d = abs(cx) + abs(cy)
    if d > 0:
        s = speed_at(load)
        if s <= 0:
            return float('inf')
        total += d / s
    return total


# ---------- intra-trip ordering ----------

def held_karp_order(trip, items):
    """Optimal visit order via Held-Karp DP. Best for small k (<= ~12)."""
    k = len(trip)
    if k <= 1:
        return list(trip)

    pos_x = [items[i][0] for i in trip]
    pos_y = [items[i][1] for i in trip]
    weights = [items[i][2] for i in trip]
    total_w = sum(weights)

    dist_origin = [pos_x[i] + pos_y[i] for i in range(k)]  # x,y >= 0 per spec
    dist_pair = [
        [abs(pos_x[i] - pos_x[j]) + abs(pos_y[i] - pos_y[j]) for j in range(k)]
        for i in range(k)
    ]

    INF = float('inf')
    full = 1 << k

    # mask_load[mask] = total weight of items in mask
    mask_load = [0] * full
    for mask in range(1, full):
        low_bit = mask & -mask
        low_idx = low_bit.bit_length() - 1
        mask_load[mask] = mask_load[mask ^ low_bit] + weights[low_idx]

    dp = [[INF] * k for _ in range(full)]
    parent = [[-1] * k for _ in range(full)]

    for j in range(k):
        # Visit j first; load was 0 before pickup.
        dp[1 << j][j] = dist_origin[j] / 10.0

    for mask in range(1, full):
        cur_load = mask_load[mask]
        if cur_load >= 100:
            inv_speed = None
        else:
            cur_speed = 10 - (cur_load // 10)
            inv_speed = 1.0 / cur_speed if cur_speed > 0 else None
        dp_mask = dp[mask]
        for last in range(k):
            if not (mask & (1 << last)):
                continue
            base = dp_mask[last]
            if base >= INF:
                continue
            dist_last = dist_pair[last]
            for nxt in range(k):
                if mask & (1 << nxt):
                    continue
                d = dist_last[nxt]
                if d == 0:
                    new_t = base
                elif inv_speed is None:
                    continue
                else:
                    new_t = base + d * inv_speed
                new_mask = mask | (1 << nxt)
                if new_t < dp[new_mask][nxt]:
                    dp[new_mask][nxt] = new_t
                    parent[new_mask][nxt] = last

    full_mask = full - 1
    if total_w >= 100:
        final_speed = 0
    else:
        final_speed = 10 - (total_w // 10)

    best_t = INF
    best_last = -1
    for last in range(k):
        base = dp[full_mask][last]
        if base >= INF:
            continue
        d = dist_origin[last]
        if d == 0:
            t = base
        elif final_speed <= 0:
            continue
        else:
            t = base + d / final_speed
        if t < best_t:
            best_t = t
            best_last = last

    if best_last == -1:
        return list(trip)

    order = []
    mask = full_mask
    cur = best_last
    while cur != -1:
        order.append(trip[cur])
        prev = parent[mask][cur]
        mask ^= (1 << cur)
        cur = prev
    order.reverse()
    return order


def iterative_optimize(trip, items):
    """2-opt + or-opt heuristic. Used for large trips and inside local search."""
    if len(trip) <= 1:
        return list(trip)

    # Bootstrap: nearest-neighbor from origin if input order is arbitrary.
    if len(trip) > 3:
        remaining = list(trip)
        cx = cy = 0
        nn = []
        while remaining:
            best_i = 0
            best_d = float('inf')
            for i, idx in enumerate(remaining):
                x, y, _ = items[idx]
                d = abs(x - cx) + abs(y - cy)
                if d < best_d:
                    best_d = d
                    best_i = i
            chosen = remaining.pop(best_i)
            nn.append(chosen)
            cx, cy, _ = items[chosen]
        order = nn
    else:
        order = list(trip)

    n = len(order)
    cur_t = trip_time(order, items)

    # 2-opt
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                new_order = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                new_t = trip_time(new_order, items)
                if new_t < cur_t - 1e-9:
                    order = new_order
                    cur_t = new_t
                    improved = True
                    break
            if improved:
                break

    # or-opt: move single item to a different position
    improved = True
    while improved:
        improved = False
        for i in range(n):
            seg = order[i]
            rest = order[:i] + order[i + 1:]
            for j in range(n):
                if j == i:
                    continue
                cand = rest[:j] + [seg] + rest[j:]
                new_t = trip_time(cand, items)
                if new_t < cur_t - 1e-9:
                    order = cand
                    cur_t = new_t
                    improved = True
                    break
            if improved:
                break

    return order


def optimize_full(trip, items, hk_threshold=11):
    if len(trip) <= hk_threshold:
        return held_karp_order(trip, items)
    # Bootstrap with Held-Karp on a subset wouldn't help; use heuristic.
    return iterative_optimize(trip, items)


def quick_optimize(trip, items):
    """Used inside local search; returns a strong-but-not-guaranteed-optimal order."""
    return iterative_optimize(trip, items)


# ---------- initial trip building (Clarke-Wright savings) ----------

def clarke_wright_init(items):
    N = len(items)
    if N == 0:
        return []

    trips = [[i] for i in range(N)]
    item_to_trip = list(range(N))
    trip_weight = [items[i][2] for i in range(N)]

    savings = []
    for i in range(N):
        xi, yi, _ = items[i]
        di = xi + yi  # x,y >= 0
        for j in range(i + 1, N):
            xj, yj, _ = items[j]
            dj = xj + yj
            dij = abs(xi - xj) + abs(yi - yj)
            s = di + dj - dij
            if s > 0:
                savings.append((s, i, j))
    savings.sort(reverse=True)

    for s, i, j in savings:
        ti = item_to_trip[i]
        tj = item_to_trip[j]
        if ti == tj:
            continue
        if trip_weight[ti] + trip_weight[tj] > CAPACITY:
            continue
        trip_i = trips[ti]
        trip_j = trips[tj]
        # i must be at endpoint of trip_i; j at endpoint of trip_j.
        if trip_i[-1] == i:
            ti_arr = trip_i
        elif trip_i[0] == i:
            ti_arr = list(reversed(trip_i))
        else:
            continue
        if trip_j[0] == j:
            tj_arr = trip_j
        elif trip_j[-1] == j:
            tj_arr = list(reversed(trip_j))
        else:
            continue
        merged = list(ti_arr) + list(tj_arr)
        trips[ti] = merged
        trip_weight[ti] += trip_weight[tj]
        for x in tj_arr:
            item_to_trip[x] = ti
        trips[tj] = []

    return [t for t in trips if t]


# ---------- inter-trip local search moves ----------

def best_insertion(trip, item_idx, items):
    """Insert item_idx into trip at the position minimizing trip_time."""
    best_t = float('inf')
    best_new = None
    for pos in range(len(trip) + 1):
        cand = trip[:pos] + [item_idx] + trip[pos:]
        t = trip_time(cand, items)
        if t < best_t:
            best_t = t
            best_new = cand
    return best_t, best_new


def relocate_pass(trips, trip_times, trip_weights, items, deadline):
    n = len(trips)
    for ai in range(n):
        if time.time() >= deadline:
            return False
        ta = trips[ai]
        if not ta:
            continue
        for pos_a in range(len(ta)):
            if time.time() >= deadline:
                return False
            item_idx = ta[pos_a]
            w = items[item_idx][2]
            ta_after = ta[:pos_a] + ta[pos_a + 1:]
            ta_after_t = trip_time(ta_after, items) if ta_after else 0.0
            base_a = trip_times[ai]

            for bi in range(n):
                if bi == ai or not trips[bi]:
                    continue
                if trip_weights[bi] + w > CAPACITY:
                    continue

                tb_t, tb_cand = best_insertion(trips[bi], item_idx, items)
                est_delta = (ta_after_t + tb_t) - (base_a + trip_times[bi])
                if est_delta >= -1e-9:
                    continue

                # Optimize and verify.
                if ta_after:
                    ta_opt = quick_optimize(ta_after, items)
                    ta_opt_t = trip_time(ta_opt, items)
                else:
                    ta_opt = []
                    ta_opt_t = 0.0
                tb_opt = quick_optimize(tb_cand, items)
                tb_opt_t = trip_time(tb_opt, items)
                final_delta = (ta_opt_t + tb_opt_t) - (base_a + trip_times[bi])
                if final_delta < -1e-9:
                    trips[ai] = ta_opt
                    trips[bi] = tb_opt
                    trip_times[ai] = ta_opt_t
                    trip_times[bi] = tb_opt_t
                    trip_weights[ai] -= w
                    trip_weights[bi] += w
                    return True
    return False


def swap_pass(trips, trip_times, trip_weights, items, deadline):
    n = len(trips)
    for ai in range(n):
        if time.time() >= deadline:
            return False
        ta = trips[ai]
        if not ta:
            continue
        for pos_a in range(len(ta)):
            if time.time() >= deadline:
                return False
            item_a = ta[pos_a]
            wa = items[item_a][2]
            for bi in range(ai + 1, n):
                tb = trips[bi]
                if not tb:
                    continue
                for pos_b in range(len(tb)):
                    item_b = tb[pos_b]
                    wb = items[item_b][2]
                    new_wa = trip_weights[ai] - wa + wb
                    new_wb = trip_weights[bi] - wb + wa
                    if new_wa > CAPACITY or new_wb > CAPACITY:
                        continue
                    ta_swap = list(ta)
                    ta_swap[pos_a] = item_b
                    tb_swap = list(tb)
                    tb_swap[pos_b] = item_a
                    est = trip_time(ta_swap, items) + trip_time(tb_swap, items)
                    base = trip_times[ai] + trip_times[bi]
                    if est >= base - 1e-9:
                        continue
                    ta_opt = quick_optimize(ta_swap, items)
                    tb_opt = quick_optimize(tb_swap, items)
                    ta_opt_t = trip_time(ta_opt, items)
                    tb_opt_t = trip_time(tb_opt, items)
                    if ta_opt_t + tb_opt_t < base - 1e-9:
                        trips[ai] = ta_opt
                        trips[bi] = tb_opt
                        trip_times[ai] = ta_opt_t
                        trip_times[bi] = tb_opt_t
                        trip_weights[ai] = new_wa
                        trip_weights[bi] = new_wb
                        return True
    return False


def extract_pass(trips, trip_times, trip_weights, items, deadline):
    """Move an item from its trip into a new singleton trip."""
    n = len(trips)
    for ai in range(n):
        if time.time() >= deadline:
            return False
        ta = trips[ai]
        if len(ta) <= 1:
            continue
        base_a = trip_times[ai]
        for pos in range(len(ta)):
            item_idx = ta[pos]
            w = items[item_idx][2]
            ta_after = ta[:pos] + ta[pos + 1:]
            solo_t = trip_time([item_idx], items)
            ta_after_t = trip_time(ta_after, items)
            if ta_after_t + solo_t >= base_a - 1e-9:
                continue
            ta_opt = quick_optimize(ta_after, items)
            ta_opt_t = trip_time(ta_opt, items)
            if ta_opt_t + solo_t < base_a - 1e-9:
                trips[ai] = ta_opt
                trip_times[ai] = ta_opt_t
                trip_weights[ai] -= w
                trips.append([item_idx])
                trip_times.append(solo_t)
                trip_weights.append(w)
                return True
    return False


def merge_pass(trips, trip_times, trip_weights, items, deadline):
    """Try to merge two trips if total time decreases."""
    n = len(trips)
    for i in range(n):
        if time.time() >= deadline:
            return False
        if not trips[i]:
            continue
        for j in range(i + 1, n):
            if not trips[j]:
                continue
            if trip_weights[i] + trip_weights[j] > CAPACITY:
                continue
            base = trip_times[i] + trip_times[j]
            merged = trips[i] + trips[j]
            qopt = quick_optimize(merged, items)
            qt = trip_time(qopt, items)
            if qt >= base - 1e-9:
                continue
            # Confirm with a stronger optimization.
            full_opt = optimize_full(merged, items)
            full_t = trip_time(full_opt, items)
            if full_t < base - 1e-9:
                trips[i] = full_opt
                trip_times[i] = full_t
                trip_weights[i] += trip_weights[j]
                trips[j] = []
                trip_times[j] = 0.0
                trip_weights[j] = 0
                return True
    return False


def cleanup_empty(trips, trip_times, trip_weights):
    keep = [k for k in range(len(trips)) if trips[k]]
    if len(keep) == len(trips):
        return
    new_trips = [trips[k] for k in keep]
    new_times = [trip_times[k] for k in keep]
    new_weights = [trip_weights[k] for k in keep]
    trips.clear()
    trips.extend(new_trips)
    trip_times.clear()
    trip_times.extend(new_times)
    trip_weights.clear()
    trip_weights.extend(new_weights)


def local_search(trips, items, deadline):
    trips = [optimize_full(t, items) for t in trips]
    trip_times = [trip_time(t, items) for t in trips]
    trip_weights = [sum(items[i][2] for i in t) for t in trips]

    while time.time() < deadline:
        if relocate_pass(trips, trip_times, trip_weights, items, deadline):
            cleanup_empty(trips, trip_times, trip_weights)
            continue
        if swap_pass(trips, trip_times, trip_weights, items, deadline):
            continue
        if extract_pass(trips, trip_times, trip_weights, items, deadline):
            continue
        if merge_pass(trips, trip_times, trip_weights, items, deadline):
            cleanup_empty(trips, trip_times, trip_weights)
            continue
        break

    cleanup_empty(trips, trip_times, trip_weights)
    return trips


# ---------- top-level solver ----------

def solve(items, deadline):
    if not items:
        return []
    safe = [[i] for i in range(len(items))]

    try:
        trips = clarke_wright_init(items)
        trips = [optimize_full(t, items) for t in trips]
        ls_deadline = deadline - 1.5  # reserve time for final pass + send
        if ls_deadline > time.time():
            trips = local_search(trips, items, ls_deadline)
        # Final full optimization pass (Held-Karp where possible).
        for i in range(len(trips)):
            if time.time() >= deadline - 0.3:
                break
            trips[i] = optimize_full(trips[i], items)

        # Score against safe baseline.
        cand_total = sum(trip_time(t, items) for t in trips)
        safe_total = sum(trip_time(t, items) for t in safe)
        if cand_total < safe_total - 1e-9 and validate_solution(trips, len(items)):
            return trips
        return safe
    except Exception:
        return safe


def validate_solution(trips, N):
    """Sanity-check before sending: every item exactly once, no overweight trips."""
    seen = set()
    for trip in trips:
        if not trip:
            return False
        weight = 0
        for i in trip:
            if not (0 <= i < N) or i in seen:
                return False
            seen.add(i)
            # weight check happens once we have items handle, but we just check uniqueness here
        # capacity is checked by caller using items
    return seen == set(range(N))


def validate_capacity(trips, items):
    for trip in trips:
        if sum(items[i][2] for i in trip) >= 100:
            return False
    return True


# ---------- network ----------

class Conn:
    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port))
        self.buf = b''

    def readline(self):
        while b'\n' not in self.buf:
            try:
                chunk = self.sock.recv(8192)
            except OSError:
                return None
            if not chunk:
                return None
            self.buf += chunk
        idx = self.buf.index(b'\n')
        line = self.buf[:idx].decode('ascii', errors='replace')
        self.buf = self.buf[idx + 1:]
        if line.endswith('\r'):
            line = line[:-1]
        return line

    def write(self, s):
        self.sock.sendall(s.encode('ascii'))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def handle_round(round_line, conn):
    parts = round_line.split()
    if len(parts) < 5:
        return
    try:
        N = int(parts[4])
    except ValueError:
        return

    items = [None] * N
    for _ in range(N):
        line = conn.readline()
        if line is None:
            return
        ip = line.split()
        if len(ip) < 5 or ip[0] != 'ITEM':
            continue
        try:
            idx = int(ip[1])
            x = int(ip[2])
            y = int(ip[3])
            w = int(ip[4])
        except ValueError:
            continue
        if 0 <= idx < N:
            items[idx] = (x, y, w)

    # Defensive: fill any missing with a trivial value (shouldn't happen).
    for i in range(N):
        if items[i] is None:
            items[i] = (1, 0, 1)

    compute_start = time.time()
    deadline = compute_start + 25.0  # leave 5s buffer for I/O / safety

    try:
        trips = solve(items, deadline=deadline)
    except Exception:
        trips = [[i] for i in range(N)]

    # Final validation; fall back if anything is off.
    if not validate_solution(trips, N) or not validate_capacity(trips, items):
        trips = [[i] for i in range(N)]

    out_lines = []
    for trip in trips:
        if not trip:
            continue
        out_lines.append('TRIP ' + ' '.join(str(i) for i in trip))
    out_lines.append('END')
    conn.write('\n'.join(out_lines) + '\n')


def main():
    botname = os.environ.get('BOTNAME', '')
    if botname.endswith('\n'):
        botname = botname[:-1]
    if not botname:
        sys.stderr.write('BOTNAME not set\n')
        sys.exit(1)

    try:
        conn = Conn('localhost', 7474)
    except OSError:
        sys.exit(1)

    conn.write(botname + '\n')

    try:
        while True:
            line = conn.readline()
            if line is None:
                break
            if not line:
                continue
            if line.startswith('ROUND '):
                handle_round(line, conn)
            elif line == 'TOURNAMENT_END':
                break
            # OK / INVALID / END_ROUND lines are read-and-ignored
    finally:
        conn.close()


if __name__ == '__main__':
    main()