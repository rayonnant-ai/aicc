#!/usr/bin/env python3
"""Blobby Tic-Tac-Toe bot — minimax with alpha-beta on irregular grids."""

import socket
import sys
import time
from typing import Optional

HOST = "localhost"
PORT = 7474
TIMEOUT = 1.8  # safety margin under 2s limit

EMPTY = 0
ME = 1
OPP = 2


def parse_board(lines: list[str]) -> tuple[int, int, list[list[int]]]:
    """Parse board lines into (rows, cols, grid). 1=valid, 0=hole."""
    rows = len(lines)
    cols = max(len(l) for l in lines) if lines else 0
    grid = []
    for r in range(rows):
        row = []
        for c in range(cols):
            if c < len(lines[r]) and lines[r][c] == '_':
                row.append(1)
            else:
                row.append(0)
        grid.append(row)
    return rows, cols, grid


def find_lines(rows: int, cols: int, valid: list[list[int]]) -> list[list[tuple[int, int]]]:
    """Find all possible winning lines (3-in-a-row on valid cells, no holes in between)."""
    lines = []
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for r in range(rows):
        for c in range(cols):
            if not valid[r][c]:
                continue
            for dr, dc in directions:
                cells = []
                ok = True
                for step in range(3):
                    nr, nc = r + dr * step, c + dc * step
                    if 0 <= nr < rows and 0 <= nc < cols and valid[nr][nc]:
                        cells.append((nr, nc))
                    else:
                        ok = False
                        break
                if ok and len(cells) == 3:
                    lines.append(cells)
    return lines


def check_win(board: list[list[int]], lines: list[list[tuple[int, int]]], player: int) -> bool:
    for line in lines:
        if all(board[r][c] == player for r, c in line):
            return True
    return False


def get_valid_moves(board: list[list[int]], valid: list[list[int]], rows: int, cols: int) -> list[tuple[int, int]]:
    moves = []
    for r in range(rows):
        for c in range(cols):
            if valid[r][c] and board[r][c] == EMPTY:
                moves.append((r, c))
    return moves


def is_full(board: list[list[int]], valid: list[list[int]], rows: int, cols: int) -> bool:
    for r in range(rows):
        for c in range(cols):
            if valid[r][c] and board[r][c] == EMPTY:
                return False
    return True


class GameState:
    def __init__(self, rows: int, cols: int, valid: list[list[int]], lines: list[list[tuple[int, int]]]):
        self.rows = rows
        self.cols = cols
        self.valid = valid
        self.lines = lines
        self.board = [[EMPTY] * cols for _ in range(rows)]
        self.me = EMPTY
        self.opp = EMPTY
        self.game_over = False

    def make_move(self, r: int, c: int, player: int):
        self.board[r][c] = player

    def evaluate(self, maximizing_player: int) -> float:
        """Static evaluation: +1000/−1000 for win/loss, else heuristic."""
        other = OPP if maximizing_player == ME else ME
        if check_win(self.board, self.lines, maximizing_player):
            return 1000
        if check_win(self.board, self.lines, other):
            return -1000

        score = 0.0
        for line in self.lines:
            vals = [self.board[r][c] for r, c in line]
            my_count = vals.count(maximizing_player)
            opp_count = vals.count(other)
            if my_count > 0 and opp_count == 0:
                score += my_count * my_count * 10
            elif opp_count > 0 and my_count == 0:
                score -= opp_count * opp_count * 10
        return score

    def order_moves(self, moves: list[tuple[int, int]], maximizing_player: int) -> list[tuple[int, int]]:
        """Order moves for better alpha-beta pruning."""
        other = OPP if maximizing_player == ME else ME
        scored = []
        mid_r, mid_c = self.rows / 2.0, self.cols / 2.0
        for r, c in moves:
            s = 0
            # Check if this move wins immediately
            self.board[r][c] = maximizing_player
            if check_win(self.board, self.lines, maximizing_player):
                s -= 10000  # sort first (most negative)
            self.board[r][c] = EMPTY
            # Check if this move blocks opponent win
            self.board[r][c] = other
            if check_win(self.board, self.lines, other):
                s -= 5000  # sort second
            self.board[r][c] = EMPTY
            # Prefer cells on more lines
            line_count = 0
            my_partial = 0
            for line in self.lines:
                if (r, c) in line:
                    line_count += 1
                    vals = [self.board[rr][cc] for rr, cc in line]
                    if maximizing_player in vals and other not in vals:
                        my_partial += 2
                    elif other in vals and maximizing_player not in vals:
                        my_partial += 1
            s -= my_partial * 100
            s -= line_count * 10
            # Center preference
            s += int(abs(r - mid_r) + abs(c - mid_c))
            scored.append((s, (r, c)))
        scored.sort()
        return [m for _, m in scored]

    def minimax(self, depth: int, alpha: float, beta: float, is_max: bool,
                maximizing_player: int, deadline: float) -> tuple[float, Optional[tuple[int, int]]]:
        if time.monotonic() > deadline:
            raise TimeoutError()

        other = OPP if maximizing_player == ME else ME
        cur_player = maximizing_player if is_max else other

        # Terminal checks
        if check_win(self.board, self.lines, maximizing_player):
            return 1000 + depth, None  # prefer faster wins
        if check_win(self.board, self.lines, other):
            return -1000 - depth, None
        if is_full(self.board, self.valid, self.rows, self.cols):
            return 0, None
        if depth == 0:
            return self.evaluate(maximizing_player), None

        moves = get_valid_moves(self.board, self.valid, self.rows, self.cols)
        if not moves:
            return 0, None

        moves = self.order_moves(moves, cur_player)

        best_move = moves[0]
        if is_max:
            value = float('-inf')
            for m in moves:
                self.board[m[0]][m[1]] = cur_player
                v, _ = self.minimax(depth - 1, alpha, beta, False, maximizing_player, deadline)
                self.board[m[0]][m[1]] = EMPTY
                if v > value:
                    value = v
                    best_move = m
                alpha = max(alpha, value)
                if alpha >= beta:
                    break
            return value, best_move
        else:
            value = float('inf')
            for m in moves:
                self.board[m[0]][m[1]] = cur_player
                v, _ = self.minimax(depth - 1, alpha, beta, True, maximizing_player, deadline)
                self.board[m[0]][m[1]] = EMPTY
                if v < value:
                    value = v
                    best_move = m
                beta = min(beta, value)
                if alpha >= beta:
                    break
            return value, best_move

    def best_move(self) -> tuple[int, int]:
        moves = get_valid_moves(self.board, self.valid, self.rows, self.cols)
        if not moves:
            return (0, 0)
        if len(moves) == 1:
            return moves[0]

        # Immediate win check (fast path)
        for r, c in moves:
            self.board[r][c] = self.me
            if check_win(self.board, self.lines, self.me):
                self.board[r][c] = EMPTY
                return (r, c)
            self.board[r][c] = EMPTY

        # Immediate block check (fast path)
        for r, c in moves:
            self.board[r][c] = self.opp
            if check_win(self.board, self.lines, self.opp):
                self.board[r][c] = EMPTY
                return (r, c)
            self.board[r][c] = EMPTY

        deadline = time.monotonic() + TIMEOUT

        # Adaptive depth based on number of valid cells
        valid_count = sum(1 for r in range(self.rows) for c in range(self.cols) if self.valid[r][c])
        if valid_count <= 9:
            max_depth = 30  # can solve small boards fully
        elif valid_count <= 14:
            max_depth = 14
        elif valid_count <= 20:
            max_depth = 10
        elif valid_count <= 30:
            max_depth = 7
        else:
            max_depth = 5

        best = moves[0]
        for depth in range(1, max_depth + 1):
            try:
                _, move = self.minimax(depth, float('-inf'), float('inf'), True, self.me, deadline)
                if move is not None:
                    best = move
            except TimeoutError:
                break
        return best


