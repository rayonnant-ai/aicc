#!/usr/bin/env python3
import os
import socket
import sys
from collections import deque

def load_trie(path='dictionary.txt'):
    trie = {}
    with open(path, 'r') as f:
        for line in f:
            word = line.strip()
            if len(word) >= 7:  # Only store 7+ letter words
                node = trie
                for ch in word:
                    if ch not in node:
                        node[ch] = {}
                    node = node[ch]
                node['$'] = word
    return trie

def find_words_in_row(row, w, trie):
    found = {}
    for c in range(w):
        node = trie
        for c2 in range(c, w):
            ch = row[c2]
            if ch == '_':
                break
            if ch not in node:
                break
            node = node[ch]
            if '$' in node:
                word = node['$']
                if word not in found:
                    found[word] = c
    return found

def find_words_in_col(grid, c, h, trie):
    found = {}
    for r in range(h):
        node = trie
        for r2 in range(r, h):
            ch = grid[r2][c]
            if ch == '_':
                break
            if ch not in node:
                break
            node = node[ch]
            if '$' in node:
                word = node['$']
                if word not in found:
                    found[word] = r
    return found

def find_all_words(grid, h, w, trie):
    found = {}
    for r in range(h):
        for word, c in find_words_in_row(grid[r], w, trie).items():
            if word not in found:
                found[word] = ('A', r, c)
    for c in range(w):
        for word, r in find_words_in_col(grid, c, h, trie).items():
            if word not in found:
                found[word] = ('D', r, c)
    return found

def main():
    botname = os.environ['BOTNAME'].strip()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    sock.sendall((botname + '\n').encode())

    trie = load_trie()

    buf = b''

    def readline():
        nonlocal buf
        while b'\n' not in buf:
            data = sock.recv(65536)
            if not data:
                raise ConnectionError("Connection closed")
            buf += data
        line, buf = buf.split(b'\n', 1)
        return line.decode()

    while True:
        line = readline()

        if line == 'TOURNAMENT_END':
            return

        if line.startswith('ROUND '):
            parts = line.split()
            w = int(parts[2])
            h = int(parts[3])

            grid = []
            for _ in range(h):
                row = readline()
                grid.append(list(row))

            readline()  # START

            # Find blank
            br, bc = -1, -1
            for r in range(h):
                for c in range(w):
                    if grid[r][c] == '_':
                        br, bc = r, c
                        break
                if br >= 0:
                    break

            # Find all words on initial board
            claimed = set()
            commands = []

            initial_words = find_all_words(grid, h, w, trie)

            # Sort by value descending
            sorted_words = sorted(initial_words.items(), key=lambda x: len(x[0]), reverse=True)

            for word, (orient, r, c) in sorted_words:
                commands.append(f'W {word} {orient} {r},{c}')
                claimed.add(word)

            # Greedy slide search
            directions = [('U', -1, 0), ('D', 1, 0), ('L', 0, -1), ('R', 0, 1)]
            reverse_dir = {'U': 'D', 'D': 'U', 'L': 'R', 'R': 'L'}
            dir_map = {'U': (-1, 0), 'D': (1, 0), 'L': (0, -1), 'R': (0, 1)}

            g = [row[:] for row in grid]
            cur_br, cur_bc = br, bc
            last_dir = None

            for _ in range(20):  # Max 20 slides
                best_dir = None
                best_value = 0
                best_new_words = {}
                best_nr, best_nc = -1, -1

                for dir_name, dr, dc in directions:
                    if last_dir and dir_name == reverse_dir[last_dir]:
                        continue

                    nr, nc = cur_br + dr, cur_bc + dc
                    if not (0 <= nr < h and 0 <= nc < w):
                        continue

                    # Apply slide
                    g[cur_br][cur_bc], g[nr][nc] = g[nr][nc], g[cur_br][cur_bc]

                    # Find new words in affected row/column
                    new_words = {}
                    if dr == 0:  # horizontal slide
                        for word, c in find_words_in_row(g[cur_br], w, trie).items():
                            if word not in claimed:
                                new_words[word] = ('A', cur_br, c)
                    else:  # vertical slide
                        for word, r in find_words_in_col(g, cur_bc, h, trie).items():
                            if word not in claimed:
                                new_words[word] = ('D', r, cur_bc)

                    value = sum(len(w) - 6 for w in new_words)

                    # Undo slide
                    g[cur_br][cur_bc], g[nr][nc] = g[nr][nc], g[cur_br][cur_bc]

                    if value > best_value:
                        best_value = value
                        best_dir = dir_name
                        best_new_words = new_words
                        best_nr, best_nc = nr, nc

                if best_dir is None:
                    break

                # Apply the best slide
                dr, dc = dir_map[best_dir]
                g[cur_br][cur_bc], g[best_nr][best_nc] = g[best_nr][best_nc], g[cur_br][cur_bc]
                cur_br, cur_bc = best_nr, best_nc

                commands.append(f'S {best_dir}')
                for word, (orient, r, c) in best_new_words.items():
                    commands.append(f'W {word} {orient} {r},{c}')
                    claimed.add(word)

                last_dir = best_dir

            # Send all commands
            if commands:
                msg = '\n'.join(commands) + '\n'
                sock.sendall(msg.encode())

            # Read responses until ROUND_END
            while True:
                resp = readline()
                if resp.startswith('ROUND_END'):
                    break

if __name__ == '__main__':
    main()