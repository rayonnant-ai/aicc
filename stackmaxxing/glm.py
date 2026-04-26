#!/usr/bin/env python3
import socket


class Tank:
    def __init__(self, n_cols, n_rows):
        self.n_cols = n_cols
        self.n_rows = n_rows
        self.grid = [[False] * n_rows for _ in range(n_cols)]
        self._heights = [0] * n_cols

    def copy(self):
        t = Tank(self.n_cols, self.n_rows)
        for x in range(self.n_cols):
            t.grid[x] = self.grid[x][:]
        t._heights = self._heights[:]
        return t

    def occupy(self, x, y):
        self.grid[x][y] = True
        if y + 1 > self._heights[x]:
            self._heights[x] = y + 1

    def get_height(self, col):
        return self._heights[col]


def rotate_piece(cells, rotation):
    result = list(cells)
    for _ in range(rotation):
        result = [(-y, x) for (x, y) in result]
    min_x = min(x for x, y in result)
    min_y = min(y for x, y in result)
    return [(x - min_x, y - min_y) for x, y in result]


def compute_settle_y(tank, rotated_cells, column):
    min_settle = 0
    for rx, ry in rotated_cells:
        bx = column + rx
        if 0 <= bx < tank.n_cols:
            cell_min = tank.get_height(bx) - ry
            if cell_min > min_settle:
                min_settle = cell_min
    return min_settle


def is_valid_placement(tank, rotated_cells, column):
    if not rotated_cells:
        return None
    w = max(x for x, y in rotated_cells) + 1
    if column < 0 or column + w > tank.n_cols:
        return None
    settle_y = compute_settle_y(tank, rotated_cells, column)
    for rx, ry in rotated_cells:
        bx, by = column + rx, settle_y + ry
        if by >= tank.n_rows:
            return None
        if 0 <= bx < tank.n_cols and 0 <= by < tank.n_rows and tank.grid[bx][by]:
            return None
    return settle_y


def place_piece(tank, rotated_cells, column, settle_y):
    for rx, ry in rotated_cells:
        tank.occupy(column + rx, settle_y + ry)


def count_holes(tank):
    holes = 0
    for x in range(tank.n_cols):
        found = False
        for y in range(tank.n_rows - 1, -1, -1):
            if tank.grid[x][y]:
                found = True
            elif found:
                holes += 1
    return holes


def evaluate(tank):
    holes = count_holes(tank)
    heights = tank._heights
    roughness = sum(abs(heights[i] - heights[i + 1]) for i in range(len(heights) - 1))
    max_height = max(heights)
    return holes * 100 + roughness * 5 + max_height * 3


def can_piece_fit(tank, cells):
    for rot in range(4):
        rotated = rotate_piece(cells, rot)
        w = max(x for x, y in rotated) + 1
        if w > tank.n_cols:
            continue
        for col in range(tank.n_cols - w + 1):
            if is_valid_placement(tank, rotated, col) is not None:
                return True
    return False


def find_best_placement(tank, current_cells, next_cells=None):
    best_score = float('inf')
    best_rot = best_col = best_sy = 0
    found = False
    for rot in range(4):
        rotated = rotate_piece(current_cells, rot)
        w = max(x for x, y in rotated) + 1
        if w > tank.n_cols:
            continue
        for col in range(tank.n_cols - w + 1):
            sy = is_valid_placement(tank, rotated, col)
            if sy is None:
                continue
            found = True
            temp = tank.copy()
            place_piece(temp, rotated, col, sy)
            score = evaluate(temp)
            if next_cells is not None and not can_piece_fit(temp, next_cells):
                score += 10000
            if score < best_score:
                best_score, best_rot, best_col, best_sy = score, rot, col, sy
    return (best_rot, best_col, best_sy) if found else None


def parse_cells(s):
    if s == "END":
        return None
    return [tuple(int(v) for v in p.split(',')) for p in s.split()]


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall(b"glm_stackmax_bot\n")
    buf = ""

    def readline():
        nonlocal buf
        while '\n' not in buf:
            data = sock.recv(4096)
            if not data:
                return None
            buf += data.decode()
        line, buf = buf.split('\n', 1)
        return line

    tank = None
    while True:
        line = readline()
        if line is None:
            break
        if line.startswith("ROUND"):
            parts = line.split()
            tank = Tank(int(parts[2]), int(parts[3]))
        elif line == "PIECE":
            cur_line = readline()
            cur_cells = parse_cells(cur_line.split(' ', 1)[1])
            n1_line = readline()
            n1_parts = n1_line.split(' ', 1)
            n1_cells = parse_cells(n1_parts[1]) if len(n1_parts) > 1 and n1_parts[1] != "END" else None
            readline()  # NEXT2 unused
            result = find_best_placement(tank, cur_cells, n1_cells)
            if result is None:
                rot, col = 0, 0
            else:
                rot, col, sy = result
                place_piece(tank, rotate_piece(cur_cells, rot), col, sy)
            sock.sendall(f"{rot} {col}\n".encode())
        elif line == "END":
            break
    sock.close()


if __name__ == "__main__":
    main()