#!/usr/bin/env python3
"""
Laden Knight's Tour - TCP Client
Solves the weighted knight's tour problem using a Randomized Warnsdorff Heuristic
with Backwards Search optimization.
"""

import json
import socket
import time
import random
import sys

HOST = 'localhost'
PORT = 7474
BOT_NAME = 'gemini_bot'

def compute_tour(rows, cols, weights, time_limit=9.0):
    start_time = time.time()
    best_tour = None
    best_cost = float('inf')

    N_squares = rows * cols
    max_w = max(max(r) for r in weights)
    
    # Precompute knight moves for every square
    neighbors = {}
    for r in range(rows):
        for c in range(cols):
            neighbors[(r, c)] = []
            for dr, dc in [(1, 2), (2, 1), (-1, 2), (-2, 1), 
                           (1, -2), (2, -1), (-1, -2), (-2, -1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    neighbors[(r, c)].append((nr, nc))

    # All squares sorted by weight descending.
    # We search backwards: the START of our reversed tour corresponds to the END 
    # of the forward tour, where the weight multiplier is 0. 
    # Therefore, we want to place the heaviest squares early in the backwards tour.
    all_squares = [(r, c) for r in range(rows) for c in range(cols)]
    all_squares.sort(key=lambda sq: weights[sq[0]][sq[1]], reverse=True)

    def get_rev_tour(start_sq, noise_deg, weight_factor, max_bt):
        rev_tour = [start_sq]
        visited = {start_sq}
        backtracks = 0
        found_tour = None
        calls = 0
        
        def solve(curr):
            nonlocal backtracks, found_tour, calls
            calls += 1
            
            # Periodic time check to avoid overhead
            if calls % 50 == 0 and time.time() - start_time > time_limit:
                return True 
            
            if backtracks > max_bt:
                return True # Abort this branch
                
            if len(rev_tour) == N_squares:
                found_tour = list(rev_tour)
                return True
                
            unvisited = [n for n in neighbors[curr] if n not in visited]
            if not unvisited:
                return False
                
            scored = []
            for n in unvisited:
                deg = sum(1 for nn in neighbors[n] if nn not in visited)
                w = weights[n[0]][n[1]]
                
                # Base score is Warnsdorff's degree
                score = deg 
                
                if noise_deg > 0:
                    score += random.uniform(0, noise_deg)
                if weight_factor > 0:
                    # Subtract weight influence: we PREFER heavy squares in backwards search
                    score -= (w / max_w) * random.uniform(0, weight_factor)
                    
                scored.append((score, n))
                
            # Sort neighbors prioritizing lowest score (low degree, high weight)
            scored.sort(key=lambda x: x[0])
            
            for _, nxt in scored:
                visited.add(nxt)
                rev_tour.append(nxt)
                if solve(nxt):
                    return True
                visited.remove(nxt)
                rev_tour.pop()
                backtracks += 1
                
            return False

        solve(start_sq)
        return found_tour

    # 1. Baseline Phase: Try to find ANY valid tour quickly
    # Uses strict Warnsdorff with tiny weight tie-breakers to ensure completion.
    for start_sq in all_squares:
        if best_tour is not None:
            break
        if time.time() - start_time > time_limit - 1.0:
            break
            
        rev_t = get_rev_tour(start_sq, noise_deg=0.0, weight_factor=0.01, max_bt=5000)
        if rev_t:
            forward_tour = rev_t[::-1]
            cost = sum(weights[r][c] * (N_squares - 1 - i) for i, (r, c) in enumerate(forward_tour))
            best_tour = forward_tour
            best_cost = cost

    # 2. Optimization Phase: Randomized Restarts
    # Aggressively samples paths trying to place heavy weights near the end.
    top_heaviest = all_squares[:max(1, len(all_squares) // 5)]
    
    while time.time() - start_time < time_limit:
        start_sq = random.choice(top_heaviest)
        
        n_deg = random.uniform(0.5, 2.0)
        w_fac = random.uniform(0.5, 3.0)
        m_bt = random.choice([50, 100, 200, 400])
        
        rev_t = get_rev_tour(start_sq, noise_deg=n_deg, weight_factor=w_fac, max_bt=m_bt)
        if rev_t:
            forward_tour = rev_t[::-1]
            cost = sum(weights[r][c] * (N_squares - 1 - i) for i, (r, c) in enumerate(forward_tour))
            if cost < best_cost:
                best_cost = cost
                best_tour = forward_tour

    return best_tour

def main():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))
    except Exception as e:
        print(f"Failed to connect to {HOST}:{PORT}: {e}")
        sys.exit(1)
        
    f = sock.makefile('rw', encoding='utf-8')
    
    # Register bot
    f.write(f"{BOT_NAME}\n")
    f.flush()
    print(f"Connected and registered as {BOT_NAME}.")
    
    while True:
        try:
            line = f.readline()
            if not line:
                break
                
            if line.startswith("ROUND"):
                round_num = line.strip().split()[1]
                print(f"--- Starting Round {round_num} ---")
                
                size_line = f.readline()
                size = int(size_line.strip().split()[1])
                
                payload = f.read(size)
                data = json.loads(payload)
                
                rows = data['rows']
                cols = data['cols']
                weights = data['weights']
                
                print(f"Received {rows}x{cols} board. Computing...")
                
                # Use 9.5s to ensure we respond well within the 10.0s server timeout
                tour = compute_tour(rows, cols, weights, time_limit=9.5)
                
                if tour is None:
                    print("Failed to find any valid tour!")
                    tour = []
                else:
                    print(f"Tour found! Length: {len(tour)}")

                resp = json.dumps({"tour": tour})
                f.write(resp + "\n")
                f.flush()
                
            elif line.startswith("VALID") or line.startswith("INVALID") or line.startswith("TIMEOUT"):
                print(f"Result: {line.strip()}")
            else:
                pass # Ignore or log unexpected lines if necessary
                
        except Exception as e:
            print(f"Error during execution: {e}")
            break

if __name__ == "__main__":
    main()