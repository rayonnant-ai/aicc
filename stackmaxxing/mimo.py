#!/usr/bin/env python3
import sys
import socket

def parse_cells(s):
    if s.strip() == 'END':
        return None
    return [tuple(map(int, p.split(','))) for p in s.strip().split()]

def rotate_cells(cells, k):
    result = list(cells)
    for _ in range(k):
        result = [(-y, x) for x, y in result]
    mx = min(x for x, y in result)
    my = min(y for x, y in result)
    return tuple(sorted((x - mx, y - my) for x, y in result))

def unique_rotations(cells):
    seen = set()
    out = []
    for k in range(4):
        r = rotate_cells(cells, k)
        if r not in seen:
            seen.add(r)
            out.append((k, r))
    return out

def get_placements(cells, board_rows, heights, n_cols, n_rows):
    rotations = unique_rotations(cells)
    result = []

    for rot_num, rotated in rotations:
        w = max(cx for cx, cy in rotated) + 1
        max_cy = max(cy for cx, cy in rotated)

        for col in range(n_cols - w + 1):
            # Compute settle_y
            s = 0
            for cx, cy in rotated:
                s = max(s, heights[col + cx] - cy)

            # Check top bound
            if s + max_cy >= n_rows:
                continue

            # Place piece
            new_rows = board_rows[:]
            new_heights = heights[:]
            for cx, cy in rotated:
                bx = col + cx
                by = s + cy
                new_rows[by] |= (1 << bx)
                new_heights[bx] = max(new_heights[bx], by + 1)

            result.append((rot_num, col, new_rows, new_heights))

    return result

def evaluate(board_rows, heights, n_cols, n_rows):
    max_h = max(heights)
    agg_h = sum(heights)

    # Holes
    holes = 0
    for x in range(n_cols):
        h = heights[x]
        mask = 1 << x
        for y in range(h):
            if not (board_rows[y] & mask):
                holes += 1

    # Bumpiness
    bump = sum(abs(heights[i] - heights[i+1]) for i in range(n_cols - 1))

    # Wells
    wells = 0
    for i in range(n_cols):
        left = heights[i-1] if i > 0 else heights[i]
        right = heights[i+1] if i < n_cols - 1 else heights[i]
        wd = min(left, right) - heights[i]
        if wd > 0:
            wells += wd

    return -(100 * max_h + 50 * holes + 10 * bump + 5 * agg_h + 3 * wells)

def find_best_move(current_cells, next1_cells, next2_cells, n_cols, n_rows, board_rows, heights):
    placements = get_placements(current_cells, board_rows, heights, n_cols, n_rows)

    if not placements:
        return 0, 0, board_rows, heights

    # Score and sort
    scored = []
    for rot, col, nr, nh in placements:
        scored.append((evaluate(nr, nh, n_cols, n_rows), rot, col, nr, nh))
    scored.sort(reverse=True)

    if next1_cells is None:
        return scored[0][1], scored[0][2], scored[0][3], scored[0][4]

    BEAM = 12

    best_score = float('-inf')
    best_move = (scored[0][1], scored[0][2], scored[0][3], scored[0][4])

    for _, rot, col, nb1, nh1 in scored[:BEAM]:
        next_placements = get_placements(next1_cells, nb1, nh1, n_cols, n_rows)

        if not next_placements:
            s = evaluate(nb1, nh1, n_cols, n_rows) - 100000
            if s > best_score:
                best_score = s
                best_move = (rot, col, nb1, nh1)
            continue

        if next2_cells is None:
            best_next = max(evaluate(nb2, nh2, n_cols, n_rows) for _, _, nb2, nh2 in next_placements)
        else:
            scored2 = [(evaluate(nb2, nh2, n_cols, n_rows), nb2, nh2) for _, _, nb2, nh2 in next_placements]
            scored2.sort(reverse=True)

            best_next = float('-inf')
            for s2, nb2, nh2 in scored2[:BEAM]:
                n2p = get_placements(next2_cells, nb2, nh2, n_cols, n_rows)
                if not n2p:
                    best_next = max(best_next, s2 - 100000)
                else:
                    best_next = max(best_next, max(evaluate(nb3, nh3, n_cols, n_rows) for _, _, nb3, nh3 in n2p))

        if best_next > best_score:
            best_score = best_next
            best_move = (rot, col, nb1, nh1)

    return best_move

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))

    buf = b''

    def recv_line():
        nonlocal buf
        while b'\n' not in buf:
            data = sock.recv(4096)
            if not data:
                return None
            buf += data
        line, buf = buf.split(b'\n', 1)
        return line.decode('ascii').strip()

    sock.sendall(b'mimo_bot\n')

    while True:
        line = recv_line()
        if line is None:
            break
        if line == 'END':
            break

        if line.startswith('ROUND'):
            parts = line.split()
            n_cols = int(parts[2])
            n_rows = int(parts[3])
            board_rows = [0] * n_rows
            heights = [0] * n_cols

            while True:
                line = recv_line()
                if line is None or line == 'END':
                    sock.close()
                    return
                if line.startswith('ROUND_END'):
                    break
                if line.startswith('ROUND'):
                    break

                current_line = recv_line()
                next1_line = recv_line()
                next2_line = recv_line()

                current_cells = parse_cells(current_line.split(' ', 1)[1])

                n1p = next1_line.split(' ', 1)
                next1_cells = parse_cells(n1p[1]) if len(n1p) > 1 and n1p[1] != 'END' else None

                n2p = next2_line.split(' ', 1)
                next2_cells = parse_cells(n2p[1]) if len(n2p) > 1 and n2p[1] != 'END' else None

                rot, col, new_board, new_heights = find_best_move(
                    current_cells, next1_cells, next2_cells,
                    n_cols, n_rows, board_rows, heights
                )

                sock.sendall(f'{rot} {col}\n'.encode('ascii'))

                ok_line = recv_line()
                if ok_line is None:
                    sock.close()
                    return
                if ok_line.startswith('ROUND_END'):
                    break

                board_rows = new_board
                heights = new_heights

        elif line == 'END':
            break

    sock.close()

if __name__ == '__main__':
    main()