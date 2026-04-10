#!/usr/bin/env python3
import argparse
import math
import socket
import sys
import time
from dataclasses import dataclass

WIN_SCORE = 1000000
TIME_BUDGET = 1.85


class SearchTimeout(Exception):
    pass


@dataclass(frozen=True)
class Move:
    row: int
    col: int


class BoardShape:
    DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))

    def __init__(self, grid_lines):
        self.grid = [list(row.rstrip("\n")) for row in grid_lines]
        self.rows = len(self.grid)
        self.cols = len(self.grid[0]) if self.rows else 0
        self.valid = []
        self.valid_set = set()
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] != '.':
                    cell = (r, c)
                    self.valid.append(cell)
                    self.valid_set.add(cell)
        self.center_r = (self.rows - 1) / 2.0
        self.center_c = (self.cols - 1) / 2.0
        self.lines = []
        self.cell_to_lines = {cell: [] for cell in self.valid}
        for r, c in self.valid:
            for dr, dc in self.DIRS:
                p1 = (r, c)
                p2 = (r + dr, c + dc)
                p3 = (r + 2 * dr, c + 2 * dc)
                if p2 in self.valid_set and p3 in self.valid_set:
                    idx = len(self.lines)
                    triple = (p1, p2, p3)
                    self.lines.append(triple)
                    self.cell_to_lines[p1].append(idx)
                    self.cell_to_lines[p2].append(idx)
                    self.cell_to_lines[p3].append(idx)
        self.base_weight = {}
        for cell in self.valid:
            degree = len(self.cell_to_lines[cell])
            dist = abs(cell[0] - self.center_r) + abs(cell[1] - self.center_c)
            self.base_weight[cell] = degree * 10 - dist


