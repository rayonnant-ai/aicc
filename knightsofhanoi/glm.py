import socket
from collections import deque
import sys

def main():
    KNIGHT_MOVES = [(1,2),(2,1),(-1,2),(-2,1),(1,-2),(2,-1),(-1,-2),(-2,-1)]
    
    def bfs(start):
        dist = {start: 0}
        pred = {start: None}
        q = deque([start])
        while q:
            x, y = q.popleft()
            for dx, dy in KNIGHT_MOVES:
                nx, ny = x+dx, y+dy
                if 0 <= nx < 8 and 0 <= ny < 8 and (nx,ny) not in dist:
                    dist[(nx,ny)] = dist[(x,y)] + 1
                    pred[(nx,ny)] = (x,y)
                    q.append((nx,ny))
        return dist, pred
    
    # Precompute BFS from all squares
    all_dist = {}
    all_pred = {}
    for x in range(8):
        for y in range(8):
            d, p = bfs((x,y))
            all_dist[(x,y)] = d
            all_pred[(x,y)] = p
    
    def get_knight_path(start, end):
        if start == end:
            return []
        path = []
        cur = end
        while cur != start:
            path.append(cur)
            cur = all_pred[start][cur]
        path.append(start)
        path.reverse()
        return path
    
    def coords_to_square(c):
        return chr(ord('A') + c[0]) + str(c[1] + 1)
    
    # Choose peg squares
    PEG_COORDS = [
        (0,0),  # 0: A1 (source)
        (1,2),  # 1: B3
        (2,1),  # 2: C2
        (3,3),  # 3: D4
        (4,2),  # 4: E3
        (5,4),  # 5: F5
        (6,5),  # 6: G6
        (5,6),  # 7: F7
        (7,5),  # 8: H6
        (7,7),  # 9: H8 (destination)
    ]
    
    K = len(PEG_COORDS)
    
    # Compute pairwise knight distances between pegs
    peg_dist = [[0]*K for _ in range(K)]
    for i in range(K):
        for j in range(K):
            peg_dist[i][j] = all_dist[PEG_COORDS[i]][PEG_COORDS[j]]
    
    # DP for Frame-Stewart
    def solve(n_disks):
        memo = {}  # (n, src, dst, avail_frozenset) -> (cost, (m, p))
        
        def dp(n, src, dst, avail):
            if n == 0:
                return (0, None)
            if n == 1:
                return (peg_dist[src][dst], None)
            
            key = (n, src, dst, avail)
            if key in memo:
                return memo[key]
            
            best_cost = float('inf')
            best_choice = None
            
            aux = [p for p in avail if p != src and p != dst]
            
            for p in aux:
                for m in range(1, n):
                    c1, _ = dp(m, src, p, avail)
                    if c1 >= best_cost:
                        continue
                    new_avail = avail - frozenset([p])
                    c2, _ = dp(n-m, src, dst, new_avail)
                    if c1 + c2 >= best_cost:
                        continue
                    c3, _ = dp(m, p, dst, avail)
                    total = c1 + c2 + c3
                    if total < best_cost:
                        best_cost = total
                        best_choice = (m, p)
            
            memo[key] = (best_cost, best_choice)
            return memo[key]
        
        all_pegs = frozenset(range(K))
        cost, _ = dp(n_disks, 0, K-1, all_pegs)
        
        # Reconstruct moves
        def reconstruct(n, src, dst, avail):
            if n == 0:
                return []
            if n == 1:
                return [(src, dst)]
            _, choice = memo[(n, src, dst, avail)]
            if choice is None:
                return []
            m, p = choice
            moves1 = reconstruct(m, src, p, avail)
            new_avail = avail - frozenset([p])
            moves2 = reconstruct(n-m, src, dst, new_avail)
            moves3 = reconstruct(m, p, dst, avail)
            return moves1 + moves2 + moves3
        
        hanoi_moves = reconstruct(n_disks, 0, K-1, all_pegs)
        
        # Expand Hanoi moves to knight paths
        result = []
        for src_i, dst_i in hanoi_moves:
            path = get_knight_path(PEG_COORDS[src_i], PEG_COORDS[dst_i])
            for k in range(len(path) - 1):
                result.append(coords_to_square(path[k]) + coords_to_square(path[k+1]))
        
        return result
    
    # Connect to server
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.settimeout(15)
    
    buf = b''
    
    def read_line():
        nonlocal buf
        while b'\n' not in buf:
            data = sock.recv(4096)
            if not data:
                return None
            buf += data
        line, buf = buf.split(b'\n', 1)
        return line.decode().strip()
    
    # Register
    sock.sendall(b'glm_bot\n')
    
    while True:
        line = read_line()
        if line is None or line == 'END':
            break
        
        if line.startswith('ROUND'):
            parts = line.split()
            round_num = int(parts[1])
            n = int(parts[2])
            
            moves = solve(n)
            
            response = ','.join(moves) + '\n'
            sock.sendall(response.encode())
            
            # Read server reply
            reply = read_line()
    
    sock.close()

if __name__ == '__main__':
    main()