import socket
import sys

def parse_ppm(data_bytes):
    """Parse ASCII PPM P3 data (bytes) into list-of-lists of (R,G,B) tuples. Fast path using split."""
    text = data_bytes.decode('ascii')
    tokens = text.split()
    assert tokens[0] == 'P3'
    w = int(tokens[1])
    h = int(tokens[2])
    maxv = int(tokens[3])
    assert maxv == 255
    assert len(tokens) == 4 + w * h * 3
    pixels = []
    idx = 4
    for y in range(h):
        row = []
        for x in range(w):
            r = int(tokens[idx])
            g = int(tokens[idx + 1])
            b = int(tokens[idx + 2])
            row.append((r, g, b))
            idx += 3
        pixels.append(row)
    return pixels


def downsample_to_size(img, target):
    """Downsample 512x512 image to target×target by block averaging (box filter approximation of blur)."""
    if target == 512:
        return [row[:] for row in img]  # shallow copy of structure
    block = 512 // target
    ds = [[(0, 0, 0) for _ in range(target)] for _ in range(target)]
    for ty in range(target):
        for tx in range(target):
            sr = sg = sb = 0
            for dy in range(block):
                for dx in range(block):
                    r, g, b = img[ty * block + dy][tx * block + dx]
                    sr += r
                    sg += g
                    sb += b
            n = block * block
            ds[ty][tx] = (sr // n, sg // n, sb // n)
    return ds


def compute_mse(a, b, size):
    """Sum of squared differences on two size×size images."""
    total = 0
    for y in range(size):
        for x in range(size):
            ra, ga, ba = a[y][x]
            rb, gb, bb = b[y][x]
            total += (ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2
    return total


def get_target_size(blur):
    """Map blur radius → thumbnail size (larger blur → smaller thumbnail)."""
    return {
        64: 8,
        32: 16,
        16: 32,
        8: 64,
        4: 128,
        2: 256,
        1: 512,
        0: 512,
    }[blur]


def get_confidence_threshold(blur):
    """Higher threshold for blurrier images (require stronger signal to guess early)."""
    return 1.8 + (blur / 32.0)  # blur=64 → ~3.8× better, blur=0 → 1.8× better


def main():
    bot_name = "grok_dialup_bot"
    if len(sys.argv) > 1:
        bot_name = sys.argv[1]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall(f"{bot_name}\n".encode('ascii'))

    f = sock.makefile('rb')

    def read_line():
        line = f.readline()
        if not line:
            print("Connection closed by server.", file=sys.stderr)
            sys.exit(0)
        return line.decode('ascii').rstrip('\r\n')

    references = None
    ds_cache = None

    while True:
        line = read_line()

        if line.startswith('ROUND'):
            round_n = int(line.split()[1])
            print(f"\n=== Round {round_n} ===", file=sys.stderr)

            refs_line = read_line()
            assert refs_line == 'REFERENCES 10'

            references = [None] * 10
            ds_cache = {}

            for _ in range(10):
                ref_line = read_line()
                parts = ref_line.split()
                ref_idx = int(parts[1])
                size = int(parts[3])
                ppm_bytes = f.read(size)
                img = parse_ppm(ppm_bytes)
                references[ref_idx] = img

                # Precompute downsampled versions for all possible target sizes
                for t in (8, 16, 32, 64, 128, 256, 512):
                    ds_cache.setdefault(t, [None] * 10)
                    ds_cache[t][ref_idx] = downsample_to_size(img, t)

            print(f"  → 10 references loaded & pre-downsampled", file=sys.stderr)
            continue

        if line.startswith('REVEAL'):
            parts = line.split()
            step = int(parts[1])
            blur = int(parts[3])
            size = int(parts[5])

            ppm_bytes = f.read(size)
            reveal_img = parse_ppm(ppm_bytes)

            guess_prompt = read_line()
            assert guess_prompt == 'GUESS?'

            target = get_target_size(blur)
            reveal_ds = downsample_to_size(reveal_img, target)
            ref_dss = ds_cache[target]

            # Find best and second-best matches
            best_mse = float('inf')
            second_mse = float('inf')
            best_idx = -1

            for idx, ref_ds in enumerate(ref_dss):
                mse = compute_mse(ref_ds, reveal_ds, target)
                if mse < best_mse:
                    second_mse = best_mse
                    best_mse = mse
                    best_idx = idx
                elif mse < second_mse:
                    second_mse = mse

            # Confidence metric
            if best_mse == 0:
                confidence_ratio = float('inf')
            else:
                confidence_ratio = second_mse / best_mse if second_mse > 0 else float('inf')

            thresh = get_confidence_threshold(blur)
            should_guess = confidence_ratio > thresh or best_mse == 0

            print(f"  Step {step:2d} | blur={blur:2d} | target={target:3d} | "
                  f"best={best_idx} (MSE={best_mse:,}) | ratio={confidence_ratio:.2f} "
                  f"→ {'GUESS' if should_guess else 'PASS'}", file=sys.stderr)

            if should_guess:
                sock.sendall(f"GUESS {best_idx}\n".encode('ascii'))
                resp = read_line()
                print(f"  Server → {resp}", file=sys.stderr)
                # Round ends here – next line will be ROUND
            else:
                sock.sendall(b"PASS\n")
                # Continue to next REVEAL

        elif line.startswith(('CORRECT', 'WRONG')):
            print(f"  Server → {line}", file=sys.stderr)
        else:
            print(f"  Unexpected: {line}", file=sys.stderr)


if __name__ == "__main__":
    main()