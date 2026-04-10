#!/usr/bin/env python3
"""Blobby Tic-Tac-Toe bot — minimax with alpha-beta pruning."""

import socket
import sys
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Board helpers
# ---------------------------------------------------------------------------

def parse_board(lines: list[str]) -> list[list[str]]:
    return [list(row) for row in lines]


def find_winning_lines(board: list[list[str]]) -> list[list[tuple[int, int]]]:
    """Return all lines of 3 consecutive valid cells (no holes between them)."""
    rows, cols = len(board), len(board[0])
    lines: list[list[tuple[int, int]]] = []
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]  # horiz, vert, diag-down-right, diag-down-left

    for r in range(rows):
        for c in range(cols):
            if board[r][c] == '.':
                continue
            for dr, dc in directions:
                cells: list[tuple[int, int]] = []
                ok = True
                for step in range(3):
                    nr, nc = r + dr * step, c + dc * step
                    if 0 <= nr < rows and 0 <= nc < cols and board[nr][nc] != '.':
                        cells.append((nr, nc))
                    else:
                        ok = False
                        break
                if ok and len(cells) == 3:
                    lines.append(cells)
    return lines


def get_valid_cells(board: list[list[str]]) -> list[tuple[int, int]]:
    return [(r, c) for r in range(len(board)) for c in range(len(board[0])) if board[r][c] != '.']


# ---------------------------------------------------------------------------
# Game state for one game
# ---------------------------------------------------------------------------

class Game:
    def __init__(self, board_template: list[list[str]], my_mark: str):
        self.board = [row[:] for row in board_template]
        self.my_mark = my_mark  # 'X' or 'O'
        self.opp_mark = 'O' if my_mark == 'X' else 'X'
        self.lines = find_winning_lines(board_template)
        self.valid_cells = set(get_valid_cells(board_template))
        self.empty_cells: set[tuple[int, int]] = set(
            (r, c) for r, c in self.valid_cells
        )
        self.finished = False

    def apply_move(self, r: int, c: int, mark: str):
        self.board[r][c] = mark
        self.empty_cells.discard((r, c))

    def check_winner(self) -> Optional[str]:
        for line in self.lines:
            marks = [self.board[r][c] for r, c in line]
            if marks[0] in ('X', 'O') and marks[0] == marks[1] == marks[2]:
                return marks[0]
        return None

    def is_draw(self) -> bool:
        return len(self.empty_cells) == 0 and self.check_winner() is None

    # ------------------------------------------------------------------
    # Minimax with alpha-beta
    # ------------------------------------------------------------------

    def evaluate(self) -> int:
        """Return +10 if my_mark wins, -10 if opp wins, 0 otherwise."""
        w = self.check_winner()
        if w == self.my_mark:
            return 10
        if w == self.opp_mark:
            return -10
        return 0

    def _score_line(self, line: list[tuple[int, int]]) -> int:
        """Heuristic score for a single line from my perspective."""
        marks = [self.board[r][c] for r, c in line]
        my, opp, empty = 0, 0, 0
        for m in marks:
            if m == self.my_mark:
                my += 1
            elif m == self.opp_mark:
                opp += 1
            else:
                empty += 1
        if my > 0 and opp > 0:
            return 0  # contested
        if my == 3:
            return 100
        if opp == 3:
            return -100
        if my == 2 and empty == 1:
            return 10
        if opp == 2 and empty == 1:
            return -10
        if my == 1 and empty == 2:
            return 1
        if opp == 1 and empty == 2:
            return -1
        return 0

    def heuristic(self) -> int:
        return sum(self._score_line(l) for l in self.lines)

    def ordered_moves(self, is_maximizing: bool) -> list[tuple[int, int]]:
        """Return empty cells ordered by heuristic value for better pruning."""
        mark = self.my_mark if is_maximizing else self.opp_mark
        moves = list(self.empty_cells)
        scores: list[tuple[int, tuple[int, int]]] = []
        for r, c in moves:
            self.board[r][c] = mark
            self.empty_cells.discard((r, c))
            h = self.heuristic()
            self.board[r][c] = '_'
            self.empty_cells.add((r, c))
            scores.append((h, (r, c)))
        scores.sort(key=lambda x: x[0], reverse=is_maximizing)
        return [m for _, m in scores]

    def minimax(self, depth: int, is_maximizing: bool, alpha: float, beta: float,
                deadline: float) -> float:
        winner = self.check_winner()
        if winner == self.my_mark:
            return 10 + depth  # prefer faster wins
        if winner == self.opp_mark:
            return -10 - depth
        if not self.empty_cells:
            return 0
        if depth <= 0 or time.monotonic() > deadline:
            return self.heuristic() / 100.0  # scale heuristic to be < |10|

        if is_maximizing:
            best = -float('inf')
            for r, c in self.ordered_moves(True):
                self.board[r][c] = self.my_mark
                self.empty_cells.discard((r, c))
                val = self.minimax(depth - 1, False, alpha, beta, deadline)
                self.board[r][c] = '_'
                self.empty_cells.add((r, c))
                best = max(best, val)
                alpha = max(alpha, val)
                if beta <= alpha:
                    break
            return best
        else:
            best = float('inf')
            for r, c in self.ordered_moves(False):
                self.board[r][c] = self.opp_mark
                self.empty_cells.discard((r, c))
                val = self.minimax(depth - 1, True, alpha, beta, deadline)
                self.board[r][c] = '_'
                self.empty_cells.add((r, c))
                best = min(best, val)
                beta = min(beta, val)
                if beta <= alpha:
                    break
            return best

    def best_move(self) -> tuple[int, int]:
        deadline = time.monotonic() + 1.5  # stay well within 2s

        # Immediate win / block check
        for r, c in self.empty_cells:
            self.board[r][c] = self.my_mark
            if self.check_winner() == self.my_mark:
                self.board[r][c] = '_'
                return (r, c)
            self.board[r][c] = '_'

        for r, c in self.empty_cells:
            self.board[r][c] = self.opp_mark
            if self.check_winner() == self.opp_mark:
                self.board[r][c] = '_'
                return (r, c)
            self.board[r][c] = '_'

        # Iterative deepening minimax
        n_empty = len(self.empty_cells)
        max_depth = min(n_empty, 20)
        best_action: Optional[tuple[int, int]] = None

        for depth in range(1, max_depth + 1):
            if time.monotonic() > deadline:
                break
            current_best = -float('inf')
            current_action: Optional[tuple[int, int]] = None
            for r, c in self.ordered_moves(True):
                if time.monotonic() > deadline:
                    break
                self.board[r][c] = self.my_mark
                self.empty_cells.discard((r, c))
                val = self.minimax(depth - 1, False, -float('inf'), float('inf'), deadline)
                self.board[r][c] = '_'
                self.empty_cells.add((r, c))
                if val > current_best:
                    current_best = val
                    current_action = (r, c)
            if current_action is not None:
                best_action = current_action

        if best_action is None:
            # fallback: pick any empty cell
            best_action = next(iter(self.empty_cells))
        return best_action


