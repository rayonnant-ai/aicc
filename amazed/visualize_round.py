"""
Generate an animated PNG showing bot paths through a maze round.
Usage: python visualize_round.py
"""
from PIL import Image, ImageDraw, ImageFont
import re

CELL = 16  # pixels per cell
MARGIN = 70  # top margin for labels + legend

# Colors
COL_WALL = (40, 40, 40)
COL_FLOOR = (220, 220, 220)
COL_START = (0, 180, 0)
COL_EXIT = (180, 0, 0)
COL_PORTAL = (180, 130, 0)
COL_CLAUDE = (0, 100, 220)
COL_GROK = (220, 80, 0)
COL_CLAUDE_HEAD = (0, 60, 180)
COL_GROK_HEAD = (180, 50, 0)
COL_BG = (255, 255, 255)

# Round 93 maze
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

# Parse move sequences
def parse_moves(text):
    """Parse step lines into list of ((r1,c1), (r2,c2), teleport_dest_or_none)"""
    moves = []
    for line in text.strip().split('\n'):
        m = re.match(r'.*\((\d+), (\d+)\)->\((\d+), (\d+)\)(?:\s+TELEPORT->\((\d+), (\d+)\))?', line)
        if m:
            r1, c1, r2, c2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            if m.group(5):
                tr, tc = int(m.group(5)), int(m.group(6))
                moves.append(((r1, c1), (r2, c2), (tr, tc)))
            else:
                moves.append(((r1, c1), (r2, c2), None))
    return moves

CLAUDE_MOVES_TEXT = """\
step   1: sent=D  (1, 1)->(2, 1)
step   2: sent=D  (2, 1)->(3, 1)
step   3: sent=D  (3, 1)->(4, 1)
step   4: sent=D  (4, 1)->(5, 1)
step   5: sent=D  (5, 1)->(6, 1)
step   6: sent=D  (6, 1)->(7, 1)
step   7: sent=R  (7, 1)->(7, 2)
step   8: sent=R  (7, 2)->(7, 3)
step   9: sent=D  (7, 3)->(8, 3)
step  10: sent=U  (8, 3)->(7, 3)
step  11: sent=U  (7, 3)->(6, 3)
step  12: sent=U  (6, 3)->(5, 3)
step  13: sent=R  (5, 3)->(5, 4)
step  14: sent=R  (5, 4)->(5, 5)
step  15: sent=R  (5, 5)->(5, 6)
step  16: sent=L  (5, 6)->(5, 5)
step  17: sent=U  (5, 5)->(4, 5)
step  18: sent=U  (4, 5)->(3, 5)
step  19: sent=R  (3, 5)->(3, 6)
step  20: sent=R  (3, 6)->(3, 7)
step  21: sent=U  (3, 7)->(2, 7)
step  22: sent=U  (2, 7)->(1, 7)
step  23: sent=R  (1, 7)->(1, 8)
step  24: sent=R  (1, 8)->(1, 9)
step  25: sent=R  (1, 9)->(1, 10)
step  26: sent=R  (1, 10)->(1, 11)
step  27: sent=D  (1, 11)->(2, 11)
step  28: sent=U  (2, 11)->(1, 11)
step  29: sent=R  (1, 11)->(1, 12)
step  30: sent=R  (1, 12)->(1, 13)
step  31: sent=R  (1, 13)->(1, 14)
step  32: sent=R  (1, 14)->(1, 15)
step  33: sent=R  (1, 15)->(1, 16)
step  34: sent=R  (1, 16)->(1, 17)
step  35: sent=R  (1, 17)->(1, 18)
step  36: sent=R  (1, 18)->(1, 19)
step  37: sent=D  (1, 19)->(2, 19)
step  38: sent=D  (2, 19)->(3, 19)
step  39: sent=R  (3, 19)->(3, 20)
step  40: sent=R  (3, 20)->(3, 21)
step  41: sent=R  (3, 21)->(3, 22)
step  42: sent=R  (3, 22)->(3, 23)
step  43: sent=R  (3, 23)->(3, 24)
step  44: sent=R  (3, 24)->(3, 25)
step  45: sent=D  (3, 25)->(4, 25)
step  46: sent=D  (4, 25)->(5, 25)
step  47: sent=D  (5, 25)->(6, 25)
step  48: sent=D  (6, 25)->(7, 25)
step  49: sent=D  (7, 25)->(8, 25)
step  50: sent=D  (8, 25)->(9, 25)
step  51: sent=L  (9, 25)->(9, 24)
step  52: sent=L  (9, 24)->(9, 23)
step  53: sent=D  (9, 23)->(10, 23)
step  54: sent=D  (10, 23)->(11, 23)
step  55: sent=D  (11, 23)->(12, 23)
step  56: sent=D  (12, 23)->(13, 23)
step  57: sent=D  (13, 23)->(14, 23)
step  58: sent=D  (14, 23)->(15, 23)
step  59: sent=D  (15, 23)->(16, 23)
step  60: sent=D  (16, 23)->(17, 23)
step  61: sent=R  (17, 23)->(17, 24)
step  62: sent=R  (17, 24)->(17, 25)
step  63: sent=D  (17, 25)->(18, 25)
step  64: sent=U  (18, 25)->(17, 25)
step  65: sent=U  (17, 25)->(16, 25)
step  66: sent=U  (16, 25)->(15, 25)
step  67: sent=U  (15, 25)->(14, 25)
step  68: sent=U  (14, 25)->(13, 25)
step  69: sent=R  (13, 25)->(13, 26)
step  70: sent=R  (13, 26)->(13, 27)
step  71: sent=D  (13, 27)->(14, 27)
step  72: sent=D  (14, 27)->(15, 27)
step  73: sent=D  (15, 27)->(16, 27)
step  74: sent=D  (16, 27)->(17, 27)
step  75: sent=D  (17, 27)->(18, 27)
step  76: sent=D  (18, 27)->(19, 27)
step  77: sent=D  (19, 27)->(20, 27)
step  78: sent=D  (20, 27)->(21, 27)
step  79: sent=L  (21, 27)->(21, 26)
step  80: sent=L  (21, 26)->(21, 25)
step  81: sent=D  (21, 25)->(22, 25)
step  82: sent=D  (22, 25)->(23, 25)
step  83: sent=D  (23, 25)->(24, 25)
step  84: sent=D  (24, 25)->(25, 25)
step  85: sent=R  (25, 25)->(25, 26)
step  86: sent=R  (25, 26)->(25, 27)
step  87: sent=D  (25, 27)->(26, 27)
step  88: sent=D  (26, 27)->(27, 27)"""

