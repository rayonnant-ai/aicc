**Task:** Write a Python 3.10 client for a competitive "Robot Word Racer" tournament.

**1. Network Protocol:**
* **Connection:** Connect via TCP to `localhost:7474`.
* **Identification:** Client identifies itself by sending name as a string terminated by a newline character (`\n`) 
* **Grid Reception:** The server will send a 225-character uppercase string followed immediately by a newline character (`\n`). This represents a 15x15 grid in row-major order.
* **Word Submission:** Submit discovered words to the server as UTF-8 strings, each terminated by a newline character (`\n`).
* **Server Responses:** For every client Submission, the server replies with a single character followed by a newline (`\n`):
    * `0\n`: Submission accepted.
    * `1\n`: Game has ended, or you have been disqualified.

**2. Game Rules:**
* **Grid Mechanics:** Valid words must be formed by connecting adjacent letter tiles on the 15x15 grid (horizontally, vertically, or diagonally). A single tile cannot be used more than once in the same word. Minimum word length is 3 letters.
* **Vocabulary:** You are provided a local file named `dictionary.txt` containing 1,000,000 valid words (one word per line). 
* **Disqualification:** Submitting a word that is **not** in `dictionary.txt` or **not** valid on the current grid results in instant disqualification.
* **Claiming (The Race):** You are competing against other bots in real-time. Only the first bot to submit a specific valid word receives the points. Speed and network efficiency are critical.
* **Scoring:** Points = (number of letters) - 6.

**3. Deliverable & Constraints:**
* Provide a complete, standalone Python script that loads the dictionary, connects to the server, solves the grid, and rapidly transmits words.
* The client must gracefully exit if the server sends a `1` or closes the connection.
* Use strictly the Python Standard Library (no external packages).
---
$ python3.10 wordracerserver.py
[*] Loading dictionary: dictionary.txt...
[*] 15x15 Server Live. Lobby: 30s | Round: 10s
[*] Identified: 'ClaudeBot'
[*] Identified: 'GeminiBot'
[*] Identified: 'ChatGPTBot'
[*] Identified: 'GrokBot'

--- START (NBHLRIIGBTPFVIMZISHZ...) ---

--- END ---

LEADERBOARD:
1. ClaudeBot: 258 pts
2. GeminiBot: 0 pts
3. GrokBot: 0 pts
4. ChatGPTBot: -24283 pts
$ python3.10 wordracerserver.py
[*] Loading dictionary: dictionary.txt...
[*] 15x15 Server Live. Lobby: 30s | Round: 10s
[*] Identified: 'ClaudeBot'
[*] Identified: 'GeminiBot'
[*] Identified: 'ChatGPTBot'
[*] Identified: 'GrokBot'

--- START (KWPDZMMHOZGRHGLYUGXC...) ---

--- END ---

LEADERBOARD:
1. ClaudeBot: 324 pts
2. GeminiBot: 0 pts
3. GrokBot: -1477 pts
4. ChatGPTBot: -24025 pts
$ python3.10 wordracerserver.py
[*] Loading dictionary: dictionary.txt...
[*] 15x15 Server Live. Lobby: 30s | Round: 10s
[*] Identified: 'ClaudeBot'
[*] Identified: 'GeminiBot'
[*] Identified: 'ChatGPTBot'
[*] Identified: 'GrokBot'

--- START (NOKXRIVSHRXUVIICJTXL...) ---

--- END ---

LEADERBOARD:
1. ClaudeBot: 272 pts
2. GeminiBot: 0 pts
3. GrokBot: -43 pts
4. ChatGPTBot: -26075 pts
