#!/usr/bin/env python3
"""build-kafka-pixel-cursor.py — theme con trỏ pixel art "Kafka-Pixel" (vẽ tay bằng bản đồ điểm ảnh).

Phong cách pixel viền trắng + viền tối, mỗi con trỏ = ký hiệu nhỏ ở góc trên trái (mũi tên, ?, đồng hồ cát,
con trỏ chữ, bàn tay, biển cấm, tim, tâm ngắm) + linh vật gốc: chú nhện tím đeo kính râm hồng. Đổi cỡ/di
chuyển = bông mạng nhện hồng có tam giác chỉ hướng. Lưới 32×32, phóng to kiểu "nearest" để giữ nét pixel.

Dùng: build-kafka-pixel-cursor.py [--out ~/.local/share/icons/Kafka-Pixel] [--preview ảnh.png]
Đổi theme: hyprctl setcursor Kafka-Pixel 32 (xem CLAUDE.md, mục con trỏ).
"""

import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xcursor_write as xw  # noqa: E402

THEME = "Kafka-Pixel"
GRID = 32
SIZES = (32, 48, 64, 96)
WAIT_FRAMES = 8
WAIT_DELAY = 110

PAL = {
    "K": (30, 14, 34, 255),  # viền tối
    "W": (255, 255, 255, 255),  # viền trắng
    "P": (138, 42, 110, 255),  # thân nhện
    "p": (190, 80, 150, 255),  # thân sáng
    "D": (92, 26, 74, 255),  # thân tối
    "G": (40, 16, 48, 255),  # kính râm
    "g": (255, 140, 192, 255),  # ánh kính
    "C": (255, 150, 190, 255),  # má hồng
    "m": (60, 20, 50, 255),  # miệng
    "L": (214, 120, 182, 255),  # chân (sáng để không lẫn vào viền tối)
    "R": (224, 85, 154, 255),  # hồng nhấn
    "r": (170, 40, 100, 255),  # hồng tối
    "H": (255, 205, 230, 255),  # hồng rất sáng
    "X": (230, 50, 70, 255),  # đỏ biển cấm
    "S": (240, 200, 120, 255),  # cát
    "w": (235, 230, 240, 255),  # trắng ngà (bàn tay)
    "V": (169, 94, 232, 255),  # tím
}

SPIDER = [
    "       pppppppppp       ",
    "     ppPPPPPPPPPPpp     ",
    "    pPPPPPPPPPPPPPPp    ",
    "   pPGGGGGGPPGGGGGGPp   ",
    "LL PPGgGGGGGGGgGGGGPP LL",
    "  LPPGGGGGPPPPGGGGGPPL  ",
    "   PPPGGGPPPPPPGGGPPP   ",
    "   PPPPPPPPPPPPPPPPPP   ",
    "LL PCCPPPPPmmPPPPPCCP LL",
    "  LDPPPPPPPPPPPPPPPPDL  ",
    "    DPPPPPPPPPPPPPPD    ",
    "     DDPPPPPPPPPPDD     ",
    "       DDDDDDDDDD       ",
]

ARROW = [
    "R        ",
    "RR       ",
    "RRR      ",
    "RRRr     ",
    "RRRrr    ",
    "RRRrrr   ",
    "RRRrrrr  ",
    "RRRrrrrr ",
    "RRRrr    ",
    "RR  rr   ",
    "R    rr  ",
]
QMARK = [
    " RRRR ",
    "RR  RR",
    "    RR",
    "   RR ",
    "  RR  ",
    "  RR  ",
    "      ",
    "  RR  ",
]
HOURGLASS = [  # khung; cát vẽ theo khung hình
    "rrrrrrr",
    " r   r ",
    " r   r ",
    "  r r  ",
    "   r   ",
    "  r r  ",
    " r   r ",
    " r   r ",
    "rrrrrrr",
]
IBEAM = [
    "WWW WWW",
    "   W   ",
    "   W   ",
    "   W   ",
    "   W   ",
    "   W   ",
    "   W   ",
    "   W   ",
    "   W   ",
    "   W   ",
    "WWW WWW",
]
HAND = [
    "  ww    ",
    "  ww    ",
    "  ww    ",
    "  wwww  ",
    "  wwwwww",
    "wwwwwwww",
    "wwwwwwww",
    " wwwwwww",
    "  wwwww ",
]
NOSIGN = [
    "  XXXX  ",
    " XXXXXX ",
    "XXWWWWXX",
    "XWWWWWWX",
    "XXXXXXXX",
    " XXXXXX ",
    "  XXXX  ",
]
HEART = [
    " RR RR ",
    "RHRRRRR",
    "RRRRRRR",
    "RRRRRRR",
    " RRRRR ",
    "  RRR  ",
    "   R   ",
]
CROSS = [
    "    W    ",
    "    W    ",
    "    W    ",
    "         ",
    "WWW R WWW",
    "         ",
    "    W    ",
    "    W    ",
    "    W    ",
]
PLUS = ["  W  ", "  W  ", "WWWWW", "  W  ", "  W  "]
TRI = ["r", "rr", "rrr", "rrrr", "rrr", "rr", "r"]  # tam giác chỉ sang trái (đầu nhọn bên trái)


