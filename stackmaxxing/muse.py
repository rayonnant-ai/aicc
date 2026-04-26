#!/usr/bin/env python3
import sys
import socket
import time
from collections import namedtuple
from typing import List, Tuple, Set, Optional

Piece = List[Tuple[int, int]] # list of (x,y) cells, normalized to min_x=0, min_y=0
Move = namedtuple('Move', ['rotation', 'column', 'settle_y', 'cells'])

HOST = 'localhost'
PORT = 7474
BOT_NAME = 'muse_spark_bot'

class Board:
    def __init__(self, cols: int, rows: int):
        self.cols = cols
        self.rows = rows
        self.grid = [[False] * cols for _ in range(rows)] # grid[y][x]
        self.heights = [0] * cols # height of highest occupied cell + 1 per column

    def copy(self) -> 'Board':
        b = Board(self.cols, self.rows)
        b.grid = [row[:] for row in self.grid]
        b.heights = self.heights[:]
        return b

    def can_place(self, cells: List[Tuple[int, int]]) -> bool:
        for x, y in cells:
            if x < 0 or x >= self.cols or y < 0 or y >= self.rows:
                return False
            if self.grid[y][x]:
                return False
        return True

    def place(self, cells: List[Tuple[int, int]]):
        for x, y in cells:
            self.grid[y][x] = True
            self.heights[x] = max(self.heights[x], y + 1)

    def drop_height(self, piece: Piece, col: int) -> Optional[int]:
        """Return settle_y for piece at col, or None if OOB horizontally"""
        w = max(x for x, y in piece) + 1
        if col < 0 or col + w > self.cols:
            return None

        # For each column the piece occupies, find highest blocker below each cell
        min_settle = 0
        for px, py in piece:
            x = col + px
            # highest occupied cell in this column below where this piece cell would be
            # We need settle_y + py >= heights[x] to avoid collision
            min_settle = max(min_settle, self.heights[x] - py)

        # Check top bound
        for px, py in piece:
            if min_settle + py >= self.rows:
                return None # would overflow top

        return min_settle

    def get_move(self, piece: Piece, col: int) -> Optional[Move]:
        settle_y = self.drop_height(piece, col)
        if settle_y is None:
            return None
        cells = [(col + px, settle_y + py) for px, py in piece]
        if not self.can_place(cells):
            return None
        return Move(0, col, settle_y, cells)

    def score(self) -> float:
        """Heuristic: penalize height, holes, bumpiness. Lower is better."""
        max_h = max(self.heights) if self.heights else 0
        holes = 0
        for x in range(self.cols):
            filled = False
            for y in range(self.rows - 1, -1, -1):
                if self.grid[y][x]:
                    filled = True
                elif filled:
                    holes += 1

        bumpiness = sum(abs(self.heights[i] - self.heights[i+1])
                       for i in range(self.cols - 1))

        return max_h * 1.0 + holes * 2.5 + bumpiness * 0.6

def rotate_piece(piece: Piece, rot: int) -> Piece:
    """Apply (x,y) -> (-y,x) rot times, then renormalize once"""
    cells = piece[:]
    for _ in range(rot % 4):
        cells = [(-y, x) for x, y in cells]

    if not cells:
        return cells

    min_x = min(x for x, y in cells)
    min_y = min(y for x, y in cells)
    return [(x - min_x, y - min_y) for x, y in cells]

def parse_piece_line(line: str) -> Optional[Piece]:
    """Parse 'CURRENT 0,0 1,0' or 'NEXT END'"""
    parts = line.strip().split()
    if len(parts) < 2 or parts[1] == 'END':
        return None
    cells = []
    for token in parts[1:]:
        x, y = token.split(',')
        cells.append((int(x), int(y)))
    return cells

def all_placements(board: Board, piece: Piece) -> List[Move]:
    """Generate all legal placements for all 4 rotations"""
    moves = []
    for rot in range(4):
        rp = rotate_piece(piece, rot)
        w = max(x for x, y in rp) + 1
        for col in range(board.cols - w + 1):
            m = board.get_move(rp, col)
            if m:
                moves.append(Move(rot, col, m.settle_y, m.cells))
    return moves

def choose_move(board: Board, pieces: List[Piece], beam_width=30) -> Optional[Move]:
    """
    Beam search over 3-piece lookahead.
    We want to survive longest, so minimize board score after lookahead.
    """
    if not pieces or pieces[0] is None:
        return None

    current = pieces[0]
    futures = [p for p in pieces[1:] if p is not None]

    first_moves = all_placements(board, current)
    if not first_moves:
        return None

    if not futures: # no lookahead, just pick lowest score
        best = None
        best_score = float('inf')
        for m in first_moves:
            b = board.copy()
            b.place(m.cells)
            s = b.score()
            if s < best_score:
                best_score, best = s, m
        return best

    # Evaluate with lookahead using beam search
    candidates = []
    for m in first_moves:
        b1 = board.copy()
        b1.place(m.cells)
        candidates.append((b1.score(), b1, m, 0))

    candidates.sort(key=lambda t: t[0])
    candidates = candidates[:beam_width]

    for depth, future_piece in enumerate(futures, 1):
        new_candidates = []
        for _, b, first_move, _ in candidates:
            for m in all_placements(b, future_piece):
                b2 = b.copy()
                b2.place(m.cells)
                new_candidates.append((b2.score(), b2, first_move, depth))

        if not new_candidates:
            break
        new_candidates.sort(key=lambda t: t[0])
        candidates = new_candidates[:beam_width]

    return candidates[0][2] if candidates else first_moves[0]

class StackMaxBot:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.rfile = sock.makefile('r', encoding='ascii', newline='\n')
        self.wfile = sock.makefile('w', encoding='ascii', newline='\n')
        self.board: Optional[Board] = None

    def send(self, msg: str):
        self.wfile.write(msg)
        self.wfile.flush()

    def readline(self) -> str:
        line = self.rfile.readline()
        if not line:
            raise EOFError("Server closed connection")
        return line.rstrip('\n')

    def run(self):
        self.send(f'{BOT_NAME}\n')

        while True:
            line = self.readline()
            if line == 'END':
                return

            if not line.startswith('ROUND '):
                raise ValueError(f'Expected ROUND, got: {line}')

            _, round_num, n_cols, n_rows = line.split()
            self.board = Board(int(n_cols), int(n_rows))

            while True:
                line = self.readline()
                if line.startswith('ROUND_END'):
                    break
                if line!= 'PIECE':
                    raise ValueError(f'Expected PIECE, got: {line}')

                pieces = []
                for _ in range(3): # CURRENT, NEXT, NEXT
                    pieces.append(parse_piece_line(self.readline()))

                move = choose_move(self.board, pieces)
                if move is None:
                    # No legal move - send something invalid to end cleanly
                    # But spec says any invalid ends round, so 0 0 is safest
                    # If 0 0 is also invalid, server ends it anyway
                    self.send('0 0\n')
                else:
                    self.send(f'{move.rotation} {move.column}\n')
                    self.board.place(move.cells)

                resp = self.readline()
                if resp.startswith('ROUND_END'):
                    break
                elif resp.startswith('OK '):
                    # Sanity check: server's bottom_y should match ours
                    _, bottom_y = resp.split()
                    assert int(bottom_y) == move.settle_y
                else:
                    raise ValueError(f'Unexpected response: {resp}')

def main():
    with socket.create_connection((HOST, PORT)) as sock:
        bot = StackMaxBot(sock)
        bot.run()

if __name__ == '__main__':
    main()