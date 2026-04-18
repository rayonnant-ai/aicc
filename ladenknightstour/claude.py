#!/usr/bin/env python3
"""Laden Knight's Tour bot.

Connects to localhost:7474, identifies as claude_bot, and plays 10 rounds
of the weighted knight's tour problem.

Strategy
--------
The cost is sum_{k=0..n-2} (w_0 + w_1 + ... + w_k).  Equivalently the
weight of the square at 0-indexed position k is multiplied by (n-1-k).
So we want light squares early, heavy squares late, subject to knight-move
connectivity.

1. Phase A: deterministic multi-start Warnsdorff with prefer-light
   and prefer-heavy tie-breaking, and try both the tour and its reverse.
2. Phase B: iterated local search with randomized Warnsdorff restarts
   and random-reversal perturbations.
3. Phase C: long final segment-reversal polish on the best tour.

Segment reversal [i..j] is the 2-opt analogue for a Hamiltonian path.
Cost delta = sum_{k=i..j} w[tour[k]] * (2k - i - j), computed
incrementally in O(1) per j with running sums S1 = sum 2k*w, S2 = sum w.
A reversal is valid iff the two new boundary edges remain knight moves;
internal edges stay valid because knight moves are symmetric.
"""
import socket
import json
import sys
import time
import random

HOST = 'localhost'
PORT = 7474
BOT_NAME = 'claude_bot'
TIME_BUDGET = 8.5  # leave margin under the 10s server timeout

KNIGHT_DELTAS = (
    (-2, -1), (-2, 1), (-1, -2), (-1, 2),
    ( 1, -2), ( 1, 2), ( 2, -1), ( 2, 1),
)


# --------------------------------------------------------------------- #
#  Core graph + cost helpers                                            #
# --------------------------------------------------------------------- #

def compute_neighbors(rows, cols):
    """For each square index, the list of reachable square indices."""
    n = rows * cols
    nbrs = [[] for _ in range(n)]
    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            for dr, dc in KNIGHT_DELTAS:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    nbrs[i].append(nr * cols + nc)
    return nbrs


def tour_cost(tour, w):
    """Total elapsed time. Last square's weight is free."""
    total = 0
    load = 0
    for i in range(len(tour) - 1):
        load += w[tour[i]]
        total += load
    return total


# --------------------------------------------------------------------- #
#  Warnsdorff construction                                              #
# --------------------------------------------------------------------- #

def warnsdorff(n, nbrs, w, start, tie_sign=1, rng=None):
    """Classical Warnsdorff with weighted tie-break.

    tie_sign=+1 -> prefer lighter (save heavy for later in forward tour)
    tie_sign=-1 -> prefer heavier (useful when we then reverse the tour)
    tie_sign= 0 -> weight indifferent
    rng, if given, adds a final jitter term for extra diversity.
    Returns the tour as a list of square indices, or None on dead-end.
    """
    visited = bytearray(n)
    visited[start] = 1
    tour = [start]

    for _ in range(n - 1):
        cur = tour[-1]
        best = -1
        best_key = None
        for m in nbrs[cur]:
            if visited[m]:
                continue
            deg = 0
            for x in nbrs[m]:
                if not visited[x]:
                    deg += 1
            jitter = rng.random() if rng is not None else 0.0
            key = (deg, tie_sign * w[m], jitter)
            if best_key is None or key < best_key:
                best_key = key
                best = m
        if best < 0:
            return None
        tour.append(best)
        visited[best] = 1
    return tour


# --------------------------------------------------------------------- #
#  Segment-reversal local search (2-opt for Hamiltonian paths)          #
# --------------------------------------------------------------------- #

def segment_reverse_improve(tour, nbrs_set, w, time_limit):
    """Steepest-descent local search that reverses contiguous segments.

    Each pass scans all O(n^2) segments, records the best improving valid
    reversal, applies it, and repeats until no improvement or time is up.
    """
    t_start = time.time()
    n = len(tour)
    while time.time() - t_start < time_limit:
        best_delta = 0
        best_ij = None
        timed_out = False
        for i in range(n):
            if time.time() - t_start > time_limit:
                timed_out = True
                break
            S1 = 0
            S2 = 0
            nbrs_prev = nbrs_set[tour[i - 1]] if i > 0 else None
            tour_i = tour[i]
            nbrs_i = nbrs_set[tour_i]
            for j in range(i, n):
                tj = tour[j]
                wtj = w[tj]
                S1 += 2 * j * wtj
                S2 += wtj
                if j == i:
                    continue
                delta = S1 - (i + j) * S2
                if delta >= best_delta:
                    continue
                # Validate new boundary edges (internals are symmetric).
                if nbrs_prev is not None and tj not in nbrs_prev:
                    continue
                if j + 1 < n and tour[j + 1] not in nbrs_i:
                    continue
                best_delta = delta
                best_ij = (i, j)
        if timed_out or best_ij is None:
            break
        i, j = best_ij
        tour[i:j + 1] = tour[i:j + 1][::-1]
    return tour


def random_perturb(tour, nbrs_set, rng):
    """Apply one random valid segment reversal of length >= 3, in place."""
    n = len(tour)
    for _ in range(30):
        i = rng.randrange(n)
        j = rng.randrange(n)
        if i > j:
            i, j = j, i
        if j - i < 2:
            continue
        prev = tour[i - 1] if i > 0 else None
        if prev is not None and tour[j] not in nbrs_set[prev]:
            continue
        if j + 1 < n and tour[j + 1] not in nbrs_set[tour[i]]:
            continue
        tour[i:j + 1] = tour[i:j + 1][::-1]
        return True
    return False


