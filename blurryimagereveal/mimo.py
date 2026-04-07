#!/usr/bin/env python3
"""Day 1 Challenge: Dial-Up Download — Progressive deblur image identification client."""

import socket
import sys
import time


def parse_ppm(data):
    """Parse ASCII PPM (P3) data into (width, height, pixels) where pixels is list of (r,g,b)."""
    tokens = data.split()
    idx = 0
    # P3 magic
    idx += 1
    width = int(tokens[idx]); idx += 1
    height = int(tokens[idx]); idx += 1
    maxval = int(tokens[idx]); idx += 1
    n = width * height
    pixels = [(int(tokens[idx + i*3]),
               int(tokens[idx + i*3 + 1]),
               int(tokens[idx + i*3 + 2])) for i in range(n)]
    return width, height, pixels


def downsample(pixels, w, h, tw, th):
    """Area-average downsample to tw x th."""
    sx, sy = w / tw, h / th
    result = []
    for ty in range(th):
        for tx in range(tw):
            x0, x1 = int(tx * sx), min(int((tx + 1) * sx), w)
            y0, y1 = int(ty * sy), min(int((ty + 1) * sy), h)
            sr = sg = sb = 0
            cnt = 0
            for y in range(y0, y1):
                row = y * w
                for x in range(x0, x1):
                    r, g, b = pixels[row + x]
                    sr += r; sg += g; sb += b
                    cnt += 1
            if cnt:
                result.append((sr // cnt, sg // cnt, sb // cnt))
            else:
                result.append(pixels[y0 * w + x0])
    return result


def box_blur(pixels, w, h, radius):
    """Apply separable box blur. radius=0 returns copy."""
    if radius <= 0:
        return list(pixels)
    n = radius * 2 + 1
    # Horizontal pass
    tmp = [None] * (w * h)
    for y in range(h):
        row = y * w
        rs = gs = bs = 0
        # Initial window
        for x in range(min(radius, w)):
            r, g, b = pixels[row + x]
            rs += r; gs += g; bs += b
        for x in range(w):
            xr = min(x + radius, w - 1)
            xl = max(x - radius - 1, -1)
            if x + radius < w:
                r, g, b = pixels[row + xr]
                rs += r; gs += g; bs += b
            if x - radius - 1 >= 0:
                r, g, b = pixels[row + xl]
                rs -= r; gs -= g; bs -= b
            cnt = min(x + radius, w - 1) - max(x - radius, 0) + 1
            tmp[row + x] = (rs // cnt, gs // cnt, bs // cnt)
    # Vertical pass
    out = [None] * (w * h)
    for x in range(w):
        rs = gs = bs = 0
        for y in range(min(radius, h)):
            r, g, b = tmp[y * w + x]
            rs += r; gs += g; bs += b
        for y in range(h):
            yb = min(y + radius, h - 1)
            ya = max(y - radius - 1, -1)
            if y + radius < h:
                r, g, b = tmp[yb * w + x]
                rs += r; gs += g; bs += b
            if y - radius - 1 >= 0:
                r, g, b = tmp[ya * w + x]
                rs -= r; gs -= g; bs -= b
            cnt = min(y + radius, h - 1) - max(y - radius, 0) + 1
            out[y * w + x] = (rs // cnt, gs // cnt, bs // cnt)
    return out


def blur_image(pixels, w, h, radius):
    """Multiple box-blur passes to approximate Gaussian blur (3 passes)."""
    if radius <= 0:
        return list(pixels)
    r = max(1, round(radius * w / 512))
    result = list(pixels)
    for _ in range(3):
        result = box_blur(result, w, h, r)
    return result


def compare(ref, reveal, w, h):
    """Sum of absolute differences (lower = more similar)."""
    total = 0
    n = w * h
    for i in range(n):
        rr, rg, rb = ref[i]
        vr, vg, vb = reveal[i]
        total += abs(rr - vr) + abs(rg - vg) + abs(rb - vb)
    return total


SIZE = 64  # comparison resolution
NPIX = SIZE * SIZE


class Client:
    def __init__(self, host="localhost", port=7474, name="mimo_bot"):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(15)
        self.sock.connect((host, port))
        self.sock.sendall(f"{name}\n".encode())
        self.buf = b""

    def readline(self):
        while b"\n" not in self.buf:
            data = self.sock.recv(65536)
            if not data:
                return None
            self.buf += data
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode().strip()

    def read_ppm(self):
        """Read PPM image, return downsampled pixels at SIZE x SIZE."""
        header = []
        while True:
            line = self.readline()
            if line is None:
                return None
            if line.startswith("P3"):
                header.append(line)
                break
        for _ in range(3):
            header.append(self.readline())

        w, h = int(header[1].split()[0]), int(header[1].split()[1])
        need = w * h * 3
        tokens = []
        while len(tokens) < need:
            line = self.readline()
            if line:
                tokens.extend(line.split())

        n = w * h
        pixels = [(int(tokens[i*3]), int(tokens[i*3+1]), int(tokens[i*3+2]))
                  for i in range(n)]

        if w != SIZE or h != SIZE:
            return downsample(pixels, w, h, SIZE, SIZE)
        return pixels

    def compare_images(self, ref, reveal, blur_r):
        """Compare with blur-matching."""
        if blur_r > 0:
            rb = blur_image(ref, SIZE, SIZE, blur_r)
            ib = blur_image(reveal, SIZE, SIZE, blur_r)
            return compare(rb, ib, SIZE, SIZE)
        return compare(ref, reveal, SIZE, SIZE)

    def run(self):
        total_score = 0
        for rnd in range(1, 11):
            line = self.readline()
            if not line or not line.startswith("ROUND"):
                break
            print(f"\n{'='*50}")
            print(f"  {line}")
            print(f"{'='*50}")

            # Read references
            ref_line = self.readline()  # REFERENCES 10
            refs = []
            for i in range(10):
                hdr = self.readline()  # REF i SIZE bytes
                print(f"  Reading reference {i}/9...", end="\r", flush=True)
                refs.append(self.read_ppm())
            print(f"  ✓ 10 references loaded          ")

            # Progressive reveal
            guessed = False
            for step in range(8):
                reveal_hdr = self.readline()
                if not reveal_hdr or not reveal_hdr.startswith("REVEAL"):
                    break
                parts = reveal_hdr.split()
                step_num = int(parts[1])
                blur_r = int(parts[3])
                reveal = self.read_ppm()

                guess_prompt = self.readline()  # GUESS?

                t0 = time.time()
                scores = [(self.compare_images(refs[i], reveal, blur_r), i)
                          for i in range(10)]
                scores.sort()
                elapsed = time.time() - t0

                best_s, best_i = scores[0]
                second_s = scores[1][0] if len(scores) > 1 else best_s
                margin = (second_s - best_s) / max(second_s, 1)

                # Confidence thresholds: higher blur → need more margin
                if blur_r >= 32:
                    threshold = 0.18
                elif blur_r >= 8:
                    threshold = 0.12
                elif blur_r >= 2:
                    threshold = 0.06
                else:
                    threshold = 0.03

                pts = {64: 100, 32: 60, 16: 30, 8: 15, 4: 8, 2: 4, 1: 2, 0: 1}
                print(f"  Step {step_num} blur={blur_r:>2} ({pts.get(blur_r,0):>3}pts) "
                      f"margin={margin:.4f} [{elapsed:.2f}s]")
                print(f"    Top-3: ref={best_i}({best_s:.0f}) "
                      f"ref={scores[1][1]}({scores[1][0]:.0f}) "
                      f"ref={scores[2][1]}({scores[2][0]:.0f})")

                if margin > threshold:
                    self.sock.sendall(f"GUESS {best_i}\n".encode())
                    resp = self.readline()
                    if resp and resp.startswith("CORRECT"):
                        pts_earned = int(resp.split()[1])
                        total_score += pts_earned
                        print(f"  ✅ CORRECT! +{pts_earned} pts (total: {total_score})")
                        guessed = True
                        break
                    elif resp and resp.startswith("WRONG"):
                        actual = resp.split()[1]
                        total_score -= 10
                        print(f"  ❌ WRONG! actual={actual} -10 pts (total: {total_score})")
                        guessed = True
                        break
                else:
                    self.sock.sendall(b"PASS\n")
                    print(f"  → PASS (need margin>{threshold:.2f})")

            if not guessed:
                print(f"  ⏭ No guess — 0 pts (total: {total_score})")

        print(f"\n{'='*50}")
        print(f"  🏁 FINAL SCORE: {total_score}")
        print(f"{'='*50}")
        self.sock.close()


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "mimo_bot"
    Client(name=name).run()