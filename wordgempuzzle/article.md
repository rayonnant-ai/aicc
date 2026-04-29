# AI coding contest day 12: Word Gem Puzzle. Kimi runs the slide loop.

The twelfth challenge: a sliding letter puzzle. Each round both bots receive an identical `w × h` grid containing `w·h − 1` lowercase letter tiles plus one blank slot. Bots can slide tiles into the blank (4-directional) and claim words on their private grid as straight horizontal (across, left-to-right) or vertical (down, top-to-bottom) runs of letter tiles. Crossword and Scrabble orientations only: no diagonals, no reverse. Score per word = `len(word) − 6`, so 7-letter words are worth +1, 9-letter words +3, and short words score negative (3-letter words are −3, 5-letter words are −1). 10-second wall-clock timer per round from the moment the server sends `START`.

The format is a round-robin of 1v1 matches. Every pair of registered bots plays one match. Each match is 5 rounds at grid sizes 10×10, 15×15, 20×20, 25×25, 30×30. Starting grids are seeded crossword-style (random dictionary words placed across or down with consistent letter overlaps), letters left over filled from the English Scrabble-tile-bag distribution, then scrambled by sliding the blank in an X pattern across the whole grid (small boards) or four nested X patterns one per quadrant (boards with `max(w,h) ≥ 20`). Both paired bots see the same starting grid; slides only mutate the slider's local copy.

Each unique word in a round can be scored by at most one of the two paired bots. Whichever submits it first gets `OK <points>`, the other gets `TAKEN`. Round winner is the higher round score (ties draw). Match winner is whoever wins more of the 5 rounds. Match win = 3 points, draw = 1, loss = 0. Tiebreak by total round wins, then cumulative round score.

10 bot scripts were launched. Nemotron 3 Super has a syntax error in its main loop (`elif line.startswith('TOURNAMENT_END':` is missing a closing paren), so the file never parses and the bot never connects. The remaining 9 bots ran the full bracket: C(9,2) = 36 matches × 5 rounds = 180 rounds.

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

*(Rank by tournament points; tiebreak by round wins, then cumulative score. W-D-L is matches; round-wins is total rounds won across matches; cumulative score is summed `OK <points>` across all 40 rounds the bot played. Match-result lines from the server like "2-0" report round wins to round wins; draws are not part of that pair.)*

Kimi takes the tournament with 22 match points, 2 ahead of MiMo. Grok and Gemini are tied at 9 match points; Grok scores more cumulative points (30 vs 22) but loses the tiebreak on round wins (9 vs 11). DeepSeek's 3 match points are entirely a single match win against Muse (M16 ended 2 round wins to 0 with 3 draws); DeepSeek never sent a valid command in any of its 40 rounds. Muse is last by a 15,309-point margin after a Phase 1 claim filter that submits every dictionary word of length ≥ 3, including the negative-scoring 3- to 5-letter words.

Per-grid average round score, in points (each bot played 8 rounds at each grid size):

| Bot | 10×10 | 15×15 | 20×20 | 25×25 | 30×30 |
|---|---|---|---|---|---|
| Kimi | 0.00 | 0.75 | 0.12 | **2.88** | **5.88** |
| MiMo | 0.00 | 0.62 | **0.75** | 1.00 | 3.00 |
| ChatGPT | 0.00 | **1.75** | 0.38 | 0.88 | 5.38 |
| GLM | **0.50** | 0.25 | 0.25 | 0.38 | 2.88 |
| Claude | 0.00 | 0.38 | 0.25 | **1.38** | 1.00 |
| Gemini | 0.38 | 0.50 | 0.12 | 0.62 | 1.12 |
| Grok | 0.00 | 0.25 | **0.75** | 0.75 | 2.00 |

The 10×10 column is mostly zero: GLM averages 0.50 and Gemini 0.38, every other bot averages 0.00. After the X scramble cycles the blank through all four corners and back, a 10×10 board carries almost no intact 6+ letter dictionary words, and slides inside 10 seconds rarely reconstruct one. Most of the points in the tournament come from 30×30, the highest-scoring column for 5 of the 7 scoring bots. The single column that has a clear non-Kimi leader is 15×15, where ChatGPT averages 1.75, more than twice Kimi's 0.75 on the same grid.

## Kimi: greedy slide loop, alphabetical fallback

