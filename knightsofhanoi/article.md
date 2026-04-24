# AI coding contest day 10: Knights of Hanoi. Claude swept, and the optimum has a clean floor.

The tenth challenge is a Towers-of-Hanoi variant on a chessboard: `n` disks start stacked on **A1**; move them all to **H8**; the only legal moves are knight's jumps; Hanoi placement rules apply on every move. Bots submit a full solution per round. Shortest valid sequence wins; ties broken by server-receive time. 10-second per-round budget, standard library Python only.

10 rounds, `n` growing from 3 to 12. Scoring 10/7/5/3/1/0 by rank.

## The results

| Bot | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | Points |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Claude (Opus 4.7)** | **18** | **24** | **30** | **36** | **42** | **48** | **54** | **60** | **66** | **72** | **100** |
| **Gemini (Pro 3.1)** | 18 | 24 | 30 | 36 | 42 | 48 | 54 | 60 | 66 | 72 | **70** |
| **Kimi (K2.6)** | 20 | 36 | 64 | 120 | 234 | 464 | 920 | 1824 | 3644 | 7340 | **50** |
| **Grok (Expert 4.2)** | 28 | 52 | 98 | 186 | 360 | 704 | 1390 | 2758 | 5492 | 10956 | **30** |
| **GLM (5.1)** | INV | INV | INV | INV | INV | INV | INV | INV | INV | INV | **0** |
| **Nemotron (3 Super)** | INV | INV | INV | INV | INV | INV | INV | INV | INV | INV | **0** |
| **ChatGPT (GPT 5.5)** | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | **0** |
| **MiMo (V2-Pro)** | — | — | — | — | — | — | — | — | — | — | **DNF** |

*(Cell values are knight-move counts for valid solutions. Bold = round winner. INV = invalid; T/O = timeout; DNF = no bot shipped. MiMo, Claude, and Kimi all hit runaway chain-of-thought loops during authoring — more below.)*

Claude posted a perfect 100 points, winning every round. Gemini matched Claude's move count in every round but submitted slower every time.

## The 6n floor

Look at Claude's and Gemini's counts more carefully: **18, 24, 30, 36, 42, 48, 54, 60, 66, 72** for `n = 3..12`. That's exactly `6n`.

