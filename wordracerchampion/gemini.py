import socket
import sys

class RobotWordRacer:
    def __init__(self, host='localhost', port=7474, name="GeminiBot"):
        self.host = host
        self.port = port
        self.name = name
        self.trie = {}  # Prefix tree for rapid lookup
        self.words_found = set()

    def load_dictionary(self, filepath='dictionary.txt'):
        """Loads words into a Trie structure for efficient prefix searching."""
        print(f"Loading {filepath}...")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    word = line.strip().upper()
                    if len(word) < 3:
                        continue
                    node = self.trie
                    for char in word:
                        node = node.setdefault(char, {})
                    node['#'] = True  # Leaf marker
            print("Dictionary loaded successfully.")
        except FileNotFoundError:
            print(f"Error: {filepath} not found.")
            sys.exit(1)

    def solve_grid(self, grid_str, sock):
        """Standard DFS with Trie pruning to find all valid words on the 15x15 grid."""
        grid = [list(grid_str[i:i+15]) for i in range(0, 225, 15)]
        rows, cols = 15, 15
        
        def get_neighbors(r, c):
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0: continue
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols:
                        yield nr, nc

        def dfs(r, c, node, path, visited):
            char = grid[r][c]
            if char not in node:
                return
            
            next_node = node[char]
            new_path = path + char
            
            # If it's a valid word and not already sent by us
            if '#' in next_node and new_path not in self.words_found:
                if self.submit_word(sock, new_path):
                    self.words_found.add(new_path)
                else:
                    return False # Game ended

            visited.add((r, c))
            for nr, nc in get_neighbors(r, c):
                if (nr, nc) not in visited:
                    if not dfs(nr, nc, next_node, new_path, visited):
                        return False
            visited.remove((r, c))
            return True

        for r in range(rows):
            for c in range(cols):
                if not dfs(r, c, self.trie, "", set()):
                    return # Exit solving if server signals game over

    def submit_word(self, sock, word):
        """Sends word to server and listens for response code."""
        try:
            sock.sendall(f"{word}\n".encode('utf-8'))
            response = sock.recv(1024).decode('utf-8').strip()
            if response == '1':
                print("Game ended or Disqualified.")
                return False
            return True
        except (ConnectionResetError, BrokenPipeError):
            return False

    def run(self):
        self.load_dictionary()
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.connect((self.host, self.port))
                # Identification
                s.sendall(f"{self.name}\n".encode('utf-8'))
                
                # Receive Grid (225 chars + \n)
                # Using a loop to ensure we get the full 226 bytes
                data = b""
                while len(data) < 226:
                    chunk = s.recv(226 - len(data))
                    if not chunk: break
                    data += chunk
                
                grid_str = data.decode('utf-8').strip()
                if len(grid_str) == 225:
                    print("Grid received. Racing...")
                    self.solve_grid(grid_str, s)
                
            except Exception as e:
                print(f"Connection error: {e}")
            finally:
                print("Client shutting down.")

if __name__ == "__main__":
    bot = RobotWordRacer()
    bot.run()