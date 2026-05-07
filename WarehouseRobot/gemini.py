# bot author: Gemini Pro 3.1
# bot author: Gemini 1.5 Pro
import socket
import os
import sys
import time
import random
import math
from dataclasses import dataclass

@dataclass
class Item:
    id: int
    x: int
    y: int
    w: int

def trip_time(trip: list[int], items: dict[int, Item]) -> float:
    """
    Computes the total time for a trip given a list of item indices.
    Returns float('inf') if the trip violates the capacity constraint.
    """
    t = 0.0
    load = 0
    cx, cy = 0, 0

    for idx in trip:
        item = items[idx]
        ix, iy, iw = item.x, item.y, item.w
        dist = abs(cx - ix) + abs(cy - iy)
        
        if dist > 0:
            if load >= 100:
                return float('inf')
            speed = 10 - (load // 10)
            if speed <= 0: 
                return float('inf')
            t += dist / speed
            
        load += iw
        cx, cy = ix, iy

    # Return to depot
    dist = abs(cx - 0) + abs(cy - 0)
    if dist > 0:
        if load >= 100:
            return float('inf')
        speed = 10 - (load // 10)
        if speed <= 0: 
            return float('inf')
        t += dist / speed
        
    return t

def reinsert_greedily(trips: list[list[int]], items_to_insert: list[int], items: dict[int, Item]) -> list[list[int]]:
    """
    Takes a set of trips and sequentially inserts items greedily into the position 
    that yields the lowest increase in total time.
    """
    trip_times = [trip_time(t, items) for t in trips]
    
    for item_id in items_to_insert:
        best_delta = float('inf')
        best_trip_idx = -1
        best_insert_idx = -1
        
        # Try inserting into all possible positions of all existing trips
        for t_idx, t in enumerate(trips):
            curr_time = trip_times[t_idx]
            # Try every insertion index in the current trip
            for i in range(len(t) + 1):
                t.insert(i, item_id)
                new_time = trip_time(t, items)
                t.pop(i)
                
                delta = new_time - curr_time
                if delta < best_delta:
                    best_delta = delta
                    best_trip_idx = t_idx
                    best_insert_idx = i
                    
        # Consider making a brand new trip just for this item
        new_trip_time = trip_time([item_id], items)
        if new_trip_time < best_delta:
            best_delta = new_trip_time
            best_trip_idx = len(trips)
            best_insert_idx = 0
            
        if best_trip_idx == len(trips):
            trips.append([item_id])
            trip_times.append(new_trip_time)
        else:
            trips[best_trip_idx].insert(best_insert_idx, item_id)
            trip_times[best_trip_idx] += best_delta
            
    return trips

def solve_round(items: dict[int, Item], f):
    """
    Finds a near-optimal set of trips for the given items within the time budget.
    """
    # 30 seconds max. We use 28.5s to ensure a safe buffer for computation and network overhead.
    start_time = time.time()
    time_limit = 28.5 
    
    # Construct Initial Solution: Farthest Insertion
    # Farthest items constrain the routing more, closer items get picked up on the return.
    sorted_items = sorted(items.values(), key=lambda i: abs(i.x) + abs(i.y), reverse=True)
    
    current_trips = []
    for item in sorted_items:
        current_trips = reinsert_greedily(current_trips, [item.id], items)
        
    best_trips = [list(t) for t in current_trips]
    best_score = sum(trip_time(t, items) for t in best_trips)
    
    curr_trips = [list(t) for t in best_trips]
    curr_score = best_score
    
    num_items = len(items)
    
    # Large Neighborhood Search (LNS) combined with Simulated Annealing
    while time.time() - start_time < time_limit:
        new_trips = [list(t) for t in curr_trips]
        
        # Destruction phase: remove a random subset of items
        # Remove between 1 and min(20, 25% of all items)
        max_remove = min(max(1, num_items // 4), 20)
        k = random.randint(1, min(max_remove, num_items))
        
        removed_items = random.sample(list(items.keys()), k)
        removed_set = set(removed_items)
        
        # Clean trips by dropping removed items and empty trips
        cleaned_trips = []
        for t in new_trips:
            filtered_t = [x for x in t if x not in removed_set]
            if filtered_t:
                cleaned_trips.append(filtered_t)
                
        # Shuffle removed items to encourage different reconstruction paths
        random.shuffle(removed_items)
        
        # Reconstruction phase
        cleaned_trips = reinsert_greedily(cleaned_trips, removed_items, items)
        new_score = sum(trip_time(t, items) for t in cleaned_trips)
        
        # Evaluate new configuration
        if new_score < best_score:
            best_score = new_score
            best_trips = [list(t) for t in cleaned_trips]
            curr_trips = [list(t) for t in cleaned_trips]
            curr_score = new_score
        else:
            # Simulated Annealing acceptance for escaping local minima
            elapsed = time.time() - start_time
            progress = elapsed / time_limit
            # Temperature decays linearly over time
            temp = 2.0 * (1.0 - progress)
            if temp > 0.0001:
                diff = new_score - curr_score
                # diff is always >= 0 here. Accept slightly worse solutions with small probability.
                if random.random() < math.exp(-diff / temp):
                    curr_trips = cleaned_trips
                    curr_score = new_score

    # Send submission
    for t in best_trips:
        # Items are joined by spaces. Decimal digits only, no leading zeros logic needed 
        # (Python str() automatically formats without leading zeros)
        f.write(f"TRIP {' '.join(map(str, t))}\n")
    
    f.write("END\n")
    f.flush()

def main():
    botname = os.environ.get('BOTNAME', '').strip()
    if not botname:
        sys.exit(1)
        
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(('localhost', 7474))
    except ConnectionRefusedError:
        sys.exit(1)
        
    f = s.makefile('rw', encoding='utf-8')
    
    # Send bot identification
    f.write(f"{botname}\n")
    f.flush()
    
    while True:
        line = f.readline()
        if not line:
            break
            
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('ROUND'):
            parts = line.split()
            n = int(parts[1])
            wm = int(parts[2])
            hm = int(parts[3])
            N = int(parts[4])
            
            items = {}
            for _ in range(N):
                iline = f.readline().strip()
                iparts = iline.split()
                idx = int(iparts[1])
                x = int(iparts[2])
                y = int(iparts[3])
                w = int(iparts[4])
                items[idx] = Item(idx, x, y, w)
                
            solve_round(items, f)
            
        elif line == 'TOURNAMENT_END':
            break
            
        # Ignore OK <time> <trips>, INVALID <reason>, and END_ROUND <n>. 
        # The while loop will seamlessly wait for the next ROUND command.

if __name__ == '__main__':
    main()