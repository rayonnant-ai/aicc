import os
import socket

def load_dictionary(path="dictionary.txt"):
    """Load the dictionary into a set for O(1) look‑ups."""
    words = set()
    try:
        with open(path, encoding="ascii") as f:
            for line in f:
                w = line.strip()
                if w:                     # ignore empty lines
                    words.add(w)
    except FileNotFoundError:
        # If the dictionary is missing we cannot claim any words.
        pass
    return words

def process_round(sock, file, grid, w, h, dictionary, claimed):
    """
    Find all dictionary words of length >= 6 that appear horizontally
    left‑to‑right or vertically top‑to‑bottom in the current grid.
    Send a claim for each distinct word (first occurrence only).
    """
    claims = []  # list of (word, orientation, r, c)

    # ----- Horizontal (across) -----
    for r in range(h):
        c = 0
        while c < w:
            if grid[r][c] == '_':
                c += 1
                continue
            start = c
            while c < w and grid[r][c] != '_':
                c += 1
            end = c
            segment = grid[r][start:end]
            L = len(segment)
            for i in range(L):
                # only consider lengths that give non‑negative points
                max_len = L - i
                for length in range(6, max_len + 1):
                    word = segment[i:i + length]
                    if word in dictionary and word not in claimed:
                        claimed.add(word)
                        claims.append((word, 'A', r, start))
            # c already positioned at the blank or at w

    # ----- Vertical (down) -----
    for c in range(w):
        r = 0
        while r < h:
            if grid[r][c] == '_':
                r += 1
                continue
            start = r
            while r < h and grid[r][c] != '_':
                r += 1
            end = r
            # build column string
            segment = ''.join(grid[row][c] for row in range(start, end))
            L = len(segment)
            for i in range(L):
                max_len = L - i
                for length in range(6, max_len + 1):
                    word = segment[i:i + length]
                    if word in dictionary and word not in claimed:
                        claimed.add(word)
                        claims.append((word, 'D', start + i, c))
            # r already at blank or h

    # Send all claims (pipelining is allowed)
    for word, orient, rr, cc in claims:
        cmd = f'W {word} {orient} {rr},{cc}\n'
        sock.sendall(cmd.encode())

def main():
    botname = os.environ.get('BOTNAME')
    if botname is None:
        return
    botname = botname.strip()  # remove possible trailing newline

    # Connect to the server
    sock = socket.create_connection(('localhost', 7474))
    sock.sendall((botname + '\n').encode())
    file = sock.makefile('r')

    dictionary = load_dictionary()

    round_active = False
    claimed_this_round = set()

    while True:
        line = file.readline()
        if not line:          # connection closed
            break
        line = line.rstrip('\n')

        if line.startswith('ROUND'):
            # Header: ROUND <n> <w> <h>
            _, _, w_str, h_str = line.split()
            w = int(w_str)
            h = int(h_str)

            # Read the grid
            grid = []
            for _ in range(h):
                row = file.readline().rstrip('\n')
                grid.append(row)

            # Consume the START line
            start_line = file.readline().rstrip('\n')
            # start_line should be 'START'
            # Reset per‑round state
            claimed_this_round.clear()
            round_active = True

            # Process the round (send claims)
            process_round(sock, file, grid, w, h, dictionary, claimed_this_round)

        elif line.startswith('ROUND_END'):
            # Round finished; wait for next header or tournament end
            round_active = False
            # Nothing to do here; just continue reading
        elif line.startswith('TOURNAMENT_END':
            break
        # All other lines (MOVED, OK, TAKEN, DUP, DQ<reason>) are ignored

    # Clean shutdown
    sock.close()

if __name__ == '__main__':
    main()
