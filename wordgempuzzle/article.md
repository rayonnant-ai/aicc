# AI coding contest day 12: Word Gem Puzzle. Kimi runs the slide loop.

The twelfth challenge: a sliding letter puzzle. Each round both bots receive an identical `w × h` grid containing `w·h − 1` lowercase letter tiles plus one blank slot. Bots can slide tiles into the blank (4-directional) and claim words on their private grid as straight horizontal (across, left-to-right) or vertical (down, top-to-bottom) runs of letter tiles. Crossword and Scrabble orientations only: no diagonals, no reverse. Score per word = `len(word) − 6`, so 7-letter words are worth +1, 9-letter words +3, and short words score negative (3-letter words are −3, 5-letter words are −1). 10-second wall-clock timer per round from the moment the server sends `START`.

The format is a **round-robin of 1v1 matches**. Every pair of registered bots plays one match. Each match is 5 rounds at grid sizes 10×10, 15×15, 20×20, 25×25, 30×30. Starting grids are seeded crossword-style (random dictionary words placed across or down with consistent letter overlaps), letters left over filled from the English Scrabble-tile-bag distribution, then scrambled by sliding the blank in an X pattern across the whole grid (small boards) or four nested X patterns one per quadrant (boards with `max(w,h) ≥ 20`). Both paired bots see the same starting grid; slides only mutate the slider's local copy.

Each unique word in a round can be scored by at most one of the two paired bots. Whichever submits it first gets `OK <points>`, the other gets `TAKEN`. Round winner is the higher round score (ties draw). Match winner is whoever wins more of the 5 rounds. Match win = 3 points, draw = 1, loss = 0. Tiebreak by total round wins, then cumulative round score.

9 bots competed. Nemotron 3 Super has a syntax error in its main loop (`elif line.startswith('TOURNAMENT_END':` is missing a closing paren) so the file never parses; the bot never connected and never joined the round-robin. The field shrank to 9 and the bracket ran C(9,2) = 36 matches × 5 rounds = 180 rounds.

## The results

| Rank | Bot | Match pts | W-D-L | Round wins | Cumulative score |
|---|---|---|---|---|---|
| **#1** | **Kimi (K2.6)** | **22** | 7-1-0 | 20 | 77 |
| **#2** | **MiMo (V2-Pro)** | 20 | 6-2-0 | 18 | 43 |
| **#3** | **ChatGPT (GPT 5.5)** | 16 | 5-1-2 | 13 | 67 |
| **#4** | **GLM (5.1)** | 15 | 5-0-3 | 13 | 34 |
| **#5** | **Claude (Opus 4.7)** | 12 | 4-0-4 | 11 | 24 |
| **#6** | **Gemini (Pro 3.1)** | 9 | 3-0-5 | 11 | 22 |
| **#7** | **Grok (Expert 4.2)** | 9 | 3-0-5 | 9 | 30 |
| **#8** | **DeepSeek (V4)** | 3 | 1-0-7 | 2 | 0 |
| **#9** | **Muse (Spark)** | 0 | 0-0-8 | 0 | −15,309 |

*(Rank by tournament points; tiebreak by round wins, then cumulative score. W-D-L is matches; round-wins is total rounds won across matches; cumulative score is summed `OK <points>` across all 40 rounds the bot played.)*

Kimi takes the tournament with 22 match points, 2 ahead of MiMo. ChatGPT, GLM, Claude, and Gemini fill the middle of the field. Grok scored as many cumulative points as Gemini but won fewer rounds, so it places below on the round-wins tiebreak. The bottom two are runaway: DeepSeek played all 40 rounds without ever sending a valid command and earned its 3 match points entirely from a single match against Muse, while Muse finished at −15,309 cumulative points after submitting hundreds of negative-scoring short words per round.

Per-grid average round score, in points:

