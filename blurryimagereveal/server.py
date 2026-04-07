"""
Dial-Up Download Tournament Server.

Loads images from images/ folder, sends progressive reveals to bots,
scores their guesses based on resolution confidence.
"""
import socket
import threading
import time
import random
import json
import os
from PIL import Image

# Configuration
HOST = 'localhost'
PORT = 7474
MAX_ROUNDS = 10
IMAGES_PER_ROUND = 10
REGISTRATION_WINDOW = 10.0
GUESS_TIMEOUT = 10.0
LOG_PATH = 'results.log'
IMG_DIR = 'images'

BLUR_RADII = [64, 32, 16, 8, 4, 2, 1, 0]
POINTS = [100, 60, 30, 15, 8, 4, 2, 1]
FULL_RES = 512


def rotate_log():
    if not os.path.exists(LOG_PATH):
        return
    n = 1
    while os.path.exists(f"{LOG_PATH}.{n}"):
        n += 1
    for i in range(n - 1, 0, -1):
        os.rename(f"{LOG_PATH}.{i}", f"{LOG_PATH}.{i+1}")
    os.rename(LOG_PATH, f"{LOG_PATH}.1")


def load_images():
    """Load all images from IMG_DIR, center-crop to square, resize to 512×512."""
    images = []
    for f in sorted(os.listdir(IMG_DIR)):
        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp')):
            path = os.path.join(IMG_DIR, f)
            try:
                img = Image.open(path).convert('RGB')
                # Center crop to square
                w, h = img.size
                side = min(w, h)
                left = (w - side) // 2
                top = (h - side) // 2
                img = img.crop((left, top, left + side, top + side))
                img = img.resize((FULL_RES, FULL_RES), Image.LANCZOS)
                images.append((f, img))
            except Exception as e:
                print(f"[!] Failed to load {path}: {e}")
    return images


def color_fingerprint(img):
    """Compute 4×4 block average RGB fingerprint (48 floats)."""
    pixels = list(img.getdata())
    fp = []
    block = FULL_RES // 4
    for by in range(4):
        for bx in range(4):
            r_sum = g_sum = b_sum = 0
            for dy in range(block):
                for dx in range(block):
                    r, g, b = pixels[(by * block + dy) * FULL_RES + bx * block + dx]
                    r_sum += r; g_sum += g; b_sum += b
            n = block * block
            fp.extend([r_sum / n, g_sum / n, b_sum / n])
    return fp


def fp_distance(fp1, fp2):
    return sum((a - b) ** 2 for a, b in zip(fp1, fp2))


MIN_PAIR_DISTANCE = 500.0  # minimum fingerprint distance between any two references


def pick_similar_group(all_images, fingerprints, n, used):
    """Pick n visually similar images, ensuring no two are too similar to distinguish."""
    available = [i for i in range(len(all_images)) if i not in used]
    if len(available) < n:
        available = list(range(len(all_images)))

    seed = random.choice(available)

    # Rank all available images by distance to seed
    dists = []
    for i in available:
        if i == seed:
            continue
        dists.append((fp_distance(fingerprints[seed], fingerprints[i]), i))
    dists.sort()

    # Greedily add candidates, skipping any too close to an already-selected image
    group = [seed]
    for _, candidate in dists:
        if len(group) >= n:
            break
        too_close = False
        for member in group:
            if fp_distance(fingerprints[candidate], fingerprints[member]) < MIN_PAIR_DISTANCE:
                too_close = True
                break
        if not too_close:
            group.append(candidate)

    # If we couldn't fill the group (unlikely), pad from remaining
    if len(group) < n:
        for _, candidate in dists:
            if candidate not in group:
                group.append(candidate)
            if len(group) >= n:
                break

    random.shuffle(group)
    return group


def image_to_ppm(img):
    """Convert PIL Image to ASCII PPM (P3) string."""
    w, h = img.size
    pixels = list(img.getdata())
    lines = [f"P3\n{w} {h}\n255"]
    for row_start in range(0, len(pixels), w):
        row = pixels[row_start:row_start + w]
        lines.append(" ".join(f"{r} {g} {b}" for r, g, b in row))
    return "\n".join(lines) + "\n"


