# Day 10 Challenge: Knights of Hanoi

**Task:** Write a Python 3.10 client that solves a Towers-of-Hanoi variant on a chessboard where the only legal moves are knight's jumps.

---

### 1. Overview

There are `n` disks stacked on **A1** (bottom-left corner of an 8×8 chessboard), largest on the bottom. You must move all `n` disks to **H8** (top-right corner), obeying:

* **Towers-of-Hanoi placement.** A disk can only be placed on an empty square or on top of a strictly larger disk. Disks are labelled `1..n`, where `1` is the smallest.
* **Knight movement.** Each move picks the top disk of one square and jumps it to another square by a standard chess knight's move: `(±1, ±2)` or `(±2, ±1)` in `(file, rank)`. The destination must be on the board and satisfy the Hanoi placement rule.

Every square on the board can hold a stack of disks. You have 62 squares between A1 and H8 available as intermediate storage.

The round ends when you submit a complete, valid sequence of moves that transports all `n` disks from A1 to H8. Fewest knight-moves wins the round.

---

### 2. Chess Notation

Squares are named by a **file** letter (`A`–`H`, column from left) followed by a **rank** digit (`1`–`8`, row from bottom). Examples:

* `A1` — bottom-left (start) — column 0, row 0
* `H8` — top-right (goal) — column 7, row 7
* `A8` — top-left — column 0, row 7
* `H1` — bottom-right — column 7, row 0
* `D5` — column 3, row 4

Case is flexible; the server accepts both `A1` and `a1`.

---

### 3. Connection & Registration

* Connect via TCP to `localhost:7474`.
* Send your bot name followed by a newline: `{model_name}_bot\n` (e.g. `claude_bot\n`).
* **Registration window:** 10 seconds from server startup. Connect promptly; bots that register after the window close may not receive rounds.

---

### 4. Round Start

At the start of each round the server sends a single line:

```
ROUND {round_num} {n}
```

Where `round_num` is the 1-indexed round number and `n` is the disk count for this round. That is the entire input. The board and start/goal squares are fixed: 8×8, A1 → H8.

Initial state: `n` disks stacked on A1 largest-at-bottom, every other square empty.

Compute a move sequence, then reply with a single-line response (format described below) followed by a newline.

**Server replies once your solution is received:**

* `VALID {num_moves}\n` — solution accepted. `num_moves` is the length of your sequence. Lower is better.
* `INVALID {reason}\n` — solution failed validation. 0 points for this round.
* `TIMEOUT\n` — you took longer than 10 seconds. 0 points.

**Your bot must read the server's reply line before the next `ROUND` line arrives.** The sequence per round is always: `ROUND …` → your response → server reply → next `ROUND …`. Treating the `VALID N` / `INVALID …` / `TIMEOUT` line as the next round header is the most common way to desync and lose the rest of the tournament.

**After the final round** (round 10), the server sends the `VALID`/`INVALID`/`TIMEOUT` reply for that round *first*, then a single line `END\n`, then closes the connection. Bots should exit cleanly on EOF.

---

### 5. Response Format

Your bot responds with a single line: a comma-separated list of moves, each written as the source square immediately followed by the destination square (4 characters per move).

```
A1C2,A1B3,C2A1,B3D4,...
```

Each move describes one knight-jump: pick up the disk on top of the first square and place it on top of the second. Terminate the line with a single newline.

**Strict parsing.** The server expects exactly this shape: `{square}{square},{square}{square},...\n`. Any of the following scores `INVALID`:

* Whitespace anywhere in the response (including spaces after commas, indentation, or tabs).
* A trailing comma (`A1C2,A1B3,`).
* Alternate separators (dashes, arrows, semicolons).
* A JSON wrapper (`{"moves": [...]}`, `[["A1","C2"],...]`).
* Quotes, brackets, or any characters other than `A–H` / `a–h`, `1–8`, and `,`.
* Multiple lines — the response must be a single line.
* An empty response.
* Square names outside the board (e.g. `I5`, `A9`, `Z0`).

Case is flexible for square names (`A1` == `a1`), but nothing else about the format is.

The server replays the sequence: for each move it verifies (a) the source square is non-empty, (b) the destination is a knight's move away, (c) the destination is empty or has a strictly larger top disk. After the last move, it checks the final board: all `n` disks stacked on H8, largest at bottom. If any check fails, your round scores 0.

---

### 6. Game Rules

1. **Goal:** every disk on H8, correctly stacked (disk `n` at the bottom, disk `1` at the top).
2. **Single-disk moves only.** Each move transports exactly the top disk of its source square.
3. **Hanoi placement enforced on every move**, including intermediate placements.
4. **Any intermediate square is fair game.** There is no per-square capacity limit.
5. **No rewinding.** Once submitted, the full sequence is evaluated in order — you cannot partially submit or revise.
6. **Lowest move count wins** the round. Ties are broken by submission time, measured as when the server finishes reading your response line (`\n`-terminated). Earlier server-receive wins the tie.
7. **Timeout:** 10 seconds per round to submit.
8. **Rounds:** 10 total, with `n` growing each round.

---

### 7. Scoring

Per round, valid solutions are ranked by move count (shortest wins). Points awarded by rank:

| Rank  | 1st | 2nd | 3rd | 4th | 5th | 6th+ |
|-------|-----|-----|-----|-----|-----|------|
| Points| 10  | 7   | 5   | 3   | 1   | 0    |

Invalid solutions and timeouts score 0 regardless of rank.

---

### 8. Round Schedule

Disk counts grow across the tournament:

| Round | Disks (`n`) |
|-------|-------------|
| 1     | 3           |
| 2     | 4           |
| 3     | 5           |
| 4     | 6           |
| 5     | 7           |
| 6     | 8           |
| 7     | 9           |
| 8     | 10          |
| 9     | 11          |
| 10    | 12          |

For scale, the classical three-peg Towers of Hanoi minimum is `2^n - 1` moves (e.g. 4095 for n=12). With the knight-jump restriction but 62 helper squares, the minimum is larger but its shape depends on the algorithm you construct. You won't necessarily find the optimum for large `n`; submit the best you can within the budget.

---

### 9. Constraints

* **Language:** Standalone Python 3.10 script using only the **Standard Library**.
* **Timeout:** 10 seconds per round from the moment the server sends `ROUND {round_num} {n}`.
* **Port:** `localhost:7474`.
* **Case insensitivity:** square names in your response may be upper or lower case (`A1` == `a1`).
