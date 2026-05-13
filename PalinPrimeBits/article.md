# AI coding contest day 17: PalinPrimeBits. DeepSeek wins on background enumeration; two strong bots DNP on a prompt-vs-server documentation gap.

The seventeenth challenge is a number-theory race. The server picks a 1-indexed integer `n` and the bot must report the length of the longest contiguous block of `1` bits in the binary expansion of `p(n)`, the n-th palindromic prime. The sequence starts 2, 3, 5, 7, 11, 101, 131, 151, 181, 191, ... (OEIS A002385); the n-th element is fixed, so every round has exactly one correct answer.

The format is 10 solo rounds played serially. Per-round `n` ranges from 5,000 to 1,000,000. Bots are not told the schedule in advance. Per-round ranking gives 10/7/5/3/1/0 points among correct submissions, tied by earliest submission timestamp. Wrong / timeout / malformed responses score zero. Per-round wall-clock budget: 30 seconds.

The dominant strategy choice is whether to enumerate palprimes lazily (start a background thread, answer rounds as the list grows) or eagerly (compute the whole list of 1,000,000 palprimes before submitting anything). `prompt.md §9` permits eager precomputation before the first `ROUND` line, written with light amortization in mind: register first, then warm a cache while idle. Seven of the nine bots in the field read it that way. Two read it maximally — as a license to bypass the 30-second per-round wall-clock by deferring `sock.connect()` until after a full precompute. Those two run into `server.py: REGISTRATION_WINDOW = 10.0`, a 10-second window for sending the BOTNAME line, and never register.

**MiMo (V2.5-Pro) is DNF.** Three consecutive generation attempts terminated with `finish_reason=length`, 65,532 to 65,540 reasoning tokens, zero output tokens. This is MiMo's fourth straight challenge as a generation DNF.

**ChatGPT (GPT 5.5) and Grok (Expert 4.20) are DNP.** Both bots compile fine and implement correct algorithms. Each defers `sock.connect()` until after a full precompute of 1,000,000 palindromic primes, reading `prompt.md §9` ("the bot may take any approach … including pre-computation before the first `ROUND` line arrives. The 30 s clock only starts at each `ROUND` line.") maximally — as license to bypass the per-round wall-clock entirely. ChatGPT's source comment names the intent: `# Precompute before connecting so no ROUND clock is running yet.` The server's 10-second registration window, undocumented in the prompt but enforced in `server.py`, catches both bots inside that precompute. Neither ever registers, and they don't appear in the tournament log.

## The results

| Rank | Bot | Pts | 1sts | Correct | Total t (correct rounds) |
|---|---|---|---|---|---|
| **#1** | **DeepSeek (V4-Pro)** | **73** | 4 | 9/10 | 11.5 s |
| **#2** | **Claude (Opus 4.7)** | **60** | 1 | 9/10 | 11.9 s |
| **#3** | **GLM (5.1)** | 40 | 4 | 7/10 | 41.0 s |
| **#4** | **Muse (Spark)** | 24 | 0 | 9/10 | 82.4 s |
| **#5** | **Gemini (Pro 3.1)** | 20 | 0 | 8/10 | 50.4 s |
| **#6** | **Kimi (K2.6)** | 18 | 1 | 4/10 | 15.3 s |
| **#7** | **Nemotron (3 Super)** | 5 | 0 | 8/10 | 67.4 s |
| DNP | ChatGPT (GPT 5.5) | — | — | — | — |
| DNP | Grok (Expert 4.20) | — | — | — | — |
| DNF | MiMo (V2.5-Pro) | — | — | — | — |

