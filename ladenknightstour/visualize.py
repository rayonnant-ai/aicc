#!/usr/bin/env python3
"""
Animate round 10 (8x8) comparing claude_bot and gemini_bot's tours side-by-side.

Usage:
    python3 visualize.py                     # writes round10.mp4
    python3 visualize.py --frames-dir out/   # writes PNG frames instead
    python3 visualize.py --log results.log.1 # pick a different log

Requires Pillow (PIL). MP4 output requires ffmpeg on $PATH.
"""
import argparse
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

from PIL import Image, ImageDraw, ImageFont

# ── layout ────────────────────────────────────────────────────────────────────
CELL = 60
ROWS, COLS = 8, 8
BOARD_W = COLS * CELL
BOARD_H = ROWS * CELL

BOARD_PAD = 24
BOARD_GAP = 80
HEADER_H = 96
TITLE_Y = 14
SUBTITLE_Y = 52

BANNER_H = 36
BOARD_TOP = HEADER_H + BANNER_H
STATS_H = 96

CANVAS_W = BOARD_PAD * 2 + BOARD_W * 2 + BOARD_GAP
CANVAS_H = BOARD_TOP + BOARD_H + STATS_H + BOARD_PAD

FPS = 4
HOLD_FINAL_FRAMES = 12

# ── palette ───────────────────────────────────────────────────────────────────
BG = (22, 22, 28)
HEADER_BG = (12, 12, 18)
BOARD_BORDER = (80, 80, 92)

UNVISITED_BG = (40, 40, 50)
CELL_LINE = (65, 65, 76)

CLAUDE_TRAIL = (45, 100, 160)
CLAUDE_BANNER = (110, 180, 250)

GEMINI_TRAIL = (140, 55, 120)
GEMINI_BANNER = (230, 120, 200)

CURRENT_BG = (255, 215, 70)   # yellow knight position
CURRENT_TEXT = (20, 20, 30)

PATH_COLOR = (230, 230, 235)

TEXT_LIGHT = (235, 235, 240)
TEXT_MUTED = (150, 150, 160)
LABEL = (170, 170, 180)

# weight text colors by magnitude
W_LIGHT = (195, 200, 210)   # 1–3
W_MID = (255, 185, 90)      # 10–20
W_HEAVY = (255, 95, 95)     # 21+


def load_font(size, bold=False):
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def weight_color(w):
    if w >= 21:
        return W_HEAVY
    if w >= 10:
        return W_MID
    return W_LIGHT


# ── log parsing ───────────────────────────────────────────────────────────────

def parse_round10(log_path):
    text = open(log_path).read()
    m = re.search(r'--- ROUND 10:.*?(?=--- ROUND|={10,})', text, re.DOTALL)
    if not m:
        sys.exit("Round 10 block not found in log.")
    block = m.group(0)

    # weights: 8 lines after "WEIGHTS:"
    wm = re.search(r'WEIGHTS:\n((?:.*\n){8})', block)
    if not wm:
        sys.exit("Could not parse weights.")
    weights = []
    for line in wm.group(1).rstrip('\n').split('\n'):
        nums = [int(x) for x in line.split() if x.lstrip('-').isdigit()]
        if len(nums) == COLS:
            weights.append(nums)
    if len(weights) != ROWS:
        sys.exit(f"Parsed {len(weights)} weight rows; expected {ROWS}.")

    # per-bot cost line:  "  claude_bot ... | time=  7926 | ... "
    def grab_cost(name):
        cm = re.search(rf'  {re.escape(name)}\s+\|\s*time=\s*(\d+)', block)
        return int(cm.group(1)) if cm else None

    # tour line: "  name (VALID, time=X):\n    [[...]]"
    def grab_tour(name):
        tm = re.search(rf'  {re.escape(name)} \(VALID[^)]*\):\n\s+(\[.*\])', block)
        if not tm:
            sys.exit(f"Tour for {name} not found in round 10.")
        return json.loads(tm.group(1))

    return {
        "weights": weights,
        "claude_tour": grab_tour('claude_bot'),
        "gemini_tour": grab_tour('gemini_bot'),
        "claude_cost": grab_cost('claude_bot'),
        "gemini_cost": grab_cost('gemini_bot'),
    }


def compute_states(tour, weights):
    """Return list of (load, cost) after each move index."""
    out = []
    load = 0
    cost = 0
    prev_load = 0
    for i, (r, c) in enumerate(tour):
        if i > 0:
            cost += prev_load
        load += weights[r][c]
        out.append((load, cost))
        prev_load = load
    return out


# ── rendering ─────────────────────────────────────────────────────────────────

