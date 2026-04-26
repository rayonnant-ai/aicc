import socket
import sys

HOST = "localhost"
PORT = 7474


# ---------------------------
# Geometry helpers
# ---------------------------

def rotate(cells, k):
    pts = cells
    for _ in range(k):
        pts = [(-y, x) for x, y in pts]
    min_x = min(x for x, y in pts)
    min_y = min(y for x, y in pts)
    return [(x - min_x, y - min_y) for x, y in pts]


def width(cells):
    return max(x for x, _ in cells) + 1


# ---------------------------
# Simulation
# ---------------------------

def drop(board, n_cols, n_rows, cells, col):
    # find settle_y
    y = 0
    while True:
        collision = False
        for x, cy in cells:
            bx = col + x
            by = y + cy
            if by < 0:
                collision = True
                break
            if (bx, by) in board:
                collision = True
                break
        if collision:
            break
        y += 1

    settle_y = y - 1

    # check validity
    for x, cy in cells:
        bx = col + x
        by = settle_y + cy
        if by >= n_rows:
            return None

    # apply
    new_board = set(board)
    for x, cy in cells:
        new_board.add((col + x, settle_y + cy))

    return new_board


# ---------------------------
# Heuristic
# ---------------------------

def evaluate(board, n_cols):
    heights = [0] * n_cols

    for x, y in board:
        heights[x] = max(heights[x], y + 1)

    max_h = max(heights)

    # variance
    avg = sum(heights) / n_cols
    var = sum((h - avg) ** 2 for h in heights) / n_cols

    # bumpiness
    bump = sum(abs(heights[i] - heights[i+1]) for i in range(n_cols - 1))

    # holes
    holes = 0
    filled = set(board)
    for x in range(n_cols):
        col_cells = [y for (cx, y) in filled if cx == x]
        if not col_cells:
            continue
        top = max(col_cells)
        for y in range(top):
            if (x, y) not in filled:
                holes += 1

    return (
        5 * max_h +
        2 * var +
        3 * holes +
        1 * bump
    )


# ---------------------------
# Decision
# ---------------------------

def choose_move(board, n_cols, n_rows, piece):
    best = None
    best_move = (0, 0)

    for r in range(4):
        rot = rotate(piece, r)
        w = width(rot)

        for col in range(n_cols - w + 1):
            new_board = drop(board, n_cols, n_rows, rot, col)
            if new_board is None:
                continue

            score = evaluate(new_board, n_cols)

            if best is None or score < best:
                best = score
                best_move = (r, col)

    return best_move


# ---------------------------
# Parsing
# ---------------------------

def parse_cells(line):
    parts = line.split()[1:]
    cells = []
    for p in parts:
        x, y = map(int, p.split(","))
        cells.append((x, y))
    return cells


# ---------------------------
# Client loop
# ---------------------------

def main():
    s = socket.socket()
    s.connect((HOST, PORT))
    f = s.makefile()

    s.sendall(b"chatgpt_stackmaxxing_bot\n")

    board = set()
    n_cols = n_rows = 0

    while True:
        line = f.readline()
        if not line:
            break

        line = line.strip()

        if line.startswith("ROUND"):
            _, _, n_cols, n_rows = line.split()
            n_cols = int(n_cols)
            n_rows = int(n_rows)
            board = set()

        elif line == "PIECE":
            current = parse_cells(f.readline().strip())
            f.readline()
            f.readline()

            r, col = choose_move(board, n_cols, n_rows, current)

            s.sendall(f"{r} {col}\n".encode())

            reply = f.readline().strip()

            if reply.startswith("OK"):
                rot = rotate(current, r)
                board = drop(board, n_cols, n_rows, rot, col)
            else:
                board = set()

        elif line.startswith("ROUND_END"):
            board = set()

        elif line == "END":
            break


if __name__ == "__main__":
    main()