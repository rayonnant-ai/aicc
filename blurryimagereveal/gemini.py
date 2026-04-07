import socket
import sys

def get_fingerprint(ppm_bytes):
    """
    Extracts an 8x8 spatial color average fingerprint from ASCII PPM data.
    Uses list slicing and sum() heavily to stay extremely fast in CPython.
    """
    # Split the raw byte string by whitespace
    tokens = ppm_bytes.split()
    
    # Skip the standard header: 'P3', width, height, '255'
    # Tokens[4:] starts the actual R G B sequence
    pixels = [int(p) for p in tokens[4:]]
    
    fingerprint = []
    
    # 512x512 image divided into an 8x8 grid of 64x64 blocks
    for block_row in range(8):
        for block_col in range(8):
            r_sum, g_sum, b_sum = 0, 0, 0
            
            # Iterate over the 64 pixel rows in this block
            for r in range(block_row * 64, (block_row + 1) * 64):
                # Calculate start and end indices in the flat 1D array
                start_idx = (r * 512 + block_col * 64) * 3
                end_idx = start_idx + 192 # 64 pixels * 3 channels = 192 values
                
                # Extract the row chunk for this block
                chunk = pixels[start_idx:end_idx]
                
                # sum(chunk[start::step]) is highly optimized in Python
                r_sum += sum(chunk[0::3])
                g_sum += sum(chunk[1::3])
                b_sum += sum(chunk[2::3])
                
            # Average the sums (64x64 = 4096 pixels per block)
            fingerprint.extend([r_sum / 4096.0, g_sum / 4096.0, b_sum / 4096.0])
            
    return fingerprint

def distance(fp1, fp2):
    """Calculates Mean Squared Error between two fingerprints."""
    return sum((a - b)**2 for a, b in zip(fp1, fp2))

def main():
    host = 'localhost'
    port = 7474
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        # Use makefile for robust buffered reading of both text lines and exact byte chunks
        f = sock.makefile('rwb')
    except ConnectionRefusedError:
        print(f"Error: Could not connect to the server at {host}:{port}")
        return

    # 1. Registration
    f.write(b'gemini_bot\n')
    f.flush()
    print("Connected and registered.")
    
    reference_fps = {}
    
    def get_line():
        """Helper to read the next non-empty line as a string."""
        while True:
            line = f.readline()
            if not line:
                return ""
            line = line.strip()
            if line:
                return line.decode('ascii')

    # 2. Main Game Loop
    while True:
        line = get_line()
        if not line:
            break
            
        if line.startswith('ROUND'):
            print(f"\n{'='*30}\n{line}\n{'='*30}")
            reference_fps.clear()
            
        elif line.startswith('REFERENCES'):
            parts = line.split()
            num_refs = int(parts[1])
            print(f"Downloading {num_refs} reference images...")
            
            for _ in range(num_refs):
                ref_line = get_line()
                parts = ref_line.split()
                idx = int(parts[1])
                size = int(parts[3])
                
                # Read exact bytes specified by server
                ppm_data = f.read(size)
                reference_fps[idx] = get_fingerprint(ppm_data)
                
        elif line.startswith('REVEAL'):
            parts = line.split()
            step = int(parts[1])
            blur = int(parts[3])
            size = int(parts[5])
            
            ppm_data = f.read(size)
            mystery_fp = get_fingerprint(ppm_data)
            
            prompt = get_line()
            if prompt == 'GUESS?':
                best_idx = -1
                best_dist = float('inf')
                second_dist = float('inf')
                
                # Compare the mystery image to our 10 references
                for idx, fp in reference_fps.items():
                    dist = distance(mystery_fp, fp)
                    if dist < best_dist:
                        second_dist = best_dist
                        best_dist = dist
                        best_idx = idx
                    elif dist < second_dist:
                        second_dist = dist
                        
                # Confidence check: Lower ratio means higher confidence
                ratio = best_dist / second_dist if second_dist > 0 else 0
                
                # Strategy: 
                # If the distance to the best match is less than 70% of the distance to the second best,
                # we are highly confident and guess early. If the blur is <= 16, it's safe to guess regardless.
                if ratio < 0.70 or blur <= 16:
                    cmd = f"GUESS {best_idx}\n"
                    f.write(cmd.encode('ascii'))
                    f.flush()
                    print(f"Step {step} (Blur {blur:2}): Guessed Ref {best_idx} | Confidence Ratio: {ratio:.3f}")
                else:
                    f.write(b"PASS\n")
                    f.flush()
                    print(f"Step {step} (Blur {blur:2}): Passed       | Confidence Ratio: {ratio:.3f}")
                    
        elif line.startswith('CORRECT'):
            print(f">>> SUCCESS: {line}")
        elif line.startswith('WRONG'):
            print(f">>> ELIMINATED: {line}")

if __name__ == "__main__":
    main()