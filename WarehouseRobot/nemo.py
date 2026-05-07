# bot author: Nemotron 3 Super (nvidia/nemotron-3-super-120b-a12b via OpenRouter)
# bot author: gpt-4o-2024-08-06
import os
import sys
import socket

def main():
    bot_name = os.environ.get('BOTNAME')
    if not bot_name:
        # Misconfigured, do not attempt to connect
        return
    # Validate bot name characters (optional, but we assume correct)
    try:
        sock = socket.create_connection(('localhost', 7474))
    except Exception:
        return
    try:
        # Send bot name
        sock.sendall((bot_name + '\n').encode('ascii'))
        file = sock.makefile('r', encoding='ascii')
        while True:
            line = file.readline()
            if not line:
                break
            line = line.rstrip('\n')
            if line == 'TOURNAMENT_END':
                break
            if line.startswith('ROUND'):
                # Parse round header
                parts = line.split()
                # ROUND <n> <wm> <hm> <N>
                # We only need N
                try:
                    N = int(parts[4])
                except Exception:
                    # malformed, skip
                    continue
                items = []
                for _ in range(N):
                    it_line = file.readline()
                    if not it_line:
                        break
                    it_line = it_line.rstrip('\n')
                    # ITEM <idx> <x> <y> <weight>
                    it_parts = it_line.split()
                    if len(it_parts) != 4:
                        continue
                    idx = int(it_parts[1])
                    x = int(it_parts[2])
                    y = int(it_parts[3])
                    w = int(it_parts[4])
                    items.append({'idx': idx, 'x': x, 'y': y, 'weight': w})
                # Ensure items are in order of index
                items.sort(key=lambda it: it['idx'])
                # Build list for easier access
                it_list = [{'x': it['x'], 'y': it['y'], 'weight': it['weight']} for it in items]
                trips = plan_trips(it_list)
                # Send trips
                for trip in trips:
                    if not trip:
                        continue  # should not happen
                    sock.sendall(('TRIP ' + ' '.join(str(idx) for idx in trip) + '\n').encode('ascii'))
                sock.sendall(('END\n').encode('ascii'))
                # Read server response
                resp_line = file.readline()
                if not resp_line:
                    break
                resp_line = resp_line.rstrip('\n')
                # Expect OK or INVALID
                # Then read END_ROUND
                end_round_line = file.readline()
                if not end_round_line:
                    break
                end_round_line = end_round_line.rstrip('\n')
                # Expect END_ROUND <n>
                # Continue loop
            else:
                # Unexpected line, ignore
                continue
    finally:
        sock.close()

def plan_trips(items):
    n = len(items)
    remaining = set(range(n))
    trips = []
    while remaining:
        trip = []
        load = 0
        cur_x, cur_y = 0, 0
        while True:
            best_idx = None
            best_dist = None
            best_weight = None
            for idx in remaining:
                it = items[idx]
                dx = abs(it['x'] - cur_x)
                dy = abs(it['y'] - cur_y)
                dist = dx + dy
                if dist == 0:
                    # zero distance always reachable; choose by weight
                    cand = (0, it['weight'])
                else:
                    if load >= 100:
                        continue  # cannot travel positive distance
                    cand = (dist, it['weight'])
                if best_idx is None or cand < (best_dist, best_weight):
                    best_idx = idx
                    best_dist, best_weight = cand
            if best_idx is None:
                break
            # Add to trip
            trip.append(best_idx)
            remaining.remove(best_idx)
            it = items[best_idx]
            cur_x, cur_y = it['x'], it['y']
            load += it['weight']
        trips.append(trip)
    return trips

if __name__ == '__main__':
    main()
