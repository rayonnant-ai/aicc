import socket
import sys
from typing import List, Tuple, Optional

Cell = Tuple[int, int]

def parse_cells(s: str) -> List[Cell]:
    if not s or s == "END":
        return []
    cells = []
    for p in s.split():
        if ',' in p:
            x_str, y_str = p.split(',')
            cells.append((int(x_str), int(y_str)))
    return cells

def rotate_once(cells: List[Cell]) -> List[Cell]:
    return [(-y, x) for x, y in cells]

def normalize(cells: List[Cell]) -> List[Cell]:
    if not cells:
        return []
    min_x = min(x for x, y in cells)
    min_y = min(y for x, y in cells)
    normalized = [(x - min_x, y - min_y) for x, y in cells]
    return sorted(set(normalized))

def rotate_piece(base: List[Cell], k: int) -> List[Cell]:
    rotated = base[:]
    for _ in range(k % 4):
        rotated = rotate_once(rotated)
    return normalize(rotated)

def get_width(piece: List[Cell]) -> int:
    if not piece:
        return 0
    return max((x for x, y in piece), default=0) + 1

def compute_settle_y(heights: List[int], rot_piece: List[Cell], col: int) -> Optional[int]:
    if not rot_piece:
        return 0
    max_req = float('-inf')
    for rx, ry in rot_piece:
        c = col + rx
        if not (0 <= c < len(heights)):
            return None
        h = heights[c]
        req = h + 1 - ry
        max_req = max(max_req, req)
    settle_y = max(0, int(max_req))
    return settle_y

def get_placement_score(heights: List[int], n_rows: int, piece: List[Cell], n_cols: int) -> float:
    if not piece:
        m = max(heights) if heights and max(heights) >= 0 else -1
        return -m
    best = -float('inf')
    for rot in range(4):
        rp = rotate_piece(piece, rot)
        w = get_width(rp)
        for c in range(n_cols - w + 1):
            settle = compute_settle_y(heights, rp, c)
            if settle is None:
                continue
            valid = True
            new_max = max(heights) if max(heights) >= 0 else -1
            for rx, ry in rp:
                py = settle + ry
                if py >= n_rows:
                    valid = False
                    break
                new_max = max(new_max, py)
            if valid:
                score = -new_max
                best = max(best, score)
    return best if best > -float('inf') else -1e9

def main():
    name = "grok_bot"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(('localhost', 7474))
        s.sendall(f"{name}\n".encode('ascii'))
        file = s.makefile("r", encoding="ascii")
        while True:
            line = file.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith("ROUND "):
                parts = line.split()
                round_num = int(parts[1])
                n_cols = int(parts[2])
                n_rows = int(parts[3])
                print(f"Round {round_num}: {n_cols}x{n_rows}", file=sys.stderr)
                heights: List[int] = [-1] * n_cols
                while True:
                    p_line = file.readline().strip()
                    if p_line.startswith("ROUND_END") or p_line == "END":
                        if p_line == "END":
                            print("Tournament ended.", file=sys.stderr)
                            return
                        print("Round ended:", p_line, file=sys.stderr)
                        break
                    if p_line != "PIECE":
                        continue
                    curr_line = file.readline().strip()
                    current_str = curr_line[8:] if curr_line.startswith("CURRENT ") else ""
                    current_cells = parse_cells(current_str)
                    next1_line = file.readline().strip()
                    next1_str = next1_line[5:] if next1_line.startswith("NEXT ") else ""
                    next1_cells = parse_cells(next1_str) if next1_str != "END" else []
                    next2_line = file.readline().strip()
                    next2_str = next2_line[5:] if next2_line.startswith("NEXT ") else ""
                    next2_cells = parse_cells(next2_str) if next2_str != "END" else []
                    # Choose best current placement using 1-step lookahead on NEXT1
                    best_score = -float('inf')
                    best_rot = 0
                    best_col = 0
                    best_settle_y = 0
                    for rot in range(4):
                        rot_p = rotate_piece(current_cells, rot)
                        w = get_width(rot_p)
                        for c in range(n_cols - w + 1):
                            settle = compute_settle_y(heights, rot_p, c)
                            if settle is None:
                                continue
                            valid = True
                            temp_heights = heights[:]
                            new_max = max(heights) if max(heights) >= 0 else -1
                            for rx, ry in rot_p:
                                px = c + rx
                                py = settle + ry
                                if py >= n_rows:
                                    valid = False
                                    break
                                temp_heights[px] = max(temp_heights[px], py)
                                new_max = max(new_max, py)
                            if not valid:
                                continue
                            if next1_cells:
                                lookahead_score = get_placement_score(temp_heights, n_rows, next1_cells, n_cols)
                            else:
                                lookahead_score = -new_max
                            if lookahead_score > best_score:
                                best_score = lookahead_score
                                best_rot = rot
                                best_col = c
                                best_settle_y = settle
                    s.sendall(f"{best_rot} {best_col}\n".encode('ascii'))
                    resp = file.readline().strip()
                    if resp.startswith("OK "):
                        # commit to board
                        rot_p = rotate_piece(current_cells, best_rot)
                        for rx, ry in rot_p:
                            px = best_col + rx
                            py = best_settle_y + ry
                            heights[px] = max(heights[px], py)
                    elif resp.startswith("ROUND_END"):
                        print("Round ended:", resp, file=sys.stderr)
                        break
            elif line == "END":
                print("End of tournament.", file=sys.stderr)
                break

if __name__ == "__main__":
    main()