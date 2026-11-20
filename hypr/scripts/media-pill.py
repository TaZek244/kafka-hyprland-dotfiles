#!/usr/bin/env python3
"""media-pill.py — ô "Đang phát" trên thanh trên, tự vẽ để bắt được rê chuột.

Waybar (0.16) không có sự kiện rê chuột cho module, Hyprland cũng không báo di chuột. Nên Waybar chỉ
giữ một ô trống rộng cố định (`custom/media-slot`, sau đồng hồ), còn script này vẽ đè đúng chỗ đó một
cửa sổ GTK3 layer-shell lớp OVERLAY (lớp top luôn nằm dưới Waybar) — cùng cách với corner-fillet.py.

  • Hiện: icon trạng thái, tên bài — ca sĩ (chữ dài thì chạy ngang), 4 vạch nhún nhảy khi đang phát.
  • Rê chuột: bật sóng nhạc nổi trên màn hình (cava-wallpaper.py --overlay), rời chuột thì tắt
    (trừ khi bạn đã tự bật bằng Super + Shift + A).
  • Bấm trái: popup "Đang phát" (media-popup.py: ảnh bìa, điều khiển, sóng nhạc, lời bài hát).
    Bấm phải: phát/dừng. Lăn: bài sau/trước.
  • Không có nhạc: ẩn ô và báo Waybar ẩn ô trống (file $XDG_RUNTIME_DIR/kafka-media-slot + signal 17).
  • Tự ẩn khi workspace có cửa sổ toàn màn hình thật.
Vị trí (SLOT_X…) đo bằng grim cho màn 1920 — đổi đồng hồ/độ rộng ô thì đo lại (xem CLAUDE.md).

Dùng: media-pill.py (chạy, 1 bản) · --stop · --selftest
"""

import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
PIDFILE = os.path.join(RUN, "kafka-media-pill.pid")
SLOT_FILE = os.path.join(RUN, "kafka-media-slot")
SLOT_SIGNAL = 17

PILL_W, PILL_H = 229, 26          # cỡ mặc định trước khi dò được; ô trống (min-width 240px) ra ~229x27 tại y = 6..32
TOP = 6                           # mép trên ô trống (bản phẳng)
PIXEL_TOP = 1                     # bản pixel: cụm cao từ y=1 (lề 1px) → viên thuốc cao bằng các cụm khác
SLOT_X_1920 = 998                 # vị trí đoán ban đầu; vị trí thật dò bằng vạch đánh dấu (xem dưới)
# Vị trí ô trống KHÔNG cố định: cụm trái (workspace, bản đồ cột, tốc độ mạng) dài ra thì GTK đẩy cụm giữa
# sang phải. Nên Waybar kẻ ở đáy ô trống một vạch 1px màu riêng MARKER (CSS #custom-media-slot border-bottom,
# hàng y = MARKER_Y, nằm ngay dưới viên thuốc nên không bị che) và script chụp đúng hàng đó mỗi 1.5s để tìm.
MARKER = (0x2d, 0x25, 0x35)
MARKER_Y = TOP + PILL_H           # = 32
CALIBRATE_MS = 1500


def find_marker(row_rgb, color=MARKER, min_run=40):
    """Hàng điểm ảnh (bytes RGB) → (x, độ dài) của đoạn liền màu color dài nhất (≥ min_run), hoặc None."""
    best, start = None, None
    n = len(row_rgb) // 3
    for x in range(n + 1):
        hit = x < n and tuple(row_rgb[3 * x:3 * x + 3]) == color
        if hit and start is None:
            start = x
        elif not hit and start is not None:
            if x - start >= min_run and (best is None or x - start > best[1]):
                best = (start, x - start)
            start = None
    return best
HOVER_DELAY_MS = 180              # rê vào bao lâu mới bật sóng (lướt qua thì thôi)
LEAVE_DELAY_MS = 450

TEXT = (0xfb / 255, 0xf7 / 255, 0xfd / 255)
DIM = (0xd4 / 255, 0xca / 255, 0xde / 255)
ACCENT = (0xe0 / 255, 0x55 / 255, 0x9a / 255)
UI_THEME_FILE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "kafka", "ui-theme")


