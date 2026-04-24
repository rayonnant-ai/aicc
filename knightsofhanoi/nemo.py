import socket
import sys
from collections import deque

# Knight move offsets (dx, dy) where x = file (0=A..7=H), y = rank (0=1..8)
KNIGHT_OFFSETS = [
    (2, 1), (1, 2), (-1, 2), (-2, 1),
    (-2, -1), (-1, -2), (1, -2), (2, -1)
]

def square_to_coord(sq: str):
    """Convert 'A1'..'H8' (case‑insensitive) to (row, col) with 0‑based indices."""
    sq = sq.strip().upper()
    if len(sq) != 2 or sq[0] not in 'ABCDEFGH' or sq[1] not in '12345678':
        raise ValueError(f'Invalid square: {sq}')
    col = ord(sq[0]) - ord('A')
    row = int(sq[1]) - 1
    return (row, col)

def coord_to_square(rc):
    r, c = rc
    return chr(ord('A') + c) + str(r + 1)

def top_of_stack(stack):
    return stack[-1] if stack else None

def can_move(disk_size, src_rc, dst_rc, board):
    """Check whether moving the top disk of size `disk_size` from src to dst is legal."""
    src_stack = board[src_rc[0]][src_rc[1]]
    if not src_stack or src_stack[-1] != disk_size:
        return False  # not the top disk of that size
    dst_stack = board[dst_rc[0]][dst_rc[1]]
    if not dst_stack:
        return True   # empty square is always allowed
    return dst_stack[-1] > disk_size  # can only place on a larger disk

def locate_disk(board, size):
    """Find the square (row, col) where the top disk is `size`."""
    for r in range(8):
        for c in range(8):
            if board[r][c] and board[r][c][-1] == size:
                return (r, c)
    raise ValueError(f'Disk {size} not found on board')

def bfs_path(board, disk_size, src, goal_is_empty=False, goal_square=None):
    """
    Breadth‑first search for a sequence of squares from `src` to a goal.
    If `goal_is_empty` is True, the goal is any empty square reachable via legal moves.
    If `goal_square` is given, the goal is that specific square.
    Returns a list of squares (including start and goal) or None if no path exists.
    """
    if src == goal_square and not goal_is_empty:
        return [src]
    q = deque()
    q.append((src, [src]))
    visited = set([src])
    while q:
        cur, path = q.popleft()
        r, c = cur
        for dr, dc in KNIGHT_OFFSETS:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < 8 and 0 <= nc < 8):
                continue
            nxt = (nr, nc)
            if nxt in visited:
                continue
            # Check legality of moving the disk from cur to nxt
            if not can_move(disk_size, cur, nxt, board):
                continue
            # If we are looking for an empty square, require that nxt is empty *before* the move
            if goal_is_empty:
                if not board[nr][nc]:  # empty before move
                    return path + [nxt]
            else:
                if nxt == goal_square:
                    return path + [nxt]
            visited.add(nxt)
            q.append((nxt, path + [nxt]))
    return None

def solve_round(n):
    """
    Compute a list of moves (src, dst) to transfer `n` disks from A1 to H8.
    Returns a list of tuples like [('A1', 'C2'), ('C2', 'E3'), ...].
    """
    # Board: 8x8, each cell is a list representing a stack (bottom first, top last)
    board = [[[] for _ in range(8)] for _ in range(8)]
    # Start: all disks on A1, largest at bottom
    board[0][0] = list(range(n, 0, -1))  # e.g., n=3 -> [3,2,1]
    moves = []

    # Phase 1: Unstack – move each disk off the source to a distinct empty square.
    # Process disks from smallest to largest so we can always access the top disk.
    for disk in range(1, n + 1):
        src = locate_disk(board, disk)
        # Find any empty square reachable via legal moves.
        path = bfs_path(board, disk, src, goal_is_empty=True)
        if path is None:
            # As a fallback, try to treat any square as goal (should not happen)
            path = bfs_path(board, disk, src, goal_square=(0, 0))
            if path is None:
                raise RuntimeError(f'Failed to move disk {disk} off source')
        # Execute the path
        for i in range(len(path) - 1):
            cur = path[i]
            nxt = path[i + 1]
            moves.append((coord_to_square(cur), coord_to_square(nxt)))
            val = board[cur[0]][cur[1]].pop()
            board[nxt[0]][nxt[1]].append(val)

    # Phase 2: Stack – move disks from their current squares to H8, largest first.
    target = square_to_coord('H8')
    for disk in range(n, 0, -1):
        src = locate_disk(board, disk)
        path = bfs_path(board, disk, src, goal_square=target)
        if path is None:
            raise RuntimeError(f'Failed to move disk {disk} to target')
        for i in range(len(path) - 1):
            cur = path[i]
            nxt = path[i + 1]
            moves.append((coord_to_square(cur), coord_to_square(nxt)))
            val = board[cur[0]][cur[1]].pop()
            board[nxt[0]][nxt[1]].append(val)

    return moves

def main():
    host = 'localhost'
    port = 7474
    bot_name = 'nemotron_bot'  # follows {model_name}_bot convention
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        # Send bot name
        sock.sendall((bot_name + '\n').encode())
        buffer = ''
        while True:
            data = sock.recv(4096)
            if not data:
                break
            buffer += data.decode()
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                if not line:
                    continue
                if line.startswith('ROUND'):
                    parts = line.split()
                    if len(parts) != 3:
                        continue  # malformed, ignore
                    round_num = int(parts[1])
                    n = int(parts[2])
                    try:
                        move_list = solve_round(n)
                    except Exception:
                        move_list = []  # empty response -> INVALID
                    if move_list:
                        out = ','.join(src + dst for src, dst in move_list) + '\n'
                    else:
                        out = '\n'
                    sock.sendall(out.encode())
                    # Read server reply (VALID/INVALID/TIMEOUT) – we just consume it
                    reply = sock.recv(4096)
                    if not reply:
                        return
                elif line == 'END':
                    return
                else:
                    # Unexpected line, ignore
                    pass
    except Exception as e:
        sys.stderr.write(f'Error: {e}\n')
    finally:
        try:
            sock.close()
        except:
            pass

if __name__ == '__main__':
    main()