# bot author: DeepSeek V4-Pro (deepseek/deepseek-v4-pro via OpenRouter)
# bot author: optimized Python 3.10 bot

import os
import sys
import socket
import threading

class PalPrimeGenerator:
    def __init__(self):
        self.primes = [2, 3, 5, 7, 11]
        self.k = 1
        self.first_digits = (1, 3, 7, 9)
        self.digit_idx = 0
        self.first_half = None
        self.sub_start = None
        self.sub_end = None
        self.end = None
        self.pow10 = [1]
        for _ in range(1, 20):
            self.pow10.append(self.pow10[-1] * 10)
        self.small_primes = (7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97)
        self.mr_bases = (2, 325, 9375, 28178, 450775, 9780504, 1795265022)
        self._init_k_state()

    def _init_k_state(self):
        start = self.pow10[self.k]
        self.end = self.pow10[self.k + 1] - 1
        self.digit_idx = 0
        self._set_digit_range()

    def _set_digit_range(self):
        if self.digit_idx >= len(self.first_digits):
            self.k += 1
            self._init_k_state()
            return
        fd = self.first_digits[self.digit_idx]
        self.sub_start = fd * self.pow10[self.k]
        self.sub_end = min((fd + 1) * self.pow10[self.k] - 1, self.end)
        self.first_half = self.sub_start

    def _next_candidate(self):
        while True:
            if self.first_half > self.sub_end:
                self.digit_idx += 1
                self._set_digit_range()
                continue
            first_half = self.first_half
            self.first_half += 1
            temp = first_half // 10
            rev = 0
            while temp:
                rev = rev * 10 + temp % 10
                temp //= 10
            p = first_half * self.pow10[self.k] + rev
            return p

    def _is_prime(self, p):
        if p < 2:
            return False
        if p in (2, 3, 5, 7, 11):
            return True
        if p % 2 == 0 or p % 3 == 0 or p % 5 == 0:
            return False
        for prime in self.small_primes:
            if p % prime == 0:
                return False
        d = p - 1
        s = 0
        while d % 2 == 0:
            d //= 2
            s += 1
        for a in self.mr_bases:
            if a % p == 0:
                continue
            x = pow(a, d, p)
            if x == 1 or x == p - 1:
                continue
            for _ in range(s - 1):
                x = (x * x) % p
                if x == p - 1:
                    break
            else:
                return False
        return True

    def next_prime(self):
        while True:
            p = self._next_candidate()
            if self._is_prime(p):
                return p


# Global generator and lock
gen = PalPrimeGenerator()
gen_lock = threading.Lock()


def get_p(n):
    with gen_lock:
        while len(gen.primes) < n:
            p = gen.next_prime()
            gen.primes.append(p)
    return gen.primes[n - 1]


def longest_one_run(x):
    b = bin(x)[2:]
    return max(len(seg) for seg in b.split('0'))


def main():
    botname = os.environ.get('BOTNAME')
    if not botname:
        sys.exit(1)

    # Background precomputation up to 1,000,000
    def precompute():
        while len(gen.primes) < 1_000_000:
            with gen_lock:
                if len(gen.primes) >= 1_000_000:
                    break
                p = gen.next_prime()
                gen.primes.append(p)

    t = threading.Thread(target=precompute, daemon=True)
    t.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode('ascii'))

    f = sock.makefile('r', encoding='ascii')
    for line in f:
        line = line.strip()
        if line.startswith('ROUND'):
            parts = line.split()
            # round_num = int(parts[1])  # not needed
            n = int(parts[2])
            pn = get_p(n)
            k = longest_one_run(pn)
            ans = f"ANSWER {k}\n"
            sock.sendall(ans.encode('ascii'))
        elif line.startswith('OK') or line.startswith('INVALID'):
            pass
        elif line.startswith('END_ROUND'):
            pass
        elif line == 'TOURNAMENT_END':
            break
    sock.close()


if __name__ == '__main__':
    main()
