# bot author: Grok Expert 4.20
#!/usr/bin/env python3
# bot author: Grok (xAI) - PalinPrimeBits tournament bot

import os
import sys
import socket

def is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n == 2 or n == 3:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    SMALL_PRIMES = [5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97]
    for p in SMALL_PRIMES:
        if p * p > n:
            break
        if n % p == 0:
            return False
    # Miller-Rabin deterministic for n < ~10^16 and beyond
    s = 0
    d = n - 1
    while d % 2 == 0:
        d //= 2
        s += 1
    witnesses = [2, 3, 5, 7, 11, 13, 17, 19, 23]
    for a in witnesses:
        if a >= n:
            break
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(1, s):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def generate_palindromic_primes(max_n: int = 1000000):
    primes = []
    # 1-digit
    for i in range(2, 10):
        if is_prime(i):
            primes.append(i)
            if len(primes) >= max_n:
                return primes
    # 2-digit (only 11)
    if is_prime(11):
        primes.append(11)
        if len(primes) >= max_n:
            return primes
    # odd digit lengths >= 3 up to 15
    for d in range(3, 16, 2):
        if len(primes) >= max_n:
            break
        m = d // 2
        root_start = 10 ** m
        root_end = 10 ** (m + 1)
        for root in range(root_start, root_end):
            if len(primes) >= max_n:
                break
            s = str(root)
            pal_str = s + s[:m][::-1]
            pal = int(pal_str)
            if is_prime(pal):
                primes.append(pal)
    return primes[:max_n]


def longest_one_run(num: int) -> int:
    if num <= 0:
        return 0
    binary = bin(num)[2:]
    max_run = 0
    current = 0
    for bit in binary:
        if bit == '1':
            current += 1
            if current > max_run:
                max_run = current
        else:
            current = 0
    return max_run


def main():
    botname = os.environ.get('BOTNAME')
    if not botname:
        sys.exit(1)

    # Precompute first 1,000,000 palindromic primes and their answers
    pal_primes = generate_palindromic_primes(1000000)
    answers = [0] + [longest_one_run(p) for p in pal_primes]

    # Connect to server
    HOST = 'localhost'
    PORT = 7474
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        sock.sendall(f"{botname}\n".encode('ascii'))

        sock_file = sock.makefile(mode='r', encoding='ascii', newline='\n')
        try:
            while True:
                line = sock_file.readline()
                if not line:
                    break
                line = line.rstrip('\n\r')
                if not line:
                    continue
                tokens = line.split()
                if not tokens:
                    continue
                cmd = tokens[0]
                if cmd == 'ROUND':
                    n = int(tokens[2])
                    k = answers[n]
                    sock.sendall(f"ANSWER {k}\n".encode('ascii'))
                elif cmd == 'TOURNAMENT_END':
                    break
                # Other lines (OK, INVALID, END_ROUND) are read and ignored to stay in sync
        finally:
            sock_file.close()


if __name__ == '__main__':
    main()