#!/usr/bin/env python3
"""make-frames.py — sinh ảnh khung "pixel mềm" 9-slice cho theme Waybar pixel (waybar/theme-pixel.css).

Khung = hình chữ nhật bo góc bán kính RADIUS tính theo từng điểm ảnh 1px (bậc thang nhỏ, không khử răng cưa):
  viền ngoài tối (OUTLINE) → mép sáng trên-trái (HI) / bóng dưới-phải (SH) → nền (FILL).
Ảnh SIZE×SIZE, CSS cắt 9 mảnh bằng `border-image: url(...) SLICE stretch` với `border-width: SLICE px`
(cụm Waybar: frame*.png, cắt 7; popup: panel*.png, cắt 14). Mép ngoài khử răng cưa nhẹ (SS), viền trong sắc.
Đổi màu/bán kính ở bảng FRAMES rồi chạy lại; SLICE phải khớp theme-pixel.css.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "cursors"))
import xcursor_write as xw  # noqa: E402  (bộ ghi PNG thuần Python)

RADIUS = 6.0       # khung cụm (Waybar): bo 6, cắt 7
SLICE = 7          # px cắt mỗi cạnh (≥ bán kính + viền)
SIZE = 2 * SLICE + 1
PANEL_RADIUS = 12.0   # khung popup lớn ("panel-*"): bo 12, cắt 14
PANEL_SLICE = 14
SS = 4             # lấy mẫu 4×4 cho mép NGOÀI (khử răng cưa nhẹ = "mượt hơn xíu"); viền trong vẫn sắc


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
    # khung popup (trung tâm điều khiển, lịch, nhạc, tiện ích…): nền đậm hơn cụm, hơi trong để thấy nền mờ
    "panel":        ("#140e1a", "#56466a", "#1d1626", "#261e30"),
    "panel-card":   ("#140e1a", "#4a3c5c", "#241c2e", "#30263c"),   # thẻ/ô bên trong popup
    "panel-active": ("#3d1028", "#f08cbb", "#962f62", "#c94785"),
}
PANEL_ALPHA = {"panel": 242}     # độ đục nền panel (0..255)

# Ảnh cỡ cố định (không 9-slice) cho màn hình khoá hyprlock (hypr/hyprlock-pixel.conf):
# tên: (rộng, cao, bán kính, độ đục nền, màu như FRAMES)
FIXED = {
    "lock-card":  (460, 420, 16, 215, ("#140e1a", "#56466a", "#1d1626", "#261e30")),
    "lock-clock": (420, 150, 14, 190, ("#140e1a", "#56466a", "#1d1626", "#261e30")),
}


def inside(px, py, n, r, nh=None):
    """Điểm (px, py) (toạ độ thực) có nằm trong hình chữ nhật bo góc n×nh (mặc định vuông) bán kính r không."""
    nh = n if nh is None else nh
    qx = min(px, n - px)
    qy = min(py, nh - py)
    if qx >= r or qy >= r:
        return True
    return (r - qx) ** 2 + (r - qy) ** 2 <= r * r


def coverage(x, y, n, r, nh=None):
    """Tỉ lệ điểm ảnh (x, y) nằm trong hình (lấy mẫu SS×SS) → khử răng cưa mép ngoài."""
    hit = sum(inside(x + (i + 0.5) / SS, y + (j + 0.5) / SS, n, r, nh) for i in range(SS) for j in range(SS))
    return hit / (SS * SS)


def render(outline, hi, sh, fill, n, r, fill_alpha=255, nh=None):
    """Ảnh RGBA n×nh (nh mặc định = n)."""
    nh = n if nh is None else nh
    ins = [[inside(x + 0.5, y + 0.5, n, r, nh) for x in range(n)] for y in range(nh)]

    def inn(x, y):
        return 0 <= x < n and 0 <= y < nh and ins[y][x]

    def depth(x, y):
        """0 = điểm viền (sát ngoài), 1 = lớp thứ hai, 2 = bên trong."""
        for d in (1, 2):
            if any(not inn(x + dx, y + dy) for dx in range(-d, d + 1) for dy in range(-d, d + 1)
                   if abs(dx) + abs(dy) <= d):
                return d - 1
        return 2
    buf = bytearray(n * nh * 4)
    for y in range(nh):
        for x in range(n):
            cov = coverage(x, y, n, r, nh)
            if cov <= 0:
                continue
            d = depth(x, y) if ins[y][x] else 0
            if d == 0:
                col = (*outline[:3], round(255 * cov))
            elif d == 1:
                # mép sáng nửa trên-trái, bóng nửa dưới-phải (chia theo đường chéo phụ)
                col = hi if (x * nh + y * n) < n * nh - min(n, nh) else sh   # vuông: x + y < n - 1
            else:
                col = (*fill[:3], fill_alpha)
            buf[(y * n + x) * 4:(y * n + x) * 4 + 4] = bytes(col)
    return bytes(buf)


def main():
    for name, cols in FRAMES.items():
        panel = name.startswith("panel")
        n = 2 * PANEL_SLICE + 1 if panel else SIZE
        r = PANEL_RADIUS if panel else RADIUS
        rgba = render(*(hexc(c) for c in cols), n, r, PANEL_ALPHA.get(name, 255))
        xw._write_png(os.path.join(HERE, f"{name}.png"), n, n, rgba)
    for name, (w, h, r, a, cols) in FIXED.items():
        rgba = render(*(hexc(c) for c in cols), w, r, a, h)
        xw._write_png(os.path.join(HERE, f"{name}.png"), w, h, rgba)
    print(f"Đã sinh {len(FRAMES)} khung + {len(FIXED)} ảnh cố định vào {HERE} (cụm: bo {RADIUS} cắt {SLICE}; popup: bo {PANEL_RADIUS} cắt {PANEL_SLICE})")


if __name__ == "__main__":
    main()
