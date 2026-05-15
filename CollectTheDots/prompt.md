# CollectTheDots — Tournament Spec

## Task

**Write a complete, self-contained Python 3.10 bot client that competes in this tournament.** The bot connects to the tournament server at `localhost:7474`, plays every round it is dealt, and tries to score as many tournament points as possible. Use only the Python standard library. Do not leave placeholder strategies, demo stubs, or "STRATEGY GOES HERE" comments — the bot must implement a full solution that produces a valid circle covering for each round.

You may add your model name as a comment at the top of the file (e.g. `# bot author: <model name and version>`).

## 1. The puzzle

A `w × h` axis-aligned rectangle in the first quadrant of the plane, with its lower-left corner at `(0, 0)` and its upper-right corner at `(w, h)`. The rectangle contains `N` dots at integer coordinates. Each dot has a unique index `0..N − 1`; two dots may share the same `(x, y)` coordinate (coincident dots are still two separate dots that both need to be covered). The bot must cover every dot with one or more circles, subject to three constraints, and the round score is the number of circles submitted. **Fewer circles wins.**

### Definitions

- A **circle** is a triple `(cx, cy, r)` of real numbers with `r > 0`. The circle is the set of points `(x, y)` with `(x − cx)² + (y − cy)² ≤ r²` (closed disk; the boundary counts as part of the circle).
- A circle **lies inside the rectangle** if `cx − r ≥ 0` and `cx + r ≤ w` and `cy − r ≥ 0` and `cy + r ≤ h`. The circle's boundary may touch the rectangle's edge.
- Two circles **overlap** if the distance between their centres is strictly less than the sum of their radii. They may touch (distance equal to the sum of radii) without overlapping.
- A dot `(x, y)` is **covered** by a circle `(cx, cy, r)` if `(x − cx)² + (y − cy)² ≤ r²` (the dot is on or inside the circle).

### Constraints

A valid submission satisfies all three:

1. **Every dot is covered by at least one circle.**
2. **Every circle lies inside the rectangle.**
3. **No two circles overlap.**

Because circles cannot overlap, each dot is covered by exactly one circle (boundary cases aside).

### Tolerance

The server applies a tolerance of `ε = 1e-6` to every geometric inequality:

- Rectangle containment: `cx − r ≥ −ε`, `cx + r ≤ w + ε`, `cy − r ≥ −ε`, `cy + r ≤ h + ε`.
- Non-overlap: distance between centres ≥ `r₁ + r₂ − ε`.
- Dot coverage: distance from dot to centre ≤ `r + ε`.

This lets bots use float arithmetic without worrying about the last bit of precision. Do not rely on the tolerance to fit illegal placements — the cushion is for rounding, not for cheating.

### Worked example

A round with `w = 20`, `h = 10`, and three dots at `(2, 5)`, `(3, 5)`, `(15, 5)`:

- Submission with **3 circles** (one per dot): always valid, score 3.
- Submission with **2 circles** that covers `(2, 5)` and `(3, 5)` with one circle and `(15, 5)` with another: valid if the circles fit in the rectangle and don't overlap; e.g., `CIRCLE 2.5 5.0 0.7` plus `CIRCLE 15.0 5.0 4.5`. Score 2.
- Submission with **1 circle** of radius 6.6 centred at `(8.5, 5.0)`: covers all three dots, fits in the rectangle (centre to right edge = 11.5 ≥ 6.6, centre to left edge = 8.5 ≥ 6.6, top/bottom = 5 ≥ 6.6 — fails the top/bottom check). Invalid.

## 2. Tournament structure

10 solo rounds played serially. Each round's rectangle dimensions and dot positions are chosen by the server and announced at round start; the bot adapts at runtime. Bots are not told the per-round schedule in advance.

Per-round bounds the bot can rely on:

- `30 ≤ w ≤ 300`, integer.
- `30 ≤ h ≤ 300`, integer.
- `5 ≤ N ≤ 100`, integer.
- Each dot has integer coordinates `x ∈ [0, w]`, `y ∈ [0, h]`. Multiple dots may share a coordinate.

### Per-round score and ranking

The bot's **round score** is the number of circles in its submission if the submission is valid; an invalid submission scores no round-score (it scores 0 tournament points for the round, regardless of timing).

Per-round ranking among **valid** submissions: **lower circle count wins**. Tournament points by rank:

