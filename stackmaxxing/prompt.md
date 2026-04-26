# Day 11 Challenge: StackMaxxing

**Task:** Write a Python 3.10 client that drops as many polyomino shapes as possible into a fixed-size 2D tank. Tetris-style stacking rules, no line clearing.

---

### 1. Overview

A round gives you a 2D rectangular tank (`n` columns × `m` rows). The server sends shapes one at a time. For each shape you choose a rotation and a column to drop it from; the shape falls vertically and settles when any of its squares is blocked from below. Round continues until you can't fit a shape (no valid placement) or until the sequence is exhausted. The bot that successfully places the most shapes wins the round.

**Gravity is per-piece, not per-square.** Once any one square of a falling piece would collide with something below (the floor or a previously placed cell), the entire piece stops. Other squares in the piece may end up unsupported in mid-air — they stay there. The piece is rigid.

Worked example with `..CCC` falling onto `BBB..`:

```
       ..CCC          <- C settles here, leftmost two squares hover
       BBB..
```

The C-piece's rightmost square rests on B's middle square. The C-piece's two leftmost squares are floating but don't fall further; the piece is rigid.

**No line clearing**, no horizontal sliding, no rotation-after-drop. One shot per piece.

---

### 2. Connection & Registration

* Connect via TCP to `localhost:7474`.
* Send your bot name followed by a newline: `{model_name}_bot\n`.
* **Registration window:** 10 seconds from server startup.

---

### 3. Round Start

At the start of each round the server sends a single line:

```
ROUND {round_num} {n_cols} {n_rows}
```

* `round_num` is 1-indexed.
* `n_cols`, `n_rows` are integers giving the tank size in unit cells.
* Coordinates are `(x, y)` with `x` increasing rightward (`0 .. n_cols-1`) and `y` increasing **upward** (`0` is the floor, `n_rows-1` is the top row).

Tank starts empty.

---

### 4. Per-piece Protocol

For each piece (until the round ends), the server sends **exactly four lines**:

```
PIECE
CURRENT {cells}
NEXT {cells | END}
NEXT {cells | END}
```

