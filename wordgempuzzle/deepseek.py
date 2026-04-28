#!/usr/bin/env python3
import os
import socket
import threading
import time
from collections import deque

class WordGemBot:
    def __init__(self):
        # 1. Bot identity
        self.botname = os.environ['BOTNAME'].strip()
        # 2. Connect
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(('localhost', 7474))
        self.sock.sendall((self.botname + '\n').encode())

        # 3. Load dictionary (only words of length ≥ 3 matter)
        self.dictionary = set()
        with open('dictionary.txt', 'r') as f:
            for line in f:
                w = line.strip()
                if len(w) >= 3:
                    self.dictionary.add(w)

        # 4. Shared state for threading
        self.w = self.h = 0
        self.grid_rows = []          # received before START
        self.expected_rows = 0
        self.blank_pos = (0, 0)
        self.start_time = 0.0        # monotonic timestamp of START

        self.start_event = threading.Event()
        self.stop_event = threading.Event()     # set when round ends / DQ
        self.round_end_event = threading.Event()
        self.round_active = False
        self.tournament_end = False

        # 5. Start reader thread
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()

    # ------------------------------------------------------------------ #
    #                           Reader thread                             #
    # ------------------------------------------------------------------ #
    def _reader_loop(self):
        buf = ""
        while True:
            try:
                data = self.sock.recv(4096)
                if not data:
                    self.tournament_end = True
                    self.start_event.set()
                    self.round_end_event.set()
                    break
                buf += data.decode()
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    self._process_line(line)
            except Exception:
                self.tournament_end = True
                self.start_event.set()
                self.round_end_event.set()
                break

    def _process_line(self, line):
        # New round header
        if line.startswith("ROUND "):
            parts = line.split()
            self.w = int(parts[2])
            self.h = int(parts[3])
            self.grid_rows = []
            self.expected_rows = self.h
            return

        # Collect grid rows
        if self.expected_rows > 0:
            self.grid_rows.append(line)
            if len(self.grid_rows) == self.expected_rows:
                self.expected_rows = 0          # wait for START
            return

        # Round starts
        if line == "START":
            self.blank_pos = self._find_blank(self.grid_rows)
            self.start_time = time.monotonic()
            self.round_active = True
            self.stop_event.clear()
            self.start_event.set()
            return

        # Round lifecycle events
        if line.startswith("MOVED") or line.startswith("OK "):
            return
        if line in ("TAKEN", "DUP"):
            return
        if line.startswith("DQ "):
            self.round_active = False
            self.stop_event.set()
            return
        if line.startswith("ROUND_END "):
            self.round_active = False
            self.stop_event.set()
            self.round_end_event.set()
            return
        if line == "TOURNAMENT_END":
            self.tournament_end = True
            self.stop_event.set()
            self.round_end_event.set()
            return

    @staticmethod
    def _find_blank(rows):
        for r, row in enumerate(rows):
            c = row.find('_')
            if c != -1:
                return r, c
        return 0, 0

    # ------------------------------------------------------------------ #
    #                            Game control                             #
    # ------------------------------------------------------------------ #
    def play(self):
        while not self.tournament_end:
            self.start_event.wait()
            self.start_event.clear()
            if self.tournament_end:
                break
            self._play_round()
            self.round_end_event.wait()
            self.round_end_event.clear()
            if self.tournament_end:
                break
        self.sock.close()

    # ------------------------------------------------------------------ #
    #                          Single round logic                         #
    # ------------------------------------------------------------------ #
    def _play_round(self):
        grid_rows = self.grid_rows
        w, h = self.w, self.h
        br, bc = self.blank_pos

        # Mutable copy for local tracking
        grid = [list(row) for row in grid_rows]

        # All valid words on the starting board (length ≥ 3, in dictionary)
        placements = self._extract_placements(grid_rows, w, h)
        valuable = [(word, o, r, c) for word, o, r, c in placements if len(word) >= 7]
        valuable.sort(key=lambda x: len(x[0]), reverse=True)   # best points first

        attempted = set()
        # Immediately claim every distinct valuable word
        for word, o, r, c in valuable:
            if not self.round_active:
                break
            if word in attempted:
                continue
            cmd = f"W {word} {o} {r},{c}\n"
            self.sock.sendall(cmd.encode())
            attempted.add(word)

        deadline = self.start_time + 9.95   # stop a tiny bit early

        # Keep searching for new high-value words by sliding the blank
        while time.monotonic() < deadline and self.round_active:
            grid_tuple = tuple(''.join(row) for row in grid)
            path, word, o, r, c = self._bfs_find_word(
                grid_tuple, (br, bc), w, h, attempted, max_depth=4, deadline=deadline
            )
            if not path:
                # Try a little deeper if time allows
                path, word, o, r, c = self._bfs_find_word(
                    grid_tuple, (br, bc), w, h, attempted, max_depth=6, deadline=deadline
                )
                if not path:
                    break

            # Execute the slide sequence
            for d in path:
                if not self.round_active or time.monotonic() >= deadline:
                    break
                self.sock.sendall(f"S {d}\n".encode())
                br, bc = self._apply_move_mutable(grid, br, bc, d)

            if not self.round_active:
                break

            # Claim the newly formed word
            self.sock.sendall(f"W {word} {o} {r},{c}\n".encode())
            attempted.add(word)

    # ------------------------------------------------------------------ #
    #                       Word extraction helpers                       #
    # ------------------------------------------------------------------ #
    def _extract_placements(self, grid_rows, w, h):
        """Return all valid (word, orientation, r, c) for a list‑of‑strings grid."""
        vocab = self.dictionary
        placements = []

        # Rows
        for r, row in enumerate(grid_rows):
            segments = row.split('_')
            col_offset = 0
            for seg in segments:
                if len(seg) < 3:
                    col_offset += len(seg) + 1
                    continue
                L = len(seg)
                for start in range(L):
                    for end in range(start + 3, L + 1):
                        sub = seg[start:end]
                        if sub in vocab:
                            placements.append((sub, 'A', r, col_offset + start))
                col_offset += L + 1

        # Columns
        for c in range(w):
            col_chars = [grid_rows[r][c] for r in range(h)]
            col_str = ''.join(col_chars)
            segments = col_str.split('_')
            row_offset = 0
            for seg in segments:
                if len(seg) < 3:
                    row_offset += len(seg) + 1
                    continue
                L = len(seg)
                for start in range(L):
                    for end in range(start + 3, L + 1):
                        sub = seg[start:end]
                        if sub in vocab:
                            placements.append((sub, 'D', row_offset + start, c))
                row_offset += L + 1
        return placements

    def _extract_placements_tuple(self, grid, w, h):
        """Same as above but for a tuple‑of‑strings grid (used in BFS)."""
        vocab = self.dictionary
        placements = []

        for r, row in enumerate(grid):
            segments = row.split('_')
            col_offset = 0
            for seg in segments:
                if len(seg) < 3:
                    col_offset += len(seg) + 1
                    continue
                L = len(seg)
                for start in range(L):
                    for end in range(start + 3, L + 1):
                        sub = seg[start:end]
                        if sub in vocab:
                            placements.append((sub, 'A', r, col_offset + start))
                col_offset += L + 1

        for c in range(w):
            col_chars = [grid[r][c] for r in range(h)]
            col_str = ''.join(col_chars)
            segments = col_str.split('_')
            row_offset = 0
            for seg in segments:
                if len(seg) < 3:
                    row_offset += len(seg) + 1
                    continue
                L = len(seg)
                for start in range(L):
                    for end in range(start + 3, L + 1):
                        sub = seg[start:end]
                        if sub in vocab:
                            placements.append((sub, 'D', row_offset + start, c))
                row_offset += L + 1
        return placements

    # ------------------------------------------------------------------ #
    #                          Slide operations                           #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _apply_move_mutable(grid, br, bc, d):
        """Apply slide direction d on mutable grid, return new blank position."""
        if d == 'U':
            nr, nc = br - 1, bc
        elif d == 'D':
            nr, nc = br + 1, bc
        elif d == 'L':
            nr, nc = br, bc - 1
        else:  # 'R'
            nr, nc = br, bc + 1
        # Swap blank with the tile
        grid[br][bc], grid[nr][nc] = grid[nr][nc], grid[br][bc]
        return nr, nc

    def _apply_move_tuple(self, grid, br, bc, d, nr, nc, w):
        """Return a new tuple‑of‑strings grid after sliding the blank."""
        grid_list = list(grid)
        row_br = grid_list[br]
        row_nr = grid_list[nr]
        tile_char = row_nr[nc]

        if br == nr:
            chars = list(row_br)
            chars[bc], chars[nc] = chars[nc], chars[bc]
            grid_list[br] = ''.join(chars)
        else:
            chars_br = list(row_br)
            chars_br[bc] = tile_char
            grid_list[br] = ''.join(chars_br)
            chars_nr = list(row_nr)
            chars_nr[nc] = '_'
            grid_list[nr] = ''.join(chars_nr)
        return tuple(grid_list)

    # ------------------------------------------------------------------ #
    #                          BFS word search                            #
    # ------------------------------------------------------------------ #
    def _bfs_find_word(self, grid_tuple, blank, w, h, attempted, max_depth, deadline):
        """Return (path, word, orient, r, c) or (None, None, None, None)."""
        visited = {(grid_tuple, blank)}
        q = deque()
        q.append((grid_tuple, blank, []))   # (grid, blank_pos, path)

        while q:
            if time.monotonic() > deadline:
                return None, None, None, None
            grid, (br, bc), path = q.popleft()
            if len(path) >= max_depth:
                continue

            # Check all words on the current board
            placements = self._extract_placements_tuple(grid, w, h)
            for word, o, r, c in placements:
                if len(word) >= 7 and word not in attempted:
                    return path, word, o, r, c

            # Expand legal slides
            for dr, dc, d in [(-1, 0, 'U'), (1, 0, 'D'), (0, -1, 'L'), (0, 1, 'R')]:
                nr, nc = br + dr, bc + dc
                if 0 <= nr < h and 0 <= nc < w:
                    new_grid = self._apply_move_tuple(grid, br, bc, d, nr, nc, w)
                    new_blank = (nr, nc)
                    state = (new_grid, new_blank)
                    if state not in visited:
                        visited.add(state)
                        q.append((new_grid, new_blank, path + [d]))
        return None, None, None, None


if __name__ == "__main__":
    bot = WordGemBot()
    bot.play()