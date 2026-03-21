import socket
from collections import deque

HOST = "localhost"
PORT = 7474

MOVES = {
    "U": (-1, 0),
    "D": (1, 0),
    "L": (0, -1),
    "R": (0, 1),
}
DIRS = ["U", "D", "L", "R"]


class MazeBot:
    def __init__(self):
        self.map = {}  # (r, c) -> char
        self.pos = (0, 0)
        self.exit = None
        self.portals = {}  # letter -> list of positions
        self.plan = []

    def update_view(self, view):
        pr, pc = self.pos
        for i in range(5):
            for j in range(5):
                r = pr + (i - 2)
                c = pc + (j - 2)
                ch = view[i][j]

                if ch == "?":
                    continue

                self.map[(r, c)] = ch

                if ch == "<":
                    self.exit = (r, c)

                if ch.isalpha():
                    self.portals.setdefault(ch, []).append((r, c))

    def neighbors(self, pos):
        r, c = pos

        # Normal moves
        for d, (dr, dc) in MOVES.items():
            np = (r + dr, c + dc)
            tile = self.map.get(np)

            if tile is None or tile == "#":
                continue

            yield np

        # Portal moves
        tile = self.map.get(pos)
        if tile and tile.isalpha() and tile in self.portals:
            for p in self.portals[tile]:
                if p != pos:
                    yield p

    def bfs(self, targets):
        queue = deque([self.pos])
        prev = {self.pos: None}

        while queue:
            cur = queue.popleft()

            if cur in targets:
                return self.reconstruct(prev, cur)

            for nxt in self.neighbors(cur):
                if nxt not in prev:
                    prev[nxt] = cur
                    queue.append(nxt)

        return None

    def reconstruct(self, prev, end):
        path = []
        cur = end

        while prev[cur] is not None:
            p = prev[cur]
            dr = cur[0] - p[0]
            dc = cur[1] - p[1]

            for d, (r, c) in MOVES.items():
                if (r, c) == (dr, dc):
                    path.append(d)
                    break

            cur = p

        path.reverse()
        return path

    def frontier_targets(self):
        targets = set()

        for (r, c), tile in self.map.items():
            if tile == "#":
                continue

            for dr, dc in MOVES.values():
                np = (r + dr, c + dc)
                if np not in self.map:
                    targets.add((r, c))

        return targets

    def choose_plan(self):
        # If exit known → go to exit
        if self.exit:
            path = self.bfs({self.exit})
            if path:
                return path

        # Otherwise explore frontier
        targets = self.frontier_targets()
        path = self.bfs(targets)
        if path:
            return path

        # fallback (shouldn't happen)
        return ["U"]

    def next_move(self):
        if not self.plan:
            self.plan = self.choose_plan()

        return self.plan.pop(0)


def read_line(sock):
    data = b""
    while not data.endswith(b"\n"):
        data += sock.recv(1)
    return data.decode()


def read_view(sock):
    return [list(read_line(sock).rstrip("\n")) for _ in range(5)]


def main():
    bot = MazeBot()

    with socket.create_connection((HOST, PORT)) as sock:
        sock.sendall(b"gpt_bot\n")

        while True:
            line = read_line(sock)

            if line.startswith("ROUND"):
                bot = MazeBot()
                view = read_view(sock)
                bot.update_view(view)

            elif line.startswith("DONE") or line.startswith("ELIMINATED"):
                continue

            elif line.startswith("WALL"):
                # just pick another move next iteration
                continue

            elif line.startswith("TELEPORT"):
                _, r, c = line.strip().split()
                bot.pos = (int(r), int(c))
                view = read_view(sock)
                bot.update_view(view)

            else:
                # must be a view
                view = [list(line.rstrip("\n"))]
                for _ in range(4):
                    view.append(list(read_line(sock).rstrip("\n")))

                bot.update_view(view)

            move = bot.next_move()

            # update local position (optimistically)
            dr, dc = MOVES[move]
            bot.pos = (bot.pos[0] + dr, bot.pos[1] + dc)

            sock.sendall((move + "\n").encode())


if __name__ == "__main__":
    main()