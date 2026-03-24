# AI Coding Contest Day 5: The Subway Speedrun. Claude stumbled, but won.

The fifth challenge is a combinatorial optimization problem: given a subway network with schedules, transfer hubs, and variable travel times, find the fastest route that visits every station. It's a variant of the Travelling Salesman Problem on a time-dependent graph — NP-hard, no textbook shortcut, real train schedules that constrain when you can move.

Six bots competed across 10 rounds of increasing difficulty, from 3-line/12-station networks up to 11-line/119-station systems.

## The Results

| Bot | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | Points |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude_bot | 157 | 225 | **225** | **422** | **812** | **723** | INV | **921** | INV | **707** | **22** |
| gemini_bot | **142** | **216** | DC | DC | DC | DC | DC | DC | DC | DC | **6** |
| nemotron_bot | 178 | 305 | 313 | 630 | INV | INV | T/O | DC | DC | DC | **6** |
| grok_bot | 249 | 321 | 324 | 715 | INV | INV | INV | INV | INV | 1026 | **4** |
| mimo_bot | INV | INV | INV | INV | INV | INV | INV | INV | INV | INV | **0** |
| gpt54_bot | DC | DC | DC | DC | DC | DC | DC | DC | DC | DC | **0** |

*(Times in minutes. Bold = round winner. DC = disconnected, T/O = timeout, INV = invalid route.)*

Claude led with 22 points but failed two rounds. Gemini won the first two rounds before crashing permanently. Nobody solved rounds 7 and 9 — the hardest networks defeated every bot.

## GPT: The Tuple Comparison Trap

GPT's 426-line bot implemented a beam search with width 160 and 5000 expansions — an ambitious and reasonable strategy. But it crashed on every round with:

```
TypeError: '<' not supported between instances of 'Ride' and 'Ride'
```

The beam search sorts `(score, Ride)` tuples. When two candidates tie on score, Python falls through to compare the `Ride` objects, which have no `__lt__` method. A one-line fix — adding `__lt__` to `Ride` or inserting a unique counter as a tiebreaker — would have let the bot run.

## Gemini: Same Bug, Two Glorious Rounds

Gemini hit the exact same class of bug:

```
TypeError: '<' not supported between instances of 'NoneType' and 'str'
```

Its `heapq.heappush(pq, (t, v, None, None))` breaks when two entries tie on time and station — Python compares `None` against a string. But here's the twist: Gemini's bug was **intermittent**. On rounds 1 and 2, the heap entries happened not to tie, so the bot ran successfully — and **won both rounds**, beating Claude by 15 and 9 minutes respectively. Then on round 3, a tie occurred, and Gemini crashed for the rest of the tournament.

Two models, same fundamental Python error. The `heapq` tuple comparison trap is apparently a blind spot for LLMs — they generate heap-based algorithms readily but forget that Python's tuple comparison falls through to later elements when earlier ones tie.

## MiMo: Wrong Transfers

MiMo submitted a route in every round — no crashes, no timeouts — but every single route was invalid. The error was always the same pattern: "No transfer connection between X and A2." MiMo's bot hardcoded transfers to station A2 regardless of the actual network topology. It never parsed the `transfers` field from the input JSON correctly.

## Grok: No Schedule Awareness

Grok responded in 1-7ms every round — essentially instant. Its 103-line bot uses a DFS that rides each line end-to-end and transfers at hubs. No schedule modeling, no optimization.

This worked for rounds 1-4 (small networks where trains run frequently enough that timing doesn't matter) but produced invalid routes from round 5 onward: "No train available at A5 on line A direction rev after 22:20." The DFS generated routes that required trains after the last departure of the day.

Grok's one valid late-game result was round 10 (1026 minutes) — a 5-line/59-station network where the schedule happened to accommodate its naive traversal. But 1026 minutes vs Claude's 707 minutes shows the cost of ignoring the timetable.

## Nemotron: Good Ideas, Bad Scaling

Nemotron (218 lines) used Dijkstra-based pathfinding with actual schedule awareness — it modeled departure times and the 1-minute transfer buffer. This produced the second-best valid route in round 1 (178min) and stayed competitive through round 4 (630min, second place).

But it couldn't scale:
- **Round 5** (58 stations): "No train available" — the route ran past the last departure.
- **Round 6** (55 stations): same schedule failure.
- **Round 7** (78 stations): timed out at 60 seconds.
- **Round 8 onward**: disconnected.

Nemotron had the right algorithmic approach but didn't handle the edge case where its computed route exceeded the service hours.

## Claude: Best in Class, Still Imperfect

Claude's 910-line bot was the most sophisticated:

1. **Graph construction** with edges weighted by travel time + scheduled wait times.
2. **Dijkstra** for shortest paths between all important stations (terminals, hubs).
3. **Permutation search** over line orderings to find the best traversal strategy.
4. **Full timetable simulation** of each candidate route, including 1-minute transfer buffers.

This produced the best valid routes in every round it completed: 157min (R1), 225min (R3), 812min (R5), 921min (R8), 707min (R10).

But Claude failed two rounds:
- **Round 7** (8 lines, 78 stations): left 64 stations unvisited. The permutation search likely didn't explore enough orderings for 8 lines (8! = 40,320 permutations).
- **Round 9** (11 lines, 119 stations): left 106 stations unvisited. Same problem at 11 lines (11! = 39 million permutations).

When the network exceeded ~7 lines, Claude's approach couldn't enumerate enough permutations within the time limit and fell back to a partial route.

## The Difficulty Wall

| Round | Lines | Stations | Valid solutions |
|---|---|---|---|
| 1 | 3 | 12 | 4 of 6 |
| 2 | 4 | 19 | 4 of 6 |
| 3 | 3 | 18 | 3 of 6 |
| 4 | 5 | 36 | 3 of 6 |
| 5 | 7 | 58 | 1 of 6 (Claude only) |
| 6 | 6 | 55 | 1 of 6 (Claude only) |
| 7 | 8 | 78 | **0 of 6** |
| 8 | 8 | 73 | 1 of 6 (Claude only) |
| 9 | 11 | 119 | **0 of 6** |
| 10 | 5 | 59 | 2 of 6 |

Rounds 7 and 9 had zero valid solutions from any bot. These were genuinely hard instances — 78+ stations across 8-11 lines with tight schedule windows. The subway speedrun hit the wall where even the best LLM-generated code couldn't scale.

## The Verdict

This challenge exposed a hard truth: LLMs can write good optimization code for small instances, but combinatorial explosion defeats them on larger ones. Claude's Dijkstra + permutation approach was the best in the field, but it's fundamentally O(n!) in the number of lines. A human programmer would likely use simulated annealing, genetic algorithms, or branch-and-bound with better pruning — approaches that scale sublinearly.

The other failure mode was more prosaic: two models (GPT and Gemini) were killed by the same Python tuple comparison bug. The `heapq` tiebreaker trap is a known pitfall that LLMs consistently miss. Gemini's case was particularly painful — it had the best algorithm in rounds 1-2 but died from a bug that had nothing to do with the actual problem.

---

*All runs were conducted on the same machine with all six bots connecting simultaneously to `localhost:7474`. No bot was given the other bots' code or scores between rounds. Networks were randomly generated with guaranteed solvability. All server code, prompts, and generated clients are available at [github.com/rrezel/llmcomp](https://github.com/rrezel/llmcomp).*
