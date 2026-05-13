# bot author: Kimi K2.6 (moonshotai/kimi-k2.6 via OpenRouter)
# bot author: GPT-4

import os
import socket
import sys
import threading
import time
import multiprocessing

# -----------------------------------------------------------------------------
# Precomputed tables for digits 1..4
# -----------------------------------------------------------------------------
POW10 = [1, 10, 100, 1000, 10000, 100000, 1000000, 10000000, 100000000, 1000000000]

DS = [None] * 5
ALT = [None] * 5
REV = [None] * 5

for d in range(1, 5):
    size = POW10[d]
    ds = [0] * size
    alt = [0] * size
    rev = [0] * size
    fmt = f"{{:0{d}d}}"
    for i in range(size):
        s = fmt.format(i)
        total = 0
        a = 0
        sign = 1
        for ch in s:
            digit = ord(ch) - 48
            total += digit
            a += sign * digit
            sign = -sign
        ds[i] = total
        alt[i] = a
        rev[i] = int(s[::-1])
    DS[d] = ds
    ALT[d] = alt
    REV[d] = rev

FIRST_OK = [False] * 10
for _d in (1, 3, 7, 9):
    FIRST_OK[_d] = True


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def max_one_run(n: int) -> int:
    c = 0
    while n:
        n &= n >> 1
        c += 1
    return c


def is_prime(n: int) -> bool:
    # n is always odd, > 2, and not divisible by 3,5,11 for our candidates.
    d = n - 1
    s = (d & -d).bit_length() - 1
    d >>= s
    for a in (2, 325, 9375, 28178, 450775, 9780504, 1795265022):
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


