#!/usr/bin/env python3
"""build-kafka-cursor.py — dựng theme con trỏ "Kafka-Cursor" (thiết kế riêng, hợp hình nền Kafka).

Phong cách: thân tím than (#2b1530 → #4b2148), viền hồng nhấn #e0559a (cùng màu Waybar), mạng nhện
mờ trong thân mũi tên, vòng chờ xoay hồng→tím với mạng nhện ở giữa. Mọi hình vẽ bằng SVG sinh từ script
này (lưới 32×32), rồi xuất ra 2 định dạng trong cùng một thư mục theme:
  • hyprcursor (Hyprland vẽ con trỏ phía máy chủ; giữ SVG nên nét ở mọi cỡ) — qua `hyprcursor-util`
  • Xcursor (app XWayland, app không dùng cursor-shape) — PNG từ `rsvg-convert`, ghi bằng xcursor_write.py

Dùng:
  build-kafka-cursor.py [--out ~/.local/share/icons/Kafka-Cursor] [--preview ảnh.png] [--keep-build DIR]
Áp dụng: hyprland.lua đặt XCURSOR_THEME/HYPRCURSOR_THEME=Kafka-Cursor; install.sh chạy script này.
"""

import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

THEME = "Kafka-Cursor"
SIZES = (24, 32, 48, 64)          # cỡ Xcursor (cỡ danh nghĩa 24 = lưới 32 vẽ ở 24px)
WAIT_FRAMES = 12
WAIT_DELAY = 70                    # ms mỗi khung

PINK = "#e0559a"
PINK_HI = "#ff8cc0"
VIOLET = "#a95ee8"
PLUM_A = "#3a1a3c"
PLUM_B = "#1f0f24"
OUTLINE = 1.7                      # nửa độ dày viền hồng (vẽ nét 2×OUTLINE rồi tô đè)

DEFS = f"""<defs>
 <linearGradient id="body" x1="0" y1="0" x2="0.7" y2="1">
  <stop offset="0" stop-color="{PLUM_A}"/><stop offset="1" stop-color="{PLUM_B}"/></linearGradient>
 <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="{PINK_HI}"/><stop offset="0.5" stop-color="{PINK}"/><stop offset="1" stop-color="{VIOLET}"/></linearGradient>
 <filter id="sh" x="-30%" y="-30%" width="160%" height="160%">
  <feGaussianBlur in="SourceAlpha" stdDeviation="0.9"/><feOffset dx="0.6" dy="1.1"/>
  <feComponentTransfer><feFuncA type="linear" slope="0.45"/></feComponentTransfer>
  <feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>"""


def svg(body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">{DEFS}'
            f'<g filter="url(#sh)">{body}</g></svg>')


def solid(shapes, outline=OUTLINE, extra=""):
    """Khối liền: vẽ viền hồng (nét dày) cho mọi hình rồi tô thân đè lên → viền bao ngoài của hợp các hình."""
    return (f'<g stroke="url(#edge)" stroke-width="{outline * 2}" stroke-linejoin="round" '
            f'stroke-linecap="round" fill="url(#edge)">{shapes}</g>'
            f'<g fill="url(#body)" stroke="none">{shapes}</g>{extra}')


# ---------- các mảnh hình ----------
ARROW = "M5,3.2 L5,23.6 L9.9,19 L13.3,26.6 L16.5,25.1 L13.2,17.7 L19.9,17.4 Z"


