#!/usr/bin/env python3
"""Teleportal Maze solver — BFS exploration with two-phase pathfinding."""

import socket
import sys
from collections import deque

HOST, PORT = "localhost", 7474
BOT = "mimo_bot"


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((HOST, PORT))
    f = sock.makefile("r")

    def send(cmd):
        sock.sendall(f"{cmd}\n".encode())

    def rd():
        ln = f.readline()
        if not ln:
            raise ConnectionError("server closed")
        return ln.strip()

    # ── state ────────────────────────────────────────────────
    mp = {}                       # (r,c) → char
    pos = None                    # current (r,c)
    exit_pos = None               # discovered exit (r,c)

    # ── helpers ──────────────────────────────────────────────
    def read_view():
        """Read 5 rows, merge into map, detect exit."""
        nonlocal exit_pos
        for dr in range(-2, 3):
            row = rd()
            for dc in range(-2, 3):
                p = (pos[0] + dr, pos[1] + dc)
                ch = row[dc + 2]
                if ch != "?":
                    mp[p] = ch
                if ch == "<":
                    exit_pos = p

    def find_move():
        """
        Two-phase BFS.
        Phase 1 – explore only confirmed (non-?) cells.
          • If exit is reachable → return path.
          • Otherwise collect frontier cells (passable neighbours of ?).
        Phase 2 – restart BFS from start, visited = phase-1 set.
          Traverse confirmed *and* ? cells.
          Return path to first frontier or exit encountered.
        """
        visited = {pos}
        q = deque([(pos, [])])
        frontier = []             # [(coord, path_so_far)]

        # ── phase 1: confirmed only ──
        while q:
            cur, path = q.popleft()
            if exit_pos and cur == exit_pos and path:
                return path[0]
            for d, (dr, dc) in zip("UDLR", [(-1, 0), (1, 0), (0, -1), (0, 1)]):
                nb = (cur[0] + dr, cur[1] + dc)
                if nb in visited:
                    continue
                visited.add(nb)
                ch = mp.get(nb, "?")
                if ch == "#":
                    continue
                np = path + [d]
                if ch == "?":
                    frontier.append((nb, np))
                else:
                    q.append((nb, np))

        # ── phase 2: allow stepping into ? cells ──
        q = deque([(pos, [])])
        while q:
            cur, path = q.popleft()
            if exit_pos and cur == exit_pos and path:
                return path[0]
            for d, (dr, dc) in zip("UDLR", [(-1, 0), (1, 0), (0, -1), (0, 1)]):
                nb = (cur[0] + dr, cur[1] + dc)
                if nb in visited:
                    continue
                visited.add(nb)
                ch = mp.get(nb, "?")
                if ch == "#":
                    continue
                np = path + [d]
                if ch == "?":
                    return np[0]          # nearest frontier → step into unknown
                q.append((nb, np))

        # should never fire in a valid connected maze
        return "U"

    # ── registration ─────────────────────────────────────────
    send(BOT)

    # ── game loop ────────────────────────────────────────────
    try:
        while True:
            line = rd()
            if line.startswith("ROUND"):
                pos = (0, 0)
                mp = {pos: ">"}
                exit_pos = None
                read_view()

                while True:
                    if exit_pos and pos == exit_pos:
                        send("D")                 # flush; server will reply DONE
                        r = rd()
                        break

                    mv = find_move()
                    send(mv)
                    r = rd()

                    if r.startswith("DONE") or r.startswith("ELIMINATED"):
                        break
                    if r == "WALL":
                        continue                  # wasted no step; retry
                    if r.startswith("TELEPORT"):
                        _, tr, tc = r.split()
                        pos = (int(tr), int(tc))
                        read_view()
                    else:
                        # normal move — first line of the new view
                        for dc in range(-2, 3):
                            p = (pos[0] - 2, pos[1] + dc)
                            ch = r[dc + 2]
                            if ch != "?":
                                mp[p] = ch
                            if ch == "<":
                                exit_pos = p
                        pos = (pos[0] + {"U": -1, "D": 1}.get(mv, 0),
                               pos[1] + {"L": -1, "R": 1}.get(mv, 0))
                        for dr in range(-1, 3):
                            row = rd()
                            for dc in range(-2, 3):
                                p = (pos[0] + dr, pos[1] + dc)
                                ch = row[dc + 2]
                                if ch != "?":
                                    mp[p] = ch
                                if ch == "<":
                                    exit_pos = p
            elif line.startswith("DONE") or line.startswith("ELIMINATED"):
                continue
    except (ConnectionError, EOFError):
        pass
    finally:
        sock.close()


if __name__ == "__main__":
    main()
