 1. Grid per bot or shared. ★ Per-bot                                                                              
                                                                                                                    
  2. Round structure. ★ 10 rounds × 10s each, growing sizes:  Sizes not known a-priori                                                     
                                                                                                                    
  3. Sliding mechanics. ★ Standard 15-puzzle: empty slot represented by _. Slides are 4-directional only (one tile  
  swaps with the empty slot). Diagonal is for word formation only, not slides.                                      
                                                                                                                    
  4. Letter distribution. ★ Drawn from English letter frequency (Scrabble-tile-bag-ish) so boards aren't unplayable.
   Identical seed across bots within a round.                                                                       
                                                                                                                    
  5. Word race scope. ★ totally independent
                                                                                                                    
  6. Disqualification. ★ Per-round only. A bot DQ'd in R3 still plays R4–R10. DQ triggers: word not in dictionary,  
  word not currently traceable on this bot's grid, word reuses a tile, or invalid slide move.
                                                                                                                    
  7. Scoring. ★ Per-word: letters − 6. Per-round rank by cumulative word points (negative scores allowed).          
  Tournament: 10/7/5/3/1/0 per round by rank.
                                                                                                                    
  8. Protocol (line-based, per the protocol-simplicity rule):                                                       
  - Server → bot: ROUND <n> <w> <h>, then <h> lines of grid (lowercase letters and one _), then START
  - Bot → server: S <D> for slide (D ∈ U/D/L/R, meaning the tile in that direction relative to the empty slot moves 
  into the empty slot), or W <word> for claim                                                                      
  - Server → bot: OK <pts> (claim accepted), MOVED (slide accepted),
  or DQ <reason> and the connection ends for that round                                                             
                                                       
  9. Dictionary. ★ Pull a fresh 300K dict of real english words.
                                                                                                                    
  If those defaults look right, say "go" and I'll write prompt.md, server.py, and a basic test client. Redirect any
  line you don't like.                                                     