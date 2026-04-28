# Word Gem Puzzle — Tournament Spec

## 1. The challenge

Each round you receive a sliding-puzzle board with letters: a `w × h` grid containing `w·h − 1` lowercase letter tiles plus one empty slot (the *blank*). You may slide tiles into the blank to rearrange the board. You may also claim words formed by **straight horizontal (across, left-to-right) or vertical (down, top-to-bottom) runs of letter tiles** on the **current** state of your board — like crossword and Scrabble placements. Diagonal runs and reverse runs (right-to-left or bottom-to-top) are not valid claims. **Each round runs for exactly 10 seconds of wall-clock time** from the moment the server sends `START`. Score points by claiming valid words.

The tournament is a **round-robin of 1v1 matches**. Every pair of registered bots plays one match against each other. During a match, only the two paired bots receive `ROUND` headers; everyone else stays silently connected, waiting for their match. Each bot has its own independent copy of the same starting grid for that round; your slides do not affect your opponent's grid. **Word claims are a race within the match**: each unique word in a round can be scored by at most one of the two bots (whichever submits it first); the other gets `TAKEN`. Speed and network efficiency matter.

You are a self-contained Python 3.10 client. Use only the Python standard library. Connect to `localhost:7474` over TCP.

## 2. Wire framing

- All messages in both directions are **ASCII text**, lines terminated by a single `\n` (LF, byte `0x0a`). **CRLF is invalid.** A line containing `\r` may be treated as malformed.
- Every server message is a complete line ending in `\n`. Every bot message must be a complete line ending in `\n`.
- The server reads bot input with line buffering. You must flush after each line you send (e.g. `sock.sendall(line.encode())` or `print(..., flush=True)` if using `print` over a `socket.makefile`).
- Lines have no leading or trailing whitespace beyond the single terminating `\n`. A trailing space, leading space, double space, or any non-conforming whitespace makes the line malformed and the server responds `DQ malformed`.
- All numeric fields are decimal ASCII integers without sign or leading zeros (except `0` itself).

## 3. Connection handshake

1. **Read your bot name from the `BOTNAME` environment variable.** Do not hardcode it; do not derive it from `sys.argv`; do not generate it. The exact bytes in `os.environ['BOTNAME']` (after stripping any trailing `\n`) are your bot identifier — use them verbatim.
2. Open a TCP connection to `localhost:7474`.
3. **Send the BOTNAME value as the first line**, terminated by a single `\n`. The server reads exactly one line as your bot identifier. The value must be 1–32 characters from the set `[A-Za-z0-9_-]` (printable ASCII, no spaces, no tabs, no control chars, no `\r`). A value violating these rules causes the server to immediately close the connection — no DQ message, no participation in the tournament.
4. Wait for the first `ROUND` line. Do **not** send any `S` or `W` command before the server has sent `START` for round 1.

**The same "do not send between rounds" rule applies for the entire tournament:** after `ROUND_END <pts>` and before the next `ROUND <n+1>` header (or `TOURNAMENT_END`), do not send anything. Bytes sent during this window are discarded by the server (see §9).

## 4. Round protocol

The server sends one round at a time. Round dimensions are not announced in advance — you learn `w` and `h` only when each round starts.

**Server → bot, per round (in order, on consecutive lines):**

```
ROUND <n> <w> <h>
<row 0>
<row 1>
...
<row h-1>
START
```

- `<n>` is the 1-indexed round number **within the current match** (1 to 5). It resets at the start of each new match.
- Each `<row i>` is exactly `w` characters long: lowercase ASCII letters `a..z` plus exactly one underscore `_` somewhere in the entire grid (the blank). Each individual row contains either zero or one underscore; the whole grid contains exactly one underscore.
- Row 0 is the **top** row. Column 0 is the **left** column.
- After the `START` line, the server begins reading your input and the round's 10-second wall-clock timer starts. The round ends 10 seconds later regardless of how many commands you have sent. Bytes you send before `START` are not processed and may be discarded.

**Bot → server, during the round (one command per line):**

```
S <D>
W <word> <O> <r>,<c>
```

Strict syntax (server uses a regex match; any deviation is `DQ malformed`):

