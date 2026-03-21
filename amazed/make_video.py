"""
Generate an MP4 video of Round 93 maze navigation.
Renders every step as a frame, outputs frames to a temp dir, then ffmpeg stitches.
"""
from PIL import Image, ImageDraw, ImageFont
import re
import os
import subprocess
import shutil

CELL = 20  # larger for video
MARGIN = 90
FPS = 10  # steps per second

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
COL_CLAUDE_TRAIL = (120, 170, 255)
COL_GROK_TRAIL = (255, 160, 100)
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

def parse_moves(text):
    moves = []
    for line in text.strip().split('\n'):
        m = re.match(r'.*\((\d+), (\d+)\)->\((\d+), (\d+)\)(?:\s+TELEPORT->\((\d+), (\d+)\))?', line)
        if m:
            r1, c1, r2, c2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            tp = (int(m.group(5)), int(m.group(6))) if m.group(5) else None
            moves.append(((r1, c1), (r2, c2), tp))
    return moves

# Claude's 88 moves
CLAUDE_MOVES = """step   1: sent=D  (1, 1)->(2, 1)
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

# Grok's full 336 moves (first 100 + last stretch)
GROK_MOVES = """step   1: sent=D  (1, 1)->(2, 1)
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
step 100: sent=L  (15, 8)->(15, 7)
step 101: sent=D  (15, 7)->(16, 7)
step 102: sent=D  (16, 7)->(17, 7)
step 103: sent=D  (17, 7)->(18, 7)
step 104: sent=D  (18, 7)->(19, 7)
step 105: sent=D  (19, 7)->(20, 7)
step 106: sent=D  (20, 7)->(21, 7)
step 107: sent=L  (21, 7)->(21, 6)
step 108: sent=R  (21, 6)->(21, 7)
step 109: sent=R  (21, 7)->(21, 8)
step 110: sent=D  (21, 8)->(22, 8)
step 111: sent=D  (22, 8)->(23, 8)
step 112: sent=L  (23, 8)->(23, 7)
step 113: sent=D  (23, 7)->(24, 7)
step 114: sent=D  (24, 7)->(25, 7)
step 115: sent=L  (25, 7)->(25, 6)
step 116: sent=L  (25, 6)->(25, 5)
step 117: sent=U  (25, 5)->(24, 5)
step 118: sent=U  (24, 5)->(23, 5)
step 119: sent=L  (23, 5)->(23, 4)
step 120: sent=L  (23, 4)->(23, 3)
step 121: sent=D  (23, 3)->(24, 3)
step 122: sent=L  (24, 3)->(24, 2)
step 123: sent=D  (24, 2)->(25, 2)
step 124: sent=L  (25, 2)->(25, 1)
step 125: sent=D  (25, 1)->(26, 1)
step 126: sent=D  (26, 1)->(27, 1)
step 127: sent=R  (27, 1)->(27, 2)
step 128: sent=R  (27, 2)->(27, 3)
step 129: sent=R  (27, 3)->(27, 4)
step 130: sent=R  (27, 4)->(27, 5)
step 131: sent=R  (27, 5)->(27, 6)
step 132: sent=R  (27, 6)->(27, 7)
step 133: sent=R  (27, 7)->(27, 8)
step 134: sent=L  (27, 8)->(27, 7)
step 135: sent=L  (27, 7)->(27, 6)
step 136: sent=L  (27, 6)->(27, 5)
step 137: sent=L  (27, 5)->(27, 4)
step 138: sent=L  (27, 4)->(27, 3)
step 139: sent=U  (27, 3)->(26, 3)
step 140: sent=U  (26, 3)->(25, 3)
step 141: sent=U  (25, 3)->(24, 3)
step 142: sent=L  (24, 3)->(24, 2)
step 143: sent=L  (24, 2)->(24, 1)
step 144: sent=U  (24, 1)->(23, 1)
step 145: sent=U  (23, 1)->(22, 1)
step 146: sent=U  (22, 1)->(21, 1)
step 147: sent=U  (21, 1)->(20, 1)
step 148: sent=U  (20, 1)->(19, 1)
step 149: sent=U  (19, 1)->(18, 1)
step 150: sent=U  (18, 1)->(17, 1)
step 151: sent=R  (17, 1)->(17, 2)
step 152: sent=R  (17, 2)->(17, 3)
step 153: sent=R  (17, 3)->(17, 4)
step 154: sent=R  (17, 4)->(17, 5)
step 155: sent=U  (17, 5)->(16, 5)
step 156: sent=U  (16, 5)->(15, 5)
step 157: sent=U  (15, 5)->(14, 5)
step 158: sent=U  (14, 5)->(13, 5)
step 159: sent=L  (13, 5)->(13, 4)
step 160: sent=L  (13, 4)->(13, 3)
step 161: sent=L  (13, 3)->(13, 2)
step 162: sent=U  (13, 2)->(12, 2)
step 163: sent=R  (12, 2)->(12, 3)
step 164: sent=U  (12, 3)->(11, 3)
step 165: sent=U  (11, 3)->(10, 3)  TELEPORT->(25, 18)
step 166: sent=L  (25, 18)->(25, 17)
step 167: sent=D  (25, 17)->(26, 17)
step 168: sent=D  (26, 17)->(27, 17)
step 169: sent=L  (27, 17)->(27, 16)
step 170: sent=L  (27, 16)->(27, 15)
step 171: sent=L  (27, 15)->(27, 14)
step 172: sent=L  (27, 14)->(27, 13)
step 173: sent=L  (27, 13)->(27, 12)
step 174: sent=L  (27, 12)->(27, 11)
step 175: sent=U  (27, 11)->(26, 11)
step 176: sent=D  (26, 11)->(27, 11)
step 177: sent=R  (27, 11)->(27, 12)
step 178: sent=R  (27, 12)->(27, 13)
step 179: sent=R  (27, 13)->(27, 14)
step 180: sent=R  (27, 14)->(27, 15)
step 181: sent=R  (27, 15)->(27, 16)
step 182: sent=R  (27, 16)->(27, 17)
step 183: sent=U  (27, 17)->(26, 17)
step 184: sent=U  (26, 17)->(25, 17)
step 185: sent=R  (25, 17)->(25, 18)  TELEPORT->(10, 3)
step 186: sent=U  (10, 3)->(9, 3)
step 187: sent=R  (9, 3)->(9, 4)  TELEPORT->(24, 23)
step 188: sent=U  (24, 23)->(23, 23)
step 189: sent=U  (23, 23)->(22, 23)
step 190: sent=U  (22, 23)->(21, 23)
step 191: sent=U  (21, 23)->(20, 23)
step 192: sent=D  (20, 23)->(21, 23)
step 193: sent=L  (21, 23)->(21, 22)
step 194: sent=L  (21, 22)->(21, 21)
step 195: sent=D  (21, 21)->(22, 21)  TELEPORT->(5, 8)
step 196: sent=R  (5, 8)->(5, 9)
step 197: sent=U  (5, 9)->(4, 9)
step 198: sent=U  (4, 9)->(3, 9)
step 199: sent=R  (3, 9)->(3, 10)
step 200: sent=R  (3, 10)->(3, 11)
step 201: sent=U  (3, 11)->(2, 11)
step 202: sent=U  (2, 11)->(1, 11)
step 203: sent=L  (1, 11)->(1, 10)
step 204: sent=L  (1, 10)->(1, 9)
step 205: sent=L  (1, 9)->(1, 8)
step 206: sent=L  (1, 8)->(1, 7)
step 207: sent=D  (1, 7)->(2, 7)
step 208: sent=D  (2, 7)->(3, 7)
step 209: sent=L  (3, 7)->(3, 6)
step 210: sent=L  (3, 6)->(3, 5)
step 211: sent=L  (3, 5)->(3, 4)
step 212: sent=U  (3, 4)->(2, 4)
step 213: sent=D  (2, 4)->(3, 4)
step 214: sent=R  (3, 4)->(3, 5)
step 215: sent=R  (3, 5)->(3, 6)
step 216: sent=R  (3, 6)->(3, 7)
step 217: sent=U  (3, 7)->(2, 7)
step 218: sent=U  (2, 7)->(1, 7)
step 219: sent=R  (1, 7)->(1, 8)
step 220: sent=R  (1, 8)->(1, 9)
step 221: sent=R  (1, 9)->(1, 10)
step 222: sent=R  (1, 10)->(1, 11)
step 223: sent=R  (1, 11)->(1, 12)
step 224: sent=R  (1, 12)->(1, 13)
step 225: sent=R  (1, 13)->(1, 14)
step 226: sent=R  (1, 14)->(1, 15)
step 227: sent=R  (1, 15)->(1, 16)
step 228: sent=R  (1, 16)->(1, 17)
step 229: sent=R  (1, 17)->(1, 18)
step 230: sent=R  (1, 18)->(1, 19)
step 231: sent=D  (1, 19)->(2, 19)
step 232: sent=D  (2, 19)->(3, 19)
step 233: sent=R  (3, 19)->(3, 20)
step 234: sent=R  (3, 20)->(3, 21)
step 235: sent=R  (3, 21)->(3, 22)
step 236: sent=R  (3, 22)->(3, 23)
step 237: sent=U  (3, 23)->(2, 23)
step 238: sent=R  (2, 23)->(2, 24)
step 239: sent=R  (2, 24)->(2, 25)
step 240: sent=U  (2, 25)->(1, 25)
step 241: sent=R  (1, 25)->(1, 26)
step 242: sent=R  (1, 26)->(1, 27)
step 243: sent=D  (1, 27)->(2, 27)
step 244: sent=D  (2, 27)->(3, 27)
step 245: sent=D  (3, 27)->(4, 27)
step 246: sent=D  (4, 27)->(5, 27)
step 247: sent=D  (5, 27)->(6, 27)
step 248: sent=D  (6, 27)->(7, 27)
step 249: sent=D  (7, 27)->(8, 27)
step 250: sent=D  (8, 27)->(9, 27)
step 251: sent=D  (9, 27)->(10, 27)
step 252: sent=D  (10, 27)->(11, 27)
step 253: sent=L  (11, 27)->(11, 26)
step 254: sent=L  (11, 26)->(11, 25)
step 255: sent=D  (11, 25)->(12, 25)
step 256: sent=D  (12, 25)->(13, 25)
step 257: sent=D  (13, 25)->(14, 25)
step 258: sent=D  (14, 25)->(15, 25)
step 259: sent=D  (15, 25)->(16, 25)
step 260: sent=D  (16, 25)->(17, 25)
step 261: sent=L  (17, 25)->(17, 24)
step 262: sent=L  (17, 24)->(17, 23)
step 263: sent=U  (17, 23)->(16, 23)
step 264: sent=U  (16, 23)->(15, 23)
step 265: sent=U  (15, 23)->(14, 23)
step 266: sent=U  (14, 23)->(13, 23)
step 267: sent=U  (13, 23)->(12, 23)
step 268: sent=U  (12, 23)->(11, 23)
step 269: sent=U  (11, 23)->(10, 23)
step 270: sent=U  (10, 23)->(9, 23)
step 271: sent=L  (9, 23)->(9, 22)
step 272: sent=L  (9, 22)->(9, 21)
step 273: sent=U  (9, 21)->(8, 21)
step 274: sent=D  (8, 21)->(9, 21)
step 275: sent=D  (9, 21)->(10, 21)
step 276: sent=D  (10, 21)->(11, 21)
step 277: sent=D  (11, 21)->(12, 21)
step 278: sent=D  (12, 21)->(13, 21)
step 279: sent=L  (13, 21)->(13, 20)
step 280: sent=R  (13, 20)->(13, 21)
step 281: sent=U  (13, 21)->(12, 21)
step 282: sent=U  (12, 21)->(11, 21)
step 283: sent=U  (11, 21)->(10, 21)
step 284: sent=U  (10, 21)->(9, 21)
step 285: sent=R  (9, 21)->(9, 22)
step 286: sent=R  (9, 22)->(9, 23)
step 287: sent=R  (9, 23)->(9, 24)
step 288: sent=R  (9, 24)->(9, 25)
step 289: sent=U  (9, 25)->(8, 25)
step 290: sent=D  (8, 25)->(9, 25)
step 291: sent=L  (9, 25)->(9, 24)
step 292: sent=L  (9, 24)->(9, 23)
step 293: sent=D  (9, 23)->(10, 23)
step 294: sent=D  (10, 23)->(11, 23)
step 295: sent=D  (11, 23)->(12, 23)
step 296: sent=D  (12, 23)->(13, 23)
step 297: sent=D  (13, 23)->(14, 23)
step 298: sent=D  (14, 23)->(15, 23)
step 299: sent=D  (15, 23)->(16, 23)
step 300: sent=D  (16, 23)->(17, 23)
step 301: sent=L  (17, 23)->(17, 22)
step 302: sent=L  (17, 22)->(17, 21)
step 303: sent=U  (17, 21)->(16, 21)
step 304: sent=U  (16, 21)->(15, 21)
step 305: sent=L  (15, 21)->(15, 20)
step 306: sent=R  (15, 20)->(15, 21)
step 307: sent=D  (15, 21)->(16, 21)
step 308: sent=D  (16, 21)->(17, 21)
step 309: sent=R  (17, 21)->(17, 22)
step 310: sent=R  (17, 22)->(17, 23)
step 311: sent=R  (17, 23)->(17, 24)
step 312: sent=R  (17, 24)->(17, 25)
step 313: sent=U  (17, 25)->(16, 25)
step 314: sent=U  (16, 25)->(15, 25)
step 315: sent=U  (15, 25)->(14, 25)
step 316: sent=U  (14, 25)->(13, 25)
step 317: sent=R  (13, 25)->(13, 26)
step 318: sent=R  (13, 26)->(13, 27)
step 319: sent=D  (13, 27)->(14, 27)
step 320: sent=D  (14, 27)->(15, 27)
step 321: sent=D  (15, 27)->(16, 27)
step 322: sent=D  (16, 27)->(17, 27)
step 323: sent=D  (17, 27)->(18, 27)
step 324: sent=D  (18, 27)->(19, 27)
step 325: sent=D  (19, 27)->(20, 27)
step 326: sent=D  (20, 27)->(21, 27)
step 327: sent=L  (21, 27)->(21, 26)
step 328: sent=L  (21, 26)->(21, 25)
step 329: sent=D  (21, 25)->(22, 25)
step 330: sent=D  (22, 25)->(23, 25)
step 331: sent=D  (23, 25)->(24, 25)
step 332: sent=D  (24, 25)->(25, 25)
step 333: sent=R  (25, 25)->(25, 26)
step 334: sent=R  (25, 26)->(25, 27)
step 335: sent=D  (25, 27)->(26, 27)
step 336: sent=D  (26, 27)->(27, 27)"""

claude_moves = parse_moves(CLAUDE_MOVES)
grok_moves = parse_moves(GROK_MOVES)

def build_positions(moves):
    positions = [(1, 1)]
    for (r1, c1), (r2, c2), tp in moves:
        if tp:
            positions.append(tp)
        else:
            positions.append((r2, c2))
    return positions

claude_pos = build_positions(claude_moves)
grok_pos = build_positions(grok_moves)

W = COLS * CELL
H = ROWS * CELL + MARGIN

def draw_maze(draw):
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
                draw.text((x + 5, y + 2), ch, fill=(255, 255, 255))
            else:
                draw.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COL_FLOOR)

def draw_trail(draw, positions, step, trail_color, head_color, offset=(0, 0)):
    ox, oy = offset
    n = min(step + 1, len(positions))
    for i in range(n):
        r, c = positions[i]
        x, y = c * CELL + ox, r * CELL + MARGIN + oy
        if i == n - 1:
            draw.ellipse([x + 3, y + 3, x + CELL - 4, y + CELL - 4], fill=head_color)
        else:
            draw.ellipse([x + 5, y + 5, x + CELL - 6, y + CELL - 6], fill=trail_color)

def draw_header(draw, step):
    c_step = min(step, len(claude_pos) - 1)
    g_step = min(step, len(grok_pos) - 1)
    c_label = "DONE!" if step >= len(claude_pos) - 1 else f"step {c_step}"
    g_label = "DONE!" if step >= len(grok_pos) - 1 else f"step {g_step}"

    draw.text((5, 5), f"Round 93  |  Claude (88 steps) vs Grok (336 steps)", fill=(0, 0, 0))
    draw.text((5, 22), f"Claude: {c_label}", fill=COL_CLAUDE)
    draw.text((W // 2, 22), f"Grok: {g_label}", fill=COL_GROK)

    # Legend
    ly = 42
    draw.rectangle([5, ly, 15, ly + 10], fill=COL_START)
    draw.text((19, ly - 1), "Start", fill=(0, 0, 0))
    draw.rectangle([70, ly, 80, ly + 10], fill=COL_EXIT)
    draw.text((84, ly - 1), "Exit", fill=(0, 0, 0))
    draw.rectangle([120, ly, 130, ly + 10], fill=COL_PORTAL)
    draw.text((134, ly - 1), "A-D = Teleportals (paired)", fill=(0, 0, 0))
    draw.rectangle([350, ly, 360, ly + 10], fill=COL_WALL)
    draw.text((364, ly - 1), "Wall", fill=(0, 0, 0))

    ly2 = 58
    draw.ellipse([7, ly2 + 1, 17, ly2 + 11], fill=COL_CLAUDE)
    draw.text((21, ly2), "Claude path", fill=COL_CLAUDE)
    draw.ellipse([140, ly2 + 1, 150, ly2 + 11], fill=COL_GROK)
    draw.text((154, ly2), "Grok path", fill=COL_GROK)

# Generate frames
FRAME_DIR = "/tmp/maze_frames"
if os.path.exists(FRAME_DIR):
    shutil.rmtree(FRAME_DIR)
os.makedirs(FRAME_DIR)

max_steps = max(len(claude_pos), len(grok_pos))
frame_num = 0

# 1 second of title card
for _ in range(FPS):
    img = Image.new('RGB', (W, H), COL_BG)
    draw = ImageDraw.Draw(img)
    draw_header(draw, 0)
    draw_maze(draw)
    draw_trail(draw, claude_pos, 0, COL_CLAUDE_TRAIL, COL_CLAUDE_HEAD, offset=(-2, -2))
    draw_trail(draw, grok_pos, 0, COL_GROK_TRAIL, COL_GROK_HEAD, offset=(2, 2))
    img.save(f"{FRAME_DIR}/frame_{frame_num:05d}.png")
    frame_num += 1

# Main animation: every step
for step in range(1, max_steps):
    img = Image.new('RGB', (W, H), COL_BG)
    draw = ImageDraw.Draw(img)
    draw_header(draw, step)
    draw_maze(draw)
    g_step = min(step, len(grok_pos) - 1)
    c_step = min(step, len(claude_pos) - 1)
    draw_trail(draw, grok_pos, g_step, COL_GROK_TRAIL, COL_GROK_HEAD, offset=(2, 2))
    draw_trail(draw, claude_pos, c_step, COL_CLAUDE_TRAIL, COL_CLAUDE_HEAD, offset=(-2, -2))
    img.save(f"{FRAME_DIR}/frame_{frame_num:05d}.png")
    frame_num += 1

# Hold last frame for 3 seconds
for _ in range(FPS * 3):
    img.save(f"{FRAME_DIR}/frame_{frame_num:05d}.png")
    frame_num += 1

print(f"Generated {frame_num} frames")

# Stitch with ffmpeg
out = "round93.mp4"
subprocess.run([
    "ffmpeg", "-y",
    "-framerate", str(FPS),
    "-i", f"{FRAME_DIR}/frame_%05d.png",
    "-c:v", "h264_nvenc",
    "-pix_fmt", "yuv420p",
    "-qp", "18",
    out
], check=True)

shutil.rmtree(FRAME_DIR)
print(f"Saved {out}")
