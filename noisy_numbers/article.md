# AI Coding Contest Day 1: Noisy Soviet Postcodes. Grok won. Everyone else scored zero.

This is a rerun of the original Day 1 challenge ("sovietpost"), where every model scored zero across all rounds. In that version, the bots were given reference images of the digit glyphs but no structured data — they had to reverse-engineer the 52-dot grid font from pixel images they couldn't actually see. Every model invented wrong digit templates (7-segment displays, rectangle-and-diagonal models, hardcoded bitmaps) because LLMs cannot do spatial reasoning on pixel data.

For this rerun, the prompt was redesigned: instead of reference images, the bots receive the normalized (x, y) coordinates of all 52 dots and the complete stroke sequences for all 10 digits as text. The bots don't need to reverse-engineer the font. They have the blueprint.

The task itself is unchanged: read six-digit Soviet postal codes from noisy bitmap images, using only Python's standard library. No PIL, no OpenCV, no numpy. The digits are drawn on a 52-dot grid by connecting dots with straight lines, a glyph system no model has seen before. The images have 5% pixel noise, progressive scaling (±0% to ±10%), and progressive rotation (±0° to ±10°). Each bot receives the image as ASCII PPM data over TCP and must reply with six digits within 10 seconds.

Six bots competed across 100 rounds. Only one scored a single point.

## The Results

| Bot | Points | Status |
|---|---|---|
| GrokSovietBot | 8 | active |
| mimo_bot | 0 | active |
| claude_bot | 0 | active |
| gemini_bot | 0 | active |
| gpt54_bot | 0 | eliminated (round 1) |
| nemotron_super | 0 | eliminated (round 1) |

## GPT and Nemotron: Dead on arrival

Both bots timed out in round 1 and were eliminated. GPT's bot used `buffering=0` on its socket makefile, causing byte-by-byte reads on a ~3MB ASCII PPM image. Nemotron likely hit the same class of I/O bottleneck. Neither bot processed a single image.

## Claude: Correct digit model, broken pipeline

Claude's approach was conceptually sound. It modeled the digits as 7-segment displays — top, bottom, left-top, left-bottom, right-top, right-bottom, mid, plus two diagonals — and got every digit's segment combination correct. This is a valid simplification of the 52-dot grid glyphs.

The pipeline: parse PPM → Otsu threshold → binarize → erode → dilate → PCA rotation → tight bounds → divide into 6 cells → resize → NCC template matching.

The problem was the erosion step. The bot used `erode(mn=5)`, requiring 5 of 8 neighbors to be black for a pixel to survive. On these images, the digit strokes are only a few pixels thick. An erosion that aggressive wipes out all the strokes along with the noise. When nothing survives erosion, `sum(strokes) < 30` triggers, the bot falls back to `mn=4`, then `mn=3`, then gives up and sends `000000`.

Claude sent `000000` in all 100 rounds. Its digit recognition was never reached. The image processing destroyed the signal before the (correct) matching logic had a chance.

## Gemini: Right data, wrong metric

Gemini was the only bot besides Grok that used the dot coordinates and stroke sequences from the prompt to build templates. It rendered all 10 digit templates at 15×25 pixels using Bresenham line drawing, a reasonable approach.

The failure was in the matching. Gemini used the template pixel grids directly, scoring each cell by counting how many template pixels overlapped with dark image pixels. The digit 8 has the most strokes, a full rectangle plus a crossbar. On any noisy image, 8 will always have the highest overlap because it covers the most area. Every cell matched to 8. Every round.

Gemini sent `888888` in all 100 rounds. A normalized cross-correlation or a penalty for ink in unexpected positions would have fixed this.

## MiMo: Varied but wrong

MiMo's bot produced different answers each round. Unlike Claude's constant `000000` or Gemini's constant `888888`, MiMo's pipeline actually ran. It parsed the PPM, found dark pixels, estimated rotation angle, derotated the image, segmented cells, and scored digits using the provided stroke sequences.

The scoring function samples points along each digit's strokes and counts how many hit dark pixels. In theory, this is the right idea. In practice, the cell segmentation was off. It assumed fixed 16px gaps and divided the remaining width by 6, which doesn't account for noise-induced boundary errors or rotation. The cells were misaligned, so the stroke sampling checked the wrong regions.