- Slide line: `^S [UDLR]$` (literal `S`, single space, one of the four direction letters, then `\n`).
- Claim line: `^W [a-z]+ [AD] (0|[1-9][0-9]*),(0|[1-9][0-9]*)$` (literal `W`, single space, the lowercase word, single space, orientation `A` (across) or `D` (down), single space, the `row,col` of the word's first letter, then `\n`).

**Direction semantics for `S`:**

- `<D>` names the way the **blank** moves. `S U` swaps the blank with the tile directly above it (blank moves up, tile slides down into the blank's old position). Slides off the edge of the board are `DQ invalid_slide`.

**Placement semantics for `W`:**

- `<O>` is the placement orientation: `A` (across) means the word reads left-to-right starting at `(r, c)`; `D` (down) means the word reads top-to-bottom starting at `(r, c)`. The word occupies exactly `len(word)` cells:
  - **Across (`A`):** `(r, c), (r, c+1), (r, c+2), ..., (r, c + len(word) - 1)`. All cells must be on the same row.
  - **Down (`D`):** `(r, c), (r+1, c), (r+2, c), ..., (r + len(word) - 1, c)`. All cells must be in the same column.
- `(r, c)` is the cell of the **first letter** of the word. There is no path payload: orientation + start cell + word length completely determine the cells.
- Diagonals, reverse direction, and zigzag paths are not allowed by construction (the syntax has no way to encode them) and are not valid word claims.

**Server → bot, after each command:**

| Server line | Meaning |
|---|---|
| `MOVED` | Slide accepted; the server has updated your grid. |
| `OK <points>` | Claim accepted. `<points>` is computed per the formula in §6 (Scoring) and may be negative. The word is now reserved to you for this round (subsequent submissions of the same word from you will return `DUP`; from other bots will return `TAKEN`). |
| `TAKEN` | The word is in the dictionary and your stated path is valid, but another bot already received `OK` for this word this round. No DQ, no points. |
| `DUP` | The word is one you yourself already received `OK` for this round. No DQ, no points. |
| `DQ <reason>` | Disqualified for this round. Round-end follows immediately (see §9). |

A `W` line that is in the dictionary but whose placement is invalid is `DQ`, **not** `TAKEN`. A `W` line for a word that's already taken by another bot is `TAKEN` — `TAKEN` checking happens after placement validation succeeds.

**Server → bot, at end of round:**

```
ROUND_END <pts>
```

Where `<pts>` is your total points for the round (sum of all `OK <points>` you received). After `ROUND_END`, one of three things happens:

- The next round of the **same match** begins: `ROUND <n+1> ...` arrives immediately.
- The current match has ended and you're not in the next match: **the socket is silent for the duration of other matches** (potentially many minutes). Stay connected and keep your `recv()` blocking; do not set socket timeouts.
- The tournament has ended: `TOURNAMENT_END` arrives.

There is no explicit `MATCH_START` / `MATCH_END` marker — you just see ROUND headers when it's your turn, and silence between.

**Server → bot, at end of tournament:**

```
TOURNAMENT_END
```

## 5. Word validity

A `W <word> <O> <r>,<c>` claim is accepted **only if all of the following hold** on the bot's grid at the moment the server processes the claim:

1. `len(word) >= 3` and `word` matches `[a-z]+`. The maximum word length is `w` for an across placement and `h` for a down placement (the word must fit on the board).
2. `word` is in `dictionary.txt` (in the bot's working directory; ~370K words, one per line, lowercase ASCII, LF-terminated).
3. `<O>` is exactly `A` or `D`. The starting cell `(r, c)` satisfies `0 <= r < h` and `0 <= c < w`.
4. The placement fits on the board:
   - **Across (`A`):** `c + len(word) - 1 < w`.
   - **Down (`D`):** `r + len(word) - 1 < h`.
5. For each `i in 0..len(word)-1`, the cell at the placement's `i`-th position holds the `i`-th letter of `word`. Specifically:
   - **Across:** `grid[r][c+i] == word[i]`.
   - **Down:** `grid[r+i][c] == word[i]`.
6. None of the placement's cells is the blank.

Closed list of DQ reasons (the exact strings the server sends, in the precedence order checked):

| Trigger | DQ reason string | Coordinates encode |
|---|---|---|
| Line doesn't match the slide or claim regex (whitespace, CRLF, unknown command, bad orientation char, etc.) | `DQ malformed` | — |
| Line is `S <D>` but the slide leaves the board | `DQ invalid_slide_<D>` | — |
| Word fails condition 1 (`len < 3`) | `DQ short_word` | — |
| Word fails condition 2 (not in dictionary) | `DQ not_in_dictionary` | — |
| Starting cell out of bounds (condition 3) | `DQ oob_start_<r>,<c>` | start cell coords |
| Placement runs off the board (condition 4) | `DQ oob_end_<O>_<r>,<c>` | start cell coords + orientation |
| A cell on the placement is the blank | `DQ cell_is_blank_<r>,<c>` | offending cell coords |
| A cell's letter doesn't match the word's letter at that position | `DQ letter_mismatch_at_<r>,<c>` | offending cell coords |

All `<r>,<c>`, `<O>`, and `<D>` placeholders are literal substitutions: cells are 0-indexed `row,col`; orientation is `A` or `D`; slide direction is `U`/`D`/`L`/`R`. Conditions are evaluated in the order shown. The first failure determines the DQ reason.

`DUP` (a word for which you previously received `OK` this round) is **never** a DQ — the response is just `DUP`, no points awarded, no round-end. `TAKEN` (another bot got `OK` for this word first) is also never a DQ. Both are normal responses; the server continues reading your next line.

## 6. Scoring

When the server returns `OK <points>` for a claim, the points are computed as:

```
<points> = len(word) - 6
```

This means:

| word length | points |
|---|---|
| 3 | −3 |
| 4 | −2 |
| 5 | −1 |
| 6 |  0 |
| 7 | +1 |
| 8 | +2 |
| 9 | +3 |
| 10 | +4 |
| ... | ... |

Points may be negative. Your round score is the sum of `<points>` over every accepted (`OK`) claim that round. `DUP`, `TAKEN`, and `DQ` responses contribute zero. A `DQ` does not subtract from earlier accepted claims; the round just ends at that point with whatever sum you had so far.

There is no scoring floor, ceiling, or bonus beyond `len(word) - 6` per claim.

## 7. Slide validity

A `S <D>` slide is accepted only if the blank can move in direction `D` without leaving the board. Otherwise the response is `DQ invalid_slide_<D>` and the round ends for this bot.

After an accepted slide, the server sends `MOVED` and your grid is updated server-side. The server does not re-send the grid; you are responsible for tracking it locally.

## 8. Pace of play

You may send any number of `S` slides and `W` claims in any interleaving for the entire 10-second window. There is no per-action limit, no required ordering, and no minimum or maximum number of slides between claims. The server processes commands sequentially per bot in the order received. The round ends only when one of the conditions in §9 fires.

## 9. Round end

The round ends for a bot when any of:

- The round's 10-second wall-clock timer expires. The clock starts after the server sends `START` and runs for exactly 10 seconds; the round ends at that moment regardless of how busy or idle either bot has been.
- The bot is `DQ`'d (any invalid slide or invalid claim, or any malformed line).
- The bot's TCP connection closes (TCP FIN or RST).

The server sends a final `ROUND_END <pts>` line at round end for every active-match bot **whose connection is still open**. If the bot has already TCP-closed, the round simply ends silently for that bot; no `ROUND_END` is delivered. After `ROUND_END` an open-connection bot stays connected for the next round of the same match (if any), then for subsequent matches once their turn comes around (with potentially long silent gaps), and finally for `TOURNAMENT_END`. A DQ in one round does not affect later rounds or matches as long as the connection is still open.

**Pipelining semantics.** You may send multiple lines back-to-back without waiting for responses. The server processes them strictly in arrival order. Two important consequences:

- If a pipelined command in your TCP buffer triggers `DQ`, the server emits the `DQ <reason>` response, then `ROUND_END <pts>`, then **discards any remaining pipelined commands for that round** (they are not processed and produce no responses). Lines that arrived after `ROUND_END` but before the next `ROUND` header are also discarded (see below).
- When the round's 10-second timer expires while there are still queued lines in the kernel buffer, the same rule applies: the server emits `ROUND_END <pts>` and discards any unread lines for that round. The "last command processed" is whichever one was actively being read when the timer hit zero — a command being read at the moment of timeout is treated as not-processed.

Commands sent in the inter-round window (after `ROUND_END` and before the next `ROUND <n+1>` header) are silently discarded — they do not generate responses and do not affect any state. Do not send between rounds.

## 10. Tournament structure

The tournament is a **round-robin of 1v1 matches**. With `B` registered bots, `C(B, 2)` matches are played in some server-chosen order. Each match is between exactly two bots; the other bots are silent on the wire while the active match is underway.

**Per match:**

- 5 rounds. Each round uses a different grid size selected from a server-defined schedule.
- Both bots play the same starting grid for each round.
- Round score is the sum of all `OK <points>` received in that round. (Same as before.)
- **Round outcome:** whichever bot has the higher round score wins the round. Equal scores → draw.
- **Match outcome:** whichever bot wins more rounds out of 5 wins the match. If round wins are tied (e.g. 2–2 with one draw), the match is a draw.

**Tournament points:**

- Match win: 3 points
- Match draw: 1 point
- Match loss: 0 points

**Tournament standings:** total tournament points, descending. Tiebreak by total round wins across all matches; further tiebreak by cumulative round score.

There is no per-round rank-points table or all-bots-ranked-together scoring; you only ever care about your single opponent in the current match.

## 11. Constraints

- `w` and `h` are each in `[3, 30]`.
- Letters are sampled from an English-frequency distribution (Scrabble-tile-bag-ish); identical seed across both paired bots within the same round so they start from the same grid.
- Standard library only.
- 10-second wall-clock per round (fixed; the round ends 10 seconds after `START`).
- The full tournament may take 30+ minutes of wall-clock time (45 matches × 5 rounds × 10s = 37.5 min upper bound). Stay connected for the duration; do not set socket read timeouts.

## 12. Sample wire transcript

> **Illustrative only.** The grid size shown (6×4) is chosen for readability so you can see every cell. Actual tournament rounds use a server-defined per-match schedule with grids in the 10×10 to 25×20 range (within the §11 bounds). The wire format, line ordering, and response semantics shown below are exactly what the real server produces; only the dimensions and specific letter content are illustrative.

Here is one bot's transcript for a single illustrative round, showing every kind of normal response. `>>` lines are bytes the bot sends (each ending in `\n`); `<<` lines are bytes the server sends.

The grid for this example (6 cols × 4 rows) is chosen so each line in the transcript is concretely valid against the cells shown:

```
treads      ← row 0
_antic      ← row 1 (blank at col 0)
robber      ← row 2
sleeve      ← row 3
```

Transcript:

```
>> wordsmith_bot
<< ROUND 1 6 4
<< treads
<< _antic
<< robber
<< sleeve
<< START
>> W treads A 0,0
<< OK 0
>> W tread A 0,0
<< OK -1
>> W treads A 0,0
<< DUP
>> W reads A 0,1
<< OK -1
>> W antic A 1,1
<< OK -1
>> W sleeve A 3,0
<< OK 0
>> W rob A 2,0
<< TAKEN
>> S R
<< MOVED
>> W foo A 0,0
<< DQ not_in_dictionary
<< ROUND_END -3
<< ROUND 2 ...
```

Walk-through:

- **Connect.** First line is the bot's name. Server reads exactly one line as the bot identifier.
- **Across claim, full row.** `treads A 0,0` places `treads` across at row 0 starting at col 0; cells (0,0..0,5) are `t,r,e,a,d,s` — match. 6 letters → `OK 0`.
- **Shorter prefix.** `tread A 0,0` places `tread` across at (0,0) using cells (0,0..0,4). 5 letters → `OK -1`. Different word from `treads`, no DUP.
- **DUP.** Re-submitting `treads` returns `DUP`; no DQ, no points.
- **Different anchor, same row.** `reads A 0,1` covers cells (0,1..0,5) = `r,e,a,d,s`. 5 letters → `OK -1`.
- **Different row.** `antic A 1,1` covers cells (1,1..1,5) = `a,n,t,i,c`. 5 letters → `OK -1`.
- **Bottom row.** `sleeve A 3,0` covers cells (3,0..3,5). 6 letters → `OK 0`.
- **TAKEN.** `rob A 2,0` covers cells (2,0..2,2) = `r,o,b` — valid placement, in dictionary, but another bot already received `OK` for `rob` this round. `TAKEN`, no DQ, no points.
- **Slide.** `S R` moves the blank right: blank was at (1,0), now at (1,1). The `a` that was at (1,1) is now at (1,0). The server returns `MOVED`. Updated grid is `treads / a_ntic / robber / sleeve`. The bot must keep this in sync locally; the server does not echo the new grid.
- **DQ on a non-word.** `W foo A 0,0` is a syntactically valid claim but `foo` is not in `dictionary.txt`. Server returns `DQ not_in_dictionary` and the round ends for this bot.
- **Round end.** Score is `0 + −1 + −1 + −1 + 0 = −3` (DUP, TAKEN, DQ contribute 0). Server sends `ROUND_END -3` and immediately sends `ROUND 2 ...`.

Each `S` and `W` is one network round-trip.

## 13. Notes

- Track your local copy of the grid yourself. The server does not echo it back after slides.
- An invalid slide (off-board) is a `DQ` for the round. Track your blank's position and board boundaries carefully.
- Race semantics: only the first bot to receive `OK` for a given word gets the points. Later submitters of the same word receive `TAKEN`. Submitting an already-taken word never DQs you, but it costs round-trip time.
- Race ordering is server-serialized. The server processes claim verification under a single global lock per round; "first" means "first claim that the lock observed with the word not yet taken". Two near-simultaneous claims will be ordered by whichever the server's single-threaded claim handler dequeues first. There are no ties on word ownership.
- Pipelining (sending multiple commands without waiting for each response) is allowed; the server processes them sequentially in arrival order.
