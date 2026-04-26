# AI coding contest day 11: StackMaxxing. Claude packs the X.

The eleventh challenge: drop polyomino shapes into a rectangular tank, Tetris-style rigid gravity, no line clearing. Bots pick rotation + column for each piece; the server runs the drop and validates. A round ends when the bot can't fit the next piece. Tank dimensions grow round-by-round from 6×8 (R1) to 18×20 (R10). 10-second cumulative wait-time budget per bot per round.

Pieces are pentominoes drawn from a weighted catalog of the six gnarliest one-sided shapes: X (the cross/plus) at 5/12, F and F' at 2/12 each, W/U/T at 1/12 each. The X-pentomino arrives on average every other piece. With its 3×3 bounding box and 5 occupied cells in a plus, every X landing leaves 4 corner gaps in its bounding region — gaps that become unfillable holes unless the underlying terrain happens to have a complementary 4-corner pattern. Greedy heuristics suffer; deep-search ones survive.

10 bots competed. Two new entries this challenge: **Meta Muse Spark** and **DeepSeek V4**.

## The results

| Bot | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | Points |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Claude (Opus 4.7)** | 6 | 10 | **15** | **20** | 26 | 31 | 38 | **40** | 51 | **61** | **69** |
| **Gemini (Pro 3.1)** | 6 | **10** | 14 | 19 | 24 | 29 | **38** | 36 | **54** | 58 | **58** |
| **MiMo (V2-Pro)** | 6 | 9 | 14 | 19 | **27** | 31 | 37 | 38 | 49 | 58 | **45** |
| **Muse Spark (Meta)** | 6 | 10 | 15 | 19 | 27 | **31** | 33 | INV | INV | INV | **30** |
| **DeepSeek (V4)** | 6 | 10 | 14 | 19 | 25 | 27 | 35 | 36 | 45 | 56 | **21** |
| **Grok (Expert 4.2)** | 6 | 9 | 12 | 18 | 25 | 25 | 30 | 36 | 46 | 52 | **15** |
| **GLM (5.1)** | **6** | INV | INV | INV | INV | INV | INV | INV | INV | INV | **10** |
| **Kimi (K2.6)** | 6 | INV | INV | INV | INV | INV | INV | INV | INV | INV | **7** |
| **Nemotron (3 Super)** | 5 | 8 | 13 | 17 | 23 | 25 | 33 | 34 | 47 | 52 | **5** |
| **ChatGPT (GPT 5.5)** | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | **0** |

*(Cell values are pieces placed before the round ended. Bold = round winner. INV = invalid placement / malformed response. T/O = timeout.)*

Claude won the tournament with 69 points, 11 ahead of Gemini. MiMo took third (45). Three bots — GLM, Kimi, ChatGPT — never produced valid output past round 1.

## Claude: three-piece lookahead beam search

Claude's 485-line bot runs a **beam search of width 8–16 over 3-piece lookahead**, evaluating each candidate placement with a 7-feature Dellacherie-style heuristic: hole count (×−7.5), landing height (×−2.0), bumpiness (×−1.2), max height (×−1.0), aggregate height (×−0.6), wells (×−1.5), row fill (×+5.0). Beam width is adaptive: 16 for small tanks where compute budget is plentiful, dropping to 8 on the largest 14×16+ rounds where the search tree blows up.

The lookahead is the differentiator. On X-pentomino landings, Claude's evaluation considers not just the immediate placement but the next two pieces' best response — which often means accepting a worse-looking immediate placement to preserve a flat surface for the next X. Gemini and MiMo do similar things but with shallower or narrower searches.

Won R3, R4, R8, R10 outright; finished top-2 in all 10 rounds.

## Gemini: lightweight 2-ply with a hard time cutoff

Gemini's 237-line bot uses 1- or 2-ply search depending on time pressure: it always tries 2-ply first, but if a 7.5-second deadline approaches it falls back to 1-ply. Evaluation is `−(5×max_height + 10×holes + 1×bumpiness)` — heavy on holes, modest on height.

Lighter than Claude's setup, consistently 1–2 pieces behind on every round. Won R2, R7, R9; 2nd place in seven other rounds. The 58-point total reflects steady solid play, not flashes of brilliance.

## MiMo: 12-wide beam, same lookahead, harder height penalty

MiMo's 212-line bot is structurally similar to Claude's — beam width 12, 3-piece lookahead — but uses a different evaluation: `−(100×max_height + 50×holes + 10×bumpiness + 5×agg_height + 3×wells)`. The 100× weight on max height is huge — literally 10× any other feature. MiMo would rather place X high than place it lower with corner holes, and that bites: high placements stack up and the tank fills sooner.

R5 win (27 pieces tied with Muse). Otherwise mostly 3rd-place finishes. 45 points.

## Muse Spark: great early, crashes at the big boards

Muse's 242-line bot — Meta's new entry — runs beam search over 3-piece lookahead, similar in shape to Claude's. Played competitively through R6 (won R6 outright at 31 pieces). Then **timed out at R7** and **sent malformed responses for R8, R9, R10**.

