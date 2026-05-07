# WarehouseRobot — Tournament Spec

## Task

**Write a complete, self-contained Python 3.10 bot client that competes in this tournament.** The bot connects to the tournament server at `localhost:7474`, plays every round it is dealt, and tries to score as many tournament points as possible. Use only the Python standard library. Do not leave placeholder strategies, demo stubs, or "STRATEGY GOES HERE" comments — the bot must implement a full strategy that produces a complete trip plan for each round.

You may add your model name as a comment at the top of the file (e.g. `# bot author: <model name and version>`).

## 1. The puzzle

A robot collects items from bins in a warehouse and returns each load to a drop-off point. Each round the bot is given a list of items and must compute an offline schedule of trips that picks up every item and minimises total elapsed time. The bot ships the trip list; the server simulates and computes the score.

### Geometry

- The warehouse is a `wm × hm` integer grid (units: meters). The robot moves on a Manhattan grid: lanes at every integer `x` and every integer `y`. Distance between two points `(x1, y1)` and `(x2, y2)` is `|x2 − x1| + |y2 − y1|` meters.
- The drop-off point is at `(0, 0)`. The robot starts every round at `(0, 0)` with load 0 kg, and at the end of every trip must be at `(0, 0)` to unload.

### Items and bins

- Each item is a triple `(x, y, weight_kg)` with integer `x`, `y`, and `weight_kg`. Coordinates satisfy `0 ≤ x ≤ wm`, `0 ≤ y ≤ hm`, and `(x, y) ≠ (0, 0)` (no item is placed at the depot).
- Items are distinguishable by integer index `0..N − 1`. Multiple items may share a bin (same `x`, `y`). Item weights are integers in `[1, 25]` kg per item; no individual item can single-handedly stop the robot.

### Speed

The robot's speed in meters per minute is a function of its current load:

```
speed(load_kg) = 10 − (load_kg // 10)        # integer division; 0 if load_kg ≥ 100
```

- 0 kg → 10 m/min, 1–9 kg → 10 m/min, 10 kg → 9 m/min, …, 90 kg → 1 m/min, 91–99 kg → 1 m/min, **≥ 100 kg → 0 m/min (stuck)**.
- For a leg from point `A` to point `B`, the robot's speed is `speed(load_at_A)`. The pickup at `B` happens *after* arrival; the load update applies to the *next* leg. So picking up a heavy item at the end of a trip slows only the return-to-origin leg, not the leg used to reach that item.
- Time for a leg of distance `d` meters at speed `s` m/min is `d / s` minutes (floating-point division). **Zero-distance legs take 0 minutes at any load**, including load ≥ 100 kg; the `d / s` formula is only evaluated for `d > 0`. Total time is the sum of all leg times across all trips.
- Pickup and unload are instantaneous (zero time).

#### Worked example

Trip = `(item_0 at (3, 0, 7 kg)) → (item_1 at (3, 0, 9 kg)) → (item_2 at (5, 0, 40 kg))`:

- Leg 1: from `(0, 0)` to `(3, 0)`. Load at start = 0. Speed = 10. Distance = 3. Time = 0.30 min. After arrival, pick up item 0; load = 7 kg.
- Leg 2: from `(3, 0)` to `(3, 0)`. Same bin (item 1 shares it). Distance = 0. Time = 0. After arrival, pick up item 1; load = 16 kg.
- Leg 3: from `(3, 0)` to `(5, 0)`. Load at start = 16. Speed = `10 − 1` = 9. Distance = 2. Time = 0.2222 min. After arrival, pick up item 2; load = 56 kg.
- Return: from `(5, 0)` to `(0, 0)`. Load at start = 56. Speed = `10 − 5` = 5. Distance = 5. Time = 1.0 min.
- Trip total = 0.30 + 0 + 0.2222 + 1.0 = 1.5222 min.

### Stuck rule

If at the start of any leg the robot's load is `≥ 100 kg` AND the leg has positive distance, the trip is invalid. A zero-distance leg (the next pickup is at the current position because two consecutive items share a bin) is fine at any load.

### Trips

- A **trip** is an ordered sequence of one or more item indices. The robot starts at `(0, 0)`, traverses to each item's bin in the order given (zero distance if two consecutive items share a bin), then traverses back to `(0, 0)`. The server uses the order verbatim and does not reorder.
- Load resets to 0 at the moment the robot returns to `(0, 0)`. The next trip starts there with load 0.
- Empty trips are not allowed. A single-item trip is fine.

