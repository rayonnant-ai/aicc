#!/usr/bin/env python3.10
import os
import sys
import socket
from collections import deque
from typing import List, Tuple, Set, Dict, Optional

class TrieNode:
    __slots__ = ('children', 'is_word')
    def __init__(self):
        self.children: Dict[str, 'TrieNode'] = {}
        self.is_word = False

class WordGemBot:
    def __init__(self, host='localhost', port=7474):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.f = self.sock.makefile('rwb', buffering=0)

        botname = os.environ['BOTNAME'].rstrip('\n')
        if not (1 <= len(botname) <= 32) or any(c not in
            'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in botname):
            sys.exit(1) # server would close anyway
        self._send(botname)

        self.root = TrieNode()
        self._load_dictionary()
        self.w = self.h = 0
        self.grid: List[List[str]] = []
        self.blank_r = self.blank_c = 0
        self.seen_words: Set[str] = set()
        self.round_active = False

    def _send(self, line: str):
        self.f.write(line.encode('ascii') + b'\n')

    def _recv(self) -> str:
        line = self.f.readline()
        if not line:
            sys.exit(0)
        return line.decode('ascii').rstrip('\n')

    def _load_dictionary(self):
        try:
            with open('dictionary.txt', 'r', encoding='ascii') as f:
                for word in f:
                    word = word.strip()
                    if len(word) >= 3:
                        node = self.root
                        for ch in word:
                            node = node.children.setdefault(ch, TrieNode())
                        node.is_word = True
        except FileNotFoundError:
            pass # spec says it's there, but don't crash if not

    def _load_grid(self):
        self.grid = []
        for r in range(self.h):
            row = self._recv()
            self.grid.append(list(row))
            if '_' in row:
                self.blank_r = r
                self.blank_c = row.index('_')
        self.seen_words.clear()

    def _apply_slide_local(self, d: str):
        r, c = self.blank_r, self.blank_c
        if d == 'U': nr, nc = r - 1, c
        elif d == 'D': nr, nc = r + 1, c
        elif d == 'L': nr, nc = r, c - 1
        else: nr, nc = r, c + 1 # 'R'
        self.grid[r][c], self.grid[nr][nc] = self.grid[nr][nc], '_'
        self.blank_r, self.blank_c = nr, nc

    def _find_words_in_line(self, line: List[str], r: int, c: int, is_across: bool) -> List[Tuple[str, int, int, str]]:
        # Returns list of (word, r, c, orient) for all dict words found in this row/col
        res = []
        s = ''.join(line)
        if '_' in s: return res # can't claim across blank

        for start in range(len(s)):
            node = self.root
            for end in range(start, len(s)):
                ch = s[end]
                if ch not in node.children: break
                node = node.children[ch]
                if node.is_word:
                    word = s[start:end+1]
                    if len(word) >= 3 and word not in self.seen_words:
                        rr, cc = (r, c + start) if is_across else (r + start, c)
                        orient = 'A' if is_across else 'D'
                        res.append((word, rr, cc, orient))
        return res

    def _scan_board_for_words(self) -> List[Tuple[str, int, int, str]]:
        words = []
        # Across
        for r in range(self.h):
            words.extend(self._find_words_in_line(self.grid[r], r, 0, True))
        # Down
        for c in range(self.w):
            col = [self.grid[r][c] for r in range(self.h)]
            words.extend(self._find_words_in_line(col, 0, c, False))
        # Prefer longer words: len-6 is the score
        words.sort(key=lambda x: len(x[0]), reverse=True)
        return words

    def _bfs_slide_targets(self, max_depth=2) -> List[Tuple[List[str], int, int]]:
        # Returns list of (path, final_r, final_c) for blank positions reachable in <=max_depth slides
        q = deque([([], self.blank_r, self.blank_c)])
        seen = {(self.blank_r, self.blank_c)}
        results = []
        for _ in range(max_depth + 1):
            for _ in range(len(q)):
                path, r, c = q.popleft()
                results.append((path, r, c))
                for d, dr, dc in [('U',-1,0), ('D',1,0), ('L',0,-1), ('R',0,1)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < self.h and 0 <= nc < self.w and (nr, nc) not in seen:
                        seen.add((nr, nc))
                        q.append((path + [d], nr, nc))
        return results[1:] # skip the 0-depth entry

    def _simulate_grid_after_slides(self, path: List[str]) -> List[List[str]]:
        g = [row[:] for row in self.grid]
        br, bc = self.blank_r, self.blank_c
        for d in path:
            r, c = br, bc
            if d == 'U': nr, nc = r - 1, c
            elif d == 'D': nr, nc = r + 1, c
            elif d == 'L': nr, nc = r, c - 1
            else: nr, nc = r, c + 1
            g[r][c], g[nr][nc] = g[nr][nc], '_'
            br, bc = nr, nc
        return g

    def play_round(self):
        self.round_active = True

        # 1. Claim any free words already on board, longest first
        for word, r, c, orient in self._scan_board_for_words():
            if not self.round_active: return
            self._send(f"W {word} {orient} {r},{c}")
            resp = self._recv()
            if resp.startswith("OK"):
                self.seen_words.add(word)
            elif resp.startswith("DQ"):
                self.round_active = False
                return
            elif resp in ("TAKEN", "DUP"):
                self.seen_words.add(word) # don't try again

        # 2. BFS for 1-2 slide setups that create 7+ letter words
        for path, _, _ in self._bfs_slide_targets(max_depth=2):
            if not self.round_active: return
            sim_grid = self._simulate_grid_after_slides(path)
            old_grid = self.grid
            self.grid = sim_grid
            candidates = self._scan_board_for_words()
            self.grid = old_grid

            for word, r, c, orient in candidates:
                if len(word) >= 7: # only bother if it scores positive
                    # execute slides
                    for d in path:
                        self._send(f"S {d}")
                        resp = self._recv()
                        if resp == "MOVED":
                            self._apply_slide_local(d)
                        elif resp.startswith("DQ"):
                            self.round_active = False
                            return

                    # claim the word
                    self._send(f"W {word} {orient} {r},{c}")
                    resp = self._recv()
                    if resp.startswith("OK"):
                        self.seen_words.add(word)
                    elif resp.startswith("DQ"):
                        self.round_active = False
                        return
                    break # one good setup per BFS branch
            if candidates and len(candidates[0][0]) >= 7:
                break # we did a move, rescan board next loop

        # 3. If we still have time, spam safe slides to fish for 6-letter words
        # Server will ROUND_END us when 10s is up
        while self.round_active:
            moved = False
            for d in ['R', 'D', 'L', 'U']:
                nr = self.blank_r + (d == 'D') - (d == 'U')
                nc = self.blank_c + (d == 'R') - (d == 'L')
                if 0 <= nr < self.h and 0 <= nc < self.w:
                    self._send(f"S {d}")
                    resp = self._recv()
                    if resp == "MOVED":
                        self._apply_slide_local(d)
                        moved = True
                        # quick check after each slide
                        for word, r, c, orient in self._scan_board_for_words():
                            if len(word) >= 6:
                                self._send(f"W {word} {orient} {r},{c}")
                                resp2 = self._recv()
                                if resp2.startswith("OK"):
                                    self.seen_words.add(word)
                                elif resp2.startswith("DQ"):
                                    self.round_active = False
                                    return
                                break
                        break
                    elif resp.startswith("DQ"):
                        self.round_active = False
                        return
            if not moved: break

    def run(self):
        while True:
            line = self._recv()
            if line.startswith('ROUND '):
                _, _, w, h = line.split()
                self.w, self.h = int(w), int(h)
                self._load_grid()
            elif line == 'START':
                self.play_round()
            elif line.startswith('ROUND_END'):
                self.round_active = False
            elif line == 'TOURNAMENT_END':
                break

if __name__ == '__main__':
    WordGemBot().run()