def arrow_web():
    """Mạng nhện mờ trong thân mũi tên, tâm ở mũi."""
    cx, cy = 5, 3.2
    spokes = [62, 72, 82]                       # độ, đo từ trục x, đi xuống
    rings = (6.5, 11, 15.5)
    out = []
    for a in spokes:
        r = math.radians(a)
        out.append(f"M{cx},{cy} L{cx + 20 * math.cos(r):.2f},{cy + 20 * math.sin(r):.2f}")
    for rr in rings:
        pts = [(cx + rr * math.cos(math.radians(a)), cy + rr * math.sin(math.radians(a))) for a in [45] + spokes + [90]]
        d = f"M{pts[0][0]:.2f},{pts[0][1]:.2f}"
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            qx, qy = mx + (cx - mx) * 0.1, my + (cy - my) * 0.1
            d += f" Q{qx:.2f},{qy:.2f} {x1:.2f},{y1:.2f}"
        out.append(d)
    return (f'<clipPath id="ac"><path d="{ARROW}"/></clipPath>'
            f'<path clip-path="url(#ac)" d="{" ".join(out)}" fill="none" stroke="{PINK}" '
            f'stroke-opacity="0.45" stroke-width="0.6" stroke-linecap="round"/>'
            f'<path d="M6.3,6.2 L6.3,13" stroke="#ffffff" stroke-opacity="0.35" stroke-width="0.8" stroke-linecap="round"/>')


def arrow():
    return solid(f'<path d="{ARROW}"/>', extra=arrow_web())


def badge(inner, cx=23.5, cy=23.5, r=5.6):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r + 1.2}" fill="{PLUM_B}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#edge)"/>{inner}')


def plus(cx, cy, s=2.8, w=1.7, col="#ffffff"):
    return (f'<path d="M{cx - s},{cy} H{cx + s} M{cx},{cy - s} V{cy + s}" stroke="{col}" '
            f'stroke-width="{w}" stroke-linecap="round"/>')


def spinner(frame, cx=16, cy=16, r=9.0, w=3.2, web=True):
    """Vòng chờ: vòng nền tím than + cung hồng→tím quay theo khung; giữa là mạng nhện + con nhện nhỏ."""
    ang = frame * 360 / WAIT_FRAMES
    a0, a1 = math.radians(ang - 90), math.radians(ang + 150)
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    g = (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{PLUM_B}" stroke-width="{w + 2.2}"/>'
         f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{PINK}" stroke-opacity="0.22" stroke-width="{w}"/>'
         f'<path d="M{x0:.2f},{y0:.2f} A{r},{r} 0 1 1 {x1:.2f},{y1:.2f}" fill="none" stroke="url(#edge)" '
         f'stroke-width="{w}" stroke-linecap="round"/>')
    if web:
        rw = r - w / 2 - 1.2
        spokes = " ".join(f"M{cx},{cy} L{cx + rw * math.cos(math.radians(k * 60 + ang / 3)):.2f},"
                          f"{cy + rw * math.sin(math.radians(k * 60 + ang / 3)):.2f}" for k in range(6))
        hexes = ""
        for f in (0.45, 0.85):
            pts = [(cx + rw * f * math.cos(math.radians(k * 60 + ang / 3)),
                    cy + rw * f * math.sin(math.radians(k * 60 + ang / 3))) for k in range(7)]
            hexes += "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " "
        g += (f'<circle cx="{cx}" cy="{cy}" r="{rw + 0.6}" fill="{PLUM_B}" fill-opacity="0.85"/>'
              f'<path d="{spokes} {hexes}" fill="none" stroke="{PINK}" stroke-opacity="0.75" stroke-width="0.55"/>'
              f'<circle cx="{cx}" cy="{cy}" r="1.3" fill="{PINK_HI}"/>')
    return g


def hand(kind="point"):
    """Bàn tay cách điệu: point = ngón trỏ, open = xòe, fist = nắm."""
    if kind == "point":
        fingers = [(10.6, 2.6, 4.2, 16), (14.6, 10.6, 3.9, 9), (18.3, 11.6, 3.7, 8.4), (21.8, 13.2, 3.4, 7)]
    elif kind == "open":
        fingers = [(10.4, 5.0, 3.8, 13), (14.0, 3.6, 3.8, 14), (17.6, 4.6, 3.6, 13), (21.0, 7.0, 3.3, 11)]
    else:  # fist
        fingers = [(10.6, 11.4, 3.9, 8), (14.4, 10.8, 3.8, 8.6), (18.0, 11.2, 3.6, 8.2), (21.4, 12.6, 3.3, 7)]
    rects = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{w / 2}"/>' for x, y, w, h in fingers)
    palm = ('<path d="M10.6,15.5 H24.9 V21.4 C24.9,26.2 22.1,28.9 17.8,28.9 H15.4 C12.6,28.9 11.1,27.6 9.6,25.7 '
            'L5.4,19.9 C4.6,18.8 4.9,17.4 6.1,16.9 C7.1,16.5 8.1,16.8 8.8,17.6 L10.6,19.7 Z"/>')
    seams = "".join(f'<path d="M{x},{y + 1.6} V{min(y + h - 0.5, 21)}" stroke="{PINK}" stroke-opacity="0.55" '
                    f'stroke-width="0.7" stroke-linecap="round"/>' for x, y, w, h in fingers[1:])
    shine = f'<path d="M12.2,{fingers[0][1] + 2} V{fingers[0][1] + 6}" stroke="#fff" stroke-opacity="0.35" stroke-width="0.8" stroke-linecap="round"/>'
    return solid(rects + palm, extra=seams + shine)


