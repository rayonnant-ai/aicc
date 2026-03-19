import socket
import sys

class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_word = False

class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word):
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_word = True

def main():
    # Allow custom bot name via command-line argument (default: PythonWordRacer)
    name = "GrokBot"
    if len(sys.argv) > 1:
        name = sys.argv[1]
    name += "\n"

    # Load dictionary.txt into Trie (prefix pruning + exact word detection)
    trie = Trie()
    try:
        with open("dictionary.txt", "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip().upper()
                if len(word) >= 3:
                    trie.insert(word)
    except FileNotFoundError:
        print("Error: dictionary.txt not found in current directory.", file=sys.stderr)
        sys.exit(1)

    # Connect to server
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("localhost", 7474))
        sock.sendall(name.encode("utf-8"))

        # Receive exactly 225-character grid + newline
        data = b""
        while len(data) < 226:
            chunk = sock.recv(226 - len(data))
            if not chunk:
                print("Server closed connection during grid receive.", file=sys.stderr)
                return
            data += chunk

        grid_str = data[:225].decode("utf-8")
        if len(grid_str) != 225:
            print("Invalid grid length received.", file=sys.stderr)
            return

        # 2D grid for fast access
        grid = [[grid_str[i * 15 + j] for j in range(15)] for i in range(15)]

    except Exception as e:
        print(f"Connection error: {e}", file=sys.stderr)
        if sock:
            sock.close()
        return

    # 8 possible movement directions (horizontal, vertical, diagonal)
    directions = [
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1)
    ]

    found = set()

    def dfs(i, j, node, word, visited):
        """Depth-first search with immediate submission on valid word discovery."""
        # Check if current path forms a valid word (>=3 letters)
        if len(word) >= 3 and node.is_word and word not in found:
            found.add(word)
            try:
                sock.sendall((word + "\n").encode("utf-8"))
                # Server must reply with exactly one character + newline
                response = sock.recv(2)
                if not response or response[0] == ord("1"):
                    return True  # Game ended or disqualified
            except Exception:
                return True  # Connection issue

        # Extend in all 8 directions (no cell reuse in this word)
        for di, dj in directions:
            ni, nj = i + di, j + dj
            if 0 <= ni < 15 and 0 <= nj < 15 and not visited[ni][nj]:
                letter = grid[ni][nj]
                if letter in node.children:
                    next_node = node.children[letter]
                    visited[ni][nj] = True
                    if dfs(ni, nj, next_node, word + letter, visited):
                        return True  # Propagate stop signal
                    visited[ni][nj] = False
        return False

    # Start search from every possible tile
    for i in range(15):
        for j in range(15):
            letter = grid[i][j]
            if letter in trie.root.children:
                visited = [[False] * 15 for _ in range(15)]
                visited[i][j] = True
                if dfs(i, j, trie.root.children[letter], letter, visited):
                    break  # Game over signal received
        else:
            continue
        break  # Outer loop break if inner break occurred

    # Graceful shutdown
    try:
        sock.close()
    except:
        pass

if __name__ == "__main__":
    main()
