import socket
import sys
import threading

HOST = "localhost"
PORT = 7474
NAME = "ChatGPTBot"

GRID_SIZE = 15
MIN_WORD_LEN = 3


# ----------------------------
# Trie Implementation
# ----------------------------
class TrieNode:
    __slots__ = ("children", "is_word")

    def __init__(self):
        self.children = {}
        self.is_word = False


def load_dictionary(path):
    root = TrieNode()
    with open(path, "r") as f:
        for line in f:
            word = line.strip().upper()
            if len(word) < MIN_WORD_LEN:
                continue
            node = root
            for ch in word:
                node = node.children.setdefault(ch, TrieNode())
            node.is_word = True
    return root


# ----------------------------
# Grid Solver
# ----------------------------
class Solver:
    def __init__(self, grid, trie, send_word):
        self.grid = grid
        self.trie = trie
        self.send_word = send_word

        self.visited = [False] * (GRID_SIZE * GRID_SIZE)
        self.found = set()

        # Precompute neighbors
        self.neighbors = [[] for _ in range(GRID_SIZE * GRID_SIZE)]
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                idx = r * GRID_SIZE + c
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE:
                            self.neighbors[idx].append(nr * GRID_SIZE + nc)

    def solve(self):
        for i in range(GRID_SIZE * GRID_SIZE):
            ch = self.grid[i]
            if ch in self.trie.children:
                self._dfs(i, self.trie.children[ch], ch)

    def _dfs(self, idx, node, prefix):
        if node.is_word and prefix not in self.found:
            self.found.add(prefix)
            self.send_word(prefix)

        self.visited[idx] = True

        for nxt in self.neighbors[idx]:
            if not self.visited[nxt]:
                ch = self.grid[nxt]
                if ch in node.children:
                    self._dfs(nxt, node.children[ch], prefix + ch)

        self.visited[idx] = False


# ----------------------------
# Network Client
# ----------------------------
class Client:
    def __init__(self, trie):
        self.trie = trie
        self.sock = None
        self.alive = True

    def connect(self):
        self.sock = socket.create_connection((HOST, PORT))
        self.sock.sendall((NAME + "\n").encode())

    def recv_line(self):
        data = b""
        while not data.endswith(b"\n"):
            chunk = self.sock.recv(4096)
            if not chunk:
                return None
            data += chunk
        return data.decode().strip()

    def send_word(self, word):
        if not self.alive:
            return
        try:
            self.sock.sendall((word + "\n").encode())
        except:
            self.alive = False

    def listen_responses(self):
        while self.alive:
            resp = self.recv_line()
            if resp is None:
                break
            if resp == "1":
                self.alive = False
                break
        self.sock.close()

    def run(self):
        self.connect()

        # Receive grid
        grid_line = self.recv_line()
        if grid_line is None or len(grid_line) != GRID_SIZE * GRID_SIZE:
            print("Invalid grid")
            return

        grid = list(grid_line)

        # Start response listener thread
        t = threading.Thread(target=self.listen_responses, daemon=True)
        t.start()

        # Solve grid
        solver = Solver(grid, self.trie, self.send_word)
        solver.solve()

        # Wait until server ends or disconnects
        t.join()


# ----------------------------
# Main Entry
# ----------------------------
def main():
    print("Loading dictionary...")
    trie = load_dictionary("dictionary.txt")
    print("Dictionary loaded.")

    client = Client(trie)
    client.run()


if __name__ == "__main__":
    main()