| Bot | 10×10 | 15×15 | 20×20 | 25×25 | 30×30 |
|---|---|---|---|---|---|
| Kimi | 0.00 | **0.43** | 0.38 | **2.67** | **3.92** |
| MiMo | 0.00 | 0.00 | 0.62 | 0.75 | 2.00 |
| ChatGPT | 0.00 | 0.12 | **1.86** | 0.38 | 3.12 |
| GLM | **1.33** | 0.12 | 0.29 | 0.12 | 1.86 |
| Claude | 0.00 | 0.00 | 0.43 | 0.67 | 1.00 |
| Gemini | 0.50 | 0.38 | 0.33 | 0.38 | 0.92 |
| Grok | 0.00 | 0.00 | 0.25 | 0.75 | 1.38 |

The 30×30 board is the highest-scoring round of the match for every bot in the top half: it carries the most pre-seeded crossword material, the four-quadrant X scramble breaks the most of it open, and 10 seconds buys enough time to walk a few hundred slide attempts plus the static scan.

## Kimi: greedy slide loop with random-walk fallback

Kimi's 291-line bot is the heaviest active slider in the top tier: 290,914 total `S` commands across the 40 rounds it played, averaging ~7,300 slides per round. The bot loads the dictionary into a length-indexed trie, scans the starting grid for static words and ships them, then enters a slide loop. Each iteration scores all four directions by the value of new positive-scoring words they would unlock on the affected row or column; if any direction has a positive value, take it and repeat. If none does, fall back to a random-walk slide, then re-scan.

The random-walk fallback is the key piece. On a heavily scrambled big-board grid, the greedy 1-step search often returns no productive direction: nearby words are partially formed but no single slide completes one. Kimi takes a "cooling" random slide anyway, accepts that the immediate value is zero, and re-scans. Across enough iterations, the random walk wanders into configurations where the greedy step has new candidates, and the bot picks them up.

Kimi peaks on the biggest two grids: 2.67 average on 25×25 and 3.92 on 30×30. Both are the highest in their column. The match record is 7 wins, 1 draw, 0 losses; the only non-win was a 1-1 draw against MiMo where the rounds split evenly. Kimi led the field in round wins (20 of 40) and in cumulative score (77).

## MiMo: the wire race, and where it stops working

MiMo's 205-line bot has slide logic but never deploys it. It loads the dictionary, filters to words of length ≥ 7 (the minimum that scores a positive `len-6`), and builds a trie indexed by length. Each round it walks every row left-to-right and every column top-to-bottom, descends the trie, and records each terminal it hits. All claims are sorted longest-first, joined into one buffer, and shipped in a single `sock.sendall()`. The socket has `TCP_NODELAY` set, so Nagle doesn't coalesce the buffer; the entire batch hits the server in one TCP segment.

After the static scan, MiMo enters a greedy slide loop capped at 20 iterations, gated by `best_value > 0`. On the seeded-then-scrambled boards the gate never triggers: the loop evaluates four directions on the first iteration, finds no slide that unlocks a positive-scoring word, and bails. Across 40 rounds, 0 `S` commands fire.

That single-write static-scan pattern wins on 20×20 and below by being first to the server's per-round word lock. MiMo's match record is 6 wins, 2 draws, 0 losses. The wins are all by the same shape: MiMo claims a few words on the static grid, the opponent gets `TAKEN` on the same words, and any non-static-grid words the opponent finds via slides aren't enough to flip the round.

Where MiMo stops winning is the 25×25 and 30×30 grids. With more pre-seeded material and bigger four-quadrant X scrambles, the inventory of words Kimi (and ChatGPT, and GLM) can construct via slides exceeds what's traceable on the starting grid. MiMo claims its static finds, the opponent claims those plus a slide-derived stack on top, and the round goes to the slider. MiMo's 30×30 average is 2.00, against Kimi's 3.92.

## ChatGPT: measured slider, peaks on 20×20

ChatGPT's 339-line bot is the most conservative slider in the top half: 4,800 total `S` commands across 40 rounds, ~120 per round. Like Kimi it does a Phase 1 static scan and ships claims, then enters a slide-and-rescan loop, but with much tighter bounds on slide count. The loop uses a deadline-based stop and a per-round slide cap; once either hits, the bot stops and waits for round end.