def double_arrow(rot=0, bar=None):
    """Mũi tên hai đầu (đổi cỡ). rot độ; bar: vạch giữa cho col/row-resize."""
    d = "M3.2,16 L9.4,9.8 V13.6 H22.6 V9.8 L28.8,16 L22.6,22.2 V18.4 H9.4 V22.2 Z"
    extra = ""
    shapes = f'<path d="{d}"/>'
    if bar:
        shapes += '<rect x="14.6" y="5" width="2.8" height="22" rx="1.2"/>'
    return f'<g transform="rotate({rot} 16 16)">{solid(shapes)}{extra}</g>'


def four_way():
    h = "M3.2,16 L8.6,10.8 V14.2 H23.4 V10.8 L28.8,16 L23.4,21.2 V17.8 H8.6 V21.2 Z"
    v = "M16,3.2 L21.2,8.6 H17.8 V23.4 H21.2 L16,28.8 L10.8,23.4 H14.2 V8.6 H10.8 Z"
    return solid(f'<path d="{h}"/><path d="{v}"/>', extra=f'<circle cx="16" cy="16" r="1.6" fill="{PINK}"/>')


def ibeam(rot=0):
    d = "M12,5 Q16,5 16,8.2 Q16,5 20,5 M16,8.2 V23.8 M12,27 Q16,27 16,23.8 Q16,27 20,27 M13.4,16 H18.6"
    return (f'<g transform="rotate({rot} 16 16)"><path d="{d}" fill="none" stroke="{PLUM_B}" stroke-width="4.4" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{d}" fill="none" stroke="url(#edge)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></g>')


def crosshair():
    d = "M16,3 V12 M16,20 V29 M3,16 H12 M20,16 H29"
    return (f'<path d="{d}" stroke="{PLUM_B}" stroke-width="4" stroke-linecap="round"/>'
            f'<circle cx="16" cy="16" r="6" fill="none" stroke="{PLUM_B}" stroke-width="3.6"/>'
            f'<path d="{d}" stroke="url(#edge)" stroke-width="1.8" stroke-linecap="round"/>'
            f'<circle cx="16" cy="16" r="6" fill="none" stroke="url(#edge)" stroke-width="1.3"/>'
            f'<circle cx="16" cy="16" r="1.2" fill="{PINK_HI}"/>')


def cell():
    d = "M16,6 V26 M6,16 H26"
    return (f'<path d="{d}" stroke="{PINK}" stroke-width="7.6" stroke-linecap="round"/>'
            f'<path d="{d}" stroke="url(#body)" stroke-width="4.2" stroke-linecap="round"/>')


def forbidden(cx=16, cy=16, r=9.2, w=3.2):
    a = math.radians(45)
    dx, dy = r * math.cos(a), r * math.sin(a)
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{PLUM_B}" stroke-width="{w + 2.4}"/>'
            f'<path d="M{cx - dx},{cy - dy} L{cx + dx},{cy + dy}" stroke="{PLUM_B}" stroke-width="{w + 2.4}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#ff4f86" stroke-width="{w}"/>'
            f'<path d="M{cx - dx},{cy - dy} L{cx + dx},{cy + dy}" stroke="#ff4f86" stroke-width="{w}"/>')


