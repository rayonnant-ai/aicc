# AI coding contest day 18: CollectTheDots. Every solver was brittle; Grok's heuristic had the fewest cliffs.

The eighteenth challenge is a circle-covering puzzle. Each round the bot gets a `w × h` rectangle and `N` dots at integer coordinates. It must cover every dot with one or more circles, each circle entirely inside the rectangle and no two circles overlapping. **Fewest circles wins.** Trivially, one tiny circle per dot is always valid; the puzzle is to merge dots into shared larger circles without the merged circles colliding with each other or running off the rectangle.

![The 10 round layouts: each rectangle's dots clustered into 5–16 Gaussian groups, with the dimensions and round labels shown.](/media/collect-the-dots/og_image.png)

The format is 10 solo rounds played serially. Rectangles range from `120 × 80` (small, wide) to `220 × 300` (large, tall) with `N = 50` to `N = 100` dots. Server-side dot generation draws integer points around 5 to 16 Gaussian cluster centres with growing standard deviation; the cluster count is the rough latent target the dots are drawn from, but it doesn't directly translate to a minimum-circles bound (some rounds are coverable with fewer circles than there are clusters, others need more — explained below). Per-round ranking is `10/7/5/3/1/0` to ranks 1–6 among valid submissions, with ties on circle count broken by earliest submission timestamp. 30-second wall-clock per round; 10-second registration window.

## The results

| Rank | Bot | Pts | 1sts | Correct | Total t (correct rounds) |
|---|---|---|---|---|---|
| **#1** | **Grok (Expert 4.20)** | **64** | 2 | 10/10 | 12.44 s |
| **#2** | **Kimi (K2.6)** | **63** | 3 | 10/10 | 256.40 s |
| **#3** | **DeepSeek (V4-Pro)** | **60** | 5 | 10/10 | 0.49 s |
| **#4** | **ChatGPT (GPT 5.5)** | 43 | 0 | 10/10 | 13.49 s |
| **#5** | **Claude (Opus 4.7)** | 28 | 0 | 10/10 | 260.00 s |
| **#6** | **MiniMax (M2.7)** | 2 | 0 | 4/10 | 0.15 s |
| #7 | Muse (Spark) | 0 | 0 | 10/10 | 0.43 s |
| #8 | GLM (5.1) | 0 | 0 | 4/10 | 55.21 s |
| DNF | Gemini (Pro 3.1) | — | — | 0/10 | — |
| DNF | Nemotron (3 Super) | — | — | 0/10 | — |

*MiniMax M2.7 debuts this challenge; MiMo (V2.5-Pro) is retired after five consecutive challenge DNFs in generation. Total t is summed only over rounds the bot answered correctly. Per-round timings come from the server's `results.log`, kept local-only by repo policy; the relevant data is inlined in the per-round positions table below and the bot-specific sections that follow.*

## Per-round positions

| Round | w × h | N | k | 1st (circles) | 2nd | 3rd | Min observed |
|---|---|---|---|---|---|---|---|
| R1 | 120 × 80 | 50 | 5 | DeepSeek (2) | ChatGPT (2) | Grok (2) | **2** |
| R2 | 100 × 150 | 60 | 6 | DeepSeek (4) | Grok (4) | Kimi (6) | **4** |
| R3 | 180 × 110 | 70 | 7 | DeepSeek (3) | Grok (4) | ChatGPT (4) | **3** |
| R4 | 130 × 200 | 80 | 8 | DeepSeek (3) | Kimi (3) | Grok (4) | **3** |
| R5 | 240 × 140 | 85 | 9 | Grok (4) | ChatGPT (4) | Kimi (4) | **4** |
| R6 | 160 × 250 | 90 | 10 | DeepSeek (11) | ChatGPT (11) | Kimi (11) | **11** |
| R7 | 270 × 170 | 95 | 11 | Grok (3) | DeepSeek (4) | Kimi (8) | **3** |
| R8 | 190 × 280 | 100 | 12 | Kimi (8) | Grok (11) | ChatGPT (11) | **8** |
| R9 | 290 × 200 | 100 | 14 | Kimi (10) | Grok (11) | ChatGPT (13) | **10** |
| R10 | 220 × 300 | 100 | 16 | Kimi (10) | Claude (10) | Grok (12) | **10** |

`k` is the server-side cluster-centre count used to generate the dots, not a mathematical lower bound on the minimum number of valid circles. The observed minimum is sometimes below `k` (R1: k=5, min=2; R3: k=7, min=3; R7: k=11, min=3) because adjacent server-side clusters whose dots fall close enough can be covered by one larger circle that still fits the rectangle and doesn't overlap other circles. The reverse also happens: when two server-side clusters' minimum enclosing circles would overlap each other, the bot has to split at least one cluster into smaller circles, pushing the observed minimum above `k` (R6, R8, R9 all show this). The relationship between `k` and the round's true optimum is not monotone; it depends on the specific dot placement.

The first-place finishes split roughly by `N`: DeepSeek takes R1–R4 (N=50 to 80) plus R6 (N=90); Grok takes R5 (N=85) and R7 (N=95); Kimi takes R8–R10 (N=100). The split isn't quite clean — DeepSeek wins R6 (N=90, k=10) while losing R5 (N=85, k=9) and R7 (N=95, k=11), and the rounds it loses on don't have an obvious common feature beyond "Grok or Kimi found a smaller cover." But the broad pattern is that DeepSeek dominates while the cluster pattern fits its grid resolution, Kimi takes over when N approaches 100 and the cluster structure needs iterative discovery, and Grok lands in between. Points totals (64, 63, 60) put the three approaches within 4 points of each other.

## Grok: enumerate every pair and every triple, then greedy

Grok (Expert 4.20, 152 lines) takes the most direct approach in the field: build every candidate circle that could plausibly cover a non-trivial subset of dots, then greedy-pick.

```python
def get_circles(points, w, h):
    N = len(points)
    circles = []
    # All pairs (diameter circles)
    for i in range(N):
        for j in range(i + 1, N):
            circ = circle_from_two(points[i], points[j])
            if is_valid_circle(circ, w, h):
                circles.append(circ)
    # All triples (circumcircles, fallback to diameter if collinear)
    for i in range(N):
        for j in range(i + 1, N):
            for k in range(j + 1, N):
                circ = circle_from_three(points[i], points[j], points[k])
                if is_valid_circle(circ, w, h):
                    circles.append(circ)
    # Sort by number of points covered (largest first)
    circles.sort(key=lambda c: -count_points_inside(c, points))
    selected = []
    for circ in circles:
        if not any(circles_overlap(circ, sel) for sel in selected):
            selected.append(circ)
    # Tiny circles for any remaining points
    for p in uncovered(points, selected):
        selected.append(safe_tiny_circle_at(p, w, h, selected))
    return selected
```

For `N = 100`, that's `C(100, 2) + C(100, 3) = 4,950 + 161,700 ≈ 166K` candidate circles enumerated, filtered for rectangle-containment, ranked by coverage, and greedy-selected with overlap checks. Python evaluates that in roughly 1–3 seconds per round, comfortably inside the budget. Grok's per-round times average 1.2 s; the longest is 2.4 s on R9.

Two first-place finishes (R5 at 4 circles, R7 at 3 circles), eight 2nd-to-5th finishes, valid on every round. The points scale (10/7/5/3/1) rewards ranking, not margin of victory, so steady top-5 placement totals more than a few wins plus some bad rounds. 64 points overall.

The triple-circumcircle layer is the structural advantage over a pair-only enumeration. When the minimum enclosing circle of a 3-dot cluster is determined by all three points (rather than the farthest pair), pair-only enumeration produces a strictly larger candidate, which the greedy then can't fit alongside an adjacent cluster's circle. The brute-force enumeration is genuinely a brute-force; the value-add over the next-tier bots is in *which* candidates are in the search space, not in any algorithmic cleverness about how to search through them.

## DeepSeek: grid-search candidate centres, greedy fill

DeepSeek (V4-Pro, 210 lines) takes a different shape: instead of enumerating dot-pair candidates, it builds a fixed grid of candidate centres across the rectangle plus the dot positions, then iteratively places the largest possible non-overlapping circle that covers the most uncovered dots.

```python
candidates = set()
step = max(5, int(min(w, h) // 10))
for gx in range(0, w + 1, step):
    for gy in range(0, h + 1, step):
        candidates.add((float(gx), float(gy)))
for (x, y) in unique_coords:
    candidates.add(clamp_point(x, y, w, h))
for (x, y) in points:
    candidates.add((float(x), float(y)))

while uncovered:
    for cx, cy in candidates:
        rmax = min(cx, w - cx, cy, h - cy)
        for pcx, pcy, pr in placed:
            rmax = min(rmax, math.hypot(cx - pcx, cy - pcy) - pr)
        cov = count_uncovered_in(cx, cy, rmax)
        # track best (cov, rmax)
    placed.append(best_circle)
```

The radius at each candidate is constrained to whichever is smallest: distance to nearest rectangle edge, distance to the nearest *already-placed* circle. So DeepSeek places circles one at a time, each as large as it can be without overlapping anything that already exists. Greedy on coverage count.

DeepSeek's first-half performance is exceptional: instant submission (0.05 s typical) and **5 first-place finishes** on R1–R4 and R6. R5–R7 it stays in the top 5 (1st, 5th, 2nd). On R8 (190 × 280, N=100, k=12) it submits 16 circles — 8 more than Kimi's 8, dropping to 6th place (0 points). R9 and R10 it lands 5th. The article does not run ablations, but two plausible mechanisms for the late-round drop both point at the candidate set: with `step ≈ min(w,h)/10` the grid has roughly 100 candidate centres on R8's 190×280 board, which probably underresolves 12 cluster centres; and the one-pass greedy never reconsiders earlier placements, so a first-pick large circle that splits a cluster awkwardly locks the rest of the layout. A finer grid or a randomized restart pass would be a small change to test.

The trade-off is stark: instant first-half wins, the lowest cumulative correct-rounds time in the field (0.49 s vs Grok's 12 s vs Kimi's 256 s), but no late-round resilience. 60 points, 5 first-place finishes, 3rd overall.

## Kimi: minimum enclosing circles + iterative merge

Kimi (K2.6, 372 lines) is the most engineered bot in the field. It starts with one cluster per unique dot coordinate, computes the minimum enclosing circle (MEC) for each cluster, then iteratively tries pairwise and triple merges:

- For every pair `(i, j)` of current clusters, compute the MEC of the union of their points. If it fits in the rectangle and doesn't overlap any other current cluster's MEC, the merge is feasible.
- Pick the feasible merge that reduces total radius the most.
- Apply it; repeat.
- Triple merges `(i, j, k)` get tried after pairwise saturates.
- Repeat with several random seeds; keep the best result.

Kimi spends essentially the full 25-second budget on this every round (per-round timings of 25.0 s through 26.3 s on all 10 rounds). On R8, R9, R10 — the hardest rounds where DeepSeek's greedy falls apart — Kimi's iterative merging finds the genuinely tight clustering that other bots miss. Kimi wins all three of those rounds outright.

The cost is steep on small rounds. On R1 Kimi finds the 2-circle optimum that DeepSeek, ChatGPT, and Grok also find, but submits at t=25.1 s versus DeepSeek's t=0.02 s. The 10/7/5/3/1 scale is rank-based; identical circle counts go by submission timestamp, and 25 seconds of compute for the same answer drops Kimi from 1st to 4th. Same pattern on R2 (6c, 3rd at 25.3s while DeepSeek wins at 0.05s), R4 (3c, 2nd losing timestamp to DeepSeek), R6 (11c, 3rd losing to two faster bots).

63 points, 3 first-place finishes, 2nd overall. A faster small-N path would have caught Grok for 1st.

## ChatGPT: pairwise agglomerative merging with MEC

ChatGPT (GPT 5.5, 432 lines) uses a different strategy than Grok's enumerate-and-greedy. It starts with one singleton cluster per dot, computes the **minimum enclosing circle** (MEC) for each cluster's point set via randomized incremental MEC (the standard Welzl-style algorithm, with `circle_from_three` for the boundary case), and then iteratively tries pairwise cluster merges: for each pair of current clusters, compute the MEC of the union, and merge if the merged MEC fits the rectangle and doesn't overlap any other cluster's MEC. Repeat until no compatible merge exists. Total correct-round time 13.5 s.

ChatGPT lands 2nd or 3rd on the late rounds (R6, R8, R9, R10) where its agglomerative merging recovers most of the cluster structure. On the small-N rounds it places 3rd or 5th, behind DeepSeek's faster grid-search and Grok's broader candidate set. 43 points overall, 0 first-place finishes.

What ChatGPT does not do is **triple-cluster merging** (try merging three current clusters at once, computing the MEC of their union). Kimi adds that layer; ChatGPT stops at pairwise. Triple merges find groups of three clusters where pairwise merges are individually blocked by overlap with a third cluster's MEC, but a simultaneous three-way merge yields a single circle that does fit. On the hard rounds (R8–R10) this is the main thing separating ChatGPT (11, 13, 12 circles) from Kimi (8, 10, 10). The gap between Grok (64 pts) and ChatGPT (43 pts) is harder to attribute to a single component — the two solvers take fundamentally different shapes (enumerate vs. agglomerate), and Grok's triple-circumcircle candidates are not directly comparable to ChatGPT's pairwise-merge MECs.

## Claude: pair-only with deep local search, full budget every round

Claude (Opus 4.7, 480 lines) is the longest bot in the field and the slowest, spending the full 26-second budget every round. Its solver enumerates pair-diameter circles, computes smallest-enclosing-disks on cluster candidates, then runs local-search refinements (split overlapping circles, merge under-utilized ones, try alternative seedings). Circle counts: `[2, 6, 9, 9, 5, 12, 11, 11, 13, 10]`.

Claude's most interesting result is R10 (220 × 300, N=100, k=16): it finds a 10-circle covering, tying Kimi for the round optimum. Kimi's submission timestamp is 25.6 s, Claude's is 26.0 s — Kimi wins the tiebreak, Claude takes 2nd. The fact that Claude's deep local search hit the same answer as Kimi's iterative-merge search is a small validation: two different algorithms found the same tight cover for the hardest round of the day.

On the small-N rounds Claude lands 4th or 5th: its solver finds *a* valid cover, but the local-search refinement doesn't iterate enough times within the 26-second budget to discover that better candidate circles exist. 28 points, 5th overall.

## MiniMax M2.7 debut: 4 of 10 valid, radius-inflation bug

MiniMax M2.7 (166 lines) is new to the field this challenge. The solver goes 4/10 valid (R1, R2, R5, R8) and INVALID on the other six rounds, all with `out_of_bounds_<i>` reasons.

The bug is on line 42:

```python
r_edge = min(cx, w - cx, cy, h - cy) + EPS    # EPS = 1e-6
```

The maximum radius before hitting a rectangle edge is `min(cx, w-cx, cy, h-cy)`. MiniMax adds `EPS = 1e-6` on top of that, so its circle extends past the edge by exactly 1e-6. The server applies the same `1e-6` tolerance on the other side (`cx - r >= -EPS`), and the two cushions cancel out — so the circle should land exactly at the validation boundary. Float drift then decides whether the check passes or fails on any given dot. For boundary-adjacent dot positions where the math is tight, the `+ EPS` flips the result. Wins zero rounds (its 4 valid submissions land 4th, 5th, 6th, 5th — outside the points zone). 2 points, 6th place.

## The bottom: Muse, GLM, Gemini, Nemotron

**Muse (Spark, 129 lines)** submits valid covers every round but uses essentially the trivial strategy: ~1.1 circles per dot. Round circle counts: 17, 32, 30, 41, 36, 46, 48, 48, 55, 57. Always last among bots that submit, always zero points.

**GLM (5.1, 205 lines)** completes R1–R4 with valid submissions (7, 8, 15, 11 circles), then times out every subsequent round. The solver's complexity grows superlinearly with N, and the 30-second budget runs out for `N ≥ 85`. 0 points despite getting 4 rounds correct (4th–6th place on each).

**Gemini (Pro 3.1, 299 lines)** disconnects on R1 at t=0.096 s; R2–R10 register as immediate EOF (0.001 s) because the socket is already closed. The bot file is a randomized agglomerative solver with what looks like a complete protocol layer; the cause of the R1 exit isn't visible from reading the source alone, and the bot exits on any uncaught exception without stderr (`try/except: sys.exit(1)`) so the in-tournament traceback wasn't captured. 0/10, 0 points.

**Nemotron (3 Super, 72 lines)** has an off-by-one in its `DOT` parser:

```python
# Nemotron's dot parser, line 50–51:
x = float(dparts[1])
y = float(dparts[2])
```

The DOT line format is `DOT <idx> <x> <y>`, so `dparts[1]` is the dot's index and `dparts[2..3]` are the coordinates. Nemotron uses the index as the x coordinate and the actual x as the y coordinate. Every round either fails `out_of_bounds_<i>` (coordinates outside the rectangle because the index is small but treated as a position) or `uncovered_dot_<idx>` (no circle near the real dot positions). 0/10, 0 points.

## What separates the top three from the next tier

The three top solvers differ in their candidate set:

- **DeepSeek**: a fixed grid plus the dot positions. Finds the optimum instantly when the grid aligns with the cluster centres, which is true for the small-N rounds. Loses resolution at N=100 with dots spread over 50,000 px².
- **Grok**: every dot-pair diameter circle and every triple-circumcircle. ~166K candidates at N=100. Always contains the optimal small-cluster circles; the greedy can't backtrack, so on harder rounds it sometimes locks in a suboptimal first pick.
- **Kimi**: the result of iterative merging from one-cluster-per-dot, searched across the merge tree using the full budget and multiple random seeds. Slow but converges on the true cluster structure when N is large.

The hard rounds (R8–R10) need to recover the genuine 12–16 cluster structure from 100 noisy points; only Kimi's iterative merge does that. The easy rounds (R1–R4) just need 2–4 circles around obvious cluster centres, which a fast grid-search nails first. Grok sits in between: pair and triple candidates cover both regimes' optima, and 1–3 second submission times don't lose the timestamp tiebreak to DeepSeek on the small rounds.

ChatGPT (43 pts) and Claude (28 pts) finish off the podium for the same reason: pair-only enumeration. No triple-circumcircles like Grok, no iterative merge like Kimi. The two structural omissions each cost about 20 points across the 10 rounds; ChatGPT's Grok delta and Claude's Kimi delta are both roughly that size.

## The verdict

Every solver in the field had a brittle regime where its heuristic broke down. The differences in points came from how deep each bot's cliff was, not from any solver finding a generally robust approach.

- **DeepSeek's cliff** is at R8: with `step ≈ min(w,h)/10`, the grid candidate set is ~100 centres on the 190×280 board, which underresolves 12 cluster centres. The greedy commits to a large first pick that locks the rest of the layout, and circle count jumps from 4 (R7) to 16 (R8) in one round. Five wins evaporate into a 6th-place 0-pointer at R8; R9 and R10 also drop to 5th. Catastrophic but isolated to the largest-N rounds.
- **Kimi's cliff** is the small-N submission timestamp. On R1–R4 it finds the same circle count as DeepSeek but submits 25 seconds later, losing every tiebreak. A smooth fade rather than a single-round collapse — Kimi still scores 3 to 7 points on the rounds it loses — but it adds up to a 1-point gap behind Grok overall.
- **Grok's cliff is the shallowest**: greedy lock-in on a suboptimal first pick gives a 4th- or 5th-place finish rather than a 1st-place. R6 at 13 circles (vs the leaders' 11) is the worst. Never invalid, never below 5th. The 1–3 second runtime is fast enough to keep timestamp tiebreaks alive on small rounds, and the pair-plus-triple candidate set is broad enough that the greedy has a reasonable pick available even when the optimal first pick is missed.

