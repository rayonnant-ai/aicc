#!/usr/bin/env python3
"""
Offline: enumerate palindromic primes in ascending order and emit
(n, p(n), longest_binary_1_run) for the indices needed by the tournament
schedule. Output is written to `answers.txt` as one line per scheduled n.

Strategy:
- Hardcode the first five palindromic primes: 2, 3, 5, 7, 11. All higher
  palprimes have odd digit length (every even-length palindrome > 11 is
  divisible by 11, so it cannot be prime).
- For each odd digit length d = 3, 5, 7, ..., enumerate the 9 * 10**((d-1)//2)
  palindromes by their left half, test primality with Miller-Rabin, and
  yield in ascending order (loop over the half in ascending integer order;
  that produces palindromes in ascending value order).
- Stop when we have produced all scheduled n's.

Miller-Rabin uses a fixed set of witnesses that is deterministic for
n < 3,317,044,064,679,887,385,961,981 (covers anything up to 24-digit
palindromes, far past where we will go).
"""
import sys
import time

# ── Schedule: one n per round ────────────────────────────────────────────────
SCHEDULE = [5000, 10000, 20000, 30000, 50000, 75000, 100000, 250000, 500000, 1000000]
MAX_N = max(SCHEDULE)


# Deterministic Miller-Rabin witnesses for n < 3.317e24.
MR_WITNESSES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def is_prime(n):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47):
        if n == p:
            return True
        if n % p == 0:
            return False
    d = n - 1
    s = 0
    while d & 1 == 0:
        d >>= 1
        s += 1
    for a in MR_WITNESSES:
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


def palprimes_iter():
    """Yield palindromic primes in ascending order."""
    yield 2
    yield 3
    yield 5
    yield 7
    yield 11
    d = 3
    while True:
        half_len = (d + 1) // 2     # for d=3: half_len=2; d=5: 3; d=7: 4; ...
        half_lo = 10 ** (half_len - 1)
        half_hi = 10 ** half_len
        for half in range(half_lo, half_hi):
            s = str(half)
            rev = s[-2::-1]         # drop last char (the "middle"), reverse
            pal = int(s + rev)
            if is_prime(pal):
                yield pal
        d += 2


def longest_1_run(n):
    s = bin(n)[2:]
    best = cur = 0
    for ch in s:
        if ch == '1':
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best


def main():
    targets = sorted(set(SCHEDULE))
    target_set = set(targets)

    found = {}
    t0 = time.time()
    next_milestone = 1
    n = 0
    last_print = t0
    for p in palprimes_iter():
        n += 1
        if n in target_set:
            run = longest_1_run(p)
            found[n] = (p, run)
            print(f"[+] n={n:>8}  p={p:>20}  digits={len(str(p))}  "
                  f"binlen={p.bit_length()}  1run={run}  "
                  f"elapsed={time.time() - t0:.1f}s")
            sys.stdout.flush()
        if n == next_milestone:
            now = time.time()
            if now - last_print > 5.0:
                print(f"    .. n={n:>8}  p={p:>20}  elapsed={now - t0:.1f}s")
                last_print = now
            next_milestone = max(next_milestone * 2, n + 1)
        if n >= MAX_N:
            break

    print(f"\n[*] Done in {time.time() - t0:.1f}s. Writing answers.txt")
    with open("answers.txt", "w", encoding="utf-8") as f:
        for n_target in SCHEDULE:
            p, run = found[n_target]
            f.write(f"{n_target} {p} {run}\n")
    print("[*] Wrote answers.txt")


if __name__ == "__main__":
    main()