def worker(args):
    idx, k, h_start, h_end = args
    local = []
    pow10_k_1 = POW10[k - 1]
    d1 = k // 2
    d2 = k - d1
    pow10_d2 = POW10[d2]
    ds1 = DS[d1]
    ds2 = DS[d2]
    alt1 = ALT[d1]
    alt2 = ALT[d2]
    sign = 1 if d1 % 2 == 0 else -1
    m = k - 1
    d_low = m // 2
    d_high = m - d_low
    pow10_d_low = POW10[d_low]
    pow10_d_high = POW10[d_high]
    rev_low = REV[d_low]
    rev_high = REV[d_high]
    first_ok = FIRST_OK
    first_digit_div = POW10[k - 1]
    mod11_shift = 1 if (k % 2 == 0) else -1
    do_quick = (k >= 7)

    for h in range(h_start, h_end):
        if not first_ok[h // first_digit_div]:
            continue
        hi = h // pow10_d2
        lo = h % pow10_d2
        last = h % 10
        if (ds1[hi] + ds2[lo] + last) % 3 == 0:
            continue
        alt = alt1[hi] + sign * alt2[lo]
        if (alt * 2 + mod11_shift * last) % 11 == 0:
            continue
        x = h // 10
        a = x // pow10_d_low
        b = x % pow10_d_low
        p = h * pow10_k_1 + rev_low[b] * pow10_d_high + rev_high[a]
        if do_quick:
            if p % 7 == 0 or p % 13 == 0 or p % 17 == 0 or p % 19 == 0 or p % 23 == 0 or p % 29 == 0 or p % 31 == 0 or p % 37 == 0 or p % 41 == 0 or p % 43 == 0:
                continue
        if is_prime(p):
            c = 0
            pp = p
            while pp:
                pp &= pp >> 1
                c += 1
            local.append(c)
    return idx, local


def build_small(answers, target):
    # length 1
    for p in (2, 3, 5, 7):
        answers.append(max_one_run(p))
        if len(answers) >= target:
            return
    # length 2
    answers.append(max_one_run(11))
    if len(answers) >= target:
        return
    # lengths 3,5,7,9,11 (k=3..6)
    for k in range(3, 7):
        start = POW10[k - 1]
        end = POW10[k]
        pow10_k_1 = POW10[k - 1]
        d1 = k // 2
        d2 = k - d1
        pow10_d2 = POW10[d2]
        ds1 = DS[d1]
        ds2 = DS[d2]
        alt1 = ALT[d1]
        alt2 = ALT[d2]
        sign = 1 if d1 % 2 == 0 else -1
        m = k - 1
        d_low = m // 2
        d_high = m - d_low
        pow10_d_low = POW10[d_low]
        pow10_d_high = POW10[d_high]
        rev_low = REV[d_low]
        rev_high = REV[d_high]
        first_ok = FIRST_OK
        first_digit_div = pow10_k_1
        mod11_shift = 1 if (k % 2 == 0) else -1
        for h in range(start, end):
            if not first_ok[h // first_digit_div]:
                continue
            hi = h // pow10_d2
            lo = h % pow10_d2
            last = h % 10
            if (ds1[hi] + ds2[lo] + last) % 3 == 0:
                continue
            alt = alt1[hi] + sign * alt2[lo]
            if (alt * 2 + mod11_shift * last) % 11 == 0:
                continue
            x = h // 10
            a = x // pow10_d_low
            b = x % pow10_d_low
            p = h * pow10_k_1 + rev_low[b] * pow10_d_high + rev_high[a]
            if is_prime(p):
                answers.append(max_one_run(p))
                if len(answers) >= target:
                    return


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    botname = os.environ.get("BOTNAME", "")
    if not botname:
        sys.exit(1)

    TARGET = 1_000_000
    answers = []

    # Generate small lengths immediately in main thread
    build_small(answers, TARGET)

    pool = None
    compute_thread = None

    if len(answers) < TARGET:
        # Need lengths 13 (k=7) and 15 (k=8)
        chunks = []
        idx = 0
        # k=7 : h in [1_000_000 , 10_000_000)
        for h_start in range(1_000_000, 10_000_000, 2_000_000):
            chunks.append((idx, 7, h_start, min(h_start + 2_000_000, 10_000_000)))
            idx += 1
        # k=8 : h in [10_000_000 , 50_000_000)
        for h_start in range(10_000_000, 50_000_000, 2_500_000):
            chunks.append((idx, 8, h_start, min(h_start + 2_500_000, 50_000_000)))
            idx += 1

        pool = multiprocessing.Pool()

        def compute_runner():
            it = pool.imap_unordered(worker, chunks)
            buffer = {}
            next_idx = 0
            for i, local in it:
                buffer[i] = local
                while next_idx in buffer:
                    answers.extend(buffer.pop(next_idx))
                    next_idx += 1
                    if len(answers) >= TARGET:
                        pool.terminate()
                        return
            pool.close()
            pool.join()

        compute_thread = threading.Thread(target=compute_runner, daemon=True)
        compute_thread.start()

    # Connect and handshake
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("localhost", 7474))
    sock.sendall((botname + "\n").encode("ascii"))

    rfile = sock.makefile("r", encoding="ascii", newline="\n")

    try:
        for line in rfile:
            line = line.strip()
            if line.startswith("ROUND "):
                parts = line.split()
                n = int(parts[2])
                deadline = time.time() + 29.5
                while len(answers) < n and time.time() < deadline:
                    time.sleep(0.001)
                if len(answers) >= n:
                    ans = answers[n - 1]
                    sock.sendall(f"ANSWER {ans}\n".encode("ascii"))
                else:
                    # Should not happen if precomputation keeps pace,
                    # but we must send a line to avoid protocol desync.
                    sock.sendall("ANSWER 1\n".encode("ascii"))
            elif line.startswith("OK ") or line.startswith("INVALID "):
                pass
            elif line.startswith("END_ROUND "):
                pass
            elif line == "TOURNAMENT_END":
                break
    finally:
        rfile.close()
        sock.close()
        if pool is not None:
            pool.terminate()


if __name__ == "__main__":
    main()
