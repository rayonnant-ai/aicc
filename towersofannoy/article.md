# AI coding contest day 9: Towers of Annoy. Gemini ran the table.

The ninth challenge is adversarial Towers of Hanoi. Hero moves a disk; Villain must immediately shove that same disk to an adjacent tower (or pass if no legal move exists). Hero's budget is `2^m + 1` moves (just two more than the `2^m - 1` minimum for solo Hanoi), so almost any wasted move is fatal.

The format is a round-robin with penalty-shootout matchups: up to 5 rounds per matchup (+ sudden death), with 2 simultaneous games per round and hero/villain roles swapped. Round configurations `(n, m)` are `(4, 3)`, `(5, 4)`, `(7, 5)`, `(9, 6)`, `(12, 7)`, giving hero budgets of 9, 17, 33, 65, and 129.

Eight bots were entered; two failed to produce any code. Six competed: 15 matchups, 136 games played.

## The results

| Bot | Won | Lost | Tied | Pts |
|---|---|---|---|---|
| **Gemini (Pro 3.1)** | 5 | 0 | 0 | **15** |
| **Kimi (K2.6)** | 3 | 1 | 1 | **10** |
| **Grok (Expert 4.2)** | 3 | 1 | 1 | **10** |
| **ChatGPT (GPT 5.3)** | 1 | 3 | 1 | **4** |
| **Nemotron (3 Super)** | 0 | 3 | 2 | **2** |
| **GLM (5.1)** | 0 | 4 | 1 | **1** |
| **Claude (Opus 4.7)** | — | — | — | **DNF** |
| **MiMo (V2-Pro)** | — | — | — | **DNF** |

The hero won 36 of 136 games (26%); the villain won 100 (74%). But **70 of 136 games (51%) ended at zero hero moves**, decided by forfeit before any bot made its first move. Most "hero wins" were walkovers against bots that couldn't respond to the server. Gemini was the only bot to win hero games against a functioning villain — six of them.

## Gemini: the only one searching the game tree

Gemini's 283-line bot is the only implementation that searches the adversarial game tree. It runs minimax with alpha-beta pruning, iterative deepening under a 1.8-second per-move clock, and explicit modeling of the villain's restricted move set rather than a generic opponent.

The evaluation function is where the domain shows through: a `+100000` bonus for each disk locked in its final position on the goal tower, a `-50 × w` penalty for blockers sitting on top of disks that want to move, and exponential weights by disk size. Path-set cycle detection keeps the search from looping when the villain mirrors the hero's oscillations; without it, minimax tends to burn its entire budget on repeated positions.

Result: **5 matchups, 5 wins, 0 losses**. As hero, Gemini won 15 of 17 games. As villain, Gemini won 17 of 17 (a 100% block rate). It passed (had no legal villain move available) only 29 times, the lowest of any villain.

The margin against the other responsive bots was stark: Gemini beat Kimi 7-1 and Grok 7-1, each conceding only one game, and beat GPT 6-0. No one else threatened it.

## Kimi and Grok: statistically identical one-ply lookahead

Kimi (K2.6, 334 lines) and Grok (Expert 4.2, 228 lines) implement the same core idea with different code: on each turn, enumerate legal moves, simulate the opponent's best response one ply ahead, pick the move with the best worst-case evaluation. Kimi adds a large bonus (`+5000`) for positions where the villain is forced to pass; Grok uses a narrower distance/burying heuristic.

Their records came out identical: 3 wins, 1 loss, 1 draw, 10 points, 39% hero win rate, 87% villain win rate, 11 real villain wins each. They drew each other 10-10 and each lost only to Gemini. One-ply lookahead is enough to beat the non-responsive bottom half but not enough to solve the Hanoi puzzle itself: **neither bot won a single hero game against a functioning villain**. All their hero "wins" were forfeits against GPT, Nemotron, and GLM.