Kimi's 291-line bot is the heaviest active slider in the top tier: 290,914 total `S` commands across the 40 rounds it played, ~7,300 slides per round on average. The bot loads the dictionary into a length-indexed trie, scans the starting grid for static words and ships them, then enters a slide loop. Each iteration scores all four directions by the value of new positive-scoring words they would unlock on the affected row or column; if any direction has positive value, take it. If none does, take the first legal direction in `("U", "D", "L", "R")` order to keep the grid mutating.

The alphabetical fallback keeps the bot productive enough on the bigger grids to find a few extra words after the static-scan inventory is exhausted, but it has a clear failure mode: against any board edge, it degenerates into a deterministic 2-cycle. From row 0 the fallback picks `D` (because `U` is off-board), then from row 1 it picks `U` (back to row 0), then `D` again. M05 R5 vs MiMo is the cleanest example: Kimi claims its 3 words by frame 8, runs out of productive slides at row 0 of column 22, and burns the remaining ~2,000 slides ping-ponging between rows 0 and 1 of that column, finding nothing new. The 2,049 total actions for that round are mostly noise.

Kimi's per-grid pattern: 0.00 on 10×10, low single-digits on 15×15 and 20×20, then 2.88 on 25×25 and 5.88 on 30×30. The bigger the grid the more pre-seeded material the scramble breaks open, and the more productive slide attempts pay back before the loop saturates against an edge. Match record 7-1-0; the single non-win was a 1-1 draw against MiMo (3 of 5 rounds drawn, the deciding rounds split). Kimi led the field in round wins (20 of 40) and cumulative score (77).

## MiMo: static scan in one TCP segment, no slides

MiMo's 205-line bot has slide logic but never deploys it. It loads the dictionary, filters to length ≥ 7 (the minimum for a positive `len-6`), and builds a trie indexed by length. Each round it walks every row left-to-right and every column top-to-bottom, descends the trie, records each terminal hit, sorts longest-first, joins claims into one buffer, and ships them in a single `sock.sendall()`. The socket has `TCP_NODELAY` set, so Nagle doesn't coalesce the buffer; the entire batch lands in one TCP segment.

After the static scan, MiMo enters a greedy slide loop capped at 20 iterations and gated by `best_value > 0`. On the seeded-then-scrambled boards the gate never triggers: the loop evaluates four directions on the first iteration, finds no slide that unlocks a positive-scoring word, and bails. Across 40 rounds, 0 `S` commands fire.

The match record is 6-2-0: six wins (over GLM, Grok, Claude, Gemini, Muse, DeepSeek), two draws (vs Kimi 1-1, vs ChatGPT 2-2), no losses. MiMo never beats the heavy sliders but never loses to them either. Its consistency is what gets it to 2nd: 18 round wins and a flat per-grid profile that scores something on every grid 15×15 and up.

## ChatGPT: tight slide loop, 15×15 outlier

ChatGPT's 339-line bot is the most conservative slider in the scoring half: 4,800 total `S` commands across 40 rounds, ~120 per round. Like Kimi it does a Phase 1 static scan and ships claims, then enters a slide-and-rescan loop bounded by a per-round slide cap and a deadline.

ChatGPT's per-grid distribution is unusual: the strongest grid is 30×30 (5.38, second only to Kimi's 5.88), but the second-strongest is **15×15 at 1.75**, more than twice the next bot's 15×15 average. On the smaller grids the static scan is finishing very fast and the few slides it has time for are placed well; on 30×30 the cap is small enough that ChatGPT isn't burning round-trips on noise but big enough to find some targets. 5 match wins, 1 draw (M13 vs MiMo, 2-2), 2 losses (to Kimi and Grok), 16 match points; cumulative score 67, second-highest after Kimi.

## GLM: most slides among scoring bots, peak on 30×30

GLM's 168-line bot fired 824,855 slides, the highest count among bots that scored points (Muse fired 461,952 but they were almost all unproductive). The strategy is greedy 1-step with no random-walk fallback: each direction is scored by the value of positive words it would unlock, take the best, repeat; if none has positive value, rescan and try again.

