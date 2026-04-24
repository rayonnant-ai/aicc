# Somebody said Xiaomi's MiMo is better than Claude. So I added it to the competition.

After publishing results from the Word Racer and Growing Word Ladder tournaments, someone claimed that Xiaomi's MiMo model would outperform Claude. I wanted to put the claim to the test so I added MiMo to both competitions and reran them. Same prompt, same server, same dictionary, same rules.

MiMo did not win a single round in either tournament.

## Word Racer: 5 rounds, 5 bots

| Bot | Round 1 | Round 2 | Round 3 | Round 4 | Round 5 | Total |
|---|---|---|---|---|---|---|
| ClaudeBot | +378 | +171 | +280 | +254 | +168 | **+1,251** |
| MiMoRacer | 0 | +44 | +27 | 0 | +7 | **+78** |
| GeminiBot | 0 | 0 | 0 | 0 | 0 | **0** |
| GrokBot | −1,421 | −91 | −21 | −876 | −22 | **−2,431** |
| ChatGPTBot | −24,520 | −24,921 | −25,672 | −23,262 | −20,594 | **−118,969** |

MiMo came second. That's genuinely better than Gemini, Grok, and ChatGPT. But "second" in this tournament means scoring +78 to Claude's +1,251 — about 6% of Claude's output across five rounds.

MiMo's Word Racer bot is competent. It builds a proper array-based trie (26-slot children, faster than dict-based tries), runs trie-pruned DFS across the grid, and ,critically, sorts words longest-first before submitting. This is the optimization that ChatGPT and Grok failed to make: by submitting long words first, MiMo claims profitable words before burning through unprofitable short ones. It still submits all words down to length 3 (no profitability filter), but the sort order means it gets a few high-value words claimed before Claude takes the rest.

The problem is timing. MiMo solves the entire grid, collects all words into a list, sorts them, and then starts submitting. Claude's bot streams words to the server as they're discovered during DFS, with a three-thread pipeline and a priority queue that emits longest words first. By the time MiMo finishes solving and sends its first word, Claude has already claimed most of the valuable ones.

## Growing Word Ladder: 100 rounds, 5 bots

| Bot | Wins | Survived | Avg Time (ms) |
|---|---|---|---|
| claude_bot | 99 | 100 | ~224 |
| grok_bot | 1 | 100 | ~316 |
| mimo_bot | 0 | 100 | ~308 |
| gemini_3_1_pro_bot | 0 | 100 | ~313 |
| gpt5_3_bot | 0 | 100 | ~316 |

Claude won 99 of 100 rounds. Grok stole one (Round 70). MiMo won zero.

MiMo's word ladder bot uses bidirectional BFS with node-by-node alternation, the same approach as Grok. It pops one node from the forward queue, expands it, then pops one from the backward queue, expands it. No neighbor caching. No frontier size heuristic. Standard `set` dictionary.

The result: MiMo lands squarely in the pack with Grok, Gemini, and ChatGPT, all clustered between 260-370ms per round. Claude finishes in 170-260ms, winning by 70-100ms every time. The gap is the same one identified in the original tournament: neighbor caching and level-by-level frontier expansion.

MiMo's one distinction in this tournament is that it occasionally edges out Grok or Gemini for second place on individual rounds. But "fastest loser" doesn't score points.

## The verdict

MiMo produced correct, working code for both challenges, which already puts it ahead of ChatGPT (−118,969 cumulative in Word Racer) and Grok (−2,431). Its Word Racer bot shows real design sense: array-based trie, length-sorted output, clean threading. It's a solid second-tier result.

But "better than Claude" it is not. In Word Racer, Claude outscored MiMo 16 to 1. In Word Ladder, Claude won 99 rounds to MiMo's zero. The claim doesn't survive rigorous testing.

---

*All runs were conducted on the same machine with all five bots connecting simultaneously to `localhost:7474`. No bot was given the other bots' code or scores between rounds. MiMo was given the exact same prompt as the other four models. All server code, prompts, and generated clients are available at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
