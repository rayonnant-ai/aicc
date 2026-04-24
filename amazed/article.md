# AI coding contest day 3: The Amazing Teleportal Maze. Three bots eliminated. Two survived. Claude won.

This is the hardest challenge yet of the AI coding contest. No algorithm textbook has the answer. The bots must navigate a maze they cannot see with no map, no overview, just a 5×5 window of fog around their current position. The maze has teleportals that warp you across the grid, walls that block your path, and an exit in the far corner. Each bot explores blindly, builds a mental map from partial observations, and tries to reach the exit in as few steps as possible. Whoever finishes in the fewest steps wins the round. Take more than 500 steps, and you're eliminated from the tournament.

I gave Claude, Gemini, ChatGPT, Grok, and MiMo the same prompt and ran 100 rounds. Three bots didn't make it past round 8.

## The Results

| Bot | Rounds Won | Survived | Eliminated |
|---|---|---|---|
| claude_bot | 80 | 100 | — |
| grok_bot | 20 | 100 | — |
| gemini_bot | 0 | 4 | Round 5 (connection lost) |
| gpt_bot | 0 | 7 | Round 8 (move timeout) |
| mimo_bot | 0 | 0 | Round 1 (connection lost) |

## MiMo: Dead on arrival

MiMo's bot disconnected before making a single move. The server logged `CONNECTION LOST after step 0`. The code connects, sends the bot name, and then — based on the `sock.settimeout(10)` and the `rd()` function that calls `f.readline().strip()` — it strips trailing whitespace from incoming lines. The 5×5 view contains spaces as passable cells. `.strip()` destroys them. The bot can't parse the view, enters an invalid state, and the connection drops.

One function call. One tournament.

## Gemini: Survived four rounds, then vanished

Gemini's bot handled the first four rounds (tiny 5×5 mazes, 4 steps each) but disconnected in Round 5 when the maze grew larger. The log shows `CONNECTION LOST after step 0` — same symptom as MiMo. Gemini uses `makefile('r')` with `readline()` and strips newlines but not spaces, so the view parsing should work. The more likely cause is a protocol desynchronization: Gemini reads lines in its main loop and dispatches based on content, but if a view line happens to look like a command (e.g., a row starting with certain characters), the parser could misinterpret it and enter an unrecoverable state.

## ChatGPT: Timed out in round 8

ChatGPT lasted seven rounds before being eliminated for exceeding the 1-second move timeout in Round 8. It made three moves, then froze. The bot's code builds a full neighbor graph with portal resolution and runs BFS for pathfinding, which is structurally sound. But its `find_move()` planning logic may have entered a cycle or an expensive computation on a larger maze, blowing the per-move deadline.

## Grok: 29 wins, strong but inconsistent

Grok survived all 100 rounds and won 29 of them. It's the only bot besides Claude that could navigate large mazes with teleportals under fog of war.

Grok's strategy: BFS to the nearest unknown cell (exploration), then BFS to the exit once it's discovered. It handles portals by letter. When it sees two cells with the same uppercase letter in its map, it treats them as a linked pair in pathfinding. This works but has a flaw: the bot only learns a portal's letter from the 5×5 view, not from the `TELEPORT r c` response. If the bot teleports but the destination's 5×5 view doesn't show the partner portal, the link stays incomplete and BFS can't use it.

The step counts tell the story. On small mazes (rounds 1-20), Grok often matches Claude at 4-8 steps. On large mazes, the gap explodes:

| Round | Claude Steps | Grok Steps |
|---|---|---|
| 18 | 6 | 26 |
| 22 | 6 | 43 |
| 43 | 14 | 171 |
| 55 | 88 | 336 |
| 62 | 26 | 194 |

When Grok wins, it's usually a tie-break on a small maze or a round where Claude's exploration gets unlucky. When Claude wins, it often finishes in a fraction of Grok's step count.

## Claude: 80 wins

Claude's bot uses a three-priority decision system:

1. **Exit first.** If the exit (`<`) is visible in the explored map, BFS to it immediately, using known portal links as shortcuts.
2. **Explore frontiers.** BFS outward to find cells adjacent to unknown (`?`) territory, biased toward the bottom-right (where the exit lives). The bias score `len(path) - 0.2 * (r + c)` means the bot prefers frontiers that are both close and in the exit's direction.
3. **Discover portals.** If no good frontier exists, navigate to the nearest unlinked portal letter and step on it to learn where it goes.

The critical difference is portal handling. Claude records portal links from the `TELEPORT r c` response, mapping both directions immediately. This means Claude knows a portal pair after stepping on either end, and its BFS can use both portals as shortcuts in all future pathfinding. Grok only learns portal pairs by spotting matching letters in the 5×5 view, which requires being near both ends.

Claude also biases exploration toward the exit corner. Grok's exploration BFS finds the nearest unknown cell without directional preference, which means it can waste dozens of steps mapping dead-end corridors in the wrong direction.

## The verdict

This challenge separated the models more sharply than any previous one. The first three tournaments tested algorithmic correctness and optimization speed — things that have textbook answers. Maze navigation under fog of war with teleportals has no standard solution. The bot must decide what to explore, when to exploit what it knows, and how to integrate new information from portal discoveries. It's a planning problem, not a search problem.

Three out of five models couldn't even stay connected long enough to compete. Of the two that survived, Claude won 80% of rounds by combining directional exploration bias, immediate portal link resolution, and a clean priority system that switches between exploration and exploitation. Grok survived everything but explored less efficiently, especially on large mazes where the step counts diverged by 5-10×.

---

*All runs were conducted on the same machine with all five bots connecting simultaneously to `localhost:7474`. No bot was given the other bots' code or scores between rounds. All server code, prompts, and generated clients are available at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
