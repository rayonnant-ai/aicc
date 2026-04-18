import socket
import json
import sys

KNIGHT_MOVES = [
    (-2, -1), (-2, 1), (-1, -2), (-1, 2),
    (1, -2), (1, 2), (2, -1), (2, 1)
]

def is_valid_pos(r, c, rows, cols):
    return 0 <= r < rows and 0 <= c < cols

def get_possible_moves(r, c, rows, cols, visited):
    moves = []
    for dr, dc in KNIGHT_MOVES:
        nr, nc = r + dr, c + dc
        if is_valid_pos(nr, nc, rows, cols) and not visited[nr][nc]:
            moves.append((nr, nc))
    return moves

def count_onward(nr, nc, rows, cols, visited):
    count = 0
    for dr, dc in KNIGHT_MOVES:
        nnr, nnc = nr + dr, nc + dc
        if is_valid_pos(nnr, nnc, rows, cols) and not visited[nnr][nnc]:
            count += 1
    return count

def dfs(curr_r, curr_c, visited, tour, rows, cols, weights):
    tour.append([curr_r, curr_c])
    visited[curr_r][curr_c] = True
    
    if len(tour) == rows * cols:
        return True
    
    possibles = get_possible_moves(curr_r, curr_c, rows, cols, visited)
    
    def sort_key(pos):
        nr, nc = pos
        onward = count_onward(nr, nc, rows, cols, visited)
        w = weights[nr][nc]
        return (onward, w, nr * cols + nc)  # Warnsdorff + low-weight bias + stable tiebreak
    
    possibles.sort(key=sort_key)
    
    for nr, nc in possibles:
        if dfs(nr, nc, visited, tour, rows, cols, weights):
            return True
    
    # backtrack
    tour.pop()
    visited[curr_r][curr_c] = False
    return False

def calculate_time(tour, weights):
    # Equivalent to the problem's cumulative-load formula
    N = len(tour)
    total = 0
    for i in range(N):
        r, c = tour[i]
        total += weights[r][c] * (N - 1 - i)
    return total

def get_tour(rows, cols, weights):
    # Sort potential starts by increasing weight (we want light squares early)
    starts = []
    for r in range(rows):
        for c in range(cols):
            starts.append((weights[r][c], r * cols + c, r, c))
    starts.sort()
    
    best_tour = None
    best_time = float('inf')
    
    # Try starting from the lightest positions first (up to 30 attempts)
    # This biases the entire path toward low-weight early + heavy late
    attempts = min(30, len(starts))
    for _, _, sr, sc in starts[:attempts]:
        visited = [[False] * cols for _ in range(rows)]
        tour = []
        if dfs(sr, sc, visited, tour, rows, cols, weights):
            t = calculate_time(tour, weights)
            if t < best_time:
                best_time = t
                best_tour = [pos[:] for pos in tour]  # deep copy
    
    if best_tour:
        return best_tour
    
    # Extremely rare fallback (problem guarantees a tour exists)
    for _, _, sr, sc in starts[attempts:]:
        visited = [[False] * cols for _ in range(rows)]
        tour = []
        if dfs(sr, sc, visited, tour, rows, cols, weights):
            t = calculate_time(tour, weights)
            if t < best_time:
                best_time = t
                best_tour = [pos[:] for pos in tour]
    return best_tour

def main():
    # Bot name (change via command-line arg if desired: python client.py my_custom_bot)
    bot_name = sys.argv[1] if len(sys.argv) > 1 else "grok_laden_knight_bot"
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 7474))
    
    # Register with the server
    s.sendall(f"{bot_name}\n".encode('utf-8'))
    print(f"Registered as '{bot_name}'", file=sys.stderr)
    
    # Use file-like interface for clean line/byte reading
    f = s.makefile('r', encoding='utf-8')
    
    while True:
        line = f.readline()
        if not line:
            print("Connection closed by server.", file=sys.stderr)
            break
        line = line.strip()
        
        if line.startswith("ROUND"):
            round_num = line.split()[1]
            print(f"→ Round {round_num} started", file=sys.stderr)
            
            # Read SIZE line
            size_line = f.readline().strip()
            if size_line.startswith("SIZE"):
                json_size = int(size_line.split()[1])
                
                # Read exactly the JSON payload
                json_str = f.read(json_size)
                board = json.loads(json_str)
                
                rows = board["rows"]
                cols = board["cols"]
                weights = board["weights"]
                
                print(f"   Board size: {rows}×{cols} ({rows*cols} squares)", file=sys.stderr)
                
                # Solve!
                tour = get_tour(rows, cols, weights)
                
                if tour and len(tour) == rows * cols:
                    response = json.dumps({"tour": tour}) + "\n"
                    s.sendall(response.encode('utf-8'))
                    print(f"   ✓ Sent valid tour (length {len(tour)})", file=sys.stderr)
                else:
                    print("   ✗ Failed to find tour (should never happen)", file=sys.stderr)
                    s.sendall('{"tour": []}\n'.encode('utf-8'))
        
        elif line.startswith(("VALID", "INVALID")) or line == "TIMEOUT":
            print(f"   Server reply: {line}", file=sys.stderr)

if __name__ == "__main__":
    main()