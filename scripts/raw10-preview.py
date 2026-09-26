#!/usr/bin/env python3
"""Side-by-side preview PNG from two raw 1080p RGGB10 CSI-2 packed captures.

Stdlib only (no numpy on the bench image). Uses the last frame of each file,
the top 8 bits of each pixel, half-resolution RGB from each 2x2 Bayer cell,
and a gamma stretch. No white balance, so expect a green tint. Also prints
per-camera stats: how many sampled bytes change between frames (a live
stream, not a stuck buffer) and the pixel range of the last frame.

Usage: raw10-preview.py cam0.raw cam1.raw out.png
"""
import statistics
import struct
import sys
import zlib

W, H, STRIDE = 1920, 1080, 2400  # 4 pixels per 5 bytes
FRAME = STRIDE * H


def high_bytes(frame, y):
    row = frame[y * STRIDE:(y + 1) * STRIDE]
    out = bytearray(W)
    for i in range(4):
        out[i::4] = row[i::5]
    return out


def preview_rows(path):
    data = open(path, 'rb').read()
    frames = [data[k * FRAME:(k + 1) * FRAME] for k in range(len(data) // FRAME)]
    diffs = [sum(a != b for a, b in zip(frames[i][::997], frames[i + 1][::997]))
             for i in range(0, len(frames) - 1, 7)]
    last = frames[-1]
    sample = [v for y in range(0, H, 37) for v in high_bytes(last, y)[::13]]
    print(f'{path}: {len(frames)} frames, sampled bytes changed {diffs}, '
          f'min {min(sample)} max {max(sample)} mean {statistics.mean(sample):.1f}')

    rows = []
    for y in range(0, H, 2):
        a, b = high_bytes(last, y), high_bytes(last, y + 1)
        px = bytearray(3 * (W // 2))
        px[0::3] = a[0::2]
        px[1::3] = bytes((g1 + g2) // 2 for g1, g2 in zip(a[1::2], b[0::2]))
        px[2::3] = b[1::2]
        rows.append(px)
    peak = max(max(r) for r in rows[::10]) or 1
    lut = bytes(min(255, int(255 * (min(v, peak) / peak) ** (1 / 2.2)))
                for v in range(256))
    return [r.translate(lut) for r in rows]


def write_png(path, width, rows):
    def chunk(tag, body):
        return (struct.pack('>I', len(body)) + tag + body
                + struct.pack('>I', zlib.crc32(tag + body)))
    ihdr = struct.pack('>IIBBBBB', width, len(rows), 8, 2, 0, 0, 0)
    raw = b''.join(b'\0' + bytes(r) for r in rows)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    left, right = preview_rows(sys.argv[1]), preview_rows(sys.argv[2])
    gap = bytes(3 * 8)
    write_png(sys.argv[3], W + 8, [l + gap + r for l, r in zip(left, right)])


if __name__ == '__main__':
    main()
