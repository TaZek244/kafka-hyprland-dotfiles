#!/usr/bin/env python3
"""hud.py — HUD kiểu game RPG cho thanh trên ở theme pixel (waybar/topbar-pixel.jsonc).

Vẽ 2 ảnh PNG cho module `image` của Waybar (Waybar không vẽ được thanh máu, nên tự vẽ bằng cairo):
  player.png : THẺ NHÂN VẬT: chân dung Kafka trong khung hồng, tên người chơi (PLAYER_NAME, mặc định TaZek) + huy hiệu LV vàng,
               vạch EXP, HP (tim) và MP (giọt) là thanh liền + số FiraCode đậm.
               LV = số giờ máy đã chạy + 1, EXP = phút trong giờ hiện tại (đầy là lên cấp),
               HP = pin (đang sạc thì có dấu +, ≤ 20% thì nhấp nháy), MP = ổ đĩa / còn trống.
  stats.png  : bảng chỉ số 2 hàng: CPU | RAM (đã dùng), TMP (coretemp 30..100 °C) | NET ↓↑ (/proc/net/dev).
Mỗi ảnh kèm file .txt (dòng 1 = đường dẫn ảnh, dòng 2 = tooltip) mà module image đọc bằng `cat`.

  hud.py daemon     chạy nền (1 bản, flock), cập nhật mỗi 2s, đổi ảnh thì `pkill -RTMIN+18 waybar`;
                    tự thoát khi theme không còn là pixel (ui-theme.sh bật/tắt nó)
  hud.py once       vẽ một lần (không báo Waybar)
  hud.py --preview OUT.png   vẽ bảng xem trước phóng 4× (dữ liệu mẫu)
  hud.py --selftest

Tên = font pixel 5×7 của trình đăng nhập (greetd/kafka-greeter/pixelfont.py) phóng 2×; số/nhãn = FiraCode Nerd Font đậm
qua PangoCairo (font pixel 7px khó đọc), icon Nerd tô màu thay chữ CPU/TMP. Khung/thanh vẽ ô vuông, không khử răng cưa.
Chân dung cắt từ wallpapers/Kafka_thumbail.jpg (cùng khung FACE_CROP với bộ con trỏ); thiếu ảnh thì vẽ nhện pixel.
"""

import fcntl
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "greetd", "kafka-greeter"))
import pixelfont as pf  # noqa: E402

RUN = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
OUT = os.path.join(RUN, "kafka-hud")
STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "kafka", "ui-theme")
FACE_SRC = os.path.join(REPO, "wallpapers", "Kafka_thumbail.jpg")
FACE_CROP = (240, 100, 280, 280)  # x, y, w, h trên ảnh 736×736: sát mặt (ở 30px khung rộng hơn chỉ thấy tóc)
SIGNAL = 18
# Tên trên thẻ nhân vật (Kafka chỉ là chân dung/nền): đổi bằng biến môi trường KAFKA_HUD_NAME
PLAYER_NAME = os.environ.get("KAFKA_HUD_NAME") or "TaZek"
INTERVAL = 2.0


def rgb(h, a=1.0):
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)


