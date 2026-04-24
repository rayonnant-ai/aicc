# AI Coding Contest Day 6: Blurry Image Reveal. Gemini dominated.

The sixth challenge is image identification from progressive blur. Each round, the server sends 10 reference images at full 512×512 resolution, then reveals a mystery image through 8 stages of decreasing Gaussian blur, from radius 64 (an unrecognizable smear) down to radius 0 (pixel-perfect). After each stage the bot can guess which reference is being revealed, or pass and wait for more clarity. Guess correctly early and score up to 100 points. Guess wrong and lose 10. All images are Wikimedia Commons Pictures of the Day.

![Progressive blur stages from radius 64 to sharp](blur_steps.png)

The server picks each round's 10 references by colour similarity, so all 10 images have similar colour distributions. Average colour won't help. The bots need spatial structure to tell them apart.

Six bots competed across 10 rounds.

## The Results

| Bot | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini_bot | 0 | 0 | +100 | +100 | +100 | +100 | +100 | +100 | +60 | +100 | **760** |
| grok_dialup_bot | 0 | 0 | 0 | +100 | +100 | 0 | 0 | 0 | +60 | 0 | **260** |
| claude_bot | +100 | +100 | 0 | T/O | T/O | T/O | T/O | T/O | T/O | T/O | **200** |
| mimo_bot | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | **0** |
| nemo_bot | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | **0** |
| gpt-5.4_bot | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | T/O | **0** |

*(T/O = timed out. 0 = passed all steps or no guess.)*

## GPT, MiMo, Nemotron: Death by parsing

Three bots timed out in every round. The server sends 10 reference images before the first GUESS? prompt — roughly 30MB of ASCII PPM data. The bot has 10 seconds to respond to each step. If it's still parsing reference images when the deadline hits, it times out.

In pure Python, parsing a 512×512 ASCII PPM means converting 786,432 string tokens to integers per image — 7.8 million int() calls for all 10 references, plus precomputing features on top of that.

GPT precomputed block-averaged downscales at 7 resolutions. Too much precomputation. MiMo implemented a full box blur in pure Python to simulate what the server's Gaussian blur would produce, which was clever but far too slow. Nemotron built nested Python lists of [r,g,b] per pixel (2.6 million list objects for 10 images), then triple-nested loops for block averages.

All three had matching strategies that might have worked. They just couldn't get past the I/O step.

## Claude: Fast start, then collapsed

Claude scored 200 points, 100 in each of the first two rounds, both at blur=64. Its approach: multi-scale sparse-sampled downscaling with SSD comparison and per-blur-level confidence thresholds.

Then it timed out for the remaining 8 rounds. Claude's precomputation (sparse downscales at 5 resolutions for all 10 references) was on the edge of the 10-second deadline. In rounds 1 and 2 it finished in time (93ms and 0ms response times). In round 3 it processed all 8 blur steps but was never confident enough to guess. From round 4 onward, it consistently timed out at the first step.

The likely cause: reference image sets vary in parsing complexity (whitespace patterns, token counts), and rounds 4+ happened to hit slower configurations. Claude's pipeline was right at the boundary. Fast enough for 2 rounds, too slow for the other 8.

## Grok: Conservative scorer

Grok scored 260 points, placing second. Its approach: parse each reference PPM, precompute downsampled versions at 7 target sizes, compare using MSE at the appropriate resolution for the current blur level.

Grok's confidence threshold was `1.8 + blur/32` — at blur=64 it required the best match to be 3.8× closer than the second-best before guessing. This meant it passed on most rounds:

Rounds 4 and 5 had sufficiently distinctive references; it guessed at blur=64 for 100 points each. Round 9 needed one more deblur step, so it waited until blur=32 for 60 points. Every other round it passed without guessing.

Grok never guessed wrong, but it only scored in 3 of 10 rounds. The conservative threshold left 700 points on the table.

## Gemini: The winner

Gemini won with 760 points using the simplest code in the field — 147 lines. Claude's 405-line bot with multi-scale sparse sampling and per-blur confidence tuning scored 200. Gemini's 147 lines scored 760.

The entire strategy: compute an 8×8 spatial colour average fingerprint per image (64 blocks, each a 64×64 pixel region averaged to one RGB value). Compare using MSE. Guess when the confidence ratio (best distance / second-best distance) drops below 0.70, or when blur ≤ 16. That's it.

The 8×8 fingerprint was the fastest feature computation in the competition. One pass over the pixel array with slice-based summing. While other bots spent their time budget parsing, Gemini finished all 10 reference fingerprints and started answering immediately.

Gemini scored in 8 of 10 rounds. It guessed at blur=64 in 7 of those rounds for maximum points. Round 9 was the only round where it needed to wait until blur=32. It never guessed wrong.

The gap between Gemini and Grok came down to confidence thresholds. Both used colour-based MSE matching. Gemini guessed aggressively (ratio < 0.70) and scored 760. Grok waited conservatively (ratio > 3.8) and scored 260. Same algorithm family, 3× score difference.

## The speed filter

The challenge had a hidden qualifier: 30MB of ASCII data to parse before the first question. In a language with fast I/O, or with numpy, this is trivial. In pure Python with standard library only, it's the entire contest.

Gemini survived because it kept parsing lean and feature computation fast. Grok's downsampling was just efficient enough. Claude scraped by in 2 rounds before the deadline caught up. The other three never got past preparation.

In a stdlib-only Python contest with 10-second deadlines, I/O efficiency is the qualifying round.

---

*All runs were conducted on the same machine with all six bots connecting simultaneously to `localhost:7474`. References were selected by colour similarity to prevent trivial colour-matching. No bot was given the other bots' code or scores between rounds. All server code, prompts, and generated clients are available at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
