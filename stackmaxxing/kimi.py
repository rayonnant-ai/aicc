#!/usr/bin/env python3
import socket
import sys
from functools import lru_cache

# ----------------------------------------------------------------------
# Piece geometry
# ----------------------------------------------------------------------

@lru_cache(maxsize=None)
def rotate_piece(cells, k):
    """Rotate counter-clockwise k*90°, normalizing once at the end."""
    cells = list(cells)
    for _ in range(k):
        cells = [(-y, x) for x, y in cells]
    min_x = min(x for x, y in cells)
    min_y = min(y for x, y in cells)
    return tuple(sorted((x - min_x, y - min_y) for x, y in cells))


def get_width(cells):
    return max((x for x, y in cells), default=0) + 1


def get_height(cells):
    return max((y for x, y in cells), default=0) + 1


@lru_cache(maxsize=None)
def get_unique_rotations(cells):
    """Return {rotation_id: rotated_cells} with duplicates removed."""
    seen = set()
    result = {}
    for k in range(4):
        rot = rotate_piece(cells, k)
        if rot not in seen:
            seen.add(rot)
            result[k] = rot
    return result


# ----------------------------------------------------------------------
# Tank simulation
# ----------------------------------------------------------------------

def simulate_drop(board, cells, col, n_rows, n_cols):
    """Return settle_y or None if placement is invalid."""
    w = get_width(cells)
    if col < 0 or col + w > n_cols:
        return None

    forbidden = set()
    for rx, ry in cells:
        x = col + rx
        for y_occ in board[x]:
            forbidden.add(y_occ - ry)

    settle_y = 0
    while settle_y in forbidden:
        settle_y += 1

    h = get_height(cells)
    if settle_y + h > n_rows:
        return None
    return settle_y


def place_piece(board, cells, col, settle_y):
    """Return a new board state after committing the piece."""
    new_board = [set(s) for s in board]
    for rx, ry in cells:
        x = col + rx
        y = settle_y + ry
        new_board[x].add(y)
    return new_board


def evaluate_board(board, n_cols):
    """Return (max_height, total_height, bumpiness). Lower is better."""
    heights = [max(col) + 1 if col else 0 for col in board]
    max_h = max(heights) if heights else 0
    total_h = sum(heights)
    bumpiness = sum(abs(heights[i] - heights[i + 1]) for i in range(n_cols - 1))
    return max_h, total_h, bumpiness


def has_valid_placement(board, cells, n_cols, n_rows):
    """Quick check whether *any* rotation/column fits on this board."""
    seen = set()
    for k in range(4):
        rot = rotate_piece(cells, k)
        if rot in seen:
            continue
        seen.add(rot)
        w = get_width(rot)
        if w > n_cols:
            continue
        for col in range(n_cols - w + 1):
            if simulate_drop(board, rot, col, n_rows, n_cols) is not None:
                return True
    return False


# ----------------------------------------------------------------------
# Move selection
# ----------------------------------------------------------------------

def choose_move(board, current_cells, next_list, n_cols, n_rows):
    """Pick the best (rotation, column) for CURRENT."""
    current_rots = get_unique_rotations(current_cells)
    next_rots = []
    for nxt in next_list:
        if nxt is None:
            next_rots.append(None)
        else:
            next_rots.append(get_unique_rotations(nxt))

    best_score = None
    best_move = (0, 0)

    for rot, cells in current_rots.items():
        w = get_width(cells)
        if w > n_cols:
            continue
        for col in range(n_cols - w + 1):
            settle_y = simulate_drop(board, cells, col, n_rows, n_cols)
            if settle_y is None:
                continue

            new_board = place_piece(board, cells, col, settle_y)
            max_h, total_h, bumpiness = evaluate_board(new_board, n_cols)

            # Primary goal: keep the board low and flat
            score = -10000 * max_h - 100 * total_h - bumpiness

            # Look-ahead: heavily penalize blocking the next piece(s)
            for nxt_rot in next_rots:
                if nxt_rot is not None:
                    if not has_valid_placement(new_board, list(nxt_rot.values())[0], n_cols, n_rows):
                        # We use the first unique rotation shape for the quick check;
                        # if even one shape is blocked we still need to check all.
                        # Simpler: just test all unique rotations.
                        any_valid = False
                        for n_cells in nxt_rot.values():
                            if has_valid_placement(new_board, n_cells, n_cols, n_rows):
                                any_valid = True
                                break
                        if not any_valid:
                            score -= 500000
                    else:
                        # Small bonus for keeping options open
                        score += 5

            if best_score is None or score > best_score:
                best_score = score
                best_move = (rot, col)

    return best_move


# ----------------------------------------------------------------------
# Protocol helpers
# ----------------------------------------------------------------------

def parse_cells(s):
    cells = []
    for token in s.strip().split():
        if ',' in token:
            x, y = token.split(',')
            cells.append((int(x), int(y)))
    return tuple(sorted(cells))


def read_line(sock, buf_ref):
    buf = buf_ref[0]
    while b'\n' not in buf:
        data = sock.recv(4096)
        if not data:
            return None
        buf += data
    line, buf = buf.split(b'\n', 1)
    buf_ref[0] = buf
    return line.decode()


# ----------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------

def main():
    bot_name = sys.argv[1] + '_bot' if len(sys.argv) > 1 else 'kimi_stackmaxxer_bot'

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.connect(('localhost', 7474))
    sock.sendall((bot_name + '\n').encode())

    buffer = [b'']
    board = None
    n_cols = n_rows = 0
    pending_move = None  # (cells, col, settle_y)

    while True:
        line = read_line(sock, buffer)
        if line is None:
            break

        if line.startswith('ROUND'):
            parts = line.split()
            n_cols = int(parts[2])
            n_rows = int(parts[3])
            board = [set() for _ in range(n_cols)]
            pending_move = None

        elif line == 'PIECE':
            current_line = read_line(sock, buffer)
            next1_line = read_line(sock, buffer)
            next2_line = read_line(sock, buffer)

            current_cells = parse_cells(current_line.split(' ', 1)[1])

            next1 = (parse_cells(next1_line.split(' ', 1)[1])
                     if not next1_line.endswith('END') else None)
            next2 = (parse_cells(next2_line.split(' ', 1)[1])
                     if not next2_line.endswith('END') else None)

            rot, col = choose_move(board, current_cells, [next1, next2], n_cols, n_rows)
            response = f'{rot} {col}\n'
            sock.sendall(response.encode())

            # Remember what we sent so we can update our model on OK
            rot_cells = rotate_piece(current_cells, rot)
            settle_y = simulate_drop(board, rot_cells, col, n_rows, n_cols)
            pending_move = (rot_cells, col, settle_y)

        elif line.startswith('OK'):
            parts = line.split()
            bottom_y = int(parts[1])
            if pending_move is not None:
                cells, col, _ = pending_move
                # Trust the server's bottom_y as the authoritative settle row
                board = place_piece(board, cells, col, bottom_y)
                pending_move = None

        elif line.startswith('ROUND_END'):
            pending_move = None
            # Nothing else to do; next iteration will read ROUND or END

        elif line == 'END':
            break


if __name__ == '__main__':
    main()