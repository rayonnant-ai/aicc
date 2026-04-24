# AI coding contest day 8: laden knight's tour. Speed won small, search won big.

The eighth challenge is a weighted variant of the classic knight's tour. The knight must visit every square of a rectangular board exactly once, but each square carries an integer weight. As it moves, the knight accumulates load, and the cost of each move equals its current load. Charge is assessed upon departure, so the weight of the final square never contributes. The algebraic consequence: a square visited at position `i` of an `N`-square tour contributes `weight × (N - i)` to the total cost. Heavy squares want to be late; light squares want to be early.

Six bots played 10 rounds on solvable rectangular boards growing from 3×4 (12 squares) to 8×8 (64 squares). Weights were drawn from a heavy-tailed distribution — 80% uniform in 1–3, 20% uniform in 10–50 — so every board had a handful of expensive squares that the bot needed to push toward the end of its tour. 10-second budget per round, standard library only. Scoring: 10 points for 1st, 7 for 2nd, 5 for 3rd, 3 for 4th, 1 for 5th, 0 for T/O. Ties on tour cost broken by submission order.

## The results

| Bot | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | Points |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Squares | 12 | 20 | 24 | 25 | 30 | 36 | 42 | 49 | 56 | 64 | |
| claude_bot | 175 | 916 | **1632** | **530** | **1419** | **1480** | **1953** | **4967** | **6074** | **7926** | **90** |
| gemini_bot | 175 | 916 | 1632 | 580 | 1545 | 1638 | 2141 | 6661 | 6804 | 8587 | **62** |
| mimo_bot | **175** | **916** | 1762 | 712 | 1907 | 2723 | 2604 | 8881 | 7608 | 10835 | **60** |
| grok_bot | 175 | 916 | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | **14** |
| gpt54_bot | 183 | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | **1** |
| nemotron_bot | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | **0** |

*(Tour cost, lower is better. Bold = round winner. T/O = timeout.)*

On rounds 1 and 2, MiMo, Grok, Claude, and Gemini all submitted the same costs (175 and 916). MiMo won both on the tiebreaker, submitting in 2–7ms. Grok came second, also fast. Claude and Gemini spent 7–10 seconds polishing solutions they already had. GPT submitted a suboptimal 183 on round 1 — its construction phase ran but the polish step did not execute in time — then timed out every subsequent round.

From round 3 onward, the search space outgrows what a single Warnsdorff pass can reliably optimize, and the results diverge.

## The speed-quality crossover

| Round | Squares | Claude | Gemini | MiMo | MiMo vs Claude |
|---|---|---|---|---|---|
| 3 | 24 | 1632 | 1632 | 1762 | +8% |
| 4 | 25 | 530 | 580 | 712 | +34% |
| 5 | 30 | 1419 | 1545 | 1907 | +34% |
| 6 | 36 | 1480 | 1638 | 2723 | +84% |
| 7 | 42 | 1953 | 2141 | 2604 | +33% |
| 8 | 49 | 4967 | 6661 | 8881 | +79% |
| 9 | 56 | 6074 | 6804 | 7608 | +25% |
| 10 | 64 | 7926 | 8587 | 10835 | +37% |

MiMo's speed-first strategy banks 20 points on rounds 1 and 2, then costs it 8–84% in tour quality on every subsequent round. The fast-and-done approach stops paying once the board is large enough that a single Warnsdorff pass no longer reliably finds the best available tour.

## Claude: three-phase search

Claude's bot (369 lines) runs three phases within an 8.5-second budget.

Construction (roughly 15% of budget): multi-start Warnsdorff with both light-first and heavy-first tiebreaks, generating a diverse pool of seed tours to start from.

Iterated local search (roughly 70%): randomized Warnsdorff restarts with random perturbations. Every candidate is scored both forward and reversed, since reversing a valid knight's tour produces another valid knight's tour and flips the position-multiplier of every weight.

Segment-reversal polish (roughly 15%): a 2-opt-style move for Hamiltonian paths. Reversing a contiguous sub-segment of the tour produces a new valid tour if the endpoint squares remain connected by knight moves after reversal. Finding such a reversal that reduces cost, by pushing heavier squares to later positions, is the main source of improvement over construction alone.

Phase 3 is the differentiator. Claude allocated the bulk of its 8.5-second budget to it regardless of board size: overkill on 12 squares, decisive on 49 and above.

## Gemini: backwards Warnsdorff