Without the fallback, GLM stalls when the greedy step goes flat. The pattern shows up in the per-grid line: 0.50 on 10×10 (the highest in that column), then a flat 0.25-0.38 across 15×15, 20×20, 25×25, then a single peak at 30×30 (2.88). On 30×30 the seeded material is dense enough that some greedy steps still find targets; on the middle grids the loop runs out of productive slides and the bot mostly burns its budget on negative-value steps it doesn't take.

5 match wins, 0 draws, 3 losses, 15 match points. Cumulative score 34.

## Claude: explicit no-slide, peaks on 25×25

Claude's 266-line bot explicitly declines to slide. The file's docstring reads "Read each round's grid; do not slide." It runs a static trie scan over the starting grid, sorts results longest-first, and pipelines them in one batch.

Claude is the only top-half bot whose strongest grid is **25×25 (1.38)** rather than 30×30 (1.00). The 25×25 scramble (still using the four-quadrant X pattern at `max ≥ 20`) leaves enough intact pre-seeded words that a static scan finds them; the 30×30 scramble breaks more of them, and without slides Claude can't reconstruct what's broken. 4 match wins, 0 draws, 4 losses, 12 match points.

## Gemini and Grok

**Gemini (208 lines)** slid 29,291 times, mostly on bigger grids. Per-grid averages are flat (0.12 to 1.12), no clear peak. 3 wins, 0 draws, 5 losses, 9 match points.

**Grok (146 lines)** does zero slides; the bot file has no `S` command anywhere. Despite that, its 30×30 average (2.00) is the fifth-highest in the field, behind Kimi (5.88), ChatGPT (5.38), MiMo (3.00), and GLM (2.88). On 20×20, Grok ties MiMo for the column lead at 0.75. The static-only strategy holds up surprisingly well on the bigger grids when the seeded crossword material is dense enough to find. Cumulative score 30, ahead of Gemini's 22; loses the tiebreak with Gemini on round wins (9 vs 11). 3 wins, 0 draws, 5 losses, 9 match points.

## DeepSeek: malformed every round

DeepSeek (347 lines) was logged as `actions=0, score=0, elapsed≈0.00s | malformed (no LF / EOF mid-line)` in all 40 of its rounds. The server's per-bot reader returns immediately each round with the connection in EOF-mid-line state, before DeepSeek sends a single command.

DeepSeek's only match win was M16 vs Muse, which ended 2 round wins to 0 with 3 draws. Three of the five rounds were 0-0 draws (Muse self-DQ'd before scoring); the other two were `deepseek=0, muse=−354` and `deepseek=0, muse=−987`. When both bots score nothing positive, the bot that scored less negative wins the round, and DeepSeek's zero beat Muse's negative the two rounds Muse stayed alive long enough to claim short words. 3 match points, 2 round wins, 0 cumulative score, last among bots with a positive cumulative.

## Muse: complete strategy, broken claim filter

Muse's 230-line bot has a structurally complete strategy: trie-based dictionary, scan rows and columns for all words of length ≥ 3, claim them longest-first; then BFS up to 2 slides for 7+ letter setups; then enter a slide-and-rescan loop fishing for 6+ letter words. The bug is in the very first step. The scan gathers every word of length ≥ 3, including 3-letter (`-3` each), 4-letter (`-2`), and 5-letter (`-1`) words. Phase 1 claims them all without filtering by score.

On a 30×30 grid the static scan returns hundreds of dictionary words in the 3-to-5 letter range. Muse fires `W <word>` for each one and accepts `OK -3` or `OK -2`. Per-grid round averages: −78.12 (10×10), −192.12 (15×15), −347.75 (20×20), −529.38 (25×25), −766.25 (30×30). Cumulative across 40 rounds: −15,309. The slide phases never get to contribute meaningfully because Phase 1 burns too much of the round on negative-scoring claims.

## Slides vs no-slides

The two extremes: Kimi (1st, 290,914 slides) and MiMo (2nd, 0 slides). Slide volume alone doesn't predict rank. The 5th-place finisher Claude also fires 0 slides; the 4th-place GLM fires 824,855. Among the top 7 scoring bots, four ran a slide loop (Kimi 1st, ChatGPT 3rd, GLM 4th, Gemini 6th) and three didn't (MiMo 2nd, Claude 5th, Grok 7th). Sliders don't dominate non-sliders or vice versa; the table interleaves them. What separates the sliders from each other is how their loop behaves when no greedy step has positive value: Kimi takes the alphabetically-first legal direction (which 2-cycles against any edge), GLM rescans the same configuration and stalls, ChatGPT stops early on a tight cap, Gemini sits in between.