# ---------- ảnh pixel (lưới dict (x,y) → ký tự màu) ----------
class Canvas:
    def __init__(self):
        self.px = {}

    def stamp(self, art, ox, oy, sub=None):
        for y, row in enumerate(art):
            for x, ch in enumerate(row):
                if ch != " ":
                    if sub:
                        ch = sub.get(ch, ch)
                    self.px[(ox + x, oy + y)] = ch
        return self

    def put(self, x, y, ch):
        self.px[(int(x), int(y))] = ch

    def outline(self, keys=None):
        """Viền kiểu sticker: 1 lớp tối quanh hình (8 hướng), rồi 1 lớp trắng quanh đó (4 hướng)."""
        base = set(self.px if keys is None else keys)
        dark = set()
        for x, y in base:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (x + dx, y + dy)
                    if q not in self.px:
                        dark.add(q)
        for q in dark:
            self.px[q] = "K"
        white = set()
        for x, y in list(self.px):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (x + dx, y + dy)
                if q not in self.px:
                    white.add(q)
        for q in white:
            self.px[q] = "W"
        return self

    def merge_over(self, other):
        """Vẽ other đè lên self (other đã có viền riêng)."""
        self.px.update(other.px)
        return self

    def rgba(self):
        buf = bytearray(GRID * GRID * 4)
        for (x, y), ch in self.px.items():
            if 0 <= x < GRID and 0 <= y < GRID:
                i = (y * GRID + x) * 4
                buf[i : i + 4] = bytes(PAL[ch])
        return bytes(buf)


def sprite(art, ox, oy, sub=None):
    return Canvas().stamp(art, ox, oy, sub).outline()


def mascot(frame=0, ox=7, oy=15, look=None):
    """Linh vật nhện (có viền). frame dùng cho nhún nhẹ khi chờ."""
    art = SPIDER
    if look == "wink":  # nhắm một bên kính (đổi ánh kính)
        art = [r.replace("g", "G") for r in SPIDER]
    dy = (0, -1, 0, 1)[frame % 4] if frame >= 0 else 0
    return sprite(art, ox, oy + dy)


def web_flower(cx=16, cy=16, R=8.6):
    """Bông mạng nhện pixel: 8 tia + 3 vòng bát giác, hồng/hồng sáng, viền sticker."""
    c = Canvas()
    for k in range(8):
        a = math.radians(k * 45 + 22.5)
        for t in range(int(R * 4) + 1):
            r = t / 4
            c.put(round(cx + r * math.cos(a)), round(cy + r * math.sin(a)), "R")
    for i, rr in enumerate((3.2, 6.0, R)):
        pts = [
            (cx + rr * math.cos(math.radians(k * 45 + 22.5)), cy + rr * math.sin(math.radians(k * 45 + 22.5)))
            for k in range(9)
        ]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
            for s in range(n + 1):
                c.put(round(x0 + (x1 - x0) * s / n), round(y0 + (y1 - y0) * s / n), "H" if i == 1 else "R")
    c.put(cx, cy, "V")
    return c.outline()


def tri(direction, cx, cy):
    """Tam giác chỉ hướng (left/right/up/down/nw/ne/sw/se) với đầu nhọn tại (cx, cy)."""
    c = Canvas()
    if direction in ("left", "right", "up", "down"):
        for y, row in enumerate(TRI):
            for x in range(len(row)):
                dx, dy = x, y - 3
                if direction == "left":
                    c.put(cx + dx, cy + dy, "r")
                elif direction == "right":
                    c.put(cx - dx, cy + dy, "r")
                elif direction == "up":
                    c.put(cx + dy, cy + dx, "r")
                else:
                    c.put(cx + dy, cy - dx, "r")
    else:
        sx = 1 if "w" in direction else -1
        sy = 1 if "n" in direction else -1
        for i in range(5):
            for j in range(5 - i):
                c.put(cx + sx * i, cy + sy * j, "r")
    return c.outline()


