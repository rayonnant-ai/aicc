/*
 * soviet_ocr.c — OCR for Soviet postal code digits from PPM images.
 *
 * Soviet postal envelopes had comb fields (pre-printed dot grids in dropout
 * colour) at the bottom.  The sender formed each digit of the 6-digit postal
 * index (почтовый индекс) by connecting specific dots with straight lines,
 * producing a distinctive angular block font.
 *
 * Recognition pipeline
 * ────────────────────
 *   1. Read P3 (ASCII) or P6 (binary) PPM → grayscale.
 *   2. Otsu binarisation → ink / background.
 *   3. Projection-based segmentation with run-merging → digit bounding boxes.
 *   4. Seven-segment + diagonal template matching → digit classification.
 *
 * The Soviet "0" is a slashed zero (diagonal from lower-left to upper-right),
 * which distinguishes it from "8" (middle bar, no diagonal).
 *
 * Compile:  cc -o soviet_ocr soviet_ocr.c -lm
 * Usage:    ./soviet_ocr input.ppm
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <math.h>

/* ── limits ─────────────────────────────────────────────────────────── */

#define MAX_DIGITS  256
#define MAX_ROWS     64
#define MAX_COLS     64
#define N_SEG         8        /* 7 standard segments + 1 diagonal    */

/* ── image data (module-level) ──────────────────────────────────────── */

static int       W, H;        /* image dimensions                     */
static unsigned char *gray;    /* grey-scale  0-255                    */
static unsigned char *ink;     /* binary: 1 = ink, 0 = background     */

/* ── bounding box ───────────────────────────────────────────────────── */

typedef struct { int x, y, w, h; } Box;

/* ══════════════════════════════════════════════════════════════════════
 *  PPM reader – handles P3 (ASCII) and P6 (raw), with # comments
 * ══════════════════════════════════════════════════════════════════════ */

static int ppm_next_int(FILE *f)
{
    int c;
    for (;;) {
        while ((c = fgetc(f)) != EOF && isspace(c))
            ;
        if (c == EOF) return -1;
        if (c == '#') {
            while ((c = fgetc(f)) != EOF && c != '\n')
                ;
            continue;
        }
        ungetc(c, f);
        int v;
        if (fscanf(f, "%d", &v) == 1) return v;
        return -1;
    }
}

static int read_ppm(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "error: cannot open '%s'\n", path); return -1; }

    int c1 = fgetc(f), c2 = fgetc(f);
    if (c1 != 'P' || (c2 != '3' && c2 != '6')) {
        fprintf(stderr, "error: '%s' is not a valid PPM file\n", path);
        fclose(f); return -1;
    }
    int ascii = (c2 == '3');

    W = ppm_next_int(f);
    H = ppm_next_int(f);
    int maxv = ppm_next_int(f);
    if (W <= 0 || H <= 0 || maxv <= 0) {
        fprintf(stderr, "error: bad PPM header in '%s'\n", path);
        fclose(f); return -1;
    }

    if (!ascii) fgetc(f);  /* consume single whitespace after maxval */

    int n = W * H;
    gray = (unsigned char *)malloc(n);
    ink  = (unsigned char *)calloc(n, 1);
    if (!gray || !ink) { fclose(f); return -1; }

    for (int i = 0; i < n; i++) {
        int r, g, b;
        if (ascii) {
            r = ppm_next_int(f);
            g = ppm_next_int(f);
            b = ppm_next_int(f);
        } else {
            r = fgetc(f); g = fgetc(f); b = fgetc(f);
        }
        if (r < 0 || g < 0 || b < 0) { fclose(f); return -1; }
        if (maxv != 255 && maxv > 0) {
            r = r * 255 / maxv;
            g = g * 255 / maxv;
            b = b * 255 / maxv;
        }
        gray[i] = (unsigned char)(0.299 * r + 0.587 * g + 0.114 * b);
    }
    fclose(f);
    return 0;
}

/* ══════════════════════════════════════════════════════════════════════
 *  Otsu binarisation
 * ══════════════════════════════════════════════════════════════════════ */

