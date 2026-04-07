import socket

def parse_ppm(data):
    """Parse ASCII PPM (P3) data from bytes."""
    s = data.decode('ascii')
    tokens = s.split()
    if tokens[0] != 'P3':
        raise ValueError("Not a P3 PPM file")
    width = int(tokens[1])
    height = int(tokens[2])
    maxval = int(tokens[3])
    if maxval != 255:
        raise ValueError("Only maxval=255 supported")
    expected_tokens = 4 + width * height * 3
    if len(tokens) != expected_tokens:
        raise ValueError(f"Invalid number of tokens: expected {expected_tokens}, got {len(tokens)}")
    vals = list(map(int, tokens[4:]))
    image = []
    idx = 0
    for y in range(height):
        row = []
        for x in range(width):
            r = vals[idx]
            g = vals[idx+1]
            b = vals[idx+2]
            row.append([r, g, b])
            idx += 3
        image.append(row)
    return image

def block_averages(image, block_size):
    """Compute average RGB values for non‑overlapping blocks of size block_size x block_size."""
    height = len(image)
    width = len(image[0]) if height > 0 else 0
    n_blocks_y = height // block_size
    n_blocks_x = width // block_size
    averages = []
    for by in range(n_blocks_y):
        for bx in range(n_blocks_x):
            y_start = by * block_size
            y_end = y_start + block_size
            x_start = bx * block_size
            x_end = x_start + block_size
            sum_r = 0
            sum_g = 0
            sum_b = 0
            count = 0
            for y in range(y_start, y_end):
                for x in range(x_start, x_end):
                    if y < height and x < width:
                        pixel = image[y][x]
                        sum_r += pixel[0]
                        sum_g += pixel[1]
                        sum_b += pixel[2]
                        count += 1
            if count > 0:
                avg_r = sum_r // count
                avg_g = sum_g // count
                avg_b = sum_b // count
            else:
                avg_r = avg_g = avg_b = 0
            averages.append((avg_r, avg_g, avg_b))
    return averages

def ssd(list1, list2):
    """Sum of squared differences between two lists of RGB tuples."""
    if len(list1) != len(list2):
        raise ValueError("Lists must be of equal length")
    total = 0
    for (r1, g1, b1), (r2, g2, b2) in zip(list1, list2):
        dr = r1 - r2
        dg = g1 - g2
        db = b1 - b2
        total += dr*dr + dg*dg + db*db
    return total

def main():
    host = 'localhost'
    port = 7474
    sock = socket.create_connection((host, port))
    try:
        # Send bot name
        bot_name = "nemo_bot\n"
        sock.sendall(bot_name.encode('ascii'))
        
        for round_num in range(1, 11):  # 10 rounds
            # Read ROUND line
            line = b''
            while not line.endswith(b'\n'):
                ch = sock.recv(1)
                if not ch:
                    break
                line += ch
            line = line.decode('ascii').strip()
            if not line.startswith("ROUND"):
                print(f"Unexpected line: {line}")
                break
            
            # Read REFERENCES line
            line = b''
            while not line.endswith(b'\n'):
                ch = sock.recv(1)
                if not ch:
                    break
                line += ch
            line = line.decode('ascii').strip()
            if line != "REFERENCES 10":
                print(f"Unexpected line: {line}")
                break
            
            references = []
            for i in range(10):
                # Read REF line
                line = b''
                while not line.endswith(b'\n'):
                    ch = sock.recv(1)
                    if not ch:
                        break
                    line += ch
                line = line.decode('ascii').strip()
                parts = line.split()
                if len(parts) != 4 or parts[0] != "REF" or parts[2] != "SIZE":
                    print(f"Unexpected REF line: {line}")
                    break
                idx = int(parts[1])
                size = int(parts[3])
                # Read image data
                image_data = b''
                while len(image_data) < size:
                    chunk = sock.recv(size - len(image_data))
                    if not chunk:
                        break
                    image_data += chunk
                if len(image_data) != size:
                    print(f"Failed to read full image data for REF {idx}")
                    break
                image = parse_ppm(image_data)
                references.append(image)
            
            # Play up to 8 steps
            eliminated = False
            guessed_correctly = False
            for step in range(1, 9):  # steps 1 to 8
                # Read REVEAL line
                line = b''
                while not line.endswith(b'\n'):
                    ch = sock.recv(1)
                    if not ch:
                        break
                    line += ch
                line = line.decode('ascii').strip()
                parts = line.split()
                if len(parts) != 5 or parts[0] != "REVEAL" or parts[2] != "BLUR" or parts[4] != "SIZE":
                    print(f"Unexpected REVEAL line: {line}")
                    break
                step_num = int(parts[1])
                radius = int(parts[3])
                size = int(parts[5])
                # Read image data
                image_data = b''
                while len(image_data) < size:
                    chunk = sock.recv(size - len(image_data))
                    if not chunk:
                        break
                    image_data += chunk
                if len(image_data) != size:
                    print(f"Failed to read full image data for reveal step {step}")
                    break
                revealed_image = parse_ppm(image_data)
                
                # Read GUESS? line
                line = b''
                while not line.endswith(b'\n'):
                    ch = sock.recv(1)
                    if not ch:
                        break
                    line += ch
                line = line.decode('ascii').strip()
                if line != "GUESS?":
                    print(f"Expected GUESS? got: {line}")
                    break
                
                # Compute block size based on radius
                block_size = max(1, 2 * radius)
                
                # Compute block averages for each reference
                ref_avgs = []
                for img in references:
                    avgs = block_averages(img, block_size)
                    ref_avgs.append(avgs)
                reveal_avgs = block_averages(revealed_image, block_size)
                
                # Compute SSDs
                ssds = []
                for avgs in ref_avgs:
                    ssds.append(ssd(reveal_avgs, avgs))
                
                best_idx = ssds.index(min(ssds))
                best_ssd = ssds[best_idx]
                sorted_ssds = sorted(ssds)
                second_best_ssd = sorted_ssds[1] if len(sorted_ssds) > 1 else best_ssd
                
                # Decide whether to guess or pass
                guess = False
                if second_best_ssd == 0:
                    if best_ssd == 0:
                        guess = True
                else:
                    if best_ssd < 0.5 * second_best_ssd:
                        guess = True
                
                if guess:
                    # Send guess
                    msg = f"GUESS {best_idx}\n"
                    sock.sendall(msg.encode('ascii'))
                    # Read response
                    line = b''
                    while not line.endswith(b'\n'):
                        ch = sock.recv(1)
                        if not ch:
                            break
                        line += ch
                    line = line.decode('ascii').strip()
                    if line.startswith("CORRECT"):
                        # Correct guess, break out of step loop
                        guessed_correctly = True
                        break
                    elif line.startswith("WRONG"):
                        # Wrong guess, eliminated for this round
                        eliminated = True
                        break
                    else:
                        print(f"Unexpected guess response: {line}")
                        break
                else:
                    # Send pass
                    sock.sendall(b"PASS\n")
                    # If this is the last step, break after sending pass
                    if step == 8:
                        break
            # End of steps for this round
            # If we are eliminated or guessed correctly, we move to next round
            # If we passed all steps, we also move to next round
        # End of rounds
    finally:
        sock.close()

if __name__ == '__main__':
    main()