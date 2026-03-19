import random
import string
import urllib.request

def build_benchmark_dictionary(filename="dictionary.txt", target_size=1000000):
    words = set()
    
    # 1. Download real words to ensure the bots can find actual matches
    print("Downloading real English words from dwyl/english-words...")
    url = "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt"
    try:
        response = urllib.request.urlopen(url)
        for line in response:
            word = line.decode('utf-8').strip().lower()
            if len(word) >= 3: # Enforce 3-letter minimum
                words.add(word)
        print(f"[+] Loaded {len(words)} real words.")
    except Exception as e:
        print(f"[!] Could not download real words: {e}")
        print("Continuing with purely synthetic words...")
        
    # 2. Pad with synthetic words to hit the 1,000,000 benchmark limit
    print(f"Padding dataset to {target_size} total words to stress-test memory...")
    while len(words) < target_size:
        length = random.randint(4, 9)
        synthetic_word = ''.join(random.choices(string.ascii_lowercase, k=length))
        words.add(synthetic_word)
        
    # 3. Shuffle and save to prevent alphabetical optimization biases
    print(f"Shuffling and writing {len(words)} words to {filename}...")
    word_list = list(words)
    random.shuffle(word_list)
    
    with open(filename, "w", encoding="utf-8") as f:
        for word in word_list:
            f.write(word + "\n")
            
    print("[+] Benchmark dictionary complete.")

if __name__ == "__main__":
    build_benchmark_dictionary()