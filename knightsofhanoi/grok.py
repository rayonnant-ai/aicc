import socket
import sys
from collections import deque
from typing import List, Tuple, Dict

deltas = [(1,2),(1,-2),(-1,2),(-1,-2),(2,1),(2,-1),(-2,1),(-2,-1)]

def coord_to_sq(coord: Tuple[int, int]) -> str:
    x, y = coord
    return chr(ord('A') + x) + str(y + 1)

def get_knight_moves(pos: Tuple[int, int]) -> List[Tuple[int, int]]:
    x, y = pos
    res = []
    for dx, dy in deltas:
        nx, ny = x + dx, y + dy
        if 0 <= nx < 8 and 0 <= ny < 8:
            res.append((nx, ny))
    return res

def shortest_path(start: Tuple[int, int], goal: Tuple[int, int]) -> List[Tuple[int, int]]:
    if start == goal:
        return [start]
    q = deque([(start, [start])])
    visited = {start}
    while q:
        curr, path = q.popleft()
        for neigh in get_knight_moves(curr):
            if neigh not in visited:
                visited.add(neigh)
                newpath = path + [neigh]
                if neigh == goal:
                    return newpath
                q.append((neigh, newpath))
    raise ValueError("No path found")  # knight graph is connected

def move_tower(k: int, src: Tuple[int, int], dst: Tuple[int, int], memo: Dict) -> List[str]:
    key = (k, src, dst)
    if key in memo:
        return memo[key][:]
    if k == 0:
        moves = []
    elif k == 1:
        path = shortest_path(src, dst)
        moves = []
        curr = src
        for nxt in path[1:]:
            move_str = coord_to_sq(curr) + coord_to_sq(nxt)
            moves.append(move_str)
            curr = nxt
    else:
        path = shortest_path(src, dst)
        path_set = set(path)
        # Choose first available parking spot (row-major order) not on the path for this sub-tower
        parking = None
        for x in range(8):
            for y in range(8):
                p = (x, y)
                if p not in path_set:
                    parking = p
                    break
            if parking is not None:
                break
        # Recursive: park k-1, move largest disk along path, retrieve k-1
        moves1 = move_tower(k - 1, src, parking, memo)
        largest_moves = []
        curr = src
        for nxt in path[1:]:
            move_str = coord_to_sq(curr) + coord_to_sq(nxt)
            largest_moves.append(move_str)
            curr = nxt
        moves2 = move_tower(k - 1, parking, dst, memo)
        moves = moves1 + largest_moves + moves2
    memo[key] = moves
    return moves

def read_line(sock: socket.socket) -> str | None:
    line = b''
    while True:
        chunk = sock.recv(1)
        if not chunk:
            return None
        line += chunk
        if chunk == b'\n':
            return line.decode('ascii').strip()

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(('localhost', 7474))
        s.sendall(b'grok_knight_bot\n')
        memo: Dict = {}
        while True:
            line = read_line(s)
            if line is None or line == 'END':
                break
            if line.startswith('ROUND '):
                parts = line.split()
                round_num = int(parts[1])
                n = int(parts[2])
                print(f"Starting round {round_num} with n={n}", file=sys.stderr)
                start_pos = (0, 0)  # A1
                goal_pos = (7, 7)   # H8
                moves = move_tower(n, start_pos, goal_pos, memo)
                response = ','.join(moves)
                if response:
                    s.sendall((response + '\n').encode('ascii'))
                else:
                    s.sendall(b'\n')
                reply = read_line(s)
                if reply is None:
                    break
                print(f"Round {round_num} result: {reply}", file=sys.stderr)

if __name__ == "__main__":
    main()