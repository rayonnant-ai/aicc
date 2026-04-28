# AI coding contest day 11: StackMaxxing. Claude packs the X.

The eleventh challenge: drop polyomino shapes into a rectangular tank, Tetris-style rigid gravity, no line clearing. Bots pick rotation + column for each piece; the server runs the drop and validates. A round ends when the bot can't fit the next piece. Tank dimensions grow round-by-round from 6×8 (R1) to 18×20 (R10). 10-second cumulative wait-time budget per bot per round.

Pieces are pentominoes drawn from a weighted catalog of six one-sided shapes: X (the cross/plus) at 5/12, F and F' at 2/12 each, W/U/T at 1/12 each. X dominates the stream at about 5 of every 12 pieces (≈42%), roughly two of every five. With a 3×3 bounding box and 5 occupied cells in a plus, an X landing on flat ground leaves 4 corner gaps in its bounding region, and most of those become holes unless the next pieces happen to fit them. Most landings on non-trivial terrain create at least one hole.

10 bots competed. Two new entries this challenge: **Meta Muse Spark** and **DeepSeek V4**.

## The results

| Bot | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | Points |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Claude (Opus 4.7)** | 6 | 10 | **15** | **20** | 26 | 31 | 38 | **40** | 51 | **61** | **69** |
| **Gemini (Pro 3.1)** | 6 | **10** | 14 | 19 | 24 | 29 | **38** | 36 | **54** | 58 | **58** |
| **MiMo (V2-Pro)** | 6 | 9 | 14 | 19 | **27** | 31 | 37 | 38 | 49 | 58 | **45** |
| **Meta (Muse Spark)** | 6 | 10 | 15 | 19 | 27 | **31** | 33 | INV | INV | INV | **30** |
| **DeepSeek (V4)** | 6 | 10 | 14 | 19 | 25 | 27 | 35 | 36 | 45 | 56 | **21** |
| **Grok (Expert 4.2)** | 6 | 9 | 12 | 18 | 25 | 25 | 30 | 36 | 46 | 52 | **15** |
| **GLM (5.1)** | **6** | INV | INV | INV | INV | INV | INV | INV | INV | INV | **10** |
| **Kimi (K2.6)** | 6 | INV | INV | INV | INV | INV | INV | INV | INV | INV | **7** |
| **Nemotron (3 Super)** | 5 | 8 | 13 | 17 | 23 | 25 | 33 | 34 | 47 | 52 | **5** |
| **ChatGPT (GPT 5.5)** | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | **0** |

*(Cell values are pieces placed before the round ended. Bold = round winner. INV = invalid placement / malformed response. T/O = timeout.)*

Claude won the tournament with 69 points, 11 ahead of Gemini. MiMo took third (45). Three bots (GLM, Kimi, ChatGPT) never produced valid output past round 1.

## Claude: three-piece lookahead beam search

Claude's 485-line bot runs a **beam search of width 8–16 over 3-piece lookahead**, evaluating each candidate placement with a 7-feature Dellacherie-style heuristic: hole count (×−7.5), landing height (×−2.0), bumpiness (×−1.2), max height (×−1.0), aggregate height (×−0.6), wells (×−1.5), row fill (×+5.0). Beam width is adaptive: 16 for small tanks where compute budget is plentiful, dropping to 8 on the largest 14×16+ rounds where the search tree blows up.

The lookahead is what separates Claude from the 1- and 2-ply bots: on an X-pentomino, the search evaluates each candidate placement together with the next two pieces' best response, and sometimes picks a worse-looking immediate placement to preserve flat surface for the next X. MiMo runs the same depth with a different evaluation; Gemini runs 2-ply.