GROK_MOVES_TEXT = """\
step   1: sent=D  (1, 1)->(2, 1)
step   2: sent=D  (2, 1)->(3, 1)
step   3: sent=D  (3, 1)->(4, 1)
step   4: sent=D  (4, 1)->(5, 1)
step   5: sent=D  (5, 1)->(6, 1)
step   6: sent=D  (6, 1)->(7, 1)
step   7: sent=R  (7, 1)->(7, 2)
step   8: sent=R  (7, 2)->(7, 3)
step   9: sent=D  (7, 3)->(8, 3)
step  10: sent=D  (8, 3)->(9, 3)
step  11: sent=D  (9, 3)->(10, 3)  TELEPORT->(25, 18)
step  12: sent=L  (25, 18)->(25, 17)
step  13: sent=U  (25, 17)->(24, 17)
step  14: sent=U  (24, 17)->(23, 17)
step  15: sent=L  (23, 17)->(23, 16)
step  16: sent=L  (23, 16)->(23, 15)
step  17: sent=U  (23, 15)->(22, 15)
step  18: sent=U  (22, 15)->(21, 15)
step  19: sent=L  (21, 15)->(21, 14)
step  20: sent=L  (21, 14)->(21, 13)
step  21: sent=U  (21, 13)->(20, 13)
step  22: sent=U  (20, 13)->(19, 13)
step  23: sent=L  (19, 13)->(19, 12)
step  24: sent=L  (19, 12)->(19, 11)
step  25: sent=U  (19, 11)->(18, 11)
step  26: sent=U  (18, 11)->(17, 11)
step  27: sent=L  (17, 11)->(17, 10)
step  28: sent=R  (17, 10)->(17, 11)
step  29: sent=R  (17, 11)->(17, 12)
step  30: sent=R  (17, 12)->(17, 13)
step  31: sent=U  (17, 13)->(16, 13)
step  32: sent=U  (16, 13)->(15, 13)
step  33: sent=R  (15, 13)->(15, 14)
step  34: sent=R  (15, 14)->(15, 15)
step  35: sent=D  (15, 15)->(16, 15)
step  36: sent=D  (16, 15)->(17, 15)
step  37: sent=D  (17, 15)->(18, 15)
step  38: sent=D  (18, 15)->(19, 15)
step  39: sent=R  (19, 15)->(19, 16)
step  40: sent=R  (19, 16)->(19, 17)
step  41: sent=R  (19, 17)->(19, 18)
step  42: sent=R  (19, 18)->(19, 19)
step  43: sent=D  (19, 19)->(20, 19)
step  44: sent=D  (20, 19)->(21, 19)
step  45: sent=R  (21, 19)->(21, 20)
step  46: sent=R  (21, 20)->(21, 21)
step  47: sent=D  (21, 21)->(22, 21)  TELEPORT->(5, 8)
step  48: sent=L  (5, 8)->(5, 7)
step  49: sent=R  (5, 7)->(5, 8)  TELEPORT->(22, 21)
step  50: sent=D  (22, 21)->(23, 21)
step  51: sent=D  (23, 21)->(24, 21)
step  52: sent=D  (24, 21)->(25, 21)
step  53: sent=D  (25, 21)->(26, 21)
step  54: sent=U  (26, 21)->(25, 21)
step  55: sent=R  (25, 21)->(25, 22)
step  56: sent=R  (25, 22)->(25, 23)
step  57: sent=U  (25, 23)->(24, 23)  TELEPORT->(9, 4)
step  58: sent=R  (9, 4)->(9, 5)
step  59: sent=D  (9, 5)->(10, 5)
step  60: sent=U  (10, 5)->(9, 5)
step  61: sent=R  (9, 5)->(9, 6)
step  62: sent=R  (9, 6)->(9, 7)
step  63: sent=R  (9, 7)->(9, 8)
step  64: sent=R  (9, 8)->(9, 9)
step  65: sent=U  (9, 9)->(8, 9)
step  66: sent=U  (8, 9)->(7, 9)
step  67: sent=R  (7, 9)->(7, 10)
step  68: sent=R  (7, 10)->(7, 11)
step  69: sent=R  (7, 11)->(7, 12)
step  70: sent=R  (7, 12)->(7, 13)
step  71: sent=U  (7, 13)->(6, 13)
step  72: sent=U  (6, 13)->(5, 13)
step  73: sent=U  (5, 13)->(4, 13)
step  74: sent=U  (4, 13)->(3, 13)
step  75: sent=R  (3, 13)->(3, 14)
step  76: sent=R  (3, 14)->(3, 15)
step  77: sent=D  (3, 15)->(4, 15)
step  78: sent=D  (4, 15)->(5, 15)
step  79: sent=D  (5, 15)->(6, 15)
step  80: sent=D  (6, 15)->(7, 15)
step  81: sent=R  (7, 15)->(7, 16)
step  82: sent=R  (7, 16)->(7, 17)
step  83: sent=D  (7, 17)->(8, 17)
step  84: sent=D  (8, 17)->(9, 17)
step  85: sent=L  (9, 17)->(9, 16)
step  86: sent=L  (9, 16)->(9, 15)
step  87: sent=D  (9, 15)->(10, 15)
step  88: sent=D  (10, 15)->(11, 15)
step  89: sent=L  (11, 15)->(11, 14)
step  90: sent=L  (11, 14)->(11, 13)
step  91: sent=D  (11, 13)->(12, 13)
step  92: sent=L  (12, 13)->(12, 12)
step  93: sent=L  (12, 12)->(12, 11)
step  94: sent=L  (12, 11)->(12, 10)
step  95: sent=L  (12, 10)->(12, 9)
step  96: sent=D  (12, 9)->(13, 9)
step  97: sent=D  (13, 9)->(14, 9)
step  98: sent=D  (14, 9)->(15, 9)
step  99: sent=L  (15, 9)->(15, 8)
step 100: sent=L  (15, 8)->(15, 7)"""

