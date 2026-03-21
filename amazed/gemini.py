import socket
import sys
import collections

class MazeBot:
    def __init__(self, host='localhost', port=7474, bot_name='gemini_bot'):
        self.host = host
        self.port = port
        self.bot_name = bot_name
        self.sock = None
        self.f_in = None
        self.f_out = None
        
        # Internal State
        self.map = {}         # (r, c) -> char ('#', ' ', '>', '<', or 'A'-'Z')
        self.teleporters = {} # (r, c) -> (dest_r, dest_c) mappings
        self.pos = (1, 1)     # Absolute coordinates; spec says Start '>' is at (1,1)

    def connect(self):
        """Establish connection and register the bot."""
        print(f"Connecting to {self.host}:{self.port}...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        
        # Using makefile to easily read line-by-line and handle buffers
        self.f_in = self.sock.makefile('r', encoding='utf-8')
        self.f_out = self.sock.makefile('w', encoding='utf-8')
        
        self.f_out.write(f"{self.bot_name}\n")
        self.f_out.flush()
        print(f"Registered as {self.bot_name}")

    def read_view(self, first_line=None):
        """Reads exactly 5 lines from the server to construct the 5x5 view."""
        view = []
        if first_line:
            view.append(first_line.rstrip('\n'))
        while len(view) < 5:
            line = self.f_in.readline()
            if not line:
                break
            view.append(line.rstrip('\n'))
        return view

    def update_map(self, view):
        """Updates the internal map based on the 5x5 grid centered on self.pos."""
        if len(view) < 5:
            return
            
        for i in range(5):
            for j in range(5):
                # Ensure we don't go out of bounds if a line is malformed
                if j >= len(view[i]): continue 
                
                char = view[i][j]
                if char != '?': # Ignore fog
                    r = self.pos[0] + i - 2
                    c = self.pos[1] + j - 2
                    self.map[(r, c)] = char

    def get_next_move(self):
        """Determines the best next move using BFS."""
        # 1. Check if we have discovered the exit
        exit_pos = None
        for p, char in self.map.items():
            if char == '<':
                exit_pos = p
                break

        if exit_pos:
            path = self._bfs_to_targets([exit_pos])
            if path: 
                return path[0]

        # 2. If exit is unknown, find all 'frontiers'
        # A frontier is a known walkable cell that has an adjacent unexplored cell
        frontiers = []
        for p, char in self.map.items():
            if char != '#':
                is_frontier = False
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    if (p[0] + dr, p[1] + dc) not in self.map:
                        is_frontier = True
                        break
                if is_frontier:
                    frontiers.append(p)

        if not frontiers:
            return 'D' # Fallback if map is fully explored but no exit found (shouldn't happen)

        # 3. Pathfind to the best frontier
        return self._bfs_to_best_frontier(frontiers)

    def _bfs_to_targets(self, targets):
        """Standard BFS to find the shortest path to a set of target coordinates."""
        target_set = set(targets)
        queue = collections.deque([(self.pos, [])])
        visited = {self.pos}

        while queue:
            curr, path = queue.popleft()

            if curr in target_set:
                return path

            for dr, dc, move_char in [(-1, 0, 'U'), (1, 0, 'D'), (0, -1, 'L'), (0, 1, 'R')]:
                nxt = (curr[0] + dr, curr[1] + dc)

                if nxt in self.map and self.map[nxt] != '#':
                    # Handle known teleporters
                    actual_nxt = self.teleporters.get(nxt, nxt)

                    if actual_nxt not in visited:
                        visited.add(actual_nxt)
                        queue.append((actual_nxt, path + [move_char]))
        return []

    def _bfs_to_best_frontier(self):
        """Finds the shortest path to all reachable frontiers, then scores them."""
        queue = collections.deque([(self.pos, [])])
        visited = {self.pos}
        frontiers_found = []

        while queue:
            curr, path = queue.popleft()

            # Check if current node is a frontier
            if curr in self.map and self.map[curr] != '#':
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    if (curr[0] + dr, curr[1] + dc) not in self.map:
                        frontiers_found.append((path, curr))
                        break # Only add it once

            for dr, dc, move_char in [(-1, 0, 'U'), (1, 0, 'D'), (0, -1, 'L'), (0, 1, 'R')]:
                nxt = (curr[0] + dr, curr[1] + dc)

                if nxt in self.map and self.map[nxt] != '#':
                    actual_nxt = self.teleporters.get(nxt, nxt)

                    if actual_nxt not in visited:
                        visited.add(actual_nxt)
                        queue.append((actual_nxt, path + [move_char]))

        if not frontiers_found:
            return 'R' # Fallback

        # Heuristic: Bias heavily towards the bottom right (max r + c)
        # Score = (Distance) - (r + c) * Weight. Lower score is better.
        best_path = None
        best_score = float('inf')
        
        for path, f_pos in frontiers_found:
            if not path: continue # Already standing on a frontier
            score = len(path) - (f_pos[0] + f_pos[1]) * 2.0
            if score < best_score:
                best_score = score
                best_path = path

        return best_path[0] if best_path else 'D'

    def play(self):
        """Main event loop."""
        try:
            while True:
                line = self.f_in.readline()
                if not line: break
                
                if line.startswith("ROUND"):
                    print(f"--- Starting {line.strip()} ---")
                    # Reset round state
                    self.map.clear()
                    self.teleporters.clear()
                    self.pos = (1, 1)
                    
                    # Read initial 5x5 view
                    view = self.read_view()
                    self.update_map(view)
                    self.run_turn_loop()
                elif line.startswith("ELIMINATED") or line.startswith("DONE"):
                    # Catch-all if server sends this outside of the turn loop
                    print(line.strip())
        except KeyboardInterrupt:
            print("\nDisconnected by user.")
        finally:
            if self.sock:
                self.sock.close()

    def run_turn_loop(self):
        """Handles the turn-by-turn dialogue for a single round."""
        while True:
            move = self.get_next_move()
            self.f_out.write(move + '\n')
            self.f_out.flush()

            resp = self.f_in.readline()
            if not resp: return

            if resp.startswith("WALL"):
                # Register the wall just in case, though our map should prevent this
                dr, dc = {'U': (-1, 0), 'D': (1, 0), 'L': (0, -1), 'R': (0, 1)}[move]
                self.map[(self.pos[0] + dr, self.pos[1] + dc)] = '#'
                continue

            elif resp.startswith("DONE"):
                print(f"Success! {resp.strip()}")
                break

            elif resp.startswith("ELIMINATED"):
                print(f"Failed: {resp.strip()}")
                break

            elif resp.startswith("TELEPORT"):
                # Parse: TELEPORT {r} {c}
                parts = resp.strip().split()
                new_r, new_c = int(parts[1]), int(parts[2])
                
                # Determine which cell triggered the teleport
                dr, dc = {'U': (-1, 0), 'D': (1, 0), 'L': (0, -1), 'R': (0, 1)}[move]
                portal_entrance = (self.pos[0] + dr, self.pos[1] + dc)
                
                # Bi-directional mapping so A* can use the shortcut later
                self.teleporters[portal_entrance] = (new_r, new_c)
                self.teleporters[(new_r, new_c)] = portal_entrance

                # Update state and absorb the new view
                self.pos = (new_r, new_c)
                view = self.read_view()
                self.update_map(view)

            else:
                # Valid move (no teleport, not done, not wall). 
                # The line read is the first line of the new 5x5 view.
                dr, dc = {'U': (-1, 0), 'D': (1, 0), 'L': (0, -1), 'R': (0, 1)}[move]
                self.pos = (self.pos[0] + dr, self.pos[1] + dc)
                
                view = self.read_view(first_line=resp)
                self.update_map(view)


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 7474
    
    bot = MazeBot(host=host, port=port)
    bot.connect()
    bot.play()