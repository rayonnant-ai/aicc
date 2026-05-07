# bot author: ChatGPT GPT 5.5
#!/usr/bin/env python3
# bot author: GPT-5.5 Thinking

import os
import re
import socket
import sys
import time
import math
import heapq
from collections import defaultdict


HOST = "localhost"
PORT = 7474
CAPACITY = 99          # total trip weight must stay below 100 before positive return leg
SAFETY_SECONDS = 27.5  # leave time for sending before 30s server deadline


def speed(load):
    return 10 - (load // 10)


class Planner:
    def __init__(self, items, deadline):
        self.items = items  # list of (x, y, w)
        self.deadline = deadline
        self.cost_cache = {}

    def item_key_far(self, idx):
        x, y, _ = self.items[idx]
        return (-(x + y), -max(x, y), math.atan2(y, x), idx)

    def route_weight(self, seq):
        return sum(self.items[i][2] for i in seq)

    def route_time(self, seq):
        """Exact simulator for one trip."""
        key = tuple(seq)
        cached = self.cost_cache.get(key)
        if cached is not None:
            return cached

        load = 0
        px = py = 0
        total = 0.0

        for idx in seq:
            x, y, w = self.items[idx]
            d = abs(x - px) + abs(y - py)
            if d:
                s = speed(load)
                if s <= 0:
                    self.cost_cache[key] = float("inf")
                    return float("inf")
                total += d / s
            load += w
            px, py = x, y

        d = abs(px) + abs(py)
        if d:
            s = speed(load)
            if s <= 0:
                self.cost_cache[key] = float("inf")
                return float("inf")
            total += d / s

        self.cost_cache[key] = total
        return total

    def normalize_route(self, seq):
        """A cheap, usually strong order: visit farther bins first, drift back toward depot."""
        return sorted(seq, key=self.item_key_far)

    def best_merge_sequence(self, a, b):
        combined = a + b
        candidates = [
            a + b,
            b + a,
            list(reversed(a)) + b,
            a + list(reversed(b)),
            list(reversed(a)) + list(reversed(b)),
            list(reversed(b)) + list(reversed(a)),
            self.normalize_route(combined),
        ]

        best_seq = candidates[0]
        best_cost = self.route_time(best_seq)

        for seq in candidates[1:]:
            c = self.route_time(seq)
            if c < best_cost:
                best_cost = c
                best_seq = seq

        return best_seq, best_cost

    def pack_same_bin_chunks(self):
        """Co-located items are essentially free to pick consecutively; split only by capacity."""
        by_bin = defaultdict(list)
        for i, (x, y, w) in enumerate(self.items):
            by_bin[(x, y)].append(i)

        routes = []
        for _, ids in by_bin.items():
            ids.sort(key=lambda i: -self.items[i][2])

            # First-fit decreasing within the bin.
            chunks = []
            weights = []
            for idx in ids:
                w = self.items[idx][2]
                placed = False
                for k in range(len(chunks)):
                    if weights[k] + w <= CAPACITY:
                        chunks[k].append(idx)
                        weights[k] += w
                        placed = True
                        break
                if not placed:
                    chunks.append([idx])
                    weights.append(w)

            routes.extend(chunks)

        return routes

    def clarke_wright_merge(self, initial_routes):
        """Priority-queue route merging using exact simulated savings."""
        routes = {}
        weights = {}
        costs = {}
        active = set()
        next_id = 0

        for seq in initial_routes:
            seq = self.normalize_route(seq)
            rid = next_id
            next_id += 1
            routes[rid] = seq
            weights[rid] = self.route_weight(seq)
            costs[rid] = self.route_time(seq)
            active.add(rid)

        heap = []

        def push_pair(i, j):
            if time.monotonic() > self.deadline:
                return
            if i == j or i not in active or j not in active:
                return
            if weights[i] + weights[j] > CAPACITY:
                return

            seq, merged_cost = self.best_merge_sequence(routes[i], routes[j])
            saving = costs[i] + costs[j] - merged_cost
            if saving > 1e-9:
                heapq.heappush(heap, (-saving, i, j, tuple(seq), merged_cost))

        ids = list(active)
        for pos, i in enumerate(ids):
            for j in ids[pos + 1:]:
                push_pair(i, j)
                if time.monotonic() > self.deadline:
                    return list(routes[i] for i in active)

        while heap and time.monotonic() <= self.deadline:
            neg_saving, i, j, seq_tuple, merged_cost = heapq.heappop(heap)
            if i not in active or j not in active:
                continue
            if weights[i] + weights[j] > CAPACITY:
                continue

            # Recheck because old heap entries may be stale.
            seq, true_cost = self.best_merge_sequence(routes[i], routes[j])
            true_saving = costs[i] + costs[j] - true_cost
            if true_saving <= 1e-9:
                continue

            active.remove(i)
            active.remove(j)

            new_id = next_id
            next_id += 1
            routes[new_id] = seq
            weights[new_id] = weights[i] + weights[j]
            costs[new_id] = true_cost
            active.add(new_id)

            others = list(active)
            for k in others:
                if k != new_id:
                    push_pair(new_id, k)
                if time.monotonic() > self.deadline:
                    break

        return [routes[rid] for rid in active]

    def improve_route(self, seq):
        """Small local search: exact-cost adjacent and pair swaps."""
        if len(seq) <= 1 or time.monotonic() > self.deadline:
            return seq

        starts = [
            seq,
            self.normalize_route(seq),
            sorted(seq, key=lambda i: (-math.hypot(self.items[i][0], self.items[i][1]), i)),
            sorted(seq, key=lambda i: (math.atan2(self.items[i][1], self.items[i][0]), -(self.items[i][0] + self.items[i][1]))),
        ]

        best = min(starts, key=self.route_time)
        best_cost = self.route_time(best)
        n = len(best)

        # Adjacent-swap pass; cheap and often helpful.
        changed = True
        passes = 0
        while changed and passes < 4 and time.monotonic() <= self.deadline:
            changed = False
            passes += 1
            for i in range(n - 1):
                cand = best[:]
                cand[i], cand[i + 1] = cand[i + 1], cand[i]
                c = self.route_time(cand)
                if c + 1e-9 < best_cost:
                    best, best_cost = cand, c
                    changed = True

        # Broader pair-swap for modest route sizes.
        if n <= 55:
            improved = True
            while improved and time.monotonic() <= self.deadline:
                improved = False
                for i in range(n - 1):
                    for j in range(i + 1, n):
                        cand = best[:]
                        cand[i], cand[j] = cand[j], cand[i]
                        c = self.route_time(cand)
                        if c + 1e-9 < best_cost:
                            best, best_cost = cand, c
                            improved = True
                            break
                    if improved or time.monotonic() > self.deadline:
                        break

        return best

    def plan(self):
        routes = self.pack_same_bin_chunks()
        routes = self.clarke_wright_merge(routes)

        improved = []
        for r in routes:
            if time.monotonic() > self.deadline:
                improved.append(r)
            else:
                improved.append(self.improve_route(r))

        # Stable, deterministic output: big/far trips first. Trip order does not affect score.
        improved.sort(key=lambda seq: (-self.route_weight(seq), self.route_time(seq)))
        return improved


def valid_botname(name):
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,32}", name))