The conservative slide budget pays best on 20×20, where 120 slides is enough to find a few targets without burning the round-trip budget on noise. ChatGPT averages 1.86 on 20×20, the highest of any bot on that grid. On 30×30 it does 3.12 (second to Kimi's 3.92). On smaller grids the per-round cap leaves ChatGPT with no leverage and it scores near-zero.

5 match wins, 1 draw, 2 losses, 16 match points. Cumulative score 67, second-highest in the field after Kimi.

## GLM: most slides, only top finish on 10×10

GLM's 168-line bot ran 824,855 slides across the tournament, second only to Muse's 461,952 in the broader field but the highest among bots that actually scored points. The strategy is greedy 1-step: each direction is scored by the value of new words it unlocks on the affected row or column, take the best; no random-walk fallback when nothing productive is available, just keep evaluating.

Without the random-walk fallback, GLM gets stuck on big boards. On 25×25 and 30×30, the greedy step often returns zero positive directions and the bot spins through directions without committing to a slide that breaks new ground. GLM's 25×25 average is 0.12. The 30×30 average rebounds to 1.86 because the seeded material is dense enough that some greedy steps still find targets, but it's well below Kimi's 3.92 and ChatGPT's 3.12.

GLM's strongest grid is 10×10 (1.33 average, the highest in that column). On a small scrambled board the greedy 1-step is enough: the search space is small, the slide cost per try is low, and a single productive direction is usually findable. 5 match wins, 0 draws, 3 losses, 15 match points; 4th place on tiebreak after ChatGPT.

## Claude: explicit no-slide, lives on the static scan

Claude's 266-line bot explicitly declines to slide. The file's docstring reads "Read each round's grid; do not slide." It runs a static trie scan over the starting grid, sorts results longest-first, and pipelines them in one batch. Same general shape as MiMo, fewer optimizations on the network side.

The result is a competitive small-and-medium-board score (0.43 on 20×20, 0.67 on 25×25) and a soft 30×30 (1.00, well below Kimi/ChatGPT/MiMo on the same grid). Without slides, the 30×30 round is essentially "claim what the static scan finds, then idle"; the post-scramble grid yields a few seeded words but the slide-derived inventory dominates and Claude can't get to it.

4 match wins, 0 draws, 4 losses, 12 match points.

## Gemini and Grok: middle-of-pack, opposite slide policies

**Gemini (208 lines)** slid 29,291 times across the tournament, mostly on the bigger boards. Its 0.50 average on 10×10 is the second-highest non-zero in that column. It hangs in the field on every grid but never wins one outright in the per-grid averages. 3 wins, 0 draws, 5 losses, 9 match points.

**Grok (146 lines)** does zero slides. The bot file has no `S` command anywhere; it scans the static grid, submits, and waits. Grok's per-grid averages are the lowest of any non-broken bot on every grid above 10×10, but its cumulative score (30) is two ahead of Gemini's because when Grok does score, it scores cleanly with no negative-value claims. 3 wins, 0 draws, 5 losses, 9 match points; loses the tiebreak with Gemini on round wins (9 vs 11).

## DeepSeek: connection-malformed every round, one match win on a forfeit-shape

**DeepSeek (347 lines)** was malformed in every round of the tournament: `actions=0, score=0, elapsed≈0.00s | malformed (no LF / EOF mid-line)` for all 40 of DeepSeek's rounds. The server's per-bot reader returns immediately each round with the connection in EOF-mid-line state, before DeepSeek sends a single command.

DeepSeek's only match win was against Muse: M16 ended 2-0 in DeepSeek's favor. Three of the five rounds were 0-0 draws (Muse self-DQ'd before scoring), and the other two were `deepseek=0, muse=−354` (Muse claimed 152 short words) and `deepseek=0, muse=−987` (Muse claimed 369 short words). When both bots score nothing positive, the bot that scored less negative wins the round; DeepSeek's zero beat Muse's negative every time Muse stayed alive long enough to accumulate one.

3 match points (one match win), 0 draws, 7 losses, 2 round wins, 0 cumulative score.

## Muse: real strategy, claims everything, scores −15,309

Muse's 230-line bot has a complete strategy: trie-based dictionary, scan rows and columns for all words of length ≥ 3, claim them longest-first; then BFS up to 2 slides for 7+ letter setups; then enter a slide-and-rescan loop fishing for 6+ letter words. The bug is in the very first phase. The scan gathers every word of length ≥ 3, including 3-letter (`−3` each) and 4-letter (`−2` each) and 5-letter (`−1` each) words. Phase 1 claims them all without filtering by score.

On a 30×30 grid, the static scan returns hundreds of 3-to-5 letter dictionary words. Muse fires `W <word> <O> <r>,<c>` for each one, gets `OK -3` or `OK -2`, and accumulates a deeply negative round score. On a single 30×30 round Muse can hit −700 or worse before the timer runs out. The 5 round-size averages are −107, −82, −400, −192, −721. Cumulative across 40 rounds: −15,309.

The slide phases would have helped if Muse had survived the claim phase, but they don't run long enough to dig out of the hole the short-word claims dig in the first place. 0 match wins, 0 draws, 8 losses, 0 round wins, last place by a margin of 15,309 cumulative points.

## Slides vs no-slides

The bots that actually slid (Kimi 290K, GLM 824K, ChatGPT 4.8K, Gemini 29K, Muse 461K) split: Kimi 1st, GLM 4th, ChatGPT 3rd, Gemini 6th, Muse 9th. Slide volume alone doesn't predict rank. The bots that emitted zero slides (MiMo, Claude, Grok, DeepSeek) split: MiMo 2nd, Claude 5th, Grok 7th, DeepSeek 8th.

What separates the strategies on this board is whether the slide loop has a fallback for when no greedy step is productive. Kimi has the random-walk fallback and pulls 3.92 average on the biggest grid. GLM doesn't and gets stuck at 1.86 on the same grid despite emitting almost three times as many slides. The ratio of useful slides to total slides matters more than the absolute volume.

The non-sliders work on the small-to-medium grids because the static scan's word inventory is roughly the whole positive-scoring inventory at that size: there isn't much to add via slides. They fall off on 25×25 and 30×30 because the seeded crossword fill plus four-quadrant X scramble yields a large slide-derived inventory that the static scan can't see.

## The verdict

Kimi takes the round-robin on a slide loop that handles "no greedy step available" by taking a random slide and re-evaluating. The fallback is what scales the strategy from "scores well on 25×25" to "dominates 30×30." MiMo is 2 match points back; its single-`sendall` static-scan pattern still wins clean on small grids but loses the big ones to the slider field. ChatGPT's measured slide loop hits its sweet spot on 20×20 and finishes 3rd.

GLM's 824K-slide greedy loop without a random-walk fallback ends up 4th, below ChatGPT's 4.8K-slide measured loop. The lesson is in the small numbers, not the big ones: slide volume is a cost, not a virtue.

Muse's bot is structurally complete but the Phase 1 claim filter is wrong, and that single bug costs it the entire tournament.

---

*Model versions for this challenge: Claude Opus 4.7, GLM 5.1, ChatGPT GPT 5.5, MiMo-V2-Pro, Kimi K2.6, Meta Muse Spark, Gemini Pro 3.1, DeepSeek V4, Grok Expert 4.2, Nemotron 3 Super (DNP, syntax error at startup). 9 bots × C(9,2) = 36 matches × 5 rounds × 10s = 180 rounds. Grid sizes per match: 10×10, 15×15, 20×20, 25×25, 30×30. Letters were sampled from English Scrabble-tile-bag frequency, then arranged as crossword fill (random dictionary words across/down with consistent overlaps) before being scrambled by repeated slides of the blank in X patterns. Dictionary: `words_alpha.txt` (~370K words). Server code, prompts, generated clients, and the full action stream per bot per round are at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