def gaussian_blur(img, radius):
    """Apply Gaussian blur to an image. Returns blurred PIL Image."""
    if radius <= 0:
        return img.copy()
    from PIL import ImageFilter
    # PIL's GaussianBlur takes radius as a size parameter
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


class Client:
    def __init__(self, sock, name):
        self.sock = sock
        self.name = name
        self.score = 0
        self.f = sock.makefile('r', encoding='utf-8')

    def send(self, data):
        try:
            self.sock.sendall(data.encode('utf-8'))
        except OSError:
            pass

    def readline(self, timeout=None):
        if timeout:
            self.sock.settimeout(timeout)
        try:
            line = self.f.readline()
            if not line:
                return None
            return line.strip()
        except (OSError, socket.timeout):
            return None
        finally:
            if timeout:
                self.sock.settimeout(None)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def run_tournament():
    rotate_log()
    log = open(LOG_PATH, 'w', encoding='utf-8')

    # Load all available images
    all_images = load_images()
    if len(all_images) < IMAGES_PER_ROUND:
        print(f"[!] Need at least {IMAGES_PER_ROUND} images in {IMG_DIR}/, found {len(all_images)}")
        return

    print(f"[*] Loaded {len(all_images)} images from {IMG_DIR}/")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(10)
    server_sock.settimeout(1.0)

    clients = []

    print(f"[*] Server live on {HOST}:{PORT}. Registration: {REGISTRATION_WINDOW}s")
    start_reg = time.time()
    while time.time() - start_reg < REGISTRATION_WINDOW:
        try:
            conn, addr = server_sock.accept()
            conn.settimeout(None)
            name_line = conn.makefile('r').readline().strip()
            if name_line:
                client = Client(conn, name_line)
                clients.append(client)
                print(f"[*] Bot '{name_line}' joined.")
        except socket.timeout:
            continue

    if not clients:
        print("[!] No participants.")
        log.close()
        return

    print(f"[*] {len(clients)} bots registered. Starting tournament.\n")

    # Pre-compute fingerprints for similarity-based round selection
    fingerprints = [color_fingerprint(img) for _, img in all_images]
    print(f"[*] Computed color fingerprints for {len(fingerprints)} images.")

    used_seeds = set()

    for round_num in range(1, MAX_ROUNDS + 1):
        # Pick 10 visually similar images for this round
        group_indices = pick_similar_group(all_images, fingerprints, IMAGES_PER_ROUND, used_seeds)
        used_seeds.add(group_indices[0])
        round_images = [all_images[i] for i in group_indices]
        # Pick the mystery image (one of the 10)
        mystery_idx = random.randint(0, IMAGES_PER_ROUND - 1)
        mystery_name, mystery_img = round_images[mystery_idx]

        print(f"--- ROUND {round_num}: mystery={mystery_name} (index {mystery_idx}) ---")
        log.write(f"--- ROUND {round_num}: mystery={mystery_name} (index {mystery_idx}) ---\n")
        log.write(f"References: {[name for name, _ in round_images]}\n")

        # Pre-render all reference PPMs
        ref_ppms = []
        for i, (name, img) in enumerate(round_images):
            ppm = image_to_ppm(img)
            ref_ppms.append((i, ppm))

        # Send ROUND header and references to all clients in parallel
        def send_refs(client):
            client.send(f"ROUND {round_num}\n")
            client.send(f"REFERENCES {IMAGES_PER_ROUND}\n")
            for i, ppm in ref_ppms:
                client.send(f"REF {i} SIZE {len(ppm)}\n")
                client.send(ppm)

        threads = []
        for client in clients:
            t = threading.Thread(target=send_refs, args=(client,), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=30)

        # Progressive reveal
        round_results = {c.name: (None, None) for c in clients}  # name -> (points, step)
        eliminated = set()

        for step, blur_r in enumerate(BLUR_RADII):
            # Blur mystery image
            revealed = gaussian_blur(mystery_img, blur_r)
            ppm = image_to_ppm(revealed)

            # Send reveal to all non-eliminated clients in parallel
            def send_reveal(client):
                client.send(f"REVEAL {step} BLUR {blur_r} SIZE {len(ppm)}\n")
                client.send(ppm)
                client.send("GUESS?\n")

            reveal_threads = []
            for client in clients:
                if client.name in eliminated:
                    continue
                t = threading.Thread(target=send_reveal, args=(client,), daemon=True)
                t.start()
                reveal_threads.append(t)
            for t in reveal_threads:
                t.join(timeout=15)

            # Collect guesses in parallel
            guess_lock = threading.Lock()
            guesses = {}
            got_correct = False
            round_step_start = time.monotonic()

            def collect_guess(client):
                if client.name in eliminated:
                    return
                response = client.readline(timeout=GUESS_TIMEOUT)
                elapsed = time.monotonic()
                if response is None:
                    with guess_lock:
                        guesses[client.name] = ("TIMEOUT", elapsed)
                    return
                with guess_lock:
                    guesses[client.name] = (response, elapsed)

            threads = []
            for client in clients:
                if client.name not in eliminated:
                    t = threading.Thread(target=collect_guess, args=(client,), daemon=True)
                    t.start()
                    threads.append(t)
            for t in threads:
                t.join(timeout=GUESS_TIMEOUT + 2)

            # Process guesses
            for client in clients:
                if client.name in eliminated or client.name not in guesses:
                    continue
                response, resp_time = guesses[client.name]
                elapsed_ms = (resp_time - round_step_start) * 1000

                if response == "TIMEOUT":
                    eliminated.add(client.name)
                    round_results[client.name] = (0, step)
                    continue

                if response == "PASS":
                    continue

                if response.startswith("GUESS "):
                    try:
                        guess_idx = int(response.split()[1])
                    except (IndexError, ValueError):
                        eliminated.add(client.name)
                        client.send("WRONG parse_error\n")
                        round_results[client.name] = (0, step)
                        continue

                    if guess_idx == mystery_idx:
                        pts = POINTS[step]
                        client.score += pts
                        client.send(f"CORRECT {pts}\n")
                        round_results[client.name] = (pts, step)
                        eliminated.add(client.name)
                        log.write(f"  {client.name}: CORRECT at step {step} (blur={blur_r}) +{pts}pts ({elapsed_ms:.0f}ms)\n")
                        got_correct = True
                    else:
                        penalty = -10
                        client.score += penalty
                        client.send(f"WRONG {mystery_idx}\n")
                        round_results[client.name] = (penalty, step)
                        eliminated.add(client.name)
                        log.write(f"  {client.name}: WRONG (guessed {guess_idx}, actual {mystery_idx}) at step {step} (blur={blur_r}) {penalty}pts ({elapsed_ms:.0f}ms)\n")
                else:
                    eliminated.add(client.name)
                    round_results[client.name] = (0, step)

            # If someone got it right or all clients eliminated, skip remaining steps
            if got_correct or all(c.name in eliminated for c in clients):
                break

        # Clients that never guessed
        for client in clients:
            if round_results[client.name] == (None, None):
                round_results[client.name] = (0, len(BLUR_RADII))
                log.write(f"  {client.name}: NO GUESS (passed all steps)\n")

        # Print round summary
        for client in sorted(clients, key=lambda c: -(round_results[c.name][0] or 0)):
            pts, step = round_results[client.name]
            pts = pts or 0
            if step is not None and step < len(BLUR_RADII):
                blur_r = BLUR_RADII[step]
                status = f"+{pts}pts at blur={blur_r}" if pts > 0 else f"{pts}pts at blur={blur_r}"
            else:
                status = "no guess"
            line = f"  {client.name:<20} | {status:<25} | total: {client.score}"
            print(line)
            log.write(line + "\n")

        log.write("\n")
        log.flush()
        time.sleep(1)

    # Final standings
    header = "=" * 60 + "\nFINAL TOURNAMENT RESULTS\n" + "=" * 60
    print("\n" + header)
    log.write("\n" + header + "\n")

    sorted_clients = sorted(clients, key=lambda c: -c.score)
    for i, client in enumerate(sorted_clients):
        line = f"  #{i+1}  {client.name:<20} {client.score:>4} points"
        print(line)
        log.write(line + "\n")

    log.close()
    server_sock.close()
    for c in clients:
        c.close()


if __name__ == "__main__":
    run_tournament()
