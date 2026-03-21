#!/usr/bin/env python3
"""
Robot Word Racer — Competitive tournament client.

Loads dictionary.txt, connects to the game server, solves the 15×15
Boggle-style grid via trie-pruned DFS, and fires off the longest
(highest-scoring) words first to claim them before rival bots.

Usage:  python3 robot_word_racer.py
"""

import socket
import sys
import threading

# ---------------------------------------------------------------------------
# Trie — list-of-26-children for O(1) child lookup by letter
# ---------------------------------------------------------------------------

def build_trie(path: str) -> list:
    """Return a trie root node (list of 26 slots + [flag])."""
    root = [None] * 26 + [False]
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            w = raw.strip().upper()
            if len(w) < 3:
                continue
            node = root
            for ch in w:
                idx = ord(ch) - 65
                if node[idx] is None:
                    node[idx] = [None] * 26 + [False]
                node = node[idx]
            node[26] = True
    return root


# ---------------------------------------------------------------------------
# Grid solver — DFS with trie back-tracking
# ---------------------------------------------------------------------------

# 8-connected neighbour offsets
_OFFSETS = (
    (-1, -1), (-1, 0), (-1, 1),
    ( 0, -1),          ( 0, 1),
    ( 1, -1), ( 1, 0), ( 1, 1),
)


def solve(grid: list[str], trie: list, side: int = 15) -> list[str]:
    """Return every dictionary word reachable on *grid*."""
    found: set[str] = set()
    buf:  list[str] = []
    vis:  list[bool] = [False] * (side * side)

    def dfs(r: int, c: int, node: list) -> None:
        idx = ord(grid[r * side + c]) - 65
        child = node[idx]
        if child is None:
            return

        vis[r * side + c] = True
        buf.append(grid[r * side + c])

        if child[26] and len(buf) >= 3:
            found.add("".join(buf))

        for dr, dc in _OFFSETS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < side and 0 <= nc < side and not vis[nr * side + nc]:
                dfs(nr, nc, child)

        buf.pop()
        vis[r * side + c] = False

    for r in range(side):
        for c in range(side):
            dfs(r, c, trie)

    return list(found)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # ── 1. Dictionary ──────────────────────────────────────────────────
    print("[*] Loading dictionary …")
    trie = build_trie("dictionary.txt")
    print("[*] Trie ready.")

    # ── 2. TCP connection ──────────────────────────────────────────────
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(("localhost", 7474))
    except ConnectionRefusedError:
        sys.exit("Cannot reach localhost:7474 — is the server running?")

    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    # ── 3. Identify ────────────────────────────────────────────────────
    name = "MiMoRacer"
    sock.sendall(f"{name}\n".encode())

    # ── 4. Receive 15×15 grid (225 chars + \n) ─────────────────────────
    buf = b""
    while len(buf) < 226:                       # 225 + newline
        chunk = sock.recv(226 - len(buf))
        if not chunk:
            sys.exit("Server closed before sending grid.")
        buf += chunk

    raw = buf[:225].decode("ascii")
    grid = list(raw)
    print(f"[*] Grid received  ({len(grid)} cells)")

    # ── 5. Background receiver — watch for game-over signal ────────────
    game_over = False

    def _receiver() -> None:
        nonlocal game_over
        acc = b""
        try:
            while True:
                data = sock.recv(4096)
                if not data:                    # connection dropped
                    game_over = True
                    return
                acc += data
                while b"\n" in acc:
                    line, acc = acc.split(b"\n", 1)
                    if line == b"1":
                        game_over = True
                        return                  # game ended / disqualified
                    # b"0" — word accepted, nothing to do
        except OSError:
            game_over = True

    threading.Thread(target=_receiver, daemon=True).start()

    # ── 6. Find every valid word ───────────────────────────────────────
    print("[*] Solving grid …")
    words = solve(grid, trie)
    # Longer words → more points  (score = len − 6), submit them first
    words.sort(key=len, reverse=True)
    print(f"[*] Found {len(words)} words — submitting longest first …")

    # ── 7. Fire words at the server ────────────────────────────────────
    sent = 0
    for w in words:
        if game_over:
            break
        try:
            sock.sendall((w + "\n").encode())
            sent += 1
        except OSError:
            break

    # ── 8. Clean shutdown ──────────────────────────────────────────────
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()

    print(f"[*] Done — submitted {sent} words.")


if __name__ == "__main__":
    main()
