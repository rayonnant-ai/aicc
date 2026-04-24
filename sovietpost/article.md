**I Asked Frontier AI Models to Solve a Simple Programming Problem. They All Failed.**

My LinkedIn and Twitter feeds are flooed with posts like these: "I asked Claude Code to build a CRM from scratch. 5 minutes later, it gave me a working prototype."

I decided to put the hype to the test. I gave four of the leading "frontier" models a specific but simple C programming challenge inspired by real Soviet-era postal technology. Grok, ChatGPT, Gemini, and Claude all failed.

The prompt was unambiguous:

> Comb fields are pre-printed boxes that encourage humans to write more legibly – one glyph per box. These are often printed in a dropout color which can be easily removed by the OCR system. This technique was used in the former Soviet Union which had numeric postal codes and standardized boxes at the bottom of all envelopes where the user printed out the digits by connecting the dots.
>
> Write a C program that reads a group of Soviet numerical postal codes from an ASCII .ppm file and outputs the results. The input should be the name of the file. Print the output to stdout.
>
> You cannot use any libraries other than standard libraries.


Here’s what each of them produced.

### Grok: Didn’t even produce valid C code

The code [Grok](https://grok.com/share/c2hhcmQtMi1jb3B5_f76b1247-1607-4181-b226-d651842d214a) returned was riddled with syntax errors and missing declarations. While LLMs may not be deterministic, compilers definitely are. If you feed them code with incorrect syntax, you get errors.

```bash
$ gcc grok.c -o grok
grok.c:17:1: error: expected identifier or ‘(’ before ‘}’ token
grok.c: In function ‘is_filled’:
grok.c:20:8: warning: implicit declaration of function ‘gray’
grok.c: At top level:
grok.c:40:1: error: expected identifier or ‘(’ before ‘}’ token
grok.c: In function ‘main’:
grok.c:85:13: warning: implicit declaration of function ‘recognize_digit’
grok.c:85:29: error: ‘start_x’ undeclared
grok.c:85:73: error: ‘box_h’ undeclared
```

It never even reached runtime. Score: 0/10 for failing basic C syntax.

### ChatGPT: Valid C that immediately segfaulted

[ChatGPT](https://chatgpt.com/share/69bb48da-081c-8007-8be0-dd488762da0f) managed to output syntactically correct code that compiled without warnings. Progress!

But when ran it, it crashed instantly on the test image with a segmentation fault.

```bash
$ ./chatgpt sovpost.ppm 
Segmentation fault (core dumped)
```

It took only a cursory glance at ChatGPT's code to see the problem. ChatGPT wrote C code with no bounds checking

```c
typedef struct {
    int width, height, maxval;
    int data[MAX_HEIGHT][MAX_WIDTH][3]; // RGB
} Image;

typedef struct {
    int w, h;
    int data[64][64]; // binary digit image
} Digit;

/*...*/

void extract_digit(int bin[MAX_HEIGHT][MAX_WIDTH],
                   int x0, int y0, int w, int h,
                   Digit *d) {
    d->w = w;
    d->h = h;

    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            d->data[y][x] = bin[y0 + y][x0 + x];
        }
    }
}
```

### Gemini 3.1 Pro: Ran but got 2 out of the 3 digits wrong

Gemini actually produced runnable code. It read the file, processed the pixels, and printed a result:

```bash
$ ./gemini sovpost.ppm 
275
```

Unfortunately, 275 was not the correct postal code in the image. The numbers in the image were 234. Gemini at least got the first digit right.

### Claude (Opus 4.6 extended): Also ran, also wrong

Claude took more than 15 minutes to come up with a solution. But like Gemini, it produced runnable code that gave the wrong answer:

```bash
$ ./claude sovpost.ppm 
354
8
```

Like Gemini, Claude got one digit right.

### The Verdict

Every single frontier model failed to complete my simple programming challenge. Grok floundered even before it left the starting gate. ChatGPT got owned by a rookie mistake. Gemini and Claude produce runnable code that produced wrong results.

The "frontier models" in 2026 couldn't even solve a problem that the Soviets had solved in the 1970s.

### Code

All the code for this article can be found [here](https://github.com/rayonnant-ai/aicc)