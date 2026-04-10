#!/usr/bin/env python3
"""
Visualize a Blobby Tic-Tac-Toe matchup as animated PNG or MP4.

Usage:
  python visualize.py results.log "bot_a vs bot_b" png
  python visualize.py results.log "bot_a vs bot_b" mp4
  python visualize.py results.log 2 png          # matchup number
"""
import sys
import re
import subprocess
import tempfile
import os
from PIL import Image, ImageDraw, ImageFont

# Colors
BG_COLOR = (245, 245, 245)
HOLE_COLOR = (220, 220, 220)
CELL_COLOR = (255, 255, 255)
CELL_BORDER = (180, 180, 180)
X_COLOR = (220, 60, 60)
O_COLOR = (50, 100, 220)
WIN_HIGHLIGHT = (255, 255, 150)
TEXT_COLOR = (40, 40, 40)
LIGHT_TEXT = (120, 120, 120)
HEADER_BG = (60, 60, 70)
HEADER_TEXT = (255, 255, 255)

CELL_SIZE = 48
CELL_PAD = 4
BOARD_PAD = 30
GAME_GAP = 60
HEADER_H = 50
FOOTER_H = 40
FPS = 2


def parse_matchup(log_path, matchup_id):
    """Extract a matchup from results.log by name or number."""
    with open(log_path, 'r') as f:
        content = f.read()

    # Find all matchup blocks
    pattern = r'=== MATCHUP (\d+)/\d+: (.+?) vs (.+?) ==='
    matches = list(re.finditer(pattern, content))

    block = None
    player_a = player_b = None

    for i, m in enumerate(matches):
        num = int(m.group(1))
        pa, pb = m.group(2), m.group(3)

        # Match by number or by name
        if isinstance(matchup_id, int) or matchup_id.isdigit():
            if num != int(matchup_id):
                continue
        else:
            names_lower = matchup_id.lower()
            if not (pa.lower() in names_lower and pb.lower() in names_lower):
                continue

        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        block = content[start:end]
        player_a, player_b = pa, pb
        break

    if block is None:
        print(f"Matchup '{matchup_id}' not found.")
        sys.exit(1)

    return block, player_a, player_b


def parse_rounds(block):
    """Parse rounds from a matchup block."""
    rounds = []
    # Split into round sections
    round_splits = re.split(r'  Round (\d+):', block)
    # round_splits[0] is header, then alternating round_num, content
    for i in range(1, len(round_splits) - 1, 2):
        round_num = int(round_splits[i])
        section = round_splits[i + 1]

        # Parse board (only lines containing . and _ characters)
        board_match = re.search(r'Board:\n((?:    [._]+\n)+)', section)
        board = []
        if board_match:
            for line in board_match.group(1).strip().split('\n'):
                board.append(list(line.strip()))

        # Parse games
        games = []
        game_pattern = r'Game (\d+) \(X=(.+?), O=(.+?)\): (\w+)\n((?:    [XO] .+\n)*)'
        for gm in re.finditer(game_pattern, section):
            game_num = int(gm.group(1))
            x_player = gm.group(2)
            o_player = gm.group(3)
            result = gm.group(4)
            moves = []
            for move_line in gm.group(5).strip().split('\n'):
                if not move_line.strip():
                    continue
                parts = move_line.strip().split()
                mark = parts[0]
                player = parts[1]
                r, c = int(parts[2]), int(parts[3])
                moves.append((mark, player, r, c))
            games.append({
                'num': game_num,
                'x_player': x_player,
                'o_player': o_player,
                'result': result,
                'moves': moves,
            })

        # Parse round result
        result_match = re.search(r'Round \d+ result: .+? \+(\d+), .+? \+(\d+) \(total: (\d+)-(\d+)\)', section)
        round_score = None
        if result_match:
            round_score = (int(result_match.group(3)), int(result_match.group(4)))

        rounds.append({
            'num': round_num,
            'board': board,
            'games': games,
            'score': round_score,
        })

    return rounds


def find_winning_cells(board, marks, winner):
    """Find the 3 cells that form the winning line."""
    if winner not in ('X', 'O'):
        return set()
    rows = len(board)
    cols = len(board[0]) if rows > 0 else 0
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for r in range(rows):
        for c in range(cols):
            for dr, dc in directions:
                cells = []
                for step in range(3):
                    nr, nc = r + dr * step, c + dc * step
                    if 0 <= nr < rows and 0 <= nc < cols and marks.get((nr, nc)) == winner:
                        cells.append((nr, nc))
                    else:
                        break
                if len(cells) == 3:
                    return set(cells)
    return set()