def ui_theme():
    """"pixel" nếu đang dùng theme pixel (hypr/scripts/ui-theme.sh), còn lại "flat"."""
    try:
        return "pixel" if open(UI_THEME_FILE).read().strip() == "pixel" else "flat"
    except OSError:
        return "flat"


def parse_status_line(line):
    """'Playing\\tTên\\tCa sĩ' → dict; dòng rỗng/thiếu → trạng thái Stopped."""
    parts = (line.rstrip("\n").split("\t") + ["", "", ""])[:3]
    status, title, artist = (p.strip() for p in parts)
    if status not in ("Playing", "Paused"):
        status = "Stopped"
    return {"status": status, "title": title, "artist": artist}


def visible_for(info):
    return info["status"] in ("Playing", "Paused") and bool(info["title"])


def label_for(info):
    return f"{info['title']} — {info['artist']}" if info["artist"] else info["title"]


def write_slot(on):
    try:
        with open(SLOT_FILE, "w") as f:
            f.write("on\n" if on else "off\n")
    except OSError:
        pass
    subprocess.Popen(["pkill", f"-RTMIN+{SLOT_SIGNAL}", "waybar"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS: " if cond else "FAIL: ") + name)
        ok = ok and cond
    i = parse_status_line("Playing\tSài Gòn Hôm Nay Mưa\tJSOL, Hoàng Duyên\n")
    check("parse playing", i == {"status": "Playing", "title": "Sài Gòn Hôm Nay Mưa", "artist": "JSOL, Hoàng Duyên"})
    check("label có ca sĩ", label_for(i) == "Sài Gòn Hôm Nay Mưa — JSOL, Hoàng Duyên")
    check("hiện khi phát", visible_for(i))
    check("dòng rỗng = Stopped", parse_status_line("")["status"] == "Stopped")
    check("ẩn khi dừng", not visible_for(parse_status_line("Stopped\tx\ty")))
    check("ẩn khi không có tên (Chromium chưa phát)", not visible_for(parse_status_line("Paused\t\t")))
    row = bytes([1, 2, 3] * 10) + bytes(MARKER) * 50 + bytes([0, 0, 0] * 5) + bytes(MARKER) * 60 + bytes([9, 9, 9])
    check("dò vạch đánh dấu: lấy đoạn dài nhất", find_marker(row) == (65, 60))
    check("dò vạch: không có → None", find_marker(bytes([1, 2, 3] * 100)) is None)
    check("label không ca sĩ", label_for(parse_status_line("Paused\tBài\t")) == "Bài")
    return 0 if ok else 1


def read_pid():
    try:
        pid = int(open(PIDFILE).read().strip())
        os.kill(pid, 0)
        if b"media-pill" in open(f"/proc/{pid}/cmdline", "rb").read():
            return pid
    except (OSError, ValueError):
        pass
    return None


def main():
    if "--selftest" in sys.argv:
        return selftest()
    if "--stop" in sys.argv:
        pid = read_pid()
        if pid:
            os.kill(pid, signal.SIGTERM)
        return 0
    if read_pid():
        print("media-pill.py đã chạy", file=sys.stderr)
        return 0
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    try:
        return run()
    finally:
        try:
            if open(PIDFILE).read().strip() == str(os.getpid()):
                os.unlink(PIDFILE)
        except OSError:
            pass
        write_slot(False)


def run():
    import math
    import threading
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Gtk, Gdk, GLib, GtkLayerShell, Pango, PangoCairo
    import cairo

    sys.path.insert(0, HERE)
    import importlib.util
    spec = importlib.util.spec_from_file_location("corner_fillet", os.path.join(HERE, "corner-fillet.py"))
    cf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cf)            # dùng lại co_fullscreen_that / theo_doi_fullscreen

    class Pill(Gtk.Window):
        def __init__(self):
            super().__init__()
            self.info = {"status": "Stopped", "title": "", "artist": ""}
            self.hover = False
            self.hover_k = 0.0
            self.scroll_x = 0.0
            self.hover_proc = None
            self._hover_src = None
            self._leave_src = None
            self.fullscreen = False
            self.slot = None              # (x, rộng) của ô trống Waybar, dò bằng vạch đánh dấu
            self.pixel = ui_theme() == "pixel"
            self.pw = PILL_W
            self.ph = PILL_H
            self._cal_busy = False
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_namespace(self, "kafka-media-pill")
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_exclusive_zone(self, -1)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
            screen = self.get_screen()
            visual = screen.get_rgba_visual()
            if visual:
                self.set_visual(visual)
            self.set_app_paintable(True)
            self.set_size_request(PILL_W, PILL_H)
            self.top = PIXEL_TOP if self.pixel else TOP
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, self.top)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, self.slot_x())
            self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
                            | Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.SCROLL_MASK
                            | Gdk.EventMask.SMOOTH_SCROLL_MASK)
            self.connect("draw", self.on_draw)
            self.connect("enter-notify-event", self.on_enter)
            self.connect("leave-notify-event", self.on_leave)
            self.connect("button-press-event", self.on_button)
            self.connect("scroll-event", self.on_scroll)
            self._anim = GLib.timeout_add(50, self.tick)   # chạy chữ + vạch nhún (20 khung/giây)
            GLib.timeout_add(CALIBRATE_MS, self.calibrate)

        def slot_x(self):
            if self.slot is not None:
                return self.slot[0]
            disp = Gdk.Display.get_default()
            mon = disp.get_monitor(0)
            w = mon.get_geometry().width if mon else 1920
            return int(SLOT_X_1920 + (w - 1920) / 2)

        # ---- dò vị trí ô trống của Waybar ----
        def calibrate(self):
            if visible_for(self.info) and not self.fullscreen and not self._cal_busy:
                self._cal_busy = True
                threading.Thread(target=self._cal_worker, daemon=True).start()
            return True

        def _cal_worker(self):
            res = None
            try:
                mon = Gdk.Display.get_default().get_monitor(0)
                sw = mon.get_geometry().width if mon else 1920
                y0 = MARKER_Y - 4            # vạch ở y=32 (bản phẳng) hoặc 31 (bản pixel: thanh có viền đáy 2px)
                rows = 12                    # tới y=39: bản pixel đặt vạch ở y=37 (ô trống cao bằng cụm)
                out = subprocess.run(["grim", "-g", f"0,{y0} {sw}x{rows}", "-t", "ppm", "-"],
                                     capture_output=True, timeout=3).stdout
                # PPM: "P6\n<w> <h>\n255\n" + RGB, hàng nối tiếp
                parts = out.split(b"\n", 3)
                if len(parts) == 4 and parts[0] == b"P6":
                    data = parts[3]
                    for r in range(rows - 1, -1, -1):          # lấy hàng thấp nhất có vạch
                        m = find_marker(data[r * sw * 3:(r + 1) * sw * 3])
                        if m:
                            res = (m[0], m[1], y0 + r)
                            break
            except Exception:
                res = None
            GLib.idle_add(self._apply_slot, res)

        def _apply_slot(self, res):
            self._cal_busy = False
            if res != self.slot:
                self.slot = res
                if res:
                    GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, res[0])
                    self.pw = res[1]
                    self.ph = max(16, res[2] - self.top)     # viên thuốc phủ từ mép trên tới ngay trên vạch
                    self.set_size_request(self.pw, self.ph)
                    self.resize(self.pw, self.ph)
                self.update_visible()
                self.queue_draw()
            return False

        # ---- dữ liệu ----
        def set_info(self, info):
            changed = info != self.info
            was = visible_for(self.info)
            self.info = info
            vis = visible_for(info)
            if vis != was:
                write_slot(vis)
                if vis:
                    GLib.timeout_add(400, lambda: (self.calibrate(), False)[1])
            self.update_visible()
            if changed:
                self.scroll_x = 0.0
                self.queue_draw()
            return False

        def update_visible(self):
            # chỉ hiện khi đã thấy ô trống của Waybar (chưa dò được = có thể đè lên module khác)
            if visible_for(self.info) and not self.fullscreen and self.slot is not None:
                self.show_all()
            else:
                self.stop_hover_fx()
                self.hide()

        # ---- vẽ ----
        def tick(self):
            if self.get_visible():
                self.scroll_x += 1.2
                target = 1.0 if self.hover else 0.0
                self.hover_k += (target - self.hover_k) * 0.35   # ~200ms chuyển mượt
                self.queue_draw()
            return True

        def on_draw(self, _w, ctx):
            ctx.set_operator(cairo.OPERATOR_SOURCE)
            ctx.set_source_rgba(0, 0, 0, 0)
            ctx.paint()
            if self.pixel:
                ctx.set_operator(cairo.OPERATOR_OVER)
                return self.draw_pixel(ctx)
            ctx.set_operator(cairo.OPERATOR_OVER)
            w, h = self.pw, self.ph
            r = h / 2.0                                   # bo tròn hẳn hai đầu (viên thuốc mềm)

            def pill_path(inset=0.0):
                rr = r - inset
                ctx.new_sub_path()
                ctx.arc(w - r, r, rr, -math.pi / 2, math.pi / 2)
                ctx.arc(r, r, rr, math.pi / 2, 3 * math.pi / 2)
                ctx.close_path()

            hv = self.hover_k                              # 0..1, đổi mượt khi rê chuột
            # nền kính: gradient chéo trắng mờ + ánh hồng→tím tăng dần khi rê chuột
            pill_path()
            g = cairo.LinearGradient(0, 0, w, h)
            g.add_color_stop_rgba(0.0, 1, 1, 1, 0.10 + 0.06 * hv)
            g.add_color_stop_rgba(1.0, 1, 1, 1, 0.04 + 0.04 * hv)
            ctx.set_source(g)
            ctx.fill()
            if hv > 0.01:
                pill_path()
                g2 = cairo.LinearGradient(0, 0, w, 0)
                g2.add_color_stop_rgba(0.0, *ACCENT, 0.30 * hv)
                g2.add_color_stop_rgba(1.0, 0xa9 / 255, 0x5e / 255, 0xe8 / 255, 0.16 * hv)
                ctx.set_source(g2)
                ctx.fill()
            # vệt sáng mép trên (như mặt kính) + viền mảnh
            pill_path(0.5)
            edge = cairo.LinearGradient(0, 0, 0, h)
            edge.add_color_stop_rgba(0.0, 1, 1, 1, 0.26 + 0.14 * hv)
            edge.add_color_stop_rgba(0.5, 1, 1, 1, 0.06)
            edge.add_color_stop_rgba(1.0, 1, 1, 1, 0.10 + 0.08 * hv)
            ctx.set_source(edge)
            ctx.set_line_width(1)
            ctx.stroke()
            playing = self.info["status"] == "Playing"
            # 4 vạch nhún nhảy (giả lập, không tốn cava) — dừng thì đứng yên thấp
            t = time.monotonic()
            for i in range(4):
                amp = (0.35 + 0.65 * abs(math.sin(t * (3.1 + i * 0.9) + i * 1.3))) if playing else 0.25
                bh = 4 + amp * 12
                x = 14 + i * 4.6
                y0 = h / 2 + 8 - bh
                gb = cairo.LinearGradient(0, y0, 0, y0 + bh)
                gb.add_color_stop_rgb(0.0, 0xf0 / 255, 0x6a / 255, 0xab / 255)
                gb.add_color_stop_rgb(1.0, 0xa9 / 255, 0x5e / 255, 0xe8 / 255)
                ctx.set_source(gb)
                ctx.set_line_width(2.8)
                ctx.set_line_cap(cairo.LINE_CAP_ROUND)
                ctx.move_to(x + 1.4, y0 + 1.4)
                ctx.line_to(x + 1.4, y0 + bh - 1.4)
                ctx.stroke()
            # chữ chạy ngang
            layout = PangoCairo.create_layout(ctx)
            layout.set_font_description(Pango.FontDescription("Sans 10.5"))
            text = label_for(self.info)
            layout.set_markup(f"<i>{GLib.markup_escape_text(text)}</i>" if not playing
                              else GLib.markup_escape_text(text), -1)
            tw, th = layout.get_pixel_size()
            x0, avail = 40, w - 40 - 14
            ctx.save()
            ctx.rectangle(x0, 0, avail, h)
            ctx.clip()
            ctx.set_source_rgb(*(TEXT if (playing or self.hover) else DIM))
            if tw <= avail:
                ctx.move_to(x0, (h - th) / 2)
                PangoCairo.show_layout(ctx, layout)
            else:
                gap = 48
                off = self.scroll_x % (tw + gap)
                for k in (0, 1):
                    ctx.move_to(x0 - off + k * (tw + gap), (h - th) / 2)
                    PangoCairo.show_layout(ctx, layout)
            ctx.restore()
            return True

        def draw_pixel(self, ctx):
            """Kiểu pixel "KAFKA.SYS" (theme pixel): khung lấy đúng ảnh 9-slice lưới ô của Waybar
            (waybar/pixel/px*.png, cắt 6 8 8 6: ô thường / rê chuột), vạch nhún dạng khối, chữ trắng có bóng
            cứng 2px, không khử răng cưa."""
            w, h, P = self.pw, self.ph, 2
            ctx.set_antialias(cairo.ANTIALIAS_NONE)
            dark, white = (0x14 / 255, 0x0e / 255, 0x1a / 255), (1, 1, 1)
            self._nine(ctx, "px-hover.png" if self.hover_k > 0.5 else "px.png", w, h)

            def rect(x, y, rw, rh, col):
                ctx.set_source_rgb(*col)
                ctx.rectangle(x, y, rw, rh)
                ctx.fill()
            # vạch nhún: 4 cột khối 2px, nấc 2px
            playing = self.info["status"] == "Playing"
            t = time.monotonic()
            for i in range(4):
                amp = (0.35 + 0.65 * abs(math.sin(t * (3.1 + i * 0.9) + i * 1.3))) if playing else 0.25
                bh = min(h - 15, int(1 + amp * 8) * P)          # nằm trong khung (trên 6, dưới 8+1)
                x = 10 + i * 6
                rect(x + 2, h - 9 - bh + 2, 4, bh, dark)        # bóng cứng 1 điểm (2px)
                rect(x, h - 9 - bh, 4, bh, (0xff / 255, 0x8c / 255, 0xc0 / 255) if i % 2 == 0 else (0xc9 / 255, 0x47 / 255, 0x85 / 255))
            # chữ
            layout = PangoCairo.create_layout(ctx)
            layout.set_font_description(Pango.FontDescription("FiraCode Nerd Font Bold 11"))
            text = label_for(self.info)
            layout.set_text(text, -1)
            tw, th = layout.get_pixel_size()
            x0, avail = 40, w - 40 - 4 * P
            ctx.save()
            ctx.rectangle(x0, 2, avail, h - 5)                  # rộng theo chiều dọc: đừng xén dấu tiếng Việt
            ctx.clip()
            ty = (h - 2 - th) // 2                               # khung dưới dày hơn trên 2px (bóng)
            offs = [0] if tw <= avail else [-(int(self.scroll_x) % (tw + 48)), -(int(self.scroll_x) % (tw + 48)) + tw + 48]
            for off in offs:
                ctx.set_source_rgb(*dark)
                ctx.move_to(x0 + off + 2, ty + 2)
                PangoCairo.show_layout(ctx, layout)
                ctx.set_source_rgb(*(white if (playing or self.hover) else (0xe6 / 255, 0xdc / 255, 0xf2 / 255)))
                ctx.move_to(x0 + off, ty)
                PangoCairo.show_layout(ctx, layout)
            ctx.restore()
            return True

        def _nine(self, ctx, name, w, h, sl=(6, 8, 8, 6)):
            """Vẽ ảnh 9-slice (góc giữ nguyên, cạnh/giữa kéo giãn, lọc nearest). sl = cắt trên phải dưới trái
            (như CSS border-image; khớp waybar/theme-pixel.css)."""
            st, sr, sb, sl_ = sl if isinstance(sl, tuple) else (sl,) * 4
            cache = getattr(self, "_nine_cache", None)
            if cache is None:
                cache = self._nine_cache = {}
            if name not in cache:
                path = os.path.join(HERE, "..", "..", "waybar", "pixel", name)
                try:
                    cache[name] = cairo.ImageSurface.create_from_png(path)
                except Exception:
                    cache[name] = None
            img = cache[name]
            if img is None:
                return
            iw, ih = img.get_width(), img.get_height()
            xs = [(0, sl_, 0, sl_), (sl_, iw - sl_ - sr, sl_, w - sl_ - sr), (iw - sr, sr, w - sr, sr)]
            ys = [(0, st, 0, st), (st, ih - st - sb, st, h - st - sb), (ih - sb, sb, h - sb, sb)]
            for sx, sw, dx, dw in xs:
                for sy, sh, dy, dh in ys:
                    if dw <= 0 or dh <= 0:
                        continue
                    ctx.save()
                    ctx.rectangle(dx, dy, dw, dh)
                    ctx.clip()
                    ctx.translate(dx, dy)
                    ctx.scale(dw / sw, dh / sh)
                    ctx.set_source_surface(img, -sx, -sy)
                    ctx.get_source().set_filter(cairo.FILTER_NEAREST)
                    ctx.paint()
                    ctx.restore()

        # ---- chuột ----
        def on_enter(self, *_a):
            self.hover = True
            self.queue_draw()
            if self._leave_src:
                GLib.source_remove(self._leave_src)
                self._leave_src = None
            if not self._hover_src:
                self._hover_src = GLib.timeout_add(HOVER_DELAY_MS, self.start_hover_fx)
            return False

        def on_leave(self, _w, ev):
            if ev.detail == Gdk.NotifyType.INFERIOR:
                return False
            self.hover = False
            self.queue_draw()
            if self._hover_src:
                GLib.source_remove(self._hover_src)
                self._hover_src = None
            if not self._leave_src:
                self._leave_src = GLib.timeout_add(LEAVE_DELAY_MS, self._leave_now)
            return False

        def _leave_now(self):
            self._leave_src = None
            self.stop_hover_fx()
            return False

        def start_hover_fx(self):
            self._hover_src = None
            # đã tự bật sóng (Super + Shift + A) thì để yên
            r = subprocess.run([os.path.join(HERE, "cava-wallpaper.py"), "--status"],
                               capture_output=True, text=True)
            if r.stdout.strip() == "on" or self.info["status"] != "Playing":
                return False
            self.hover_proc = subprocess.Popen([sys.executable, os.path.join(HERE, "cava-wallpaper.py"), "--overlay"],
                                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL, start_new_session=True)
            return False

        def stop_hover_fx(self):
            p, self.hover_proc = self.hover_proc, None
            if p and p.poll() is None:
                p.terminate()

        def on_button(self, _w, ev):
            if ev.type != Gdk.EventType.BUTTON_PRESS:
                return True
            if ev.button == 1:
                self.stop_hover_fx()
                cx = self.slot_x() + self.pw // 2
                subprocess.Popen([sys.executable, os.path.join(HERE, "media-popup.py"), "--x", str(cx)],
                                 start_new_session=True, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif ev.button == 3:
                subprocess.Popen(["playerctl", "play-pause"])
            elif ev.button == 2:
                subprocess.Popen(["playerctl", "stop"])
            return True

        def on_scroll(self, _w, ev):
            d = ev.direction
            if d == Gdk.ScrollDirection.SMOOTH:
                ok, dx, dy = ev.get_scroll_deltas()
                d = Gdk.ScrollDirection.UP if dy < 0 else Gdk.ScrollDirection.DOWN
            subprocess.Popen(["playerctl", "next" if d == Gdk.ScrollDirection.UP else "previous"])
            return True

    win = Pill()
    win.realize()

    # Theo dõi trạng thái bằng playerctl --follow (đẩy sự kiện, không phải hỏi liên tục)
    def follow():
        while True:
            p = subprocess.Popen(["playerctl", "--follow", "metadata", "--format",
                                  "{{status}}\t{{title}}\t{{artist}}"],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            for line in p.stdout:
                GLib.idle_add(win.set_info, parse_status_line(line))
            p.wait()
            GLib.idle_add(win.set_info, parse_status_line(""))
            time.sleep(2)
    threading.Thread(target=follow, daemon=True).start()

    # Toàn màn hình thật → ẩn (dùng lại logic của corner-fillet, thay show/hide bằng cờ)
    class Proxy:
        def hide(self_):
            win.fullscreen = True
            win.update_visible()

        def show(self_):
            win.fullscreen = False
            win.update_visible()
    cf.theo_doi_fullscreen(Proxy(), GLib)

    def quit_(*_a):
        win.stop_hover_fx()
        Gtk.main_quit()
        return False
    for sig in (signal.SIGTERM, signal.SIGINT):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, quit_)
    win.update_visible()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
