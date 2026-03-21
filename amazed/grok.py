import socket
from collections import deque
import sys

dirs = {
    'U': (-1, 0),
    'D': (1, 0),
    'L': (0, -1),
    'R': (0, 1)
}

class MazeBot:
    def __init__(self, name="grok_bot"):
        self.name = name
        self.sock = None
        self.file = None
        self.maze_map = {}
        self.portals = {}
        self.r = 1
        self.c = 1
        self.last_move = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(('localhost', 7474))
        self.file = self.sock.makefile("r", encoding="ascii")
        self.sock.sendall(f"{self.name}\n".encode("ascii"))

    def read_line(self):
        line = self.file.readline()
        if not line:
            print("Connection closed", file=sys.stderr)
            sys.exit(0)
        return line.rstrip('\n')

    def read_view(self):
        view = []
        for _ in range(5):
            line = self.file.readline().rstrip('\n')
            view.append(line)
        return view

    def update_map(self, view):
        for i in range(5):
            for j in range(5):
                pos = (self.r - 2 + i, self.c - 2 + j)
                cell = view[i][j]
                if pos not in self.maze_map or self.maze_map[pos] == '?':
                    self.maze_map[pos] = cell

    def update_portals(self):
        self.portals = {let: [] for let in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'}
        for pos, cell in self.maze_map.items():
            if cell in self.portals:
                if pos not in self.portals[cell]:
                    self.portals[cell].append(pos)

    def find_exit(self):
        for pos, cell in self.maze_map.items():
            if cell == '<':
                return pos
        return None

    def bfs_to_target(self, sr, sc, tr, tc):
        if (sr, sc) == (tr, tc):
            return []
        visited = set([(sr, sc)])
        q = deque([(sr, sc, [])])
        while q:
            r, c, path = q.popleft()
            for m, (dr, dc) in dirs.items():
                nr, nc = r + dr, c + dc
                cell = self.maze_map.get((nr, nc), '?')
                if cell == '#' or cell == '?':
                    continue
                if cell.isupper() and len(self.portals.get(cell, [])) == 2:
                    p1, p2 = self.portals[cell]
                    land = p1 if (nr, nc) == p2 else p2
                else:
                    land = (nr, nc)
                lr, lc = land
                if (lr, lc) in visited:
                    continue
                visited.add((lr, lc))
                new_path = path + [m]
                if (lr, lc) == (tr, tc):
                    return new_path
                q.append((lr, lc, new_path))
        return None

    def get_exploration_path(self):
        visited = set([(self.r, self.c)])
        q = deque([(self.r, self.c, [])])
        while q:
            r, c, path = q.popleft()
            for m, (dr, dc) in dirs.items():
                nr, nc = r + dr, c + dc
                cell = self.maze_map.get((nr, nc), '?')
                if cell == '#':
                    continue
                if cell.isupper() and len(self.portals.get(cell, [])) == 2:
                    p1, p2 = self.portals[cell]
                    land = p1 if (nr, nc) == p2 else p2
                else:
                    land = (nr, nc)
                lr, lc = land
                if (lr, lc) in visited:
                    continue
                visited.add((lr, lc))
                new_path = path + [m]
                if cell == '?':
                    return new_path
                q.append((lr, lc, new_path))
        return None

    def choose_move(self):
        exit_pos = self.find_exit()
        if exit_pos:
            path = self.bfs_to_target(self.r, self.c, *exit_pos)
            if path:
                return path[0]
        path = self.get_exploration_path()
        if path:
            return path[0]
        # wander (prefer directions that might lead SE)
        for m in 'RDLU':
            dr, dc = dirs[m]
            nr, nc = self.r + dr, self.c + dc
            if self.maze_map.get((nr, nc), '?') != '#':
                return m
        return 'U'

    def send_move(self, move):
        self.sock.sendall((move + "\n").encode("ascii"))
        self.last_move = move

    def run(self):
        self.connect()
        # Initial ROUND + view
        line = self.read_line()
        if line.startswith("ROUND"):
            view = self.read_view()
            self.maze_map = {}
            self.update_map(view)
            self.update_portals()
            move = self.choose_move()
            self.send_move(move)
        # Main response loop
        while True:
            line = self.read_line()
            if line.startswith("ROUND"):
                view = self.read_view()
                self.maze_map = {}
                self.r = 1
                self.c = 1
                self.update_map(view)
                self.update_portals()
                move = self.choose_move()
                self.send_move(move)
                continue
            if line.startswith("DONE") or line == "ELIMINATED":
                print(line, file=sys.stderr)
                continue
            if line == "WALL":
                # Learn the wall immediately
                if self.last_move:
                    dr, dc = dirs[self.last_move]
                    wall_r = self.r + dr
                    wall_c = self.c + dc
                    self.maze_map[(wall_r, wall_c)] = '#'
                move = self.choose_move()
                self.send_move(move)
                continue
            if line.startswith("TELEPORT"):
                parts = line.split()
                new_r = int(parts[1])
                new_c = int(parts[2])
                # Compute the cell we just stepped on (portal)
                if self.last_move:
                    dr, dc = dirs[self.last_move]
                    stepped_r = self.r + dr
                    stepped_c = self.c + dc
                view = self.read_view()
                self.r = new_r
                self.c = new_c
                self.update_map(view)
                # Infer the letter on the portal we stepped onto (same as new center)
                if self.last_move and view:
                    center_ch = view[2][2]
                    if center_ch.isupper():
                        self.maze_map[(stepped_r, stepped_c)] = center_ch
                self.update_portals()
                move = self.choose_move()
                self.send_move(move)
                continue
            # Normal move: first line of view already in 'line'
            view = [line] + [self.read_line() for _ in range(4)]
            if self.last_move:
                dr, dc = dirs[self.last_move]
                self.r += dr
                self.c += dc
            self.update_map(view)
            self.update_portals()
            move = self.choose_move()
            self.send_move(move)

if __name__ == "__main__":
    bot = MazeBot()
    bot.run()