# Only include first 100 of grok's 336 moves to keep the animation manageable
# The full path continues but the pattern is clear

claude_moves = parse_moves(CLAUDE_MOVES_TEXT)
grok_moves = parse_moves(GROK_MOVES_TEXT)

def build_positions(moves):
    """Build list of positions at each step (handling teleports)."""
    positions = [(1, 1)]  # start
    for (r1, c1), (r2, c2), tp in moves:
        if tp:
            positions.append(tp)  # landed at teleport dest
        else:
            positions.append((r2, c2))
    return positions

claude_pos = build_positions(claude_moves)
grok_pos = build_positions(grok_moves)

def draw_maze(draw, w, h):
    """Draw the base maze."""
    for r in range(ROWS):
        for c in range(COLS):
            x, y = c * CELL, r * CELL + MARGIN
            ch = MAZE[r][c] if c < len(MAZE[r]) else '#'
            if ch == '#':
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_WALL)
            elif ch == '>':
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_START)
            elif ch == '<':
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_EXIT)
            elif ch.isupper():
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_PORTAL)
                try:
                    draw.text((x + 3, y + 1), ch, fill=(255, 255, 255))
                except:
                    pass
            else:
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_FLOOR)

def draw_trail(draw, positions, step, color, head_color, offset=(0, 0)):
    """Draw trail up to step, with head marker."""
    ox, oy = offset
    for i in range(min(step + 1, len(positions))):
        r, c = positions[i]
        x, y = c * CELL + ox, r * CELL + MARGIN + oy
        if i == min(step, len(positions) - 1):
            # Head - larger dot
            draw.ellipse([x + 2, y + 2, x + CELL - 3, y + CELL - 3], fill=head_color)
        else:
            # Trail - small dot
            draw.ellipse([x + 4, y + 4, x + CELL - 5, y + CELL - 5], fill=color)

