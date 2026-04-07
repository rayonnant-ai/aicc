# Day 6 Challenge: Blurry Image Reveal

**Task:** Write a Python 3.10 client that identifies images from progressively deblurred pixel data — like watching a photo come into focus.

---

### 1. Overview

At the start of each round, the server sends 10 reference images as full-resolution 512×512 ASCII PPM data. Then it picks one of the 10 and starts revealing it through progressively decreasing Gaussian blur — starting extremely blurry and sharpening each step. All images are 512×512 at every step; only the blur radius changes. After each step, your bot can either **guess** which of the 10 reference images is being revealed, or **pass** and wait for more clarity.

Guess correctly and you score points — more points for guessing while the image is still blurry. Guess wrong and you lose 10 points and are eliminated from that round.

---

### 2. Connection & Registration

* Connect via TCP to `localhost:7474`.
* Send your bot name followed by a newline: `{model_name}_bot\n`

---

### 3. Round Flow

**Step 1 — Reference images:**
```
ROUND {n}\n
REFERENCES 10\n
REF {index} SIZE {bytes}\n
{ASCII PPM P3 data}
... (repeated for all 10 references)
```

All 10 reference images are sent as 512×512 ASCII PPM (P3) at full resolution.

**Step 2 — Progressive reveal:**
The server sends up to 8 deblur steps for the mystery image:

```
REVEAL {step} BLUR {radius} SIZE {bytes}\n
{ASCII PPM P3 data}
```

Blur radii: 64, 32, 16, 8, 4, 2, 1, 0 (fully sharp). All images are 512×512.

After each REVEAL, the server sends:
```
GUESS?\n
```

**Your bot responds with either:**
* `PASS\n` — wait for the next resolution step.
* `GUESS {index}\n` — guess that the mystery image is reference `{index}` (0-9). **One chance only.**

**Server responds to a GUESS:**
* `CORRECT {points}\n` — you got it right.
* `WRONG {actual_index}\n` — eliminated from this round.

If you PASS through all 8 steps without guessing, you score 0 for that round (but are not eliminated).

---

### 4. Scoring

Points are awarded based on the resolution at which you guess correctly:

| Blur Radius | Step | Points |
|---|---|---|
| 64 | 1 | 100 |
| 32 | 2 | 60 |
| 16 | 3 | 30 |
| 8 | 4 | 15 |
| 4 | 5 | 8 |
| 2 | 6 | 4 |
| 1 | 7 | 2 |
| 0 (sharp) | 8 | 1 |

Wrong guess at any step = **-10 points** and eliminated from the round.

---

### 5. Image Properties

* **Format:** ASCII PPM (P3). Each image is a standard PPM with header `P3\n{width} {height}\n255\n` followed by space-separated R G B values (0-255), row-major order.
* **Reference images:** 512×512 pixels, sourced from Wikimedia Commons. Subjects include landscapes, animals, architecture, art, objects — diverse visual content.
* **Reveal images:** The same image at full 512×512 resolution with Gaussian blur applied. The blur radius decreases each step from 64 (extremely blurry) to 0 (perfectly sharp). No noise, no rotation, no scaling — just blur.

---

### 6. Rounds

* 10 rounds total. Each round has a fresh set of 10 reference images and a new mystery image.
* Timeout: 10 seconds per GUESS? prompt.

---

### 7. Constraints

* **Language:** Standalone Python 3.10 script using only the **Standard Library**.
* **No external image libraries.** You must implement any image comparison/feature extraction yourself.



