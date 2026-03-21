# The Growing Word Ladder: Claude won 100 out of 100 rounds.

I gave Claude, Gemini, ChatGPT, and Grok the same prompt and asked each to write a Python 3.10 client for a multi-round "Growing Word Ladder" tournament. Each round, a server sends a start word and a goal word, and the bots must find a path between them. Each step changes, adds, or removes exactly one letter, with every intermediate word in a million-word dictionary. First bot to submit a valid path wins the round. Any bot that fails to submit within five seconds of the winner is eliminated from the tournament.

I ran 100 rounds. Claude won every single one.

## The Results

| Bot | Wins | Survived | Avg Time (ms) |
|---|---|---|---|
| claude_bot | 100 | 100 | 192 |
| grok_bot | 0 | 100 | 269 |
| gemini_3_1_pro_bot | 0 | 100 | 271 |
| gpt5_3_bot | 0 | 100 | 274 |

All four bots survived every round — nobody was eliminated. All four found valid paths of the same length. The only difference was speed. Claude finished first every time, by an average margin of about 75 milliseconds.

## What all four bots got right

Every model chose bidirectional BFS, the textbook algorithm for this problem. Search forward from the start word and backward from the goal word, meet in the middle. This cuts the explored graph from exponential-in-depth to exponential-in-half-depth, which is the difference between seconds and milliseconds.

All four loaded the dictionary into a hash set for O(1) lookups. All four generated neighbors correctly: for each position in the word, try all 26 substitutions, all 26 insertions, and one deletion, keeping only candidates that exist in the dictionary. All four handled the TCP protocol correctly, reading challenges, submitting paths, parsing server responses. No bot was disqualified. No bot crashed. No bot submitted an invalid path.

This is a very different result from the Word Racer tournament, where three of the four models made fundamental errors. Here, every model understood the problem and implemented the correct solution. The competition was purely about implementation speed.

## What separated Claude

Claude's bot made three implementation choices the others didn't.

**Neighbor caching.** Claude's bot maintains a per-round dictionary that maps each word to its list of valid neighbors. When the forward and backward BFS searches both encounter the same word, which happens constantly in bidirectional search, the neighbor list is computed once and reused. The other three bots recompute neighbors from scratch every time a word appears in the search frontier.

```python
_cache = {}

def get_neighbours(word, word_set):
    hit = _cache.get(word)
    if hit is not None:
        return hit
    # ... generate neighbors ...
    _cache[word] = result
    return result
```

On paths of ~290 steps where the bidirectional search meets at depth ~145, this cache prevents thousands of redundant neighbor computations.

**Level-by-level expansion with frontier size heuristic.** Claude's BFS expands an entire frontier level before switching sides, always picking the smaller frontier first. This minimizes total work because the smaller frontier generates fewer neighbors. The other bots either expand one node at a time (Grok) or use the same heuristic but without caching (ChatGPT, Gemini), negating the benefit.

**`frozenset` dictionary and binary I/O.** Claude loads the dictionary as a `frozenset` (immutable, potentially faster hash lookups in CPython) and uses `makefile("rb")` for binary-mode socket reading, avoiding the overhead of Python's text-mode line buffering.

None of these are algorithmic breakthroughs. They're the kind of constant-factor optimizations that a senior engineer would apply after profiling. But in a race decided by milliseconds, constant factors are the only thing that matters.

## Why Grok, Gemini, and ChatGPT were slower

**Grok** alternates between the forward and backward queues one node at a time, popping from the forward queue, expanding, then popping from the backward queue, expanding. This checks for intersection more frequently, after every node rather than after every level, but it doesn't benefit from the smaller-frontier heuristic at the level granularity, and it recomputes neighbors for every word it touches.

**ChatGPT** uses `set` frontiers and expands the smaller side first (the same strategy as Claude), but without neighbor caching. It also loads unused length-bucketed data structures at startup (`BUCKETS = defaultdict(set)`) that add memory pressure without contributing to the solve.

**Gemini** uses a clean `expand_layer` abstraction that expands one full BFS level at a time and checks for intersection. Structurally similar to Claude's approach, but again without caching. Its `makefile("rw")` text-mode socket wrapper adds marginally more overhead per read/write cycle than Claude's binary-mode approach.

The timing data tells the story. Claude averaged 192ms across 100 rounds. The other three averaged 269-274ms, essentially tied with each other, separated from Claude by a consistent 75ms gap. The bottleneck for all three was the same: redundant neighbor generation on words visited by both search directions.

## The Verdict

Four frontier models wrote four correct implementations of the same algorithm. No bugs. No misread specs. No invalid submissions. The only differentiator was performance, and Claude won all 100 rounds by optimizing the constant factors that the other three left on the table.

A neighbor cache, a frontier size heuristic, and a `frozenset`. That's the margin. In a fair race between correct solutions, the one that avoids redundant work wins every time.

---

*The server code, prompt, and all four generated clients are available in the [repository](https://github.com/rrezel/llmcomp). All 100 rounds were conducted on the same machine with all four bots connecting simultaneously to `localhost:7474`. No bot was given the other bots' code or scores between rounds.*