# --------------------------------------------------------------------- #
#  Top-level solver                                                     #
# --------------------------------------------------------------------- #

def solve(rows, cols, weights, time_budget=TIME_BUDGET):
    t_start = time.time()
    n = rows * cols
    w = [weights[r][c] for r in range(rows) for c in range(cols)]
    nbrs = compute_neighbors(rows, cols)
    nbrs_set = [frozenset(x) for x in nbrs]

    rng = random.Random(0xBEEF)
    best = None
    best_cost = float('inf')

    def consider(tour):
        nonlocal best, best_cost
        if tour is None:
            return False
        c = tour_cost(tour, w)
        if c < best_cost:
            best_cost = c
            best = list(tour)
            return True
        return False

    # ---- Phase A: deterministic multi-start Warnsdorff. ----
    # Walk start squares in ascending weight (light ones make good tour
    # beginnings).  For each, run both tie-break directions and consider
    # both the tour and its reverse.
    squares_by_weight = sorted(range(n), key=lambda i: w[i])
    for start in squares_by_weight:
        if time.time() - t_start > 0.15 * time_budget:
            break
        for sign in (1, -1):
            t = warnsdorff(n, nbrs, w, start, tie_sign=sign)
            if t is not None:
                consider(t)
                consider(t[::-1])

    # ---- Phase B: iterated local search / randomized restarts. ----
    while time.time() - t_start < 0.85 * time_budget:
        rem_total = time_budget - (time.time() - t_start)
        if rem_total < 0.3:
            break

        if best is None or rng.random() < 0.55:
            # Fresh randomized Warnsdorff.
            start = rng.randrange(n)
            sign = rng.choice([-1, 0, 1])
            t = warnsdorff(n, nbrs, w, start, tie_sign=sign, rng=rng)
        else:
            # Perturb current best with 1-3 random reversals.
            t = list(best)
            for _ in range(rng.randrange(1, 4)):
                random_perturb(t, nbrs_set, rng)

        if t is None:
            continue

        local_budget = min(0.4, rem_total * 0.15)
        improved = segment_reverse_improve(t, nbrs_set, w, local_budget)
        consider(improved)
        consider(improved[::-1])

    # ---- Phase C: long final polish on the best tour so far. ----
    if best is not None:
        rem = time_budget - (time.time() - t_start)
        if rem > 0.15:
            improved = segment_reverse_improve(list(best), nbrs_set, w, rem * 0.9)
            consider(improved)

    # ---- Emergency fallback (should never trigger given problem guarantees). ----
    if best is None:
        for _ in range(2000):
            if time.time() - t_start > time_budget:
                break
            t = warnsdorff(n, nbrs, w, rng.randrange(n), tie_sign=0, rng=rng)
            if t is not None:
                consider(t)
                break

    return best


# --------------------------------------------------------------------- #
#  Networking                                                           #
# --------------------------------------------------------------------- #

class LineReader:
    def __init__(self, sock):
        self.sock = sock
        self.buf = bytearray()

    def _refill(self):
        data = self.sock.recv(65536)
        if not data:
            return False
        self.buf.extend(data)
        return True

    def readline(self):
        while True:
            idx = self.buf.find(b'\n')
            if idx >= 0:
                line = bytes(self.buf[:idx]).decode()
                del self.buf[:idx + 1]
                return line
            if not self._refill():
                return None

    def readbytes(self, nb):
        while len(self.buf) < nb:
            if not self._refill():
                return None
        out = bytes(self.buf[:nb])
        del self.buf[:nb]
        return out


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    sock.sendall((BOT_NAME + '\n').encode())
    reader = LineReader(sock)

    round_num = 0
    while True:
        try:
            line = reader.readline()
            if line is None:
                break
            line = line.strip()
            if not line:
                continue

            if line.startswith('ROUND'):
                round_num += 1
                size_line = reader.readline()
                if size_line is None:
                    break
                nbytes = int(size_line.strip().split()[1])
                payload = reader.readbytes(nbytes)
                if payload is None:
                    break
                data = json.loads(payload.decode())
                rows = data['rows']
                cols = data['cols']
                weights = data['weights']

                t0 = time.time()
                tour = solve(rows, cols, weights)
                elapsed = time.time() - t0

                if tour is None:
                    print(f'[r{round_num}] FAILED to build a tour', file=sys.stderr)
                    resp = json.dumps({'tour': []})
                else:
                    flat_w = [weights[r][c] for r in range(rows) for c in range(cols)]
                    cost = tour_cost(tour, flat_w)
                    tour_rc = [[i // cols, i % cols] for i in tour]
                    print(
                        f'[r{round_num}] {rows}x{cols}={rows * cols} sq | '
                        f'cost={cost} | {elapsed:.2f}s',
                        file=sys.stderr,
                    )
                    resp = json.dumps({'tour': tour_rc})
                sock.sendall((resp + '\n').encode())

            elif line.startswith(('VALID', 'INVALID', 'TIMEOUT')):
                print(f'[server] {line}', file=sys.stderr)
            else:
                print(f'[server ?] {line}', file=sys.stderr)

        except (ConnectionError, OSError) as e:
            print(f'Connection closed: {e}', file=sys.stderr)
            break
        except Exception as e:
            import traceback
            print(f'Error: {e}', file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            break

    try:
        sock.close()
    except Exception:
        pass


if __name__ == '__main__':
    main()