| Rank | Points |
|---|---|
| 1st | 10 |
| 2nd | 7 |
| 3rd | 5 |
| 4th | 3 |
| 5th | 1 |
| 6th and below | 0 |

Ties on circle count break by **earliest submission timestamp** at the server (earlier wins the higher rank). Invalid submissions, timeouts, and malformed submissions score 0 tournament points regardless of timing.

### Tournament standings

Total tournament points across all 10 rounds, descending. Tiebreak by total wins (1st-place finishes), then by total cumulative submission time across rounds where the bot earned ≥ 1 point (lower wins).

## 3. Wire framing

- All messages in both directions are ASCII text, lines terminated by a single `\n` (LF, byte `0x0a`). **CRLF is invalid.**
- Every server message is a complete line ending in `\n`. Every bot message must be a complete line ending in `\n`.
- The server reads bot input with line buffering. Send each line as a complete byte sequence ending in `\n`.
- Lines have no leading or trailing whitespace beyond the single terminating `\n`.

## 4. Connection handshake

**The server has a 10-second registration window.** It opens when the server starts and closes 10 seconds later. Steps 1–3 below must complete within that window. After 10 seconds, the server stops accepting new connections and begins the tournament with whichever bots registered in time. A bot that misses the window does not play any round and receives zero tournament points; it will not appear in the tournament log at all. **Do not perform heavy precomputation before step 3** — the prompt's allowance for pre-`ROUND 1` precomputation (see §9) applies *after* the connect-and-send-BOTNAME handshake, not before.

1. **Read your bot name from the `BOTNAME` environment variable.** Do not hardcode it; do not derive it from `sys.argv`; do not generate it. The value of `os.environ['BOTNAME']` is your bot identifier — use it verbatim (no whitespace stripping required; the value is plain ASCII with no surrounding whitespace). If `BOTNAME` is absent or empty, the bot is misconfigured and should exit non-zero without attempting to connect.
2. **Open a TCP connection to `localhost:7474`.** This must happen inside the 10-second registration window. Do not precompute before this step.
3. **Send the BOTNAME value as the first line**, terminated by a single `\n`. The server reads exactly one line as your bot identifier. The value must be 1–32 characters from the set `[A-Za-z0-9_-]`. A value violating these rules causes the server to immediately close the connection.
4. **Wait for a `ROUND` line announcing the first round.** Until you receive `ROUND`, do not send anything. Any heavy precomputation should run here (after steps 1–3), on a background thread or worker pool while the main thread blocks on the socket read.

## 5. Round protocol

The server announces each round to all registered bots simultaneously:

```
ROUND <round_num> <w> <h> <N>
DOT 0 <x0> <y0>
DOT 1 <x1> <y1>
...
DOT N-1 <xN-1> <yN-1>
```

- `<round_num>` is the 1-indexed round number, `1..10`.
- `<w>` and `<h>` are positive integers giving the rectangle width and height.
- `<N>` is the number of dots in this round.
- Each `DOT` line carries the dot's index (matching its order in the list, `0..N-1`) and its integer coordinates.

The bot has **30 seconds wall-clock** from the instant the server has finished sending the last `DOT` line to the instant the server has finished reading the bot's `END` line. The clock counts the bot's compute time and any time spent transmitting. Server-side validation runs after the `END` line is received and is not counted in the budget.

The bot's submission is one or more `CIRCLE` lines followed by a single `END` line:

```
CIRCLE <cx> <cy> <r>
CIRCLE <cx> <cy> <r>
...
END
```

- `<cx>`, `<cy>`, `<r>` are decimal floats. The server parses them with Python `float()`. Exponential notation (`1.5e2`) is permitted. The radius must be strictly positive (`r > 0`).
- Exactly one space separates `CIRCLE` from `<cx>`, and one space between each adjacent pair of numbers.
- An empty submission (zero `CIRCLE` lines) is invalid unless `N = 0`, which the server will not generate.

After the `END` line (or after the 30 s deadline), the server replies with one of:

```
OK <circle_count>
```

or

```
INVALID <reason>
```

`<circle_count>` is the number of circles submitted (an integer, decimal). `<reason>` is a closed-list machine-readable token (see §6). After `OK` or `INVALID`, the server sends:

```
END_ROUND <round_num>
```

The bot then waits for the next `ROUND` line. After all 10 rounds, the server sends:

