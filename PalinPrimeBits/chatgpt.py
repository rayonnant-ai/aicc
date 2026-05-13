# bot author: ChatGPT GPT 5.5
#!/usr/bin/env python3
# bot author: GPT-5.5 Thinking

import os
import sys
import socket
import multiprocessing as mp
from array import array


HOST = "localhost"
PORT = 7474
MAX_N = 1_000_000

# Deterministic Miller-Rabin bases for all unsigned 64-bit integers.
# The 1,000,000th palindromic prime is well below 2^64.
MR_BASES_64 = (2, 325, 9375, 28178, 450775, 9780504, 1795265022)

SMALL_PRIMES = (
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37
)


def is_prime_u64(n: int) -> bool:
    if n < 2:
        return False

    for p in SMALL_PRIMES:
        if n % p == 0:
            return n == p

    d = n - 1
    s = 0
    while (d & 1) == 0:
        s += 1
        d >>= 1

    for a in MR_BASES_64:
        a %= n
        if a == 0:
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


def longest_one_run(n: int) -> int:
    best = 0
    cur = 0

    while n:
        if n & 1:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
        n >>= 1

    return best


def odd_decimal_palindrome_from_half(half: int) -> int:
    """
    half = 1234 -> 1234321
    half = 10   -> 101
    """
    x = half
    y = half // 10
    while y:
        x = x * 10 + (y % 10)
        y //= 10
    return x


def worker_range(args):
    start, stop = args
    out = array("B")

    for half in range(start, stop):
        # For an odd-length palindrome made from half:
        # digit_sum(pal) = 2 * digit_sum(half) - last_digit(half).
        # If divisible by 3, it cannot be prime except for 3, which is handled
        # in the seed list.
        h = half
        digit_sum = 0
        while h:
            digit_sum += h % 10
            h //= 10

        if (2 * digit_sum - (half % 10)) % 3 == 0:
            continue

        p = odd_decimal_palindrome_from_half(half)

        if is_prime_u64(p):
            out.append(longest_one_run(p))

    return out


def make_chunks_for_half_digits(half_digits: int, workers: int):
    """
    Generate candidate half ranges in increasing numeric order.

    We only need palindromes whose final digit is 1, 3, 7, or 9.
    For an odd-length palindrome, the final digit equals the first digit of
    the half, so half must start with 1, 3, 7, or 9.
    """
    base = 10 ** (half_digits - 1)
    ranges = []

    for first_digit in (1, 3, 7, 9):
        lo = first_digit * base
        hi = (first_digit + 1) * base

        size = hi - lo
        chunk_size = max(1, (size + workers - 1) // workers)

        x = lo
        while x < hi:
            y = min(hi, x + chunk_size)
            ranges.append((x, y))
            x = y

    return ranges


def precompute_answers(limit: int = MAX_N) -> array:
    """
    Returns an array ans where ans[n] is the answer for n.
    ans[0] is unused.

    p(1..5) = 2, 3, 5, 7, 11.
    After that, every even-length palindrome is divisible by 11, so the only
    possible palindromic primes are odd-length decimal palindromes.
    """
    ans = array("B", [0])

    # n = 1..5
    for p in (2, 3, 5, 7, 11):
        ans.append(longest_one_run(p))

    if len(ans) > limit:
        return ans[: limit + 1]

    cpu = os.cpu_count() or 1
    workers = max(1, min(cpu, 8))

    # half_digits = 2 gives 3-digit palindromes, e.g. 10 -> 101.
    half_digits = 2

    if workers == 1:
        while len(ans) <= limit:
            for r in make_chunks_for_half_digits(half_digits, 1):
                ans.extend(worker_range(r))
                if len(ans) > limit:
                    return ans[: limit + 1]
            half_digits += 1

    else:
        ctx = mp.get_context("fork" if sys.platform != "win32" else "spawn")
        with ctx.Pool(processes=workers) as pool:
            while len(ans) <= limit:
                chunks = make_chunks_for_half_digits(half_digits, workers)

                # imap preserves chunk order, and chunks are constructed in
                # increasing numeric order, so ans remains indexed correctly.
                for part in pool.imap(worker_range, chunks, chunksize=1):
                    ans.extend(part)
                    if len(ans) > limit:
                        pool.terminate()
                        pool.join()
                        return ans[: limit + 1]

                half_digits += 1

    return ans[: limit + 1]


def valid_botname(name: str) -> bool:
    if not (1 <= len(name) <= 32):
        return False
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    return all(c in allowed for c in name)


def main() -> int:
    botname = os.environ.get("BOTNAME")
    if not botname or not valid_botname(botname):
        return 2

    # Precompute before connecting so no ROUND clock is running yet.
    answers = precompute_answers(MAX_N)

    with socket.create_connection((HOST, PORT)) as sock:
        rf = sock.makefile("r", encoding="ascii", newline="\n")
        wf = sock.makefile("w", encoding="ascii", newline="\n")

        wf.write(botname + "\n")
        wf.flush()

        for line in rf:
            line = line.rstrip("\n")

            if line == "TOURNAMENT_END":
                return 0

            if not line.startswith("ROUND "):
                continue

            parts = line.split()
            if len(parts) != 3:
                continue

            try:
                n = int(parts[2])
            except ValueError:
                continue

            if 1 <= n <= MAX_N:
                k = answers[n]
            else:
                # Spec says this cannot happen. Still produce a syntactically
                # valid line rather than desyncing.
                k = 0

            wf.write(f"ANSWER {k}\n")
            wf.flush()

            # Must read result line and END_ROUND line before next ROUND.
            result = rf.readline()
            if not result:
                return 0

            end_round = rf.readline()
            if not end_round:
                return 0

        return 0


if __name__ == "__main__":
    raise SystemExit(main())