def run(name: str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    sock.connect((HOST, PORT))
    sock.sendall(f"{name}\n".encode())

    buf = ""

    def read_lines():
        nonlocal buf
        while '\n' not in buf:
            data = sock.recv(8192)
            if not data:
                raise ConnectionError("Server closed")
            buf += data.decode()

    def next_line() -> str:
        nonlocal buf
        read_lines()
        line, buf = buf.split('\n', 1)
        return line.strip()

    games: dict[int, Optional[GameState]] = {1: None, 2: None}

    while True:
        line = next_line()
        if not line:
            continue

        if line.startswith("ROUND "):
            # Read BOARD section
            board_lines = []
            _header = next_line()  # "BOARD"
            while True:
                bl = next_line()
                if bl == "END":
                    break
                board_lines.append(bl)

            rows, cols, valid = parse_board(board_lines)
            win_lines = find_lines(rows, cols, valid)

            # Read GAME1 and GAME2 assignments
            g1_parts = next_line().split()  # GAME1 X|O
            g2_parts = next_line().split()  # GAME2 X|O
            g1_role = g1_parts[1]
            g2_role = g2_parts[1]

            g1 = GameState(rows, cols, valid, win_lines)
            g2 = GameState(rows, cols, valid, win_lines)
            g1.me, g1.opp = (ME, OPP) if g1_role == 'X' else (OPP, ME)
            g2.me, g2.opp = (ME, OPP) if g2_role == 'X' else (OPP, ME)

            games[1] = g1
            games[2] = g2

        elif line.startswith("YOURTURN "):
            game_num = int(line.split()[1])
            g = games.get(game_num)
            if g and not g.game_over:
                r, c = g.best_move()
                g.make_move(r, c, g.me)
                sock.sendall(f"{r} {c}\n".encode())

        elif line.startswith("OPPONENT "):
            parts = line.split()
            game_num = int(parts[1])
            r, c = int(parts[2]), int(parts[3])
            g = games.get(game_num)
            if g:
                g.make_move(r, c, g.opp)

        elif line.startswith("RESULT "):
            parts = line.split()
            game_num = int(parts[1].replace("GAME", ""))
            g = games.get(game_num)
            if g:
                g.game_over = True

        elif line.startswith("ROUND_SCORE"):
            pass

        elif line.startswith("MATCHUP"):
            games[1] = None
            games[2] = None

        elif line in ("TOURNAMENT_OVER", "BYE"):
            break

    sock.close()


if __name__ == "__main__":
    bot_name = sys.argv[1] if len(sys.argv) > 1 else "mimo_bot"
    run(bot_name)