def hourglass(frame):
    c = Canvas().stamp(HOURGLASS, 1, 1)
    k = frame % WAIT_FRAMES
    top = max(0, 3 - k // 2)  # cát trên vơi dần, dưới đầy dần
    sand_top = [(2, 2), (3, 2), (4, 2), (5, 2), (3, 3), (4, 3), (5, 3), (4, 4)][: top * 2 + (1 if top else 0)]
    sand_bot = [(4, 8), (3, 8), (5, 8), (2, 8), (6, 8), (3, 7), (4, 7), (5, 7)][: min(8, 2 + k)]
    for x, y in sand_top + sand_bot:
        c.put(x, y, "S")
    if k % 2 == 0:
        c.put(5, 5, "S")  # hạt cát rơi
    return c.outline()


def compose(*layers):
    out = Canvas()
    for l in layers:
        out.merge_over(l)
    return out


# ---------- danh sách hình ----------
def shapes():
    S = {}

    def add(name, frames, hot, aliases=()):
        S[name] = (frames if isinstance(frames, list) else [frames], hot, list(aliases))

    arrow = lambda: sprite(ARROW, 2, 2)
    add(
        "default",
        compose(mascot(-1), arrow()),
        (2, 2),
        ["left_ptr", "arrow", "top_left_arrow", "left-arrow", "x-cursor", "X_cursor"],
    )
    add(
        "help",
        compose(mascot(-1, look="wink"), arrow(), sprite(QMARK, 23, 2)),
        (2, 2),
        ["question_arrow", "whats_this", "left_ptr_help", "context-menu"],
    )
    add(
        "progress",
        [compose(mascot(f), arrow(), _shift(hourglass(f), 12, 1)) for f in range(WAIT_FRAMES)],
        (2, 2),
        ["left_ptr_watch", "half-busy"],
    )
    add("wait", [compose(mascot(f), hourglass(f)) for f in range(WAIT_FRAMES)], (5, 5), ["watch", "clock"])
    add("text", compose(mascot(-1), sprite(IBEAM, 2, 1)), (5, 6), ["xterm", "ibeam", "vertical-text"])
    add(
        "pointer",
        compose(mascot(-1), sprite(HAND, 2, 2)),
        (4, 2),
        ["hand1", "hand2", "hand", "pointing_hand", "grab", "openhand", "grabbing", "closedhand"],
    )
    add(
        "not-allowed",
        compose(mascot(-1, look="wink"), sprite(NOSIGN, 2, 2)),
        (5, 5),
        ["forbidden", "circle", "crossed_circle", "no-drop", "dnd-no-drop"],
    )
    add("alias", compose(mascot(-1), arrow(), sprite(HEART, 22, 3)), (2, 2), ["link", "dnd-link"])
    add("copy", compose(mascot(-1), arrow(), sprite(PLUS, 23, 3)), (2, 2), ["dnd-copy"])
    add("crosshair", compose(mascot(-1), sprite(CROSS, 1, 1)), (5, 5), ["cross", "tcross", "cell", "plus"])
    W = web_flower
    add(
        "move",
        compose(W(), tri("up", 16, 2), tri("down", 16, 30), tri("left", 2, 16), tri("right", 30, 16)),
        (16, 16),
        ["fleur", "size_all", "all-scroll", "dnd-move"],
    )
    add(
        "ew-resize",
        compose(W(), tri("left", 2, 16), tri("right", 30, 16)),
        (16, 16),
        [
            "sb_h_double_arrow",
            "h_double_arrow",
            "size_hor",
            "e-resize",
            "w-resize",
            "col-resize",
            "split_h",
            "left_side",
            "right_side",
        ],
    )
    add(
        "ns-resize",
        compose(W(), tri("up", 16, 2), tri("down", 16, 30)),
        (16, 16),
        [
            "sb_v_double_arrow",
            "v_double_arrow",
            "size_ver",
            "n-resize",
            "s-resize",
            "row-resize",
            "split_v",
            "top_side",
            "bottom_side",
        ],
    )
    add(
        "nwse-resize",
        compose(W(), tri("nw", 3, 3), tri("se", 29, 29)),
        (16, 16),
        ["size_fdiag", "nw-resize", "se-resize", "top_left_corner", "bottom_right_corner", "bd_double_arrow"],
    )
    add(
        "nesw-resize",
        compose(W(), tri("ne", 29, 3), tri("sw", 3, 29)),
        (16, 16),
        ["size_bdiag", "ne-resize", "sw-resize", "top_right_corner", "bottom_left_corner", "fd_double_arrow"],
    )
    add("zoom-in", compose(mascot(-1), sprite(PLUS, 2, 2)), (4, 4), ["zoom-out"])
    return S


def _shift(c, dx, dy):
    o = Canvas()
    o.px = {(x + dx, y + dy): ch for (x, y), ch in c.px.items()}
    return o


def scale_nearest(rgba, n):
    if n == GRID:
        return rgba
    out = bytearray(n * n * 4)
    for y in range(n):
        sy = y * GRID // n
        for x in range(n):
            sx = x * GRID // n
            i, j = (y * n + x) * 4, (sy * GRID + sx) * 4
            out[i : i + 4] = rgba[j : j + 4]
    return bytes(out)


def build(out, preview=None):
    work = tempfile.mkdtemp(prefix="kafka-pixel-")
    try:
        src = os.path.join(work, "src")
        os.makedirs(os.path.join(src, "hyprcursors"))
        with open(os.path.join(src, "manifest.hl"), "w") as f:
            f.write(
                f"name = {THEME}\ndescription = Con trỏ pixel nhện Kafka\nversion = 1.0\ncursors_directory = hyprcursors\n"
            )
        xc = os.path.join(work, "cursors")
        os.makedirs(xc)
        S = shapes()
        prev_files = []
        for name, (frames, (hx, hy), aliases) in S.items():
            d = os.path.join(src, "hyprcursors", name)
            os.makedirs(d)
            meta = [
                "resize_algorithm = nearest",
                f"hotspot_x = {hx / GRID:.4f}",
                f"hotspot_y = {hy / GRID:.4f}",
                "nominal_size = 1.0",
            ]
            xf = []
            for size in SIZES:
                for i, fr in enumerate(frames):
                    fn = f"{name}-{size}-{i:02d}.png"
                    p = os.path.join(d, fn)
                    xw._write_png(p, size, size, scale_nearest(fr.rgba(), size))
                    meta.append(f"define_size = {size}, {fn}" + (f", {WAIT_DELAY}" if len(frames) > 1 else ""))
                    xf.append(
                        {
                            "size": size,
                            "png": p,
                            "xhot": hx * size // GRID,
                            "yhot": hy * size // GRID,
                            "delay": WAIT_DELAY if len(frames) > 1 else 0,
                        }
                    )
                    if size == 96 and i == 0:
                        prev_files.append(p)
            if aliases:
                meta.append("define_override = " + ";".join(aliases))
            with open(os.path.join(d, "meta.hl"), "w") as f:
                f.write("\n".join(meta) + "\n")
            xw.write_xcursor(os.path.join(xc, name), xf)
            for a in aliases:
                os.symlink(name, os.path.join(xc, a))
        hout = os.path.join(work, "hout")
        os.makedirs(hout)
        p = subprocess.run(["hyprcursor-util", "--create", src, "--output", hout], capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError("hyprcursor-util lỗi:\n" + p.stdout[-800:] + p.stderr[-800:])
        built = os.path.join(hout, os.listdir(hout)[0])
        out = os.path.expanduser(out)
        if os.path.basename(out.rstrip("/")) != THEME:
            raise SystemExit(f"--out phải kết thúc bằng /{THEME}")
        shutil.rmtree(out, ignore_errors=True)
        shutil.copytree(built, out, symlinks=True)
        shutil.copytree(xc, os.path.join(out, "cursors"), symlinks=True)
        with open(os.path.join(out, "index.theme"), "w") as f:
            f.write(f"[Icon Theme]\nName={THEME}\nComment=Con trỏ pixel nhện Kafka\nInherits=Kafka-Cursor,Adwaita\n")
        if preview:
            subprocess.run(
                [
                    "magick",
                    "montage",
                    *prev_files,
                    "-tile",
                    "8x",
                    "-geometry",
                    "96x96+12+12",
                    "-background",
                    "#6b5a7e",
                    preview,
                ],
                check=True,
            )
        print(f"Đã dựng {THEME}: {len(S)} hình → {out}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    out, preview = f"~/.local/share/icons/{THEME}", None
    it = iter(argv)
    for a in it:
        if a == "--out":
            out = next(it)
        elif a == "--preview":
            preview = next(it)
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
    build(out, preview)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