The minimum knight-move distance between A1 and H8 is 6 (they're both dark squares, and a knight must change colour every move — parity forces an even distance, 6 being the shortest). Any disk that ends up on H8 must have traveled at least 6 knight-moves total. For `n` disks that gives a hard lower bound of `6n` total moves. And because each disk needs at least 6, hitting `6n` exactly forces every disk to travel exactly 6 moves — no slack for one disk to cover for another.

That doesn't mean each disk makes a single uninterrupted trip. Both winning strategies do park disks on intermediate squares and pick them up again. What they avoid is any wasted hop: the sum of each disk's knight-move count is exactly 6, never 7, never 8. No disk backtracks, no disk detours around a collision. Claude and Gemini both choreograph `n` disk-journeys along the knight graph such that no disk's route forces another disk off its own 6-move trajectory, while Hanoi placement holds at every intermediate step. Classical Hanoi's `2^n − 1` bound doesn't bind here because 62 helper squares give enough parking room to schedule the disks in pipeline rather than serialize them through a single buffer peg.

## Claude: offline-tuned peg set plus Frame-Stewart

Claude's 249-line bot picks a peg set whose *size* scales with the disk count: 3 pegs for `n ≤ 2`, 4 for `n = 3`, 5 for `n ∈ {4, 5}`, 6 for `n = 6`, 7 for `n = 7`, and 8 pegs — `{A1, B3, C6, D4, E5, F7, D3, H8}` — for `n ≥ 8`. It then runs a Frame-Stewart recursion over the chosen set. For every ordered pair of pegs `(u, v)`, it precomputes a shortest knight path `u → v` that avoids every *other* peg in the set, so the intermediate squares on any peg-to-peg path are non-peg squares and stay empty during normal operation. The Hanoi placement rule therefore holds on every single knight hop without extra checks.

The peg sets were tuned by offline greedy search against a 72-moves-for-n=12 target, which Claude documents in its own module docstring:

```
Peg set tuned via offline greedy search:
  {A1, H8, B3, C6, D4, E5, F7, D3}  -> 72 moves for n=12.
```

The DP is memoized on `(n, src, dst, aux_set)` with `aux_set` as a frozenset, so order-independent subproblems collapse.

Claude was also the fastest to submit — 706ms for n=12 versus Gemini's 1609ms — which is why every tie went Claude's way.

## Gemini: beam-search parking plan, same answer

Gemini's 220-line bot takes a different path to the same floor: a beam search with width 100 that plans parking squares for disks 1..n-1, one disk per level. For each disk, it scores candidate parking squares by `dist(A1→sq) + dist(sq→H8)` and keeps the top-100 parking layouts. Then it executes the plan in three phases — scatter n-1 disks to their parking squares, march disk n from A1 to H8, gather all n-1 disks from their parking squares to H8.

It always reached 72 moves for n=12. The submission-time gap to Claude grew roughly linearly with `n` — at n=3 it was 156ms, by n=12 it was 902ms. Gemini's beam search is more computational work per round than Claude's precomputed Frame-Stewart tables, even though both arrive at the same optimum.

## Kimi and Grok: suboptimal scaling

Kimi (197 lines) runs a standard recursive Hanoi where at each level it tries up to 5 candidate parking pegs scored by path-length sums. There's no global optimization over the peg *set*, so it commits to local choices that compound. At n=12 it emits 7340 moves against the 72-move floor — a 102× penalty.

Grok (114 lines) is simpler still: recursive divide-and-conquer that picks a parking square per sub-problem by scanning row-major for the first square that isn't on the current sub-problem's A→B shortest path. The blocking set shifts with every recursive call rather than tracking a global peg set, so the choreography collapses into a pile of local decisions. 10956 moves at n=12, 152× the floor.

Both scale exponentially in move count; the floor-finders scale linearly. That's the signal from this challenge — move count as `n` grows separates "found the structural insight" (6n) from "brute-forced a tree" (roughly `2^n`).

## Three different ways to zero out

**GLM (5.1, 175 lines)** also runs Frame-Stewart, on a 10-peg set `{A1, B3, C2, D4, E3, F5, G6, F7, H6, H8}` that includes most of Claude's pegs plus extras. The DP is correct. The bug is in move expansion: GLM computes shortest knight paths between peg pairs *without* blocking the other pegs as forbidden intermediates. So on round 1 (n=3) move 3, it tries to place disk 3 directly onto a peg where disk 1 is already parked. `INVALID: cannot place disk 3 on smaller disk 1 at B3`. Same error on every round — the peg interference is structural, not data-dependent.

**Nemotron (3 Super, 179 lines)** uses a two-phase greedy: unstack all disks to arbitrary empty squares, then gather to H8. Its BFS pathfinder rejects any hop that would violate Hanoi at the destination, and when no reachable destination passes the check the BFS returns `None`. That raises, and a broad `except Exception` in the main loop catches the `RuntimeError`, discards the in-progress solution, and sends a literal empty newline. The failure isn't specific to any one disk — any unstack or gather step whose BFS can't find a Hanoi-legal landing triggers it. Server: `INVALID: empty response`. Every round.

**ChatGPT (GPT 5.5, 233 lines)** — the upgrade from GPT 5.3 — has a far simpler bug: `socket.create_connection((HOST, PORT), timeout=5)`. That sets the socket's read timeout to 5 seconds. The server's registration window is 10 seconds; between registering and the first `ROUND` message, the bot waits ~8 seconds idle. Its socket raises `socket.timeout` at the 5-second mark, the exception propagates, Python exits. The server sees EOF on every round read. `TIMEOUT: no response`. The precomputed tables and Frame-Stewart solver are never exercised.

## The CoT loop problem, round two

Three bots — **MiMo, Claude, and Kimi** — all got stuck in runaway chain-of-thought loops during authoring. Last round (Towers of Annoy) Claude and MiMo both DNFed from the same failure mode; Gemini cleaned up. This time, manual intervention pulled Claude and Kimi out of their loops and they both shipped working code. MiMo didn't come out. Second consecutive DNF for MiMo on a challenge that layers protocol, stateful reasoning, and optimization.

This is now a recurring pattern. The challenges are reaching a complexity level where reasoning models are prone to open-ended analysis spirals that they can't close on their own. Intervention can rescue some, but it's a qualitatively different failure than "wrote a bug" — it's "didn't produce output at all."

## The verdict

Knights of Hanoi is the first challenge in this series where two models independently found the theoretical optimum. That's a real marker: the problem structure (disks must travel ≥6 moves; 62 helper squares give you pipeline room) is readable by frontier models without prior exposure. Claude and Gemini both landed it.

The gap between them was pure execution speed. Claude's offline-tuned peg set encoded the answer in a small DP; Gemini's beam search rediscovered it at runtime. Both approaches produce 72 moves for n=12; only one produces them in 700ms.

Below the top two, the gap is vertical. Kimi and Grok scale roughly exponentially against a linear floor — their point scores (50 and 30) flatter their effective performance. The three zero-scorers each illustrate a distinct class of single-line bug: wrong algorithm (GLM's unblocked path expansion), wrong error handling (Nemotron's swallow-and-empty), wrong timeout (GPT 5.5's 5s socket on a 10s protocol).

MiMo's second DNF in two challenges is the real story in the DNF column. Whatever is pushing reasoning models into unbounded deliberation on these prompts, it's hit MiMo harder than any other bot in the field.

---

*Model versions for this challenge: Claude Opus 4.7, Gemini Pro 3.1, Kimi K2.6, Grok Expert 4.2, ChatGPT GPT 5.5 (upgraded from 5.3), GLM 5.1, Nemotron 3 Super. MiMo-V2-Pro was entered but its authoring session looped indefinitely and no `mimo.py` was produced. Claude and Kimi also looped during authoring but were recovered with manual intervention. Board is a standard 8×8 chessboard with disks always starting at A1 and ending at H8; no randomness. Server code, prompt, and generated clients at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
