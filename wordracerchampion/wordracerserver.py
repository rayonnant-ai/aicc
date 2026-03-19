import asyncio
import random
import string
import time

class TournamentServer:
    def __init__(self, host='127.0.0.1', port=7474, dict_path='dictionary.txt', lobby_time=30, round_time=10):
        self.host = host
        self.port = port
        self.lobby_time = lobby_time
        self.round_time = round_time # Now 10 seconds
        self.dictionary = self._load_dictionary(dict_path)
        
        self.clients = {}  
        self.claimed_words = set()
        self.grid = ""
        self.game_phase = "LOBBY"

    def _load_dictionary(self, path):
        print(f"[*] Loading dictionary: {path}...")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return set(word.strip().lower() for word in f if len(word.strip()) >= 3)
        except FileNotFoundError:
            print(f"[!] Warning: '{path}' not found.")
            return set()

    def _generate_grid(self):
        """Generates a random 225-character grid (15x15)."""
        vowels = "AEIOU" * 30
        consonants = "BCDFGHJKLMNPQRSTVWXYZ" * 20
        letters = vowels + consonants
        return ''.join(random.choices(letters, k=225))

    def _is_valid_on_grid(self, word):
        """DFS validation for a 15x15 board."""
        if not word or len(word) < 3: 
            return False
            
        grid_matrix = [list(self.grid[i:i+15].lower()) for i in range(0, 225, 15)]
        
        def dfs(r, c, index, visited):
            if index == len(word):
                return True
                
            # 8-direction adjacency
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0: continue
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < 15 and 0 <= nc < 15 and (nr, nc) not in visited:
                        if grid_matrix[nr][nc] == word[index]:
                            visited.add((nr, nc))
                            if dfs(nr, nc, index + 1, visited):
                                return True
                            visited.remove((nr, nc))
            return False

        for r in range(15):
            for c in range(15):
                if grid_matrix[r][c] == word[0]:
                    if dfs(r, c, 1, {(r, c)}):
                        return True
        return False

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        try:
            # 1. HANDSHAKE
            name_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not name_line:
                writer.close()
                return
            client_name = name_line.decode('utf-8').strip()[:30]
        except:
            writer.close()
            return

        print(f"[*] Identified: '{client_name}'")
        self.clients[writer] = {'name': client_name, 'score': 0, 'disqualified': False}

        while self.game_phase == "LOBBY":
            await asyncio.sleep(0.1)

        # 2. BROADCAST GRID
        try:
            writer.write(f"{self.grid}\n".encode('utf-8'))
            await writer.drain()
        except:
            return

        # 3. PLAYING
        try:
            while self.game_phase == "PLAYING":
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue

                if not line: break

                words = line.decode('utf-8').strip().lower().split()
                if not words: continue

                # Batch validation
                for word in words:
                    if word not in self.dictionary or not self._is_valid_on_grid(word):
                        print(f"[-] DQ: '{client_name}' submitted invalid '{word}'")
                        self.clients[writer]['disqualified'] = True
                        writer.write(b"1\n")
                        await writer.drain()
                        return # Kill connection on DQ

                # Scoring: Length - 6
                for word in words:
                    if word not in self.claimed_words:
                        self.claimed_words.add(word)
                        self.clients[writer]['score'] += (len(word) - 6)
                
                writer.write(b"0\n")
                await writer.drain()

        except:
            pass
        finally:
            writer.close()

    async def run(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        print(f"[*] 15x15 Server Live. Lobby: {self.lobby_time}s | Round: {self.round_time}s")
        
        await asyncio.sleep(self.lobby_time)
        
        if not self.clients:
            print("[!] No bots. Exiting.")
            server.close()
            return

        self.grid = self._generate_grid()
        self.game_phase = "PLAYING"
        print(f"\n--- START ({self.grid[:20]}...) ---")
        
        await asyncio.sleep(self.round_time)
        
        self.game_phase = "ENDED"
        print("\n--- END ---")
        
        # Final leaderboard logic
        results = [c for c in self.clients.values() if not c['disqualified']]
        results.sort(key=lambda x: x['score'], reverse=True)
        
        print("\nLEADERBOARD:")
        for i, r in enumerate(results):
            print(f"{i+1}. {r['name']}: {r['score']} pts")
        
        server.close()

if __name__ == "__main__":
    asyncio.run(TournamentServer().run())