Below the top three, every other bot's cliff is fatal. ChatGPT (43 pts) and Claude (28 pts) miss the triple-cluster-merge layer on R8–R10, costing 2–3 extra circles on the hardest rounds. MiniMax (2 pts) has a radius-inflation bug that invalidates 6 of 10 submissions. GLM, Gemini, Nemotron, and Muse score zero for different code-level reasons that all bottom out: timeout, disconnect, parser bug, trivial cover.

The points scale rewards rank-occupancy across all 10 rounds. Grok occupied points-scoring ranks more times than any other bot because its brittleness produced 4th- or 5th-place results rather than 6th-or-below. That's the 1-point margin over Kimi and the 4-point margin over DeepSeek: not a deeper algorithm, just a shallower failure mode.

The relationship between the server-side cluster count `k` and the optimum number of circles is not monotone in either direction. Adjacent clusters can sometimes merge into one larger circle (R1, R3, R7 — observed minima below `k`), and they can sometimes force splits (R6, R8, R9 — observed minima above `k`). The bots' rankings sort by how well their candidate sets and search strategies handle both of those decisions, and by how their search strategy degrades when the decision lands outside the regime they're tuned for.

---

*Model versions for this challenge: Claude Opus 4.7, Gemini Pro 3.1, Grok Expert 4.20, ChatGPT GPT 5.5, MiniMax M2.7 (debut, replacing MiMo V2.5-Pro), Nemotron 3 Super, GLM 5.1, Kimi K2.6, Meta Muse Spark, DeepSeek V4-Pro. 10 bots played 10 rounds each; rectangles ranged from 120 × 80 to 290 × 200, dot counts from 50 to 100. 30-second wall-clock per bot per round, 10-second registration window before R1. Bots were generated by sending `prompt.md` to each OpenRouter model in a single chat completion request (no `max_tokens` cap, `temperature=0.2`); five model bots were authored via direct chat. Server code, prompt, generated bots, and the per-round dot placements are at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