Kimi passed 68 times as villain; Grok 81; Gemini 29. Pass frequency is partly a villain-skill measurement (manufacturing adjacent-tower blocks that force a pass) and partly a hero-quality measurement, since Gemini's hero play sets up more traps for its opponents. The clearest signal isn't "minimax vs greedy" but depth of search: Gemini is the only bot that looks past the immediate exchange, and that's the variable that tracks the final ordering.

## Three different ways to forfeit everything

**Nemotron (3 Super, 346 lines)** defines a full `make_move()` method with hero and villain strategies, but the main `run()` loop reads server messages and *never calls it*. The bot updates its internal state on every `YOURTURN`, `STATE`, `LAST` message and then loops back to `readline` without sending a response. Result: **29 hero forfeits, 9 villain forfeits, zero moves sent in the entire tournament**. A one-line `self.sock.send(...)` inside the `YOURTURN` handler would have let the bot compete.

**GLM (5.1, 218 lines)** crashes on the very first server message. Its handler reads the `ROUND` command and tries `self.n = int(parts[2]); self.m = int(parts[3])`, but `ROUND {n}` only has two parts. `IndexError`, process dies. GLM's 1 tournament point came from its draw with Nemotron: both bots were non-responsive, so every round split 1-1 on mutual forfeits. The matchup ran the full 10-round cap for 10-10.

**ChatGPT (GPT 5.3, 222 lines)** has a different bug: `elif line.startswith("MATCHUP"): break` exits the main loop on *any* `MATCHUP` message, so GPT disconnects after its first matchup and forfeits the remaining four. GPT's 4 tournament points are entirely from that first matchup (a 6-0 forfeit-win against GLM) plus one draw with Nemotron (again: two broken bots, 10-10 mutual forfeits). GPT's strategy code never gets exercised.

## Claude and MiMo: no code at all

Claude (Opus 4.7) and MiMo (V2-Pro) both failed to produce any code. In Claude's case, the work fragmented across a chain of sessions titled "Architecting bot strategy for adversarial Hanoi tower game", then "Finalizing competitive Towers of Hanoi bot implementation", then "Validating hero strategy robustness across game configurations", each running out of reasoning budget mid-thought and requiring a manual Continue. None of them emitted a finished `claude.py`. MiMo followed the same shape: `mimo.py` ended the day empty.

Both models finished 1st and 3rd on the previous challenge (Day 8, Laden Knight's Tour), so this isn't a capability ceiling; it's a mode failure. The prompt layers round-robin tournament structure, role-swapped simultaneous games, the tight `2^m + 1` budget, and an `OPPONENT`/PASS protocol; apparently enough combinatorial scaffolding to push two reasoning models into open-ended analysis they couldn't close.

## The verdict

The tournament has two separable signals. The first is protocol plumbing — whether a bot can complete the `register → round → turn → move → result` cycle dozens of times without crashing, disconnecting, or deadlocking. Five of eight entries failed that test: three in distinct post-connect ways (never-sends, crash-on-first-message, break-on-MATCHUP) and two before a single socket opened. The second signal is strategy, and there we have little to go on. Gemini is the only bot that searches the game tree; it beat every non-Gemini bot that could respond. That's two matchups of close play.

The challenge-over-challenge arc may be sharper than the matchup data. Day 8 (Laden Knight's Tour) ended Claude 1st, MiMo 3rd, Gemini 2nd. Day 9 is Claude DNF, MiMo DNF, Gemini running the table. At the top of the leaderboard, challenge-to-challenge variance in which model produces working code is currently a bigger effect than challenge-to-challenge variance in which model writes the best code.

---

*Model versions for this challenge: Gemini Pro 3.1, Kimi K2.6, Grok Expert 4.2, ChatGPT GPT 5.3, Nemotron 3 Super, GLM 5.1. Claude Opus 4.7 and MiMo-V2-Pro were entered but failed to produce code and did not connect. Board configurations grew from 4×3 (9 hero moves) up to 12×7 (129 hero moves). All bots connected to `localhost:7474` simultaneously; no bot saw the others' code or scores between rounds. Server code, prompt, and generated clients at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
