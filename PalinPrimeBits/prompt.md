# PalinPrimeBits — Tournament Spec

## Task

**Write a complete, self-contained Python 3.10 bot client that competes in this tournament.** The bot connects to the tournament server at `localhost:7474`, plays every round it is dealt, and tries to score as many tournament points as possible. Use only the Python standard library. Do not leave placeholder strategies, demo stubs, or "STRATEGY GOES HERE" comments — the bot must implement a full solution that produces a numeric answer for each round.

You may add your model name as a comment at the top of the file (e.g. `# bot author: <model name and version>`).

## 1. The puzzle

A **palindromic prime** is a positive integer whose decimal expansion reads the same forwards and backwards AND that is prime. Leading zeros are not allowed in the decimal expansion (so e.g. `010` is not a palindrome — `10` is its decimal representation and reads "10" forwards, "01" backwards, not a palindrome).

Let `p(n)` be the `n`-th palindromic prime in ascending order, 1-indexed. The first few values are:

| n | p(n) |
|---|---|
| 1 | 2 |
| 2 | 3 |
| 3 | 5 |
| 4 | 7 |
| 5 | 11 |
| 6 | 101 |
| 7 | 131 |
| 8 | 151 |
| 9 | 181 |
| 10 | 191 |
| 11 | 313 |
| 12 | 353 |

Each round the server announces a single integer `n` and the bot must compute and submit the length of the longest contiguous run of binary `1` digits in the standard base-2 representation of `p(n)`.

### Binary 1-run definition

Write `p(n)` in base 2 with no leading zeros. The "longest 1-run" is the length of the longest substring consisting entirely of the character `1`. Equivalently: the maximum `k` such that there exist `k` consecutive bits, all `1`, somewhere in the binary expansion. The answer is always a positive integer (since every prime is at least 2, the binary expansion contains at least one `1`).

### Worked examples

| n | p(n) | binary of p(n) | longest 1-run |
|---|---|---|---|
| 1 | 2 | `10` | 1 |
| 4 | 7 | `111` | 3 |
| 5 | 11 | `1011` | 2 |
| 6 | 101 | `1100101` | 2 |
| 7 | 131 | `10000011` | 2 |
| 10 | 191 | `10111111` | 6 |
| 11 | 313 | `100111001` | 3 |

## 2. Tournament structure

10 solo rounds played serially. Each round's value of `n` is chosen by the server and announced at round start; the bot adapts at runtime. Bots are not told the per-round schedule in advance.

Per-round bound the bot can rely on:

- `1 ≤ n ≤ 1,000,000`, integer.

### Per-round score and ranking

The bot's submission is **correct** if it equals the actual longest 1-run length of `p(n)`, and **incorrect** otherwise. Per-round ranking → tournament points:

| Rank (among correct submissions) | Points |
|---|---|
| 1st | 10 |
| 2nd | 7 |
| 3rd | 5 |
| 4th | 3 |
| 5th | 1 |
| 6th and below | 0 |

Rank among correct submissions is by **earliest submission timestamp** at the server (earlier wins the higher rank). Incorrect submissions, timeouts, and malformed submissions score 0 tournament points for the round regardless of timing.

### Tournament standings

Total tournament points across all 10 rounds, descending. Tiebreak by total wins (1st-place finishes), then by total cumulative submission time across rounds where the bot earned ≥ 1 point (lower wins).

## 3. Wire framing

- All messages in both directions are ASCII text, lines terminated by a single `\n` (LF, byte `0x0a`). **CRLF is invalid.**
- Every server message is a complete line ending in `\n`. Every bot message must be a complete line ending in `\n`.
- The server reads bot input with line buffering. Send each line as a complete byte sequence ending in `\n`.
- Lines have no leading or trailing whitespace beyond the single terminating `\n`.

## 4. Connection handshake

1. **Read your bot name from the `BOTNAME` environment variable.** Do not hardcode it; do not derive it from `sys.argv`; do not generate it. The value of `os.environ['BOTNAME']` is your bot identifier — use it verbatim (no whitespace stripping required; the value is plain ASCII with no surrounding whitespace). If `BOTNAME` is absent or empty, the bot is misconfigured and should exit non-zero without attempting to connect.
2. Open a TCP connection to `localhost:7474`.
3. **Send the BOTNAME value as the first line**, terminated by a single `\n`. The server reads exactly one line as your bot identifier. The value must be 1–32 characters from the set `[A-Za-z0-9_-]`. A value violating these rules causes the server to immediately close the connection.
4. Wait for a `ROUND` line announcing the first round. Until you receive `ROUND`, do not send anything.

## 5. Round protocol

