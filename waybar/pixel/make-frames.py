#!/usr/bin/env python3
"""make-frames.py — sinh ảnh khung pixel 9-slice cho theme Waybar "pixel" (waybar/theme-pixel.css).

Mỗi khung là lưới 7×7 "điểm pixel nghệ thuật" phóng 2× (PX) → ảnh 14×14; CSS cắt 9 mảnh bằng
`border-image: url(...) 6 stretch` (6px = 3 điểm: viền tối + viền trắng + 1 điểm nền). Góc bị khuyết một điểm
→ bo góc kiểu pixel bậc thang. Chạy lại script khi đổi bảng màu (PALETTE) cho khớp theme-pixel.css.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "cursors"))
import xcursor_write as xw  # noqa: E402  (dùng lại bộ ghi PNG thuần Python)

PX = 2
OUT_DARK = (42, 31, 51, 255)      # viền ngoài tối #2a1f33
WHITE = (255, 255, 255, 255)
SHADE = (74, 58, 92, 255)         # bóng đáy-phải bên trong (#4a3a5c)

FRAMES = {
    # tên: (nền, viền trong sáng, có bóng đáy-phải)
    "frame":        ((143, 127, 166, 255), WHITE, True),    # ô thường  #8f7fa6
    "frame-hover":  ((168, 151, 191, 255), WHITE, True),    # rê chuột  #a897bf
    "frame-active": ((201, 71, 133, 255), WHITE, True),     # đang chọn #c94785
    "frame-dark":   ((93, 76, 112, 255), (190, 176, 210, 255), False),  # ô chìm (khay, thẻ app) #5d4c70
    "frame-crit":   ((230, 70, 100, 255), WHITE, True),
}

ART = [
    ".KKKKK.",
    "KWWWWWK",
    "KWFFFSK",
    "KWFFFSK",
    "KWFFFSK",
    "KWSSSSK",
    ".KKKKK.",
]


def render(fill, rim, shade):
    n = len(ART) * PX
    buf = bytearray(n * n * 4)
    for y, row in enumerate(ART):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            col = {"K": OUT_DARK, "W": rim, "F": fill, "S": SHADE if shade else fill}[ch]
            for dy in range(PX):
                for dx in range(PX):
                    i = ((y * PX + dy) * n + x * PX + dx) * 4
                    buf[i:i + 4] = bytes(col)
    return n, bytes(buf)


def main():
    for name, (fill, rim, shade) in FRAMES.items():
        n, rgba = render(fill, rim, shade)
        xw._write_png(os.path.join(HERE, f"{name}.png"), n, n, rgba)
    print(f"Đã sinh {len(FRAMES)} khung vào {HERE}")


if __name__ == "__main__":
    main()
