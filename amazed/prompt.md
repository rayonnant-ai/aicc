# Tournament Specification: The Amazing Teleportal Maze 

**Task:** Write a Python 3.10 client to navigate a 2D ASCII maze with teleportals under foggy conditions. You have no map — you must explore, remember what you've seen, and find the exit in as few steps as possible.

---

### 1. Overview

Each round is a **turn-by-turn dialogue**. The server never sends the full maze. Instead, each turn you send one move and receive a 5×5 view of your surroundings.

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
```

Immediately followed by your initial 5×5 view. You are always at the centre.

---

### 4. Turn Sequence

**You send:**
```
{move}\n
```
Where `{move}` is exactly one of: `U`, `D`, `L`, `R`

**Server responds with one of:**

* A new **5×5 view** — move was valid, you are now at the new cell.
* `WALL\n` — target cell is `#`. You do not move. Send a different move.
* `TELEPORT {r} {c}\n` followed by a new **5×5 view** — you stepped onto a portal and were teleported to `(r, c)`. The view is centred on your new position.

---

### 5. The 5×5 View

Always 5 rows of exactly 5 characters, each terminated by `\n`. Centred on your current position. Uses the standard symbols: `#`, ` `, `>`, `<`, `A-Z`.

* Cells outside the maze boundary appear as `#`.
* **Foggy cells** you have never been near appear as `?`.
* Your current position is always the centre cell `[2][2]`.

---

### 6. Round End

When you step onto `<`, the server sends:

```
DONE {steps}\n
```

`{steps}` is the total number of valid moves made. `WALL` responses do not count.

---

### 7. Scoring & Elimination

* Fewest steps to exit wins the round (+1 point).
* Tie on steps → earliest finish time wins.
* Exceeding **500 moves** without reaching the exit → `ELIMINATED\n`.
* Sending anything other than `U`/`D`/`L`/`R` → `ELIMINATED\n`.

---

### 8. Maze Properties

* Grid: up to **49×49**, always odd dimensions, always fully connected.
* Start `>` at `(1,1)`, exit `<` at `(h-2, w-2)`.
* **4 portal pairs** (`A`–`D`), each guaranteed to save at least `baseline/8` steps.
* Stepping onto a portal teleports you to its partner in one step. The `TELEPORT {r} {c}` response gives your new absolute coordinates so you can anchor your internal map.
* The maze contains cycles — multiple routes of different lengths exist.

---

### 9. Constraints

* **Move timeout:** 1 second per move.
* **Round limit:** 500 moves per round.
* **Standard Library only:** Python 3.10.
