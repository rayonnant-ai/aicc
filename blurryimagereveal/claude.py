#!/usr/bin/env python3
"""Dial-Up Download client — identifies images from progressively deblurred pixel data."""

import socket
import sys
import time

BOT_NAME = "claude_bot"
HOST = "localhost"
PORT = 7474


class Connection:
    """Buffered TCP connection with line and byte reading."""

    def __init__(self, host, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(120)
        self.sock.connect((host, port))
        self.buf = b""

    def readline(self):
        while b"\n" not in self.buf:
            chunk = self.sock.recv(262144)
            if not chunk:
                raise ConnectionError("Server closed connection")
            self.buf += chunk
        i = self.buf.index(b"\n")
        line = self.buf[:i].decode("ascii")
        self.buf = self.buf[i + 1:]
        return line

    def readbytes(self, n):
        while len(self.buf) < n:
            want = n - len(self.buf)
            chunk = self.sock.recv(max(262144, want))
            if not chunk:
                raise ConnectionError("Server closed connection")
            self.buf += chunk
        data = self.buf[:n]
        self.buf = self.buf[n:]
        return data

    def send(self, s):
        self.sock.sendall(s.encode("ascii"))

    def close(self):
        self.sock.close()


def parse_ppm(data):
    """Parse ASCII PPM P3 data. Returns (width, height, pixels) where pixels
    is a flat list of ints: [r0,g0,b0, r1,g1,b1, ...]."""
    # Fast path: assume no comments (typical for machine-generated PPM)
    tokens = data.split()
    # tokens[0] == b'P3'
    w = int(tokens[1])
    h = int(tokens[2])
    # tokens[3] == maxval (255)
    n = w * h * 3
    pixels = list(map(int, tokens[4:4 + n]))
    return w, h, pixels


def downsample_block_avg(pixels, w, h, tw, th):
    """Downsample by block-averaging to tw x th. Returns list of floats."""
    bw = w // tw
    bh = h // th
    inv_n = 1.0 / (bw * bh)
    out = [0.0] * (tw * th * 3)

    for y in range(h):
        ty = y // bh
        if ty >= th:
            break
        row_base = y * w * 3
        for x in range(w):
            tx = x // bw
            if tx >= tw:
                continue
            src = row_base + x * 3
            dst = (ty * tw + tx) * 3
            out[dst]     += pixels[src]
            out[dst + 1] += pixels[src + 1]
            out[dst + 2] += pixels[src + 2]

    for i in range(len(out)):
        out[i] *= inv_n
    return out


def downsample_center(pixels, w, h, tw, th):
    """Fast approximate downsample by sampling center pixel of each block.
    Good for blurred images where block contents are nearly uniform."""
    bw = w // tw
    bh = h // th
    cy_base = bh // 2
    cx_base = bw // 2
    out = []
    for ty in range(th):
        cy = ty * bh + cy_base
        row_base = cy * w * 3
        for tx in range(tw):
            cx = tx * bw + cx_base
            off = row_base + cx * 3
            out.append(float(pixels[off]))
            out.append(float(pixels[off + 1]))
            out.append(float(pixels[off + 2]))
    return out


def downsample_sparse(pixels, w, h, tw, th, samples_per_dim=4):
    """Downsample by sampling a grid of points within each block and averaging.
    Faster than full block avg but more accurate than center-only."""
    bw = w // tw
    bh = h // th
    # Pick evenly spaced sample points within each block
    sy_offsets = [bh * (i + 1) // (samples_per_dim + 1) for i in range(samples_per_dim)]
    sx_offsets = [bw * (i + 1) // (samples_per_dim + 1) for i in range(samples_per_dim)]
    inv_n = 1.0 / (samples_per_dim * samples_per_dim)

    out = []
    for ty in range(th):
        y0 = ty * bh
        for tx in range(tw):
            x0 = tx * bw
            rs = gs = bs = 0.0
            for dy in sy_offsets:
                row_base = (y0 + dy) * w * 3
                for dx in sx_offsets:
                    off = row_base + (x0 + dx) * 3
                    rs += pixels[off]
                    gs += pixels[off + 1]
                    bs += pixels[off + 2]
            out.append(rs * inv_n)
            out.append(gs * inv_n)
            out.append(bs * inv_n)
    return out


def compute_ssd(a, b):
    """Sum of squared differences between two flat float lists."""
    total = 0.0
    for i in range(len(a)):
        d = a[i] - b[i]
        total += d * d
    return total


def color_histogram(pixels, bins=16):
    """Compute RGB color histogram with given number of bins per channel."""
    hist = [0] * (bins * 3)
    scale = bins / 256.0
    for i in range(0, len(pixels), 3):
        ri = int(pixels[i] * scale)
        gi = int(pixels[i + 1] * scale)
        bi = int(pixels[i + 2] * scale)
        if ri >= bins: ri = bins - 1
        if gi >= bins: gi = bins - 1
        if bi >= bins: bi = bins - 1
        hist[ri] += 1
        hist[bins + gi] += 1
        hist[2 * bins + bi] += 1
    return hist


def hist_diff(a, b):
    """Chi-squared distance between two histograms."""
    total = 0.0
    for i in range(len(a)):
        s = a[i] + b[i]
        if s > 0:
            d = a[i] - b[i]
            total += d * d / s
    return total


# --- Configuration ---

# Primary comparison scale for each blur radius
BLUR_TO_SCALE = {
    64: 4,
    32: 8,
    16: 16,
    8:  16,
    4:  32,
    2:  32,
    1:  32,
    0:  32,
}

# Secondary (coarser) scale for additional discrimination
BLUR_TO_SCALE2 = {
    64: None,
    32: 4,
    16: 8,
    8:  8,
    4:  16,
    2:  16,
    1:  16,
    0:  16,
}

# Confidence thresholds: ratio of 2nd-best / best SSD must exceed this
# Lower blur = higher reward = can afford more risk = lower threshold
# But at very high blur, discrimination is hard, so moderate threshold
CONF_THRESHOLDS = {
    # EV analysis: at blur=64, break-even is P=9%, so be aggressive
    # At blur=1, break-even is P=83%, but accuracy should be ~100% anyway
    64: 1.4,   # 100 pts: high reward justifies moderate risk
    32: 1.3,   # 60 pts
    16: 1.25,  # 30 pts
    8:  1.2,   # 15 pts
    4:  1.15,  # 8 pts
    2:  1.1,   # 4 pts
    1:  1.05,  # 2 pts
    0:  1.0,   # 1 pt: always guess (perfect match available)
}

ALL_SCALES = sorted(set(
    [v for v in BLUR_TO_SCALE.values()] +
    [v for v in BLUR_TO_SCALE2.values() if v is not None]
))


def score_references(reveal_pixels, w, h, ref_ds, n_refs, blur):
    """Score each reference against the reveal image. Returns list of scores."""
    s1 = BLUR_TO_SCALE[blur]
    s2 = BLUR_TO_SCALE2[blur]

    # For blurred reveals, center sampling is fast and accurate
    if blur >= 16:
        rev_ds1 = downsample_center(reveal_pixels, w, h, s1, s1)
        rev_ds2 = downsample_center(reveal_pixels, w, h, s2, s2) if s2 else None
    else:
        # For sharper images, use sparse sampling for better accuracy
        rev_ds1 = downsample_sparse(reveal_pixels, w, h, s1, s1, samples_per_dim=4)
        rev_ds2 = downsample_sparse(reveal_pixels, w, h, s2, s2, samples_per_dim=4) if s2 else None

    scores = []
    npix1 = s1 * s1 * 3
    npix2 = (s2 * s2 * 3) if s2 else 1

    for ri in range(n_refs):
        ssd1 = compute_ssd(rev_ds1, ref_ds[(ri, s1)]) / npix1
        if s2:
            ssd2 = compute_ssd(rev_ds2, ref_ds[(ri, s2)]) / npix2
            # Weight finer scale more heavily
            score = ssd1 * 0.7 + ssd2 * 0.3
        else:
            score = ssd1
        scores.append(score)

    return scores


def decide(scores, blur):
    """Decide whether to guess. Returns (should_guess, best_index)."""
    ranked = sorted(range(len(scores)), key=lambda i: scores[i])
    best = ranked[0]
    best_s = scores[best]
    second_s = scores[ranked[1]]

    if best_s > 0:
        ratio = second_s / best_s
    else:
        ratio = float("inf")  # Perfect match

    threshold = CONF_THRESHOLDS.get(blur, 1.1)

    # Always guess on the last step (blur == 0)
    should_guess = (ratio >= threshold) or (blur == 0)

    return should_guess, best, ratio, threshold, ranked[1]


def main():
    print(f"Connecting to {HOST}:{PORT}...", flush=True)
    conn = Connection(HOST, PORT)

    # Register
    conn.send(f"{BOT_NAME}\n")
    print(f"Registered as {BOT_NAME}", flush=True)

    total_score = 0

    for round_idx in range(10):
        # --- Read ROUND header ---
        try:
            round_line = conn.readline()
        except ConnectionError:
            print("Server closed connection (game over)", flush=True)
            break
        print(f"\n{'='*50}", flush=True)
        print(f"{round_line}", flush=True)

        # --- Read REFERENCES ---
        ref_line = conn.readline()
        n_refs = int(ref_line.split()[1])
        print(f"Loading {n_refs} reference images...", flush=True)

        ref_ds = {}  # (ref_index, scale) -> downsampled pixel list

        t0 = time.time()
        for _ in range(n_refs):
            hdr = conn.readline()
            parts = hdr.split()
            ri = int(parts[1])
            sz = int(parts[3])

            data = conn.readbytes(sz)
            w, h, pixels = parse_ppm(data)

            # Precompute downsampled versions at all needed scales
            for s in ALL_SCALES:
                if s <= 8:
                    # Small scales: use sparse sampling (faster, good enough)
                    ref_ds[(ri, s)] = downsample_sparse(pixels, w, h, s, s, samples_per_dim=8)
                else:
                    # Larger scales: use sparse sampling with fewer points
                    ref_ds[(ri, s)] = downsample_sparse(pixels, w, h, s, s, samples_per_dim=4)

            print(f"  ref {ri}: {w}x{h} loaded", flush=True)

        t1 = time.time()
        print(f"References loaded in {t1-t0:.1f}s", flush=True)

        # --- Process REVEAL steps ---
        guessed = False
        for step_idx in range(8):
            hdr = conn.readline()
            if not hdr.startswith("REVEAL"):
                print(f"  Unexpected: {hdr}", flush=True)
                break

            parts = hdr.split()
            step_num = int(parts[1])
            blur = int(parts[3])
            sz = int(parts[5])

            data = conn.readbytes(sz)

            # Read GUESS? prompt
            prompt = conn.readline()

            if guessed:
                conn.send("PASS\n")
                continue

            t2 = time.time()
            w, h, reveal_pixels = parse_ppm(data)
            t3 = time.time()

            # Score references
            scores = score_references(reveal_pixels, w, h, ref_ds, n_refs, blur)
            t4 = time.time()

            # Decide
            should_guess, best, ratio, threshold, second = decide(scores, blur)

            print(f"  step {step_num} blur={blur:2d}: "
                  f"best=ref{best}({scores[best]:.0f}) "
                  f"2nd=ref{second}({scores[second]:.0f}) "
                  f"ratio={ratio:.2f} thresh={threshold:.2f} "
                  f"[parse={t3-t2:.2f}s score={t4-t3:.2f}s]",
                  flush=True)

            if should_guess:
                conn.send(f"GUESS {best}\n")
                result = conn.readline()
                print(f"  >>> GUESS {best} -> {result}", flush=True)
                if result.startswith("CORRECT"):
                    pts = int(result.split()[1])
                    total_score += pts
                elif result.startswith("WRONG"):
                    total_score -= 10
                guessed = True
                break  # Round is over after guessing
            else:
                conn.send("PASS\n")
                print(f"  >>> PASS", flush=True)

        if not guessed:
            print(f"  Round ended without guessing (0 pts)", flush=True)

        print(f"  Running total: {total_score}", flush=True)

    print(f"\n{'='*50}", flush=True)
    print(f"FINAL SCORE: {total_score}", flush=True)
    try:
        conn.close()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except ConnectionError as e:
        print(f"\nConnection ended: {e}", flush=True)
    except KeyboardInterrupt:
        print("\nInterrupted", flush=True)
    except Exception as e:
        print(f"\nError: {e}", flush=True)
        import traceback
        traceback.print_exc()