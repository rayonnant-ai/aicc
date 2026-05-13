# bot author: Claude Opus 4.7
# bot author: Claude Opus 4.7 (Anthropic)
"""
PalinPrimeBits tournament client.

Strategy
--------
A background thread starts generating palindromic primes in ascending order
the moment we have a process and keeps doing so for the life of the bot, so
that the time the bot spends idle (waiting for ROUND lines, waiting between
rounds) is spent extending a shared cache of palindromic primes.

When a round arrives the main thread asks the cache for entry n; if the
cache already has at least n entries we answer essentially instantaneously,
and otherwise we wait for the background thread to catch up, bounded by the
per-round deadline.

Filters that make the generator cheap:
 * Every palindromic prime with more than 2 digits has odd length: any
   palindrome with an even number of digits is divisible by 11, so the only
   even-length palindromic prime is 11 itself.
 * The first (and therefore last) digit of a palindromic prime > 5 must be
   one of 1, 3, 7, 9.

Primality test: trial division by primes up to 199, then deterministic
Miller-Rabin with witnesses {2,3,5,7,11,13,17,19,23}, which is conclusive
for all n < 3,825,123,056,546,413,051. Palindromes reachable within
n <= 1,000,000 sit comfortably below that.

Wire safety: if we don't have the answer by the round budget we deliberately
send nothing for that round. Sending an ANSWER line late would land in the
next round's input slot at the server and desync every subsequent round.
"""

import os
import socket
import sys
import threading
import time


# ---------------------------------------------------------------------------
# Primality
# ---------------------------------------------------------------------------

_SMALL_PRIMES = (
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47,
    53, 59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113,
    127, 131, 137, 139, 149, 151, 157, 163, 167, 173, 179, 181, 191,
    193, 197, 199,
)

# Deterministic Miller-Rabin witnesses for n < 3,825,123,056,546,413,051.
# Every palindromic prime reachable for n <= 1,000,000 lives below 10^16,
# so this witness set is conclusive across the entire tournament range.
_MR_WITNESSES = (2, 3, 5, 7, 11, 13, 17, 19, 23)


def is_prime(n):
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n == p:
            return True
        if n % p == 0:
            return False
    # Miller-Rabin
    d = n - 1
    s = 0
    while not (d & 1):
        d >>= 1
        s += 1
    for a in _MR_WITNESSES:
        if a >= n:
            continue
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = (x * x) % n
            if x == n - 1:
                break
        else:
            return False
    return True


# ---------------------------------------------------------------------------
# Palindromic-prime generator
# ---------------------------------------------------------------------------

def gen_palindromic_primes():
    """Yield palindromic primes in ascending order: 2, 3, 5, 7, 11, 101, ..."""
    yield 2
    yield 3
    yield 5
    yield 7
    yield 11
    length = 3
    while True:
        half_len = (length + 1) // 2
        tail_block = 10 ** (half_len - 1)
        # First digit must be in {1, 3, 7, 9}; palindromes ending in
        # 0/2/4/5/6/8 are divisible by 2 or 5.
        for first in (1, 3, 7, 9):
            base = first * tail_block
            for half in range(base, base + tail_block):
                s = str(half)
                pal = int(s + s[-2::-1])
                if is_prime(pal):
                    yield pal
        length += 2


def longest_one_run(num):
    """Length of the longest contiguous run of 1-bits in num's base-2 form."""
    longest = 0
    current = 0
    while num:
        if num & 1:
            current += 1
            if current > longest:
                longest = current
        else:
            current = 0
        num >>= 1
    return longest


# ---------------------------------------------------------------------------
# Background cache
# ---------------------------------------------------------------------------

_cache = []
_cache_cond = threading.Condition()


def _filler():
    gen = gen_palindromic_primes()
    while True:
        try:
            pp = next(gen)
        except StopIteration:
            return
        with _cache_cond:
            _cache.append(pp)
            _cache_cond.notify_all()


def get_p(n, deadline):
    """Return p(n) (1-indexed), or None if the deadline passes first."""
    with _cache_cond:
        while len(_cache) < n:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            _cache_cond.wait(remaining)
        return _cache[n - 1]


# ---------------------------------------------------------------------------
# Line-based socket I/O
# ---------------------------------------------------------------------------

class LineSocket:
    """Minimal line reader/writer over a TCP socket using LF terminators."""

    def __init__(self, sock):
        self.sock = sock
        self.buf = b''

    def readline(self):
        while b'\n' not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                if self.buf:
                    line = self.buf
                    self.buf = b''
                    return line.decode('ascii')
                return None
            self.buf += chunk
        line, _, self.buf = self.buf.partition(b'\n')
        return line.decode('ascii')

    def sendline(self, text):
        self.sock.sendall((text + '\n').encode('ascii'))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Cap how long we'll wait inside a round before giving up. The server's
# wall-clock is 30s from end-of-ROUND to end-of-ANSWER; staying under 29s
# leaves comfortable headroom for transmission on localhost.
ROUND_BUDGET = 29.0


def main():
    bot_name = os.environ.get('BOTNAME')
    if not bot_name:
        print('BOTNAME environment variable missing or empty', file=sys.stderr)
        sys.exit(1)

    # Begin pre-computation immediately; the spec explicitly permits this.
    threading.Thread(target=_filler, daemon=True).start()

    raw = socket.create_connection(('localhost', 7474))
    sock = LineSocket(raw)
    try:
        sock.sendline(bot_name)

        while True:
            line = sock.readline()
            if line is None:
                break

            if line.startswith('ROUND '):
                round_start = time.monotonic()
                parts = line.split()
                # ROUND <round_num> <n>
                try:
                    n = int(parts[2])
                except (IndexError, ValueError):
                    # Malformed ROUND from the server; just consume the
                    # round's tail and move on.
                    sock.readline()
                    sock.readline()
                    continue

                pp = get_p(n, deadline=round_start + ROUND_BUDGET)
                # Re-check the clock before transmitting: if a slow wakeup
                # pushed us past the budget we suppress the ANSWER rather
                # than risking a late line that would desync the next round.
                if pp is not None and time.monotonic() - round_start < ROUND_BUDGET:
                    answer = longest_one_run(pp)
                    try:
                        sock.sendline('ANSWER ' + str(answer))
                    except OSError:
                        pass

                # The server always emits a result line (OK / INVALID) and
                # then END_ROUND, even on timeout. Consume both to stay in
                # sync, regardless of whether we sent ANSWER.
                sock.readline()
                sock.readline()
            elif line == 'TOURNAMENT_END':
                break
            # Any other line: outside the documented protocol; ignore.
    finally:
        sock.close()


if __name__ == '__main__':
    main()