def read_line(sock_file):
    line = sock_file.readline()
    if not line:
        return None
    return line.decode("ascii").rstrip("\n")


def send_line(sock, text):
    sock.sendall(text.encode("ascii") + b"\n")


def submit_trips(sock, trips):
    out = []
    for trip in trips:
        out.append("TRIP " + " ".join(str(i) for i in trip))
    out.append("END")
    sock.sendall(("\n".join(out) + "\n").encode("ascii"))


def main():
    botname = os.environ.get("BOTNAME", "").rstrip("\n")
    if not botname or not valid_botname(botname):
        return 2

    try:
        sock = socket.create_connection((HOST, PORT))
    except OSError as e:
        print(f"connection failed: {e}", file=sys.stderr)
        return 1

    with sock:
        f = sock.makefile("rb", buffering=0)
        send_line(sock, botname)

        while True:
            line = read_line(f)
            if line is None:
                break

            if line == "TOURNAMENT_END":
                break

            if not line.startswith("ROUND "):
                # Ignore OK / INVALID / END_ROUND or any unexpected informational line.
                continue

            parts = line.split()
            if len(parts) != 5:
                break

            try:
                round_no = int(parts[1])
                wm = int(parts[2])
                hm = int(parts[3])
                n = int(parts[4])
            except ValueError:
                break

            items = [None] * n
            for _ in range(n):
                item_line = read_line(f)
                if item_line is None:
                    return 0
                p = item_line.split()
                if len(p) != 5 or p[0] != "ITEM":
                    return 1
                idx = int(p[1])
                x = int(p[2])
                y = int(p[3])
                w = int(p[4])
                if 0 <= idx < n:
                    items[idx] = (x, y, w)

            # Fallback should never be needed for valid server input.
            for i in range(n):
                if items[i] is None:
                    items[i] = (1, 0, 1)

            deadline = time.monotonic() + SAFETY_SECONDS
            planner = Planner(items, deadline)

            try:
                trips = planner.plan()
            except Exception:
                # Always prefer a valid weak submission over an invalid/no submission.
                trips = [[i] for i in range(n)]

            # Final validation fallback.
            seen = set()
            safe_trips = []
            valid = True
            for trip in trips:
                if not trip:
                    valid = False
                    break
                tw = sum(items[i][2] for i in trip)
                if tw > CAPACITY:
                    valid = False
                    break
                for i in trip:
                    if i in seen or not (0 <= i < n):
                        valid = False
                        break
                    seen.add(i)
                if not valid:
                    break
                safe_trips.append(trip)

            if not valid or len(seen) != n:
                safe_trips = [[i] for i in range(n)]

            submit_trips(sock, safe_trips)

        return 0


if __name__ == "__main__":
    raise SystemExit(main())