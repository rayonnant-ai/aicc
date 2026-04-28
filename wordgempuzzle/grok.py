import os
import socket
import sys

def load_dictionary():
    """Load dictionary.txt into a set for O(1) lookups. Only keep valid words >=3 letters."""
    try:
        with open('dictionary.txt', 'r', encoding='ascii') as f:
            return {line.strip() for line in f if len(line.strip()) >= 3 and line.strip().isalpha()}
    except FileNotFoundError:
        print("ERROR: dictionary.txt not found in working directory.", file=sys.stderr)
        sys.exit(1)

def get_valid_claims(grid, w, h, word_set):
    """Find all unique valid words (length >= 6 for non-negative score) in horizontal and vertical lines.
    Deduplicate by exact word string (same word in multiple places only needs one claim).
    Return list sorted by score descending (longest words first for race advantage)."""
    claims = []
    seen_words = set()

    # Horizontal (Across)
    for r in range(h):
        row_str = ''.join(grid[r])
        for start_c in range(w):
            for leng in range(6, w - start_c + 1):
                segment = row_str[start_c:start_c + leng]
                if '_' not in segment and segment in word_set and segment not in seen_words:
                    score = leng - 6
                    claims.append((score, segment, 'A', r, start_c))
                    seen_words.add(segment)

    # Vertical (Down)
    for c in range(w):
        col_str = ''.join(grid[r][c] for r in range(h))
        for start_r in range(h):
            for leng in range(6, h - start_r + 1):
                segment = col_str[start_r:start_r + leng]
                if '_' not in segment and segment in word_set and segment not in seen_words:
                    score = leng - 6
                    claims.append((score, segment, 'D', start_r, c))
                    seen_words.add(segment)

    # Sort by score descending (highest value first)
    claims.sort(reverse=True)
    return claims

def play_round(sock, f, grid, w, h, word_set):
    """Pipeline all qualifying word claims, then drain server responses until ROUND_END."""
    claims = get_valid_claims(grid, w, h, word_set)

    # Pipeline all W commands (fastest possible on localhost)
    for _, word, orient, r, c in claims:
        cmd = f"W {word} {orient} {r},{c}\n"
        sock.sendall(cmd.encode('ascii'))

    # Drain responses until round ends (handles OK/TAKEN/DUP/DQ/ROUND_END)
    while True:
        line = f.readline()
        if not line:
            return  # connection lost
        line = line.rstrip('\n')

        if line.startswith('ROUND_END '):
            try:
                pts = int(line.split()[1])
                print(f"Round complete. Server reported {pts} points ({len(claims)} claims sent).", file=sys.stderr)
            except (IndexError, ValueError):
                pass
            return
        elif line.startswith('DQ '):
            print(f"DQ received: {line}", file=sys.stderr)
            # Still wait for ROUND_END (per spec)
        # Ignore OK, TAKEN, DUP, MOVED - they are normal

def main():
    """Main tournament client loop. Reads BOTNAME from environment (required by spec)."""
    # 1. Read BOTNAME from environment (exact bytes, stripped)
    try:
        botname = os.environ['BOTNAME'].strip()
        if not botname or len(botname) > 32 or not all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in botname):
            print("ERROR: BOTNAME env var invalid or missing (must be 1-32 chars [A-Za-z0-9_-]).", file=sys.stderr)
            sys.exit(1)
    except KeyError:
        print("ERROR: BOTNAME environment variable not set.", file=sys.stderr)
        sys.exit(1)

    # 2. Load dictionary
    word_set = load_dictionary()
    print(f"Bot '{botname}' loaded {len(word_set)} words from dictionary.txt", file=sys.stderr)

    # 3. Connect and send bot name (first line)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode('ascii'))

    # Line-buffered reader (spec requires exact LF, no CRLF)
    f = sock.makefile('r', encoding='ascii')

    print(f"Connected as '{botname}'. Waiting for first ROUND...", file=sys.stderr)

    # 4. Main tournament loop (handles multiple matches + silence between them)
    while True:
        line = f.readline()
        if not line:
            print("Server closed connection.", file=sys.stderr)
            break
        line = line.rstrip('\n')

        if line.startswith('ROUND '):
            parts = line.split()
            if len(parts) != 4:
                continue
            round_n = int(parts[1])
            w = int(parts[2])
            h = int(parts[3])

            # Read grid rows
            grid = []
            for _ in range(h):
                row_line = f.readline().rstrip('\n')
                if len(row_line) != w:
                    print("Malformed grid row received", file=sys.stderr)
                    break
                grid.append(list(row_line))

            # Read START
            start_line = f.readline().rstrip('\n')
            if start_line != 'START':
                print(f"Expected START, got: {start_line}", file=sys.stderr)
                continue

            print(f"Round {round_n} started ({w}×{h} grid)", file=sys.stderr)

            # Play: claim words (no sliding in this strong & safe v1)
            play_round(sock, f, grid, w, h, word_set)

        elif line == 'TOURNAMENT_END':
            print("TOURNAMENT_END received - tournament finished.", file=sys.stderr)
            break
        # Ignore everything else (ROUND_END between matches, silence between matches)

    # Cleanup
    f.close()
    sock.close()

if __name__ == "__main__":
    main()