EDGE, TEXT, DIM, FAINT = rgb("#140e1a"), rgb("#fbf7fd"), rgb("#d4cade"), rgb("#9a8bab")
SHADOW = rgb("#0b0710", 0.9)
PINK, PINK_HI, PINK_SH, PINK_EDGE = rgb("#c94785"), rgb("#f08cbb"), rgb("#962f62"), rgb("#3d1028")
GOLD, GOLD_SH = rgb("#ffe08a"), rgb("#b8862e")
TRACK = rgb("#1a1422")
# thanh: (màu chính, mép sáng, mép tối, màu nhãn)
BARS = {
    "HP": (rgb("#e0506e"), rgb("#ff9aae"), rgb("#a8344c"), rgb("#ff9aae")),
    "HP_LOW": (rgb("#ff3b5c"), rgb("#ffc2cc"), rgb("#b0203c"), rgb("#ff6b82")),
    "MP": (rgb("#7d6cf0"), rgb("#b3a8ff"), rgb("#4f40b8"), rgb("#b3a8ff")),
    "CPU": (rgb("#f2c14e"), rgb("#ffe08a"), rgb("#b8862e"), rgb("#ffe08a")),
    "TMP": (rgb("#f0884f"), rgb("#ffb98a"), rgb("#b4562a"), rgb("#ffb98a")),
    "TMP_HOT": (rgb("#e0506e"), rgb("#ff9aae"), rgb("#a8344c"), rgb("#ff9aae")),
    "RAM": (rgb("#7d6cf0"), rgb("#b3a8ff"), rgb("#4f40b8"), rgb("#b3a8ff")),
}
NET_DOWN, NET_UP = rgb("#7fd6c2"), rgb("#f08cbb")


# ------------------------------------------------------------------ đọc số liệu hệ thống
def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def battery():
    """(phần trăm, đang sạc) hoặc (None, False) nếu không có pin."""
    base = "/sys/class/power_supply"
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return None, False
    for n in names:
        if read(f"{base}/{n}/type") == "Battery":
            cap = read(f"{base}/{n}/capacity")
            st = read(f"{base}/{n}/status")
            if cap.isdigit():
                return int(cap), st in ("Charging", "Full")
    return None, False


def mem_free_pct():
    info = {}
    for line in read("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        info[k] = int(v.split()[0]) if v.split() else 0
    tot = info.get("MemTotal", 0)
    return (100.0 * info.get("MemAvailable", 0) / tot) if tot else 0.0, tot, info.get("MemAvailable", 0)


_cpu_prev = None


def cpu_pct():
    global _cpu_prev
    parts = read("/proc/stat").splitlines()[0].split()[1:]
    vals = [int(x) for x in parts]
    idle, total = vals[3] + (vals[4] if len(vals) > 4 else 0), sum(vals)
    prev, _cpu_prev = _cpu_prev, (idle, total)
    if not prev or total == prev[1]:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (1 - (idle - prev[0]) / (total - prev[1]))))


def temp_c():
    base = "/sys/class/hwmon"
    try:
        for h in sorted(os.listdir(base)):
            if read(f"{base}/{h}/name") == "coretemp":
                v = read(f"{base}/{h}/temp1_input")
                return int(v) / 1000 if v.isdigit() else None
    except OSError:
        pass
    return None


_net_prev = None


def net_rate():
    """(xuống, lên) byte/giây, cộng mọi giao diện trừ lo; lần đầu trả (0, 0)."""
    global _net_prev
    rx = tx = 0
    for line in read("/proc/net/dev").splitlines()[2:]:
        name, _, rest = line.partition(":")
        if name.strip() == "lo" or not rest.split():
            continue
        f = rest.split()
        rx += int(f[0])
        tx += int(f[8])
    now = time.monotonic()
    prev, _net_prev = _net_prev, (now, rx, tx)
    if not prev or now <= prev[0]:
        return 0.0, 0.0
    dt = now - prev[0]
    return max(0.0, (rx - prev[1]) / dt), max(0.0, (tx - prev[2]) / dt)


def human_rate(b):
    """Tốc độ gọn 4 ký tự: 0B, 999B, 12K, 1.2M, 12M, 1.2G."""
    for unit, k in (("G", 1e9), ("M", 1e6), ("K", 1e3)):
        if b >= k:
            v = b / k
            return (f"{v:.1f}" if v < 10 else f"{v:.0f}") + unit
    return f"{int(b)}B"


def uptime_s():
    try:
        return float(read("/proc/uptime").split()[0])
    except (ValueError, IndexError):
        return 0.0