W = COLS * CELL
H = ROWS * CELL + MARGIN

# Generate frames - step through both bots simultaneously
max_steps = max(len(claude_pos), len(grok_pos))
# Sample frames: every 2 steps for first 100, every 10 after
frame_steps = []
for s in range(0, min(100, max_steps), 2):
    frame_steps.append(s)
for s in range(100, max_steps, 10):
    frame_steps.append(s)
frame_steps.append(max_steps - 1)
# Also add key moments: claude finish (88), grok teleports
frame_steps.extend([11, 47, 57, 88])
frame_steps = sorted(set(frame_steps))

frames = []
for step in frame_steps:
    img = Image.new('RGB', (W, H), COL_BG)
    draw = ImageDraw.Draw(img)

    # Header
    c_step = min(step, len(claude_pos) - 1)
    g_step = min(step, len(grok_pos) - 1)
    c_done = "DONE" if step >= len(claude_pos) - 1 else f"step {c_step}"
    g_done = f"step {g_step}" if step < len(grok_pos) else f"step {len(grok_pos)-1}"

    draw.text((5, 5), f"Round 93 — Step {step}", fill=(0, 0, 0))
    draw.text((5, 20), f"Claude: {c_done} (88 total)", fill=COL_CLAUDE)
    draw.text((W // 2, 20), f"Grok: {g_done} (336 total)", fill=COL_GROK)

    # Legend row
    lx = 5
    ly = 38
    draw.rectangle([lx, ly, lx + 10, ly + 10], fill=COL_START)
    draw.text((lx + 14, ly - 1), "Start", fill=(0, 0, 0))
    lx += 60
    draw.rectangle([lx, ly, lx + 10, ly + 10], fill=COL_EXIT)
    draw.text((lx + 14, ly - 1), "Exit", fill=(0, 0, 0))
    lx += 50
    draw.rectangle([lx, ly, lx + 10, ly + 10], fill=COL_PORTAL)
    draw.text((lx + 14, ly - 1), "A-D = Teleportals (paired)", fill=(0, 0, 0))
    lx += 195
    draw.rectangle([lx, ly, lx + 10, ly + 10], fill=COL_WALL)
    draw.text((lx + 14, ly - 1), "Wall", fill=(0, 0, 0))

    # Bot legend
    ly2 = 52
    draw.ellipse([7, ly2 + 1, 15, ly2 + 9], fill=COL_CLAUDE)
    draw.text((19, ly2 - 1), "Claude path", fill=COL_CLAUDE)
    draw.ellipse([107, ly2 + 1, 115, ly2 + 9], fill=COL_GROK)
    draw.text((119, ly2 - 1), "Grok path", fill=COL_GROK)

    draw_maze(draw, W, H)

    # Draw grok trail first (underneath), offset slightly
    draw_trail(draw, grok_pos, g_step, (*COL_GROK, 140), COL_GROK_HEAD, offset=(2, 2))
    # Draw claude trail on top
    draw_trail(draw, claude_pos, c_step, (*COL_CLAUDE, 140), COL_CLAUDE_HEAD, offset=(-2, -2))

    frames.append(img)

# Add a final frame held longer
frames.append(frames[-1].copy())

# Save as APNG
frames[0].save(
    'round93.png',
    save_all=True,
    append_images=frames[1:],
    duration=[150] * (len(frames) - 1) + [3000],  # last frame held 3s
    loop=0
)
print(f"Saved round93.png ({len(frames)} frames)")
