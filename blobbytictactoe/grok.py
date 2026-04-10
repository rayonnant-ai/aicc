import socket
import sys

def get_winning_lines(R, C, shape):
    """Precompute all possible 3-in-a-row lines on the given shape.
    Only lines where all 3 cells are valid (not holes) are included.
    """
    lines = []
    for r in range(R):
        for c in range(C):
            if shape[r][c] == '.':
                continue
            # Horizontal
            if c + 2 < C and shape[r][c + 1] != '.' and shape[r][c + 2] != '.':
                lines.append([(r, c), (r, c + 1), (r, c + 2)])
            # Vertical
            if r + 2 < R and shape[r + 1][c] != '.' and shape[r + 2][c] != '.':
                lines.append([(r, c), (r + 1, c), (r + 2, c)])
            # Diagonal down-right
            if r + 2 < R and c + 2 < C and shape[r + 1][c + 1] != '.' and shape[r + 2][c + 2] != '.':
                lines.append([(r, c), (r + 1, c + 1), (r + 2, c + 2)])
            # Diagonal down-left
            if r + 2 < R and c - 2 >= 0 and shape[r + 1][c - 1] != '.' and shape[r + 2][c - 2] != '.':
                lines.append([(r, c), (r + 1, c - 1), (r + 2, c - 2)])
    return lines

def get_valid_positions(R, C, shape):
    """List of all valid (non-hole) positions."""
    return [(r, c) for r in range(R) for c in range(C) if shape[r][c] != '.']

def check_win(board, player, winning_lines):
    """Check if player has any winning line."""
    for line in winning_lines:
        if all(board[rr][cc] == player for rr, cc in line):
            return True
    return False

def is_full(board, R, C, valid_positions):
    """Check if no empty valid cells remain."""
    for r, c in valid_positions:
        if board[r][c] == ' ':
            return False
    return True

def evaluate(board, my_mark, winning_lines, valid_positions, R, C):
    """Return 1 if my_mark wins, -1 if opponent wins, 0 for draw, None if ongoing."""
    if check_win(board, my_mark, winning_lines):
        return 1
    opp_mark = 'O' if my_mark == 'X' else 'X'
    if check_win(board, opp_mark, winning_lines):
        return -1
    if is_full(board, R, C, valid_positions):
        return 0
    return None

def minimax(board, is_maximizing, my_mark, winning_lines, valid_positions, R, C, alpha=-float('inf'), beta=float('inf')):
    """Alpha-beta minimax. Score from perspective of my_mark."""
    score = evaluate(board, my_mark, winning_lines, valid_positions, R, C)
    if score is not None:
        return score

    best_score = -float('inf') if is_maximizing else float('inf')
    opp_mark = 'O' if my_mark == 'X' else 'X'
    current_mark = my_mark if is_maximizing else opp_mark

    for r, c in valid_positions:
        if board[r][c] == ' ':
            board[r][c] = current_mark
            val = minimax(board, not is_maximizing, my_mark, winning_lines, valid_positions, R, C, alpha, beta)
            board[r][c] = ' '
            if is_maximizing:
                best_score = max(best_score, val)
                alpha = max(alpha, best_score)
            else:
                best_score = min(best_score, val)
                beta = min(beta, best_score)
            if beta <= alpha:
                break  # Prune remaining branches
    return best_score

def get_best_move(board, my_mark, winning_lines, valid_positions, R, C):
    """Find best move using minimax. First check for immediate wins, then full search."""
    opp_mark = 'O' if my_mark == 'X' else 'X'
    best_score = -float('inf')
    best_move = None

    # 1. Immediate win check (depth 1)
    for r, c in valid_positions:
        if board[r][c] == ' ':
            board[r][c] = my_mark
            if check_win(board, my_mark, winning_lines):
                board[r][c] = ' '
                return (r, c)  # Instant win
            board[r][c] = ' '

    # 2. Block opponent immediate win
    for r, c in valid_positions:
        if board[r][c] == ' ':
            board[r][c] = opp_mark
            if check_win(board, opp_mark, winning_lines):
                board[r][c] = ' '
                return (r, c)  # Must block
            board[r][c] = ' '

    # 3. Full minimax for best score
    for r, c in valid_positions:
        if board[r][c] == ' ':
            board[r][c] = my_mark
            score = minimax(board, False, my_mark, winning_lines, valid_positions, R, C)
            board[r][c] = ' '
            if score > best_score:
                best_score = score
                best_move = (r, c)

    # Fallback: any valid move (should never reach if board not full)
    if best_move is None:
        for r, c in valid_positions:
            if board[r][c] == ' ':
                return (r, c)
    return best_move

