#!/usr/bin/env python3
# bot author: Gemini 3 Flash

import os
import sys
import socket

def get_longest_1_run(n_val):
    """Calculates the length of the longest contiguous run of 1s in binary."""
    binary_repr = bin(n_val)[2:]
    runs = binary_repr.split('0')
    return max(len(run) for run in runs) if runs else 0

def is_palindromic(n_val):
    """Checks if the decimal representation of n is a palindrome."""
    s = str(n_val)
    return s == s[::-1]

def find_nth_palindromic_prime(n_target):
    """
    Finds the n-th palindromic prime.
    Uses a generator for palindromes to minimize primality tests.
    """
    if n_target == 1: return 2
    if n_target == 2: return 3
    if n_target == 3: return 5
    if n_target == 4: return 7
    if n_target == 5: return 11
    
    count = 5 # We start after 11
    
    # Palindromes with even number of digits (except 11) are divisible by 11.
    # Therefore, we only need to generate palindromes with an odd number of digits.
    # We iterate by the number of digits 'd'.
    d = 3
    while True:
        # For an odd number of digits d = 2k + 1, the first k+1 digits determine the palindrome.
        k = (d - 1) // 2
        start = 10**k
        end = 10**(k + 1)
        
        for i in range(start, end):
            s = str(i)
            # Construct palindrome: e.g., i=12, d=3 -> "12" + "1" = "121"
            p_str = s + s[:-1][::-1]
            p_int = int(p_str)
            
            # Primality test
            if is_prime(p_int):
                count += 1
                if count == n_target:
                    return p_int
        d += 2

def is_prime(num):
    """Standard trial division primality test."""
    if num < 2: return False
    if num % 2 == 0: return num == 2
    if num % 3 == 0: return num == 3
    for i in range(5, int(num**0.5) + 1, 6):
        if num % i == 0 or num % (i + 2) == 0:
            return False
    return True

def run_bot():
    # 1. Handshake setup
    bot_name = os.environ.get('BOTNAME')
    if not bot_name:
        sys.exit(1)

    host = 'localhost'
    port = 7474

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            
            # Send BOTNAME
            s.sendall(f"{bot_name}\n".encode('ascii'))
            
            # 2. Main Loop
            f = s.makefile('r', encoding='ascii', newline='\n')
            
            while True:
                line = f.readline()
                if not line:
                    break
                
                parts = line.strip().split()
                if not parts:
                    continue
                
                cmd = parts[0]
                
                if cmd == "ROUND":
                    # ROUND <round_num> <n>
                    n_val = int(parts[2])
                    
                    # Solve
                    p_n = find_nth_palindromic_prime(n_val)
                    k = get_longest_1_run(p_n)
                    
                    # Submit
                    s.sendall(f"ANSWER {k}\n".encode('ascii'))
                    
                elif cmd == "OK" or cmd == "INVALID":
                    # Server logic: result line followed by END_ROUND
                    continue
                    
                elif cmd == "END_ROUND":
                    continue
                    
                elif cmd == "TOURNAMENT_END":
                    break
                    
    except Exception:
        sys.exit(1)

if __name__ == "__main__":
    run_bot()