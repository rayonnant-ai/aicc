/* Gemini 3.1 Pro link https://gemini.google.com/share/fcf0bb4c0611 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* Skips comment lines starting with '#' in the PPM file */
void skip_comments(FILE *fp) {
    int c;
    while ((c = fgetc(fp)) != EOF) {
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r') continue;
        if (c == '#') {
            while ((c = fgetc(fp)) != EOF && c != '\n');
        } else {
            ungetc(c, fp);
            break;
        }
    }
}

/* Calculates the squared distance from a point to a line segment */
float dist2_to_segment(float px, float py, float ax, float ay, float bx, float by) {
    float l2 = (bx - ax) * (bx - ax) + (by - ay) * (by - ay);
    if (l2 == 0) return (px - ax) * (px - ax) + (py - ay) * (py - ay);
    float t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / l2;
    t = t < 0 ? 0 : (t > 1 ? 1 : t);
    float proj_x = ax + t * (bx - ax);
    float proj_y = ay + t * (by - ay);
    return (px - proj_x) * (px - proj_x) + (py - proj_y) * (py - proj_y);
}

/* Processes a single character bounding box, extracts the 9-segment mask, and outputs the digit */
void process_digit(int x_min, int x_max, unsigned char* img_bin, int img_width, int img_height) {
    int y_min = img_height, y_max = 0;
    int total_black = 0;
    
    for (int x = x_min; x <= x_max; x++) {
        for (int y = 0; y < img_height; y++) {
            if (img_bin[y * img_width + x]) {
                if (y < y_min) y_min = y;
                if (y > y_max) y_max = y;
                total_black++;
            }
        }
    }
    
    int w = x_max - x_min;
    int h = y_max - y_min;
    
    // Ignore stray noise or trivially small boxes
    if (w < img_width / 50 || h < img_height / 10 || total_black < 10) return;
    
    int votes[9] = {0};
    float y_mid = (y_min + y_max) / 2.0f;
    float lengths[9] = {
        w, w, w,                  // H1, H2, H3
        h/2.0f, h/2.0f, h/2.0f, h/2.0f, // V1, V2, V3, V4
        sqrt((float)w*w + (h/2.0f)*(h/2.0f)), // D1
        sqrt((float)w*w + (h/2.0f)*(h/2.0f))  // D2
    };

    float max_dist = w / 3.0f;
    if (max_dist < 2.0f) max_dist = 2.0f;
    float max_dist2 = max_dist * max_dist;

    // Distribute pixels to the nearest segments
    for (int y = y_min; y <= y_max; y++) {
        for (int x = x_min; x <= x_max; x++) {
            if (img_bin[y * img_width + x]) {
                float min_d2 = 1e9;
                int best_s = -1;
                for (int s = 0; s < 9; s++) {
                    float ax=0, ay=0, bx=0, by=0;
                    if(s==0){ax=x_min; ay=y_min; bx=x_max; by=y_min;} // Top H
                    else if(s==1){ax=x_min; ay=y_mid; bx=x_max; by=y_mid;} // Mid H
                    else if(s==2){ax=x_min; ay=y_max; bx=x_max; by=y_max;} // Bot H
                    else if(s==3){ax=x_min; ay=y_min; bx=x_min; by=y_mid;} // Top-Left V
                    else if(s==4){ax=x_max; ay=y_min; bx=x_max; by=y_mid;} // Top-Right V
                    else if(s==5){ax=x_min; ay=y_mid; bx=x_min; by=y_max;} // Bot-Left V
                    else if(s==6){ax=x_max; ay=y_mid; bx=x_max; by=y_max;} // Bot-Right V
                    else if(s==7){ax=x_min; ay=y_mid; bx=x_max; by=y_min;} // D1: Mid-Left to Top-Right
                    else if(s==8){ax=x_max; ay=y_mid; bx=x_min; by=y_max;} // D2: Mid-Right to Bot-Left
                    
                    float d2 = dist2_to_segment(x, y, ax, ay, bx, by);
                    if (d2 < min_d2) {
                        min_d2 = d2;
                        best_s = s;
                    }
                }
                if (best_s != -1 && min_d2 <= max_dist2) {
                    votes[best_s]++;
                }
            }
        }
    }
    
    // Normalize votes by physical length
    float norm_votes[9];
    float max_norm = 0;
    for (int s = 0; s < 9; s++) {
        norm_votes[s] = votes[s] / (lengths[s] + 1e-5f);
        if (norm_votes[s] > max_norm) max_norm = norm_votes[s];
    }
    
    int mask = 0;
    for (int s = 0; s < 9; s++) {
        if (norm_votes[s] > 0.25f * max_norm) { // Requires 25% of the max local thickness
            mask |= (1 << s);
        }
    }
    
    // Ideal 9-segment bitmasks for Soviet Postal format (0-9)
    int ideal_masks[10] = {
        0x07D, // 0: H1, H3, V1, V2, V3, V4
        0x0D0, // 1: V2, V4, D1
        0x115, // 2: H1, H3, V2, D2
        0x057, // 3: H1, H2, H3, V2, V4
        0x05A, // 4: H2, V1, V2, V4
        0x04F, // 5: H1, H2, H3, V1, V4
        0x0E6, // 6: H2, H3, V3, V4, D1
        0x111, // 7: H1, V2, D2
        0x07F, // 8: H1, H2, H3, V1, V2, V3, V4
        0x11B  // 9: H1, H2, V1, V2, D2
    };
    
    // Minimize Hamming Distance to find the closest digit match
    int min_dist = 99;
    int best_digit = -1;
    for (int d = 0; d < 10; d++) {
        int diff = mask ^ ideal_masks[d];
        int dist = 0;
        for (int b = 0; b < 9; b++) {
            if (diff & (1 << b)) dist++;
        }
        if (dist < min_dist) {
            min_dist = dist;
            best_digit = d;
        }
    }
    
    if (best_digit != -1) {
        printf("%d", best_digit);
    }
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <input.ppm>\n", argv[0]);
        return 1;
    }
    
    FILE *fp = fopen(argv[1], "r");
    if (!fp) {
        fprintf(stderr, "Could not open file %s\n", argv[1]);
        return 1;
    }
    
    char magic[3];
    if (fscanf(fp, "%2s", magic) != 1 || strcmp(magic, "P3") != 0) {
        fprintf(stderr, "Invalid PPM format. Must be ASCII P3.\n");
        fclose(fp);
        return 1;
    }
    
    skip_comments(fp);
    int w, h, max_val;
    if (fscanf(fp, "%d %d", &w, &h) != 2) { fclose(fp); return 1; }
    skip_comments(fp);
    if (fscanf(fp, "%d", &max_val) != 1) { fclose(fp); return 1; }
    
    unsigned char* img_bin = (unsigned char*)malloc(w * h);
    
    // Binarize
    for (int i = 0; i < w * h; i++) {
        int r, g, b;
        if (fscanf(fp, "%d %d %d", &r, &g, &b) != 3) break;
        // Identify the dark ink threshold
        if (r + g + b < 3 * max_val / 2) {
            img_bin[i] = 1;
        } else {
            img_bin[i] = 0;
        }
    }
    fclose(fp);
    
    // X-Projection
    int* col_sum = (int*)calloc(w, sizeof(int));
    for (int x = 0; x < w; x++) {
        for (int y = 0; y < h; y++) {
            col_sum[x] += img_bin[y * w + x];
        }
    }
    
    // Bridge minor gaps in continuous characters
    int max_gap = w / 100;
    if (max_gap < 3) max_gap = 3;
    int* col_sum_smooth = (int*)calloc(w, sizeof(int));
    for (int x = 0; x < w; x++) col_sum_smooth[x] = col_sum[x];
    
    for (int x = 0; x < w; x++) {
        if (col_sum[x] == 0) {
            int left_x = x - 1, right_x = x + 1;
            while(left_x >= 0 && col_sum[left_x] == 0) left_x--;
            while(right_x < w && col_sum[right_x] == 0) right_x++;
            if (left_x >= 0 && right_x < w && (right_x - left_x - 1) <= max_gap) {
                col_sum_smooth[x] = 1;
            }
        }
    }
    
    // Identify character regions and OCR
    int in_digit = 0;
    int x_start = 0;
    for (int x = 0; x <= w; x++) {
        int val = (x < w) ? col_sum_smooth[x] : 0;
        if (val > 0 && !in_digit) {
            in_digit = 1;
            x_start = x;
        } else if (val == 0 && in_digit) {
            in_digit = 0;
            int x_end = x - 1;
            if (x_end - x_start > max_gap) {
                process_digit(x_start, x_end, img_bin, w, h);
            }
        }
    }
    
    printf("\n");
    free(img_bin);
    free(col_sum);
    free(col_sum_smooth);
    return 0;
}