def draw_board(draw, board, marks, x0, y0, win_cells=None):
    """Draw a board with marks at position (x0, y0)."""
    rows = len(board)
    cols = len(board[0]) if rows > 0 else 0

    for r in range(rows):
        for c in range(cols):
            px = x0 + c * (CELL_SIZE + CELL_PAD)
            py = y0 + r * (CELL_SIZE + CELL_PAD)

            if board[r][c] == '.':
                # Hole
                draw.rounded_rectangle(
                    [px, py, px + CELL_SIZE, py + CELL_SIZE],
                    radius=6, fill=HOLE_COLOR)
            else:
                # Valid cell
                fill = WIN_HIGHLIGHT if win_cells and (r, c) in win_cells else CELL_COLOR
                draw.rounded_rectangle(
                    [px, py, px + CELL_SIZE, py + CELL_SIZE],
                    radius=6, fill=fill, outline=CELL_BORDER, width=2)

                mark = marks.get((r, c))
                if mark:
                    color = X_COLOR if mark == 'X' else O_COLOR
                    # Draw X or O
                    cx = px + CELL_SIZE // 2
                    cy = py + CELL_SIZE // 2
                    r2 = CELL_SIZE // 2 - 8
                    if mark == 'X':
                        draw.line([(cx - r2, cy - r2), (cx + r2, cy + r2)], fill=color, width=4)
                        draw.line([(cx + r2, cy - r2), (cx - r2, cy + r2)], fill=color, width=4)
                    else:
                        draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2],
                                     outline=color, width=4)


def board_pixel_size(board):
    """Get pixel dimensions of a board."""
    rows = len(board)
    cols = len(board[0]) if rows > 0 else 0
    w = cols * (CELL_SIZE + CELL_PAD) - CELL_PAD
    h = rows * (CELL_SIZE + CELL_PAD) - CELL_PAD
    return w, h