## 2. Tournament structure

10 solo rounds played serially. Each round's warehouse dimensions, item count, item placements, and item weights are chosen by the server and announced at round start; the bot adapts at runtime. Bots are not told the per-round schedule in advance.

Per-round bounds the bot can rely on:

- `30 ≤ wm ≤ 200`, `30 ≤ hm ≤ 200`, integer.
- `1 ≤ N ≤ 300`, integer.
- Item weights as specified in §1: integer kg in `[1, 25]` per item.
- Items are not placed at `(0, 0)`.

### Per-round score and ranking

The bot's score for the round is `total_time` in minutes (floating-point; lower is better). Per-round ranking → tournament points:

| Rank | Points |
|---|---|
| 1st | 10 |
| 2nd | 7 |
| 3rd | 5 |
| 4th | 3 |
| 5th | 1 |
| 6th and below | 0 |

Ties on `total_time` break by **earliest submission timestamp** at the server (earlier wins the higher rank; later bots drop down). Invalid submissions, timeouts, and any submission rejected by the validation rules in §6 score 0 round-time points and 0 tournament points for the round, regardless of timing.

### Tournament standings

Total tournament points across all 10 rounds, descending. Tiebreak by total wins (1st-place finishes), then by total cumulative `total_time` across rounds where the bot earned ≥ 1 point.

## 3. Wire framing

- All messages in both directions are ASCII text, lines terminated by a single `\n` (LF, byte `0x0a`). **CRLF is invalid.**
- Every server message is a complete line ending in `\n`. Every bot message must be a complete line ending in `\n`.
- The server reads bot input with line buffering. Send each line as a complete byte sequence ending in `\n`.
- Lines have no leading or trailing whitespace beyond the single terminating `\n`.

## 4. Connection handshake

1. **Read your bot name from the `BOTNAME` environment variable.** Do not hardcode it; do not derive it from `sys.argv`; do not generate it. The exact bytes in `os.environ['BOTNAME']` (after stripping any trailing `\n`) are your bot identifier — use them verbatim. If `BOTNAME` is absent or empty, the bot is misconfigured and should not attempt to connect.
2. Open a TCP connection to `localhost:7474`.
3. **Send the BOTNAME value as the first line**, terminated by a single `\n`. The server reads exactly one line as your bot identifier. The value must be 1–32 characters from the set `[A-Za-z0-9_-]`. A value violating these rules causes the server to immediately close the connection.
4. Wait for a `ROUND` line announcing the first round. Until you receive `ROUND`, do not send anything.

## 5. Round protocol

The server announces each round to all registered bots simultaneously:

```
ROUND <n> <wm> <hm> <N>
ITEM 0 <x0> <y0> <w0>
ITEM 1 <x1> <y1> <w1>
...
ITEM N-1 <xN-1> <yN-1> <wN-1>
```

- `<n>` is the 1-indexed round number, `1..10`.
- `<wm>` and `<hm>` are positive integers giving the warehouse width and height in meters.
- `<N>` is the number of items in this round.
- Each `ITEM` line carries the item's index (matching its order in the list, `0..N-1`), its bin coordinates `(x, y)`, and its integer weight in kg.

The bot has **30 seconds wall-clock** from the instant the server has finished sending the last `ITEM` line to the instant the server has finished reading the bot's `END` line. The clock counts the bot's compute time and any time spent transmitting. Server-side simulation runs after the `END` line is received and is not counted in the budget.

The bot's submission is one or more `TRIP` lines followed by a single `END` line:

```
TRIP <i1> <i2> ...
TRIP <j1> <j2> ...
...
END
```

- Each `TRIP` line lists one or more item indices in the order the robot visits them on that trip.
- Indices are non-negative integers in decimal (no leading zeros except `0`, no sign).
- Every item index `0..N − 1` must appear in exactly one position across all trips. No duplicates, no omissions.
- Trips are simulated by the server in the order the bot sends them. Trip-order does not affect the score (each trip starts and ends at `(0, 0)` with load 0), but the order is preserved in the log for replay.
- An empty `TRIP` line (no item indices) is not allowed.

After the `END` line (or after the 30 s deadline), the server replies with one of:

