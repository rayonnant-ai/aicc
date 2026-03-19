# I pitted Claude, Gemini, ChatGPT, and Grok against each other in a real-time coding challenge. Claude won, and it wasn't close.

I wanted to pit four frontier AI models against each other in a perfectly fair and completely objective coding competition — same prompt, same constraints, same ten-second clock. No human review, no subjective grading. Just a TCP server, a dictionary, and a scoreboard.

I designed a "Robot Word Racer" tournament. I gave Claude, Gemini, ChatGPT, and Grok the same prompt and asked each to write a complete Python 3.10 client using only the standard library. The four generated bots then connect simultaneously to a TCP server, receive a 15×15 letter grid, and compete to find and submit valid words before each other. Words must be traced adjacently on the grid (horizontally, vertically, or diagonally). No tile reused per word. Minimum three letters. Scoring is `letters − 6`, so short words cost you points and long ones pay off. The catch: submitting a word that isn't in the dictionary or isn't traceable on the grid results in instant disqualification. The entire round lasts ten seconds.

I ran the server three times with all four bots competing simultaneously. Here's what happened.

## The Results

| Bot | Round 1 | Round 2 | Round 3 | Total |
|---|---|---|---|---|
| ClaudeBot | +258 | +324 | +272 | **+854** |
| GeminiBot | 0 | 0 | 0 | **0** |
| GrokBot | 0 | −1,477 | −43 | **−1,520** |
| ChatGPTBot | −24,283 | −24,025 | −26,075 | **−74,383** |

## ChatGPT: Death by a thousand short words

ChatGPTBot compiled, connected, and received the grid without issue. The code it generated was structurally sound — a proper trie, a proper DFS with backtracking, adjacency validation, deduplication. Every word it submitted was a real dictionary word traceable on the grid. It wasn't disqualified. It did something worse.

```
$ python3.10 wordracerserver.py
[*] Loading dictionary: dictionary.txt...
[*] 15x15 Server Live. Lobby: 30s | Round: 10s
[*] Identified: 'ClaudeBot'
[*] Identified: 'GeminiBot'
[*] Identified: 'ChatGPTBot'
[*] Identified: 'GrokBot'

--- START (NBHLRIIGBTPFVIMZISHZ...) ---

--- END ---

LEADERBOARD:
1. ClaudeBot: 258 pts
2. GeminiBot: 0 pts
3. GrokBot: 0 pts
4. ChatGPTBot: -24,283 pts
```

The prompt states: **Points = (number of letters) − 6.** A seven-letter word scores +1. A six-letter word scores 0. A three-letter word scores −3. ChatGPTBot set `MIN_WORD_LEN = 3` and submitted every valid word it found, starting from length three. On a 15×15 grid backed by a million-word dictionary, there are thousands of valid three-, four-, and five-letter paths. ChatGPTBot found them all and proudly submitted each one for negative points.

The math is straightforward. If the average submitted word was four letters long (scoring −2 each), accumulating −24,283 points requires roughly twelve thousand submissions in ten seconds. The bot's architecture — an asynchronous listener thread decoupled from the solver — actually made this worse. The solver never blocked on server acknowledgments, so it could fire words as fast as DFS could find them. A machine gun of valid, verified, unprofitable words.

A one-line fix would have changed everything: filter submissions to seven letters or longer. The model built the entire pipeline correctly — trie construction, grid traversal, adjacency checking, socket protocol, threading — and then failed to apply the scoring formula it had been explicitly given. It read the rules and did not do the arithmetic. ChatGPTBot ran this same strategy across all three rounds and finished with a cumulative score of −74,383.

## Grok: Same mistake, plus a bottleneck

GrokBot made the same fundamental error as ChatGPT — submitting all words of three letters or longer without filtering for profitability. But its scores across three rounds (0, −1,477, −43) were orders of magnitude less negative than ChatGPT's, and wildly inconsistent. The reason is in the network code.

```
LEADERBOARD:
1. ClaudeBot: 324 pts
2. GeminiBot: 0 pts
3. GrokBot: -1,477 pts
4. ChatGPTBot: -24,025 pts
```

GrokBot sends each word and then immediately calls `sock.recv(2)` to read the server's response before continuing the DFS. This means the solver blocks on every single submission, waiting for a network round-trip before it can resume searching. The DFS, the trie lookup, and the socket write are all serialized into one synchronous loop. Where ChatGPTBot decoupled solving from sending and flooded the server at maximum speed, GrokBot self-throttled by design.

This created an accidental saving grace. The synchronous bottleneck limited throughput to a few hundred submissions per round instead of twelve thousand, which capped the damage from short-word penalties. But it also meant GrokBot could never submit words fast enough to beat ClaudeBot to the high-value long words, even if it found them.

The variance across rounds (0 vs −1,477 vs −43) comes from grid topology. Some grids have denser clusters of short traceable words near the DFS starting cells; others are sparser. GrokBot's score on any given grid was essentially a function of how many three-letter words its DFS happened to encounter before the ten-second clock ran out. It wasn't being tuned between runs. It was just slow enough that the random grid layout determined how much damage it could do to itself.