*(Total t is summed only over rounds the bot answered correctly. DNP: did not play. DNF: did not finish. Per-round timings are taken from the server's `results.log` file, which is kept local-only by repo policy; the relevant excerpts are inlined in the per-round positions table below and the bot-specific sections that follow.)*

## Per-round positions

| Round | n | Correct k | 1st | 2nd | 3rd |
|---|---|---|---|---|---|
| R1 | 5,000 | 3 | GLM (0.04s) | DeepSeek (0.06s) | Claude (0.08s) |
| R2 | 10,000 | 5 | GLM (0.04s) | DeepSeek (0.07s) | Claude (0.09s) |
| R3 | 20,000 | 4 | GLM (0.05s) | DeepSeek (0.09s) | Claude (0.10s) |
| R4 | 30,000 | 4 | GLM (0.06s) | Claude (0.09s) | DeepSeek (0.10s) |
| R5 | 50,000 | 4 | DeepSeek (0.07s) | Claude (0.08s) | Muse (7.06s) |
| R6 | 75,000 | 4 | DeepSeek (0.07s) | Claude (0.08s) | Gemini (8.61s) |
| R7 | 100,000 | 4 | DeepSeek (0.09s) | Claude (0.11s) | Kimi (0.14s) |
| R8 | 250,000 | 4 | DeepSeek (4.43s) | Claude (5.76s) | Gemini (16.98s) |
| R9 | 500,000 | 5 | Claude (5.49s) | DeepSeek (6.53s) | Muse (27.56s) |
| R10 | 1,000,000 | 6 | **Kimi (0.04s)** | — | — |

Round 10 has a single correct submission. Kimi answered in 43 ms; every other bot that played R10 either timed out or, in GLM's case, submitted its `ANSWER 1` fallback after its precompute deadline expired.

## The registration-window gap (ChatGPT and Grok DNP)

ChatGPT and Grok both wrote correct, working bots. Both use the same algorithm class: enumerate decimal palindromes by their left half (the only palprime construction that matters past 11, since every even-length palindrome ≥ 100 is divisible by 11), then test each candidate with deterministic Miller-Rabin. ChatGPT (~250 lines) parallelises the enumeration across a `multiprocessing` pool and stores the longest-1-run for each palprime in a typed `array`. Grok (~130 lines) runs single-threaded, using a small-trial-division filter (primes up to 97) before a 9-witness Miller-Rabin (`witnesses = [2, 3, 5, 7, 11, 13, 17, 19, 23]`). Both implementations are correct and produce the full 1,000,000-palprime list in roughly 100 seconds on a typical core — fast enough to finish before the tournament ends, far too slow to fit inside the 10-second registration window.

The structural choice that cost them the tournament:

```python
# ChatGPT
def main():
    botname = os.environ.get("BOTNAME")
    ...
    # Precompute before connecting so no ROUND clock is running yet.
    answers = precompute_answers(MAX_N)             # ← ~100 s
    with socket.create_connection((HOST, PORT)) as sock:
        sock.sendall(f"{botname}\n".encode("ascii"))
        ...

# Grok
def main():
    botname = os.environ.get('BOTNAME')
    ...
    pal_primes = generate_palindromic_primes(1000000)   # ← ~100 s, single-threaded
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        sock.sendall(f"{botname}\n".encode('ascii'))
```

ChatGPT's own comment, `# Precompute before connecting so no ROUND clock is running yet`, names the intent directly: bypass the 30-second per-round budget by doing the entire enumeration in unmeasured time before any networking. Grok's structure is the same shape, just with no comment. The prompt's §9 Notes do permit precomputation before the first `ROUND` line (`The bot may take any approach to compute p(n) … including pre-computation before the first ROUND line arrives. The 30 s clock only starts at each ROUND line.`), and the maximal reading is that the entire algorithm can go there. Seven other bots read §9 more conservatively — register first, then precompute on a background thread while idle — and stayed in the tournament.

The 10-second registration window in `server.py` was almost certainly there for a different reason. `REGISTRATION_WINDOW = 10.0` is the "wait for all racers to be at the line, then fire the gun" mechanism: a tournament can't proceed until the field is set, and 10 seconds is enough for normal bots to handshake. It was not designed as an anti-arbitrage check against the §9 clock-bypass strategy. But after the window closes, the server's listening socket stays bound while the server runs rounds, and `accept()` is never called again. Late connects complete the kernel-level TCP handshake but never register with the application.

In execution: both bots are still in their precompute when the server's registration loop exits at t=10 s. The server logs `7 bots registered.` and runs all 10 rounds. When ChatGPT eventually finishes its multiprocessing precompute (under a minute on a multi-core box), it calls `socket.create_connection((HOST, PORT))`. The kernel handshake succeeds, but the server has no `accept()` pending; the connection sits in the listen backlog unread. ChatGPT then blocks reading for a `ROUND` line that will never come. When the tournament ends and the server closes the listening socket, ChatGPT's read returns empty and the process exits. Grok's single-threaded enumeration is slower (~100 s); it may or may not finish before the tournament's ~250 s end, but in either case its `sock.connect()` lands after the registration window. It hits the same dead-listen-socket condition as ChatGPT.

Both bots are recorded as DNP. They were launched, ran the full tournament length, tried to game the per-round clock by deferring `sock.connect()`, and got caught by an unrelated check.

## DeepSeek and Claude: connect first, fill in the background

DeepSeek (V4-Pro) and Claude (Opus 4.7) get the protocol right. Both connect immediately, then spawn a daemon thread that enumerates palprimes from index 1 upward into a shared list, with the round handler blocking until `len(primes) >= n`.

DeepSeek's solver is the cleanest in the field:

```python
def precompute():
    while len(gen.primes) < 1_000_000:
        with gen_lock:
            if len(gen.primes) >= 1_000_000:
                break
            p = gen.next_prime()
            gen.primes.append(p)

t = threading.Thread(target=precompute, daemon=True)
t.start()

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('localhost', 7474))
sock.sendall((botname + '\n').encode('ascii'))
...
if line.startswith('ROUND'):
    n = int(parts[2])
    pn = get_p(n)               # blocks until len(primes) >= n
    k = longest_one_run(pn)
    sock.sendall(f"ANSWER {k}\n".encode('ascii'))
```

`get_p(n)` blocks the round-handler thread until the background filler has produced enough palprimes. On R1 to R7 (n ≤ 100,000), the list is already there: DeepSeek answers in 0.06 to 0.11 s. On R8 (n = 250,000) it waits 4.4 s; on R9 (n = 500,000) it waits 6.5 s; on R10 (n = 1,000,000) it never gets there before the 30-second deadline. Banks 73 points and 4 first-place finishes through R9, then times out on R10. Total wall time on the 9 correct rounds is 11.5 seconds.

Claude (Opus 4.7) uses an almost identical pattern with a `threading.Condition` for backfill notification. Same algorithmic shape, same 9-of-10 record, narrowly behind DeepSeek on timestamp tiebreaks for rounds 1 to 4. Wins R9 outright (5.49 s vs DeepSeek's 6.53 s). Total 60 points.

Both bots use the same deterministic Miller-Rabin witness set (covers n < 3.3×10²⁴) and the same odd-digit-length-only palindrome enumeration (every even-length palindrome above 11 is divisible by 11). The difference between them on points is entirely submission-timestamp microseconds for rounds where both answered correctly.

## GLM: fast on small n, then collapses

GLM (5.1) takes a different shape. It precomputes while waiting for the first `ROUND` line, using `select()` on the socket to check whether a round has arrived. The strategy is correct for small n: GLM is the fastest bot on R1 to R4, often by an order of magnitude over DeepSeek, because by the time the first round arrives GLM has already built a list of 30,000 palprimes.

```python
sock.connect(('localhost', 7474))
sock.sendall((botname + '\n').encode('ascii'))

pp_gen = gen_palindromic_primes()
pp_list = []

count = 0
while len(pp_list) < 1_000_000:
    count += 1
    if count % 100 == 0:
        readable, _, _ = select.select([sock], [], [], 0)
        if readable:
            ...
            break
    pp_list.append(next(pp_gen))
```

The problem is in the round handler:

```python
deadline = time.time() + 25
while n > len(pp_list) and time.time() < deadline:
    try:
        pp_list.append(next(pp_gen))
    except StopIteration:
        break

if n <= len(pp_list):
    answer = longest_1_run(pp_list[n - 1])
else:
    answer = 1                              # ← bails out
```

When `n > len(pp_list)` and the 25-second deadline expires, GLM submits `ANSWER 1` and moves on. R8 (n = 250,000), R9 (n = 500,000), and R10 (n = 1,000,000) all trigger this fallback. Three wrong answers in a row, all scored zero. GLM keeps its 4 first-place finishes from R1 to R4 and lands 3rd overall on 40 points.

## Muse, Gemini, Nemotron: compute-per-round

Muse (Spark), Gemini (Pro 3.1), and Nemotron (3 Super) take the "compute from scratch on each ROUND" approach. The bots connect, register, then idle until a round arrives and enumerate palprimes inside the round handler. This works while the answer is in cache (each round's enumeration extends the local list, and subsequent rounds with smaller n hit the cache), but their enumerators are slower than DeepSeek's, so they fall behind as n grows.

Muse finishes 4th overall with 9 correct rounds and 24 points; the wins are mostly 3rd, 4th, and 5th-place finishes from R5 onward when its slower-but-correct enumerator finally completed. Gemini scores 20 points; Nemotron 5 points after consistent 6th and 7th place finishes. None of these three bots win a round.

All three time out on R10 (n = 1,000,000) with their palprime list still building.

## Kimi: an off-by-15 bug, two coincidences, and a 10-point R10

Kimi (K2.6) is the strangest bot in the field. It uses `multiprocessing.Pool` to enumerate palindromes and test primality across CPU cores in parallel, while answering rounds from a shared list. Strictly speaking it is not purely connect-first: `main()` calls `build_small(answers, TARGET)` before opening the socket, which handles the small palprimes (lengths 1, 2, 5, 7, 9, 11) synchronously. That pre-connect phase finishes inside the 10-second registration window in practice, so Kimi registers in time. The heavy lifting (lengths 13 and 15, via the multiprocess pool) happens after the connect, in parallel with rounds. The same general shape as DeepSeek and Claude — connect, then fill in the background — with the seed phase done up front and the bulk work parallelised.

The bug is in `build_small`, which seeds the small-n entries before the multiprocess pool starts up:

```python
def build_small(answers, target):
    # length 1
    for p in (2, 3, 5, 7):
        answers.append(max_one_run(p))      # ✓ indices 0–3
    # length 2
    answers.append(max_one_run(11))         # ✓ index 4
    # lengths 3,5,7,9,11 (k=3..6)            # ← comment lies
    for k in range(3, 7):                   # k = 3, 4, 5, 6
        start = POW10[k - 1]
        ...                                  # generates 2k-1 = 5, 7, 9, 11 digit palindromes
```

The variable `k` is the *half-length* of the constructed palindrome, not the digit count. For k=3 the loop produces 5-digit palindromes; for k=4 it produces 7-digit; and so on. The loop never hits k=2 (3-digit palindromes), and there is no special case for length-3 in `build_small`. The 15 three-digit palindromic primes (101, 131, 151, 181, 191, 313, 353, 373, 383, 727, 757, 787, 797, 919, 929) are silently omitted from Kimi's answer list.

Result: Kimi's `answers[n-1]` is the longest-1-run of the true `p(n+15)`, not `p(n)`. Every round Kimi submits the answer that would have been correct 15 indices later in the true sequence.

The off-by-15 hypothesis predicts Kimi's submitted value exactly:

| Round | n | True p(n+15) | longest_1_run(p(n+15)) | Kimi submitted | Match |
|---|---|---|---|---|---|
| R1 | 5,000 | 922,393,229 | 5 | 5 | ✓ |
| R2 | 10,000 | 13,663,036,631 | 3 | 3 | ✓ |
| R3 | 20,000 | 32,985,458,923 | 4 | 4 | ✓ |
| R4 | 30,000 | 72,469,696,427 | 6 | 6 | ✓ |
| R5 | 50,000 | 1,021,638,361,201 | 4 | 4 | ✓ |
| R6 | 75,000 | 1,295,479,745,921 | 3 | 3 | ✓ |
| R7 | 100,000 | 1,566,034,306,651 | 4 | 4 | ✓ |
| R8 | 250,000 | 7,242,506,052,427 | 3 | 3 | ✓ |
| R9 | 500,000 | 112,293,787,392,211 | 4 | 4 | ✓ |
| R10 | 1,000,000 | 175,608,575,806,571 | 6 | 6 | ✓ |

Ten rounds, ten exact matches with the off-by-15 prediction. The hypothesis is correct in every round.

Now compare against the true answers to see which rounds Kimi "got right":

| Round | n | True k | Kimi k | Result |
|---|---|---|---|---|
| R1 | 5,000 | 3 | 5 | wrong |
| R2 | 10,000 | 5 | 3 | wrong |
| R3 | 20,000 | 4 | 4 | **right (coincidence)** |
| R4 | 30,000 | 4 | 6 | wrong |
| R5 | 50,000 | 4 | 4 | **right (coincidence)** |
| R6 | 75,000 | 4 | 3 | wrong |
| R7 | 100,000 | 4 | 4 | **right (coincidence)** |
| R8 | 250,000 | 4 | 3 | wrong |
| R9 | 500,000 | 5 | 4 | wrong |
| R10 | 1,000,000 | 6 | 6 | **right (coincidence)** |

Every "correct" Kimi submission is a coincidence: `p(n)` and `p(n+15)` happen to share a longest-1-run value. The 1-run lengths in this range cluster around 3–5, so two arbitrary palprimes 15 apart have a non-trivial probability of matching by chance.

R10 is the punchline. Kimi was the *only* bot that answered R10 correctly. Every other bot that played R10 was still enumerating palprimes when the 30-second deadline hit. Kimi's lookup is instant because n=1,000,000 hit the precomputed cache, and `answers[999,999] = longest_1_run(p(1,000,015)) = 6`, which equals the true answer for `p(1,000,000) = 175,606,737,606,571` (binary `100111111011011010100001001101110001011110101011`, longest 1-run is the leading `111111` of length 6). A bug that happens to round to the correct answer at exactly the round where every other bot fails to answer at all.

Kimi banks 10 points for R10 plus 3 for R3, 1 for R5 (3rd-place after DeepSeek/Claude), and 5 for R7, totaling 18 points and a 6th-place finish.

## Counterfactual: what if Kimi's bug wasn't there?

Kimi's submission *times* aren't affected by the bug, only its answer values. Replaying the standings with every Kimi answer marked correct gives the field that would have run:

| Rank | Bot | Pts | Δ vs actual |
|---|---|---|---|
| **#1** | **DeepSeek (V4-Pro)** | 66 | −7 |
| **#2** | **Claude (Opus 4.7)** | 55 | −5 |
| **#3** | **Kimi (K2.6)** | 54 | +36 |
| #4 | GLM (5.1) | 40 | 0 |
| #5 | Muse (Spark) | 14 | −10 |
| #6 | Gemini (Pro 3.1) | 12 | −8 |
| #7 | Nemotron (3 Super) | 2 | −3 |

Even with the bug fixed, **DeepSeek still wins**. The reason is in Kimi's small-n submission times: 0.10 s on R1, 0.10 s on R2, 0.13 s on R3, 0.09 s on R4. GLM finishes those rounds in 0.04-0.06 s, DeepSeek in 0.06-0.10 s, Claude in 0.08-0.10 s. Even with correct answers, Kimi lands 4th on R1-R3 (3 points each) and 3rd on R4 (5 points). The 10/7/5/3/1 scale doesn't care that the gap is 50 ms; it just looks at order. Kimi's first-half ceiling is 14 points against DeepSeek's 34 (7+7+7+3+10) and Claude's 29 (5+5+5+7+7).

Kimi's parallel architecture wins R8, R9, R10 outright if the bug is fixed (instant cache lookup, every other bot still computing). That's 30 points. But 14 + 30 = 44 in the first/second half, plus 5+5 from R6 and R7 (3rd) = 54 total — still behind DeepSeek's 66. Kimi's bug cost it a clean 3rd place, never a 1st.

## The optimal bot none of them built

The three top-end strategies each get part of the architecture right and miss a different piece:

- **GLM**: synchronous fill during the registration window using `select()` to poll the socket. Fastest on R1-R7 because the cache is populated by the time `ROUND 1` arrives. Loses everything from R8 onward by submitting `ANSWER 1` as a fallback when its 25-second extension budget expires.
- **DeepSeek / Claude**: daemon-thread fill, round handler blocks on cache miss. Never bails out. Steady through R9. Single-threaded enumeration can't reach 1M palprimes within the tournament's cumulative compute budget, so they time out cleanly on R10.
- **Kimi**: `multiprocessing.Pool` enumerating 13- and 15-digit palindromes in parallel across CPU cores. Only architecture that reaches n=1,000,000 in time. Off-by-15 seed bug aside, it has the right structure for the upper end.

The composite optimum:

```
connect immediately
spawn multiprocessing.Pool over the heavy digit lengths (Kimi)
synchronously enumerate small palindromes while polling the socket (GLM)
on each ROUND: block until cache reaches n, never fall back to a wrong value (DeepSeek)
```

That bot would plausibly win most rounds: small-n on GLM-like populated-cache speed, mid-n on DeepSeek-style clean blocking behaviour, R10 on Kimi's parallel reach. No bot in the field combined all three pieces, and the composite is a sketch from the scoreboard, not a prototype that's been benchmarked. Kimi came closest in spirit, the seed bug aside; GLM came closest on the registration-window utilisation; DeepSeek's blocking handler is the right shape for failure cases.

## The verdict

DeepSeek (V4-Pro) wins on a clean implementation of the right algorithm: connect, register, daemon-thread fill, block-on-demand. 73 points, 4 first-place finishes, 9 of 10 rounds correct. Claude is second on the same approach with 60 points.

GLM lands 3rd on 40 points by being fastest in the first half and then collapsing in the second half, which is a classic 'precompute hits a wall' shape.

The challenge differentiated cleanly: tournament shape varied with the size of the cache each bot could amortise. DeepSeek's small overhead per palprime turned into a sustained lead from R5 onward. Kimi's parallel compute would have beaten everyone on R10 timing even with a correct seed phase, but the bug means most of its rounds were wrong despite the strong infrastructure.

Two bots (ChatGPT, Grok) DNP on a clock-arbitrage attempt that backfired. The organiser wrote `prompt.md §9` ("the bot may take any approach to compute `p(n)` … including pre-computation before the first `ROUND` line arrives") with narrow intent: small seed tables, an idle cache fill while waiting for `ROUND 1`. The 7-of-9 readership confirms this intent — every other bot in the field registers first and then precomputes, exactly as §9 was meant to allow. ChatGPT and Grok read §9 maximally — as a green light to convert the entire problem into untracked pre-tournament compute followed by ten zero-cost lookups, sidestepping the 30-second per-round budget altogether. ChatGPT's source comment makes the intent explicit: `# Precompute before connecting so no ROUND clock is running yet`. The 10-second registration window in `server.py` was almost certainly there for a different reason — make sure all entrants are connected before the gun fires — but it incidentally trips the clock-arbitrage strategy. Both bots were trying to game the clock; the unrelated tripwire caught them. The DNP classification is honest: they did not play. The prompt template gets a §4 disclosure of the registration window going forward; PalinPrimeBits is past spec-lock so its prompt can't be retroactively fixed.

---

*Model versions for this challenge: Claude Opus 4.7, Gemini Pro 3.1, Grok Expert 4.20, ChatGPT GPT 5.5, MiMo V2.5-Pro (DNF, ICoTL × 3 in generation), Nemotron 3 Super, GLM 5.1, Kimi K2.6, Meta Muse Spark, DeepSeek V4-Pro. 9 bots ran the full tournament; 7 successfully registered within the 10-second window. n ranged from 5,000 to 1,000,000. 30-second wall-clock per bot per round, 10-second registration window before R1. Bots were generated by sending `prompt.md` to each OpenRouter model in a single chat completion request (no `max_tokens` cap, `temperature=0.2`); five model bots were authored via direct chat. Server code, prompt, generated bots, and the per-round answers are at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
