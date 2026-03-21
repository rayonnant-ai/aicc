"""
Generate animated PNG + MP4 of Round 93 with fog of war.
Two panels side by side: Claude's view (left) vs Grok's view (right).
"""
from PIL import Image, ImageDraw
import re
import os
import subprocess
import shutil

CELL = 14
MARGIN_TOP = 75
GAP = 20  # gap between panels
FPS = 10

# Colors
COL_WALL = (40, 40, 40)
COL_FLOOR = (220, 220, 220)
COL_START = (0, 180, 0)
COL_EXIT = (180, 0, 0)
COL_PORTAL = (180, 130, 0)
COL_FOG = (25, 25, 30)
COL_CLAUDE = (0, 100, 220)
COL_GROK = (220, 80, 0)
COL_CLAUDE_HEAD = (50, 130, 255)
COL_GROK_HEAD = (255, 120, 40)
COL_CLAUDE_TRAIL = (100, 155, 240)
COL_GROK_TRAIL = (240, 150, 90)
COL_BG = (255, 255, 255)

MAZE_STR = """\
#############################
#>#   #             #   #   #
# #  ## ### ####### # #   # #
#       #   #   # #       # #
# ### ### ### # # ####### # #
# #     D #     #         # #
# # ######### # ### ##### # #
#   #   #     #   #     # # #
### ### # # # ### # # ### # #
# C B     # # #   #       # #
# #A# #####   # ###   # ### #
# # #     # #       #   #   #
#   #####     #### ## # # ###
#       # # #         # #   #
# ###   # # ########### # # #
#   #       #   #     # # # #
#####   ##### # # ### # # # #
#     # #     # #   #     # #
#  #### # # ### ######### # #
#   # # #     #     #   # # #
# # # # ##### ### # # # ### #
#   #       #     #     #   #
# ###### ## ### #### D# # ###
# #   #   # #       C # # # #
#   # # # ### ### ### #B# # #
#   #   #   #   # A #   #   #
# # ####### ### # # # ##### #
#         #       #        <#
#############################"""

MAZE = MAZE_STR.split('\n')
ROWS = len(MAZE)
COLS = len(MAZE[0])

PANEL_W = COLS * CELL
PANEL_H = ROWS * CELL
W = PANEL_W * 2 + GAP
H = PANEL_H + MARGIN_TOP

def parse_moves(text):
    moves = []
    for line in text.strip().split('\n'):
        m = re.match(r'.*\((\d+), (\d+)\)->\((\d+), (\d+)\)(?:\s+TELEPORT->\((\d+), (\d+)\))?', line)
        if m:
            r1, c1, r2, c2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            tp = (int(m.group(5)), int(m.group(6))) if m.group(5) else None
            moves.append(((r1, c1), (r2, c2), tp))
    return moves

def build_positions(moves):
    positions = [(1, 1)]
    for (r1, c1), (r2, c2), tp in moves:
        positions.append(tp if tp else (r2, c2))
    return positions

def build_visibility(positions, step):
    seen = set()
    for i in range(min(step + 1, len(positions))):
        pr, pc = positions[i]
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r, c = pr + dr, pc + dc
                if 0 <= r < ROWS and 0 <= c < COLS:
                    seen.add((r, c))
    return seen

# Read moves from results.log
with open("results.log", "r") as f:
    content = f.read()

r93_start = content.index("==================== ROUND 93 ====================")
r94_start = content.index("==================== ROUND 94 ====================")
r93_block = content[r93_start:r94_start]

claude_section = r93_block[r93_block.index("BOT: claude_bot"):r93_block.index("BOT: grok_bot  ROUND")]
grok_section = r93_block[r93_block.index("BOT: grok_bot  ROUND"):]
if "BOT: claude_bot  STATUS:" in grok_section:
    grok_section = grok_section[:grok_section.index("BOT: claude_bot  STATUS:")]

claude_moves = parse_moves(claude_section)
grok_moves = parse_moves(grok_section)
claude_pos = build_positions(claude_moves)
grok_pos = build_positions(grok_moves)

print(f"Claude: {len(claude_pos)} positions ({len(claude_moves)} moves)")
print(f"Grok: {len(grok_pos)} positions ({len(grok_moves)} moves)")

