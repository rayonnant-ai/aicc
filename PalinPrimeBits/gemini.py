# bot author: Gemini Pro 3.1
# bot author: Gemini 3.1 Pro
import os
import sys
import socket

# Pre-computed small primes for fast divisibility checks
SMALL_PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97]

def is_prime(n):
    if n < 100:
        return n in SMALL_PRIMES
    for p in SMALL_PRIMES:
        if n % p == 0:
            return False
    
    # Miller-Rabin primality test for larger numbers
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
        
    # Bases for deterministic primality test up to 3.8 * 10^18
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23):
        if n <= a:
            break
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True

def generate_palindromes():
    """Generates palindromes sequentially. Skips even lengths > 2."""
    yield 2
    yield 3
    yield 5
    yield 7
    yield 11
    
    length = 3
    while True:
        half = (length + 1) // 2
        # A prime > 5 cannot end in 0, 2, 4, 5, 6, 8. 
        # For a palindrome, the first digit must match the last.
        # So the leading digit must be 1, 3, 7, or 9.
        for leading in (1, 3, 7, 9):
            start = leading * 10**(half - 1)
            end = (leading + 1) * 10**(half - 1)
            
            mult = 10**(half - 1)
            
            for i in range(start, end):
                temp = i // 10
                rev = 0
                while temp > 0:
                    rev = rev * 10 + temp % 10
                    temp //= 10
                yield i * mult + rev
                
        length += 2

class PrimeCache:
    def __init__(self):
        self.primes = []
        self.generator = generate_palindromes()
        
    def get_nth(self, n):
        while len(self.primes) < n:
            pal = next(self.generator)
            if is_prime(pal):
                self.primes.append(pal)
        return self.primes[n - 1]

def get_max_1_run(n):
    # Get the binary representation without the '0b' prefix
    b = bin(n)[2:]
    # Split by '0' to get all contiguous runs of '1's
    return max(len(run) for run in b.split('0'))

def main():
    botname = os.environ.get('BOTNAME')
    if not botname:
        sys.exit(1)

    host = 'localhost'
    port = 7474

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
    except Exception as e:
        sys.exit(1)

    # Use makefile to cleanly read and write line by line
    f_in = sock.makefile('r', newline='\n')
    f_out = sock.makefile('w', newline='\n')

    # Send the BOTNAME per handshake protocol
    f_out.write(f"{botname}\n")
    f_out.flush()

    cache = PrimeCache()

    while True:
        line = f_in.readline()
        if not line:
            break
            
        line = line.rstrip('\n')
        
        if line.startswith('ROUND'):
            parts = line.split()
            if len(parts) == 3:
                round_num = parts[1]
                n = int(parts[2])
                
                p_n = cache.get_nth(n)
                ans = get_max_1_run(p_n)
                
                f_out.write(f"ANSWER {ans}\n")
                f_out.flush()
                
                # Consume the OK/INVALID line and END_ROUND line to maintain sync
                res_line = f_in.readline()
                end_line = f_in.readline()
                
        elif line == 'TOURNAMENT_END':
            break

    sock.close()

if __name__ == '__main__':
    main()