static void binarise(void)
{
    long hist[256] = {0};
    int  n = W * H;
    for (int i = 0; i < n; i++) hist[gray[i]]++;

    double total_sum = 0;
    for (int i = 0; i < 256; i++) total_sum += (double)i * hist[i];

    double sum_bg = 0, best_var = -1;
    long   w_bg = 0;
    int    best_t = 128;

    for (int t = 0; t < 256; t++) {
        w_bg += hist[t];
        if (w_bg == 0) continue;
        long w_fg = n - w_bg;
        if (w_fg == 0) break;
        sum_bg += (double)t * hist[t];
        double m_bg = sum_bg / w_bg;
        double m_fg = (total_sum - sum_bg) / w_fg;
        double d    = m_bg - m_fg;
        double var  = (double)w_bg * w_fg * d * d;
        if (var > best_var) { best_var = var; best_t = t; }
    }

    for (int i = 0; i < n; i++)
        ink[i] = (gray[i] <= best_t) ? 1 : 0;
}

/* ══════════════════════════════════════════════════════════════════════
 *  Projection helpers
 * ══════════════════════════════════════════════════════════════════════ */

static int row_count(int y, int x1, int x2)
{
    int c = 0;
    for (int x = x1; x < x2; x++) c += ink[y * W + x];
    return c;
}
static int col_count(int x, int y1, int y2)
{
    int c = 0;
    for (int y = y1; y < y2; y++) c += ink[y * W + x];
    return c;
}

/*
 * Walk a projection array and return contiguous runs with value > thresh.
 * Stores start/end pairs in caller-supplied arrays; returns the count.
 */
static int find_runs(const int *proj, int len, int thresh,
                     int *starts, int *ends, int cap)
{
    int cnt = 0, in = 0;
    for (int i = 0; i < len; i++) {
        if (proj[i] > thresh) {
            if (!in) { if (cnt < cap) starts[cnt] = i; in = 1; }
        } else {
            if (in) { if (cnt < cap) ends[cnt] = i; cnt++; in = 0; }
        }
    }
    if (in) { if (cnt < cap) ends[cnt] = len; cnt++; }
    return cnt < cap ? cnt : cap;
}

/* Note: for noisy scanned images, a merge_close_runs() helper can be
 * inserted here to merge column-runs separated by tiny gaps (< 30 %
 * of estimated digit width).  For clean rendered images the zero-
 * threshold vertical projection already keeps digit interiors intact. */

/* ══════════════════════════════════════════════════════════════════════
 *  Digit segmentation
 * ══════════════════════════════════════════════════════════════════════ */

/* Trim blank margin from a bounding box (in-place). */
static void trim_box(Box *b)
{
    while (b->h > 1 && row_count(b->y, b->x, b->x + b->w) == 0)
        { b->y++; b->h--; }
    while (b->h > 1 && row_count(b->y + b->h - 1, b->x, b->x + b->w) == 0)
        b->h--;
    while (b->w > 1 && col_count(b->x, b->y, b->y + b->h) == 0)
        { b->x++; b->w--; }
    while (b->w > 1 && col_count(b->x + b->w - 1, b->y, b->y + b->h) == 0)
        b->w--;
}

/*
 * Locate every digit in the image.
 *
 *  1. Horizontal projection → row bands that contain ink.
 *  2. Vertical projection within each band → individual digit columns.
 *  3. Merge column-runs whose gaps are small relative to the widest run
 *     (keeps digits like "4" and "7" intact — their sparse interior
 *      produces thin projection valleys that must not be treated as
 *      inter-digit gaps).
 */
