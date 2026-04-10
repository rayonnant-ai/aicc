import socket
import random
import sys

HOST = 'localhost'
PORT = 7474

class BlobbyTicTacToeBot:
    def __init__(self, name):
        self.name = name
        self.socket = None
        self.board = []  # list of strings
        self.valid_cells = set()  # set of (r, c)
        self.winning_lines = []  # list of sets of three (r, c) tuples
        # Game state for the current round
        self.game1_X = set()
        self.game1_O = set()
        self.game2_X = set()
        self.game2_O = set()
        self.my_symbol_in_game1 = None
        self.my_symbol_in_game2 = None
        self.round_number = 0

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((HOST, PORT))
        # Send bot name
        self.socket.sendall(f"{self.name}\n".encode())

    def close(self):
        if self.socket:
            self.socket.close()

    def send_move(self, row, col):
        self.socket.sendall(f"{row} {col}\n".encode())

    def read_line(self):
        buffer = b""
        while True:
            data = self.socket.recv(1)
            if not data:
                return None
            buffer += data
            if buffer.endswith(b'\n'):
                return buffer.decode().strip()

    def compute_valid_cells(self, board_lines):
        valid = set()
        for r, line in enumerate(board_lines):
            for c, ch in enumerate(line):
                if ch != '.':
                    valid.add((r, c))
        return valid

    def compute_winning_lines(self, board_lines):
        lines = []
        R = len(board_lines)
        if R == 0:
            return lines
        C = len(board_lines[0])
        # Horizontal lines
        for r in range(R):
            for c in range(C - 2):
                if (r, c) in self.valid_cells and (r, c+1) in self.valid_cells and (r, c+2) in self.valid_cells:
                    lines.append({(r, c), (r, c+1), (r, c+2)})
        # Vertical lines
        for r in range(R - 2):
            for c in range(C):
                if (r, c) in self.valid_cells and (r+1, c) in self.valid_cells and (r+2, c) in self.valid_cells:
                    lines.append({(r, c), (r+1, c), (r+2, c)})
        # Diagonal down-right
        for r in range(R - 2):
            for c in range(C - 2):
                if (r, c) in self.valid_cells and (r+1, c+1) in self.valid_cells and (r+2, c+2) in self.valid_cells:
                    lines.append({(r, c), (r+1, c+1), (r+2, c+2)})
        # Diagonal up-right
        for r in range(2, R):
            for c in range(C - 2):
                if (r, c) in self.valid_cells and (r-1, c+1) in self.valid_cells and (r-2, c+2) in self.valid_cells:
                    lines.append({(r, c), (r-1, c+1), (r-2, c+2)})
        return lines

    def choose_move(self, game_num, symbol):
        # Determine my and opponent's sets for this game
        if game_num == 1:
            my_set = self.game1_X if symbol == 'X' else self.game1_O
            opp_set = self.game1_O if symbol == 'X' else self.game1_X
        else:
            my_set = self.game2_X if symbol == 'X' else self.game2_O
            opp_set = self.game2_O if symbol == 'X' else self.game2_X

        empty = self.valid_cells - (my_set | opp_set)
        if not empty:
            # Should not happen if game is not over, but fallback
            return next(iter(self.valid_cells)) if self.valid_cells else (0, 0)

        # First, check if we can win
        for line in self.winning_lines:
            line_set = set(line)
            my_in_line = line_set & my_set
            empty_in_line = line_set & empty
            if len(my_in_line) == 2 and len(empty_in_line) == 1:
                return (empty_in_line.pop())

        # Second, check if we need to block opponent's win
        for line in self.winning_lines:
            line_set = set(line)
            opp_in_line = line_set & opp_set
            empty_in_line = line_set & empty
            if len(opp_in_line) == 2 and len(empty_in_line) == 1:
                return (empty_in_line.pop())

        # Otherwise, choose a random empty cell
        return random.choice(list(empty))

    def update_own_move(self, game_num, row, col, symbol):
        if game_num == 1:
            if symbol == 'X':
                self.game1_X.add((row, col))
            else:
                self.game1_O.add((row, col))
        else:
            if symbol == 'X':
                self.game2_X.add((row, col))
            else:
                self.game2_O.add((row, col))

    def update_opponent_move(self, game_num, row, col):
        # Determine opponent's symbol in this game
        if game_num == 1:
            opp_symbol = 'O' if self.my_symbol_in_game1 == 'X' else 'X'
            if opp_symbol == 'X':
                self.game1_X.add((row, col))
            else:
                self.game1_O.add((row, col))
        else:
            opp_symbol = 'O' if self.my_symbol_in_game2 == 'X' else 'X'
            if opp_symbol == 'X':
                self.game2_X.add((row, col))
            else:
                self.game2_O.add((row, col))

    def run(self):
        try:
            self.connect()
            while True:
                line = self.read_line()
                if line is None:
                    break
                if line.startswith("ROUND"):
                    parts = line.split()
                    self.round_number = int(parts[1])
                    # Read board
                    board_lines = []
                    while True:
                        l = self.read_line()
                        if l == "END":
                            break
                        board_lines.append(l)
                    self.board = board_lines
                    self.valid_cells = self.compute_valid_cells(board_lines)
                    self.winning_lines = self.compute_winning_lines(board_lines)
                    # Read GAME1 and GAME2
                    game1_line = self.read_line()
                    game2_line = self.read_line()
                    self.my_symbol_in_game1 = game1_line.split()[1]
                    self.my_symbol_in_game2 = game2_line.split()[1]
                    # Reset game states for this round
                    self.game1_X.clear()
                    self.game1_O.clear()
                    self.game2_X.clear()
                    self.game2_O.clear()
                elif line.startswith("YOURTURN"):
                    parts = line.split()
                    game_num = int(parts[1])
                    if game_num == 1:
                        symbol = self.my_symbol_in_game1
                    else:
                        symbol = self.my_symbol_in_game2
                    row, col = self.choose_move(game_num, symbol)
                    self.send_move(row, col)
                    self.update_own_move(game_num, row, col, symbol)
                elif line.startswith("OPPONENT"):
                    parts = line.split()
                    game_num = int(parts[1])
                    row = int(parts[2])
                    col = int(parts[3])
                    self.update_opponent_move(game_num, row, col)
                elif line.startswith("RESULT"):
                    # We don't need to do anything, but we could log
                    pass
                elif line.startswith("ROUND_SCORE"):
                    pass
                elif line.startswith("MATCHUP"):
                    # Matchup over, reset for next matchup? The next ROUND will reinitialize.
                    pass
                else:
                    # Ignore other lines
                    pass
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
        finally:
            self.close()

if __name__ == "__main__":
    bot_name = "Nemo_bot"
    bot = BlobbyTicTacToeBot(bot_name)
    bot.run()