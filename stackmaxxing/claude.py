#!/usr/bin/env python3
"""
StackMaxxing bot — Day 11 Challenge.

Strategy:
- Maintain authoritative tank state by simulating each accepted move with the
  exact server algorithm (Section 5).
- For each piece, enumerate all (rotation, column) placements that fit.
- With 3-piece lookahead (CURRENT + 2 NEXT), do a depth-limited beam search:
  evaluate the resulting board with a Dellacherie-style heuristic, and pick
  the CURRENT move that maximizes the best achievable lookahead score.
- Heuristic rewards: low landing rows, full rows (we don't clear, but rows
  that are dense are good); penalizes: holes (empty cells with filled cells
  above), aggregate height, bumpiness (column-to-column height variance),
  wells (deep narrow gaps), max height.
"""

import socket
import sys
import time
from typing import List, Tuple, Optional, FrozenSet

MODEL_NAME = "claude_opus_4_7"  # bot identifier
HOST = "localhost"
PORT = 7474

# Heuristic weights (tuned roughly; well-known Tetris weight families).
# y=0 is floor, y increases upward. We want pieces to land low (small bottom_y),
# minimize holes, minimize bumpiness, minimize max height.
W_LANDING = -2.0      # bottom_y of placement (penalize landing high)
W_HOLES = -7.5        # number of empty cells with filled cell above in same column
W_BUMPINESS = -1.2    # sum of |h[i]-h[i+1]|
W_MAX_HEIGHT = -1.0   # max column height
W_AGG_HEIGHT = -0.6   # sum of column heights
W_WELLS = -1.5        # sum of (depth of each well; well = column lower than both neighbors)
W_ROW_FILL = +5.0     # density of active region (heights occupancy fraction)
W_DEATH = -1e9        # cannot place — extremely bad


# -------------------- Protocol IO --------------------

class LineReader:
    """Buffered line reader over a socket — handles TCP fragmentation."""
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = b""

    def readline(self) -> Optional[str]:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                if self.buf:
                    line = self.buf.decode("ascii", errors="replace")
                    self.buf = b""
                    return line
                return None
            self.buf += chunk
        nl = self.buf.index(b"\n")
        line = self.buf[:nl].decode("ascii", errors="replace")
        self.buf = self.buf[nl + 1:]
        return line


def send_line(sock: socket.socket, line: str) -> None:
    sock.sendall(line.encode("ascii"))


# -------------------- Piece geometry --------------------

def parse_cells(rest: str) -> Tuple[Tuple[int, int], ...]:
    """Parse 'x1,y1 x2,y2 ...' into a tuple of (x,y) ints."""
    out = []
    for tok in rest.split(" "):
        if not tok:
            continue
        x_s, y_s = tok.split(",")
        out.append((int(x_s), int(y_s)))
    return tuple(out)


def rotate_cells(cells: Tuple[Tuple[int, int], ...], k: int) -> Tuple[Tuple[int, int], ...]:
    """Apply (x,y) -> (-y,x) exactly k times, then normalize once."""
    pts = list(cells)
    for _ in range(k % 4):
        pts = [(-y, x) for (x, y) in pts]
    min_x = min(p[0] for p in pts)
    min_y = min(p[1] for p in pts)
    return tuple(sorted((x - min_x, y - min_y) for (x, y) in pts))


def unique_rotations(cells: Tuple[Tuple[int, int], ...]) -> List[Tuple[int, Tuple[Tuple[int, int], ...]]]:
    """Return list of (rotation_index, rotated_cells) deduplicating equivalent shapes.
    We pick the smallest rotation index for each distinct rotated cell-set."""
    seen = {}
    for k in range(4):
        rc = rotate_cells(cells, k)
        if rc not in seen:
            seen[rc] = k
    # return in ascending k order for deterministic behaviour
    return sorted([(k, rc) for rc, k in seen.items()], key=lambda t: t[0])


# -------------------- Tank model --------------------

