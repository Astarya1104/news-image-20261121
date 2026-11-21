#!/usr/bin/env python3
"""The World in One Picture - Saturday 21 November 2026.

A deterministic program (standard library only, no network) that draws one
1024x1024 PNG front page summing up the day's world news and writes it to
/output/entry.png (or $MAKEFUN_OUTPUT_DIR/entry.png).

Design: a newspaper front page. Masthead with the date, a KPI strip, three
large illustrated lead stories, a grid of ten smaller illustrated stories,
a world map with pins, a numbered list of 28 more stories, and a date-check
footer naming Friday's news that was deliberately left out.
"""

import os
import struct
import sys
import zlib
from math import sqrt

W = 1024
H = 1024

# --- palette -------------------------------------------------------------
PAPER = (247, 243, 232)
INK = (20, 33, 61)
INK_SOFT = (52, 64, 92)
RED = (178, 28, 28)
RED_DARK = (140, 20, 20)
TEAL = (13, 92, 92)
TEAL_DARK = (8, 60, 60)
GOLD = (198, 158, 38)
CREAM = (233, 228, 214)
LIGHT_LINE = (205, 198, 180)
GREY = (96, 96, 96)
WHITE = (255, 255, 255)
SKY_NIGHT = (16, 24, 58)
SKY_DAY = (174, 214, 232)
SEA = (46, 110, 138)
LAND = (122, 168, 92)

# --- 5x7 bitmap font -----------------------------------------------------
# Each glyph is 7 rows; each row is a 5-bit integer, bit 4 = leftmost pixel.
FONT = {
    'A': (4, 10, 17, 31, 17, 17, 17),
    'B': (30, 17, 17, 30, 17, 17, 30),
    'C': (14, 17, 16, 16, 16, 17, 14),
    'D': (30, 17, 17, 17, 17, 17, 30),
    'E': (31, 16, 16, 30, 16, 16, 31),
    'F': (31, 16, 16, 30, 16, 16, 16),
    'G': (14, 17, 16, 23, 17, 17, 15),
    'H': (17, 17, 17, 31, 17, 17, 17),
    'I': (14, 4, 4, 4, 4, 4, 14),
    'J': (7, 2, 2, 2, 2, 18, 12),
    'K': (17, 18, 20, 24, 20, 18, 17),
    'L': (16, 16, 16, 16, 16, 16, 31),
    'M': (17, 27, 21, 21, 17, 17, 17),
    'N': (17, 25, 21, 19, 17, 17, 17),
    'O': (14, 17, 17, 17, 17, 17, 14),
    'P': (30, 17, 17, 30, 16, 16, 16),
    'Q': (14, 17, 17, 17, 21, 18, 13),
    'R': (30, 17, 17, 30, 20, 18, 17),
    'S': (15, 16, 16, 14, 1, 1, 30),
    'T': (31, 4, 4, 4, 4, 4, 4),
    'U': (17, 17, 17, 17, 17, 17, 14),
    'V': (17, 17, 17, 17, 17, 10, 4),
    'W': (17, 17, 17, 21, 21, 21, 10),
    'X': (17, 17, 10, 4, 10, 17, 17),
    'Y': (17, 17, 10, 4, 4, 4, 4),
    'Z': (31, 1, 2, 4, 8, 16, 31),
    '0': (14, 17, 19, 21, 25, 17, 14),
    '1': (4, 12, 4, 4, 4, 4, 14),
    '2': (14, 17, 1, 6, 8, 16, 31),
    '3': (31, 2, 4, 6, 1, 17, 14),
    '4': (2, 6, 10, 18, 31, 2, 2),
    '5': (31, 16, 30, 1, 1, 17, 14),
    '6': (14, 17, 16, 30, 17, 17, 14),
    '7': (31, 1, 2, 4, 8, 8, 8),
    '8': (14, 17, 17, 14, 17, 17, 14),
    '9': (14, 17, 17, 15, 1, 17, 14),
}


def glyph_rows(ch):
    """Return the 7 row bit-patterns for a character, defaulting to blank."""
    return FONT.get(ch, (0, 0, 0, 0, 0, 0, 0))


