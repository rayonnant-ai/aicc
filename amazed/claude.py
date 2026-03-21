#!/usr/bin/env python3
"""Maze navigation client for The Amazing Teleportal Maze tournament."""

import socket
from collections import deque

DELTAS = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}
MOVE_ORDER = ["D", "R", "U", "L"]  # Bias toward exit (bottom-right)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("localhost", 7474))
    f = sock.makefile("r")

    sock.sendall(b"claude_bot\n")

    while True:
        line = f.readline()
        if not line:
            break
        line = line.strip()
        if line.startswith("ROUND"):
            play_round(sock, f)
        elif line == "ELIMINATED":
            break


def readline_raw(f):
    """Read a line preserving trailing spaces but removing newline."""
    line = f.readline()
    if not line:
        return None
    if line.endswith("\n"):
        line = line[:-1]
    return line


def read_view(f):
    """Read 5 lines of a 5x5 view."""
    view = []
    for _ in range(5):
        line = readline_raw(f)
        if line is None:
            return None
        view.append(line)
    return view


def update_map(world, pos, view):
    """Merge a 5x5 view centered on pos into the world map."""
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            r, c = pos[0] + dr, pos[1] + dc
            row_idx, col_idx = dr + 2, dc + 2
            if row_idx < len(view) and col_idx < len(view[row_idx]):
                ch = view[row_idx][col_idx]
                if ch != "?":
                    world[(r, c)] = ch


def find_cell(world, target_char):
    """Find position of a specific character in the world map."""
    for pos, ch in world.items():
        if ch == target_char:
            return pos
    return None


def is_passable(ch):
    """Check if a cell character is passable (not wall, not unknown)."""
    return ch is not None and ch != "#" and ch != "?"


def bfs_path(start, goal, world, portal_links):
    """BFS shortest path from start to goal using known portal links.
    Returns list of moves, or None if no path found."""
    if start == goal:
        return []
    queue = deque([(start, [])])
    visited = {start}

    while queue:
        pos, path = queue.popleft()

        for move in MOVE_ORDER:
            dr, dc = DELTAS[move]
            npos = (pos[0] + dr, pos[1] + dc)
            ch = world.get(npos)

            if not is_passable(ch):
                continue

            # Skip unknown portals — can't predict destination
            if ch.isalpha() and ch.isupper() and npos not in portal_links:
                continue

            # Resolve portal teleport
            actual = portal_links.get(npos, npos)
            new_path = path + [move]

            if npos == goal or actual == goal:
                return new_path

            if actual not in visited:
                visited.add(actual)
                queue.append((actual, new_path))

    return None


def bfs_path_allow_portals(start, goal, world, portal_links):
    """BFS that treats unknown portals as passable (for reaching them)."""
    if start == goal:
        return []
    queue = deque([(start, [])])
    visited = {start}

    while queue:
        pos, path = queue.popleft()

        for move in MOVE_ORDER:
            dr, dc = DELTAS[move]
            npos = (pos[0] + dr, pos[1] + dc)
            ch = world.get(npos)

            if not is_passable(ch):
                continue

            new_path = path + [move]

            if npos == goal:
                return new_path

            # Don't traverse THROUGH unknown portals, only TO them
            if ch.isalpha() and ch.isupper() and npos not in portal_links:
                continue

            actual = portal_links.get(npos, npos)
            if actual not in visited:
                visited.add(actual)
                queue.append((actual, new_path))

    return None


def decide_move(pos, world, portal_links):
    """Decide the next move: exit > frontier exploration > portal discovery > fallback."""

    # === Priority 1: Navigate to exit if visible ===
    exit_pos = find_cell(world, "<")
    if exit_pos:
        path = bfs_path(pos, exit_pos, world, portal_links)
        if path:
            return path[0]

    # === Priority 2 & 3: Explore via unified BFS ===
    queue = deque([(pos, [])])
    visited = {pos}
    best_frontier = None       # (score, first_move)
    best_unknown_portal = None  # (distance, first_move, portal_pos)

    while queue:
        p, path = queue.popleft()
        if len(path) > 120:
            break

        if path:
            # Check if p is adjacent to any unknown cell (frontier)
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = p[0] + dr, p[1] + dc
                if (nr, nc) not in world:
                    # Score: fewer steps is better, bias toward bottom-right
                    score = len(path) - 0.2 * (p[0] + p[1])
                    if best_frontier is None or score < best_frontier[0]:
                        best_frontier = (score, path[0])
                    break

        for move in MOVE_ORDER:
            dr, dc = DELTAS[move]
            npos = (p[0] + dr, p[1] + dc)
            ch = world.get(npos)

            if not is_passable(ch):
                continue

            # Track unknown portals as exploration targets
            if ch.isalpha() and ch.isupper() and npos not in portal_links:
                full_path = path + [move]
                dist = len(full_path)
                if best_unknown_portal is None or dist < best_unknown_portal[0]:
                    best_unknown_portal = (dist, full_path[0], npos)
                continue  # Don't BFS through unknown portals

            actual = portal_links.get(npos, npos)
            if actual not in visited:
                visited.add(actual)
                queue.append((actual, path + [move]))

    if best_frontier:
        return best_frontier[1]

    # === Priority 3: Discover unknown portals ===
    if best_unknown_portal:
        return best_unknown_portal[1]

    # === Fallback: any passable move ===
    for move in MOVE_ORDER:
        dr, dc = DELTAS[move]
        npos = (pos[0] + dr, pos[1] + dc)
        ch = world.get(npos)
        if ch and ch != "#":
            return move
    return "D"


def play_round(sock, f):
    """Play one round of the maze."""
    view = read_view(f)
    if view is None:
        return

    pos = (1, 1)  # Start is always at (1, 1)
    world = {}
    portal_links = {}  # (r,c) -> (r,c): known teleport mappings

    update_map(world, pos, view)

    for _ in range(500):
        move = decide_move(pos, world, portal_links)
        sock.sendall((move + "\n").encode())

        resp = readline_raw(f)
        if resp is None:
            return

        if resp == "WALL":
            # Mark wall cell and try again next iteration
            dr, dc = DELTAS[move]
            world[(pos[0] + dr, pos[1] + dc)] = "#"
            continue

        elif resp.startswith("DONE"):
            return

        elif resp.startswith("ELIMINATED"):
            return

        elif resp.startswith("TELEPORT"):
            # Parse: TELEPORT r c
            parts = resp.split()
            new_r, new_c = int(parts[1]), int(parts[2])

            # Record bidirectional portal link
            dr, dc = DELTAS[move]
            portal_from = (pos[0] + dr, pos[1] + dc)
            portal_to = (new_r, new_c)
            portal_links[portal_from] = portal_to
            portal_links[portal_to] = portal_from

            pos = portal_to
            view = read_view(f)
            if view is None:
                return
            update_map(world, pos, view)

        else:
            # Normal move — resp is first line of new 5x5 view
            remaining = []
            for _ in range(4):
                line = readline_raw(f)
                if line is None:
                    return
                remaining.append(line)
            view = [resp] + remaining

            dr, dc = DELTAS[move]
            pos = (pos[0] + dr, pos[1] + dc)
            update_map(world, pos, view)


if __name__ == "__main__":
    main()