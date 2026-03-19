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
- **Gemini (1.5 Pro):** Code compiled and ran, but produced the wrong output.
- **Claude (3.5 Sonnet):** Code compiled and ran, but produced the wrong output.

For more details on this test, see the [article](sovietpost/article.md) and the [prompt](sovietpost/prompt.md).