# ---------------------------------------------------------------------------
# Network client
# ---------------------------------------------------------------------------

class Client:
    def __init__(self, host: str, port: int, name: str):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.buf = ""
        self.name = name
        self.games: dict[int, Game] = {}

    def send(self, msg: str):
        self.sock.sendall((msg + "\n").encode())

    def readline(self) -> str:
        while "\n" not in self.buf:
            data = self.sock.recv(4096)
            if not data:
                raise ConnectionError("Server closed connection")
            self.buf += data.decode()
        line, self.buf = self.buf.split("\n", 1)
        return line.strip()

    def run(self):
        self.send(self.name)

        while True:
            try:
                line = self.readline()
            except ConnectionError:
                break

            if not line:
                continue

            if line.startswith("ROUND "):
                self._handle_round()

            elif line.startswith("YOURTURN"):
                game_id = int(line.split()[1])
                move = self.games[game_id].best_move()
                self.send(f"{move[0]} {move[1]}")
                self.games[game_id].apply_move(move[0], move[1], self.games[game_id].my_mark)

            elif line.startswith("OPPONENT"):
                parts = line.split()
                game_id = int(parts[1])
                r, c = int(parts[2]), int(parts[3])
                self.games[game_id].apply_move(r, c, self.games[game_id].opp_mark)

            elif line.startswith("RESULT GAME"):
                parts = line.split()
                game_id = int(parts[1].replace("GAME", ""))
                self.games[game_id].finished = True

            elif line.startswith("ROUND_SCORE"):
                pass  # info only

            elif line.startswith("MATCHUP"):
                # matchup done — loop to wait for next or disconnect
                self.games.clear()

    def _handle_round(self):
        # Read BOARD ... END
        board_lines: list[str] = []
        line = self.readline()
        assert line == "BOARD", f"Expected BOARD, got {line!r}"
        while True:
            line = self.readline()
            if line == "END":
                break
            board_lines.append(line)

        board = parse_board(board_lines)

        # Read GAME1 and GAME2
        g1_line = self.readline()
        g2_line = self.readline()
        mark1 = g1_line.split()[1]
        mark2 = g2_line.split()[1]

        self.games[1] = Game(board, mark1)
        self.games[2] = Game(board, mark2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    host = "localhost"
    port = 7474
    name = "claude_bot"

    if len(sys.argv) >= 2:
        name = sys.argv[1]
    if len(sys.argv) >= 3:
        host = sys.argv[2]
    if len(sys.argv) >= 4:
        port = int(sys.argv[3])

    client = Client(host, port, name)
    client.run()


if __name__ == "__main__":
    main()