The server announces each round to all registered bots simultaneously:

```
ROUND <round_num> <n>
```

- `<round_num>` is the 1-indexed round number, `1..10`.
- `<n>` is a positive integer in `[1, 1,000,000]`.

The bot has **30 seconds wall-clock** from the instant the server has finished sending the `ROUND` line to the instant the server has finished reading the bot's `ANSWER` line. The clock counts the bot's compute time and any time spent transmitting. Server-side checking happens after the `ANSWER` line is received and is not counted in the budget.

The bot's submission is a single line:

```
ANSWER <k>
```

- `<k>` is a non-negative decimal integer (no leading zeros except the literal `0`, no sign).
- Exactly one space between `ANSWER` and `<k>`.

After the `ANSWER` line (or after the 30 s deadline), the server replies with one of:

```
OK <correct_k>
```

or

```
INVALID <reason>
```

`<correct_k>` is the actual longest 1-run length for `p(n)` (a positive integer in decimal). `<reason>` is a closed-list machine-readable token (see §6). After `OK` or `INVALID`, the server sends:

```
END_ROUND <round_num>
```

The bot then waits for the next `ROUND` line. After all 10 rounds, the server sends:

```
TOURNAMENT_END
```

Stay connected for the duration of the tournament; do not close your socket until you receive `TOURNAMENT_END` or the server closes the connection.

A round in which the bot's submission is rejected (timeout, malformed, or incorrect) still proceeds to `END_ROUND` normally; the bot is expected to continue to the next round.

**Per-round message sequence.** After the bot sends its `ANSWER` line, the server sends exactly two lines in order: first one result line (`OK <correct_k>` or `INVALID <reason>`), then one `END_ROUND <round_num>` line. The bot must read both lines before reading the next `ROUND` line; ignoring the result line will desync the line-by-line parser.

## 6. Validation

The server validates the submission. The first failure determines `INVALID <reason>`:

| Trigger | INVALID reason |
|---|---|
| The submission did not arrive (no `ANSWER` line received) within 30 s | `timeout` |
| The submission line doesn't match `^ANSWER (0\|[1-9][0-9]*)$` exactly (wrong prefix, lowercase, leading zero on `<k>` other than the literal `0`, extra whitespace, trailing characters, etc.) | `malformed` |
| The submitted `<k>` doesn't equal the actual longest 1-run length of `p(n)` | `wrong` |

If all checks pass, the server replies `OK <correct_k>`.

`OK` answers score 10/7/5/3/1/0 tournament points by submission-timestamp rank as described in §2. All `INVALID` answers score 0 tournament points for the round.

## 7. Constraints

- One TCP connection per bot, opened once at startup and held open until `TOURNAMENT_END` or socket close.
- Standard library only.
- Bot identifier from `BOTNAME` env var (see §4).
- Per-round wall-clock budget 30 s.
- Tournament structure is 10 rounds played serially, fixed by the server at startup. Per-round `n` is chosen by the server within the bound in §2.
- Do not set socket read timeouts; idle reads should block.

## 8. Sample wire transcript

Illustrative — three rounds, showing `alpha_bot`'s point of view.

```
>> alpha_bot
<< ROUND 1 10
>> ANSWER 6
<< OK 6
<< END_ROUND 1
<< ROUND 2 5
>> ANSWER 2
<< OK 2
<< END_ROUND 2
<< ROUND 3 7
>> ANSWER 1
<< INVALID wrong
<< END_ROUND 3
...
```

Walk-through:

- **Connect.** First line sent is the bot's `BOTNAME`.
- **Round 1.** `n = 10`, so `p(10) = 191 = 0b10111111`. Longest 1-run = 6. Bot answers correctly.
- **Round 2.** `n = 5`, so `p(5) = 11 = 0b1011`. Longest 1-run = 2. Bot answers correctly.
- **Round 3.** `n = 7`, so `p(7) = 131 = 0b10000011`. Longest 1-run = 2. Bot answers `1` — incorrect. Server replies `INVALID wrong`. Round proceeds to `END_ROUND 3` and the bot moves on.

## 9. Notes

- The submission line is parsed as a single line of ASCII bytes terminated by `\n`. `ANSWER\t6` is malformed (tab, not space). `ANSWER  6` (two spaces) is malformed. `Answer 6` is malformed.
- The bot may take any approach to compute `p(n)` and its longest 1-run, including pre-computation before the first `ROUND` line arrives. The 30 s clock only starts at each `ROUND` line.
- A round's `INVALID` only forfeits points for that round. The bot remains connected and is expected to handle the next `ROUND` normally.
- After `TOURNAMENT_END`, the bot may close its socket and exit.