def disk_free_pct(path="/"):
    import shutil

    try:
        u = shutil.disk_usage(path)
        return 100.0 * u.free / u.total, u.free, u.total
    except OSError:
        return 0.0, 0, 0


def sample():
    up = uptime_s()
    disk, dfree, dtot = disk_free_pct()
    bat, charging = battery()
    free, tot, avail = mem_free_pct()
    return {
        "uptime": up,
        "lv": int(up // 3600) + 1,
        "exp": (up % 3600) / 3600,
        "bat": bat,
        "charging": charging,
        "mp": free,
        "mem_tot": tot,
        "mem_avail": avail,
        "disk": disk,
        "disk_free": dfree,
        "disk_tot": dtot,
        "cpu": cpu_pct(),
        "temp": temp_c(),
        "net": net_rate(),
    }


# ------------------------------------------------------------------ vẽ
def fill(ctx, col, x, y, w, h):
    ctx.set_source_rgba(*col)
    ctx.rectangle(x, y, w, h)
    ctx.fill()


def text(ctx, s, x, y, cell, col, shadow=SHADOW, keep_case=False):
    pf.draw_text(ctx, s, x, y, cell, col, shadow, keep_case=keep_case)
    return x + pf.text_width(s, cell)


_portrait = None


def portrait(size):
    """Chân dung size×size (cairo surface) từ ảnh Kafka, cache; None nếu không có ảnh."""
    global _portrait
    if _portrait is not None:
        return _portrait or None
    _portrait = False
    try:
        import gi

        gi.require_version("GdkPixbuf", "2.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, GdkPixbuf
        import cairo

        pb = GdkPixbuf.Pixbuf.new_from_file(FACE_SRC)
        x, y, w, h = FACE_CROP
        sx = pb.get_width() / 736
        pb = pb.new_subpixbuf(int(x * sx), int(y * sx), int(w * sx), int(h * sx))
        pb = pb.scale_simple(size, size, GdkPixbuf.InterpType.HYPER)
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        c = cairo.Context(surf)
        Gdk.cairo_set_source_pixbuf(c, pb, 0, 0)
        c.paint()
        _portrait = surf
    except Exception:
        _portrait = False
    return _portrait or None


def portrait_frame(ctx, x, y, s):
    """Khung chân dung s×s trên lưới 2px: góc bậc thang, viền tối, mép hồng sáng/tối, ảnh bên trong."""
    fill(ctx, PINK_EDGE, x + 2, y, s - 4, s)  # viền tối, cắt góc 2px
    fill(ctx, PINK_EDGE, x, y + 2, s, s - 4)
    fill(ctx, PINK_HI, x + 2, y + 2, s - 4, s - 4)  # mép sáng trên-trái
    fill(ctx, PINK_SH, x + 4, y + 4, s - 6, s - 6)  # mép tối dưới-phải
    inner = s - 8
    p = portrait(inner)
    if p is not None:
        ctx.set_source_surface(p, x + 4, y + 4)
        ctx.paint()
    else:
        fill(ctx, rgb("#2a2034"), x + 4, y + 4, inner, inner)
        pf.draw_icon(ctx, "spider", x + 4 + (inner - 18) // 2, y + 4 + (inner - 18) // 2, 2, PINK_HI)


def seg_bar(ctx, x, y, frac, kind, n=10, sw=8, h=8, blink=False):
    """Thanh dạng ô: viền 1px tối, n ô rộng sw cách 1px; ô cuối điền theo phần lẻ. Trả về x cuối."""
    col, hi, sh, _ = BARS[kind]
    w = n * sw + (n - 1) + 2
    fill(ctx, EDGE, x, y, w, h)
    frac = max(0.0, min(1.0, frac))
    filled = frac * n
    for i in range(n):
        sx = x + 1 + i * (sw + 1)
        fill(ctx, TRACK, sx, y + 1, sw, h - 2)
        part = max(0.0, min(1.0, filled - i))
        if part <= 0 or blink:
            continue
        pw = max(2, int(round(part * sw / 2)) * 2) if part < 1 else sw
        fill(ctx, col, sx, y + 1, pw, h - 2)
        fill(ctx, hi, sx, y + 1, pw, 1)
        fill(ctx, sh, sx, y + h - 2, pw, 1)
    return x + w


PLAYER_W, PLAYER_H = 196, 34  # cao 34: nằm gọn trong thanh 40 (module image tự cộng 2px + lề 2+2)
STATS_W, STATS_H = 190, 34  # 2 hàng 16px: CPU | RAM, TMP | NET — rộng CỐ ĐỊNH (số canh phải trong ô cố định)

# Chữ số/nhãn: FiraCode Nerd Font ĐẬM qua Pango (dễ đọc hơn font pixel 7px — người dùng 2026-11-22: "khó nhìn");
# font pixel chỉ còn cho TÊN người chơi (cỡ 14px, 2px/điểm).
FONT = "FiraCode Nerd Font"
ICON_HP, ICON_MP = "\U000f02d1", "\U000f058c"  # tim, giọt (MP = ổ đĩa trống)
ICON_CPU, ICON_RAM, ICON_TMP = "\U000f035b", "\U000f061a", "\U000f050f"
ICON_DOWN, ICON_UP = "\U000f0045", "\U000f005d"


def ftext(ctx, s, x, y, px, col, bold=True, align="left", width=None, shadow=True, vcenter=None):
    """Chữ FiraCode cỡ px (tuyệt đối), y = mép trên dòng; align left/right/center trong `width`. Trả về x cuối."""
    import gi

    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo
    import cairo

    lay = PangoCairo.create_layout(ctx)
    fo = cairo.FontOptions()
    fo.set_antialias(cairo.ANTIALIAS_GRAY)
    fo.set_hint_style(cairo.HINT_STYLE_FULL)
    fo.set_hint_metrics(cairo.HINT_METRICS_ON)
    PangoCairo.context_set_font_options(lay.get_context(), fo)
    fd = Pango.FontDescription.from_string(FONT)
    fd.set_absolute_size(px * Pango.SCALE)
    fd.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
    lay.set_font_description(fd)
    lay.set_text(s, -1)
    ink, log = lay.get_pixel_extents()
    w = log.width
    if vcenter is not None:  # canh giữa theo NÉT chữ thật trong khung cao vcenter
        y = y + (vcenter - ink.height) // 2 - ink.y
    if width is not None and align == "right":
        x = x + width - w
    elif width is not None and align == "center":
        x = x + (width - w) // 2
    if shadow:
        ctx.set_source_rgba(*SHADOW)
        ctx.move_to(x + 1, y + 1)
        PangoCairo.show_layout(ctx, lay)
    ctx.set_source_rgba(*col)
    ctx.move_to(x, y)
    PangoCairo.show_layout(ctx, lay)
    return x + w


def bar(ctx, x, y, w, h, frac, kind, blink=False):
    """Thanh liền kiểu game: viền tối 1px, rãnh tối, phần đầy có mép sáng trên + mép tối dưới,
    vạch chia mờ mỗi 1/4 (đọc nhanh mức). Trả về x cuối."""
    col, hi, sh, _ = BARS[kind]
    fill(ctx, EDGE, x, y, w, h)
    fill(ctx, TRACK, x + 1, y + 1, w - 2, h - 2)
    frac = max(0.0, min(1.0, frac))
    fw = int(round((w - 2) * frac))
    if fw and not blink:
        fill(ctx, col, x + 1, y + 1, fw, h - 2)
        fill(ctx, hi, x + 1, y + 1, fw, 1)
        fill(ctx, sh, x + 1, y + h - 2, fw, 1)
    for q in (1, 2, 3):
        fill(ctx, rgb("#0b0710", 0.55), x + 1 + (w - 2) * q // 4, y + 1, 1, h - 2)
    return x + w


def badge(ctx, x, y, w, h, bg, edge, hi):
    """Huy hiệu góc bậc thang 1px: viền tối, nền, mép sáng trên."""
    fill(ctx, edge, x + 1, y, w - 2, h)
    fill(ctx, edge, x, y + 1, w, h - 2)
    fill(ctx, bg, x + 1, y + 1, w - 2, h - 2)
    fill(ctx, hi, x + 2, y + 1, w - 4, 1)


def draw_player(d, tick=0):
    """[chân dung] TaZek            [LV 4]
    ━━━━━━━ EXP ━━━━━━━━━━━━━━
    ♥ ▰▰▰▰▰▱ 85   ● ▰▰▰▱▱▱ 57      (HP = pin, MP = ổ đĩa trống)"""
    import cairo

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, PLAYER_W, PLAYER_H)
    ctx = cairo.Context(surf)
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    portrait_frame(ctx, 0, 0, PLAYER_H)
    x0 = PLAYER_H + 6
    # tên (font pixel 2px/điểm, giữ hoa/thường)
    text(ctx, PLAYER_NAME[:9], x0, 1, 2, TEXT, keep_case=True)
    # huy hiệu LV vàng ở mép phải
    lv = f"LV {min(d['lv'], 999)}"
    bw = 10 + 7 * len(lv)
    bx = PLAYER_W - bw - 1
    by, bh = 4, 12  # hạ xuống: giữa huy hiệu = giữa chữ tên (y 1..15), không sát mép thanh
    badge(ctx, bx, by, bw, bh, GOLD, rgb("#5a3d10"), rgb("#fff3c4"))
    ftext(ctx, lv, bx, by, 10, rgb("#3a2408"), align="center", width=bw, shadow=False, vcenter=bh)
    # EXP: vạch vàng mảnh dưới tên
    ew = PLAYER_W - x0 - 1
    fill(ctx, EDGE, x0, 17, ew, 3)
    fill(ctx, TRACK, x0 + 1, 18, ew - 2, 1)
    xw = int((ew - 2) * d["exp"])
    if xw:
        fill(ctx, GOLD, x0 + 1, 18, xw, 1)
    # HP | MP
    bat = d["bat"]
    low = bat is not None and bat <= 20 and not d["charging"]
    kind = "HP_LOW" if low else "HP"
    half = (PLAYER_W - x0) // 2
    for i, (icon, k, frac, val, blink) in enumerate(
        (
            (
                ICON_HP,
                kind,
                (bat if bat is not None else 100) / 100,
                "AC" if bat is None else f"{bat}{'+' if d['charging'] else ''}",
                low and tick % 2 == 1,
            ),
            (ICON_MP, "MP", d.get("disk", d["mp"]) / 100, f"{int(round(d.get('disk', d['mp'])))}", False),
        )
    ):
        cx = x0 + i * half
        ftext(ctx, icon, cx, 21, 11, BARS[k][3], bold=False)
        bw = half - 13 - 37  # icon 13 · thanh · số 29 ("100+") · khoảng cách tới ô sau
        bar(ctx, cx + 13, 24, bw, 7, frac, k, blink)
        ftext(ctx, val, cx + 13 + bw + 2, 20, 11, TEXT if not low or i else BARS[k][3], align="right", width=29)
    return surf


def stat_cell(ctx, x, y, icon, kind, frac, value, value_col=TEXT):
    """Một ô chỉ số rộng 88: icon màu · thanh 44px · số canh phải sát thanh (rộng cố định → không giật)."""
    ftext(ctx, icon, x, y + 1, 12, BARS[kind][3], bold=False)
    bar(ctx, x + 16, y + 5, 44, 7, frac, kind)
    ftext(ctx, value, x + 61, y, 12, value_col, align="right", width=28)


def draw_stats(d):
    """CPU ▰▰▱ 12%  │ RAM ▰▰▰ 43%
    TMP ▰▰▱ 52°  │ ↓ 1.2M  ↑ 14K"""
    import cairo

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, STATS_W, STATS_H)
    ctx = cairo.Context(surf)
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    col2 = 100
    fill(ctx, rgb("#4a3c59", 0.7), col2 - 6, 3, 1, STATS_H - 6)  # vạch chia cột
    fill(ctx, rgb("#0b0710", 0.6), col2 - 5, 3, 1, STATS_H - 6)
    cpu = d["cpu"]
    stat_cell(ctx, 0, 1, ICON_CPU, "CPU", cpu / 100, f"{int(round(cpu))}%")
    ram = 100 - d["mp"]
    stat_cell(ctx, col2, 1, ICON_RAM, "RAM", ram / 100, f"{int(round(ram))}%")
    t = d["temp"]
    hot = t is not None and t >= 85
    kind = "TMP_HOT" if hot else "TMP"
    stat_cell(
        ctx,
        0,
        18,
        ICON_TMP,
        kind,
        ((t or 30) - 30) / 70,
        "--" if t is None else f"{int(round(t))}°",
        TEXT if not hot else BARS[kind][3],
    )
    down, up = d.get("net", (0.0, 0.0))
    ftext(ctx, ICON_DOWN, col2 + 1, 19, 11, NET_DOWN, bold=False)
    ftext(ctx, human_rate(down), col2 + 10, 18, 12, TEXT, align="right", width=32)
    ftext(ctx, ICON_UP, col2 + 50, 19, 11, NET_UP, bold=False)
    ftext(ctx, human_rate(up), col2 + 58, 18, 12, TEXT, align="right", width=32)
    return surf


def tooltips(d):
    h, m = int(d["uptime"] // 3600), int(d["uptime"] % 3600 // 60)
    bat = "không có pin" if d["bat"] is None else f"{d['bat']}%" + (" (đang sạc)" if d["charging"] else "")
    # Module image chỉ đọc MỘT dòng tooltip (dòng 2 của file) và không hiểu "\\n" → ngăn bằng " · "/" ┃ "
    player = (
        f"{PLAYER_NAME} · LV {d['lv']}: máy đã chạy {h} giờ {m} phút (EXP đầy = lên cấp mỗi giờ) ┃ "
        f"HP = pin {bat} ┃ MP = ổ đĩa trống {d.get('disk_free', 0) / 1e9:.0f}/{d.get('disk_tot', 0) / 1e9:.0f} GB ┃ "
        f"Bấm: mở ứng dụng · Chuột phải: cuộn ⇄ Desktop"
    )
    t = "?" if d["temp"] is None else f"{d['temp']:.0f} °C"
    down, up = d.get("net", (0.0, 0.0))
    stats = (
        f"CPU {d['cpu']:.0f}% · RAM {100 - d['mp']:.0f}% · nhiệt độ {t} ┃ "
        f"Mạng ↓ {human_rate(down)}/s ↑ {human_rate(up)}/s ┃ Bấm: btop · Chuột phải: bảng Wi-Fi"
    )
    return player, stats


def write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def png_bytes(surf):
    import io

    b = io.BytesIO()
    surf.write_to_png(b)
    return b.getvalue()


_last = {}


def render(d, tick=0):
    """Ghi ảnh + tooltip; trả về True nếu có gì đổi."""
    os.makedirs(OUT, exist_ok=True)
    tp, ts = tooltips(d)
    changed = False
    for name, surf, tip in (("player", draw_player(d, tick), tp), ("stats", draw_stats(d), ts)):
        data = png_bytes(surf)
        txt = f"{os.path.join(OUT, name + '.png')}\n{tip}\n".encode()
        if _last.get(name) != (data, txt):
            write_atomic(os.path.join(OUT, name + ".png"), data)
            write_atomic(os.path.join(OUT, name + ".txt"), txt)
            _last[name] = (data, txt)
            changed = True
    return changed


def is_pixel():
    return read(STATE) == "pixel"


def daemon():
    os.makedirs(OUT, exist_ok=True)
    lock = open(os.path.join(RUN, "kafka-hud.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("hud.py: đã có một bản đang chạy", file=sys.stderr)
        return 0
    with open(os.path.join(RUN, "kafka-hud.pid"), "w") as f:
        f.write(str(os.getpid()))
    cpu_pct()
    tick = 0
    while is_pixel():
        time.sleep(INTERVAL if tick else 0.3)
        if render(sample(), tick):
            subprocess.run(["pkill", f"-RTMIN+{SIGNAL}", "waybar"], stderr=subprocess.DEVNULL)
        tick += 1
    return 0


def preview(out):
    import cairo

    demo = [
        {
            "uptime": 3 * 3600 + 1500,
            "lv": 4,
            "exp": 0.42,
            "bat": 85,
            "charging": False,
            "mp": 57,
            "mem_tot": 16e6,
            "mem_avail": 9e6,
            "cpu": 12,
            "temp": 52,
            "net": (1.2e6, 14e3),
        },
        {
            "uptime": 41 * 3600,
            "lv": 42,
            "exp": 0.9,
            "bat": 64,
            "charging": True,
            "mp": 23,
            "mem_tot": 16e6,
            "mem_avail": 4e6,
            "cpu": 78,
            "temp": 91,
            "net": (25e6, 3.1e6),
        },
        {
            "uptime": 60,
            "lv": 1,
            "exp": 0.02,
            "bat": 14,
            "charging": False,
            "mp": 88,
            "mem_tot": 16e6,
            "mem_avail": 14e6,
            "cpu": 3,
            "temp": None,
            "net": (0, 512),
        },
    ]
    k, pad = 4, 6
    W = PLAYER_W + STATS_W + 3 * pad
    H = len(demo) * (PLAYER_H + pad) + pad
    big = cairo.ImageSurface(cairo.FORMAT_ARGB32, W * k, H * k)
    c = cairo.Context(big)
    c.set_source_rgb(0.15, 0.11, 0.19)
    c.paint()
    c.scale(k, k)
    for i, d in enumerate(demo):
        y = pad + i * (PLAYER_H + pad)
        for surf, x, yy in ((draw_player(d), pad, y), (draw_stats(d), 2 * pad + PLAYER_W, y)):
            c.set_source_surface(surf, x, yy)
            c.get_source().set_filter(cairo.FILTER_NEAREST)
            c.paint()
    big.write_to_png(out)
    print(out)


def selftest():
    import cairo  # noqa: F401

    d = {
        "uptime": 7300,
        "lv": 3,
        "exp": 0.03,
        "bat": None,
        "charging": False,
        "mp": 50,
        "mem_tot": 8e6,
        "mem_avail": 4e6,
        "cpu": 0,
        "temp": None,
    }
    assert draw_player(d).get_width() == PLAYER_W
    assert draw_stats(d).get_height() == STATS_H
    s = sample()
    assert s["lv"] >= 1 and 0 <= s["exp"] < 1 and 0 <= s["mp"] <= 100
    tp, ts = tooltips(d)
    assert "\n" not in tp and "\\n" not in tp and "không có pin" in tp  # tooltip đúng 1 dòng
    assert [human_rate(x) for x in (0, 999, 12345, 1.25e6, 34e6)] == ["0B", "999B", "12K", "1.2M", "34M"]
    print("hud.py selftest OK")
    return 0


def main(argv):
    if not argv or argv[0] == "daemon":
        return daemon()
    if argv[0] == "once":
        cpu_pct()
        time.sleep(0.3)
        render(sample())
        return 0
    if argv[0] == "--preview" and len(argv) > 1:
        preview(argv[1])
        return 0
    if argv[0] == "--selftest":
        return selftest()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