def magnifier(sign):
    inner = plus(12.5, 12.5, 3, 1.7) if sign == "+" else '<path d="M9.5,12.5 H15.5" stroke="#fff" stroke-width="1.7" stroke-linecap="round"/>'
    return (f'<path d="M18,18 L27,27" stroke="{PLUM_B}" stroke-width="6" stroke-linecap="round"/>'
            f'<path d="M18,18 L27,27" stroke="url(#edge)" stroke-width="3.4" stroke-linecap="round"/>'
            f'<circle cx="12.5" cy="12.5" r="8" fill="{PLUM_B}"/><circle cx="12.5" cy="12.5" r="6.6" fill="url(#body)" '
            f'stroke="url(#edge)" stroke-width="2"/>{inner}')


def qmark(cx=23.5, cy=23.5):
    return (f'<path d="M{cx - 2},{cy - 1.8} Q{cx - 2},{cy - 4} {cx},{cy - 4} Q{cx + 2.2},{cy - 4} {cx + 2.2},{cy - 2} '
            f'Q{cx + 2.2},{cy - 0.6} {cx},{cy + 0.2} V{cy + 1}" fill="none" stroke="#fff" stroke-width="1.5" '
            f'stroke-linecap="round" stroke-linejoin="round"/><circle cx="{cx}" cy="{cy + 3}" r="0.95" fill="#fff"/>')


def alias_mark(cx=23.5, cy=23.5):
    return (f'<path d="M{cx - 2.6},{cy + 2.4} Q{cx - 2.6},{cy - 2} {cx + 1.6},{cy - 2}" fill="none" stroke="#fff" '
            f'stroke-width="1.5" stroke-linecap="round"/><path d="M{cx + 0.4},{cy - 4} L{cx + 2.8},{cy - 2} '
            f'L{cx + 0.4},{cy}" fill="none" stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>')


def menu_mark(cx=23.5, cy=23.5):
    return "".join(f'<path d="M{cx - 2.6},{cy + k} H{cx + 2.6}" stroke="#fff" stroke-width="1.3" '
                   f'stroke-linecap="round"/>' for k in (-2.2, 0, 2.2))