def render_frame(board, game1_marks, game2_marks, game1_info, game2_info,
                 player_a, player_b, round_num, score, canvas_w, canvas_h,
                 win1_cells=None, win2_cells=None, result_text=None):
    """Render a single frame."""
    img = Image.new('RGB', (canvas_w, canvas_h), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Header
    draw.rectangle([0, 0, canvas_w, HEADER_H], fill=HEADER_BG)
    header = f"Round {round_num}    {player_a} vs {player_b}"
    if score:
        header += f"    [{score[0]}-{score[1]}]"
    draw.text((canvas_w // 2 - len(header) * 4, 16), header, fill=HEADER_TEXT)

    bw, bh = board_pixel_size(board)

    # Game 1 label
    g1_x = BOARD_PAD
    label_y = HEADER_H + 8
    g1_label = f"Game 1: {game1_info['x_player']}(X) vs {game1_info['o_player']}(O)"
    draw.text((g1_x, label_y), g1_label, fill=TEXT_COLOR)

    # Game 2 label
    g2_x = BOARD_PAD + bw + GAME_GAP
    g2_label = f"Game 2: {game2_info['x_player']}(X) vs {game2_info['o_player']}(O)"
    draw.text((g2_x, label_y), g2_label, fill=TEXT_COLOR)

    board_y = label_y + 24

    # Draw both boards
    draw_board(draw, board, game1_marks, g1_x, board_y, win1_cells)
    draw_board(draw, board, game2_marks, g2_x, board_y, win2_cells)

    # Result text
    if result_text:
        ry = board_y + bh + 12
        draw.text((canvas_w // 2 - len(result_text) * 4, ry), result_text, fill=TEXT_COLOR)

    return img


def generate_frames(rounds, player_a, player_b):
    """Generate all animation frames."""
    if not rounds:
        return []

    # Compute canvas size from largest board
    max_bw = max_bh = 0
    for rd in rounds:
        bw, bh = board_pixel_size(rd['board'])
        max_bw = max(max_bw, bw)
        max_bh = max(max_bh, bh)

    canvas_w = BOARD_PAD * 2 + max_bw * 2 + GAME_GAP
    canvas_h = HEADER_H + 24 + max_bh + FOOTER_H + BOARD_PAD + 20

    frames = []
    prev_score = (0, 0)

    for rd in rounds:
        board = rd['board']
        games = rd['games']
        if len(games) < 2:
            continue

        g1 = games[0]
        g2 = games[1]

        # Interleave moves from both games
        g1_marks = {}
        g2_marks = {}
        g1_moves = list(g1['moves'])
        g2_moves = list(g2['moves'])
        i1 = i2 = 0

        # Initial empty board frame
        frames.append(render_frame(
            board, g1_marks, g2_marks, g1, g2,
            player_a, player_b, rd['num'], prev_score,
            canvas_w, canvas_h))

        # Alternate moves: game1 move, game2 move, game1, game2...
        while i1 < len(g1_moves) or i2 < len(g2_moves):
            if i1 < len(g1_moves):
                mark, player, r, c = g1_moves[i1]
                g1_marks[(r, c)] = mark
                i1 += 1

            if i2 < len(g2_moves):
                mark, player, r, c = g2_moves[i2]
                g2_marks[(r, c)] = mark
                i2 += 1

            frames.append(render_frame(
                board, g1_marks, g2_marks, g1, g2,
                player_a, player_b, rd['num'], prev_score,
                canvas_w, canvas_h))

        # Final frame with results highlighted
        win1 = find_winning_cells(board, g1_marks, g1['result'])
        win2 = find_winning_cells(board, g2_marks, g2['result'])

        result_parts = []
        result_parts.append(f"G1: {g1['result']}")
        result_parts.append(f"G2: {g2['result']}")
        result_text = "   ".join(result_parts)

        for _ in range(FPS * 2):
            frames.append(render_frame(
                board, g1_marks, g2_marks, g1, g2,
                player_a, player_b, rd['num'], prev_score,
                canvas_w, canvas_h, win1, win2, result_text))

        if rd['score']:
            prev_score = rd['score']

    return frames


def save_apng(frames, output_path):
    """Save frames as animated PNG."""
    if not frames:
        print("No frames to save.")
        return
    durations = [500] * len(frames)  # 500ms per frame
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0)
    print(f"Saved {output_path} ({len(frames)} frames, {frames[0].size[0]}x{frames[0].size[1]})")


def save_mp4(frames, output_path):
    """Save frames as MP4 using ffmpeg."""
    if not frames:
        print("No frames to save.")
        return
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, frame in enumerate(frames):
            frame.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))
        cmd = [
            'ffmpeg', '-y', '-framerate', str(FPS),
            '-i', os.path.join(tmpdir, 'frame_%04d.png'),
            '-c:v', 'mpeg4', '-q:v', '2', '-pix_fmt', 'yuv420p',
            '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ffmpeg error: {result.stderr[-300:]}")
    print(f"Saved {output_path} ({len(frames)} frames)")


def main():
    if len(sys.argv) < 4:
        print("Usage: python visualize.py <results.log> <matchup_id> <png|mp4> [round_num]")
        print("  matchup_id: number (e.g. 2) or names (e.g. 'bot_a vs bot_b')")
        print("  round_num: optional, visualize only this round")
        sys.exit(1)

    log_path = sys.argv[1]
    matchup_id = sys.argv[2]
    fmt = sys.argv[3].lower()
    round_filter = int(sys.argv[4]) if len(sys.argv) > 4 else None

    block, player_a, player_b = parse_matchup(log_path, matchup_id)
    rounds = parse_rounds(block)

    if not rounds:
        print("No rounds found in matchup.")
        sys.exit(1)

    if round_filter:
        rounds = [r for r in rounds if r['num'] == round_filter]
        if not rounds:
            print(f"Round {round_filter} not found.")
            sys.exit(1)

    print(f"Matchup: {player_a} vs {player_b}, {len(rounds)} rounds")
    for rd in rounds:
        for g in rd['games']:
            print(f"  Round {rd['num']} Game {g['num']}: {g['result']} ({len(g['moves'])} moves)")

    frames = generate_frames(rounds, player_a, player_b)

    safe_a = re.sub(r'[^\w]', '', player_a)
    safe_b = re.sub(r'[^\w]', '', player_b)
    suffix = f"_r{round_filter}" if round_filter else ""
    output = f"matchup_{safe_a}_vs_{safe_b}{suffix}.{fmt}"

    if fmt == 'png':
        save_apng(frames, output)
    elif fmt == 'mp4':
        save_mp4(frames, output)
    else:
        print(f"Unknown format: {fmt}. Use 'png' or 'mp4'.")
        sys.exit(1)


if __name__ == '__main__':
    main()
