# AI Coding Contest (`llmcomp`)

Frontier LLMs take part in real time programming challenges. Each bot gets the same prompt, connects to the same server, and has seconds to respond. Standard library Python only, no numpy, no PIL. The tasks are narrow enough to have a correct answer and hard enough that getting there isn't obvious.

## Medal Tally

| Challenge | Gold | Silver | Bronze |
|---|---|---|---|
| **1. Noisy Postcodes** | Grok | — | — |
| **2. Word Racer** | Claude | MiMo | — |
| **3. Word Ladder** | Claude | Grok | Gemini |
| **4. Teleportal Maze** | Claude | Grok | — |
| **5. Subway Speedrun** | Claude | Gemini | Nemotron |
| **6. Blurry Image Reveal** | Gemini | Grok | Claude |
| **7. Blobby Tic-Tac-Toe** | Claude | Gemini | ChatGPT |
| **8. Laden Knight's Tour** | Claude | Gemini | MiMo |
| **9. Towers of Annoy** | Gemini | Grok / Kimi (tied) | — |
| **10. Knights of Hanoi** | Claude | Gemini | Kimi |

| Model | Gold | Silver | Bronze |
|---|---|---|---|
| **Claude (Opus 4.6 / 4.7)** | **7** | 0 | **1** |
| **Gemini (Pro 3.1)** | **2** | **4** | **1** |
| **Grok (Expert 4.2)** | **1** | **3** | 0 |
| **MiMo (V2-Pro)** | 0 | **1** | **1** |
| **Kimi (K2.6)** | 0 | **1** | **1** |
| **ChatGPT (GPT 5.3 / 5.5)** | 0 | 0 | **1** |
| **Nemotron (3 Super)** | 0 | 0 | **1** |
| **GLM (5.1)** | 0 | 0 | 0 |

*Postcodes: Grok scored 8/100, all others scored 0 (no silver/bronze). Subway: Gemini and Nemotron tied on 6pts, Gemini took silver (2 round wins vs 0). Maze: Gemini, GPT, MiMo eliminated early (no medal). Blurry Image: GPT, MiMo, Nemotron timed out every round (no medal). Laden Knight's Tour: Grok, ChatGPT, Nemotron all timed out on most rounds (no medal). Towers of Annoy: Grok and Kimi tied on 10 points and share silver; Claude and MiMo DNFed (runaway chain-of-thought, no code produced); GLM and Kimi joined the tournament for this challenge. Knights of Hanoi: Claude and Kimi looped during authoring but were rescued with manual intervention; MiMo DNFed for the second consecutive challenge; GPT upgraded to 5.5 but timed out every round via a 5s-socket-timeout bug on a 10s registration window. Claude used Opus 4.6 for challenges 1–7 and Opus 4.7 for challenges 8+; ChatGPT used GPT 5.3 for challenges 1–9 and GPT 5.5 for challenge 10.*

## Challenges

### 1. Noisy Soviet Postcodes (`noisy_numbers/`)

**Task:** Write a Python 3.10 client that reads six-digit Soviet postal codes from noisy PPM images sent over TCP. Digits are drawn on a 52-dot grid. Images have 5% pixel noise with progressive scaling (±0–10%) and rotation (±0–10°). 100 rounds. Standard library only.

*This is a rerun of the original Day 1 challenge ("sovietpost"), where every model scored zero. In that version, bots were given reference images of the digit glyphs but no structured data — every model invented wrong digit templates because LLMs cannot do spatial reasoning on pixel data. For the rerun, the prompt provides all 52 dot coordinates and stroke sequences as text.*

**Results:**
- **Grok (Expert 4.2):** 8 points (1st). Used dot coordinates to probe the image directly with required-vs-forbidden stroke scoring. Many near-misses with 5/6 digits correct.
- **MiMo (V2-Pro):** 0 points. Pipeline ran but cell segmentation was misaligned.
- **Claude (Opus 4.6):** 0 points. Correct 7-segment digit model, but erosion destroyed all image content. Sent `000000` every round.
- **Gemini (Pro 3.1):** 0 points. Built templates from provided stroke data, but matching always picked digit 8 (most ink). Sent `888888` every round.
- **ChatGPT (GPT 5.3):** 0 points. Eliminated round 1 (I/O timeout).
- **Nemotron (3 Super):** 0 points. Eliminated round 1 (timeout).

For more details on this test, see the [article](noisy_numbers/article.md) and the [prompt](noisy_numbers/prompt.md).

### 2. Word Racer Champion (`wordracerchampion/`)

**Task:** Write a Python 3.10 client that connects to a TCP server, receives a 15×15 letter grid, and races to find and submit valid dictionary words traced adjacently on the grid. Scoring: `letters − 6`. Five bots compete simultaneously in a ten-second round, five rounds total.

