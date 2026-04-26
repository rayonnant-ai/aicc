#!/usr/bin/env python3
import socket
import sys
import time

# --- Game Logic & Simulation ---

def parse_piece(tokens):
    """Parse string tokens 'x,y' into a list of (x,y) tuples."""
    if not tokens or tokens[0] == "END":
        return None
    cells = []
    for t in tokens:
        x, y = map(int, t.split(','))
        cells.append((x, y))
    return cells

def rotate_and_normalize(cells, k):
    """Rotates piece k times CCW and normalizes so min_x=0, min_y=0."""
    res = []
    for x, y in cells:
        for _ in range(k):
            x, y = -y, x
        res.append((x, y))
    
    min_x = min(r[0] for r in res)
    min_y = min(r[1] for r in res)
    
    return frozenset((x - min_x, y - min_y) for x, y in res)

def get_piece_masks(rotated_cells):
    """Converts a normalized piece into a dictionary of {y_offset: bitmask}."""
    masks = {}
    for x, y in rotated_cells:
        masks[y] = masks.get(y, 0) | (1 << x)
    return masks

def collides(board, shifted_masks, settle_y):
    """Checks if the piece intersects with the floor or existing blocks."""
    for ry, mask in shifted_masks.items():
        y = settle_y + ry
        if y < 0:
            return True
        if y < len(board) and (board[y] & mask):
            return True
    return False

def simulate_drop(board, rotated_cells, col, n_rows):
    """Simulates a vertical drop, returning the settle_y or None if invalid."""
    masks = get_piece_masks(rotated_cells)
    shifted_masks = {ry: (mask << col) for ry, mask in masks.items()}

    y = n_rows
    # Drop down until collision
    while y > 0:
        if collides(board, shifted_masks, y - 1):
            break
        y -= 1

    # Check top boundary out-of-bounds
    for ry in shifted_masks:
        if y + ry >= n_rows:
            return None

    return y

def evaluate(board, n_cols, n_rows):
    """Heuristic evaluation: penalize high max height, holes, and bumpiness."""
    col_heights = [0] * n_cols
    holes = 0

    for x in range(n_cols):
        mask = 1 << x
        h = 0
        for y in range(n_rows - 1, -1, -1):
            if board[y] & mask:
                if h == 0:
                    h = y + 1  # Record highest block in column
            elif h > 0:
                holes += 1     # Empty cell with a block above it
        col_heights[x] = h

    max_h = max(col_heights)
    bump = sum(abs(col_heights[i] - col_heights[i+1]) for i in range(n_cols - 1))

    # Weightings: Holes are heavily penalized, max height keeps it flat, bumpiness prevents deep wells
    return - (5 * max_h + 10 * holes + 1 * bump)

def get_valid_moves(cells, n_cols):
    """Generates all unique valid (rotation, column) combinations."""
    unique_moves = {}
    for rot in range(4):
        rotated = rotate_and_normalize(cells, rot)
        w = max(x for x, y in rotated) + 1
        for col in range(n_cols - w + 1):
            key = (rotated, col)
            if key not in unique_moves:
                unique_moves[key] = (rot, col, rotated)
    return list(unique_moves.values())

# --- Search Algorithm ---

def get_best_move(board, current_piece, next_piece_1, n_cols, n_rows):
    """Finds the best move using a 1-ply or 2-ply search depending on look-ahead."""
    best_score = -1e9
    best_move = (0, 0)

    current_moves = get_valid_moves(current_piece, n_cols)
    if not current_moves:
        return 0, 0  # No valid moves left

    for rot, col, rotated in current_moves:
        settle_y = simulate_drop(board, rotated, col, n_rows)
        if settle_y is None:
            continue

        # Create hypothetical board
        new_board = list(board)
        masks = get_piece_masks(rotated)
        for ry, mask in masks.items():
            new_board[settle_y + ry] |= (mask << col)

        # 1-Ply mode (Fallback if time is tight or NEXT is END)
        if next_piece_1 is None:
            score = evaluate(new_board, n_cols, n_rows)
            
        # 2-Ply mode (Look ahead to NEXT piece)
        else:
            next_moves = get_valid_moves(next_piece_1, n_cols)
            max_next = -1e9
            for n_rot, n_col, n_rotated in next_moves:
                n_settle_y = simulate_drop(new_board, n_rotated, n_col, n_rows)
                if n_settle_y is None:
                    continue
                nn_board = list(new_board)
                n_masks = get_piece_masks(n_rotated)
                for n_ry, n_mask in n_masks.items():
                    nn_board[n_settle_y + n_ry] |= (n_mask << n_col)

                score = evaluate(nn_board, n_cols, n_rows)
                if score > max_next:
                    max_next = score

            if max_next == -1e9:
                # Heavy penalty if this move makes placing the next piece impossible
                score = evaluate(new_board, n_cols, n_rows) - 100000 
            else:
                score = max_next

        if score > best_score:
            best_score = score
            best_move = (rot, col)

    return best_move

# --- Network & Control Loop ---

def main():
    HOST = 'localhost'
    PORT = 7474

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))
        f = sock.makefile('r', encoding='ascii')
    except ConnectionRefusedError:
        print("Connection refused. Is the StackMaxxing server running?", file=sys.stderr)
        return

    # Registration
    sock.sendall(b"gemini_StackMaxxing_bot\n")

    board = []
    n_cols = n_rows = 0
    last_move = None
    time_used = 0.0

    while True:
        line = f.readline()
        if not line:
            break
        
        parts = line.strip().split()
        if not parts:
            continue

        cmd = parts[0]
        
        if cmd == "ROUND":
            n_cols = int(parts[2])
            n_rows = int(parts[3])
            # Board is represented as a list of integers (bitmasks) for blazing fast row ops
            board = [0] * n_rows
            time_used = 0.0

        elif cmd == "PIECE":
            t0 = time.time()
            cur_line = f.readline().strip().split()
            n1_line = f.readline().strip().split()
            n2_line = f.readline().strip().split()

            cur = parse_piece(cur_line[1:])
            n1 = parse_piece(n1_line[1:])

            # Safety trigger: disable 2-ply search if we've consumed >7.5s this round
            use_2ply = (time_used < 7.5)
            
            best_rot, best_col = get_best_move(board, cur, n1 if use_2ply else None, n_cols, n_rows)
            last_move = (cur, best_rot, best_col)
            
            # Send exactly in compliance with server strict parsing
            sock.sendall(f"{best_rot} {best_col}\n".encode('ascii'))
            
            # Tally compute time just like the server stopwatch does
            time_used += (time.time() - t0)

        elif cmd == "OK":
            # State Update: Server accepts placement, sync board using server's ground-truth bottom_y
            bottom_y = int(parts[1])
            cur, rot, col = last_move
            rotated = rotate_and_normalize(cur, rot)
            masks = get_piece_masks(rotated)
            
            for ry, mask in masks.items():
                board[bottom_y + ry] |= (mask << col)

        elif cmd == "ROUND_END":
            # Wait for next round init (board resets upon `ROUND`)
            pass

        elif cmd == "END":
            # Tournament complete
            break

    sock.close()

if __name__ == "__main__":
    main()