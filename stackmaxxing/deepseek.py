import sys
import socket

# ----------------------------------------------------------------------
#  Piece rotation and normalisation (counter‑clockwise)
# ----------------------------------------------------------------------
def rotate_cells(cells, k):
    """Apply (x,y) -> (-y,x) exactly k times, then re‑normalise once."""
    cur = set(cells)
    for _ in range(k):
        cur = {(-y, x) for x, y in cur}
    minx = min(x for x, y in cur)
    miny = min(y for x, y in cur)
    return frozenset((x - minx, y - miny) for x, y in cur)


def get_orientations(cells):
    """Return all four rotated, normalised orientations as frozensets."""
    return [rotate_cells(cells, k) for k in range(4)]


# ----------------------------------------------------------------------
#  Tank simulation
# ----------------------------------------------------------------------
def simulate_drop(board, rotated_cells, column, n_rows, n_cols):
    """
    Drop the rotated piece at the given column.
    Returns (settle_y, new_board) or None if invalid (goes out of top).
    """
    # rotated_cells is already normalised: min rx = 0, min ry = 0
    max_rx = max(x for x, y in rotated_cells)
    width = max_rx + 1
    if column < 0 or column + width > n_cols:
        return None

    # simulate falling from above the tank
    y = n_rows                     # one row above the visible top
    while True:
        y_next = y - 1
        if y_next < 0:
            break                  # floor prevents further falling
        # would any cell collide after one step down?
        collision = False
        for rx, ry in rotated_cells:
            ay = y_next + ry
            ax = column + rx
            if ay < 0:            # below floor
                collision = True
                break
            if ay < n_rows and board[ay][ax]:
                collision = True
                break
        if collision:
            break
        y = y_next

    # final check: any cell out of the top?
    for rx, ry in rotated_cells:
        if y + ry >= n_rows:
            return None

    # build new board
    new_board = [row[:] for row in board]
    for rx, ry in rotated_cells:
        ay = y + ry
        ax = column + rx
        new_board[ay][ax] = True
    return y, new_board


# ----------------------------------------------------------------------
#  Board evaluation (heuristic)
# ----------------------------------------------------------------------
def evaluate(board, n_rows, n_cols):
    """Return a cost (lower is better)."""
    heights = []
    hole_count = 0

    for x in range(n_cols):
        # highest filled cell in this column
        h = -1
        for y in range(n_rows):
            if board[y][x]:
                h = y
        heights.append(h)

        if h >= 0:
            # count empty cells below the highest filled cell  => holes
            for y in range(h):
                if not board[y][x]:
                    hole_count += 1

    # effective surface height (0 if column empty)
    eff = [h + 1 if h >= 0 else 0 for h in heights]
    max_height = max(eff) if eff else 0
    bumpiness = sum(abs(eff[i] - eff[i+1]) for i in range(n_cols-1))
    sum_eff = sum(eff)

    # holes are catastrophic – give them huge weight
    return hole_count * 1000 + max_height * 10 + sum_eff + bumpiness * 5


# ----------------------------------------------------------------------
#  Move generation
# ----------------------------------------------------------------------
def get_valid_placements(board, piece_cells, n_cols, n_rows, orient_cache):
    """Return list of (rotation, column, new_board) for all legal drops."""
    key = frozenset(piece_cells)
    if key not in orient_cache:
        orient_cache[key] = get_orientations(piece_cells)
    ori_list = orient_cache[key]

    placements = []
    for rot, ori in enumerate(ori_list):
        max_rx = max(x for x, y in ori)
        width = max_rx + 1
        for col in range(0, n_cols - width + 1):
            res = simulate_drop(board, ori, col, n_rows, n_cols)
            if res is not None:
                _, new_board = res
                placements.append((rot, col, new_board))
    return placements


# ----------------------------------------------------------------------
#  Look‑ahead search (max depth = current + 1 upcoming piece)
# ----------------------------------------------------------------------
MAX_LOOKAHEAD_NEXT = 1          # only look at the first NEXT piece

