# Day 7 Challenge: Blobby Tic-Tac-Toe

**Task:** Write a Python 3.10 client that plays tic-tac-toe on irregular grid shapes against other bots in a round-robin tournament.

---

### 1. Overview

Standard tic-tac-toe rules — three in a row wins — but the board is not a 3×3 square. Each round, the board is an irregular blob shape: a rectangular grid where some cells are valid and some are holes. The shape changes every round.

You play every other bot in a penalty-shootout-style matchup. Each matchup consists of up to 5 rounds. Each round, you play two games simultaneously on the same board — one as X (first mover) and one as O (second mover). This eliminates first-mover advantage.

---

### 2. Connection & Registration

* Connect via TCP to `localhost:7474`.
* Send your bot name followed by a newline: `{model_name}_bot\n`

---

### 3. Matchup Flow

Each matchup between two bots proceeds as follows:

**Penalty shootout format:**
* Up to 5 rounds per matchup. Each round = 2 games on the same board (you play X in one, O in the other).
* 1 match point per game won. 0 for draw or loss.
* After 5 rounds, whoever has more match points wins the matchup (3 tournament points to the winner, 0 to the loser).
* If tied after 5 rounds, sudden-death rounds continue until one player leads after a round.
* If still tied after 10 rounds, both players get 1 tournament point.
* The server may terminate a matchup early if the outcome is already decided. Your bot should be prepared for this — the next message will be a `MATCHUP` result.

---

### 4. Round Flow

At the start of each round, the server sends:

```
ROUND {n}
BOARD
{grid rows, one per line}
END
GAME1 {X or O}
GAME2 {X or O}
```

`GAME1 X` means you play as X (first mover) in Game 1. `GAME2 O` means you play as O (second mover) in Game 2. X always moves first.

The grid uses these characters:
* `.` — hole (not a valid cell)
* `_` — empty valid cell

At the start, all valid cells are `_`.

---

### 5. Turn Flow

On your turn, the server sends:

```
YOURTURN {1 or 2}
```

This tells you which game to move in. You respond with:

```
{row} {col}\n
```

Rows and columns are 0-indexed from the top-left of the grid.

Both bots submit their moves simultaneously (each in a different game). Neither sees the other's move before committing.

After both moves are collected, the server sends each bot the opponent's move in the other game:

```
OPPONENT {1 or 2} {row} {col}
```

You must maintain your own board state. The server does not resend the full board after each turn.

---

### 6. End of Game

When a game ends (win, loss, or draw), the server sends:

```
RESULT GAME{1 or 2} {WIN|LOSS|DRAW}
```

Once a game ends, there are no further `YOURTURN` or `OPPONENT` messages for that game.

When both games in a round are finished:

```
ROUND_SCORE {your_match_points} {opponent_match_points}
```

When the matchup ends:

```
MATCHUP {WIN|LOSS|DRAW} {your_total} {opponent_total}
```

---

### 7. Winning Condition

Three in a row horizontally, vertically, or diagonally on valid cells. Only cells that are adjacent in a straight line on the grid count — holes do not connect cells on either side. For example, in the row `_._`, the left and right cells are NOT connected through the hole.

A draw occurs when all valid cells are filled and no player has three in a row.

---

### 8. Board Properties

* Grid dimensions: R rows, C columns, where 4 <= R <= 10 and 4 <= C <= 10.
* Valid cells form an irregular 4-connected blob (cells are connected through shared horizontal or vertical edges, not diagonals).
* Every board is guaranteed to have at least one possible winning line.
* The board shape changes each round within a matchup.

---

### 9. Constraints

* **Language:** Standalone Python 3.10 script using only the **Standard Library**.
* **Timeout:** 2 seconds per move.
* **Invalid move** (occupied cell, hole, out of bounds, malformed input, timeout) = you forfeit that game. The opponent receives 1 match point.
