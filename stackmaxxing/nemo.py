#!/usr/bin/env python3
"""
StackMaxxing client for the polyomino stacking challenge.
Connects to localhost:7474, plays rounds by choosing placements
that minimize the maximum height in the tank.
"""

import socket

HOST = 'localhost'
PORT = 7474

class StackMaxxerBot:
    def __init__(self, name):
        self.name = name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.buffer = b''
        self.cols = 0
        self.rows = 0
        self.heights = []          # per column height (first empty y)
        self.round_num = 0

    def connect(self):
        self.sock.connect((HOST, PORT))
        self.sock.sendall(f'{self.name}_bot\n'.encode('ascii'))

    def recv_line(self):
        while b'\n' not in self.buffer:
            data = self.sock.recv(4096)
            if not data:
                return None
            self.buffer += data
        line, self.buffer = self.buffer.split(b'\n', 1)
        return line.decode('ascii').rstrip('\r\n')

    def send_response(self, rotation, column):
        msg = f'{rotation} {column}\n'
        self.sock.sendall(msg.encode('ascii'))

    @staticmethod
    def parse_cells(cell_str):
        if cell_str == 'END':
            return None
        cells = []
        for pair in cell_str.split():
            x_str, y_str = pair.split(',')
            cells.append((int(x_str), int(y_str)))
        return cells

    @staticmethod
    def normalize(cells):
        min_x = min(c[0] for c in cells)
        min_y = min(c[1] for c in cells)
        return [(c[0]-min_x, c[1]-min_y) for c in cells]

    def rotate_cells(self, cells, times):
        rot = cells
        for _ in range(times):
            rot = [(-y, x) for (x, y) in rot]
        return self.normalize(rot)

    def can_place(self, shape, column):
        """Return settle_y if placement is valid, else None."""
        max_dx = max(dx for dx, dy in shape)
        width = max_dx + 1
        if column < 0 or column + width > self.cols:
            return None
        settle_y = -10**9
        for dx, dy in shape:
            x = column + dx
            req = self.heights[x] - dy
            if req > settle_y:
                settle_y = req
        if settle_y < 0:
            return None
        for dx, dy in shape:
            y = settle_y + dy
            if y >= self.rows:
                return None
        return settle_y

    def update_heights_from_shape(self, shape, column, settle_y):
        for dx, dy in shape:
            x = column + dx
            y = settle_y + dy
            if y + 1 > self.heights[x]:
                self.heights[x] = y + 1

    def choose_move(self, shape):
        best = None
        best_max_height = self.rows
        for rot in range(4):
            rotated = self.rotate_cells(shape, rot)
            max_dx = max(dx for dx, dy in rotated)
            width = max_dx + 1
            for col in range(0, self.cols - width + 1):
                settle_y = self.can_place(rotated, col)
                if settle_y is None:
                    continue
                new_heights = self.heights[:]
                for dx, dy in rotated:
                    x = col + dx
                    y = settle_y + dy
                    if y + 1 > new_heights[x]:
                        new_heights[x] = y + 1
                max_height = max(new_heights) if new_heights else 0
                if max_height < best_max_height:
                    best_max_height = max_height
                    best = (rot, col, settle_y)
        if best is None:
            return (0, 0)
        rot, col, _ = best
        return (rot, col)

    def run(self):
        self.connect()
        while True:
            line = self.recv_line()
            if line is None:
                break
            if line.startswith('ROUND'):
                parts = line.split()
                self.round_num = int(parts[1])
                self.cols = int(parts[2])
                self.rows = int(parts[3])
                self.heights = [0] * self.cols
                continue
            if line == 'PIECE':
                cur_line = self.recv_line()
                if cur_line is None or not cur_line.startswith('CURRENT'):
                    break
                _, cur_cells = cur_line.split(' ', 1)
                shape = self.parse_cells(cur_cells)
                if shape is None:
                    break
                _ = self.recv_line()   # NEXT 1 (ignored)
                _ = self.recv_line()   # NEXT 2 (ignored)
                rot, col = self.choose_move(shape)
                self.send_response(rot, col)
                resp = self.recv_line()
                if resp is None:
                    break
                if resp.startswith('OK'):
                    _, bottom_y = resp.split()
                    settle_y = int(bottom_y)
                    rotated = self.rotate_cells(shape, rot)
                    if self.can_place(rotated, col) is not None:
                        self.update_heights_from_shape(rotated, col, settle_y)
                elif resp.startswith('ROUND_END'):
                    continue
                elif resp == 'END':
                    break
        self.sock.close()

if __name__ == '__main__':
    bot_name = 'nemo'
    bot = StackMaxxerBot(bot_name)
    bot.run()