# bot author: Nemotron 3 Super (nvidia/nemotron-3-super-120b-a12b via OpenRouter)
# bot author: gpt-4o
import os
import sys
import socket

def main():
    botname = os.environ.get('BOTNAME', '')
    if not botname:
        sys.exit(1)
    try:
        sock = socket.create_connection(('localhost', 7474))
    except Exception:
        sys.exit(1)
    try:
        sock.sendall((botname + '\n').encode('ascii'))
        file = sock.makefile('r', encoding='ascii')
        while True:
            line = file.readline()
            if not line:
                break
            line = line.rstrip('\n')
            if line == 'TOURNAMENT_END':
                break
            if not line.startswith('ROUND'):
                # Unexpected line; ignore or break?
                continue
            # Parse ROUND line
            parts = line.split()
            # ROUND <round_num> <w> <h> <N>
            if len(parts) < 4:
                continue
            try:
                w = int(parts[2])
                h = int(parts[3])
                N = int(parts[4])
            except ValueError:
                continue
            dots = []
            for _ in range(N):
                dot_line = file.readline()
                if not dot_line:
                    break
                dot_line = dot_line.rstrip('\n')
                # DOT <idx> <x> <y>
                dparts = dot_line.split()
                if len(dparts) >= 3:
                    try:
                        x = float(dparts[1])
                        y = float(dparts[2])
                        dots.append((x, y))
                    except ValueError:
                        pass
            # Submit trivial solution: one tiny circle per dot
            radius = 0.0000004  # 4e-7, ensures non-overlap due to epsilon
            for (x, y) in dots:
                circ_line = f'CIRCLE {x} {y} {radius}\n'
                sock.sendall(circ_line.encode('ascii'))
            sock.sendall(b'END\n')
            # Read result line
            result_line = file.readline()
            if not result_line:
                break
            # Read END_ROUND line
            end_round_line = file.readline()
            if not end_round_line:
                break
    finally:
        sock.close()

if __name__ == '__main__':
    main()