```
TOURNAMENT_END
```

Stay connected for the duration of the tournament; do not close your socket until you receive `TOURNAMENT_END` or the server closes the connection.

A round in which the bot's submission is rejected still proceeds to `END_ROUND` normally; the bot is expected to continue to the next round.

**Per-round message sequence.** After the bot sends its `END` line, the server sends exactly two lines in order: first one result line (`OK <circle_count>` or `INVALID <reason>`), then one `END_ROUND <round_num>` line. The bot must read both lines before reading the next `ROUND` line; ignoring the result line will desync the line-by-line parser.

## 6. Validation

The server validates the submission as a unit. The first failure determines `INVALID <reason>`:

| Trigger | INVALID reason |
|---|---|
| The submission did not arrive (no `END` line received) within 30 s | `timeout` |
| Some line before `END` doesn't match `^CIRCLE -?[0-9]+(\.[0-9]+)?(e[+-]?[0-9]+)? -?[0-9]+(\.[0-9]+)?(e[+-]?[0-9]+)? -?[0-9]+(\.[0-9]+)?(e[+-]?[0-9]+)?$` (wrong prefix, missing or extra fields, leading/trailing whitespace, etc.) | `malformed_circle_<i>` (`i` is the 0-indexed line number among the bot's submission lines) |
| A circle has `r ≤ 0` after parsing | `bad_radius_<i>` |
| A circle does not lie inside the rectangle (within tolerance) | `out_of_bounds_<i>` |
| Two distinct circles overlap (centre distance strictly less than `r₁ + r₂ − ε`) | `overlap_<i>_<j>` (lower-indexed circle first) |
| Some dot is not covered by any circle (within tolerance) | `uncovered_dot_<idx>` (server reports the smallest uncovered dot index) |

If all checks pass, the server replies `OK <circle_count>` and the round score is `<circle_count>`.

## 7. Constraints

- One TCP connection per bot, opened once at startup and held open until `TOURNAMENT_END` or socket close.
- Standard library only.
- Bot identifier from `BOTNAME` env var (see §4).
- Per-round wall-clock budget 30 s.
- Tournament structure is 10 rounds played serially, fixed by the server at startup. Per-round dimensions and dot counts are chosen by the server within the bounds in §2.
- Do not set socket read timeouts; idle reads should block.

## 8. Sample wire transcript

Illustrative — a small round, showing `alpha_bot`'s point of view.

```
>> alpha_bot
<< ROUND 1 20 10 3
<< DOT 0 2 5
<< DOT 1 3 5
<< DOT 2 15 5
>> CIRCLE 2.5 5.0 0.7
>> CIRCLE 15.0 5.0 4.5
>> END
<< OK 2
<< END_ROUND 1
<< ROUND 2 ...
```

Walk-through:

- **Connect.** First line sent is the bot's `BOTNAME`.
- **ROUND header + DOT lines.** Round 1 is a 20×10 rectangle with 3 dots.
- **Submission.** Bot sends two circles. The first covers `(2, 5)` and `(3, 5)`; the second covers `(15, 5)`. Both fit inside the rectangle and don't overlap. Terminates with `END`.
- **Server response.** `OK 2` — two circles, valid covering. `END_ROUND 1` follows. The bot waits for the next `ROUND`.

## 9. Notes

- The bot may take any approach to compute its circle covering, including pre-computation before the first `ROUND` line arrives. To use pre-`ROUND 1` time for precomputation, the bot must first complete the §4 handshake (open the TCP connection and send BOTNAME) within the 10-second registration window, then run the precomputation on a background thread or worker pool while waiting for the first `ROUND` line. Precomputing before opening the TCP connection risks missing the registration window and forfeiting the whole tournament.
- The 30 s clock per round only starts at each `ROUND` line.
- A round's `INVALID` only forfeits points for that round. The bot remains connected and is expected to handle the next `ROUND` normally.
- Submitted circle order does not affect the score. The server validates as an unordered set.
- After `TOURNAMENT_END`, the bot may close its socket and exit.
- A trivial valid submission always exists: one tiny circle per dot, each with radius `r < ½ × dist_to_nearest_dot` and `r < dist_to_nearest_rectangle_edge`. This guarantees `N` circles. Beating the trivial submission requires clustering dots into larger circles that still fit the non-overlap and rectangle constraints.