static int find_digits(Box *out, int cap)
{
    /* ── Step 1: horizontal projection → row bands ── */
    int *hp = (int *)calloc(H, sizeof(int));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            hp[y] += ink[y * W + x];

    int h_thresh = W / 50;
    if (h_thresh < 1) h_thresh = 1;
    int rs[MAX_ROWS], re[MAX_ROWS];
    int nr = find_runs(hp, H, h_thresh, rs, re, MAX_ROWS);
    free(hp);

    /* merge row bands that are very close together (e.g. stroke
     * bleed, not actual inter-row gaps — use a tight threshold)  */
    for (int i = 0; i + 1 < nr; ) {
        int gap    = rs[i + 1] - re[i];
        int band_h = (re[i] - rs[i] + re[i + 1] - rs[i + 1]) / 2;
        int limit  = band_h / 8;
        if (limit < 3) limit = 3;
        if (gap < limit) {
            re[i] = re[i + 1];
            for (int j = i + 1; j + 1 < nr; j++) {
                rs[j] = rs[j + 1]; re[j] = re[j + 1];
            }
            nr--;
        } else i++;
    }

    /* ── Step 2 & 3: vertical projection per row band ── */
    int total = 0;
    for (int r = 0; r < nr && total < cap; r++) {
        int y1 = rs[r], y2 = re[r], rh = y2 - y1;
        if (rh < 4) continue;

        /* vertical projection — threshold = 0 keeps even single-pixel
         * columns alive so thin horizontal bars are not cut              */
        int *vp = (int *)calloc(W, sizeof(int));
        for (int x = 0; x < W; x++)
            for (int y = y1; y < y2; y++)
                vp[x] += ink[y * W + x];

        int cs[MAX_COLS], ce[MAX_COLS];
        int nc = find_runs(vp, W, 0, cs, ce, MAX_COLS);
        free(vp);

        /* With threshold = 0 every column containing even one ink pixel
         * is included, so digits like "4" and "7" whose interiors have
         * thin horizontal bars are kept intact.  No merging is needed
         * for clean images; for noisy scans a small merge would be
         * added here.                                                   */

        /* Filter out tiny noise fragments */
        int min_w = rh / 10;
        if (min_w < 2) min_w = 2;
        for (int c = 0; c < nc && total < cap; c++) {
            int cw = ce[c] - cs[c];
            if (cw < min_w) continue;
            out[total].x = cs[c];
            out[total].y = y1;
            out[total].w = cw;
            out[total].h = rh;
            total++;
        }
    }
    return total;
}

/* ══════════════════════════════════════════════════════════════════════
 *  Seven-segment + diagonal classification
 * ══════════════════════════════════════════════════════════════════════
 *
 *  Segment map (standard seven-segment labels):
 *
 *       ╶──a──╴
 *      │       │
 *      f       b
 *      │       │
 *       ╶──g──╴          ← middle bar
 *      │       │
 *      e       c
 *      │       │
 *       ╶──d──╴
 *
 *  Plus segment index 7 = diagonal (/) for the Soviet slashed zero.
 *
 *  Indices:  0=a  1=b  2=c  3=d  4=e  5=f  6=g  7=diag
 */

/* Reference templates: 1.0 = segment on, 0.0 = off.
 *                 a    b    c    d    e    f    g   diag */
static const double TMPL[10][N_SEG] = {
    /* 0 */ { 1,   1,   1,   1,   1,   1,   0,   1 },
    /* 1 */ { 0,   1,   1,   0,   0,   0,   0,   0 },
    /* 2 */ { 1,   1,   0,   1,   1,   0,   1,   0 },
    /* 3 */ { 1,   1,   1,   1,   0,   0,   1,   0 },
    /* 4 */ { 0,   1,   1,   0,   0,   1,   1,   0 },
    /* 5 */ { 1,   0,   1,   1,   0,   1,   1,   0 },
    /* 6 */ { 1,   0,   1,   1,   1,   1,   1,   0 },
    /* 7 */ { 1,   1,   1,   0,   0,   0,   0,   0 },
    /* 8 */ { 1,   1,   1,   1,   1,   1,   1,   0 },
    /* 9 */ { 1,   1,   1,   1,   0,   1,   1,   0 },
};

/* Ink density in a rectangle.  Returns 0.0-1.0. */
static double rect_density(int rx, int ry, int rw, int rh)
{
    if (rw <= 0 || rh <= 0) return 0.0;
    int cnt = 0;
    for (int y = ry; y < ry + rh && y < H; y++)
        for (int x = rx; x < rx + rw && x < W; x++)
            cnt += ink[y * W + x];
    return (double)cnt / ((double)rw * rh);
}

/*
 * Ink density along the "/" diagonal (lower-left → upper-right).
 * Only the central 60 % of the path is sampled so the vertical edge
 * strokes of a closed rectangle do not contaminate the measurement
 * (critical for distinguishing "0" from "8").
 */