**Results:**
- **Claude (Opus 4.6):** Scored +1,251 cumulative, winning all five rounds. Only bot to filter for profitable word lengths (7+), with a pipelined three-thread architecture.
- **MiMo (V2-Pro):** Scored +78 cumulative. Array-based trie with length-sorted output — correct strategy, but batch-then-submit was too slow to beat Claude's streaming pipeline.
- **Gemini (Pro 3.1):** Scored 0 in all five rounds. Too slow to claim any words before Claude.
- **Grok (Expert 4.2):** Scored −2,431 cumulative. Submitted all words including unprofitable short ones, throttled by synchronous I/O.
- **ChatGPT (GPT 5.3):** Scored −118,969 cumulative. Same short-word mistake as Grok but with async I/O, flooding the server with thousands of negative-scoring submissions per round.

For more details on this test, see the [article](wordracerchampion/article.md) and the [prompt](wordracerchampion/prompt.md).

### 3. Growing Word Ladder (`growingwordladder/`)

**Task:** Write a Python 3.10 client for a multi-round word ladder tournament. Each round, the server sends a start word and a goal word. Bots must find a path between them — each step changing, adding, or removing exactly one letter — with all intermediate words in a million-word dictionary. First valid submission wins the round. Bots that fail to submit within 5 seconds of the winner are eliminated. 100 rounds.

**Results:**
- **Claude (Opus 4.6):** Won all 100 rounds (avg 192ms). Bidirectional BFS with neighbor caching, frontier size heuristic, and frozenset dictionary.
- **Grok (Expert 4.2):** Survived all 100 rounds, won 0 (avg 269ms). Correct algorithm but no caching.
- **Gemini (Pro 3.1):** Survived all 100 rounds, won 0 (avg 271ms). Correct algorithm but no caching.
- **ChatGPT (GPT 5.3):** Survived all 100 rounds, won 0 (avg 274ms). Correct algorithm but no caching.

For more details on this test, see the [article](growingwordladder/article.md) and the [prompt](growingwordladder/prompt.md).

### 4. The Amazing Teleportal Maze (`amazed/`)

**Task:** Write a Python 3.10 client to navigate a 2D ASCII maze with teleportals under foggy conditions. No map — bots must explore, remember what they've seen, and find the exit in as few steps as possible. 100 rounds of increasing maze size. Exceeding 500 moves or timing out = elimination.

**Results:**
- **Claude (Opus 4.6):** Won 80 of 100 rounds. BFS exploration biased toward exit corner, immediate portal link resolution from TELEPORT coordinates.
- **Grok (Expert 4.2):** Won 20 of 100 rounds. BFS exploration without directional bias, portal detection by letter matching only.
- **Gemini (Pro 3.1):** Eliminated round 5. Protocol desynchronization on larger mazes.
- **ChatGPT (GPT 5.3):** Eliminated round 8. Move timeout on larger mazes.
- **MiMo (V2-Pro):** Eliminated round 1. `.strip()` destroyed spaces in the 5×5 view.

For more details on this test, see the [article](amazed/article.md) and the [prompt](amazed/prompt.md).

### 5. The Subway Speedrun (`subwayspeedrun/`)

**Task:** Write a Python 3.10 client that solves subway routing optimization: given a network with schedules, transfer hubs, and variable travel times, find the fastest route visiting every station. 10 rounds of increasing difficulty (3-11 lines, 12-119 stations). NP-hard combinatorial optimization with real timetable constraints.

**Results:**
- **Claude (Opus 4.6):** 22 points (1st). Won 8 of 10 rounds with Dijkstra + permutation search + timetable simulation. Failed on 8+ line networks (permutation explosion).
- **Gemini (Pro 3.1):** 6 points (2nd). Won rounds 1-2 with the fastest times, then crashed permanently due to `heapq` tuple comparison bug.
- **Nemotron (3 Super):** 6 points (3rd). Dijkstra with schedule awareness, but couldn't scale past 55 stations.
- **Grok (Expert 4.2):** 4 points (4th). Instant DFS with no schedule modeling. Produced invalid routes on larger networks.
- **ChatGPT (GPT 5.3):** 0 points. Beam search crashed every round — same `heapq` tuple comparison bug as Gemini.
- **MiMo (V2-Pro):** 0 points. Hardcoded wrong transfer stations in every route.

For more details on this test, see the [article](subwayspeedrun/article.md) and the [prompt](subwayspeedrun/prompt.md).

### 6. Blurry Image Reveal (`blurryimagereveal/`)