# --- canvas ---------------------------------------------------------------
class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)
        self.fill(bg)

    def fill(self, color):
        row = bytes(color) * self.w
        for y in range(self.h):
            o = y * self.w * 3
            self.buf[o:o + self.w * 3] = row

    def px(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = (y * self.w + x) * 3
            self.buf[o] = color[0]
            self.buf[o + 1] = color[1]
            self.buf[o + 2] = color[2]

    def rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        span = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            o = (yy * self.w + x0) * 3
            self.buf[o:o + (x1 - x0) * 3] = span

    def hline(self, x, y, w, color):
        self.rect(x, y, w, 1, color)

    def vline(self, x, y, h, color):
        self.rect(x, y, 1, h, color)

    def line(self, x0, y0, x1, y1, color):
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.px(x0, y0, color)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def circle(self, cx, cy, r, color):
        for dy in range(-r, r + 1):
            dx = int(sqrt(max(0, r * r - dy * dy)))
            self.rect(cx - dx, cy + dy, 2 * dx + 1, 1, color)

    def ellipse(self, cx, cy, rx, ry, color):
        for dy in range(-ry, ry + 1):
            t = 1.0 - (dy * dy) / float(ry * ry)
            dx = int(rx * sqrt(max(0.0, t)))
            self.rect(cx - dx, cy + dy, 2 * dx + 1, 1, color)

    def poly(self, pts, color):
        """Scanline fill of a polygon given as [(x, y), ...]."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        for y in range(max(0, min(ys)), min(self.h, max(ys) + 1)):
            xs = []
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if y0 == y1:
                    continue
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.rect(int(xs[i]), y, max(1, int(xs[i + 1]) - int(xs[i])), 1, color)

    def ring(self, cx, cy, r, color, thick=2):
        for dy in range(-r, r + 1):
            dx = int(sqrt(max(0, r * r - dy * dy)))
            dx2 = int(sqrt(max(0, (r - thick) * (r - thick) - dy * dy))) if r - thick > 0 else 0
            if dx2 > 0:
                self.rect(cx - dx, cy + dy, dx - dx2, 1, color)
                self.rect(cx + dx2, cy + dy, dx - dx2 + 1, 1, color)
            else:
                self.rect(cx - dx, cy + dy, 2 * dx + 1, 1, color)


# --- PNG encoding ---------------------------------------------------------
def _chunk(kind, data):
    out = struct.pack(">I", len(data)) + kind + data
    out += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return out


def write_png(canvas, path):
    ihdr = struct.pack(">IIBBBBB", canvas.w, canvas.h, 8, 2, 0, 0, 0)
    raw = bytearray()
    stride = canvas.w * 3
    for y in range(canvas.h):
        raw.append(0)
        raw += canvas.buf[y * stride:(y + 1) * stride]
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += _chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)



# --- font, part two: lowercase letters and punctuation --------------------
# Glyph rows are five-character strings: '#' is ink, '.' is empty.
FONT.update({
    'a': (".....", ".....", ".###.", "....#", ".####", "#...#", ".####"),
    'b': ("#....", "#....", "#.##.", "##..#", "#...#", "#...#", "####."),
    'c': (".....", ".....", ".###.", "#...#", "#....", "#...#", ".###."),
    'd': ("....#", "....#", ".##.#", "#..##", "#...#", "#...#", ".####"),
    'e': (".....", ".....", ".###.", "#...#", "#####", "#....", ".###."),
    'f': ("..##.", ".#...", ".#...", "####.", ".#...", ".#...", ".#..."),
    'g': (".....", ".....", ".####", "#...#", ".####", "....#", ".###."),
    'h': ("#....", "#....", "#.##.", "##..#", "#...#", "#...#", "#...#"),
    'i': (".....", "..#..", ".....", ".##..", "..#..", "..#..", ".###."),
    'j': (".....", "...#.", ".....", "..##.", "...#.", "...#.", ".##.."),
    'k': ("#....", "#....", "#..#.", "#.#..", "##...", "#.#..", "#..#."),
    'l': (".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    'm': (".....", ".....", "##.#.", "#.#.#", "#.#.#", "#.#.#", "#.#.#"),
    'n': (".....", ".....", "#.##.", "##..#", "#...#", "#...#", "#...#"),
    'o': (".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."),
    'p': (".....", ".....", "#.##.", "##..#", "#...#", "####.", "#...."),
    'q': (".....", ".....", ".##.#", "#..##", "#...#", ".####", "....#"),
    'r': (".....", ".....", "#.##.", "###..", "#....", "#....", "#...."),
    's': (".....", ".....", ".####", "#....", ".###.", "....#", "####."),
    't': (".#...", ".#...", "####.", ".#...", ".#...", ".#..#", "..##."),
    'u': (".....", ".....", "#...#", "#...#", "#...#", "#..##", ".##.#"),
    'v': (".....", ".....", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    'w': (".....", ".....", "#...#", "#...#", "#.#.#", "#.#.#", ".#.#."),
    'x': (".....", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#"),
    'y': (".....", ".....", "#...#", "#...#", ".####", "....#", ".###."),
    'z': (".....", ".....", "#####", "...#.", "..#..", ".#...", "#####"),
    ' ': (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    '.': (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    ',': (".....", ".....", ".....", ".....", ".##..", "..#..", ".#..."),
    ':': (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    ';': (".....", ".##..", ".##..", ".....", ".##..", "..#..", ".#..."),
    '!': ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    '?': (".###.", "#...#", "....#", "..##.", "..#..", ".....", "..#.."),
    '-': (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    '(': ("...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."),
    ')': (".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."),
    '/': ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    '%': ("##..#", "##..#", "...#.", "..#..", ".#...", "#..##", "#..##"),
    '$': ("..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."),
    '€': (".###.", "#...#", "####.", "###..", "####.", "#...#", ".###."),
    '&': (".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"),
    '*': (".....", "..#..", "#.#.#", ".###.", "#.#.#", "..#..", "....."),
    '+': (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    '=': (".....", ".....", "#####", ".....", "#####", ".....", "....."),
    '<': ("...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."),
    '>': (".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."),
    '#': (".#.#.", ".#.#.", "#####", ".#.#.", "#####", ".#.#.", ".#.#."),
    '@': (".###.", "#...#", "#.###", "#.#.#", "#.###", "#....", ".###."),
    '_': (".....", ".....", ".....", ".....", ".....", ".....", "#####"),
    '"': (".#.#.", ".#.#.", ".#.#.", ".....", ".....", ".....", "....."),
    "'": ("..#..", "..#..", ".#...", ".....", ".....", ".....", "....."),
    '°': (".##..", "#..#.", "#..#.", ".##..", ".....", ".....", "....."),
    '·': (".....", ".....", ".....", ".##..", ".##..", ".....", "....."),
    '•': (".....", "..#..", ".###.", ".###.", ".###.", "..#..", "....."),
})


def _normalise_font():
    """Turn string glyph rows into the integer rows glyph_rows expects."""
    for key in list(FONT):
        rows = FONT[key]
        if rows and isinstance(rows[0], str):
            converted = []
            for row in rows:
                value = 0
                for ch in row:
                    value = (value << 1) | (1 if ch == '#' else 0)
                converted.append(value)
            FONT[key] = tuple(converted)


_normalise_font()


# --- text rendering -------------------------------------------------------
def text_width(text, scale):
    return len(text) * 6 * scale - scale


def draw_text(cv, x, y, text, scale, color):
    """Paint text with its top-left corner at (x, y); returns end x."""
    pen = x
    for ch in text:
        for row_idx, bits in enumerate(glyph_rows(ch)):
            col = 0
            while col < 5:
                if bits & (16 >> col):
                    run_start = col
                    while col < 5 and bits & (16 >> col):
                        col += 1
                    cv.rect(pen + run_start * scale, y + row_idx * scale,
                            (col - run_start) * scale, scale, color)
                else:
                    col += 1
        pen += 6 * scale
    return pen


def draw_text_centred(cv, centre_x, y, text, scale, color):
    draw_text(cv, centre_x - text_width(text, scale) // 2, y, text, scale, color)


def wrap_text(text, scale, max_px):
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if text_width(candidate, scale) <= max_px:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_para(cv, x, y, text, scale, color, max_px, leading=None):
    if leading is None:
        leading = 9 * scale
    for line in wrap_text(text, scale, max_px):
        draw_text(cv, x, y, line, scale, color)
        y += leading
    return y


def draw_star(cv, cx, cy, r, color):
    """Four-point sparkle centred on (cx, cy)."""
    cv.poly([(cx, cy - r), (cx + r // 3, cy - r // 3), (cx + r, cy),
             (cx + r // 3, cy + r // 3), (cx, cy + r),
             (cx - r // 3, cy + r // 3), (cx - r, cy),
             (cx - r // 3, cy - r // 3)], color)


def draw_burst(cv, cx, cy, r, color):
    """Eight-spike explosion burst centred on (cx, cy)."""
    dirs = [(0, -1), (1, -1), (1, 0), (1, 1),
            (0, 1), (-1, 1), (-1, 0), (-1, -1)]
    for i, (dx, dy) in enumerate(dirs):
        length = r if i % 2 == 0 else int(r * 0.7)
        cv.line(cx, cy, cx + dx * length, cy + dy * length, color)
    cv.circle(cx, cy, max(2, r // 3), color)


# --- illustrated scenes for the three lead stories ------------------------
def scene_riyadh(cv, x, y, w, h):
    """Night skyline over Riyadh with three intercepted missiles."""
    cv.rect(x, y, w, h, SKY_NIGHT)
    for sx, sy, sr in [(12, 14, 2), (48, 8, 1), (90, 20, 2), (150, 10, 1),
                       (200, 26, 2), (240, 12, 1), (280, 22, 2), (30, 34, 1)]:
        draw_star(cv, x + sx, y + sy, sr + 1, (255, 240, 180))
    cv.circle(x + w - 42, y + 26, 13, (240, 230, 190))
    cv.circle(x + w - 48, y + 22, 11, SKY_NIGHT)
    base = y + h
    for bx, bw, bh in [(0, 42, 52), (48, 30, 74), (84, 46, 44), (136, 34, 66),
                       (176, 44, 50), (226, 30, 80), (262, 44, 58)]:
        cv.rect(x + bx, base - bh, bw, bh, (28, 38, 74))
        for wy in range(base - bh + 8, base - 6, 12):
            for wx in range(x + bx + 6, x + bx + bw - 6, 12):
                if (wx + wy) % 3 == 0:
                    cv.rect(wx, wy, 4, 5, (255, 214, 110))
    for tx in (60, 150, 235):
        cv.line(x + tx, y + 18, x + tx - 26, y + 62, (255, 140, 60))
        cv.line(x + tx - 2, y + 18, x + tx - 28, y + 62, (255, 200, 90))
        draw_burst(cv, x + tx - 30, y + 68, 9, (255, 190, 80))
        draw_burst(cv, x + tx - 30, y + 68, 4, WHITE)


def scene_mercury(cv, x, y, w, h):
    """Grey cratered Mercury with the BepiColombo craft approaching."""
    cv.rect(x, y, w, h, (8, 10, 26))
    for sx, sy in [(14, 12), (52, 30), (96, 10), (150, 22), (210, 14),
                   (262, 34), (288, 12), (40, 48), (180, 44), (120, 8)]:
        cv.rect(x + sx, y + sy, 2, 2, WHITE)
    cx, cy, r = x + 78, y + h // 2 + 18, 52
    cv.circle(cx, cy, r, (168, 164, 152))
    for ox, oy, orad, shade in [(-22, -16, 12, (140, 136, 124)),
                                (18, 8, 16, (146, 142, 130)),
                                (-6, 26, 9, (132, 128, 116)),
                                (28, -24, 8, (150, 146, 134)),
                                (-34, 14, 7, (138, 134, 122))]:
        cv.circle(cx + ox, cy + oy, orad, shade)
    cv.circle(cx - 20, cy - 18, 3, (120, 116, 106))
    cv.circle(cx + 30, cy + 28, 3, (120, 116, 106))
    px, py = x + 218, y + 42
    cv.rect(px - 26, py - 6, 20, 12, (52, 110, 180))
    cv.rect(px, py - 8, 16, 16, (220, 220, 220))
    cv.rect(px + 22, py - 6, 20, 12, (52, 110, 180))
    cv.poly([(px + 8, py + 8), (px + 2, py + 22), (px + 14, py + 22)], (255, 150, 50))
    cv.line(px - 30, py, cx + 40, cy - 30, (120, 120, 120))
    draw_text(cv, x + 12, y + 10, "8 YEARS - 10 BN KM", 2, (200, 200, 200))


def scene_cop31(cv, x, y, w, h):
    """Thermometer past 1.5C over a negotiation table in Antalya."""
    cv.rect(x, y, w, h, (186, 228, 226))
    cv.circle(x + 42, y + 28, 16, (255, 214, 110))
    for dx, dy in [(0, -24), (17, -17), (24, 0), (17, 17), (0, 24),
                   (-17, 17), (-24, 0), (-17, -17)]:
        cv.line(x + 42, y + 28, x + 42 + dx, y + 28 + dy, (255, 190, 60))
    tx = x + w - 70
    cv.rect(tx, y + 10, 24, 88, WHITE)
    cv.rect(tx + 2, y + 12, 20, 84, (220, 235, 235))
    cv.rect(tx + 2, y + 42, 20, 54, RED)
    cv.circle(tx + 12, y + 106, 16, RED)
    cv.circle(tx + 12, y + 106, 10, (255, 120, 110))
    draw_text(cv, tx - 56, y + 16, "1.5C", 2, RED)
    cv.rect(x + 14, y + 118, w - 28, 6, (120, 82, 52))
    cv.rect(x + 26, y + 124, 8, 16, (90, 60, 38))
    cv.rect(x + w - 34, y + 124, 8, 16, (90, 60, 38))
    for i, col in enumerate([(178, 28, 28), (52, 110, 180), (13, 92, 92),
                            (198, 158, 38), (90, 60, 38)]):
        fx = x + 52 + i * 38
        cv.rect(fx, y + 92, 24, 14, col)
        cv.rect(fx + 11, y + 92, 2, 26, (80, 80, 80))


# --- small icons for the ten grid stories ---------------------------------
def icon_plane(cv, x, y, s, color):
    cv.poly([(x + 2, y + 18), (x + 30, y + 18), (x + 42, y + 22),
             (x + 30, y + 26), (x + 2, y + 26)], color)
    cv.poly([(x + 16, y + 18), (x + 22, y + 4), (x + 26, y + 18)], color)
    cv.poly([(x + 16, y + 26), (x + 22, y + 40), (x + 26, y + 26)], color)
    cv.poly([(x + 4, y + 18), (x + 8, y + 8), (x + 12, y + 18)], color)


def icon_blast(cv, x, y, s, color):
    draw_burst(cv, x + 20, y + 20, 18, color)
    draw_burst(cv, x + 34, y + 8, 7, GOLD)


def icon_ship(cv, x, y, s, color):
    cv.poly([(x + 2, y + 22), (x + 42, y + 22), (x + 36, y + 36), (x + 8, y + 36)], color)
    cv.rect(x + 8, y + 10, 10, 12, RED)
    cv.rect(x + 20, y + 10, 10, 12, GOLD)
    cv.rect(x + 32, y + 10, 8, 12, TEAL)
    cv.rect(x, y + 38, 44, 2, SEA)


def icon_chip(cv, x, y, s, color):
    cv.rect(x + 10, y + 10, 24, 24, color)
    cv.rect(x + 16, y + 16, 12, 12, WHITE)
    for i in range(4):
        cv.rect(x + 12 + i * 6, y + 4, 3, 6, color)
        cv.rect(x + 12 + i * 6, y + 34, 3, 6, color)
        cv.rect(x + 4, y + 12 + i * 6, 6, 3, color)
        cv.rect(x + 34, y + 12 + i * 6, 6, 3, color)


def icon_lock(cv, x, y, s, color):
    cv.ring(x + 22, y + 14, 9, color, 4)
    cv.rect(x + 10, y + 18, 24, 18, color)
    cv.rect(x + 20, y + 24, 4, 8, WHITE)


def icon_gavel(cv, x, y, s, color):
    cv.rect(x + 6, y + 8, 22, 8, color)
    cv.line(x + 28, y + 12, x + 40, y + 30, color)
    cv.line(x + 29, y + 10, x + 41, y + 28, color)
    cv.rect(x + 4, y + 34, 36, 3, GOLD)


def icon_coin(cv, x, y, s, color):
    cv.circle(x + 22, y + 20, 16, GOLD)
    cv.circle(x + 22, y + 20, 12, (232, 196, 90))
    draw_text(cv, x + 17, y + 12, "E", 2, (120, 90, 10))


def icon_cricket(cv, x, y, s, color):
    cv.line(x + 12, y + 6, x + 30, y + 32, color)
    cv.line(x + 14, y + 6, x + 32, y + 32, color)
    cv.circle(x + 34, y + 10, 6, RED)
    cv.rect(x + 4, y + 34, 36, 3, (120, 168, 92))


def icon_trophy(cv, x, y, s, color):
    cv.poly([(x + 12, y + 4), (x + 32, y + 4), (x + 30, y + 22), (x + 14, y + 22)], GOLD)
    cv.rect(x + 8, y + 6, 5, 10, GOLD)
    cv.rect(x + 31, y + 6, 5, 10, GOLD)
    cv.rect(x + 20, y + 22, 4, 8, GOLD)
    cv.rect(x + 12, y + 30, 20, 4, GOLD)


def icon_car(cv, x, y, s, color):
    cv.poly([(x + 4, y + 18), (x + 12, y + 8), (x + 30, y + 8), (x + 40, y + 18),
             (x + 40, y + 26), (x + 4, y + 26)], RED)
    cv.circle(x + 13, y + 28, 6, INK)
    cv.circle(x + 31, y + 28, 6, INK)
    cv.circle(x + 13, y + 28, 2, WHITE)
    cv.circle(x + 31, y + 28, 2, WHITE)
    draw_text(cv, x + 14, y + 12, "F1", 2, WHITE)


# --- world map ------------------------------------------------------------
MAP_PINS = [
    (208, 68, "1"), (180, 48, "3"), (170, 16, "4"), (190, 24, "5"),
    (196, 88, "6"), (252, 38, "7"), (58, 42, "8"), (148, 12, "9"),
    (138, 34, "10"), (282, 158, "11"), (158, 44, "12"), (36, 52, "13"),
]


def draw_map(cv, x, y, w, h):
    cv.rect(x, y, w, h, (24, 58, 96))
    cv.poly([(x + 20, y + 30), (x + 60, y + 18), (x + 95, y + 28), (x + 105, y + 45),
             (x + 85, y + 60), (x + 60, y + 70), (x + 35, y + 60), (x + 15, y + 45)], LAND)
    cv.poly([(x + 75, y + 95), (x + 105, y + 90), (x + 115, y + 115), (x + 100, y + 150),
             (x + 85, y + 135), (x + 72, y + 110)], LAND)
    cv.poly([(x + 140, y + 25), (x + 165, y + 15), (x + 185, y + 25), (x + 180, y + 45),
             (x + 160, y + 50), (x + 145, y + 40)], LAND)
    cv.poly([(x + 140, y + 60), (x + 175, y + 55), (x + 190, y + 75), (x + 180, y + 110),
             (x + 160, y + 125), (x + 145, y + 95), (x + 138, y + 75)], LAND)
    cv.poly([(x + 190, y + 20), (x + 250, y + 10), (x + 290, y + 25), (x + 285, y + 55),
             (x + 250, y + 70), (x + 220, y + 60), (x + 195, y + 45)], LAND)
    cv.poly([(x + 255, y + 130), (x + 275, y + 125), (x + 280, y + 145), (x + 260, y + 150)], LAND)
    for px, py, num in MAP_PINS:
        cv.circle(x + px, y + py, 6, RED)
        tx = x + px - 2 if len(num) == 1 else x + px - 5
        draw_text(cv, tx, y + py - 4, num, 1, WHITE)
    draw_text(cv, x + 8, y + h - 16, "PINS 1-13 MARK THE DRAWN STORIES.", 1, (200, 210, 230))
    draw_text(cv, x + 8, y + h - 7, "NO. 2 IS IN SPACE: MERCURY.", 1, (200, 210, 230))


# --- content: 41 stories, all dated Saturday 21 November 2026 --------------
LEADS = [
    ("ANTALYA, TURKIYE - CLIMATE - REUTERS, AP",
     "COP31 runs into overtime with no deal",
     "Talks pass the deadline; the draft drops fossil-fuel language. "
     "A third draft is due Saturday.",
     scene_cop31),
    ("RIYADH, SAUDI ARABIA - CONFLICT - REPORTS",
     "Three missiles downed over Riyadh",
     "Air defences destroy three Houthi missiles fired at the capital "
     "early on Saturday.",
     scene_riyadh),
    ("MERCURY - SPACE - ESA",
     "BepiColombo reaches Mercury after eight years",
     "The ESA-JAXA craft is caught by Mercury's gravity after an "
     "eight-year, 10-billion-km voyage.",
     scene_mercury),
]

GRID = [
    ("WARSAW, POLAND - NATO - AP",
     "Rutte in Warsaw as Poland seeks more support",
     "NATO chief visits after Friday's missile landings.",
     icon_plane),
    ("KRYVYI RIH, UKRAINE - WAR - SAT",
     "Overnight strike kills 2, injures 42",
     "Four children among the hurt, officials say.",
     icon_blast),
    ("HODEIDAH, YEMEN - AID - UN, AP",
     "UN warns port strikes threaten aid lifeline",
     "Civilians told to leave the port area.",
     icon_ship),
    ("BEIJING - TECH - REPORTS",
     "US clears ~880,000 AI chips for China",
     "Sale approved over six months, reports say.",
     icon_chip),
    ("NEW YORK - CYBER - REPORTS",
     "Banks hit in cyber attack on outside vendors",
     "Names and emails exposed; payments safe.",
     icon_lock),
    ("COPENHAGEN - SECURITY - REPORTS",
     "Denmark charges two over Russian murder plot",
     "Two Danes accused; Moscow denies the plot.",
     icon_gavel),
    ("BRUSSELS - EUROPE - EU",
     "EU pays out nearly €7.9bn to Ukraine",
     "Largest single payment under the facility.",
     icon_coin),
    ("WELLINGTON - CRICKET - SCORECARD",
     "Rahul's 100 takes India to 239 for 1",
     "NZ made 368; Nicholls 175 not out.",
     icon_cricket),
    ("TURIN - TENNIS - ATP",
     "Medvedev meets Zverev in tonight's semi",
     "Medvedev beat Tiafoe on Friday to set it up.",
     icon_trophy),
    ("LAS VEGAS - FORMULA 1 - F1",
     "Las Vegas GP qualifying today",
     "Grid decided under lights; race on Sunday.",
     icon_car),
]

MORE = [
    "BRASILIA - Brazil shields Indigenous land",
    "MADRID - General strike grips Spain",
    "ROME - Marchers protest Meloni budget",
    "LOS ANGELES - Jury convicts Palisades fire starter",
    "HEALTH - Pill hailed for pancreatic cancer",
    "WASHINGTON - Trump: no Iran call until 2027",
    "KYIV - Ukraine hits three missile launchers",
    "BRUSSELS - EU, Canada deepen mineral ties",
    "NEW DELHI - US panel faults India voter rolls",
    "OTTAWA - US sanctions crime gangs in Canada",
    "GAZA - Children appeal on Children's Day",
    "KYIV - Ukraine to send food aid to 9 nations",
    "BERN - Swiss hail ICJ Myanmar ruling",
    "LONDON - Ruling may test Israel at the ICJ",
    "PARIS - Fourth weekend of cost protests",
    "ATLANTIC - Storm Xavier gales narrow",
    "LOS ANGELES - Hyundai shows 2027 Elantra",
    "GAZA - Four nations demand aid access",
    "JERUSALEM - Herzog taps Eisenkot for PM",
    "WASHINGTON - $12bn Venezuela oil report",
    "MELBOURNE - Australia host England in T20",
    "WOLVERHAMPTON - Darts quarters live today",
    "WASHINGTON - Pentagon: Iran cost $48.3bn",
    "UN - Only 44 of 96 climate signs improve",
    "TALLINN - Estonia shuts Russia crossings",
    "BUDAPEST - Hungary lifts EU accession block",
    "MURMANSK - Drones hit Kola oil terminal",
    "ANKARA - Turkey welcomes ICJ ruling",
]

KPIS = [
    ("3", "MISSILES DOWNED OVER RIYADH"),
    ("92,934", "AT COP31 - LARGEST EVER"),
    ("42", "HURT IN THE KRYVYI RIH STRIKE"),
    ("880,000", "AI CHIPS CLEARED FOR CHINA"),
    ("€7.9bn", "EU PAYMENT TO UKRAINE"),
]

DATE_CHECK = (
    "DATE CHECK - LEFT OUT AS FRIDAY 20 NOVEMBER NEWS, NOT SATURDAY'S: "
    "RUSSIAN MISSILES LAND IN POLAND - KYIV'S BRIDGES HIT - UK-EU SUMMIT "
    "DEALS - TRUMP-XI-PUTIN SHENZHEN SUMMIT - ICJ MYANMAR GENOCIDE RULING - "
    "MONGOLIA'S PRESIDENT QUITS - LA QUAKE 4.2 - US-CHINA MILITARY-AI PACT - "
    "PETE ROSE PARDON - WALL STREET'S AI SELL-OFF - PERU QUAKE 6.8 - "
    "CYCLONE AKVAN LANDFALL"
)


# --- layout -----------------------------------------------------------------
def draw_masthead(cv):
    draw_text(cv, 16, 10, "THE WORLD IN ONE PICTURE", 2, RED)
    right = "41 STORIES - 6 REGIONS - EVERY ONE DATED"
    draw_text(cv, 1008 - text_width(right, 2), 10, right, 2, INK_SOFT)
    draw_text_centred(cv, 512, 32, "Saturday 21 November 2026", 6, INK)
    draw_text_centred(cv, 512, 82,
                      "COP31 in overtime - Missiles over Riyadh - "
                      "BepiColombo reaches Mercury",
                      2, INK_SOFT)
    cv.rect(16, 104, 992, 2, INK)


def draw_kpi_strip(cv):
    box_w = 992 // 5
    for i, (num, label) in enumerate(KPIS):
        x0 = 16 + i * box_w
        if i:
            cv.rect(x0, 118, 1, 40, LIGHT_LINE)
        draw_text_centred(cv, x0 + box_w // 2, 116, num, 4, INK)
        draw_text_centred(cv, x0 + box_w // 2, 148, label, 1, RED)
    cv.rect(16, 164, 992, 2, INK)


def draw_leads(cv):
    col_w = (1024 - 32 - 24) // 3
    for i, (tag, headline, summary, scene) in enumerate(LEADS):
        x0 = 16 + i * (col_w + 12)
        scene(cv, x0, 172, col_w, 140)
        cv.rect(x0, 312, col_w, 18, RED)
        draw_text(cv, x0 + 6, 316, tag, 1, WHITE)
        y = draw_para(cv, x0, 336, headline, 2, INK, col_w, leading=18)
        draw_para(cv, x0, y + 4, summary, 2, INK_SOFT, col_w, leading=17)


def draw_grid(cv):
    cell_w = (1024 - 32 - 40) // 5
    for i, (tag, headline, summary, icon) in enumerate(GRID):
        row, col = divmod(i, 5)
        x0 = 16 + col * (cell_w + 10)
        y0 = 452 + row * 138
        icon(cv, x0 + 6, y0 + 4, 44, INK)
        draw_text(cv, x0 + 6, y0 + 50, tag, 1, RED)
        y = draw_para(cv, x0 + 6, y0 + 64, headline, 2, INK, cell_w - 12,
                      leading=16)
        draw_para(cv, x0 + 6, y + 2, summary, 1, INK_SOFT, cell_w - 12,
                  leading=9)
        if col < 4:
            cv.rect(x0 + cell_w + 4, y0 + 6, 1, 126, LIGHT_LINE)
        if row == 0:
            cv.rect(x0, y0 + 134, cell_w, 1, LIGHT_LINE)


def draw_map_and_list(cv):
    draw_text(cv, 16, 734, "WHERE IT HAPPENED", 2, INK)
    draw_map(cv, 16, 754, 300, 204)
    draw_text(cv, 330, 734, "ALSO ON SATURDAY 21 NOVEMBER - 28 MORE STORIES",
              2, INK)
    for i, item in enumerate(MORE):
        col = 0 if i < 14 else 1
        row = i if i < 14 else i - 14
        x0 = 330 + col * 338
        y0 = 758 + row * 15
        draw_text(cv, x0, y0, "%d %s" % (14 + i, item), 1, INK_SOFT)


def draw_footer(cv):
    cv.rect(16, 966, 992, 2, RED)
    cv.rect(16, 1004, 992, 2, RED)
    cv.rect(16, 966, 2, 40, RED)
    cv.rect(1006, 966, 2, 40, RED)
    y = 970
    for line in wrap_text(DATE_CHECK, 1, 976):
        draw_text(cv, 24, y, line, 1, RED_DARK)
        y += 9
    draw_text_centred(cv, 512, 1010,
                      "EVERY STORY HERE HAPPENED, OR WAS FIRST REPORTED, ON "
                      "SATURDAY 21 NOVEMBER 2026 IN AT LEAST ONE TIME ZONE.",
                      1, GREY)


def render():
    cv = Canvas(W, H, PAPER)
    draw_masthead(cv)
    draw_kpi_strip(cv)
    draw_leads(cv)
    draw_grid(cv)
    draw_map_and_list(cv)
    draw_footer(cv)
    return cv


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    size = write_png(render(), path)
    print("wrote %s (%d bytes)" % (path, size))
    if size > 1048576:
        print("ERROR: over the 1 MiB limit", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
