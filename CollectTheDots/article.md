# AI coding contest day 18: CollectTheDots. Three different solvers split the field by round size.

The eighteenth challenge is a circle-covering puzzle. Each round the bot gets a `w × h` rectangle and `N` dots at integer coordinates. It must cover every dot with one or more circles, each circle entirely inside the rectangle and no two circles overlapping. **Fewest circles wins.** Trivially, one tiny circle per dot is always valid; the puzzle is to merge dots into shared larger circles without the merged circles colliding with each other or running off the rectangle.

![The 10 round layouts: each rectangle's dots clustered into 5–16 Gaussian groups, with the dimensions and round labels shown.](/media/collect-the-dots/og_image.png)

The format is 10 solo rounds played serially. Rectangles range from `120 × 80` (small, wide) to `220 × 300` (large, tall) with `N = 50` to `N = 100` dots. Server-side dot generation draws integer points around 5 to 16 Gaussian cluster centres with growing standard deviation; the cluster count gives the lower bound a perfect-clusterer could reach. Per-round ranking is `10/7/5/3/1/0` to ranks 1–6 among valid submissions, with ties on circle count broken by earliest submission timestamp. 30-second wall-clock per round; 10-second registration window.

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

`k` is the server-side cluster count (the lower bound a perfect clusterer could reach). The minimum observed circle count tracks `k` only loosely; on most rounds even the best bot ends up using more circles than there are clusters, because two adjacent clusters' minimum enclosing circles often overlap and force a split into a third circle.

The standings tell a clear story: **DeepSeek owns R1–R4 and R6** (the small-N rounds where instant submission carries the day), **Grok wins R5 and R7** (mid-N rounds where finding a tight 3- or 4-dot circle matters), and **Kimi wins R8, R9, R10** (the largest N where finding the genuine 12–16 cluster structure beats everything else). Three solvers, three regimes; the totals are within 4 points of each other.

## Grok: enumerate every pair and every triple, then greedy

Grok (Expert 4.20, 152 lines) takes the most direct approach in the field: build *every* candidate circle that could plausibly cover a non-trivial subset of dots, then greedy-pick.

```python
def get_circles(points, w, h):
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

Grok wins R5 (4 circles) and R7 (3 circles) outright. Its real value is consistency: 2nd or 3rd on every other round, never below 4th when valid, and valid on every submission. That's how 2 first-place finishes become 64 points: ten high-rank finishes outweigh a 5-wins-then-collapses arc.

The triple-circumcircle layer is the key over a pair-only enumeration. Three-dot clusters where the minimum enclosing circle is determined by all three (not by the farthest pair) appear in 7 of the 10 rounds, and Grok's enumeration captures them; bots that only try pairs miss the optimal candidate and use one more circle to cover the third dot.

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

DeepSeek's first-half performance is exceptional: instant submission (0.05 s typical) and **5 first-place finishes** on R1–R4 and R6. R5–R7 it stays in the top 5 (1st, 5th, 2nd). Then on R8 (190 × 280, N=100, k=12) it submits 16 circles — 8 more than Kimi's 8, dropping to 6th place (0 points). R9 and R10 it lands 5th. The collapse isn't a code bug; it's that the greedy candidate set, with a `step ≈ min(w,h)/10` grid, doesn't have enough resolution to find the tight clusters on the larger rectangles where dots are spread over 50,000 px² with 12–16 clusters. The first big circle the greedy picks is often suboptimal for the rest of the dot layout.

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

## ChatGPT: pair-only enumeration

ChatGPT (GPT 5.5, 432 lines) is the most balanced bot among those with no first-place finishes. It enumerates pair-diameter circles only (no triples), greedy-selects with overlap checks, and uses smallest-enclosing-disk computation for clusters formed by the greedy. Total correct-round time 13.5 s, similar to Grok.

ChatGPT lands 2nd or 3rd on the late rounds (R6, R8, R9, R10) where pair-only enumeration is enough because the tight clusters are dominated by their farthest-pair diameter. On the small-N rounds where Grok's triple-circles find a smaller circle than ChatGPT's pair-only set, ChatGPT places 3rd or 5th. 43 points overall, 0 first-place finishes.

The gap between Grok (64 pts) and ChatGPT (43 pts) is essentially the triple-circumcircle layer: Grok's R5 (4 circles, 1st) and R7 (3 circles, 1st) wins both come from triple-circles that ChatGPT can't enumerate.

## Claude: pair-only with deep local search, full budget every round

Claude (Opus 4.7, 480 lines) is the longest bot in the field and the slowest, spending the full 26-second budget every round. Its solver enumerates pair-diameter circles, computes smallest-enclosing-disks on cluster candidates, then runs local-search refinements (split overlapping circles, merge under-utilized ones, try alternative seedings). Circle counts: `[2, 6, 9, 9, 5, 12, 11, 11, 13, 10]`.

Claude's most interesting result is R10 (220 × 300, N=100, k=16): it finds a 10-circle covering, tying Kimi for the round optimum. Kimi's submission timestamp is 25.6 s, Claude's is 26.0 s — Kimi wins the tiebreak, Claude takes 2nd. The fact that Claude's deep local search hit the same answer as Kimi's iterative-merge search is a small validation: two different algorithms found the same tight cover for the hardest round of the day.

On the small-N rounds Claude lands 4th or 5th: its solver finds *a* valid cover, but the local-search refinement doesn't iterate enough times within the 26-second budget to discover that better candidate circles exist. 28 points, 5th overall.

## MiniMax M2.7 debut: 4 of 10 valid, geometry bug on non-square rectangles

MiniMax M2.7 (166 lines) is new to the field this challenge. The solver goes 4/10 valid (R1, R2, R5, R8) and INVALID on the other six rounds, all with `out_of_bounds_<i>` reasons. The pattern: when the rectangle's longer dimension is much larger than the shorter, MiniMax places circles whose extent goes outside the shorter axis. The bot is calculating rectangle containment with respect to a square's symmetry. Wins zero rounds (its 4 valid submissions land 4th, 5th, 6th, 5th — outside the points zone). 2 points, 6th place.

## The bottom: Muse, GLM, Gemini, Nemotron

**Muse (Spark, 129 lines)** submits valid covers every round but uses essentially the trivial strategy: ~1.1 circles per dot. Round circle counts: 17, 32, 30, 41, 36, 46, 48, 48, 55, 57. Always last among bots that submit, always zero points.

**GLM (5.1, 205 lines)** completes R1–R4 with valid submissions (7, 8, 15, 11 circles), then times out every subsequent round. The solver's complexity grows superlinearly with N, and the 30-second budget runs out for `N ≥ 85`. 0 points despite getting 4 rounds correct (4th–6th place on each).

**Gemini (Pro 3.1, 299 lines)** times out every round. R1 disconnects in 0.096 s, then R2–R10 register as immediate EOF (0.001 s) because the socket is already closed. The solver code looks reasonable on inspection but throws somewhere inside `solve_round` on the first ROUND line, killing the process before any submission. 0/10, 0 points.

**Nemotron (3 Super, 72 lines)** has an off-by-one indexing bug in its `DOT` parser:

```python
# Nemotron's dot parser, line 50–51:
x = float(dparts[1])    # ← dparts[1] is the dot INDEX, not x
y = float(dparts[2])    # ← dparts[2] is x, not y
```

The DOT line format is `DOT <idx> <x> <y>`, so `dparts[1]` is the dot's index and `dparts[2..3]` are its coordinates. Nemotron reads the index as x and reads x as y, leaving y unset (or reading the dot index `0..N-1` as a coordinate). Every round it gets `out_of_bounds_<i>` or `uncovered_dot_<idx>` failures because its circles land at the wrong points. 0/10, 0 points.

## What the three top solvers each get right

Three populations among the top tier, defined by what their candidate set is:

- **DeepSeek**: candidate set is a fixed grid plus the dot positions. Finds the optimum instantly when the grid aligns with the cluster centres, which is true for the small-N rounds. Fails when N=100 spread over 50,000 px² needs finer resolution.
- **Grok**: candidate set is every dot-pair circle plus every triple-circumcircle. ~166K candidates at N=100. Always contains the optimal small-cluster circles, but the greedy can't backtrack so it sometimes locks in a suboptimal first pick.
- **Kimi**: candidate set is the result of iterative merging from one-cluster-per-dot. Searches across the merge tree using full budget and multiple random seeds. Slow but converges on the true cluster structure when N is large.

The hard rounds (R8–R10) require recovering the genuine 12–16 cluster structure from 100 noisy points. Only Kimi's iterative merge does that. The easy rounds (R1–R4) just need to find 2–4 circles around obvious cluster centres, which a fast grid-search nails first. Grok sits in between: candidates from pairs and triples include both regimes' optima, and the speed (1–3 s) doesn't lose the timestamp tiebreak to DeepSeek on small rounds.

## The verdict

Three different solvers, three different shapes of the rank-points curve:

- **Grok wins on consistency.** Two firsts, eight 2nd-or-3rds, never below 5th place. 64 points.
- **Kimi wins on late-round dominance.** Three firsts (R8, R9, R10) plus consistent middle placements when its 25-second computation produces the same answer as faster bots. 63 points. The deficit is entirely the timestamp tiebreak on early rounds where Kimi found the optimum but submitted too late.
- **DeepSeek wins on first-half speed.** Five firsts (R1–R4, R6) at 0.05 s submission, then a sharp drop on R8–R10 when the grid resolution can't recover the tight clusters. 60 points.

The 4-point gap between #1 and #3 is the smallest top-of-podium spread of any challenge in the contest so far. The challenge differentiates clearly between candidate-set quality (Grok > ChatGPT, Kimi > Claude, DeepSeek > MiniMax), but among bots with adequate candidate sets, the ranking comes down to time-budget allocation.

ChatGPT and Claude both finish off the podium for the same reason: pair-only enumeration on small rounds, no equivalent of Grok's triple-circles or Kimi's iterative merge. 43 and 28 points respectively. The Grok–ChatGPT delta and the Kimi–Claude delta are both about 20 points, which is roughly the cost of missing one structural search component.

---

*Model versions for this challenge: Claude Opus 4.7, Gemini Pro 3.1, Grok Expert 4.20, ChatGPT GPT 5.5, MiniMax M2.7 (debut, replacing MiMo V2.5-Pro), Nemotron 3 Super, GLM 5.1, Kimi K2.6, Meta Muse Spark, DeepSeek V4-Pro. 10 bots played 10 rounds each; rectangles ranged from 120 × 80 to 290 × 200, dot counts from 50 to 100. 30-second wall-clock per bot per round, 10-second registration window before R1. Bots were generated by sending `prompt.md` to each OpenRouter model in a single chat completion request (no `max_tokens` cap, `temperature=0.2`); five model bots were authored via direct chat. Server code, prompt, generated bots, and the per-round dot placements are at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
