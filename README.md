# LLM Comparison (`llmcomp`)

A repository for evaluating AI frontier models on simple programming tasks to see how well they perform in practice.

## Overview

This project aims to benchmark various Large Language Models (LLMs) by giving them specific, well-defined programming challenges. The goal is to see if they can produce valid, working, and correct code for tasks that require a bit more than just basic syntax knowledge.

## Tests

### 1. Soviet Post (`sovietpost/`)

**Task:** Write a C program that reads Soviet numerical postal codes from an ASCII `.ppm` file and outputs the digits to `stdout`. The program must only use standard libraries.

**Results:**
- **Grok:** Failed to produce valid C code.
- **ChatGPT:** Produced valid C code, but the executable resulted in a segmentation fault.
- **Gemini (3.1 Pro):** Code compiled and ran, but produced the wrong output.
- **Claude (Opus 4.6):** Code compiled and ran, but produced the wrong output.

For more details on this test, see the [article](sovietpost/article.md) and the [prompt](sovietpost/prompt.md).

### 2. Word Racer Champion (`wordracerchampion/`)

**Task:** Write a Python 3.10 client that connects to a TCP server, receives a 15×15 letter grid, and races to find and submit valid dictionary words traced adjacently on the grid. Scoring: `letters − 6`. Four bots compete simultaneously in a ten-second round.

**Results:**
- **ChatGPT (GPT 5.3):** Submitted thousands of valid but unprofitable short words, scoring −74,383 cumulative across three rounds.
- **Grok (Expert 4.2):** Same short-word mistake but throttled by synchronous I/O, scoring −1,520 cumulative.
- **Gemini (Pro 3.1):** Too slow to claim any words before Claude, scoring 0 in all three rounds.
- **Claude (Opus 4.6):** Only bot to filter for profitable word lengths (7+), with a pipelined three-thread architecture. Scored +854 cumulative, winning all three rounds.

For more details on this test, see the [article](wordracerchampion/article.md) and the [prompt](wordracerchampion/prompt.md).