def main():
    bot_name = "grok_bot"  # Change only if you want a different name

    print(f"Starting {bot_name}...")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 7474))
    s.sendall(f"{bot_name}\n".encode('utf-8'))

    f = s.makefile('r', encoding='utf-8', newline=None)

    # Per-round state
    R = C = 0
    winning_lines = []
    valid_positions = []
    game_boards = [None, None]   # 0 = GAME1, 1 = GAME2
    my_roles = [None, None]

    while True:
        line = f.readline()
        if not line:
            print("Server closed connection.")
            break
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        cmd = parts[0]

        if cmd == "ROUND":
            round_num = int(parts[1])
            print(f"\n=== Round {round_num} starting ===")

            # Read BOARD
            board_lines = []
            while True:
                bline = f.readline().strip()
                if bline == "END":
                    break
                board_lines.append(bline)

            R = len(board_lines)
            C = len(board_lines[0]) if R > 0 else 0
            shape = [list(row) for row in board_lines]

            # Normalize shape: _ → ' '
            for r in range(R):
                for c in range(C):
                    if shape[r][c] == '_':
                        shape[r][c] = ' '

            # Precompute for this round (same for both games)
            winning_lines = get_winning_lines(R, C, shape)
            valid_positions = get_valid_positions(R, C, shape)

            # Create fresh boards for both games
            game_boards[0] = [row[:] for row in shape]
            game_boards[1] = [row[:] for row in shape]

            # Read GAME1 and GAME2 assignments
            for g in range(2):
                gline = f.readline().strip()
                while not gline:
                    gline = f.readline().strip()
                gparts = gline.split()
                if gparts[0].startswith("GAME"):
                    game_id = int(gparts[0][4:]) - 1
                    my_roles[game_id] = gparts[1]
            print(f"Roles → Game1: {my_roles[0]} | Game2: {my_roles[1]}")

        elif cmd == "YOURTURN":
            game_id = int(parts[1]) - 1
            board = game_boards[game_id]
            my_mark = my_roles[game_id]

            move = get_best_move(board, my_mark, winning_lines, valid_positions, R, C)
            r, c = move

            # Apply my move locally immediately
            board[r][c] = my_mark

            # Send move
            s.sendall(f"{r} {c}\n".encode('utf-8'))
            print(f"→ Moved in Game{game_id+1}: ({r}, {c}) as {my_mark}")

        elif cmd == "OPPONENT":
            game_id = int(parts[1]) - 1
            r = int(parts[2])
            c = int(parts[3])
            board = game_boards[game_id]
            opp_mark = 'O' if my_roles[game_id] == 'X' else 'X'
            board[r][c] = opp_mark
            print(f"← Opponent moved in Game{game_id+1}: ({r}, {c})")

        elif cmd == "RESULT":
            game_str = parts[1]
            game_id = int(game_str[4:]) - 1
            outcome = parts[2]
            print(f"Game{game_id+1} ended: {outcome}")

        elif cmd == "ROUND_SCORE":
            my_pts = int(parts[1])
            opp_pts = int(parts[2])
            print(f"Round score → You: {my_pts} | Opponent: {opp_pts}")

        elif cmd == "MATCHUP":
            outcome = parts[1]
            my_total = int(parts[2])
            opp_total = int(parts[3])
            print(f"\n*** MATCHUP RESULT: {outcome} (You {my_total} - Opponent {opp_total}) ***\n")

        else:
            print(f"Unknown command: {line}")

    s.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBot terminated by user.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)