class GameState:
    def __init__(self, shape, my_mark):
        self.shape = shape
        self.my_mark = my_mark
        self.opp_mark = 'O' if my_mark == 'X' else 'X'
        self.cells = {cell: '_' for cell in self.shape.valid}
        self.empty_count = len(self.shape.valid)
        self.active = True

    def empties(self):
        return [cell for cell, v in self.cells.items() if v == '_']

    def apply(self, cell, mark):
        if self.cells.get(cell) != '_':
            raise ValueError(f"invalid move {cell}")
        self.cells[cell] = mark
        self.empty_count -= 1

    def undo(self, cell):
        self.cells[cell] = '_'
        self.empty_count += 1

    def is_win_after(self, cell, mark):
        for idx in self.shape.cell_to_lines[cell]:
            triple = self.shape.lines[idx]
            if all(self.cells[p] == mark for p in triple):
                return True
        return False

    def immediate_wins(self, mark):
        wins = set()
        other = 'O' if mark == 'X' else 'X'
        for triple in self.shape.lines:
            marks = [self.cells[p] for p in triple]
            if other in marks:
                continue
            if marks.count(mark) == 2 and marks.count('_') == 1:
                wins.add(triple[marks.index('_')])
        return wins

    def evaluate(self):
        score = 0.0
        my_threats = 0
        opp_threats = 0
        for triple in self.shape.lines:
            marks = [self.cells[p] for p in triple]
            m = marks.count(self.my_mark)
            o = marks.count(self.opp_mark)
            e = 3 - m - o
            if m and o:
                continue
            if m == 3:
                return WIN_SCORE
            if o == 3:
                return -WIN_SCORE
            if m == 2 and e == 1:
                my_threats += 1
                score += 120
            elif m == 1 and e == 2:
                score += 14
            elif o == 2 and e == 1:
                opp_threats += 1
                score -= 135
            elif o == 1 and e == 2:
                score -= 16
        score += 40 * my_threats - 55 * opp_threats
        if self.empty_count:
            for cell, val in self.cells.items():
                if val == self.my_mark:
                    score += self.shape.base_weight[cell] * 0.35
                elif val == self.opp_mark:
                    score -= self.shape.base_weight[cell] * 0.35
        return score

    def static_cell_score(self, cell, mark):
        other = 'O' if mark == 'X' else 'X'
        score = self.shape.base_weight[cell]
        self.apply(cell, mark)
        try:
            if self.is_win_after(cell, mark):
                return WIN_SCORE - 1
            future_wins = len(self.immediate_wins(mark))
            opp_wins = len(self.immediate_wins(other))
            score += future_wins * 280
            score -= opp_wins * 240
            for idx in self.shape.cell_to_lines[cell]:
                triple = self.shape.lines[idx]
                marks = [self.cells[p] for p in triple]
                m = marks.count(mark)
                o = marks.count(other)
                e = 3 - m - o
                if m and o:
                    continue
                if m == 2 and e == 1:
                    score += 150
                elif m == 1 and e == 2:
                    score += 20
                elif o == 2 and e == 1:
                    score -= 125
                elif o == 1 and e == 2:
                    score -= 12
        finally:
            self.undo(cell)
        return score

    def ordered_moves(self, mark):
        other = 'O' if mark == 'X' else 'X'
        win_now = self.immediate_wins(mark)
        if win_now:
            return sorted(win_now)
        must_block = self.immediate_wins(other)
        empties = self.empties()
        scored = []
        for cell in empties:
            bonus = 0
            if cell in must_block:
                bonus += WIN_SCORE // 2
            bonus += self.static_cell_score(cell, mark)
            scored.append((bonus, cell))
        scored.sort(key=lambda x: (-x[0], x[1]))
        if must_block:
            forced = [cell for _, cell in scored if cell in must_block]
            extras = [cell for _, cell in scored if cell not in must_block][:4]
            return forced + extras
        if len(scored) <= 14:
            return [cell for _, cell in scored]
        limit = 8 if self.empty_count > 24 else 10 if self.empty_count > 16 else 12
        return [cell for _, cell in scored[:limit]]

    def choose_move(self):
        empties = self.empties()
        if not empties:
            return Move(0, 0)
        win_now = self.immediate_wins(self.my_mark)
        if win_now:
            cell = max(sorted(win_now), key=lambda c: self.shape.base_weight[c])
            return Move(*cell)
        must_block = self.immediate_wins(self.opp_mark)
        if must_block:
            best = None
            best_score = -float('inf')
            for cell in sorted(must_block):
                score = self.static_cell_score(cell, self.my_mark)
                if score > best_score:
                    best_score = score
                    best = cell
            return Move(*best)
        if self.empty_count == len(self.shape.valid):
            cell = max(empties, key=lambda c: (self.shape.base_weight[c], -abs(c[0]-self.shape.center_r)-abs(c[1]-self.shape.center_c), -c[0], -c[1]))
            return Move(*cell)
        start = time.monotonic()
        deadline = start + TIME_BUDGET
        root_moves = self.ordered_moves(self.my_mark)
        if not root_moves:
            cell = max(empties, key=lambda c: self.shape.base_weight[c])
            return Move(*cell)
        best = root_moves[0]
        best_val = -float('inf')
        if self.empty_count <= 8:
            max_depth = 6
        elif self.empty_count <= 14:
            max_depth = 5
        elif self.empty_count <= 24:
            max_depth = 4
        else:
            max_depth = 3
        try:
            for depth in range(1, max_depth + 1):
                current_best = best
                current_val = -float('inf')
                alpha = -float('inf')
                beta = float('inf')
                ordered_root = sorted(root_moves, key=lambda c: (-self.static_cell_score(c, self.my_mark), c))
                for cell in ordered_root:
                    if time.monotonic() >= deadline:
                        raise SearchTimeout
                    self.apply(cell, self.my_mark)
                    if self.is_win_after(cell, self.my_mark):
                        self.undo(cell)
                        return Move(*cell)
                    val = -self.negamax(depth - 1, -beta, -alpha, self.opp_mark, cell, deadline)
                    self.undo(cell)
                    if val > current_val or (val == current_val and self.shape.base_weight[cell] > self.shape.base_weight[current_best]):
                        current_val = val
                        current_best = cell
                    if val > alpha:
                        alpha = val
                best = current_best
                best_val = current_val
                root_moves = [best] + [c for c in ordered_root if c != best]
        except SearchTimeout:
            pass
        if best_val == -float('inf'):
            best = max(root_moves, key=lambda c: self.static_cell_score(c, self.my_mark))
        return Move(*best)

    def negamax(self, depth, alpha, beta, to_move, last_cell, deadline):
        if time.monotonic() >= deadline:
            raise SearchTimeout
        just_played = 'O' if to_move == 'X' else 'X'
        if last_cell is not None and self.is_win_after(last_cell, just_played):
            if just_played == self.my_mark:
                return WIN_SCORE - (6 - depth)
            return -WIN_SCORE + (6 - depth)
        if self.empty_count == 0:
            return 0
        if depth == 0:
            return self.evaluate() if to_move == self.my_mark else -self.evaluate()
        moves = self.ordered_moves(to_move)
        if not moves:
            return 0
        best = -float('inf')
        next_mark = 'O' if to_move == 'X' else 'X'
        for cell in moves:
            self.apply(cell, to_move)
            score = -self.negamax(depth - 1, -beta, -alpha, next_mark, cell, deadline)
            self.undo(cell)
            if score > best:
                best = score
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break
        return best