**Task:** Write a Python 3.10 client that identifies images from progressively deblurred pixel data. Each round, the server sends 10 reference images at full 512×512 resolution, then reveals a mystery image through 8 stages of decreasing Gaussian blur (radius 64 → 0). Guess early for more points (100 at max blur, 1 at sharp). Wrong guess = -10 points. 10 rounds. Standard library only.

**Results:**
- **Gemini (Pro 3.1):** 760 points (1st). 8×8 spatial color fingerprint in 147 lines — the simplest and fastest bot. Scored in 8 of 10 rounds, never guessed wrong.
- **Grok (Expert 4.2):** 260 points (2nd). Multi-resolution MSE matching with conservative confidence thresholds. Only scored in 3 of 10 rounds.
- **Claude (Opus 4.6):** 200 points (3rd). Multi-scale sparse sampling with the most sophisticated matching strategy. Scored in rounds 1-2, then timed out for the rest.
- **ChatGPT (GPT 5.3):** 0 points. Timed out every round (PPM parsing too slow).
- **MiMo (V2-Pro):** 0 points. Timed out every round (box blur simulation too slow).
- **Nemotron (3 Super):** 0 points. Timed out every round (nested list allocation too slow).

For more details on this test, see the [article](blurryimagereveal/article.md) and the [prompt](blurryimagereveal/prompt.md).

### 7. Blobby Tic-Tac-Toe (`blobbytictactoe/`)

**Task:** Write a Python 3.10 client that plays tic-tac-toe on irregular blob-shaped grids against other bots. Round-robin tournament with penalty-shootout matchups: each matchup is up to 5 rounds (+ sudden death), each round is 2 simultaneous games with first-mover swapped. 3 tournament points per matchup win, 1 for a draw. Standard library only.

**Results:**

| Bot | Won | Lost | Tied | Pts |
|---|---|---|---|---|
| **Claude (Opus 4.6)** | 4 | 0 | 1 | **13** |
| **Gemini (Pro 3.1)** | 3 | 0 | 2 | **11** |
| **ChatGPT (GPT 5.3)** | 3 | 1 | 1 | **10** |
| **Nemotron (3 Super)** | 2 | 3 | 0 | **6** |
| **Grok (Expert 4.2)** | 0 | 4 | 1 | **1** |
| **MiMo (V2-Pro)** | 0 | 4 | 1 | **1** |

Top three all used minimax with alpha-beta pruning and iterative deepening. Grok and MiMo timed out repeatedly (69 combined timeouts) due to missing iterative deepening. Nemotron used win-or-block heuristic with random fallback — no search — but still beat the two bots that self-destructed.

For more details on this test, see the [article](blobbytictactoe/article.md) and the [prompt](blobbytictactoe/prompt.md).

### 8. Laden Knight's Tour (`ladenknightstour/`)

**Task:** Write a Python 3.10 client that finds the fastest weighted Knight's Tour on a rectangular board sent over TCP. Every square has a weight; visiting it adds to the knight's load. Each move costs `load` time units (charged on departure), so heavy squares want to be visited last. 10 rounds of increasing board size (3×4 up to 8×8) with heavy-tailed weight distributions. Lowest total time wins; ties broken by submission order. Scoring: 10/7/5/3/1/0 by rank.

**Results:**
- **Claude (Opus 4.7):** 90 points (1st). Won 8 of 10 rounds with a three-phase strategy: Warnsdorff construction, iterated local search, and segment-reversal polish (2-opt for Hamiltonian paths).
- **Gemini (Pro 3.1):** 62 points (2nd). Backwards Warnsdorff placed heavy squares late by construction — competitive on medium boards but lacked a polish step to close the gap on 7×7 and 8×8.
- **MiMo (V2-Pro):** 60 points (3rd). Won rounds 1–2 on submission speed (all top bots tied on cost); fell 8–84% behind Claude from round 3 onward by submitting in milliseconds rather than searching.
- **Grok (Expert 4.2):** 14 points. Solved rounds 1–2, then timed out on all subsequent rounds — no deadline check in the attempt loop.
- **ChatGPT (GPT 5.3):** 1 point. Shipped a suboptimal tour on round 1 before its polish step could execute, then desynchronized from the server protocol and hung every subsequent round.
- **Nemotron (3 Super):** 0 points. Weight-first DFS with a Warnsdorff fallback — the two heuristics fight each other, consuming the budget in dead-end exploration every round.

For more details on this test, see the [article](ladenknightstour/article.md) and the [prompt](ladenknightstour/prompt.md).

### 9. Towers of Annoy (`towersofannoy/`)

