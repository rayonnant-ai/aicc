/* link https://chatgpt.com/share/69bb48da-081c-8007-8be0-dd488762da0f */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define MAX_WIDTH 2000
#define MAX_HEIGHT 2000

typedef struct {
    int width, height, maxval;
    int data[MAX_HEIGHT][MAX_WIDTH][3]; // RGB
} Image;

typedef struct {
    int w, h;
    int data[64][64]; // binary digit image
} Digit;

// ---------- PPM READER ----------
int read_ppm(const char *filename, Image *img) {
    FILE *f = fopen(filename, "r");
    if (!f) return 0;

    char format[3];
    fscanf(f, "%2s", format);
    if (strcmp(format, "P3") != 0) {
        fclose(f);
        return 0;
    }

    fscanf(f, "%d %d %d", &img->width, &img->height, &img->maxval);

    for (int y = 0; y < img->height; y++) {
        for (int x = 0; x < img->width; x++) {
            fscanf(f, "%d %d %d",
                   &img->data[y][x][0],
                   &img->data[y][x][1],
                   &img->data[y][x][2]);
        }
    }

    fclose(f);
    return 1;
}

// ---------- GRAYSCALE + BINARIZE ----------
void binarize(Image *img, int out[MAX_HEIGHT][MAX_WIDTH]) {
    for (int y = 0; y < img->height; y++) {
        for (int x = 0; x < img->width; x++) {
            int r = img->data[y][x][0];
            int g = img->data[y][x][1];
            int b = img->data[y][x][2];

            int gray = (r + g + b) / 3;

            // simple threshold
            out[y][x] = (gray < 128) ? 1 : 0;
        }
    }
}

// ---------- EXTRACT DIGIT REGION ----------
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

// ---------- TEMPLATE MATCH ----------
int match_digit(Digit *d);

// crude templates (7x5 style scaled)
int templates[10][7][5] = {
    // 0
    {{1,1,1,1,1},
     {1,0,0,0,1},
     {1,0,0,1,1},
     {1,0,1,0,1},
     {1,1,0,0,1},
     {1,0,0,0,1},
     {1,1,1,1,1}},
    // 1
    {{0,0,1,0,0},
     {0,1,1,0,0},
     {1,0,1,0,0},
     {0,0,1,0,0},
     {0,0,1,0,0},
     {0,0,1,0,0},
     {1,1,1,1,1}},
    // 2
    {{1,1,1,1,1},
     {0,0,0,0,1},
     {0,0,0,1,1},
     {0,0,1,1,0},
     {0,1,1,0,0},
     {1,1,0,0,0},
     {1,1,1,1,1}},
    // 3
    {{1,1,1,1,1},
     {0,0,0,0,1},
     {0,0,1,1,1},
     {0,0,0,1,1},
     {0,0,0,0,1},
     {0,0,0,0,1},
     {1,1,1,1,1}},
    // 4
    {{1,0,0,1,0},
     {1,0,0,1,0},
     {1,0,0,1,0},
     {1,1,1,1,1},
     {0,0,0,1,0},
     {0,0,0,1,0},
     {0,0,0,1,0}},
    // 5
    {{1,1,1,1,1},
     {1,0,0,0,0},
     {1,1,1,1,0},
     {0,0,0,0,1},
     {0,0,0,0,1},
     {1,0,0,0,1},
     {1,1,1,1,1}},
    // 6
    {{1,1,1,1,1},
     {1,0,0,0,0},
     {1,1,1,1,0},
     {1,0,0,0,1},
     {1,0,0,0,1},
     {1,0,0,0,1},
     {1,1,1,1,1}},
    // 7
    {{1,1,1,1,1},
     {0,0,0,0,1},
     {0,0,0,1,0},
     {0,0,1,0,0},
     {0,1,0,0,0},
     {0,1,0,0,0},
     {0,1,0,0,0}},
    // 8
    {{1,1,1,1,1},
     {1,0,0,0,1},
     {1,1,1,1,1},
     {1,0,0,0,1},
     {1,0,0,0,1},
     {1,0,0,0,1},
     {1,1,1,1,1}},
    // 9
    {{1,1,1,1,1},
     {1,0,0,0,1},
     {1,0,0,0,1},
     {1,1,1,1,1},
     {0,0,0,0,1},
     {0,0,0,0,1},
     {1,1,1,1,1}}
};

// scale digit to 7x5 and compare
int match_digit(Digit *d) {
    int best = -1;
    int best_score = -1;

    for (int k = 0; k < 10; k++) {
        int score = 0;

        for (int y = 0; y < 7; y++) {
            for (int x = 0; x < 5; x++) {
                int sy = y * d->h / 7;
                int sx = x * d->w / 5;

                if (d->data[sy][sx] == templates[k][y][x])
                    score++;
            }
        }

        if (score > best_score) {
            best_score = score;
            best = k;
        }
    }

    return best;
}

// ---------- MAIN ----------
int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s input.ppm\n", argv[0]);
        return 1;
    }

    Image img;
    if (!read_ppm(argv[1], &img)) {
        fprintf(stderr, "Failed to read PPM\n");
        return 1;
    }

    static int bin[MAX_HEIGHT][MAX_WIDTH];
    binarize(&img, bin);

    // --- ASSUME FIXED GRID ---
    int digits = 6;
    int box_w = img.width / digits;
    int box_h = img.height;

    for (int i = 0; i < digits; i++) {
        Digit d;
        extract_digit(bin, i * box_w, 0, box_w, box_h, &d);

        int val = match_digit(&d);
        printf("%d", val);
    }

    printf("\n");

    return 0;
}