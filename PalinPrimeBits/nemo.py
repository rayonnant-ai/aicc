# bot author: Nemotron 3 Super (nvidia/nemotron-3-super-120b-a12b via OpenRouter)
# bot author: gpt-4
import os
import socket
import math

def sieve(limit):
    is_prime = bytearray(b'\x01') * (limit + 1)
    is_prime[0:2] = b'\x00\x00'
    for i in range(2, int(limit ** 0.5) + 1):
        if is_prime[i]:
            step = i
            start = i * i
            is_prime[start:limit + 1:step] = b'\x00' * ((limit - start) // step + 1)
    return [i for i, v in enumerate(is_prime) if v]

SMALL_PRIMES = sieve(1000)  # includes 2,3,5,7,...

def is_prime_mr(n: int) -> bool:
    if n < 2:
        return False
    # Miller-Rabin deterministic for 64-bit integers
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in (2, 325, 9375, 28178, 450775, 9780504, 1795265022):
        if a % n == 0:
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

def max_ones_run(x: int) -> int:
    max_run = cur = 0
    while x:
        if x & 1:
            cur += 1
            if cur > max_run:
                max_run = cur
        else:
            cur = 0
        x >>= 1
    return max_run

def palindromic_prime_gen():
    # yield the first few known palindromic primes
    yield 2
    yield 3
    yield 5
    yield 7
    yield 11
    length = 3
    while True:
        k = length // 2
        pow10_k = 10 ** k
        for fd in (1, 3, 7, 9):
            base = fd * pow10_k
            for rest in range(0, 10 ** k):
                a = base + rest
                x = a // 10
                # reverse x of k digits
                rev = 0
                t = x
                for _ in range(k):
                    rev = rev * 10 + (t % 10)
                    t //= 10
                pal = a * pow10_k + rev
                if pal % 3 == 0:
                    continue
                # trial division by small primes
                limit_isqrt = int(math.isqrt(pal))
                composite = False
                for p in SMALL_PRIMES:
                    if p * p > pal:
                        break
                    if pal % p == 0:
                        composite = True
                        break
                if composite:
                    continue
                if is_prime_mr(pal):
                    yield pal
        length += 2

def main():
    bot_name = os.environ.get('BOTNAME')
    if not bot_name:
        sys.exit(1)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', 7474))
        sock.sendall((bot_name + '\n').encode())
        file = sock.makefile('r', encoding='ascii')
        answers = bytearray()
        # pre-seed answers for n=1..5
        answers.extend([max_ones_run(2), max_ones_run(3), max_ones_run(5), max_ones_run(7), max_ones_run(11)])
        prime_iter = palindromic_prime_gen()
        # we already consumed the first 5 primes from the generator; need to advance it to after 11
        for _ in range(5):
            next(prime_iter)
        while True:
            line = file.readline()
            if not line:
                break
            line = line.rstrip('\n')
            if line.startswith('ROUND'):
                _, _, n_str = line.split()
                n = int(n_str)
                # ensure we have computed up to n
                while len(answers) < n:
                    p = next(prime_iter)
                    answers.append(max_ones_run(p))
                ans = answers[n - 1]
                sock.sendall((f'ANSWER {ans}\n'.encode()))
                # read result line and END_ROUND line
                file.readline()  # result line (OK or INVALID)
                file.readline()  # END_ROUND
            elif line.startswith('TOURNAMENT_END'):
                break
            # other lines (OK, INVALID, END_ROUND) are ignored here
    finally:
        sock.close()

if __name__ == '__main__':
    import sys
    main()