# ---------- danh sách hình: tên chính → (svg hoặc hàm khung, điểm nóng (x,y) trên lưới 32, các tên phụ) ----------
def shapes():
    S = {}
    def add(name, body, hot, aliases=()):
        S[name] = (body, hot, list(aliases))
    tip = (5, 3.2)
    add("default", svg(arrow()), tip, ["left_ptr", "arrow", "top_left_arrow", "left-arrow", "x-cursor", "X_cursor"])
    add("pointer", svg(hand("point")), (12.7, 2.8), ["hand1", "hand2", "hand", "pointing_hand", "e29285e634086352946a0e7090d73106", "9d800788f1b08800ae810202380a0822"])
    add("text", svg(ibeam()), (16, 16), ["xterm", "ibeam"])
    add("vertical-text", svg(ibeam(90)), (16, 16), [])
    add("crosshair", svg(crosshair()), (16, 16), ["cross", "tcross", "cross_reverse", "diamond_cross"])
    add("cell", svg(cell()), (16, 16), ["plus"])
    add("not-allowed", svg(forbidden()), (16, 16), ["forbidden", "circle", "crossed_circle", "03b6e0fcb3499374a867c041f52298f0"])
    add("no-drop", svg(arrow() + badge("", r=5) + forbidden(23.5, 23.5, 3.6, 1.6)), tip, ["dnd-no-drop"])
    add("help", svg(arrow() + badge(qmark())), tip, ["question_arrow", "whats_this", "left_ptr_help", "d9ce0ab605698f320427677b458ad60b", "5c6cd98b3f3ebcb1f9c7f1c204630408"])
    add("copy", svg(arrow() + badge(plus(23.5, 23.5))), tip, ["dnd-copy", "1081e37283d90000800003c07f3ef6bf", "6407b0e94181790501fd1e167b474872"])
    add("alias", svg(arrow() + badge(alias_mark())), tip, ["link", "dnd-link", "3085a0e285430894940527032f8b26df", "640fb0e74195791501fd1ed57b41487f"])
    add("context-menu", svg(arrow() + badge(menu_mark())), tip, [])
    add("move", svg(four_way()), (16, 16), ["fleur", "size_all", "dnd-move", "4498f0e0c1937ffe01fd06f973665830", "9081237383d90e509aa00f00170e968f"])
    add("all-scroll", svg(four_way()), (16, 16), [])
    add("grab", svg(hand("open")), (16, 12), ["openhand", "fd_double_arrow_grab", "5aca4d189052212118709018842178c0"])
    add("grabbing", svg(hand("fist")), (16, 14), ["closedhand", "dnd-none", "208530c400c041818281048008011002"])
    add("ew-resize", svg(double_arrow(0)), (16, 16), ["sb_h_double_arrow", "h_double_arrow", "size_hor", "e-resize", "w-resize", "right_side", "left_side", "028006030e0e7ebffc7f7070c0600140", "14fef782d02440884392942c11205230"])
    add("ns-resize", svg(double_arrow(90)), (16, 16), ["sb_v_double_arrow", "v_double_arrow", "size_ver", "n-resize", "s-resize", "top_side", "bottom_side", "00008160000006810000408080010102", "2870a09082c103050810ffdffffe0204"])
    add("nwse-resize", svg(double_arrow(45)), (16, 16), ["size_fdiag", "nw-resize", "se-resize", "top_left_corner", "bottom_right_corner", "bd_double_arrow", "c7088f0f3e6c8088236ef8e1e3e70000"])
    add("nesw-resize", svg(double_arrow(-45)), (16, 16), ["size_bdiag", "ne-resize", "sw-resize", "top_right_corner", "bottom_left_corner", "fd_double_arrow", "fcf1c3c7cd4491d801f1e1c78f100000"])
    add("col-resize", svg(double_arrow(0, bar=True)), (16, 16), ["split_h", "sb_h_double_arrow_bar", "14fef782d02440884392942c11205230"])
    add("row-resize", svg(double_arrow(90, bar=True)), (16, 16), ["split_v", "2870a09082c103050810ffdffffe0204"])
    add("zoom-in", svg(magnifier("+")), (12.5, 12.5), [])
    add("zoom-out", svg(magnifier("-")), (12.5, 12.5), [])
    add("wait", [svg(spinner(f)) for f in range(WAIT_FRAMES)], (16, 16), ["watch", "clock"])
    add("progress", [svg(arrow() + spinner(f, 23.2, 23.2, 4.8, 2.0, web=False)) for f in range(WAIT_FRAMES)], tip,
        ["left_ptr_watch", "half-busy", "00000000000000020006000e7e9ffc3f", "08e8e1c95fe2fc01f976f1e063a24ccd", "3ecb610c1bf2410f44200f48c40d3599"])
    # bỏ tên phụ trùng với tên chính khác (col/row-resize có hash trùng ew/ns: giữ cho ew/ns)
    seen = set(S)
    for name, (_b, _h, al) in S.items():
        keep = []
        for a in al:
            if a not in seen:
                keep.append(a)
                seen.add(a)
        al[:] = keep
    return S


def render_png(svg_text, size, path):
    p = subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), "-o", path],
                       input=svg_text.encode(), capture_output=True)
    if p.returncode:
        raise RuntimeError(f"rsvg-convert lỗi: {p.stderr.decode()[:300]}")


