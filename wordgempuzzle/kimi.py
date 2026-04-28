#!/usr/bin/env python3
"""
Word Gem Puzzle — Tournament Bot
Standard library only. Connects to localhost:7474.
"""
import os
import select
import socket
import sys
import time


class TrieNode:
    __slots__ = ("children", "is_word", "word")

    def __init__(self):
        self.children = {}
        self.is_word = False
        self.word = None


class WordGemBot:
    def __init__(self):
        self.trie = TrieNode()
        self.sock = None
        self.rfile = None

        # Board state
        self.grid = []
        self.h = 0
        self.w = 0
        self.br = 0
        self.bc = 0

        # Round state
        self.claimed = set()
        self.min_len = 7          # Only words scoring +1 or better
        self.deadline = 0.0

    # --------------------------------------------------------------------- #
    #  Dictionary
    # --------------------------------------------------------------------- #
    def load_dictionary(self):
        with open("dictionary.txt", "r") as f:
            for line in f:
                word = line.strip()
                if 3 <= len(word) <= 30:
                    node = self.trie
                    for ch in word:
                        node = node.children.setdefault(ch, TrieNode())
                    node.is_word = True
                    node.word = word

    # --------------------------------------------------------------------- #
    #  Network
    # --------------------------------------------------------------------- #
    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.connect(("localhost", 7474))
        self.rfile = self.sock.makefile("r")

    def send(self, line: str):
        self.sock.sendall((line + "\n").encode())

    def recv(self, timeout=None):
        if timeout is not None:
            self.sock.settimeout(timeout)
        try:
            line = self.rfile.readline()
        except socket.timeout:
            return None
        finally:
            if timeout is not None:
                self.sock.settimeout(None)
        return line.strip() if line else None

    def has_data(self, timeout=0.0):
        ready, _, _ = select.select([self.sock], [], [], timeout)
        return bool(ready)

    def drain(self, timeout=0.0):
        """Non-blocking read of pending server lines.
        Returns 'dq'/'round_end' if the round is over, else None."""
        while self.has_data(timeout):
            resp = self.recv()
            if resp is None:
                return "disconnect"
            if resp.startswith("DQ"):
                return "dq"
            if resp.startswith("ROUND_END"):
                return "round_end"
        return None

    # --------------------------------------------------------------------- #
    #  Board helpers
    # --------------------------------------------------------------------- #
    def find_blank(self):
        for r in range(self.h):
            for c in range(self.w):
                if self.grid[r][c] == "_":
                    return r, c
        return 0, 0

    def do_slide(self, d: str) -> bool:
        """Apply slide locally. Returns False if move is off-board."""
        br, bc = self.br, self.bc
        if d == "U":
            nr, nc = br - 1, bc
        elif d == "D":
            nr, nc = br + 1, bc
        elif d == "L":
            nr, nc = br, bc - 1
        elif d == "R":
            nr, nc = br, bc + 1
        else:
            return False

        if not (0 <= nr < self.h and 0 <= nc < self.w):
            return False

        self.grid[br][bc], self.grid[nr][nc] = self.grid[nr][nc], self.grid[br][bc]
        self.br, self.bc = nr, nc
        return True

    def simulate_slide(self, d: str):
        """Return (ok, words) for a slide WITHOUT mutating real state."""
        br, bc = self.br, self.bc
        if d == "U":
            nr, nc = br - 1, bc
        elif d == "D":
            nr, nc = br + 1, bc
        elif d == "L":
            nr, nc = br, bc - 1
        elif d == "R":
            nr, nc = br, bc + 1
        else:
            return False, []

        if not (0 <= nr < self.h and 0 <= nc < self.w):
            return False, []

        # Temporarily swap
        self.grid[br][bc], self.grid[nr][nc] = self.grid[nr][nc], self.grid[br][bc]
        self.br, self.bc = nr, nc
        words = self.scan_words()
        # Restore
        self.grid[br][bc], self.grid[nr][nc] = self.grid[nr][nc], self.grid[br][bc]
        self.br, self.bc = br, bc
        return True, words

    # --------------------------------------------------------------------- #
    #  Word finding
    # --------------------------------------------------------------------- #
    def scan_words(self):
        """Return every valid (word, orient, r, c) on the current board."""
        found = []

        # Across
        for r in range(self.h):
            row = self.grid[r]
            for c in range(self.w):
                if row[c] == "_":
                    continue
                node = self.trie
                for cc in range(c, self.w):
                    ch = row[cc]
                    if ch == "_" or ch not in node.children:
                        break
                    node = node.children[ch]
                    if node.is_word:
                        found.append((node.word, "A", r, c))

        # Down
        for c in range(self.w):
            for r in range(self.h):
                if self.grid[r][c] == "_":
                    continue
                node = self.trie
                for rr in range(r, self.h):
                    ch = self.grid[rr][c]
                    if ch == "_" or ch not in node.children:
                        break
                    node = node.children[ch]
                    if node.is_word:
                        found.append((node.word, "D", r, c))

        return found

    def blast_claims(self, words):
        """Send claims for every new, long-enough word. Pipelined."""
        for word, orient, r, c in words:
            if time.time() >= self.deadline:
                break
            if word in self.claimed or len(word) < self.min_len:
                continue
            self.send(f"W {word} {orient} {r},{c}")
            self.claimed.add(word)

    # --------------------------------------------------------------------- #
    #  Round logic
    # --------------------------------------------------------------------- #
    def play_round(self, round_line: str):
        parts = round_line.split()
        self.w = int(parts[2])
        self.h = int(parts[3])

        # Read grid rows
        self.grid = [list(self.recv()) for _ in range(self.h)]
        self.br, self.bc = self.find_blank()

        if self.recv() != "START":
            return

        start = time.time()
        self.deadline = start + 9.5          # hard safety margin
        self.claimed = set()

        # ---- Phase 1: claim everything already on the board ---------------
        words = self.scan_words()
        words.sort(key=lambda t: len(t[0]), reverse=True)
        self.blast_claims(words)

        if self.drain() in ("dq", "round_end", "disconnect"):
            return

        # ---- Phase 2: greedy slides ---------------------------------------
        directions = ("U", "D", "L", "R")

        while time.time() < self.deadline - 0.2:
            status = self.drain()
            if status in ("dq", "round_end", "disconnect"):
                return

            # Evaluate all four neighbours
            best_dir = None
            best_score = -1
            best_words = None

            for d in directions:
                ok, words = self.simulate_slide(d)
                if not ok:
                    continue
                score = sum(
                    len(w)
                    for w, _, _, _ in words
                    if w not in self.claimed and len(w) >= self.min_len
                )
                if score > best_score:
                    best_score = score
                    best_dir = d
                    best_words = words

            if best_dir and best_score > 0:
                self.do_slide(best_dir)
                self.send(f"S {best_dir}")
                best_words.sort(key=lambda t: len(t[0]), reverse=True)
                self.blast_claims(best_words)
            else:
                # Nothing promising — make any legal move to keep exploring
                for d in directions:
                    if self.do_slide(d):
                        self.send(f"S {d}")
                        break

        # ---- Phase 3: wait for ROUND_END ----------------------------------
        while True:
            resp = self.recv(timeout=2.0)
            if resp is None or resp.startswith("ROUND_END") or resp.startswith("DQ"):
                break

    # --------------------------------------------------------------------- #
    #  Main loop
    # --------------------------------------------------------------------- #
    def run(self):
        self.load_dictionary()
        self.connect()
        self.send(os.environ["BOTNAME"].strip())

        while True:
            line = self.recv()
            if line is None:
                break
            if line == "TOURNAMENT_END":
                break
            if line.startswith("ROUND"):
                self.play_round(line)
            # Anything else is ignored (should not happen)


if __name__ == "__main__":
    WordGemBot().run()