Gemini's bot (198 lines) inverted the construction: it built the tour in reverse, greedily placing heavy squares first. Since those squares land at the beginning of the backward construction, they end up late in the forward tour, directly targeting the low-cost objective. Randomized restarts within a 9.5-second budget varied backtrack limits and degree noise per attempt.

On medium boards this held up well: round 3, Gemini matched Claude exactly. Round 7, Gemini was within 10%. But on the largest boards the gap opened: on the 7×7 board (round 8), Claude's 4967 beat Gemini's 6661 by 34%. Backwards construction reaches a good tour; post-construction polish reaches a better one.

## MiMo: speed-first

MiMo's bot (124 lines) was the smallest of the three that competed: multi-start Warnsdorff with weight-based tiebreaks, plus a backtracking fallback for boards of 36 squares or fewer. Submit fast and move on.

One latent bug worth noting: MiMo's backtracking timeout relies on a module-level `_bt.t0` attribute that gets set on first use. If `solve()` were called on a small board after a large one, the stale timestamp would disable the timeout check entirely. The tournament never triggered this — backtracking only fires on small boards where it finishes quickly — but the code ships with a silent assumption about call order that would break under different scheduling.

## Grok: no scale

Grok's bot (155 lines) ran deterministic Warnsdorff with a degree-to-weight tiebreaker, trying the 30 lightest starting squares per round. No per-attempt time budget, no adaptation to board size.

It submitted on rounds 1 and 2 (2ms and 1249ms respectively, earning 7+7=14 points on the tiebreaker) and timed out on every subsequent round. The algorithm is fine. The loop runs 30 serial starts with no deadline check, and 30 serial starts on a 24-square board exceed 10 seconds. A single `if time.monotonic() > deadline: break` inside the attempt loop would have let Grok submit on every round.

## GPT: one round, then silence

GPT's bot (201 lines) used Warnsdorff with adaptive tail-swap local search. It submitted on round 1 in 1ms with a cost of 183, while MiMo, Grok, Claude, and Gemini all reached 175. Then it timed out every subsequent round.

Two failures compounded. The first: the 1ms submission came from the raw construction pass before the tail-swap polish could improve it, so GPT shipped its first-draft output rather than a polished tour. The second: after sending its response, the main loop blocks on a `readline` waiting for the server's `VALID/INVALID` acknowledgement, then re-enters the round loop without correctly re-synchronizing on the next `ROUND` header. From round 2 onward the bot is reading the wrong bytes and hangs.

## Nemotron: heuristic at war with itself

Nemotron's bot (166 lines) used iterative DFS with weight-first tiebreaks as the primary heuristic and Warnsdorff as a fallback. The two approaches conflict: Warnsdorff chooses moves by minimum remaining degree, avoiding squares that leave few onward options. Weight-first ignores connectivity entirely. Running weight-first as the primary repeatedly steers the DFS into dead ends, consuming the full 9-second budget without producing a valid tour.

The fix is to use Warnsdorff as the primary tiebreaker and weight as the secondary — breaking degree ties by weight, not substituting weight for degree.

## The verdict

Three of six bots timed out before completing a tour on any round. Grok completed rounds 1 and 2 before timing out; GPT completed only round 1. Of the three that ran to completion:

Claude (90 pts) combined Warnsdorff construction with iterated segment-reversal polish and won every round where optimization mattered.

Gemini (62 pts) found a clever structural insight, building the tour backwards to land heavy squares late, that tracked Claude closely on medium boards but needed a polish step to close the gap on large ones.

MiMo (60 pts) optimized for submission speed and won on the tiebreaker when it mattered, then gave up 8–84% in tour quality for the rest of the contest.

The gap from 1st to 3rd is 30 points. From 3rd to 6th is 60. The bottom half of the table did not lose on algorithm choice. Grok had no deadline check in its attempt loop. GPT desynced on the server protocol after round 1. Nemotron substituted weight for degree as the primary tiebreaker and broke connectivity. The laden knight's tour is not a hard problem if your bot runs to completion.

---

*Model versions used for this challenge: Claude Opus 4.7 (upgraded from Opus 4.6 used in challenges 1–7), Gemini Pro 3.1, Grok Expert 4.2, ChatGPT GPT 5.3, MiMo-V2-Pro, and Nemotron 3 Super. Boards were randomly generated with guaranteed solvability (respecting the known unsolvable dimensions: `m ≤ 2`, `m = 3` with `n ∈ {3, 5, 6}`, and `m = 4` with `n = 4`). Weights were integers drawn from a fixed heavy-tailed distribution. All six bots connected simultaneously to `localhost:7474`. No bot saw the others' code or scores between rounds. Server code, prompts, and generated clients at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
