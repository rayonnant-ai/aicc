import socket
import sys
import time

# --- 1. Graph Generation ---
# Precompute all valid Knight moves for an 8x8 board
neighbors = [[] for _ in range(64)]
for r in range(8):
    for c in range(8):
        u = r * 8 + c
        for dr, dc in [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                v = nr * 8 + nc
                neighbors[u].append(v)

A1 = 0
H8 = 63

def to_sq(u: int) -> str:
    """Convert 0-63 integer to algebraic chess notation (e.g., 0 -> A1)."""
    r, c = u // 8, u % 8
    return f"{chr(c + 65)}{r + 1}"

# --- 2. Fast Bitwise Pathfinding ---
def bfs_len(start: int, end: int, blocked_mask: int) -> int:
    """Returns the shortest path length, heavily optimized for the inner loop."""
    if start == end: return 0
    visited = blocked_mask | (1 << start)
    q = [start]
    dist = 0
    while q:
        dist += 1
        next_q = []
        for u in q:
            for v in neighbors[u]:
                if v == end: return dist
                bit = 1 << v
                if not (visited & bit):
                    visited |= bit
                    next_q.append(v)
        q = next_q
    return 999  # No path found

def bfs_path(start: int, end: int, blocked_mask: int) -> list[int]:
    """Returns the actual sequence of nodes making up the shortest path."""
    if start == end: return [start]
    visited = blocked_mask | (1 << start)
    q = [start]
    parent = {start: None}
    found = False
    
    while q:
        next_q = []
        for u in q:
            for v in neighbors[u]:
                if v == end:
                    parent[v] = u
                    found = True
                    break
                bit = 1 << v
                if not (visited & bit):
                    visited |= bit
                    parent[v] = u
                    next_q.append(v)
            if found: break
        if found: break
        q = next_q
        
    if not found: return []
    
    path = []
    curr = end
    while curr is not None:
        path.append(curr)
        curr = parent[curr]
    return path[::-1]

def format_moves(paths: list[list[int]]) -> str:
    """Flatten the generated node paths into the strict 4-char string format."""
    moves = []
    for path in paths:
        for i in range(len(path) - 1):
            u, v = path[i], path[i+1]
            moves.append(to_sq(u) + to_sq(v))
    return ",".join(moves)

# --- 3. Core Solver Algorithm ---
def solve(n: int) -> str:
    # Base case: Just one disk
    if n == 1:
        path = bfs_path(A1, H8, 0)
        return format_moves([path])

    # Beam Search configuration for selecting parking squares
    beam_width = 100
    # State: { subset_frozenset: (cost, tuple_of_squares, blocked_bitmask) }
    beam = {frozenset(): (0, (), 0)}

    # Pick N-1 distinct optimal parking spots
    for k in range(1, n):
        next_beam = {}
        for subset, (cost, tup, blocked_mask) in beam.items():
            # Try parsing the current disk into every available empty square
            for s in range(64):
                if s == A1 or s == H8 or ((1 << s) & blocked_mask):
                    continue
                
                # Check distances (cost of Scatter + Gather for this specific disk)
                l1 = bfs_len(A1, s, blocked_mask)
                if l1 > 100: continue
                l2 = bfs_len(s, H8, blocked_mask)
                if l2 > 100: continue
                
                new_cost = cost + l1 + l2
                new_subset = subset | frozenset([s])
                
                # Deduplication logic: If we've seen this exact subset of parking 
                # nodes before, only retain the permutation that gives the lowest cost.
                if new_subset not in next_beam or new_cost < next_beam[new_subset][0]:
                    new_tup = tup + (s,)
                    new_mask = blocked_mask | (1 << s)
                    next_beam[new_subset] = (new_cost, new_tup, new_mask)
        
        # Prune down to Beam Width
        sorted_next = sorted(next_beam.values(), key=lambda x: x[0])
        beam = {frozenset(v[1]): v for v in sorted_next[:beam_width]}

    # Evaluate the cost of moving Disk N (the largest) through the remaining gaps
    best_total_cost = float('inf')
    best_tup = None
    
    for subset, (cost, tup, blocked_mask) in beam.items():
        l_n = bfs_len(A1, H8, blocked_mask)
        if l_n < 100:
            if cost + l_n < best_total_cost:
                best_total_cost = cost + l_n
                best_tup = tup
                
    if best_tup is None:
        return "" # Failsafe

    # Reconstruct the exact move list using the discovered optimal parking sequence
    paths = []
    blocked_mask = 0
    
    # Phase 1: Scatter (Move 1..N-1 to their respective parking spots)
    for k in range(n - 1):
        s = best_tup[k]
        path = bfs_path(A1, s, blocked_mask)
        paths.append(path)
        blocked_mask |= (1 << s) # Mark parking spot as blocked
        
    # Phase 2: Move Largest Disk (Move N to H8)
    path = bfs_path(A1, H8, blocked_mask)
    paths.append(path)
    
    # Phase 3: Gather (Move N-1..1 from parking spots to H8)
    for k in range(n - 2, -1, -1):
        s = best_tup[k]
        blocked_mask &= ~(1 << s) # Unblock it as we pick it up
        path = bfs_path(s, H8, blocked_mask)
        paths.append(path)

    return format_moves(paths)

# --- 4. Network and Main Loop ---
def main():
    host = 'localhost'
    port = 7474
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
    except Exception as e:
        print(f"[!] Connection failed: {e}")
        return
        
    # Read/write wrapper for safe newline handling
    f = sock.makefile('rw', buffering=1) 
    
    bot_name = "gemini_bot\n"
    f.write(bot_name)
    print(f"[*] Registered as {bot_name.strip()}")
    
    while True:
        line = f.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
            
        if line == "END":
            print("[*] Tournament complete. Exiting cleanly.")
            break
            
        if line.startswith("ROUND"):
            parts = line.split()
            round_num = int(parts[1])
            n = int(parts[2])
            
            print(f"[-] Solving Round {round_num} (n={n})...")
            start_t = time.time()
            
            moves_str = solve(n)
            
            print(f"[-] Solution computed in {time.time()-start_t:.3f}s. Submitting...")
            f.write(moves_str + "\n")
            
            # Immediately read the server's sync response (VALID/INVALID/TIMEOUT)
            # This is critical to prevent desyncing from the ROUND headers.
            reply = f.readline()
            if not reply:
                break
            print(f"[SERVER] {reply.strip()}")

    sock.close()

if __name__ == "__main__":
    main()