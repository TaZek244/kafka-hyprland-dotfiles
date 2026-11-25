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

RADIUS = 6.0  # khung cụm (Waybar): bo 6, cắt 7
SLICE = 7  # px cắt mỗi cạnh (≥ bán kính + viền)
SIZE = 2 * SLICE + 1
PANEL_RADIUS = 12.0  # khung popup lớn ("panel-*"): bo 12, cắt 14
PANEL_SLICE = 14
SS = 4  # lấy mẫu 4×4 cho mép NGOÀI (khử răng cưa nhẹ = "mượt hơn xíu"); viền trong vẫn sắc


def hexc(h, a=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


# tên: (viền ngoài, mép sáng, bóng, nền)
FRAMES = {
    "frame": ("#140e1a", "#5a4a6b", "#2a2034", "#3a2f46"),  # cụm thường
    "frame-hover": ("#140e1a", "#7a6890", "#33283f", "#4a3c59"),  # rê chuột
    "frame-active": ("#3d1028", "#f08cbb", "#962f62", "#c94785"),  # đang chọn / khối Kafka
    "frame-dark": ("#140e1a", "#3f3350", "#1f1827", "#2a2134"),  # ô chìm (tooltip)
    "frame-crit": ("#3d0f1a", "#ff9aae", "#a8344c", "#e0506e"),
    # khung popup (trung tâm điều khiển, lịch, nhạc, tiện ích…): nền đậm hơn cụm, hơi trong để thấy nền mờ
    "panel": ("#140e1a", "#56466a", "#1d1626", "#261e30"),
    "panel-card": ("#140e1a", "#4a3c5c", "#241c2e", "#30263c"),  # thẻ/ô bên trong popup
    "panel-active": ("#3d1028", "#f08cbb", "#962f62", "#c94785"),
}
PANEL_ALPHA = {"panel": 242}  # độ đục nền panel (0..255)

# Ảnh cỡ cố định (không 9-slice) cho màn hình khoá hyprlock (hypr/hyprlock-pixel.conf), vẽ trên lưới ô
# FIXED_U px như khung KAFKA.SYS (bán kính trong bảng không còn dùng, góc bậc thang 3 ô):
# tên: (rộng, cao, bán kính, độ đục nền, màu như FRAMES)
FIXED_U = 4
FIXED = {
    "lock-card": (460, 420, 16, 215, ("#140e1a", "#56466a", "#1d1626", "#261e30")),
    "lock-clock": (420, 150, 14, 190, ("#140e1a", "#56466a", "#1d1626", "#261e30")),
}


# ---------------------------------------------------------------------------------------------
# Khung "KAFKA.SYS" (giống hộp đăng nhập greetd/kafka-greeter): vẽ trên LƯỚI Ô (mỗi ô U px), góc bậc
# thang 2 ô, viền ngoài 1 ô, mép sáng trên-trái / bóng dưới-phải 1 ô, BÓNG CỨNG lệch 1 ô xuống-phải.
# Ảnh 9-slice cắt KHÔNG đều: trên/trái = 3 ô, dưới/phải = 4 ô (thêm bóng). CSS phải khớp CUT_*.
#   px-*.png    : cụm Waybar / tooltip, U = 2 → cắt 6 6 8 8 (trên phải dưới trái = 6 8 8 6)
#   win.png     : khung popup, U = 3, cắt 6 9 9 6 (kafka_theme.WIN_CUT)
#   win-title.png / win-dots.png: dải tiêu đề hồng (lặp ngang) + 3 ô vuông — LỚP NỀN của .panel (GTK3 vẽ
#                 border-image đè nền nên không đặt chúng trong border-image)
#   bar-tex.png : vân quét ngang mờ cho nền thanh trên/dock (lát lặp)
PX_U = 2
WIN_U = 3
WIN_TITLE = 7  # số ô của dải tiêu đề (gồm mép sáng + bóng, không tính vạch ngăn) → ảnh cao 8 ô = 24px
SHADOW = (11, 7, 16, 200)

# tên: (viền ngoài, mép sáng, bóng trong, nền)
PX = {
    "px": ("#140e1a", "#5a4a6b", "#241b2e", "#33293f"),
    "px-hover": ("#140e1a", "#7a6890", "#2a2034", "#463955"),
    "px-active": ("#3d1028", "#f08cbb", "#962f62", "#c94785"),
    "px-dark": ("#140e1a", "#3f3350", "#1a1420", "#241c2d"),
    "px-crit": ("#3d0f1a", "#ff9aae", "#a8344c", "#e0506e"),
}
WIN = {  # popup: (viền, mép sáng, bóng, nền, độ đục nền 0..255)
    "win": ("#140e1a", "#56466a", "#1a1422", "#221a2b", 245),
}
TITLE_COLS = ("#3d1028", "#f08cbb", "#962f62", "#c94785")  # dải tiêu đề hồng


def _cut(k, r):
    """Số ô bị cắt ở hàng k (0 = hàng ngoài cùng) của góc bậc thang r ô."""
    return max(0, r - k) if r <= 2 else int(round(r - (max(0, r * r - (r - k - 0.5) ** 2)) ** 0.5)) if k < r else 0


def _grid_frame(cw, ch, cols, r=2, fill_alpha=255, shadow=True, title=0, title_cols=None):
    """Lưới ô cw×ch (đã gồm 1 ô bóng ở phải/dưới nếu shadow) → mảng màu theo ô (None = trong suốt)."""
    edge, hi, sh, fill = (hexc(c) for c in cols)
    fill = (*fill[:3], fill_alpha)
    w, h = (cw - 1, ch - 1) if shadow else (cw, ch)
    g = [[None] * cw for _ in range(ch)]

    def shape(inset):
        """Tập ô của hình chữ nhật bo bậc thang thu vào `inset` ô."""
        out = set()
        rr = max(0, r - inset)
        for y in range(inset, h - inset):
            k = min(y - inset, h - inset - 1 - y)
            c = _cut(k, rr) if k < rr else 0
            for x in range(inset + c, w - inset - c):
                out.add((x, y))
        return out

    s0, s1, s2 = shape(0), shape(1), shape(2)
    if shadow:
        for x, y in s0:
            g[y + 1][x + 1] = SHADOW
    for x, y in s0:
        g[y][x] = edge
    for x, y in s1:
        # mép sáng: ô lớp 1 mà ô trên hoặc trái là viền; còn lại của lớp 1 là bóng
        g[y][x] = hi if ((x, y - 1) not in s1 or (x - 1, y) not in s1) else sh
    for x, y in s2:
        g[y][x] = fill
    # sửa mép bóng: ô lớp 1 sát cạnh dưới/phải → bóng (kể cả góc dưới-trái/trên-phải)
    for x, y in s1 - s2:
        if (x, y + 1) not in s1 or (x + 1, y) not in s1:
            if not ((x, y - 1) not in s1 or (x - 1, y) not in s1) or (x + y) >= (w + h) // 2:
                g[y][x] = sh
    if title:
        te, thi, tsh, tfill = (hexc(c) for c in title_cols)
        for x, y in s1:
            if y <= title:  # dải tiêu đề: ô 1..title
                top_or_left = (x, y - 1) not in s1 or (x - 1, y) not in s1
                g[y][x] = thi if (top_or_left or y == 1) else (tsh if (y == title or (x + 1, y) not in s1) else tfill)
        for x, y in s0:
            if y == title + 1 and (x, y) in s1:  # vạch ngăn tối dưới dải
                g[y][x] = te
            elif y <= title and (x, y) not in s1:
                g[y][x] = te
    return g


def _raster(g, u):
    ch, cw = len(g), len(g[0])
    W, H = cw * u, ch * u
    buf = bytearray(W * H * 4)
    for cy in range(ch):
        for cx in range(cw):
            col = g[cy][cx]
            if col is None:
                continue
            px = bytes(col)
            for yy in range(cy * u, cy * u + u):
                o = (yy * W + cx * u) * 4
                buf[o : o + u * 4] = px * u
    return W, H, bytes(buf)


def make_px(name, cols):
    """Cụm Waybar: 3 ô trái/trên + 1 ô giữa + 3 ô + 1 ô bóng → 8×8 ô."""
    g = _grid_frame(8, 8, cols)
    W, H, rgba = _raster(g, PX_U)
    xw._write_png(os.path.join(HERE, f"{name}.png"), W, H, rgba)


def make_win(name, cols, alpha):
    """Khung popup: viền 1 ô + mép 1 ô (cắt trên/trái 2 ô), phải/dưới thêm 1 ô bóng → cắt 6 9 9 6 (ô 3px).
    Dải tiêu đề KHÔNG nằm trong ảnh này: GTK3 vẽ border-image ĐÈ lên nền, nên dải + 3 ô vuông là lớp nền
    (win-title.png lặp ngang, win-dots.png) đặt trong padding-box ngay dưới mép trên."""
    cw = ch = 2 + 1 + 2 + 1
    g = _grid_frame(cw, ch, cols, r=2, fill_alpha=alpha)
    W, H, rgba = _raster(g, WIN_U)
    xw._write_png(os.path.join(HERE, f"{name}.png"), W, H, rgba)
    return 2 * WIN_U, 3 * WIN_U, 3 * WIN_U, 2 * WIN_U  # cắt trên phải dưới trái (px)


def make_title():
    """Dải tiêu đề hồng 1 cột (lặp ngang): mép sáng 1 ô, nền 5 ô, bóng 1 ô, vạch ngăn tối 1 ô = 24px."""
    edge, hi, sh, fill = (hexc(c) for c in TITLE_COLS)
    col = [hi] + [fill] * (WIN_TITLE - 2) + [sh, edge]
    g = [[c] for c in col]
    W, H, rgba = _raster(g, WIN_U)
    xw._write_png(os.path.join(HERE, "win-title.png"), W, H, rgba)


def make_dots():
    """3 ô vuông tối ở góc phải dải tiêu đề (như hộp đăng nhập), cao bằng dải."""
    u = WIN_U
    cw, ch = 2 + 3 * 3 + 2 + 2, WIN_TITLE + 1  # 3 ô vuông 3×3 cách 1 ô, chừa 2 ô mỗi bên
    g = [[None] * cw for _ in range(ch)]
    for i in range(3):
        x0 = 2 + i * 4
        for y in range(2, 5):
            for x in range(x0, x0 + 3):
                g[y][x] = hexc("#3d1028")
    W, H, rgba = _raster(g, u)
    xw._write_png(os.path.join(HERE, "win-dots.png"), W, H, rgba)


def make_tex():
    """Vân quét: 1 hàng tối mờ mỗi 3 hàng + chấm dither thưa (lát 6×3)."""
    W, H = 6, 3
    buf = bytearray(W * H * 4)
    for x in range(W):
        o = (2 * W + x) * 4
        buf[o : o + 4] = bytes((0, 0, 0, 34))
    o = (0 * W + 1) * 4
    buf[o : o + 4] = bytes((255, 255, 255, 7))
    xw._write_png(os.path.join(HERE, "bar-tex.png"), W, H, bytes(buf))


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
            if any(
                not inn(x + dx, y + dy) for dx in range(-d, d + 1) for dy in range(-d, d + 1) if abs(dx) + abs(dy) <= d
            ):
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
                col = hi if (x * nh + y * n) < n * nh - min(n, nh) else sh  # vuông: x + y < n - 1
            else:
                col = (*fill[:3], fill_alpha)
            buf[(y * n + x) * 4 : (y * n + x) * 4 + 4] = bytes(col)
    return bytes(buf)


def main():
    for name, cols in FRAMES.items():
        panel = name.startswith("panel")
        n = 2 * PANEL_SLICE + 1 if panel else SIZE
        r = PANEL_RADIUS if panel else RADIUS
        rgba = render(*(hexc(c) for c in cols), n, r, PANEL_ALPHA.get(name, 255))
        xw._write_png(os.path.join(HERE, f"{name}.png"), n, n, rgba)
    for name, (w, h, r, a, cols) in FIXED.items():
        # màn hình khoá: cùng kiểu lưới ô như khung Waybar/popup (ô FIXED_U px, góc bậc thang 3 ô, bóng cứng)
        g = _grid_frame(w // FIXED_U, h // FIXED_U, cols, r=3, fill_alpha=a)
        W, H, rgba = _raster(g, FIXED_U)
        xw._write_png(os.path.join(HERE, f"{name}.png"), W, H, rgba)
    for name, cols in PX.items():
        make_px(name, cols)
    for name, (*cols, a) in WIN.items():
        cut = make_win(name, cols, a)
    make_title()
    make_dots()
    make_tex()
    print(
        f"KAFKA.SYS: {len(PX)} khung cụm (ô {PX_U}px, cắt 6 8 8 6) + popup win.png (ô {WIN_U}px, cắt {' '.join(map(str, cut))})"
    )
    print(
        f"Đã sinh {len(FRAMES)} khung + {len(FIXED)} ảnh cố định vào {HERE} (cụm: bo {RADIUS} cắt {SLICE}; popup: bo {PANEL_RADIUS} cắt {PANEL_SLICE})"
    )


if __name__ == "__main__":
    main()