def value(board, pieces, n_cols, n_rows, orient_cache):
    """
    Recursive value of a state given a sequence of *future* pieces.
    Returns a score (higher = better).  100000 bonus per piece placed.
    """
    if not pieces:
        return -evaluate(board, n_rows, n_cols)

    current_piece = pieces[0]
    placements = get_valid_placements(board, current_piece,
                                      n_cols, n_rows, orient_cache)
    if not placements:                     # can't place this piece → round ends
        return -evaluate(board, n_rows, n_cols)

    best = -float('inf')
    for _, _, new_board in placements:
        rest = value(new_board, pieces[1:], n_cols, n_rows, orient_cache)
        best = max(best, 100_000 + rest)
    return best


def choose_move(board, current_piece, next_pieces, n_cols, n_rows, orient_cache):
    """Return (rotation, column) for the current piece."""
    placements = get_valid_placements(board, current_piece,
                                      n_cols, n_rows, orient_cache)
    if not placements:
        # No legal drop – send something invalid to end the round gracefully
        return 0, 0

    # Restrict look‑ahead depth
    look_ahead = next_pieces[:MAX_LOOKAHEAD_NEXT]

    best_val = -float('inf')
    best_move = (0, 0)
    for rot, col, new_board in placements:
        rest = value(new_board, look_ahead, n_cols, n_rows, orient_cache)
        total = 100_000 + rest
        if total > best_val:
            best_val = total
            best_move = (rot, col)
    return best_move


# ----------------------------------------------------------------------
#  Wire protocol helpers
# ----------------------------------------------------------------------
def parse_cells(s):
    """Parse a cell list string like '0,0 1,0 2,0' into a set of tuples."""
    if s == "END":
        return None
    cells = set()
    for token in s.split():
        x, y = token.split(',')
        cells.add((int(x), int(y)))
    return cells


def main():
    sock = socket.create_connection(('localhost', 7474))
    # registration
    sock.sendall(b"deepseek_StackMaxxingBot\n")

    buf = b''
    orient_cache = {}
    board = []
    n_cols = n_rows = 0

    # state machine
    reading_piece = False
    piece_lines = []
    pending_new_board = None   # board that will become current after "OK"

    while True:
        data = sock.recv(4096)
        if not data:
            break
        buf += data
        while b'\n' in buf:
            line_bytes, buf = buf.split(b'\n', 1)
            line = line_bytes.decode('ascii').strip()
            if not line:
                continue

            # --- ROUND start ---
            if line.startswith("ROUND "):
                parts = line.split()
                n_cols = int(parts[2])
                n_rows = int(parts[3])
                board = [[False] * n_cols for _ in range(n_rows)]
                reading_piece = False
                piece_lines = []
                pending_new_board = None

            # --- Begin of a PIECE block ---
            elif line == "PIECE":
                reading_piece = True
                piece_lines = [line]

            # --- Collect lines inside a PIECE block ---
            elif reading_piece:
                piece_lines.append(line)
                if len(piece_lines) == 4:          # PIECE + 3 data lines
                    reading_piece = False
                    # parse the block
                    cur_line = piece_lines[1]
                    n1_line  = piece_lines[2]
                    n2_line  = piece_lines[3]

                    cur_cells = parse_cells(cur_line.split(" ", 1)[1])
                    next1 = parse_cells(n1_line.split(" ", 1)[1]) if n1_line.startswith("NEXT ") else None
                    next2 = parse_cells(n2_line.split(" ", 1)[1]) if n2_line.startswith("NEXT ") else None

                    next_list = [p for p in (next1, next2) if p is not None]

                    # choose best move
                    rot, col = choose_move(board, cur_cells, next_list,
                                           n_cols, n_rows, orient_cache)

                    # simulate locally to obtain the new board that we *expect*
                    ori = get_orientations(cur_cells)[rot]
                    drop_res = simulate_drop(board, ori, col, n_rows, n_cols)
                    if drop_res is not None:
                        _, pending_new_board = drop_res
                    else:
                        pending_new_board = board    # fallback (shouldn't happen)

                    # send response
                    sock.sendall(f"{rot} {col}\n".encode())

            # --- Successful placement ack ---
            elif line.startswith("OK "):
                if pending_new_board is not None:
                    board = pending_new_board
                    pending_new_board = None

            # --- Round ended ---
            elif line.startswith("ROUND_END "):
                board = []
                pending_new_board = None

            # --- Tournament finished ---
            elif line == "END":
                sock.close()
                return

            # Ignore any other lines (should not appear)

    # EOF before END – clean exit
    sock.close()


if __name__ == "__main__":
    main()