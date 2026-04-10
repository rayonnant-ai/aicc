import socket
import sys
import time

class Game:
    def __init__(self, grid, my_role):
        self.grid = [list(row) for row in grid]
        self.R = len(self.grid)
        self.C = len(self.grid[0])
        self.my_role = my_role
        self.opp_role = 'O' if my_role == 'X' else 'X'
        
        self.empty_cells = set()
        self.valid_lines = []
        
        # 1. Map empty cells
        for r in range(self.R):
            for c in range(self.C):
                if self.grid[r][c] == '_':
                    self.empty_cells.add((r, c))
                    
        # 2. Precompute all valid winning lines on this specific blob shape.
        # A valid line requires 3 connected cells (holes '.' break connections).
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        for r in range(self.R):
            for c in range(self.C):
                if self.grid[r][c] == '.':
                    continue
                for dr, dc in directions:
                    line = []
                    valid = True
                    for i in range(3):
                        nr, nc = r + dr * i, c + dc * i
                        if 0 <= nr < self.R and 0 <= nc < self.C and self.grid[nr][nc] != '.':
                            line.append((nr, nc))
                        else:
                            valid = False
                            break
                    if valid:
                        self.valid_lines.append(line)
                        
        # 3. Create a move ordering heuristic to speed up Alpha-Beta pruning.
        # Cells that belong to more potential winning lines are evaluated first.
        self.move_order = {}
        for line in self.valid_lines:
            for cell in line:
                self.move_order[cell] = self.move_order.get(cell, 0) + 1

    def apply_move(self, r, c, role):
        if (r, c) in self.empty_cells:
            self.empty_cells.remove((r, c))
            self.grid[r][c] = role

    def undo_move(self, r, c):
        self.empty_cells.add((r, c))
        self.grid[r][c] = '_'

    def evaluate(self):
        score = 0
        for line in self.valid_lines:
            my_count = 0
            opp_count = 0
            for r, c in line:
                if self.grid[r][c] == self.my_role:
                    my_count += 1
                elif self.grid[r][c] == self.opp_role:
                    opp_count += 1
                    
            if my_count == 3: return 10000
            if opp_count == 3: return -10000
            
            # Heuristic scoring for partial lines
            if my_count > 0 and opp_count == 0:
                if my_count == 2: score += 10
                elif my_count == 1: score += 1
            elif opp_count > 0 and my_count == 0:
                if opp_count == 2: score -= 10
                elif opp_count == 1: score -= 1
        return score

    def minimax(self, depth, alpha, beta, is_maximizing, start_time):
        # Abort search safely before the 2.0s server timeout hits
        if time.time() - start_time > 1.8:
            raise TimeoutError()
            
        state_score = self.evaluate()
        
        # We add/subtract depth to strongly prefer faster wins and slower losses
        if state_score >= 10000:
            return state_score + depth, None
        if state_score <= -10000:
            return state_score - depth, None
            
        if depth == 0 or not self.empty_cells:
            return state_score, None

        best_move = None
        # Sort moves based on our precomputed heatmap to maximize pruning efficiency
        moves = list(self.empty_cells)
        moves.sort(key=lambda m: self.move_order.get(m, 0), reverse=True)
        
        if is_maximizing:
            max_eval = -float('inf')
            for move in moves:
                r, c = move
                self.apply_move(r, c, self.my_role)
                eval_score, _ = self.minimax(depth - 1, alpha, beta, False, start_time)
                self.undo_move(r, c)
                
                if eval_score > max_eval:
                    max_eval = eval_score
                    best_move = move
                alpha = max(alpha, eval_score)
                if beta <= alpha:
                    break
            return max_eval, best_move
        else:
            min_eval = float('inf')
            for move in moves:
                r, c = move
                self.apply_move(r, c, self.opp_role)
                eval_score, _ = self.minimax(depth - 1, alpha, beta, True, start_time)
                self.undo_move(r, c)
                
                if eval_score < min_eval:
                    min_eval = eval_score
                    best_move = move
                beta = min(beta, eval_score)
                if beta <= alpha:
                    break
            return min_eval, best_move

    def get_best_move(self):
        start_time = time.time()
        best_move = None
        
        if not self.empty_cells:
            return (0, 0) # Failsafe
            
        # Iterative Deepening: Search deeper until we run out of time
        for depth in range(1, len(self.empty_cells) + 1):
            try:
                score, move = self.minimax(depth, -float('inf'), float('inf'), True, start_time)
                if move is not None:
                    best_move = move
                # Stop deepening early if we have found a guaranteed forced win
                if score >= 10000:
                    break
            except TimeoutError:
                # Time's up! Drop the current incomplete search and use the best move from the previous depth
                break
                
        if best_move is None:
            return list(self.empty_cells)[0]
        return best_move

def main():
    host = 'localhost'
    port = 7474

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        print(f"[*] Connected to {host}:{port}")
        
        # Registration
        bot_name = "gemini_bot\n"
        sock.sendall(bot_name.encode())
        print(f"[*] Registered as {bot_name.strip()}")
        
        # We read by lines to easily handle the custom text-based protocol
        f = sock.makefile('r')
        
        game1 = None
        game2 = None
        board_grid = []
        
        while True:
            line = f.readline()
            if not line: break
            line = line.strip()
            if not line: continue
            
            parts = line.split()
            cmd = parts[0]
            
            if cmd == "ROUND":
                print(f"\n--- {line} ---")
                board_grid = []
                
            elif cmd == "BOARD":
                while True:
                    b_line = f.readline().strip()
                    if b_line == "END": break
                    # Strip any spaces just in case the server pads it
                    b_line = b_line.replace(" ", "")
                    board_grid.append(b_line)
                    
            elif cmd.startswith("GAME"):
                g_idx = cmd[-1] # Pulls '1' or '2'
                role = parts[1]
                if g_idx == '1':
                    game1 = Game(board_grid, role)
                else:
                    game2 = Game(board_grid, role)
                print(f"[*] Assigned to {cmd} as {role}")
                
            elif cmd == "YOURTURN":
                g_idx = parts[1]
                game = game1 if g_idx == '1' else game2
                
                print(f"[*] Thinking for GAME {g_idx}...")
                r, c = game.get_best_move()
                game.apply_move(r, c, game.my_role)
                
                print(f"[+] Moving at ({r}, {c})")
                sock.sendall(f"{r} {c}\n".encode())
                
            elif cmd == "OPPONENT":
                g_idx = parts[1]
                r, c = int(parts[2]), int(parts[3])
                game = game1 if g_idx == '1' else game2
                print(f"[-] Opponent moved at ({r}, {c}) in GAME {g_idx}")
                game.apply_move(r, c, game.opp_role)
                
            elif cmd in ("RESULT", "ROUND_SCORE", "MATCHUP"):
                print(f"[!] {line}")
                if cmd == "MATCHUP":
                    print("[*] Matchup complete. Awaiting next matchup or server closure...")

    except ConnectionRefusedError:
        print("[!] Connection refused. Make sure the server is running.")
    except KeyboardInterrupt:
        print("\n[*] Disconnecting...")
    finally:
        sock.close()

if __name__ == "__main__":
    main()