class Client:
    def __init__(self, host, port, name):
        self.host = host
        self.port = port
        self.name = name
        self.sock = None
        self.reader = None
        self.writer = None
        self.games = {}

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port))
        self.reader = self.sock.makefile('r', encoding='utf-8', newline='\n')
        self.writer = self.sock.makefile('w', encoding='utf-8', newline='\n')
        self.send_line(self.name)

    def close(self):
        try:
            if self.writer:
                self.writer.close()
        finally:
            try:
                if self.reader:
                    self.reader.close()
            finally:
                if self.sock:
                    self.sock.close()

    def send_line(self, line):
        self.writer.write(line + '\n')
        self.writer.flush()

    def read_line(self):
        line = self.reader.readline()
        if line == '':
            return None
        return line.rstrip('\n')

    def run(self):
        self.connect()
        try:
            while True:
                line = self.read_line()
                if line is None:
                    break
                if not line:
                    continue
                if line.startswith('ROUND '):
                    self.handle_round()
                elif line.startswith('YOURTURN '):
                    game_id = int(line.split()[1])
                    move = self.games[game_id].choose_move()
                    self.games[game_id].apply((move.row, move.col), self.games[game_id].my_mark)
                    self.send_line(f'{move.row} {move.col}')
                elif line.startswith('OPPONENT '):
                    _, gid, row, col = line.split()
                    game = self.games[int(gid)]
                    game.apply((int(row), int(col)), game.opp_mark)
                elif line.startswith('RESULT '):
                    parts = line.split()
                    gid = int(parts[1][4:])
                    if gid in self.games:
                        self.games[gid].active = False
                elif line.startswith('ROUND_SCORE'):
                    continue
                elif line.startswith('MATCHUP '):
                    continue
        finally:
            self.close()

    def handle_round(self):
        board_marker = self.read_line()
        if board_marker != 'BOARD':
            raise ValueError('Expected BOARD')
        grid = []
        while True:
            line = self.read_line()
            if line is None:
                raise EOFError('Unexpected EOF while reading board')
            if line == 'END':
                break
            grid.append(line)
        game1 = self.read_line().split()
        game2 = self.read_line().split()
        shape = BoardShape(grid)
        self.games = {
            1: GameState(shape, game1[1]),
            2: GameState(shape, game2[1]),
        }


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=7474)
    parser.add_argument('--name', default='gpt54_bot')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    client = Client(args.host, args.port, args.name)
    client.run()


if __name__ == '__main__':
    main()