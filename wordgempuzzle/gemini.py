import os
import sys
import socket
import asyncio
import random

def load_optimized_dictionary(filepath="dictionary.txt"):
    """
    Loads the dictionary and pre-filters it.
    Since words < 7 letters result in 0 or negative points (len - 6),
    we strictly drop them to prevent the bot from hurting its own score.
    """
    valid_words = set()
    try:
        with open(filepath, "r", encoding="ascii") as f:
            for line in f:
                word = line.rstrip('\n')
                if len(word) >= 7:
                    valid_words.add(word)
    except FileNotFoundError:
        print(f"Warning: {filepath} not found. Bot will not be able to find words.", file=sys.stderr)
    return valid_words

class WordGemBot:
    def __init__(self, dictionary):
        # 1. Strict handshake identity
        self.botname = os.environ.get("BOTNAME")
        if not self.botname:
            print("Error: BOTNAME environment variable must be set.", file=sys.stderr)
            sys.exit(1)
            
        self.host = "localhost"
        self.port = 7474
        self.dictionary = dictionary
        
        # Round State
        self.w = 0
        self.h = 0
        self.grid = []
        self.blank_r = -1
        self.blank_c = -1
        
        # Protocol & Flow Control
        self.round_active = False
        self.handshake_done = False
        self.submitted_words = set()
        
        # Network
        self.reader = None
        self.writer = None

    async def run(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        
        # Disable Nagle's algorithm for lowest possible latency on small commands
        sock = self.writer.get_extra_info('socket')
        if sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        # Send Handshake
        self._send_raw(self.botname)
        self.handshake_done = True
        
        # Main Server Reading Loop
        while True:
            line_bytes = await self.reader.readline()
            if not line_bytes:
                break # Socket closed by server
                
            # Protocol strictly mandates single \n stripping
            line = line_bytes.decode('ascii').rstrip('\n')
            if not line:
                continue
                
            await self.handle_server_message(line)

    def _send_raw(self, payload: str):
        """Writes a strict newline-terminated payload to the socket."""
        self.writer.write((payload + '\n').encode('ascii'))

    def send_command(self, cmd: str):
        """Safeguard wrapper: Only sends data if the round is actively running."""
        if self.round_active:
            self._send_raw(cmd)

    async def handle_server_message(self, line: str):
        parts = line.split(' ')
        cmd = parts[0]
        
        if cmd == "ROUND":
            self.w = int(parts[2])
            self.h = int(parts[3])
            self.grid = []
            
            for r in range(self.h):
                row_line = (await self.reader.readline()).decode('ascii').rstrip('\n')
                self.grid.append(list(row_line))
                if '_' in row_line:
                    self.blank_r = r
                    self.blank_c = row_line.index('_')
                    
            self.submitted_words.clear()
            
        elif cmd == "START":
            self.round_active = True
            # Fork off the game execution loop without blocking the reader
            asyncio.create_task(self.play_round_loop())
            
        elif cmd == "ROUND_END":
            self.round_active = False
            
        elif cmd == "DQ":
            # DQ stops our play loop immediately, but we wait for ROUND_END
            self.round_active = False
            print(f"[{self.botname}] Disqualified: {line}", file=sys.stderr)
            
        elif cmd == "TOURNAMENT_END":
            sys.exit(0)

        # Ignored standard responses: MOVED, OK, TAKEN, DUP. 
        # Because we pipeline and perfectly track local state, we don't need to block on these.

    async def play_round_loop(self):
        """
        The frantic 10-second logic loop. 
        1. Sweep the board for high-value words.
        2. Slide the blank pseudo-randomly to create a new board state.
        3. Yield execution back to the asyncio event loop briefly to process network reads.
        """
        while self.round_active:
            self.sweep_and_submit_words()
            
            if not self.round_active:
                break
                
            slid = self.do_random_slide()
            
            # Yield slightly. If we slid, 0.01 is enough to not lock the CPU and process responses.
            await asyncio.sleep(0.01 if slid else 0.1)

    def sweep_and_submit_words(self):
        """Sweeps all rows and columns for valid dictionary words (>= 7 letters)."""
        # Horizontal sweep
        for r in range(self.h):
            row_str = "".join(self.grid[r])
            self.extract_and_send(row_str, 'A', r, 0, is_row=True)
            
        # Vertical sweep
        for c in range(self.w):
            col_str = "".join(self.grid[r][c] for r in range(self.h))
            self.extract_and_send(col_str, 'D', 0, c, is_row=False)

    def extract_and_send(self, line_str: str, orientation: str, start_r: int, start_c: int, is_row: bool):
        length = len(line_str)
        # i = start index, j = end index.
        # We start looking at lengths of 7 to avoid scoring 0 or negative points.
        for i in range(length):
            for j in range(i + 7, length + 1):
                sub = line_str[i:j]
                
                if '_' in sub:
                    break # All longer substrings from this 'i' will also contain the blank, skip them.
                    
                if sub in self.dictionary and sub not in self.submitted_words:
                    r = start_r if is_row else start_r + i
                    c = start_c + i if is_row else start_c
                    
                    if self.round_active:
                        self.send_command(f"W {sub} {orientation} {r},{c}")
                        self.submitted_words.add(sub) # Mark locally so we don't spam DUPs

    def do_random_slide(self):
        """Executes a valid random slide locally and dispatches the command."""
        valid_moves = []
        if self.blank_r > 0:           valid_moves.append(('U', -1, 0))
        if self.blank_r < self.h - 1:  valid_moves.append(('D', 1, 0))
        if self.blank_c > 0:           valid_moves.append(('L', 0, -1))
        if self.blank_c < self.w - 1:  valid_moves.append(('R', 0, 1))
        
        if not valid_moves:
            return False
            
        move, dr, dc = random.choice(valid_moves)
        new_r, new_c = self.blank_r + dr, self.blank_c + dc
        
        # Mutate the local grid instantly to match what the server will do
        self.grid[self.blank_r][self.blank_c], self.grid[new_r][new_c] = \
            self.grid[new_r][new_c], self.grid[self.blank_r][self.blank_c]
            
        self.blank_r, self.blank_c = new_r, new_c
        
        # Pipeline the command
        if self.round_active:
            self.send_command(f"S {move}")
            return True
        return False


if __name__ == "__main__":
    # 1. Pre-process the dictionary synchronously on startup
    filtered_dict = load_optimized_dictionary()
    
    # 2. Fire up the Asyncio bot logic
    bot = WordGemBot(filtered_dict)
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass