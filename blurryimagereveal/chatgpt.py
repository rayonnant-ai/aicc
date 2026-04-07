#!/usr/bin/env python3
import math
import socket
import sys
from typing import List, Tuple

HOST = 'localhost'
PORT = 7474
BOT_NAME = 'gpt-5.4_bot'
BLUR_POINTS = {64: 100, 32: 60, 16: 30, 8: 15, 4: 8, 2: 4, 1: 2, 0: 1}


class Reader:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = bytearray()

    def _fill(self, n: int = 1) -> None:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError('connection closed')
            self.buf.extend(chunk)

    def readline(self) -> str:
        while True:
            idx = self.buf.find(b'\n')
            if idx != -1:
                line = self.buf[:idx + 1]
                del self.buf[:idx + 1]
                return line.decode('ascii')
            self._fill(len(self.buf) + 1)

    def readexact(self, n: int) -> bytes:
        self._fill(n)
        data = bytes(self.buf[:n])
        del self.buf[:n]
        return data


def parse_ppm(ppm: bytes) -> List[int]:
    parts = ppm.split()
    if not parts or parts[0] != b'P3':
        raise ValueError('not a P3 ppm')
    width = int(parts[1])
    height = int(parts[2])
    maxv = int(parts[3])
    if width != 512 or height != 512 or maxv != 255:
        raise ValueError(f'unexpected ppm header: {width}x{height} max {maxv}')
    vals = list(map(int, parts[4:]))
    if len(vals) != width * height * 3:
        raise ValueError('pixel count mismatch')
    return vals


FEATURE_SPECS: List[Tuple[int, int]] = [
    (8, 8), (16, 16), (32, 32),
    (12, 9), (24, 18),
]


def image_features(rgb: List[int]) -> List[float]:
    width = 512
    height = 512
    gray = [0.0] * (width * height)
    sat_sum = 0.0
    idx = 0
    for i in range(width * height):
        r = rgb[idx]
        g = rgb[idx + 1]
        b = rgb[idx + 2]
        idx += 3
        gray[i] = 0.299 * r + 0.587 * g + 0.114 * b
        mx = max(r, g, b)
        mn = min(r, g, b)
        sat_sum += (mx - mn)

    feats: List[float] = []
    total_pixels = width * height

    mean = sum(gray) / total_pixels
    var = 0.0
    edge = 0.0
    for y in range(height):
        row = y * width
        for x in range(width):
            v = gray[row + x]
            d = v - mean
            var += d * d
            if x + 1 < width:
                edge += abs(v - gray[row + x + 1])
            if y + 1 < height:
                edge += abs(v - gray[row + x + width])
    feats.extend([mean / 255.0, math.sqrt(var / total_pixels) / 255.0, edge / (total_pixels * 255.0)])
    feats.append(sat_sum / (total_pixels * 255.0))

    for gx, gy in FEATURE_SPECS:
        block = []
        for by in range(gy):
            y0 = by * height // gy
            y1 = (by + 1) * height // gy
            for bx in range(gx):
                x0 = bx * width // gx
                x1 = (bx + 1) * width // gx
                s = 0.0
                c = 0
                for y in range(y0, y1):
                    base = y * width
                    for x in range(x0, x1):
                        s += gray[base + x]
                        c += 1
                block.append((s / c) / 255.0)
        feats.extend(block)

    return feats


class RefModel:
    def __init__(self, idx: int, feats: List[float]):
        self.idx = idx
        self.feats = feats


def l2(a: List[float], b: List[float]) -> float:
    s = 0.0
    for x, y in zip(a, b):
        d = x - y
        s += d * d
    return s


def choose_action(refs: List[RefModel], reveal_rgb: List[int], blur: int) -> str:
    rf = image_features(reveal_rgb)
    scores = [(l2(rf, ref.feats), ref.idx) for ref in refs]
    scores.sort()
    best_d, best_idx = scores[0]
    second_d = scores[1][0]
    ratio = second_d / (best_d + 1e-12)
    gap = second_d - best_d

    if blur >= 32:
        confident = ratio > 1.45 and gap > 0.015
    elif blur >= 8:
        confident = ratio > 1.22 and gap > 0.008
    elif blur >= 2:
        confident = ratio > 1.10 and gap > 0.003
    else:
        confident = True

    if confident:
        return f'GUESS {best_idx}\n'
    return 'PASS\n'


def main() -> int:
    with socket.create_connection((HOST, PORT), timeout=10) as sock:
        sock.settimeout(10)
        rd = Reader(sock)
        sock.sendall((BOT_NAME + '\n').encode('ascii'))
        refs: List[RefModel] = []

        while True:
            try:
                line = rd.readline()
            except EOFError:
                break
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            if line.startswith('ROUND '):
                refs = []
            elif line.startswith('REFERENCES '):
                continue
            elif line.startswith('REF '):
                parts = line.split()
                idx = int(parts[1])
                size = int(parts[4])
                ppm = rd.readexact(size)
                feats = image_features(parse_ppm(ppm))
                refs.append(RefModel(idx, feats))
            elif line.startswith('REVEAL '):
                parts = line.split()
                blur = int(parts[3])
                size = int(parts[5])
                ppm = rd.readexact(size)
                reveal_rgb = parse_ppm(ppm)
                prompt = rd.readline().strip()
                if prompt != 'GUESS?':
                    raise ValueError(f'unexpected prompt: {prompt!r}')
                action = choose_action(refs, reveal_rgb, blur)
                sock.sendall(action.encode('ascii'))
                if action.startswith('GUESS '):
                    result = rd.readline().strip()
                    print(result, file=sys.stderr)
            else:
                print(line, file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())