# bot author: GLM 5.1 (z-ai/glm-5.1 via OpenRouter)
# bot author: Claude 3.5 Sonnet

import os
import sys
import socket
import select
import time

def reverse_digits(n):
    r = 0
    while n:
        r = r * 10 + n % 10
        n //= 10
    return r

def digit_sum(n):
    s = 0
    while n:
        s += n % 10
        n //= 10
    return s

SMALL_PRIMES = (
    7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73,79,83,89,97,
    101,103,107,109,113,127,131,137,139,149,151,157,163,167,173,179,
    181,191,193,197,199,211,223,227,229,233,239,241,251,257,263,269,
    271,277,281,283,293,307,311,313,317,331,337,347,349,353,359,367,
    373,379,383,389,397,401,409,419,421,431,433,439,443,449,457,461,
    463,467,479,487,491,499,503,509,521,523,541,547,557,563,569,571,
    577,587,593,599,601,607,613,617,619,631,641,643,647,653,659,661,
    673,677,683,691,701,709,719,727,733,739,743,751,757,761,769,773,
    787,797,809,811,821,823,827,829,839,853,857,859,863,877,881,883,
    887,907,911,919,929,937,941,947,953,967,971,977,983,991,997
)

def is_prime(n):
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0:
        return n == 2
    if n % 3 == 0:
        return n == 3
    if n % 5 == 0:
        return n == 5
    for p in SMALL_PRIMES:
        if n == p:
            return True
        if n % p == 0:
            return False
        if p * p > n:
            return True
    d = n - 1
    r = 0
    while d & 1 == 0:
        r += 1
        d >>= 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if a >= n:
            continue
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True

def longest_1_run(n):
    best = 0
    cur = 0
    while n:
        if n & 1:
            cur += 1
        else:
            if cur > best:
                best = cur
            cur = 0
        n >>= 1
    if cur > best:
        best = cur
    return best

def gen_palindromic_primes():
    for p in (2, 3, 5, 7):
        yield p
    yield 11
    first_digits = (1, 3, 7, 9)
    for length in range(3, 22, 2):
        k = length // 2
        power = 10 ** k
        for fd in first_digits:
            half_start = fd * power
            half_end = (fd + 1) * power
            for half in range(half_start, half_end):
                ds = 2 * digit_sum(half // 10) + half % 10
                if ds % 3 == 0:
                    continue
                p = half * power + reverse_digits(half // 10)
                if is_prime(p):
                    yield p

def read_line(sock, buf):
    while b'\n' not in buf:
        data = sock.recv(4096)
        if not data:
            raise ConnectionError("Connection closed")
        buf += data
    idx = buf.index(b'\n')
    line = buf[:idx].decode('ascii')
    buf = buf[idx + 1:]
    return line, buf

def main():
    botname = os.environ.get('BOTNAME', '')
    if not botname:
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode('ascii'))

    pp_gen = gen_palindromic_primes()
    pp_list = []
    buf = b''

    # Precompute while waiting for first ROUND line
    count = 0
    while len(pp_list) < 1_000_000:
        count += 1
        if count % 100 == 0:
            readable, _, _ = select.select([sock], [], [], 0)
            if readable:
                data = sock.recv(4096)
                if not data:
                    break
                buf += data
                if b'\n' in buf:
                    break
        try:
            pp_list.append(next(pp_gen))
        except StopIteration:
            break

    # Process rounds
    for _ in range(10):
        line, buf = read_line(sock, buf)
        parts = line.split()

        if parts[0] == 'TOURNAMENT_END':
            break
        if parts[0] != 'ROUND':
            continue

        n = int(parts[2])

        # Extend precomputation if needed
        deadline = time.time() + 25
        while n > len(pp_list) and time.time() < deadline:
            try:
                pp_list.append(next(pp_gen))
            except StopIteration:
                break

        if n <= len(pp_list):
            answer = longest_1_run(pp_list[n - 1])
        else:
            answer = 1

        sock.sendall(f'ANSWER {answer}\n'.encode('ascii'))

        # Read result line (OK or INVALID)
        line, buf = read_line(sock, buf)

        # Read END_ROUND
        line, buf = read_line(sock, buf)

    # Read TOURNAMENT_END
    try:
        line, buf = read_line(sock, buf)
    except ConnectionError:
        pass

    try:
        sock.close()
    except Exception:
        pass

if __name__ == '__main__':
    main()