class Tank:
    """2D occupancy grid; columns indexed 0..n_cols-1, rows 0..n_rows-1.
    We store column heights and a dense grid for hole/landing computations."""
    __slots__ = ("n_cols", "n_rows", "grid", "heights")

    def __init__(self, n_cols: int, n_rows: int):
        self.n_cols = n_cols
        self.n_rows = n_rows
        # grid[y][x] : True if filled. y=0 is floor.
        self.grid = [[False] * n_cols for _ in range(n_rows)]
        self.heights = [0] * n_cols  # heights[x] = (max y of a filled cell in col x) + 1; 0 if empty

    def clone(self) -> "Tank":
        t = Tank.__new__(Tank)
        t.n_cols = self.n_cols
        t.n_rows = self.n_rows
        t.grid = [row[:] for row in self.grid]
        t.heights = self.heights[:]
        return t

    def settle_y(self, rcells: Tuple[Tuple[int, int], ...], column: int) -> Optional[int]:
        """Compute settle_y for rotated cells at given column. None if invalid (out of bounds)."""
        # Horizontal bounds
        w = max(rx for rx, _ in rcells) + 1
        if column < 0 or column + w > self.n_cols:
            return None

        # For each cell (rx, ry), the absolute board column is column + rx.
        # We need the smallest non-negative settle_y such that for all cells
        # (column+rx, settle_y+ry) is empty, AND lowering by 1 would either
        # put some cell at y<0 or hit an occupied cell.
        #
        # Equivalently: for each cell, the lowest settle_y where it doesn't
        # collide is: heights[column+rx] - ry. Take the max across cells.
        # Reasoning: if column c has height h, then row h is the first empty row
        # in that column. The cell with offset ry needs settle_y + ry >= h, i.e.
        # settle_y >= h - ry. We need this for every cell in the piece.
        # Note this assumes columns are "stacks" (no overhangs in those columns).
        # That is NOT generally true after polyominoes land and leave holes.
        # We handle that by computing candidate from heights, then verifying;
        # if verification fails we fall back to scanning.
        #
        # Safer: do a direct scan. For modest grids this is fine.

        n_rows = self.n_rows
        grid = self.grid

        # Lower bound from per-column heights (fast estimate, correct as a *lower* bound only
        # if the piece doesn't have to slide past holes — but with vertical-only drop, the
        # height-based formula is exactly right because the falling piece can't enter a
        # column from the side: it descends straight down. So the deepest it can sit in
        # column (column+rx) is height[column+rx] in absolute terms; the cell with offset
        # ry must be at row >= height[column+rx], so settle_y >= height[column+rx] - ry).
        candidate = 0
        for rx, ry in rcells:
            need = self.heights[column + rx] - ry
            if need > candidate:
                candidate = need
        # candidate could be negative if all offsets ry are larger than heights — clamp to 0
        if candidate < 0:
            candidate = 0
        return candidate

    def can_commit(self, rcells: Tuple[Tuple[int, int], ...], column: int, settle_y: int) -> bool:
        """Check the top-bound: every cell (column+rx, settle_y+ry) must be < n_rows
        and currently empty (defensive)."""
        n_rows = self.n_rows
        grid = self.grid
        for rx, ry in rcells:
            ax = column + rx
            ay = settle_y + ry
            if ay >= n_rows:
                return False
            if ay < 0:
                return False  # shouldn't happen
            if grid[ay][ax]:
                return False  # shouldn't happen with correct settle_y
        return True

    def commit(self, rcells: Tuple[Tuple[int, int], ...], column: int, settle_y: int) -> None:
        grid = self.grid
        for rx, ry in rcells:
            ax = column + rx
            ay = settle_y + ry
            grid[ay][ax] = True
            if ay + 1 > self.heights[ax]:
                self.heights[ax] = ay + 1

    # ---------- Heuristic features ----------
    def features(self) -> Tuple[int, int, int, int, int]:
        """Return (holes, bumpiness, max_h, agg_h, wells)."""
        n_cols = self.n_cols
        heights = self.heights
        grid = self.grid

        # holes: empty cells with at least one filled cell above in the same column.
        # We traverse only filled regions per column.
        holes = 0
        for x in range(n_cols):
            h = heights[x]
            if h <= 1:
                continue
            # count empties from y=0 to y=h-2
            col_h = 0
            for y in range(h - 1):
                if not grid[y][x]:
                    col_h += 1
            holes += col_h

        # bumpiness, max_h, agg_h in one pass
        bump = 0
        prev = heights[0]
        max_h = prev
        agg_h = prev
        for i in range(1, n_cols):
            cur = heights[i]
            d = prev - cur
            bump += -d if d < 0 else d
            if cur > max_h:
                max_h = cur
            agg_h += cur
            prev = cur

        # wells: column strictly lower than both neighbors. Walls treated as full (n_rows).
        wells = 0
        nr = self.n_rows
        for x in range(n_cols):
            left_h = heights[x - 1] if x > 0 else nr
            right_h = heights[x + 1] if x + 1 < n_cols else nr
            min_nb = left_h if left_h < right_h else right_h
            d = min_nb - heights[x]
            if d > 0:
                wells += d * (d + 1) // 2

        return (holes, bump, max_h, agg_h, wells)

    def row_fill_bonus(self) -> float:
        """Cheap proxy for row density: compare total filled cells to bounding-box volume.
        Higher fraction of cells in the active region = better packing."""
        max_h = 0
        for h in self.heights:
            if h > max_h:
                max_h = h
        if max_h == 0:
            return 0.0
        # filled cells in active region = sum(heights) - holes_below_each_column
        # We can't cheaply compute holes here without re-scanning, so just
        # use sum(heights) / (max_h * n_cols) as the density proxy.
        agg = sum(self.heights)
        return agg / (max_h * self.n_cols)