def draw_board(img, x0, y0, weights, tour, step, trail_color):
    d = ImageDraw.Draw(img)

    # all cells: base background and grid
    for r in range(ROWS):
        for c in range(COLS):
            x, y = x0 + c * CELL, y0 + r * CELL
            d.rectangle([x, y, x + CELL, y + CELL], fill=UNVISITED_BG, outline=CELL_LINE)

    # visited cells so far
    visited_idx = {}
    for k in range(min(step + 1, len(tour))):
        visited_idx[tuple(tour[k])] = k

    for (r, c), k in visited_idx.items():
        x, y = x0 + c * CELL, y0 + r * CELL
        color = CURRENT_BG if k == step else trail_color
        d.rectangle([x, y, x + CELL, y + CELL], fill=color, outline=CELL_LINE)

    # path line through visited squares
    if step >= 1:
        pts = []
        for k in range(min(step + 1, len(tour))):
            r, c = tour[k]
            pts.append((x0 + c * CELL + CELL // 2, y0 + r * CELL + CELL // 2))
        if len(pts) >= 2:
            d.line(pts, fill=PATH_COLOR, width=2)

    # weights
    font = load_font(18, bold=True)
    glyph_font = load_font(28, bold=True)
    for r in range(ROWS):
        for c in range(COLS):
            w = weights[r][c]
            x, y = x0 + c * CELL, y0 + r * CELL
            is_current = (tuple((r, c)) in visited_idx and visited_idx[(r, c)] == step)
            is_trail = (tuple((r, c)) in visited_idx and not is_current)

            if is_current:
                # draw knight glyph + tiny weight tag
                txt = "\u265E"  # ♞
                bb = glyph_font.getbbox(txt)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                d.text((x + (CELL - tw) // 2 - bb[0], y + (CELL - th) // 2 - bb[1] - 2),
                       txt, fill=CURRENT_TEXT, font=glyph_font)
                # small weight in corner
                small = load_font(11, bold=True)
                wtxt = str(w)
                wbb = small.getbbox(wtxt)
                d.text((x + CELL - (wbb[2] - wbb[0]) - 4, y + 2),
                       wtxt, fill=CURRENT_TEXT, font=small)
            else:
                color = (235, 235, 240) if is_trail else weight_color(w)
                txt = str(w)
                bb = font.getbbox(txt)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                d.text((x + (CELL - tw) // 2 - bb[0], y + (CELL - th) // 2 - bb[1]),
                       txt, fill=color, font=font)

    # outer border
    d.rectangle([x0 - 1, y0 - 1, x0 + BOARD_W + 1, y0 + BOARD_H + 1],
                outline=BOARD_BORDER, width=2)


def render_frame(step, data, claude_states, gemini_states):
    img = Image.new('RGB', (CANVAS_W, CANVAS_H), BG)
    d = ImageDraw.Draw(img)

    # header bar
    d.rectangle([0, 0, CANVAS_W, HEADER_H], fill=HEADER_BG)
    title_font = load_font(28, bold=True)
    sub_font = load_font(15)
    d.text((BOARD_PAD, TITLE_Y),
           "Laden Knight's Tour  \u2014  Round 10  \u2014  8\u00d78  \u2014  64 squares",
           fill=TEXT_LIGHT, font=title_font)
    total = len(data["claude_tour"])
    d.text((BOARD_PAD, SUBTITLE_Y),
           f"move {min(step, total - 1) + 1} / {total}",
           fill=TEXT_MUTED, font=sub_font)

    # per-board banner
    x_claude = BOARD_PAD
    x_gemini = BOARD_PAD + BOARD_W + BOARD_GAP
    y_banner = HEADER_H + 6
    y_board = BOARD_TOP + 4

    name_font = load_font(18, bold=True)
    d.text((x_claude, y_banner),
           f"claude_bot   \u2014   final cost {data['claude_cost']}",
           fill=CLAUDE_BANNER, font=name_font)
    d.text((x_gemini, y_banner),
           f"gemini_bot   \u2014   final cost {data['gemini_cost']}",
           fill=GEMINI_BANNER, font=name_font)

    # boards
    draw_board(img, x_claude, y_board, data["weights"],
               data["claude_tour"], step, CLAUDE_TRAIL)
    draw_board(img, x_gemini, y_board, data["weights"],
               data["gemini_tour"], step, GEMINI_TRAIL)

    # stats
    d = ImageDraw.Draw(img)
    big = load_font(26, bold=True)
    lbl = load_font(13, bold=True)

    def stat_block(x, load, cost, color):
        y = y_board + BOARD_H + 18
        d.text((x, y), "LOAD", fill=LABEL, font=lbl)
        d.text((x + 110, y), "COST", fill=LABEL, font=lbl)
        d.text((x, y + 20), f"{load:,}", fill=color, font=big)
        d.text((x + 110, y + 20), f"{cost:,}", fill=color, font=big)

    step_c = min(step, len(claude_states) - 1)
    step_g = min(step, len(gemini_states) - 1)
    c_load, c_cost = claude_states[step_c]
    g_load, g_cost = gemini_states[step_g]
    stat_block(x_claude, c_load, c_cost, CLAUDE_BANNER)
    stat_block(x_gemini, g_load, g_cost, GEMINI_BANNER)

    return img


def _png_chunk(ctype, data):
    crc = zlib.crc32(ctype + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", crc)


def _extract_idat(png_bytes):
    """Return concatenated IDAT data from a single-image PNG."""
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    idat = bytearray()
    p = 8
    while p < len(png_bytes):
        length = struct.unpack(">I", png_bytes[p:p + 4])[0]
        ctype = png_bytes[p + 4:p + 8]
        payload = png_bytes[p + 8:p + 8 + length]
        if ctype == b"IDAT":
            idat.extend(payload)
        p += 8 + length + 4
        if ctype == b"IEND":
            break
    return bytes(idat)


def write_apng_full_frames(out_path, frames, durations_ms):
    """Write an APNG where every fcTL declares the full canvas (no bbox crop)."""
    w, h = frames[0].size
    for fr in frames:
        if fr.size != (w, h):
            raise ValueError("all frames must be the same size")

    out = open(out_path, "wb")
    try:
        out.write(b"\x89PNG\r\n\x1a\n")

        # IHDR: 8-bit truecolor RGB
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        out.write(_png_chunk(b"IHDR", ihdr))

        # acTL: total frames, 0 loops = infinite
        actl = struct.pack(">II", len(frames), 0)
        out.write(_png_chunk(b"acTL", actl))

        seq = 0
        for idx, (frame, dur_ms) in enumerate(zip(frames, durations_ms)):
            delay_num = dur_ms
            delay_den = 1000

            fctl = struct.pack(
                ">IIIIIHHBB",
                seq,
                w, h,
                0, 0,            # x_offset, y_offset
                delay_num, delay_den,
                0,               # dispose_op: NONE (frame is overwritten by next)
                0,               # blend_op: SOURCE (overwrite, don't alpha-blend)
            )
            out.write(_png_chunk(b"fcTL", fctl))
            seq += 1

            buf = io.BytesIO()
            frame.convert("RGB").save(buf, format="PNG", optimize=False, compress_level=6)
            idat_data = _extract_idat(buf.getvalue())

            if idx == 0:
                out.write(_png_chunk(b"IDAT", idat_data))
            else:
                fdat = struct.pack(">I", seq) + idat_data
                out.write(_png_chunk(b"fdAT", fdat))
                seq += 1

        out.write(_png_chunk(b"IEND", b""))
    finally:
        out.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--log', default='results.log')
    p.add_argument('--out', default='round10.mp4',
                   help="Output file. .mp4 = video, .png = animated PNG (APNG).")
    p.add_argument('--frames-dir', default=None,
                   help="Write PNG frames here instead of producing MP4/APNG.")
    args = p.parse_args()

    data = parse_round10(args.log)
    total = len(data["claude_tour"])
    if len(data["gemini_tour"]) != total:
        sys.exit("Tours have different lengths.")

    claude_states = compute_states(data["claude_tour"], data["weights"])
    gemini_states = compute_states(data["gemini_tour"], data["weights"])

    n_frames = total + HOLD_FINAL_FRAMES

    # APNG path: write manually with full-canvas frames (PIL's built-in APNG
    # writer crops each frame to its delta bounding box, which some viewers
    # mishandle).
    if args.out.lower().endswith(".png") and not args.frames_dir:
        frames = []
        for f in range(n_frames):
            step = min(f, total - 1)
            frames.append(render_frame(step, data, claude_states, gemini_states))
        durations_ms = [int(1000 / FPS)] * total + [int(1500 / FPS)] * HOLD_FINAL_FRAMES
        write_apng_full_frames(args.out, frames, durations_ms)
        print(f"Wrote {args.out}")
        return

    tmpdir = args.frames_dir or tempfile.mkdtemp(prefix="knight_frames_")
    os.makedirs(tmpdir, exist_ok=True)

    for f in range(n_frames):
        step = min(f, total - 1)
        img = render_frame(step, data, claude_states, gemini_states)
        img.save(os.path.join(tmpdir, f"frame_{f:04d}.png"))

    if args.frames_dir:
        print(f"Wrote {n_frames} frames to {tmpdir}")
        return

    # Prefer libx264 where available; fall back to h264_nvenc (NVIDIA) or mpeg4.
    encoders = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True, text=True, check=False,
    ).stdout
    if "libx264" in encoders:
        enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]
    elif "h264_nvenc" in encoders:
        enc = ["-c:v", "h264_nvenc", "-preset", "medium", "-cq", "20"]
    else:
        enc = ["-c:v", "mpeg4", "-qscale:v", "3"]

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(FPS),
        "-i", os.path.join(tmpdir, "frame_%04d.png"),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-pix_fmt", "yuv420p",
        *enc,
        args.out,
    ]
    print("Stitching with ffmpeg...")
    subprocess.check_call(cmd)
    shutil.rmtree(tmpdir)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