## Gemini: Correct, slow, and zero to show for it

GeminiBot posted zero points in all three rounds. Not negative — zero. That exact number, three times in a row on three different grids, is revealing. The bot has the same no-length-filter problem as the others (it loads and submits all words down to three letters), but it never got to cash in on that mistake because it never successfully claimed a single word.

GeminiBot uses the same synchronous send-then-wait pattern as GrokBot: submit a word, call `sock.recv(1024)`, wait for the server's `0\n` response, then resume the DFS. But there's a subtlety in the server's scoring that explains the clean zero. The server only modifies a bot's score for *unclaimed* words. If a word has already been claimed by another bot, the submission is silently accepted — no penalty, no points, just `0\n`. GeminiBot wasn't submitting invalid words. It was submitting words that ClaudeBot had already taken.

By the time GeminiBot's synchronous pipeline found, validated, submitted, and waited for acknowledgment on a word, ClaudeBot's three-thread pipeline had already blasted through it. ClaudeBot only submitted seven-letter-and-longer words, but it submitted them in batches of up to thirty, pipelined across solver, sender, and receiver threads with `TCP_NODELAY` set. GeminiBot was sending one word at a time and waiting politely for each response. In a ten-second race, that's not a strategy — it's a courtesy.

## Claude: The only bot that read the scoring formula

ClaudeBot finished first in all three rounds with scores of 258, 324, and 272. No disqualifications.

```
LEADERBOARD:
1. ClaudeBot: 272 pts
2. GeminiBot: 0 pts
3. GrokBot: -43 pts
4. ChatGPTBot: -26,075 pts
```

The single most important line in ClaudeBot's code is `MIN_SUBMIT_LEN = 7`. Every other bot set its minimum to three — the grid minimum, not the scoring minimum. Claude recognized that `points = letters − 6` means words shorter than seven letters are liabilities, and simply refused to submit them. This one decision is the difference between +854 cumulative and −74,383.

Beyond that, the code diverged from the competition architecturally. Instead of a recursive trie, it loaded the dictionary as a sorted list of bytes objects and used `bisect` for prefix pruning — two binary searches per DFS step to narrow a `[lo, hi)` candidate range. Instead of recursive DFS, it ran an iterative DFS with an explicit stack to avoid Python's recursion limit on deep paths. Instead of synchronous send-and-wait, it ran a three-thread pipeline: the solver pushed words to a `PriorityQueue` keyed by negative length (longest words first), a sender thread drained the queue in batches of up to thirty and wrote them in a single `sendall`, and a receiver thread consumed server acknowledgments independently. The socket was configured with `TCP_NODELAY` to disable Nagle's algorithm, and the send buffer was sized at 64KB.

The result was a bot that found long words first, submitted them in bulk without blocking the solver, and never waited for a server response before searching for the next word. Nothing exotic. Just the problem, solved correctly, and, critically, with the scoring formula applied.

## The error every model except Claude made

All three losing bots made the same core mistake: they treated the grid's minimum word length (three letters) as the submission threshold. The prompt said the minimum word length was three. It also said scoring was `letters − 6`. These are two different statements. One defines legality; the other defines profitability. Every model except Claude conflated them.

This is not a subtle reading comprehension failure. The scoring formula was a single line in the prompt: `Points = (number of letters) - 6.` Any model capable of arithmetic should recognize that submitting a three-letter word costs three points. Yet three out of four models set their minimum to three and started fire-hosing. The constraint was explicit. The arithmetic was trivial. They just didn't do it.

The second common failure was architectural. Both Grok and Gemini wrote synchronous clients: submit a word, wait for the server's acknowledgment, then resume solving. In a ten-second race against a pipelined opponent, this is fatal. You cannot discover words while your thread is blocked on `sock.recv()`. Claude's three-thread design — solver, sender, receiver running independently — meant that solving never paused. Words flowed from DFS to priority queue to socket in a continuous pipeline. The other bots solved, stopped, sent, stopped, listened, stopped, and solved again.

## The Verdict

Three of the four frontier models failed a real-time programming challenge where the results are determined by a compiler, a server, and a stopwatch and not a human reviewer deciding whether the output "looks right." ChatGPT posted a cumulative score of −74,383 by submitting thousands of valid words that each cost points. Grok made the same mistake at lower throughput. Gemini avoided negative scores only because it was too slow to claim any words at all, including the short ones that would have cost it points. Only one model produced something that actually worked.

The benchmark is not exotic. Trie-based word search on a 2D grid is a classic interview problem. Streaming data over a TCP socket is covered in first-year networking. The scoring formula was one line of arithmetic. None of this required reasoning about anything novel. It required reading the spec, doing the math, and not submitting three-letter words for −3 points each.

The posts in my feed will keep going up. "I asked AI to build me an app and it worked." Fine. But when the output runs against a referee that doesn't grade on a curve, the results look a little different.

---

*The server code, prompt, and all four generated clients are available in the repository linked below. All runs were conducted on the same machine with all four bots connecting simultaneously to `localhost:7474`. No bot was given the other bots' code or scores between rounds.*