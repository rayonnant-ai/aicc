# Day 8 Challenge: Laden Knight's Tour

**Task:** Write a Python 3.10 client that finds the fastest laden knight's tour on a weighted board sent over TCP.

---

### 1. Overview

A knight must visit every square of a rectangular board exactly once, using standard chess knight moves. Unlike the classic Knight's Tour, every square has a **weight**. When the knight visits a square, it picks up that square's weight and carries it for the rest of the tour — its load grows monotonically.

The knight's speed is inversely proportional to its current load. Each move costs `load` units of time, where `load` is the sum of weights of every square visited so far. Your goal is to find a tour that minimizes the **total elapsed time**.

Each round is a new board, larger than the last. 10 rounds total.

---

### 2. Connection & Registration

* Connect via TCP to `localhost:7474`.
* Upon connection, send your bot name followed by a newline:
  * **Format:** `{model_name}_bot\n` (e.g. `claude_bot\n`)

---

### 3. Round Start

At the start of each round the server sends:

```
ROUND {n}\n
SIZE {bytes}\n
{JSON payload}
```

Your bot must parse the JSON, compute a tour, and reply with a JSON response (described below) followed by a newline.

**Server responds:**

* `VALID {total_time}\n` — tour is valid. Lower is better.
* `INVALID {reason}\n` — tour failed validation. 0 points for this round.
* `TIMEOUT\n` — you took longer than 10 seconds. 0 points.

---

### 4. Game Rules

1. **The Goal:** Submit a valid open knight's tour that visits every square exactly once, minimizing total elapsed time.
2. **Knight Moves:** Each consecutive pair of squares in your tour must differ by `(±1, ±2)` or `(±2, ±1)` in `(row, col)`. The destination must be on the board and not previously visited.
3. **Open Tour:** You may start at any square and end at any square. You do **not** need to return to the start.
4. **Time is charged upon departure.** Each move off a square costs `load` time units, where `load` is the sum of weights of every square visited up to and including the square you're departing from. You do not pay to arrive at the final square — the tour ends there.
5. **Total Time Formula.** If the weights of the squares you visit, in tour order, are `w_1, w_2, ..., w_N`, then:

   ```
   total_time = w_1 + (w_1 + w_2) + (w_1 + w_2 + w_3) + ... + (w_1 + ... + w_{N-1})
   ```

   Equivalently, the weight of the `i`-th visited square is multiplied by `(N - i)`: the first square's weight is multiplied by `N-1`, and the last square's weight is multiplied by 0 (so it never contributes).

6. **Timeout:** 10 seconds per round.
7. **Rounds:** 10 rounds total, each with a larger board than the last. Every board is guaranteed to admit at least one valid tour.

#### Worked Example

Suppose you visit three squares in order, with weights `[3, 5, 10]`:

* Enter square 1 (w=3), load = 3. Leave: pay 3.
* Enter square 2 (w=5), load = 8. Leave: pay 8.
* Enter square 3 (w=10), load = 18. Tour ends — no payment.
* **Total time = 3 + 8 = 11.**

Same three squares visited in the reverse order `[10, 5, 3]`:

* Leave square 1 (w=10), load = 10. Pay 10.
* Leave square 2 (w=5), load = 15. Pay 15.
* Enter square 3 (w=3). No payment.
* **Total time = 10 + 15 = 25.**

The weight of your final square never contributes to the total.

---

### 5. Scoring

Per round, bots are ranked by total time (lowest wins). Ties are broken by submission order — the first bot to submit a matching time takes the higher rank.

Points per round by rank (out of 6 bots):

| Rank | 1st | 2nd | 3rd | 4th | 5th | 6th |
|---|---|---|---|---|---|---|
| Points | 10 | 7 | 5 | 3 | 1 | 0 |

Invalid or timed-out responses score 0 points regardless of rank.

---

### 6. Input Data Format (JSON)

```json
{
  "rows": 5,
  "cols": 6,
  "weights": [
    [ 2,  1,  3,  1, 25,  2],
    [ 1,  3,  1,  2,  1, 18],
    [ 3,  2, 12,  1,  3,  1],
    [ 1,  1,  2,  3,  1,  2],
    [15,  2,  1,  1,  2, 30]
  ]
}
```

* `rows` / `cols`: board dimensions.
* `weights[r][c]`: positive integer weight of the square at row `r`, column `c` (0-indexed, origin top-left).

---

### 7. Expected Output Format (JSON)

Respond with a single JSON object listing the sequence of squares in your tour, followed by a newline.

```json
{"tour": [[0,0], [2,1], [4,0], [3,2], [4,4], [2,5], ...]}
```

* Each entry is a `[row, col]` pair.
* The tour must contain exactly `rows * cols` entries.
* Every square must appear exactly once.
* Every consecutive pair must be a legal knight move apart.

---

### 8. Board Properties

* Dimensions `m × n` with `3 <= m <= n`, chosen so that a tour exists. The following unsolvable shapes never appear:
  * `m = 1` or `m = 2`
  * `m = 3` with `n ∈ {3, 5, 6}`
  * `m = 4` with `n = 4`
* Boards grow across rounds. Round 1 is small (≤20 squares). Round 10 is up to 8×8 (64 squares).
* Weights are positive integers drawn from a heavy-tailed distribution: most squares are light (1–3), a minority are heavy (10–50). The distribution is fixed across rounds; only the board grows.

---

### 9. Constraints

* **Language:** Standalone Python 3.10 script using only the **Standard Library**.
* **Timeout:** 10 seconds per round.
* **Port:** `localhost:7474`.
