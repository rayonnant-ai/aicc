import socket
import json
import time
import sys

def solve_knight_tour(weights):
    """Return a knight's tour minimizing approximate total time."""
    rows = len(weights)
    cols = len(weights[0])
    N = rows * cols
    # Knight moves
    moves = [(2,1),(2,-1),(-2,1),(-2,-1),(1,2),(1,-2),(-1,2),(-1,-2)]

    def neighbors(r, c):
        for dr, dc in moves:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                yield (nr, nc)

    # Pre‑compute neighbor lists for speed
    neigh = {}
    for r in range(rows):
        for c in range(cols):
            neigh[(r, c)] = list(neighbors(r, c))

    # Helper: number of unvisited neighbors of a cell
    def onward_degree(r, c, visited):
        return sum(1 for nr, nc in neigh[(r, c)] if not visited[nr][nc])

    # Try starting from the lightest squares first (light weights early reduce total time)
    starts = sorted(
        [(r, c) for r in range(rows) for c in range(cols)],
        key=lambda rc: weights[rc[0]][rc[1]]
    )

    start_time = time.time()
    timeout = 9.0  # seconds, leave buffer for network

    # --- Heuristic DFS -------------------------------------------------
    for sr, sc in starts[:15]:  # try a handful of lightest starts
        if time.time() - start_time > timeout:
            break
        visited = [[False] * cols for _ in range(rows)]
        path = []

        # Stack elements: (r, c, step, next_neighbor_index)
        stack = []
        visited[sr][sc] = True
        path.append((sr, sc))
        stack.append((sr, sc, 1, 0))  # step=1, next neighbor index to try

        while stack and time.time() - start_time < timeout:
            r, c, step, next_i = stack[-1]
            if step == N:  # tour complete
                return [list(pos) for pos in path]

            nbrs = neigh[(r, c)]
            # Collect unvisited neighbors starting from next_i
            unvisited = []
            for i in range(next_i, len(nbrs)):
                nr, nc = nbrs[i]
                if not visited[nr][nc]:
                    unvisited.append((nr, nc, i+1))  # store next index to try after this
            if not unvisited:
                # Dead end – backtrack
                visited[r][c] = False
                path.pop()
                stack.pop()
                continue

            # Sort by weight ascending, then onward degree ascending
            unvisited.sort(key=lambda x: (weights[x[0]][x[1]], onward_degree(x[0], x[1], visited)))
            nr, nc, next_index = unvisited[0]  # best candidate

            # Update stack top to try remaining neighbors later
            stack[-1] = (r, c, step, next_index)
            # Push new state
            visited[nr][nc] = True
            path.append((nr, nc))
            stack.append((nr, nc, step+1, 0))

        # If we exited due to timeout, the loop continues with next start

    # --- Fallback: Warnsdorff (no weight) with multiple starts --------
    for sr, sc in starts[:30]:
        if time.time() - start_time > timeout:
            break
        visited = [[False] * cols for _ in range(rows)]
        path = []
        r, c = sr, sc
        for step in range(1, N+1):
            path.append((r, c))
            visited[r][c] = True
            if step == N:
                break
            # Choose unvisited neighbor with minimum onward degree
            min_deg = None
            best = None
            for nr, nc in neigh[(r, c)]:
                if not visited[nr][nc]:
                    deg = onward_degree(nr, nc, visited)
                    if min_deg is None or deg < min_deg:
                        min_deg = deg
                        best = (nr, nc)
            if best is None:
                break  # dead end
            r, c = best
        else:
            # Completed tour
            return [list(pos) for pos in path]

    # If all else fails, return empty list (will be judged invalid)
    return []

def main():
    host = 'localhost'
    port = 7474
    bot_name = 'nemotron_bot'  # any {model_name}_bot format works
    try:
        sock = socket.create_connection((host, port))
        sock.sendall((bot_name + '\n').encode())
        sbuf = sock.makefile('r')
        while True:
            line = sbuf.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith('ROUND'):
                # Read SIZE line
                size_line = sbuf.readline().strip()
                if not size_line.startswith('SIZE'):
                    break
                size = int(size_line.split()[1])
                # Receive exactly `size` bytes
                payload = b''
                while len(payload) < size:
                    chunk = sock.recv(size - len(payload))
                    if not chunk:
                        break
                    payload += chunk
                if len(payload) < size:
                    break
                data = json.loads(payload.decode())
                rows = data['rows']
                cols = data['cols']
                weights = data['weights']
                tour = solve_knight_tour(weights)
                response = json.dumps({'tour': tour}) + '\n'
                sock.sendall(response.encode())
                # Optionally read server response (VALID/INVALID/TIMEOUT)
                _ = sbuf.readline().strip()
            elif line.startswith('VALID') or line.startswith('INVALID') or line.startswith('TIMEOUT'):
                # Just continue to next round
                continue
            else:
                # Unexpected line – assume end of communication
                break
        sock.close()
    except Exception as e:
        sys.stderr.write(f'Error: {e}\n')
        try:
            sock.close()
        except:
            pass

if __name__ == '__main__':
    main()