def draw_panel(draw, x_off, positions, step, seen, trail_color, head_color, label, label_color):
    """Draw one maze panel at x_off."""
    s = min(step, len(positions) - 1)

    for r in range(ROWS):
        for c in range(COLS):
            x = x_off + c * CELL
            y = MARGIN_TOP + r * CELL

            if (r, c) not in seen:
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_FOG)
                continue

            ch = MAZE[r][c] if c < len(MAZE[r]) else '#'
            if ch == '#':
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_WALL)
            elif ch == '>':
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_START)
            elif ch == '<':
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_EXIT)
            elif ch.isupper():
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_PORTAL)
                draw.text((x + 3, y + 1), ch, fill=(255, 255, 255))
            else:
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_FLOOR)

    # Trail
    for i in range(s + 1):
        r, c = positions[i]
        x = x_off + c * CELL
        y = MARGIN_TOP + r * CELL
        if i == s:
            draw.ellipse([x + 2, y + 2, x + CELL - 3, y + CELL - 3], fill=head_color)
        else:
            draw.ellipse([x + 4, y + 4, x + CELL - 5, y + CELL - 5], fill=trail_color)

    # Panel label
    done = step >= len(positions) - 1
    status = "DONE!" if done else f"step {s}/{len(positions)-1}"
    draw.text((x_off + 5, MARGIN_TOP - 15), f"{label}: {status}", fill=label_color)

def render_frame(step):
    img = Image.new('RGB', (W, H), COL_BG)
    draw = ImageDraw.Draw(img)

    c_step = min(step, len(claude_pos) - 1)
    g_step = min(step, len(grok_pos) - 1)

    claude_seen = build_visibility(claude_pos, c_step)
    grok_seen = build_visibility(grok_pos, g_step)

    # Left panel: Claude
    draw_panel(draw, 0, claude_pos, step, claude_seen,
               COL_CLAUDE_TRAIL, COL_CLAUDE_HEAD, "Claude (88 steps)", COL_CLAUDE)

    # Right panel: Grok
    draw_panel(draw, PANEL_W + GAP, grok_pos, step, grok_seen,
               COL_GROK_TRAIL, COL_GROK_HEAD, "Grok (336 steps)", COL_GROK)

    # Gap divider
    draw.rectangle([PANEL_W, MARGIN_TOP, PANEL_W + GAP - 1, H - 1], fill=(180, 180, 180))

    # Header
    draw.text((5, 3), "Round 93: Fog of War — Each bot only sees a 5x5 window", fill=(0, 0, 0))

    ly = 22
    draw.rectangle([5, ly, 15, ly + 10], fill=COL_FOG)
    draw.text((19, ly - 1), "Unseen", fill=(80, 80, 80))
    draw.rectangle([85, ly, 95, ly + 10], fill=COL_START)
    draw.text((99, ly - 1), "Start", fill=(0, 0, 0))
    draw.rectangle([145, ly, 155, ly + 10], fill=COL_EXIT)
    draw.text((159, ly - 1), "Exit", fill=(0, 0, 0))
    draw.rectangle([200, ly, 210, ly + 10], fill=COL_PORTAL)
    draw.text((214, ly - 1), "A-D = Teleportals (paired)", fill=(0, 0, 0))
    draw.rectangle([430, ly, 440, ly + 10], fill=COL_WALL)
    draw.text((444, ly - 1), "Wall", fill=(0, 0, 0))

    # Step counter
    draw.text((5, 40), f"Step {step}", fill=(0, 0, 0))

    return img

max_steps = max(len(claude_pos), len(grok_pos))

# ── APNG ───────────────────────────────────────────
print("Generating APNG...")
apng_steps = list(range(0, min(90, max_steps), 2))
apng_steps += list(range(90, max_steps, 6))
apng_steps.append(max_steps - 1)
apng_steps.extend([0, 11, 47, 57, 88])
apng_steps = sorted(set(s for s in apng_steps if s < max_steps))

apng_frames = [render_frame(s) for s in apng_steps]
durations = [200] * len(apng_frames)
durations[-1] = 4000

apng_frames[0].save(
    'round93_fog.png',
    save_all=True,
    append_images=apng_frames[1:],
    duration=durations,
    loop=0
)
print(f"Saved round93_fog.png ({len(apng_frames)} frames)")

# ── MP4 ────────────────────────────────────────────
print("Generating MP4 frames...")
FRAME_DIR = "/tmp/maze_fog_frames"
if os.path.exists(FRAME_DIR):
    shutil.rmtree(FRAME_DIR)
os.makedirs(FRAME_DIR)

frame_num = 0

# Title: 1s
img0 = render_frame(0)
for _ in range(FPS):
    img0.save(f"{FRAME_DIR}/frame_{frame_num:05d}.png")
    frame_num += 1

# Every step
for step in range(1, max_steps):
    img = render_frame(step)
    img.save(f"{FRAME_DIR}/frame_{frame_num:05d}.png")
    frame_num += 1

# Hold final: 3s
for _ in range(FPS * 3):
    img.save(f"{FRAME_DIR}/frame_{frame_num:05d}.png")
    frame_num += 1

print(f"Generated {frame_num} frames, encoding...")

subprocess.run([
    "ffmpeg", "-y",
    "-framerate", str(FPS),
    "-i", f"{FRAME_DIR}/frame_%05d.png",
    "-c:v", "h264_nvenc",
    "-pix_fmt", "yuv420p",
    "-qp", "18",
    "round93_fog.mp4"
], check=True)

shutil.rmtree(FRAME_DIR)
print("Saved round93_fog.mp4")
