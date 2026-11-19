#!/usr/bin/env python3
"""make-frames.py — sinh ảnh khung "pixel mềm" 9-slice cho theme Waybar pixel (waybar/theme-pixel.css).

Khung = hình chữ nhật bo góc bán kính RADIUS tính theo từng điểm ảnh 1px (bậc thang nhỏ, không khử răng cưa):
  viền ngoài tối (OUTLINE) → mép sáng trên-trái (HI) / bóng dưới-phải (SH) → nền (FILL).
Ảnh SIZE×SIZE, CSS cắt 9 mảnh bằng `border-image: url(...) SLICE stretch` với `border-width: SLICE px`.
Đổi màu/bán kính ở bảng FRAMES rồi chạy lại; SLICE phải khớp theme-pixel.css.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "cursors"))
import xcursor_write as xw  # noqa: E402  (bộ ghi PNG thuần Python)

RADIUS = 5.0
SLICE = 6          # px cắt mỗi cạnh (≥ bán kính + viền)
SIZE = 2 * SLICE + 1


def hexc(h, a=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


# tên: (viền ngoài, mép sáng, bóng, nền)
FRAMES = {
    "frame":        ("#140e1a", "#5a4a6b", "#2a2034", "#3a2f46"),   # cụm thường
    "frame-hover":  ("#140e1a", "#7a6890", "#33283f", "#4a3c59"),   # rê chuột
    "frame-active": ("#3d1028", "#f08cbb", "#962f62", "#c94785"),   # đang chọn / khối Kafka
    "frame-dark":   ("#140e1a", "#3f3350", "#1f1827", "#2a2134"),   # ô chìm (tooltip)
    "frame-crit":   ("#3d0f1a", "#ff9aae", "#a8344c", "#e0506e"),
}


def inside(x, y, n, r):
    """Tâm điểm ảnh (x+.5, y+.5) có nằm trong hình chữ nhật bo góc n×n bán kính r không."""
    cx, cy = x + 0.5, y + 0.5
    qx = min(cx, n - cx)
    qy = min(cy, n - cy)
    if qx >= r or qy >= r:
        return True
    return (r - qx) ** 2 + (r - qy) ** 2 <= r * r


def render(outline, hi, sh, fill):
    n = SIZE
    ins = [[inside(x, y, n, RADIUS) for x in range(n)] for y in range(n)]

    def inn(x, y):
        return 0 <= x < n and 0 <= y < n and ins[y][x]

    def depth(x, y):
        """0 = điểm viền (sát ngoài), 1 = lớp thứ hai, 2 = bên trong."""
        for d in (1, 2):
            if any(not inn(x + dx, y + dy) for dx in range(-d, d + 1) for dy in range(-d, d + 1)
                   if abs(dx) + abs(dy) <= d):
                return d - 1
        return 2
    buf = bytearray(n * n * 4)
    for y in range(n):
        for x in range(n):
            if not ins[y][x]:
                continue
            d = depth(x, y)
            if d == 0:
                col = outline
            elif d == 1:
                # mép sáng phía trên/trái, bóng phía dưới/phải (theo nửa nào gần hơn)
                col = hi if (y < n / 2 and y <= x + 1 and y <= n - x) or (x < n / 2 and x < y) else sh
                if y >= n / 2 and x >= n / 2:
                    col = sh
            else:
                col = fill
            buf[(y * n + x) * 4:(y * n + x) * 4 + 4] = bytes(col)
    return n, bytes(buf)


def main():
    for name, cols in FRAMES.items():
        n, rgba = render(*(hexc(c) for c in cols))
        xw._write_png(os.path.join(HERE, f"{name}.png"), n, n, rgba)
    print(f"Đã sinh {len(FRAMES)} khung {SIZE}x{SIZE} (bán kính {RADIUS}, cắt {SLICE}) vào {HERE}")


if __name__ == "__main__":
    main()