def evaluate(tank: Tank, last_landing_y: int) -> float:
    holes, bump, max_h, agg_h, wells = tank.features()
    score = (W_LANDING * last_landing_y
             + W_HOLES * holes
             + W_BUMPINESS * bump
             + W_MAX_HEIGHT * max_h
             + W_AGG_HEIGHT * agg_h
             + W_WELLS * wells
             + W_ROW_FILL * tank.row_fill_bonus())
    return score


# -------------------- Search --------------------

def enumerate_placements(tank: Tank, base_cells: Tuple[Tuple[int, int], ...]) -> List[Tuple[int, int, Tuple[Tuple[int, int], ...], int]]:
    """Return list of (rotation, column, rcells, settle_y) for all valid placements."""
    out = []
    for k, rc in unique_rotations(base_cells):
        w = max(rx for rx, _ in rc) + 1
        max_col = tank.n_cols - w
        for col in range(0, max_col + 1):
            sy = tank.settle_y(rc, col)
            if sy is None:
                continue
            # top-bound check
            if any(sy + ry >= tank.n_rows for _, ry in rc):
                continue
            out.append((k, col, rc, sy))
    return out


def best_move(tank: Tank, current: Tuple[Tuple[int, int], ...],
              nexts: List[Tuple[Tuple[int, int], ...]],
              beam: int = 8, top_k: int = 12) -> Tuple[int, int]:
    """Choose (rotation, column) for the CURRENT piece using lookahead with a beam.

    Top-level: score every placement by immediate eval, keep top_k for recursion.
    Recursive lookahead uses `beam` at each next level.
    """
    placements = enumerate_placements(tank, current)
    if not placements:
        return (0, 0)

    # Score all placements by immediate evaluation.
    scored = []
    for (k, col, rc, sy) in placements:
        t1 = tank.clone()
        t1.commit(rc, col, sy)
        s = evaluate(t1, sy)
        scored.append((s, k, col, rc, sy, t1))

    scored.sort(key=lambda t: t[0], reverse=True)

    # No lookahead: just return the best immediate.
    if not nexts:
        return (scored[0][1], scored[0][2])

    # Lookahead on top_k candidates only.
    candidates = scored[:top_k]
    best_score = -float("inf")
    best_choice = (candidates[0][1], candidates[0][2])
    for (immediate, k, col, rc, sy, t1) in candidates:
        total = immediate + lookahead(t1, nexts, 0, beam, beam)
        if total > best_score:
            best_score = total
            best_choice = (k, col)

    return best_choice


def lookahead(tank: Tank, nexts: List[Tuple[Tuple[int, int], ...]], depth: int,
              beam: int, max_branch: int) -> float:
    """Best-first lookahead. Returns the best added evaluation contribution."""
    if depth >= len(nexts):
        return 0.0
    piece = nexts[depth]
    placements = enumerate_placements(tank, piece)
    if not placements:
        # We can't place this future piece — that's bad but not catastrophic for the
        # CURRENT decision (the piece sequence is fixed but the actual board at that
        # future step may differ). Add a moderate penalty proportional to depth so
        # CURRENT moves that lock us out sooner are punished more.
        return W_DEATH / (10.0 ** (depth + 1))

    # Score all placements by immediate eval, take top `beam`.
    scored: List[Tuple[float, int, int, Tuple[Tuple[int, int], ...], int]] = []
    for (k, col, rc, sy) in placements:
        t1 = tank.clone()
        t1.commit(rc, col, sy)
        s = evaluate(t1, sy)
        scored.append((s, k, col, rc, sy))
    scored.sort(key=lambda t: t[0], reverse=True)
    if len(scored) > beam:
        scored = scored[:beam]

    # Recurse on each survivor and pick the best total
    best = -float("inf")
    for (s, k, col, rc, sy) in scored:
        if depth + 1 < len(nexts):
            t1 = tank.clone()
            t1.commit(rc, col, sy)
            total = s + lookahead(t1, nexts, depth + 1, beam, max_branch)
        else:
            total = s
        if total > best:
            best = total
    return best


