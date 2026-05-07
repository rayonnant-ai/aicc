# bot author: Grok Expert 4.20
#!/usr/bin/env python3
"""
WarehouseRobot tournament bot.
bot author: Grok (xAI) - full strategy with cheapest-insertion construction (far-first seeding),
exact load-dependent time evaluation, exhaustive order optimization for small trips,
2-opt for larger, and greedy time-saving merges.
"""

import os
import sys
import socket
import math
import itertools
from typing import List, Tuple, Optional


def manhattan(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def get_speed(load_kg: int) -> int:
    if load_kg >= 100:
        return 0
    return 10 - (load_kg // 10)


def compute_trip_time(
    trip: List[int],
    positions: List[Tuple[int, int]],
    weights: List[int]
) -> float:
    if not trip:
        return 0.0
    path = [(0, 0)] + [positions[i] for i in trip] + [(0, 0)]
    load = 0
    total_time = 0.0
    k = len(trip)
    for j in range(len(path) - 1):
        p_from = path[j]
        p_to = path[j + 1]
        d = manhattan(p_from, p_to)
        s = get_speed(load)
        if d > 0 and s == 0:
            return float("inf")
        if d > 0:
            total_time += d / s
        if j < k:  # pickup after arriving at an item (not final depot)
            load += weights[trip[j]]
    return total_time


def improve_trip(
    trip: List[int],
    positions: List[Tuple[int, int]],
    weights: List[int],
    max_passes: int = 5
) -> List[int]:
    if len(trip) <= 2:
        return list(trip)
    current = list(trip)
    current_t = compute_trip_time(current, positions, weights)
    for _ in range(max_passes):
        improved = False
        n = len(current)
        for i in range(n):
            for j in range(i + 1, n):
                new_seq = current[:i] + current[i : j + 1][::-1] + current[j + 1 :]
                new_t = compute_trip_time(new_seq, positions, weights)
                if new_t < current_t:
                    current = new_seq
                    current_t = new_t
                    improved = True
        if not improved:
            break
    return current


def optimize_trip_order(
    trip: List[int],
    positions: List[Tuple[int, int]],
    weights: List[int]
) -> List[int]:
    k = len(trip)
    if k <= 1:
        return list(trip)
    if k <= 8:
        best_seq = list(trip)
        best_t = compute_trip_time(best_seq, positions, weights)
        for perm in itertools.permutations(trip):
            new_t = compute_trip_time(list(perm), positions, weights)
            if new_t < best_t:
                best_t = new_t
                best_seq = list(perm)
        return best_seq
    else:
        return improve_trip(trip, positions, weights, max_passes=5)


def improve_by_merging(
    trips: List[List[int]],
    positions: List[Tuple[int, int]],
    weights: List[int]
) -> List[List[int]]:
    if not trips:
        return trips
    trip_list: List[List[int]] = [list(t) for t in trips]
    w_list: List[int] = [sum(weights[i] for i in t) for t in trip_list]
    improved = True
    merge_count = 0
    MAX_MERGES = 200  # safety
    while improved and merge_count < MAX_MERGES:
        improved = False
        best_save = -1.0
        best_pair: Optional[Tuple[int, int]] = None
        best_new_seq: Optional[List[int]] = None
        for ii in range(len(trip_list)):
            for jj in range(ii + 1, len(trip_list)):
                if w_list[ii] + w_list[jj] > 99:
                    continue
                old_t = compute_trip_time(trip_list[ii], positions, weights) + compute_trip_time(
                    trip_list[jj], positions, weights
                )
                for order in (
                    trip_list[ii] + trip_list[jj],
                    trip_list[jj] + trip_list[ii],
                ):
                    new_t = compute_trip_time(order, positions, weights)
                    save = old_t - new_t
                    if save > best_save:
                        best_save = save
                        best_pair = (ii, jj)
                        best_new_seq = order
        if best_pair is not None and best_save > 0:
            ii, jj = best_pair
            trip_list[ii] = best_new_seq  # type: ignore
            w_list[ii] = w_list[ii] + w_list[jj]
            del trip_list[jj]
            del w_list[jj]
            trip_list[ii] = optimize_trip_order(trip_list[ii], positions, weights)
            improved = True
            merge_count += 1
    return trip_list


def plan_trips(
    positions: List[Tuple[int, int]], weights: List[int]
) -> List[List[int]]:
    N = len(positions)
    if N == 0:
        return []
    depot = (0, 0)
    dist_from_depot = [manhattan(depot, positions[i]) for i in range(N)]
    # Far-first ordering: largest distance first (break ties by heavier first, then index)
    item_order = sorted(
        range(N), key=lambda i: (-dist_from_depot[i], -weights[i], i)
    )
    trips: List[List[int]] = []
    trip_weights: List[int] = []
    for item in item_order:
        w = weights[item]
        standalone_t = compute_trip_time([item], positions, weights)
        best_increase = standalone_t
        best_trip_idx: Optional[int] = None
        best_pos: Optional[int] = None
        for t_idx, trip in enumerate(trips):
            if trip_weights[t_idx] + w > 99:
                continue
            old_t = compute_trip_time(trip, positions, weights)
            for pos in range(len(trip) + 1):
                new_trip = trip[:pos] + [item] + trip[pos:]
                new_t = compute_trip_time(new_trip, positions, weights)
                if new_t == float("inf"):
                    continue
                delta = new_t - old_t
                if delta < best_increase:
                    best_increase = delta
                    best_trip_idx = t_idx
                    best_pos = pos
        if best_trip_idx is not None:
            trips[best_trip_idx].insert(best_pos, item)  # type: ignore
            trip_weights[best_trip_idx] += w
        else:
            trips.append([item])
            trip_weights.append(w)
    # Optimize order in each trip (exhaustive if small)
    for t_idx in range(len(trips)):
        trips[t_idx] = optimize_trip_order(trips[t_idx], positions, weights)
    # Further improve by merging trips when it reduces total time
    trips = improve_by_merging(trips, positions, weights)
    return trips


class LineReader:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buffer = bytearray()

    def readline(self) -> Optional[str]:
        while b"\n" not in self.buffer:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    if self.buffer:
                        line = bytes(self.buffer)
                        self.buffer.clear()
                        return line.decode("ascii")
                    return None
                self.buffer.extend(chunk)
            except Exception:
                return None
        idx = self.buffer.find(b"\n")
        line = bytes(self.buffer[:idx])
        del self.buffer[: idx + 1]
        return line.decode("ascii")


def main() -> None:
    botname = os.environ.get("BOTNAME", "").strip()
    if not botname:
        print("ERROR: BOTNAME environment variable is missing or empty", file=sys.stderr)
        sys.exit(1)
    if not (1 <= len(botname) <= 32) or not all(
        c.isalnum() or c in "_-" for c in botname
    ):
        print(f"ERROR: Invalid BOTNAME '{botname}'", file=sys.stderr)
        sys.exit(1)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("localhost", 7474))
    except Exception as e:
        print(f"ERROR: Failed to connect to tournament server: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        sock.sendall((botname + "\n").encode("ascii"))
        reader = LineReader(sock)

        while True:
            line = reader.readline()
            if line is None:
                break
            line = line.rstrip("\r\n")
            if line == "TOURNAMENT_END":
                break
            if line.startswith("ROUND "):
                parts = line.split()
                if len(parts) != 5:
                    continue
                round_n = int(parts[1])
                wm = int(parts[2])
                hm = int(parts[3])
                N = int(parts[4])
                positions: List[Tuple[int, int]] = [ (0,0) ] * N
                weights: List[int] = [0] * N
                for i in range(N):
                    item_line = reader.readline()
                    if item_line is None:
                        break
                    item_line = item_line.rstrip("\r\n")
                    p = item_line.split()
                    if len(p) != 5 or p[0] != "ITEM":
                        continue
                    idx = int(p[1])
                    x = int(p[2])
                    y = int(p[3])
                    w = int(p[4])
                    positions[idx] = (x, y)
                    weights[idx] = w
                # Compute trips using full strategy
                trips = plan_trips(positions, weights)
                # Send submission
                for trip in trips:
                    if trip:
                        msg = "TRIP " + " ".join(str(idx) for idx in trip) + "\n"
                        sock.sendall(msg.encode("ascii"))
                sock.sendall(b"END\n")
                # Read server response (OK/INVALID + END_ROUND)
                resp = reader.readline()
                if resp:
                    resp = resp.rstrip("\r\n")
                    if "INVALID" in resp:
                        print(f"Round {round_n}: {resp}", file=sys.stderr)
                endr = reader.readline()  # END_ROUND line
    finally:
        try:
            sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()