```
OK <total_time> <trip_count>
```

or

```
INVALID <reason>
```

`<total_time>` is rendered as a float with 4 decimal places (e.g. `12.3456`). `<trip_count>` is the number of trips submitted. `<reason>` is a closed-list machine-readable token (see §6). After `OK` or `INVALID`, the server sends:

```
END_ROUND <n>
```

The bot then waits for the next `ROUND` line. After all 10 rounds, the server sends:

```
TOURNAMENT_END
```

Stay connected for the duration of the tournament; do not close your socket until you receive `TOURNAMENT_END` or the server closes the connection.

## 6. Validation

The server validates the submission as a unit. The first failure determines `INVALID <reason>`:

| Trigger | INVALID reason |
|---|---|
| The submission did not arrive (no `END` line received) within 30 s | `timeout` |
| Some line before `END` doesn't match `^TRIP( [0-9]+)+$` (wrong prefix, lowercase, leading zero in an index, leading or trailing whitespace, etc.) | `malformed_trip_<i>` (`i` is the 0-indexed line number among the bot's submission lines) |
| Some line before `END` is `TRIP` with no item indices | `empty_trip_<i>` |
| Some item index is `< 0` or `≥ N` | `bad_item_<i>_<pos>` (trip number, position within trip) |
| The same item index appears in more than one position across all trips | `duplicate_item_<idx>` |
| Some item index `0..N − 1` does not appear in any trip | `missing_item_<idx>` (server reports the smallest missing index) |
| During simulation, at the start of some leg the robot's load is `≥ 100 kg` and the leg has positive distance | `stuck_at_trip_<i>_leg_<pos>_load_<L>` (`pos` is the index within the trip; `L` is the integer load when stuck) |

If all checks pass and simulation completes, the server replies `OK <total_time> <trip_count>`.

## 7. Constraints

- One TCP connection per bot, opened once at startup and held open until `TOURNAMENT_END` or socket close.
- Standard library only.
- Bot identifier from `BOTNAME` env var (see §4).
- Per-round wall-clock budget 30 s.
- Tournament structure is 10 rounds played serially, fixed by the server at startup. Round sizes follow the table in §2.
- Do not set socket read timeouts; idle reads should block.

## 8. Sample wire transcript

Illustrative — a small round, showing `alpha_bot`'s point of view.

```
>> alpha_bot
<< ROUND 1 10 10 5
<< ITEM 0 3 4 7
<< ITEM 1 7 1 22
<< ITEM 2 1 9 15
<< ITEM 3 6 6 3
<< ITEM 4 8 8 18
>> TRIP 0 3
>> TRIP 1 4
>> TRIP 2
>> END
<< OK 14.3833 3
<< END_ROUND 1
<< ROUND 2 ...
```

Walk-through:

- **Connect.** First line sent is the bot's `BOTNAME`.
- **ROUND header + ITEM lines.** Round 1 is a 10×10 warehouse with 5 items. Each `ITEM <i> <x> <y> <w>` line carries the item's index, bin, and weight.
- **Submission.** Bot sends three trips. Trip 0 visits items 0 then 3 then returns to origin. Trip 1 visits items 1 then 4 then returns. Trip 2 visits item 2 then returns. Each item index appears exactly once. The bot terminates the submission with `END`.
- **Server response.** `OK 14.3833 3` — three trips, total elapsed time 14.3833 minutes. `END_ROUND 1` follows. The bot waits for the next `ROUND`.

## 9. Notes

- Trip order does not affect the score: each trip starts and ends at `(0, 0)` with load 0, so trips are independent. Order matters only within a trip (visit order).
- A round's `INVALID` only forfeits points for that round. The bot remains connected and is expected to handle the next `ROUND` normally. The server still sends `END_ROUND <n>` after `INVALID <reason>`.
- If the bot can't or doesn't want to submit, send any complete submission that satisfies §6 (e.g. one trip per item) and let the server score it; or send `END` on its own line, which fails validation as the first parsed item check.
- Submitted item indices are integers in `0..N − 1`. A `TRIP` line whose indices include leading zeros (e.g. `TRIP 01 02`) is malformed.
- The robot's load at the start of any positive-distance leg must be strictly less than 100 kg. A trip whose total weight is exactly 100 kg is invalid (the return-to-origin leg starts at load 100 with positive distance).