static double diag_density(int bx, int by, int bw, int bh)
{
    if (bw < 3 || bh < 3) return 0.0;
    int thick = bw / 7;
    if (thick < 1) thick = 1;

    int cnt = 0, tot = 0;
    int i0 = bh * 20 / 100;
    int i1 = bh * 80 / 100;
    for (int i = i0; i < i1; i++) {
        int cy = by + i;
        int cx = bx + (int)((double)(bh - 1 - i) / (bh - 1) * (bw - 1));
        for (int dx = -thick; dx <= thick; dx++) {
            int xx = cx + dx;
            if (xx > bx + bw / 5 && xx < bx + bw - bw / 5 &&
                cy >= 0 && cy < H && xx >= 0 && xx < W)
            {
                tot++;
                cnt += ink[cy * W + xx];
            }
        }
    }
    return tot > 0 ? (double)cnt / tot : 0.0;
}

static int classify(Box *b)
{
    int bx = b->x, by = b->y, bw = b->w, bh = b->h;

    /* ── fast heuristic: very narrow glyph → "1" ── */
    if (bw > 0 && (bh * 10 / bw) >= 35) return 1;

    /* ── measure the eight segment densities ── */
    double seg[N_SEG];

    int sh = bh * 20 / 100; if (sh < 1) sh = 1;
    int hx = bx + bw * 20 / 100;
    int hw = bw * 60 / 100; if (hw < 1) hw = 1;
    int vw = bw * 30 / 100; if (vw < 1) vw = 1;
    int vh = bh * 35 / 100; if (vh < 1) vh = 1;

    seg[0] = rect_density(hx,            by,                       hw, sh);  /* a top     */
    seg[1] = rect_density(bx + bw - vw,  by + sh / 2,             vw, vh);  /* b top-R   */
    seg[2] = rect_density(bx + bw - vw,  by + bh - vh - sh / 2,  vw, vh);  /* c bot-R   */
    seg[3] = rect_density(hx,            by + bh - sh,            hw, sh);  /* d bottom  */
    seg[4] = rect_density(bx,            by + bh - vh - sh / 2,  vw, vh);  /* e bot-L   */
    seg[5] = rect_density(bx,            by + sh / 2,             vw, vh);  /* f top-L   */
    seg[6] = rect_density(hx,            by + bh / 2 - sh / 2,   hw, sh);  /* g middle  */
    seg[7] = diag_density(bx, by, bw, bh);                                  /* diagonal  */

    /* ── normalise so the brightest segment ≈ 1.0 ── */
    double mx = 0;
    for (int i = 0; i < N_SEG; i++)
        if (seg[i] > mx) mx = seg[i];
    if (mx > 1e-6)
        for (int i = 0; i < N_SEG; i++) seg[i] /= mx;

    /* ── nearest template (Euclidean distance) ── */
    int    best   = 0;
    double best_d = 1e30;
    for (int d = 0; d < 10; d++) {
        double dist = 0;
        for (int s = 0; s < N_SEG; s++) {
            double diff = seg[s] - TMPL[d][s];
            dist += diff * diff;
        }
        if (dist < best_d) { best_d = dist; best = d; }
    }
    return best;
}

/* ══════════════════════════════════════════════════════════════════════
 *  main
 * ══════════════════════════════════════════════════════════════════════ */

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <image.ppm>\n", argv[0]);
        return 1;
    }

    /* 1. Read & binarise */
    if (read_ppm(argv[1]) != 0) return 1;
    binarise();

    /* 2. Find digit bounding boxes */
    Box boxes[MAX_DIGITS];
    int n = find_digits(boxes, MAX_DIGITS);
    if (n == 0) { fprintf(stderr, "No digits found.\n"); goto done; }

    /* 3. Trim each box */
    for (int i = 0; i < n; i++) trim_box(&boxes[i]);

    /* 4. Classify & output — insert newlines between distinct text rows */
    int prev_mid_y = boxes[0].y + boxes[0].h / 2;
    for (int i = 0; i < n; i++) {
        int mid_y = boxes[i].y + boxes[i].h / 2;
        if (i > 0 && abs(mid_y - prev_mid_y) > boxes[i].h / 2)
            putchar('\n');
        prev_mid_y = mid_y;

        if (boxes[i].w < 2 || boxes[i].h < 2) continue;
        printf("%d", classify(&boxes[i]));
    }
    putchar('\n');

done:
    free(gray);
    free(ink);
    return 0;
}