# -------------------- Main loop --------------------

def main():
    sock = socket.create_connection((HOST, PORT))
    sock.settimeout(30.0)
    reader = LineReader(sock)

    # Register
    send_line(sock, f"{MODEL_NAME}_bot\n")

    tank: Optional[Tank] = None
    round_num = 0

    while True:
        line = reader.readline()
        if line is None:
            # EOF
            break
        line = line.strip()
        if not line:
            continue

        if line.startswith("ROUND "):
            parts = line.split()
            # ROUND {n} {cols} {rows}
            round_num = int(parts[1])
            n_cols = int(parts[2])
            n_rows = int(parts[3])
            tank = Tank(n_cols, n_rows)
            # Choose beam size based on board: larger boards = more placements,
            # so trim beam to keep within time budget.
            continue

        if line == "PIECE":
            # Read three more lines
            cur_line = reader.readline()
            n1_line = reader.readline()
            n2_line = reader.readline()
            if cur_line is None or n1_line is None or n2_line is None:
                break

            assert cur_line.startswith("CURRENT "), f"Expected CURRENT, got {cur_line!r}"
            current = parse_cells(cur_line[len("CURRENT "):].strip())

            nexts: List[Tuple[Tuple[int, int], ...]] = []
            for nl in (n1_line, n2_line):
                rest = nl[len("NEXT "):].strip() if nl.startswith("NEXT ") else nl.strip()
                if rest == "END" or nl.strip() == "NEXT END":
                    continue
                # nl looks like "NEXT 0,0 1,0 ..."
                if nl.startswith("NEXT "):
                    payload = nl[len("NEXT "):].strip()
                    if payload == "END":
                        continue
                    nexts.append(parse_cells(payload))

            # Pick beam size adaptively. Self-play shows we have major budget headroom,
            # so we can afford fairly wide beams. Conservative ceilings keep big boards safe.
            assert tank is not None
            cells = tank.n_cols * tank.n_rows
            if cells <= 80:
                beam = 16; top_k = 24
            elif cells <= 144:
                beam = 12; top_k = 18
            elif cells <= 224:
                beam = 10; top_k = 14
            else:
                beam = 8; top_k = 12

            rot, col = best_move(tank, current, nexts, beam=beam, top_k=top_k)

            # Send response — strict grammar: "{rot} {col}\n"
            send_line(sock, f"{rot} {col}\n")

            # Read server reply
            reply = reader.readline()
            if reply is None:
                break
            reply = reply.strip()
            if reply.startswith("OK "):
                # Apply the move to our local tank too (the same way the server did)
                # We need rcells for the chosen rotation and the settle_y.
                rc = rotate_cells(current, rot)
                sy = tank.settle_y(rc, col)
                if sy is not None:
                    # Sanity check against server bottom_y
                    server_bottom = int(reply.split()[1])
                    if sy != server_bottom:
                        # Disagreement — trust server, but our local model is now suspect.
                        # Best effort: log to stderr and continue.
                        print(f"[warn] settle_y mismatch: ours={sy} server={server_bottom}",
                              file=sys.stderr)
                        sy = server_bottom
                    tank.commit(rc, col, sy)
            elif reply.startswith("ROUND_END"):
                # Round ended on this placement (e.g., we sent invalid). Wait for next ROUND or END.
                pass
            else:
                # unexpected
                print(f"[warn] unexpected reply: {reply!r}", file=sys.stderr)

            continue

        if line.startswith("ROUND_END"):
            # End of a round; loop back for next ROUND or END
            continue

        if line == "END":
            break

        # Unknown line — ignore
        # print(f"[debug] unknown line: {line!r}", file=sys.stderr)

    try:
        sock.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()