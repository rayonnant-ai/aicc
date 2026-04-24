There are n disks at A1 on an 8x8 chess board. You need to move them to H8 following Towers of Hanoi rules and Knight moves.
This will be a real time game like ladenknightstour.

  1. Disk count per round. My vote: n = 2, 3, 4, 5, 6, 7, 7, 8, 8, 9 across 10 rounds, with the last few flat       
  because each added disk roughly doubles the minimum move count (classical ToH grows 2^n−1). Gives weaker bots
  something to solve early.                                                                                         
  2. Square notation. Use [row, col] 0-indexed (A1 = [0,0], H8 = [7,7]) in JSON, matching Laden Knight's Tour. Chess
   notation is more thematic but coord pairs are cleaner for parsing.                                               
  3. Submission format. Bot sends a list of [[from_row, from_col], [to_row, to_col]] move pairs (or a flat tour in
  the form [[sq1], [sq2], ...] where each consecutive pair is implicit — no, that's ambiguous for multi-disk). So   
  explicit from/to per move. My vote: list of {"from": [r,c], "to": [r,c]} objects.
  4. Scoring. Lowest move count wins the round, ties by submission time. 10/7/5/3/1/0 by rank (matches LKT). Invalid
   solution = 0 points.                                                                                             
  5. Time budget. 10 seconds per round per bot (matches LKT). The full solution must be submitted before the
  deadline.                                                                                                         
  6. Validation. Server replays moves, checking each: (a) from square has disks, (b) to is a legal knight-jump from
  from, (c) Hanoi placement rule holds, (d) final state has all disks correctly stacked on H8.  