* `{cells}` is a space-separated list of `x,y` coordinates of the piece's unit squares in its **base orientation**, normalized so the minimum x and minimum y in the list are both `0`. Cells are unique, 4-connected, and the order within the line is **not significant** — treat the list as a set.
* `CURRENT` is the piece you must place now.
* The two `NEXT` lines show the next two pieces in the sequence — a 3-piece look-ahead. Both will become `CURRENT` on subsequent `PIECE` prompts (assuming the round doesn't end first).
* When fewer than two follow-up pieces remain in the sequence, the trailing `NEXT` slots are filled in order with the literal token `NEXT END` (no cells). Concretely: if exactly one follow-up remains, line 3 is `NEXT {cells}` and line 4 is `NEXT END`. If zero remain, both lines are `NEXT END`.
* `CURRENT END` is never sent; if `CURRENT` would have no piece, the round has already ended via `ROUND_END`.

**Example I-tetromino with two follow-ups:**

```
PIECE
CURRENT 0,0 1,0 2,0 3,0
NEXT 0,0 0,1 1,0 1,1
NEXT 0,0 1,0 1,1 2,1
```

**Example with only one follow-up remaining:**

```
PIECE
CURRENT 0,0 1,0 2,0 3,0
NEXT 0,0 0,1 1,0 1,1
NEXT END
```

You respond with one line:

```
{rotation} {column}\n
```

* `rotation` is an integer in `{0, 1, 2, 3}`. It rotates the piece by `rotation × 90°` counter-clockwise. The exact procedure: apply the map `(x, y) → (-y, x)` to **every** cell of the base orientation **exactly `rotation` times**, then **re-normalize once at the end** by subtracting the resulting minimum `x` and minimum `y` from every cell so the new minimum `x` and minimum `y` are both `0`. Do not normalize between intermediate rotations.
* `column` is the leftmost column the rotated piece occupies on the board. After rotation, let the rotated cells have width `w = max(x) − min(x) + 1`. The valid range is `0 ≤ column ≤ n_cols − w`. Out-of-range columns end the round.

**Server's reply** is one of:

* `OK {bottom_y}\n` — placement accepted. `bottom_y` is the minimum `y` over the piece's settled cells (the row of its lowest cell after the drop). The next `PIECE` follows. **The final piece in the sequence also gets an `OK` if successfully placed; `ROUND_END` follows immediately after.**
* `ROUND_END {pieces_placed} {cells_filled}\n` — your round is over (see Section 6 for causes). `pieces_placed` is the count of pieces successfully placed. `cells_filled` is the total occupied cells in the tank at end of round.

The server **does not echo the tank state**. You are responsible for maintaining your own model of the tank by simulating each accepted move with the same rules the server uses (Section 5). The `bottom_y` in `OK` is provided as a sanity-check signal, not as a substitute for full tank tracking.

Once `ROUND_END` arrives, wait for the next `ROUND` line — except after the final round, when `END` follows instead (see Section 10).

---

### 5. Drop Resolution

Given your `(rotation, column)` choice the server determines where the piece comes to rest. Here is the exact algorithm in concrete terms.

1. **Rotate.** Apply `(x, y) → (-y, x)` to every base-orientation cell exactly `rotation` times. Re-normalize once by subtracting the resulting minimum `x` and minimum `y` from every cell. Call the result `R = {(rx_i, ry_i)}`. By construction `min rx_i = 0` and `min ry_i = 0`.
2. **Horizontal-bounds check.** Let `w = max(rx_i) + 1`. If `column < 0` or `column + w > n_cols`, the placement is invalid — `ROUND_END`.
3. **Find the resting row.** Define `settle_y` as the **smallest non-negative integer** such that for every cell `(rx_i, ry_i)` in `R`, the absolute board cell `(column + rx_i, settle_y + ry_i)` is either an empty cell or out of bounds above the tank, AND lowering `settle_y` by 1 would either (a) put some cell at `y < 0` (below the floor), or (b) cause some cell to coincide with an already-occupied cell.

    In other words: `settle_y` is the lowest position the piece can occupy without colliding or going through the floor. Equivalently: start the piece "high above the tank," let it fall, and freeze it at the first row where one more downward step would either hit the floor or overlap an existing cell.

4. **Top-bound check.** Once `settle_y` is determined, if any settled cell `(column + rx_i, settle_y + ry_i)` has `y ≥ n_rows`, the piece does not fit — the placement is invalid and the round ends with `ROUND_END`. Otherwise the piece is committed to those cells.

5. **Reply.** The server sends `OK {bottom_y}` where `bottom_y = settle_y` (i.e. the minimum `y` of the settled cells, since `min ry_i = 0`).

**Worked numerical example.** Tank is 6 wide, 8 tall. Tank already contains: `BBB` on the floor at `(0,0), (1,0), (2,0)` (a 3-cell horizontal piece). You send rotation `0`, column `2`, with the piece `0,0 1,0 2,0` (a 3-cell horizontal piece, the example "C" of Section 1).

* After rotation 0 and re-normalization: cells stay `{(0,0), (1,0), (2,0)}`, `w=3`.
* Translation: cells become `{(2, settle_y), (3, settle_y), (4, settle_y)}`.
* `settle_y = 0` would put cell `(2, 0)` on top of B's cell `(2, 0)` — collision. So `settle_y = 1`. At `settle_y = 1`, cells `(2,1), (3,1), (4,1)` are all empty; lowering to `settle_y = 0` collides; valid.
* No cell exceeds `y < n_rows = 8`. Reply: `OK 1`.

This matches the `..CCC / BBB..` picture: C settles at `y = 1`, with two cells (`(3,1)` and `(4,1)`) hovering above empty space.

---

### 6. Round End Conditions

A round ends when any of the following happens:

* **Invalid placement.** `column` is out of range (< 0 or > `n_cols − w`); rotation is outside `{0, 1, 2, 3}`; or after running the Section 5 algorithm any settled cell has `y ≥ n_rows`. Note: a non-empty board cannot produce a settle that "passes through" occupied cells — the search defines `settle_y` as the lowest collision-free position.
* **Sequence exhausted.** You successfully placed the final piece in the round's sequence. The server still sends `OK {bottom_y}` for that placement, then `ROUND_END` immediately after.
* **Malformed response.** Anything not exactly matching the response grammar (Section 11), or no response within the time budget.
* **Time-budget exceeded.** Your accumulated wait time exceeds the round budget (Section 11).

In every case the server sends a single `ROUND_END {pieces_placed} {cells_filled}` line and moves on to the next round (or to `END` after the final round). The server does **not** distinguish causes on the wire — `pieces_placed` and `cells_filled` reflect the state at end of round in all cases.

---

### 7. Pieces

Pieces are connected polyominoes of 1 to 5 unit cells (one-sided polyominoes — reflections count as distinct shapes). The server samples them with replacement from a fixed catalogue per round; the same sequence is sent to every bot in the round so that scores are directly comparable.

You don't need to memorize the catalogue. Each `PIECE` prompt gives you the cell list inline.

---

### 8. Scoring

Per round, bots are ranked by:

1. **Pieces placed**, descending.
2. **Cells filled**, descending (tiebreak).
3. **Server-receive time of the final response**, ascending (tiebreak).

Points awarded by rank:

| Rank   | 1st | 2nd | 3rd | 4th | 5th | 6th+ |
|--------|-----|-----|-----|-----|-----|------|
| Points | 10  | 7   | 5   | 3   | 1   | 0    |

Total score is the sum across rounds.

---

### 9. Round Schedule

Tank dimensions grow over the tournament:

| Round | Cols (`n`) | Rows (`m`) |
|-------|------------|------------|
| 1     | 6          | 8          |
| 2     | 7          | 10         |
| 3     | 8          | 12         |
| 4     | 10         | 12         |
| 5     | 12         | 14         |
| 6     | 12         | 16         |
| 7     | 14         | 16         |
| 8     | 14         | 18         |
| 9     | 16         | 20         |
| 10    | 18         | 20         |

The piece sequence per round is long enough that running out of pieces is improbable on any tank size you'll see — the round generally ends because something doesn't fit.

---

### 10. Tournament End

After the final round's `ROUND_END`, the server sends a single line `END\n` and closes the connection.

The byte order is always: final-round responses → the round's `ROUND_END` → `END` → server closes the socket.

You may exit immediately upon reading `END`. There is nothing else to consume. EOF without `END` (e.g. server crash, network drop) is a protocol error from the server's side, not yours; safe behaviour is to also exit cleanly on EOF.

---

### 11. Constraints

* **Language:** Standalone Python 3.10 script using only the **Standard Library**.

* **Time budget.** The server enforces a per-round budget of **10 seconds of cumulative wait time**. Concretely: for every `PIECE` prompt, the server starts a stopwatch when it finishes sending the prompt and stops it when it finishes reading your response line. The sum of those per-piece deltas across the round must stay ≤ 10s. Inter-prompt server work, registration, and time spent reading the round header do not count. If you exceed the budget while the server is waiting on you, the round ends with `ROUND_END` and pieces placed so far are kept.

* **Port:** `localhost:7474`.

* **Strict parsing — response grammar.** Your response to a `PIECE` prompt must match this exact grammar:

    ```
    response := rotation SP column LF
    rotation := "0" | "1" | "2" | "3"
    column   := digit+                    (no leading zeros except "0" itself; no sign)
    digit    := "0".."9"
    SP       := single ASCII space (0x20)
    LF       := single ASCII line feed (0x0a)
    ```

    Concretely: `0 3\n` is valid. `0  3\n` (double space) is INVALID. `0 3 \n` (trailing space) is INVALID. `0\t3\n` (tab) is INVALID. `0 3\r\n` (CRLF) is INVALID — LF only. `+0 3\n` and `00 3\n` are INVALID. JSON, quoted strings, multi-line, empty response — all INVALID. INVALID responses end the round.

* **Strict parsing — server lines.** All server-sent lines are LF-terminated, ASCII only, single-space-separated tokens. Lines are line-buffered but TCP may fragment them across `recv()` boundaries — your client must accumulate bytes and split on `\n`.

* **Coordinate convention:** `y = 0` is the floor (bottom of the tank). `y = n_rows − 1` is the top row. The piece falls in the direction of decreasing `y`. The `settle_y` of Section 5 is therefore the lowest non-negative `y` where the piece rests without overlap.

* **Rotation convention:** counter-clockwise. Rotation `k ∈ {0, 1, 2, 3}` maps each cell `(x, y)` of the base orientation by applying `(x, y) → (-y, x)` **exactly `k` times in a row** — no normalization between intermediate steps — then re-normalizing the final cell set once by subtracting the minimum `x` and minimum `y` so both new minima are `0`.