def build(out, keep_build=None, preview=None):
    import xcursor_write as xw
    work = keep_build or tempfile.mkdtemp(prefix="kafka-cursor-")
    os.makedirs(work, exist_ok=True)
    src = os.path.join(work, "src")
    shutil.rmtree(src, ignore_errors=True)
    os.makedirs(os.path.join(src, "hyprcursors"))
    with open(os.path.join(src, "manifest.hl"), "w") as f:
        f.write(f"name = {THEME}\ndescription = Con trỏ Kafka (tím than + viền hồng, mạng nhện)\n"
                "version = 1.0\ncursors_directory = hyprcursors\n")
    xc_dir = os.path.join(work, "cursors")
    shutil.rmtree(xc_dir, ignore_errors=True)
    os.makedirs(xc_dir)
    pngdir = os.path.join(work, "png")
    os.makedirs(pngdir, exist_ok=True)

    S = shapes()
    for name, (body, (hx, hy), aliases) in S.items():
        frames = body if isinstance(body, list) else [body]
        # --- hyprcursor: giữ SVG ---
        d = os.path.join(src, "hyprcursors", name)
        os.makedirs(d)
        meta = [f"resize_algorithm = bilinear", f"hotspot_x = {hx / 32:.4f}", f"hotspot_y = {hy / 32:.4f}",
                "nominal_size = 1.0"]
        for i, fr in enumerate(frames):
            fn = f"{name}-{i:02d}.svg" if len(frames) > 1 else f"{name}.svg"
            with open(os.path.join(d, fn), "w") as f:
                f.write(fr)
            meta.append(f"define_size = 0, {fn}" + (f", {WAIT_DELAY}" if len(frames) > 1 else ""))
        if aliases:
            meta.append("define_override = " + ";".join(aliases))
        with open(os.path.join(d, "meta.hl"), "w") as f:
            f.write("\n".join(meta) + "\n")
        # --- Xcursor: PNG nhiều cỡ ---
        xf = []
        for size in SIZES:
            for i, fr in enumerate(frames):
                pth = os.path.join(pngdir, f"{name}-{size}-{i:02d}.png")
                render_png(fr, size, pth)
                xf.append({"size": size, "png": pth, "xhot": round(hx / 32 * size), "yhot": round(hy / 32 * size),
                           "delay": WAIT_DELAY if len(frames) > 1 else 0})
        xw.write_xcursor(os.path.join(xc_dir, name), xf)
        for a in aliases:
            os.symlink(name, os.path.join(xc_dir, a))

    # --- hyprcursor-util ---
    hout = os.path.join(work, "hout")
    shutil.rmtree(hout, ignore_errors=True)
    os.makedirs(hout)
    p = subprocess.run(["hyprcursor-util", "--create", src, "--output", hout], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError("hyprcursor-util lỗi:\n" + p.stdout[-800:] + p.stderr[-800:])
    built = [os.path.join(hout, x) for x in os.listdir(hout)]
    if len(built) != 1:
        raise RuntimeError(f"hyprcursor-util không ra đúng 1 theme: {built}")

    # --- gom vào thư mục theme ---
    out = os.path.expanduser(out)
    if os.path.basename(out.rstrip("/")) != THEME:
        raise SystemExit(f"--out phải kết thúc bằng /{THEME} (để xóa an toàn)")
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(built[0], out, symlinks=True)
    shutil.copytree(xc_dir, os.path.join(out, "cursors"), symlinks=True)
    with open(os.path.join(out, "index.theme"), "w") as f:
        f.write(f"[Icon Theme]\nName={THEME}\nComment=Con trỏ Kafka (tím than, viền hồng, mạng nhện)\nInherits=Adwaita\n")
    if preview:
        make_preview(S, pngdir, preview)
    if not keep_build:
        shutil.rmtree(work, ignore_errors=True)
    print(f"Đã dựng {THEME}: {len(S)} hình, {sum(len(a) for _b, _h, a in S.values())} tên phụ → {out}")


def make_preview(S, pngdir, path):
    """Bảng xem trước: mọi hình ở cỡ 64 trên nền tối và nền sáng."""
    files = [os.path.join(pngdir, f"{n}-64-00.png") for n in S]
    for bg, suf in (("#241a2c", "dark"), ("#efe6f2", "light")):
        subprocess.run(["magick", "montage", *files, "-tile", "9x", "-geometry", "64x64+10+10",
                        "-background", bg, f"{path}.{suf}.png"], check=True)
    subprocess.run(["magick", f"{path}.dark.png", f"{path}.light.png", "-append", path], check=True)


def main(argv):
    out = f"~/.local/share/icons/{THEME}"
    keep = preview = None
    it = iter(argv)
    for a in it:
        if a == "--out":
            out = next(it)
        elif a == "--keep-build":
            keep = next(it)
        elif a == "--preview":
            preview = next(it)
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
    build(out, keep, preview)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
