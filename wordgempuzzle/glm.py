import os
import socket
import time

def main():
    botname = os.environ['BOTNAME'].strip()
    
    # Load dictionary
    dictionary = set()
    with open('dictionary.txt', 'r') as f:
        for line in f:
            word = line.strip()
            if len(word) >= 3 and word.isalpha() and word.islower():
                dictionary.add(word)
    
    # Build trie
    trie = {}
    for word in dictionary:
        node = trie
        for ch in word:
            if ch not in node:
                node[ch] = {}
            node = node[ch]
        node['$'] = True  # marks end of word
    
    # Connect
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    
    # Send botname
    sock.sendall((botname + '\n').encode())
    
    # Buffer for reading
    recv_buf = b''
    
    def read_line():
        nonlocal recv_buf
        while b'\n' not in recv_buf:
            data = sock.recv(4096)
            if not data:
                return None
            recv_buf += data
        idx = recv_buf.index(b'\n')
        line = recv_buf[:idx].decode('ascii')
        recv_buf = recv_buf[idx+1:]
        return line
    
    def send_cmd(cmd):
        sock.sendall((cmd + '\n').encode())
    
    def find_words(grid, w, h):
        results = []
        # Across
        for r in range(h):
            for c in range(w):
                if grid[r][c] == '_':
                    continue
                node = trie
                word = []
                for ci in range(c, w):
                    ch = grid[r][ci]
                    if ch == '_':
                        break
                    if ch not in node:
                        break
                    node = node[ch]
                    word.append(ch)
                    if '$' in node and len(word) >= 7:
                        results.append((''.join(word), 'A', r, c))
        # Down
        for c in range(w):
            for r in range(h):
                if grid[r][c] == '_':
                    continue
                node = trie
                word = []
                for ri in range(r, h):
                    ch = grid[ri][c]
                    if ch == '_':
                        break
                    if ch not in node:
                        break
                    node = node[ch]
                    word.append(ch)
                    if '$' in node and len(word) >= 7:
                        results.append((''.join(word), 'D', r, c))
        return results
    
    def do_slide(grid, w, h, br, bc, direction):
        """Try to slide. Returns new (br, bc) or None if invalid."""
        dr, dc = {'U': (-1, 0), 'D': (1, 0), 'L': (0, -1), 'R': (0, 1)}[direction]
        nr, nc = br + dr, bc + dc
        if 0 <= nr < h and 0 <= nc < w:
            grid[br][bc], grid[nr][nc] = grid[nr][nc], grid[br][bc]
            return nr, nc
        return None
    
    # Main loop
    while True:
        line = read_line()
        if line is None or line == 'TOURNAMENT_END':
            break
        
        if not line.startswith('ROUND '):
            continue
        
        parts = line.split()
        w = int(parts[2])
        h = int(parts[3])
        
        # Read grid
        grid = []
        for i in range(h):
            row = read_line()
            grid.append(list(row))
        
        # Wait for START
        read_line()  # START
        
        # Find blank
        br, bc = 0, 0
        for r in range(h):
            for c in range(w):
                if grid[r][c] == '_':
                    br, bc = r, c
        
        # Find and claim words
        claimed = set()
        words = find_words(grid, w, h)
        words.sort(key=lambda x: len(x[0]), reverse=True)
        
        for word, orient, r, c in words:
            if word not in claimed:
                claimed.add(word)
                send_cmd(f'W {word} {orient} {r},{c}')
        
        # Now try sliding and looking for more words
        start_time = time.time()
        
        # Simple sliding: move blank in a pattern
        directions = ['R', 'D', 'L', 'U']
        dir_idx = 0
        
        while time.time() - start_time < 8.0:
            # Try a slide
            direction = directions[dir_idx % 4]
            dir_idx += 1
            
            result = do_slide(grid, w, h, br, bc, direction)
            if result is None:
                continue
            
            br, bc = result
            send_cmd(f'S {direction}')
            
            # Check for new words
            words = find_words(grid, w, h)
            words.sort(key=lambda x: len(x[0]), reverse=True)
            
            for word, orient, r, c in words:
                if word not in claimed:
                    claimed.add(word)
                    send_cmd(f'W {word} {orient} {r},{c}')
    
    sock.close()

if __name__ == '__main__':
    main()