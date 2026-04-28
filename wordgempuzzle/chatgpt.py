#!/usr/bin/env python3
import os
import re
import socket
import sys
import time
import random
import threading
import queue
from dataclasses import dataclass

HOST = "localhost"
PORT = 7474
DICT_FILE = "dictionary.txt"

MIN_WORD_LEN = 7          # scoring is len(word)-6, so 7+ only
ROUND_SECONDS = 10.0
SAFETY_MARGIN = 0.30      # stop before timer edge
MAX_BURST = 96            # claim lines per send burst
MAX_SLIDES = 120          # prevents over-sliding
TRIE_END = ""


@dataclass(frozen=True)
class Claim:
    word: str
    orient: str
    r: int
    c: int

    @property
    def score(self):
        return len(self.word) - 6

    def line(self):
        return f"W {self.word} {self.orient} {self.r},{self.c}\n"


def load_trie(path):
    root = {}
    count = 0

    with open(path, "r", encoding="ascii", errors="ignore") as f:
        for line in f:
            w = line.strip()
            if len(w) < MIN_WORD_LEN:
                continue
            if not w.isalpha() or not w.islower():
                continue

            node = root
            for ch in w:
                node = node.setdefault(ch, {})
            node[TRIE_END] = True
            count += 1

    return root, count


def scan_line(chars, trie, orient, fixed, start_index_base, already_sent):
    """
    chars: row or column as list[str]
    orient: 'A' or 'D'
    fixed: row for A, col for D
    start_index_base: normally 0
    """
    claims = []
    n = len(chars)

    for start in range(n):
        if chars[start] == "_":
            continue

        node = trie
        word_chars = []

        for i in range(start, n):
            ch = chars[i]
            if ch == "_":
                break
            node = node.get(ch)
            if node is None:
                break

            word_chars.append(ch)

            if len(word_chars) >= MIN_WORD_LEN and TRIE_END in node:
                word = "".join(word_chars)
                if word not in already_sent:
                    if orient == "A":
                        claims.append(Claim(word, "A", fixed, start + start_index_base))
                    else:
                        claims.append(Claim(word, "D", start + start_index_base, fixed))

    return claims


def scan_board(board, trie, already_sent):
    h = len(board)
    w = len(board[0])
    claims = []

    for r in range(h):
        claims.extend(scan_line(board[r], trie, "A", r, 0, already_sent))

    for c in range(w):
        col = [board[r][c] for r in range(h)]
        claims.extend(scan_line(col, trie, "D", c, 0, already_sent))

    # One placement per unique word; longer / higher-value first.
    best = {}
    for cl in claims:
        old = best.get(cl.word)
        if old is None or cl.score > old.score:
            best[cl.word] = cl

    out = list(best.values())
    out.sort(key=lambda x: (-x.score, -len(x.word), x.word))
    return out


def find_blank(board):
    for r, row in enumerate(board):
        for c, ch in enumerate(row):
            if ch == "_":
                return r, c
    raise RuntimeError("no blank found")


def valid_moves(blank_r, blank_c, h, w):
    moves = []
    if blank_r > 0:
        moves.append("U")
    if blank_r + 1 < h:
        moves.append("D")
    if blank_c > 0:
        moves.append("L")
    if blank_c + 1 < w:
        moves.append("R")
    return moves


def apply_slide(board, blank, move):
    h = len(board)
    w = len(board[0])
    r, c = blank

    nr, nc = r, c
    if move == "U":
        nr -= 1
    elif move == "D":
        nr += 1
    elif move == "L":
        nc -= 1
    elif move == "R":
        nc += 1
    else:
        raise ValueError(move)

    if not (0 <= nr < h and 0 <= nc < w):
        raise RuntimeError("invalid local slide")

    board[r][c], board[nr][nc] = board[nr][nc], board[r][c]
    return nr, nc


def opposite(move):
    return {"U": "D", "D": "U", "L": "R", "R": "L"}[move]


def choose_slide(board, blank, last_move):
    h = len(board)
    w = len(board[0])
    moves = valid_moves(blank[0], blank[1], h, w)

    # Avoid immediate undo when possible.
    if last_move and len(moves) > 1:
        rev = opposite(last_move)
        moves = [m for m in moves if m != rev] or moves

    return random.choice(moves)


class Bot:
    def __init__(self):
        self.name = self.get_bot_name()
        self.trie, self.word_count = load_trie(DICT_FILE)

        self.sock = socket.create_connection((HOST, PORT))
        self.sock.sendall((self.name + "\n").encode("ascii"))

        self.lines = queue.Queue()
        self.round_done = threading.Event()
        self.closed = threading.Event()

        self.reader = threading.Thread(target=self.reader_loop, daemon=True)
        self.reader.start()

    @staticmethod
    def get_bot_name():
        name = os.environ.get("BOTNAME")
        if name is None:
            print("BOTNAME environment variable is required", file=sys.stderr)
            sys.exit(2)

        name = name.rstrip("\n")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", name):
            print("Invalid BOTNAME", file=sys.stderr)
            sys.exit(2)

        return name

    def reader_loop(self):
        buf = b""
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    self.closed.set()
                    self.lines.put(None)
                    return

                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode("ascii", errors="replace")
                    if line.startswith("ROUND_END"):
                        self.round_done.set()
                    self.lines.put(line)
        except Exception:
            self.closed.set()
            self.lines.put(None)

    def get_line(self):
        line = self.lines.get()
        if line is None:
            raise EOFError
        return line

    def send_lines(self, lines):
        if not lines:
            return
        self.sock.sendall("".join(lines).encode("ascii"))

    def play_round(self, board):
        self.round_done.clear()

        h = len(board)
        w = len(board[0])
        blank = find_blank(board)

        already_sent = set()
        last_move = None
        slides = 0

        start = time.monotonic()
        end = start + ROUND_SECONDS - SAFETY_MARGIN

        # Immediate opening harvest.
        while time.monotonic() < end and not self.round_done.is_set():
            claims = scan_board(board, self.trie, already_sent)

            burst = []
            for cl in claims:
                if cl.word in already_sent:
                    continue
                already_sent.add(cl.word)
                burst.append(cl.line())
                if len(burst) >= MAX_BURST:
                    break

            if burst:
                self.send_lines(burst)
                continue

            if slides >= MAX_SLIDES:
                time.sleep(0.005)
                continue

            move = choose_slide(board, blank, last_move)
            blank = apply_slide(board, blank, move)
            last_move = move
            slides += 1

            self.send_lines([f"S {move}\n"])

        # Stop sending. Main loop will consume responses until ROUND_END.

    def run(self):
        while True:
            try:
                line = self.get_line()
            except EOFError:
                return

            if line == "TOURNAMENT_END":
                return

            if not line.startswith("ROUND "):
                continue

            parts = line.split()
            if len(parts) != 4:
                continue

            _, n, w_s, h_s = parts
            w = int(w_s)
            h = int(h_s)

            board = []
            for _ in range(h):
                row = list(self.get_line())
                if len(row) != w:
                    raise RuntimeError("bad row length from server")
                board.append(row)

            start_line = self.get_line()
            if start_line != "START":
                raise RuntimeError(f"expected START, got {start_line!r}")

            self.play_round(board)

            # Drain until ROUND_END. Preserve future ROUND lines naturally because
            # the reader queues them in order after ROUND_END.
            while True:
                line = self.get_line()
                if line.startswith("ROUND_END"):
                    break
                if line == "TOURNAMENT_END":
                    return


def main():
    random.seed(os.getpid() ^ int(time.time() * 1000000))
    bot = Bot()
    bot.run()


if __name__ == "__main__":
    main()