Won R4, R8, R10 outright; tied for first with Muse at R3 (both 15, tiebreaker to Claude); top-2 in 9 of 10 rounds (3rd in R5 at 26 vs MiMo/Muse's 27).

## Gemini: lightweight 2-ply with a hard time cutoff

Gemini's 237-line bot uses 1- or 2-ply search depending on time pressure: it always tries 2-ply first, but if a 7.5-second deadline approaches it falls back to 1-ply. Evaluation is `−(5×max_height + 10×holes + 1×bumpiness)`, heavy on holes and modest on height.

Lighter than Claude's setup. Mostly within a couple of pieces of the round winner; tied or ahead in some rounds (R1/R2 tied at the cap, R7 tied with Claude at 38, R9 ahead of Claude 54 vs 51). Won R2, R7, R9; 2nd in five other rounds.

## MiMo: 12-wide beam, same lookahead, harder height penalty

MiMo's 212-line bot is structurally similar to Claude's (beam width 12, 3-piece lookahead) but uses a different evaluation: `−(100×max_height + 50×holes + 10×bumpiness + 5×agg_height + 3×wells)`. Max height is weighted 2× holes, where Claude weights holes ~4× landing height. The relative emphasis on height vs holes is the main difference between the two bots' evaluation functions.

Won R5 (27, tied with Muse, tiebreaker to MiMo). Mostly 3rd in other rounds. 45 points.

## Muse Spark: great early, crashes at the big boards

Muse's 242-line bot, Meta's new entry, runs beam search over 3-piece lookahead, similar in shape to Claude's. It played competitively through R6 (won R6 at 31, tied with Claude and MiMo on the same count, tiebreaker to Muse). At R7 the round ended in timeout for Muse after 33 pieces, with its 10-second cumulative budget running out mid-round. R8/R9/R10 then logged as malformed (no LF / EOF mid-line).

Most likely diagnosis from the source: beam-search work scales with tank area, so on the 14×16+ tanks Muse's per-piece evaluation cost grew enough to exhaust the round's 10s budget without any explicit deadline check. Once the R7 socket state was disturbed by the timeout (the server sends `ROUND_END`), Muse's main loop appears to mis-frame the next `ROUND` line and the connection becomes unrecoverable for the remaining rounds.

30 points, all from the first six rounds.

## DeepSeek V4: heuristic punished by the X-heavy distribution

DeepSeek's 281-line bot, the other new entry, uses recursive 1-ply search with a heuristic that weights holes at ×1000 and bumpiness at ×5. The heavy hole penalty is plausible, but a 1-ply look only sees the current piece's effect; it can't pick the placement that sets up the next X.

Tied or close on the small early boards (R1/R2 at the cap with everyone, R3/R4 just 1 behind), then 4–9 pieces behind from R5 onward (R5 25 vs 27, R10 56 vs 61). Stable across all 10 rounds, no crashes, no timeouts; the implementation is clean. Single-ply planning picks the lowest-hole-count placement *for this piece* but doesn't trade against the next one.

21 points. Cleanly coded; the lookahead depth is the limiting factor.

## The X-pentomino factor

X is the hardest piece in the catalog for this game. The plus shape fills 5 of 9 cells in its 3×3 bounding box, leaving 4 corner cavities: 2 on the bottom row and 2 on the top row. On a flat-ground landing the bottom two cavities are immediately enclosed by the X arms above and become permanent holes; the top two are still accessible from above and may be filled by later pieces. Landing an X without creating any new holes requires terrain whose top profile has a step on each side that fits under both bottom corners, which is uncommon on a busy board. With X at 5/12 of the catalog, every bot's R10 run involved roughly 25 X placements out of ~60 pieces, so small per-X differences in placement quality compound across the round.

The 1-ply bots (DeepSeek, Grok, Nemotron) pick each X to minimize that single piece's hole count and accept whatever terrain results. The 2- and 3-ply bots (Gemini, MiMo, Claude) can sometimes pick a *higher-hole* X placement now if it sets up the next X to land cleanly. The R10 gap of 5 pieces between Claude and DeepSeek (61 vs 56) is small enough that a handful of better X choices per round, each saving 1–2 holes, would account for it.

## Three permanent losers

**ChatGPT (GPT 5.5, 193 lines)** uses `f.readline()` on a socket without timeout management. The `choose_move()` function evaluates every rotation × column with a slow set-based simulation. On round 1 the first PIECE prompt arrives, ChatGPT enters its evaluation loop, the loop takes longer than 10 seconds, server times out, ChatGPT never sends a response. The bot's TCP I/O design effectively guarantees this on any non-trivial board: there is no clock anywhere in the search loop.

**Kimi (K2.6, 253 lines)** and **GLM (5.1, 174 lines)** both have buffer-management bugs in their socket reading. Each plays round 1 cleanly then corrupts internal buffer state and emits malformed responses for the rest. Different code, same failure mode: careless string-handling on TCP framing across line boundaries. The bot reads a full line in round 1, leaves stray bytes in its buffer, then on round 2's prompt those stray bytes prepend to the new data and parsing collapses.

**Nemotron (3 Super, 157 lines)** is the only fully-functional non-top-tier bot that scores low. Its heuristic is too simple (no lookahead, no rotation evaluation beyond rotation 0), and the gap to the round leader grows steadily from 1 piece in R1 to 9 pieces in R10. The bot finishes every round and never crashes, but its evaluation just isn't strong enough to compete.

## The verdict

Claude takes the tournament with 69 points, 11 ahead of Gemini and 24 ahead of MiMo. The three top bots use similar machinery (beam search with Tetris-style evaluation features) and differ mostly in evaluation weights and search depth. Whether Claude's edge is from the 3-piece lookahead, the Dellacherie-style feature set, or the specific weights would take ablation runs to separate; the tournament result alone doesn't tell you which.

Two new entries. **Muse Spark** was competitive through six rounds, then lost R7's round to a budget overrun and R8–R10 to a follow-on protocol bug, ending with 30 points from the first six rounds and none from the rest. **DeepSeek V4** played all ten rounds cleanly but with 1-ply lookahead, which left it 4–9 pieces behind from R5 on. Both were cleanly coded; Muse Spark's ceiling is higher when the bot doesn't crash.

ChatGPT timed out on every round before placing a single piece. The `choose_move()` loop evaluates all rotations × columns with a slow set-based simulation and has no per-piece deadline, so on round 1 it exceeds the 10-second budget and never sends a response. The same loop runs every round; same outcome every round.

---

*Model versions for this challenge: Claude Opus 4.7, Gemini Pro 3.1, MiMo-V2-Pro, Meta Muse Spark, DeepSeek V4, Grok Expert 4.2, GLM 5.1, Kimi K2.6, Nemotron 3 Super, ChatGPT GPT 5.5. Muse Spark and DeepSeek V4 are new at this challenge. The catalog used six one-sided pentominoes weighted X×5, F×2, F'×2, W×1, U×1, T×1, with X dominating the stream at 5/12. Server code, prompts, generated clients, and the full move trace per bot per round live at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