**Task:** Write a Python 3.10 client that plays a two-player adversarial variant of the Towers of Hanoi. Hero moves a disk; Villain must immediately move that same disk to an adjacent tower (or pass if no legal move). Hero's budget is `2^m + 1` moves — barely more than the `2^m - 1` solo optimum, so almost any wasted move loses. Round-robin tournament with penalty-shootout matchups: up to 5 rounds (+ sudden death), 2 simultaneous games per round with hero/villain roles swapped. Round configs grow from 4 towers / 3 disks up to 12 towers / 7 disks. First tournament with 8 bots (GLM 5.1 and Kimi K2.6 joining).

**Results:**
- **Gemini (Pro 3.1):** 15 points (1st). Won all 5 matchups undefeated. The only bot to implement adversarial search: minimax with alpha-beta, iterative deepening, and cycle detection. Only bot to win hero games against a functioning villain.
- **Kimi (K2.6):** 10 points (shared 2nd). One-ply lookahead with villain-pass bonus. Beat the non-responsive bottom half but never solved a hero game against a functioning villain; all its hero wins were forfeits.
- **Grok (Expert 4.2):** 10 points (shared 2nd). Identical record to Kimi (3W/1L/1D, 39% hero, 87% villain). Same one-ply lookahead design, different heuristic.
- **ChatGPT (GPT 5.3):** 4 points. Bug: `break` on any `MATCHUP` message exited the main loop after the first matchup, forfeiting the remaining four.
- **Nemotron (3 Super):** 2 points. Defined a full `make_move()` method with hero and villain strategies — but the main loop never called it. Zero moves sent all tournament.
- **GLM (5.1):** 1 point. Crashed on the first server message (`ROUND {n}` only has 2 tokens, but the handler read `parts[2]`/`parts[3]`). Its 1 point came from a 10-10 forfeit draw with Nemotron.
- **Claude (Opus 4.7):** DNF. Work fragmented across multiple `Continue`-required subsessions; `claude.py` ended the day empty.
- **MiMo (V2-Pro):** DNF. Same failure mode; `mimo.py` empty.

51% of all 136 games in the tournament were decided at zero hero moves, forfeit-out before a single move was played. For more details on this test, see the [article](towersofannoy/article.md) and the [prompt](towersofannoy/prompt.md).

### 10. Knights of Hanoi (`knightsofhanoi/`)

**Task:** Write a Python 3.10 client that solves a Towers-of-Hanoi variant on an 8×8 chessboard: `n` disks start stacked on A1, the goal is to move them all to H8, the only legal moves are knight's jumps, and Hanoi placement rules apply on every move. 10 rounds, `n` growing from 3 to 12. Shortest valid solution wins; ties broken by server-receive time. Scoring: 10/7/5/3/1/0 by rank.

**Results:**
- **Claude (Opus 4.7):** 100 points (1st). Won every round, every time at `6n` moves — the theoretical minimum, since any disk's path from A1 to H8 is ≥6 knight moves. Frame-Stewart multi-peg solver with an adaptive peg set (3–8 pegs scaling with `n`), precomputed peg-to-peg knight paths that avoid the other pegs.
- **Gemini (Pro 3.1):** 70 points (2nd). Matched `6n` every round via a beam search (width 100) that plans parking squares for `n−1` disks, then scatters / marches / gathers. Same move count as Claude; always submitted slower.
- **Kimi (K2.6):** 50 points (3rd). One-ply recursive Hanoi with candidate-peg filtering. Scales exponentially against the linear floor — 7340 moves at n=12 (102× the optimum).
- **Grok (Expert 4.2):** 30 points (4th). Recursive divide-and-conquer with per-subproblem row-major parking. 10956 moves at n=12 (152× the optimum).
- **GLM (5.1):** 0 points. Frame-Stewart on a 10-peg set but didn't block the other pegs when expanding knight paths, so move 3 of every round tried to stack disk 3 on disk 1. INVALID every round.
- **Nemotron (3 Super):** 0 points. Two-phase BFS greedy; any unstack or gather failure was swallowed by a broad `except` and sent as an empty newline. INVALID every round.
- **ChatGPT (GPT 5.5):** 0 points. First appearance of the GPT 5.5 upgrade. Bug: `socket.create_connection(..., timeout=5)` set a 5-second socket timeout on a 10-second registration window — the bot raised `socket.timeout` during the idle wait, Python exited, and the server read EOF on every round. TIMEOUT every round.
- **MiMo (V2-Pro):** DNF. Second consecutive DNF via runaway chain-of-thought loop — no `mimo.py` produced. Claude and Kimi also looped during authoring but were rescued with manual intervention.

First challenge in the series where two models independently found the theoretical optimum. For more details on this test, see the [article](knightsofhanoi/article.md) and the [prompt](knightsofhanoi/prompt.md).

