#!/usr/bin/env python3
"""Growing Word Ladder tournament client."""

import socket
import sys
import os
from collections import deque
from typing import Optional

BOT_NAME = "mimo_bot"
DICT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictionary.txt")
HOST = "localhost"
PORT = 7474

ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def load_dictionary(path: str) -> set[str]:
    with open(path, "r") as f:
        return set(line.strip() for line in f if line.strip())


def neighbors(word: str, dictionary: set[str]) -> list[str]:
    """Generate all valid neighbors (change 1, add 1, remove 1 letter)."""
    results: list[str] = []
    wl = len(word)

    # Change 1 letter
    for i in range(wl):
        for c in ALPHA:
            candidate = word[:i] + c + word[i + 1:]
            if candidate != word and candidate in dictionary:
                results.append(candidate)

    # Add 1 letter (at each position)
    for i in range(wl + 1):
        for c in ALPHA:
            candidate = word[:i] + c + word[i:]
            if candidate in dictionary:
                results.append(candidate)

    # Remove 1 letter
    for i in range(wl):
        candidate = word[:i] + word[i + 1:]
        if candidate in dictionary:
            results.append(candidate)

    return results


def bidirectional_bfs(start: str, goal: str, dictionary: set[str]) -> Optional[list[str]]:
    """Bidirectional BFS from start and goal simultaneously."""
    if start == goal:
        return [start]

    front: dict[str, Optional[str]] = {start: None}
    back: dict[str, Optional[str]] = {goal: None}
    front_q: deque[str] = deque([start])
    back_q: deque[str] = deque([goal])

    while front_q or back_q:
        # Expand the smaller frontier
        if front_q and (not back_q or len(front_q) <= len(back_q)):
            meeting = _expand(front_q, front, back, dictionary)
            if meeting is not None:
                return _reconstruct(meeting, front, back)
        if back_q:
            meeting = _expand(back_q, back, front, dictionary)
            if meeting is not None:
                return _reconstruct(meeting, front, back)

    return None


def _expand(
    queue: deque[str],
    visited: dict[str, Optional[str]],
    other: dict[str, Optional[str]],
    dictionary: set[str],
) -> Optional[str]:
    """Expand one level. Returns meeting point if found."""
    if not queue:
        return None
    current = queue.popleft()
    for nb in neighbors(current, dictionary):
        if nb in other:
            visited[nb] = current
            return nb
        if nb not in visited:
            visited[nb] = current
            queue.append(nb)
    return None


def _reconstruct(
    meeting: str,
    front: dict[str, Optional[str]],
    back: dict[str, Optional[str]],
) -> list[str]:
    """Reconstruct path from start -> meeting -> goal."""
    path: list[str] = []
    node: Optional[str] = meeting
    while node is not None:
        path.append(node)
        node = front.get(node)
    path.reverse()

    node = back.get(meeting)
    while node is not None:
        path.append(node)
        node = back.get(node)
    return path


def main():
    dictionary = load_dictionary(DICT_PATH)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    # Send bot name
    sock.sendall((BOT_NAME + "\n").encode())

    buf = b""
    while True:
        try:
            data = sock.recv(65536)
            if not data:
                break
            buf += data

            while b"\n" in buf:
                line_bytes, buf = buf.split(b"\n", 1)
                line = line_bytes.decode().strip()
                if not line:
                    continue

                if line == "1":
                    sock.close()
                    return

                if line == "0":
                    # Round accepted, wait for next challenge
                    continue

                # Challenge: START,GOAL
                if "," in line:
                    parts = line.split(",", 1)
                    start = parts[0].strip().upper()
                    goal = parts[1].strip().upper()

                    path = bidirectional_bfs(start, goal, dictionary)

                    if path:
                        sock.sendall(("\n".join(path) + "\n").encode())
                    else:
                        # No path found — send start,goal as fallback (will disqualify)
                        sock.sendall((start + "\n" + goal + "\n").encode())

        except (socket.timeout, ConnectionError, OSError):
            break

    sock.close()


if __name__ == "__main__":
    main()
