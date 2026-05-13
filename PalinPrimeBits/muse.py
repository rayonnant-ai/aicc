# bot author: Meta Muse Spark
# bot author: Muse Spark
import os
import sys
import socket

# ---------- palindromic prime utilities ----------
def is_prime(n: int) -> bool:
    if n < 2:
        return False
    # small primes
    small = (2,3,5,7,11,13,17,19,23,29,31,37)
    for p in small:
        if n % p == 0:
            return n == p
    d = n-1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    # deterministic for 64-bit
    for a in (2,325,9375,28178,450775,9780504,1795265022):
        if a % n == 0:
            continue
        x = pow(a, d, n)
        if x == 1 or x == n-1:
            continue
        for _ in range(s-1):
            x = (x * x) % n
            if x == n-1:
                break
        else:
            return False
    return True

def longest_one_run(n: int) -> int:
    b = bin(n)[2:]
    best = cur = 0
    for ch in b:
        if ch == '1':
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best

def make_pal(half: int, odd: bool) -> int:
    pal = half
    x = half // 10 if odd else half
    while x:
        pal = pal * 10 + (x % 10)
        x //= 10
    return pal

# caches
pal_primes = [2,3,5,7,11]
runs = [longest_one_run(p) for p in pal_primes]

# generator state
_next_digit = 3  # next odd length to generate
_next_half = 10  # start of 2-digit halves for length 3

def ensure_n(n: int):
    global _next_digit, _next_half
    while len(pal_primes) < n:
        half_len = (_next_digit + 1)//2
        start = 10**(half_len-1)
        end = 10**half_len
        if _next_half < start:
            _next_half = start
        for half in range(_next_half, end):
            # quick filters: first digit odd and not 5
            first = half // (10**(half_len-1))
            if first & 1 == 0 or first == 5:
                continue
            pal = make_pal(half, True)
            if pal % 3 == 0:
                continue
            if is_prime(pal):
                pal_primes.append(pal)
                runs.append(longest_one_run(pal))
                if len(pal_primes) >= n:
                    _next_half = half + 1
                    return
        _next_digit += 2
        _next_half = 10**((_next_digit-1)//2)

# ---------- network protocol ----------
def main():
    botname = os.environ.get('BOTNAME')
    if not botname or not (1 <= len(botname) <= 32):
        sys.exit(1)

    s = socket.create_connection(('localhost', 7474))
    s.sendall((botname + '\n').encode('ascii'))

    f = s.makefile('r', newline='\n')

    while True:
        line = f.readline()
        if not line:
            break
        line = line.rstrip('\n')
        if line.startswith('ROUND'):
            _, _, n_str = line.split()
            n = int(n_str)
            ensure_n(n)
            k = runs[n-1]
            s.sendall(f'ANSWER {k}\n'.encode('ascii'))
            # read result and END_ROUND to stay in sync
            _ = f.readline()  # OK or INVALID
            _ = f.readline()  # END_ROUND
        elif line == 'TOURNAMENT_END':
            break
    s.close()

if __name__ == '__main__':
    main()