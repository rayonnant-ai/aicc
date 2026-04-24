There are n disks at A1 on an 8x8 chess board. You need to move them to H8 following Towers of Hanoi rules and Knight moves.
This will be a real time game like ladenknightstour.

  1. Disk count per round.  n = 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 across 10 rounds                                
  2. Square notation. Chess notation. But explain how it works in the prompt.                                               
  3. Submission format. Bot sends a list of move pairs using chess notation.
  4. Scoring. Lowest move count wins the round, ties by submission time. 10/7/5/3/1/0 by rank (matches LKT). Invalid
   solution = 0 points.                                                                                             
  5. Time budget. 10 seconds per round per bot (matches LKT). The full solution must be submitted before the
  deadline.                                                                                                        
  6. Validation. Server replays moves, checking each: (a) from square has disks, (b) to is a legal knight-jump from
  from, (c) Hanoi placement rule holds, (d) final state has all disks correctly stacked on H8.  