MiMo scored 0 but showed partial signal: its answers often contained 1-2 correct digits (e.g., `401800` for `550049`, `108800` for `567557`). With better cell localization, this bot could have competed.

## Grok: 8 points, the only scorer

Grok had the best algorithm in the field, and the 8 points showed it.

Its approach was unique among the competitors: instead of rendering templates and doing pixel-level matching, it used the dot coordinates to directly probe the image. The pipeline:

1. **Parse and binarize** the PPM (threshold at 50% of max value).
2. **Find cells** using column projection — count dark pixels per column, find contiguous runs above 25% of the peak, reject runs narrower than 30px.
3. **Align the dot grid** for each cell by searching over 3,125 combinations of scale (5 values), rotation (5 values), and position offset (5×5 grid). At each combination, it maps all 52 dot positions into pixel coordinates and checks how many dots land on dark pixels.
4. **Score each digit** using the best alignment. For each candidate digit 0-9, it samples points along the candidate's strokes and computes the "fill ratio" (fraction of sample points that hit dark pixels). It then does the same for all strokes that the candidate should NOT have (forbidden strokes) and computes a penalty. The final score is `required_fill - forbidden_fill`.

The required-vs-forbidden scoring is the key insight that Gemini missed. Digit 8 has high required fill, but it also has zero forbidden strokes (it uses every segment). Digit 1 has low required fill, but most strokes are forbidden. The subtraction balances this naturally.

Grok's 8 correct rounds were: 3, 6, 7, 9, 16, 20, 78, and 80. It also had many near-misses where 5 of 6 digits were correct:

| Round | Grok sent | Correct | Wrong digits |
|---|---|---|---|
| 15 | 519675 | 579675 | 1 |
| 18 | 177056 | 777056 | 1 |
| 22 | 483398 | 473398 | 1 |
| 25 | 748279 | 740279 | 1 |
| 31 | 836296 | 136296 | 1 |
| 33 | 388492 | 385492 | 1 |
| 57 | 597527 | 597427 | 1 |
| 99 | 335540 | 335510 | 1 |

Eight more rounds where a single digit was off. If scoring were per-digit instead of all-or-nothing, Grok would have scored significantly higher.

But Grok also had a failure mode: when `find_cells` couldn't locate 6 cells (usually because noise or rotation blurred the column projections), the bot sent `000000`. This happened in roughly 40% of rounds. The cell segmentation was the weakest link. The alignment and scoring logic worked when it had the right input.

## What went wrong across the board

Every model was given the same advantage: the 52 dot coordinates and all 10 digit stroke sequences, as text in the prompt. The correct approach, mapping the dot positions onto the image and checking which connections have ink, was right there in the data. Grok was the only model that fully implemented it.

The failure modes split three ways:

1. **Ignored the provided data** (Claude). Built a 7-segment model from scratch instead of using the dot coordinates and stroke sequences that were literally in the prompt. The digit model happened to be correct, but the image processing pipeline was tuned blind and destroyed all signal.

2. **Used the data but botched the matching** (Gemini, MiMo). Both built templates from the provided strokes but failed at the matching step. Gemini didn't penalize unexpected ink. MiMo misaligned its cells.

3. **Never got to processing** (GPT, Nemotron). Crashed on I/O before reading a single image.

What connected all the failures was that LLMs can write image processing code but they can't debug it without seeing the images. Every model made pipeline decisions (erosion strength, binarization threshold, cell segmentation heuristics) that required visual feedback to tune. Without being able to look at a sample image and check whether their cells were aligned or their templates matched, they were coding blind.

## The Verdict

Grok won with 8 points and earned them. Its required-vs-forbidden stroke scoring was the most sophisticated recognition approach in the field, and its alignment search over scale, rotation, and position was the right way to handle image distortions. Getting 5-of-6 digits right in eight additional rounds shows the algorithm works. It just needed more robust cell segmentation.

Claude had the right digit model but the wrong erosion parameters. Gemini had the right data but the wrong matching metric. MiMo had the right pipeline structure but the wrong cell boundaries. GPT and Nemotron never started. This was the hardest challenge of the contest, and it wasn't particularly close.

---

*All runs were conducted on the same machine with all six bots connecting simultaneously to `localhost:7474`. No bot was given the other bots' code or scores between rounds. All server code, prompts, and generated clients are available at [github.com/rrezel/llmcomp](https://github.com/rrezel/llmcomp).*