The diagnosis is in the source: beam-search work scales with tank area, so on the 14×16+ tanks the per-piece evaluation count exceeds Muse's compute budget without an explicit deadline check. After the R7 timeout, the server sends `ROUND_END`; Muse's main loop expects `PIECE` next and raises on the next `ROUND` line, killing the socket. The R8/9/10 responses are EOF reads on a dead connection.

30 points all from the first six rounds, zero from the rest.

## DeepSeek V4: heuristic punished by the X-heavy distribution

DeepSeek's 281-line bot — the other new entry — uses recursive 1-ply search with a heuristic that weights holes at ×1000 and bumpiness at ×5. The heavy hole penalty looks right but its 1-ply lookahead doesn't anticipate the X-pentomino's corner-hole creation.

Result: at every round 4–6 pieces behind the leader. Stable across all 10 rounds, no crashes, no timeouts — the implementation is clean. The heuristic just isn't deep enough for an X-heavy stream. Single-ply planning picks the lowest-hole-count placement *for this piece* but fails to leave good landing terrain for the next X. The cost compounds.

21 points. Cleanly-coded but fundamentally outclassed by anything with two-piece lookahead.

## The X-pentomino factor

The X-pentomino is geometrically the worst pentomino for stacking. Its 3×3 bounding box has 4 unfilled corners that become unfillable holes unless the surrounding terrain happens to have a complementary pattern. With X arriving on average every other piece, every bot's stacking strategy was tested against the same recurring nightmare.

Bots that planned ahead (Claude, Gemini, MiMo) survived because they could choose X placements that minimize hole creation by exploiting existing terrain. Bots with shallower or weaker heuristics (DeepSeek, Grok, Nemotron) saw their placements compound into earlier board collapse. The 5-piece spread between Claude and DeepSeek at R10 (61 vs 56) is mostly attributable to X-placement quality: each missed-opportunity X creates 1–2 holes, and a handful of such misses across a round translates to several fewer pieces fit before the tank caps out.

## Three permanent losers

**ChatGPT (GPT 5.5, 193 lines)** uses `f.readline()` on a socket without timeout management. The `choose_move()` function evaluates every rotation × column with a slow set-based simulation. On round 1 the first PIECE prompt arrives, ChatGPT enters its evaluation loop, the loop takes longer than 10 seconds, server times out, ChatGPT never sends a response. The bot's TCP I/O design effectively guarantees this on any non-trivial board: there is no clock anywhere in the search loop.

**Kimi (K2.6, 253 lines)** and **GLM (5.1, 174 lines)** both have buffer-management bugs in their socket reading. Each plays round 1 cleanly then corrupts internal buffer state and emits malformed responses for the rest. Different code, same failure mode: careless string-handling on TCP framing across line boundaries — the bot reads a full line in round 1, leaves stray bytes in its buffer, then on round 2's prompt those stray bytes prepend to the new data and parsing collapses.

**Nemotron (3 Super, 157 lines)** is the only fully-functional non-top-tier bot that scores low. Its heuristic is too simple — no lookahead, no rotation evaluation beyond rotation 0 — and it places consistently 4–6 pieces behind the leader on every round. Doesn't crash. Doesn't time out. Just isn't strategic enough to win anything.

## The verdict

The top tier separated decisively: 11-point gap from Claude to Gemini, 13 from Gemini to MiMo. Claude's 3-piece lookahead beam search with Dellacherie-style evaluation is the strongest implementation by a clear margin. Gemini's 2-ply with hard cutoff is the cleanest "good enough" approach. MiMo's same-shape-as-Claude beam search loses the 14 points to evaluation tuning — over-weighting max height meant placing X-pentominoes too high too fast.

Two new entries with two distinct stories. **Muse Spark** showed real ability — won R6 at 31 pieces, edging Claude and MiMo who also hit 31 — but lost R8/R9/R10 entirely to a crash bug at the larger board sizes. **DeepSeek V4** played all 10 rounds cleanly but the 1-ply heuristic was the wrong tool for an X-heavy terrain. Both bots are signal: Muse on the upside (capable when running), DeepSeek on the downside (clean code, weak strategy).

ChatGPT's failure is the noisiest line in the table — every round timed out before a single piece was placed. The bot's evaluation loop has no clock, no early exit, no per-piece deadline. Whatever GPT 5.5's code-generation defaults are for socket I/O, they don't include timeout management, and the bot pays the maximum penalty for it.

---

*Model versions for this challenge: Claude Opus 4.7, Gemini Pro 3.1, MiMo-V2-Pro, Meta Muse Spark, DeepSeek V4, Grok Expert 4.2, GLM 5.1, Kimi K2.6, Nemotron 3 Super, ChatGPT GPT 5.5. Muse Spark and DeepSeek V4 are new at this challenge. The catalog used six one-sided pentominoes weighted X×5, F×2, F'×2, W×1, U×1, T×1 — sampling biased toward the geometrically worst stacking shapes. Server code, prompts, generated clients, and the full move trace per bot per round are at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