The non-slider strategies score reliably on the grids where the seeded crossword fill survives the scramble (10×10 has very little to find for anyone; 15×15 to 25×25 retain enough for a static scan to score). On 30×30 the four-quadrant X scramble breaks more of the inventory, and the gap between sliders and non-sliders opens: Kimi and ChatGPT both clear 5.0 average on 30×30; MiMo at 3.00 is the strongest non-slider; Claude at 1.00 is the weakest top-half bot on that grid.

## The verdict: Kimi won because every other bot was worse

Kimi takes the round-robin on 30×30 dominance: 5.88 average on 30×30, 47 of its 77 cumulative points from the largest grid alone. The bot is not good. Most of its 290,914 slides are wasted oscillating against board edges after the few productive greedy steps run out. M05 R5 vs MiMo is representative: Kimi claims 3 words (cinerous, sheafed, onionet) for +4 in the first ~50ms, then ping-pongs SD/SU across rows 0 and 1 of column 22 for the remaining ~9.95 seconds, finding nothing. 2,049 actions for 3 OKs.

Kimi wins because every other bot is worse:

- **MiMo (#2)** has slide logic but its `best_value > 0` gate never fires across 40 rounds, so the bot is effectively a static-scan-only client on a sliding-puzzle game.
- **ChatGPT (#3)** caps slides tightly enough to avoid thrash but never plans toward a target word configuration; it's a measured version of the same greedy 1-step.
- **GLM (#4)** has no fallback at all, so when the greedy step goes flat its slide loop becomes a no-op that re-evaluates the same four directions repeatedly without committing to anything productive.
- **Claude (#5)** explicitly declines to slide. The bot's docstring reads "Read each round's grid; do not slide" on a sliding-puzzle challenge.
- **Gemini (#6)** slides 29K times spread across all grid sizes with no clear peak, no targeted strategy.
- **Grok (#7)**'s 146-line bot has no `S` command anywhere in the source. The bot ignores the central mechanic of the game entirely.
- **DeepSeek (#8)** sends malformed bytes on every round and never executes a single valid command across 40 rounds.
- **Muse (#9)** has a structurally complete strategy that fails on the most basic filter (claim length ≥ 3 instead of length ≥ 7), submits hundreds of −3 short words per round, and finishes at −15,309.
- **Nemotron** has a syntax error in its main loop and never connects.

Common gaps across the field: only Muse runs a search deeper than 1-step (a 2-slide BFS for 7+ letter setups, but its overall round score is dragged below zero by the broken Phase 1 filter). Nobody runs anything deeper. Nobody detects when the slide loop has degenerated into an edge-cycle and breaks out. Only MiMo and a couple of others filter their dictionary to length ≥ 7 at load time; Muse claims everything ≥ 3 letters and pays the price.

All the strategies are weak. Kimi's bad strategy fails least catastrophically on 30×30 because its alphabetical fallback at least keeps mutating the grid in a region where mutation occasionally lands on a word; the others either mutate badly (GLM stalls, Gemini drifts), refuse to mutate at all (MiMo, Claude, Grok), or mutate while submitting trash (Muse). Strategy does differentiate the bots; what's notable is that none of the differentiating strategies are designed for the puzzle. They're all the first thing an LLM produced for a sliding-puzzle prompt, and none of those first attempts thought past 1-step search.

---

*Model versions for this challenge: Claude Opus 4.7, GLM 5.1, ChatGPT GPT 5.5, MiMo-V2-Pro, Kimi K2.6, Meta Muse Spark, Gemini Pro 3.1, DeepSeek V4, Grok Expert 4.2, Nemotron 3 Super (DNP, syntax error at startup). 9 bots × C(9,2) = 36 matches × 5 rounds × 10s = 180 rounds. Grid sizes per match: 10×10, 15×15, 20×20, 25×25, 30×30. Letters were sampled from English Scrabble-tile-bag frequency, then arranged as crossword fill (random dictionary words across/down with consistent overlaps) before being scrambled by repeated slides of the blank in X patterns. Dictionary: `words_alpha.txt` (~370K words). Server code, prompts, generated clients, and the full action stream per bot per round are at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
