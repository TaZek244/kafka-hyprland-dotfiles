#!/usr/bin/env python3
"""Góc lõm (bo cong lõm) ở chỗ nối thanh trên với dock phải của Waybar (khung chữ L).

Tự chạy trong hl.on("hyprland.start"); 1 bản, pid ở $XDG_RUNTIME_DIR/kafka-corner-fillet.pid.
Đo lại TOP_MARGIN / DOCK_LEFT_FROM_RIGHT nếu đổi chiều cao thanh trên hay độ rộng dock.
--png out.png: xem trước, --selftest: kiểm tra hình học.
"""

import math
import os
import signal
import sys


# Hình học cố định của màn 1920x1080 (scale 1).
R = 14
CORNER_SIZE = R + 1
TOP_MARGIN = 39   # hàng viền dưới thanh trên (thanh cao 40, gắn sát mép trên)
DOCK_LEFT_FROM_RIGHT = 48  # 1920 - x cột viền trái dock (1872, dock 48px phẳng), dock gắn sát mép phải
SCREEN_WIDTH = 1920
BG = (44 / 255, 36 / 255, 52 / 255, 0.93)   # = @bg trong waybar/style.css
BORDER = (1.0, 1.0, 1.0, 0.10)   # = @line (viền trung tính)
PIDFILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
                       "kafka-corner-fillet.pid")


def margin_right(screen_width):
    """Lề phải để cột cục bộ R nằm đúng tại mép trái dock."""
    # Mép phải cửa sổ là x = screen_width - margin; cột R ở x = 1846.
    return screen_width - (screen_width - DOCK_LEFT_FROM_RIGHT + 1)


def geometry_for_width(screen_width):
    """Trả về (margin_top, margin_right, width, height) cho màn hình."""
    return TOP_MARGIN, margin_right(screen_width), CORNER_SIZE, CORNER_SIZE


def draw_corner(ctx, scale=1.0):
    """Vẽ phần nền ngoài đường tròn và cung viền 1px."""
    size = CORNER_SIZE
    ctx.save()
    ctx.scale(scale, scale)

    # Hình chữ nhật trừ hình tròn: phần trong tròn giữ alpha = 0.
    ctx.set_fill_rule(__import__("cairo").FILL_RULE_EVEN_ODD)
    ctx.new_path()
    ctx.rectangle(0, 0, size, size)
    ctx.arc(0, R + 1, R + 0.5, 0, 2 * math.pi)
    ctx.set_source_rgba(*BG)
    ctx.fill()

    ctx.new_path()
    ctx.arc(0, R + 1, R + 0.5, -math.pi / 2, 0)
    ctx.set_source_rgba(*BORDER)
    ctx.set_line_width(1.0)
    ctx.set_antialias(__import__("cairo").ANTIALIAS_BEST)
    ctx.stroke()
    ctx.restore()


def render_png(path):
    """Xuất ảnh phóng to, nền đen để nhìn rõ alpha của góc."""
    import cairo

    factor = 8
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                  CORNER_SIZE * factor, CORNER_SIZE * factor)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(0, 0, 0)
    ctx.paint()
    draw_corner(ctx, factor)
    surface.write_to_png(path)


def already_running():
    try:
        pid = int(open(PIDFILE).read().strip())
        os.kill(pid, 0)
        with open(f"/proc/{pid}/cmdline", "rb") as proc:
            return pid if b"corner-fillet.py" in proc.read() else None
    except (OSError, ValueError):
        return None


def remove_pidfile():
    try:
        if os.path.exists(PIDFILE) and open(PIDFILE).read().strip() == str(os.getpid()):
            os.unlink(PIDFILE)
    except OSError:
        pass


def co_fullscreen_that():
    """True nếu workspace đang xem có cửa sổ toàn màn hình thật (mode 2; mode 1 = phóng to chừa Waybar)."""
    import json
    import subprocess
    try:
        ws = json.loads(subprocess.run(["hyprctl", "activeworkspace", "-j"], capture_output=True, text=True, timeout=2).stdout)
        if not ws.get("hasfullscreen"):
            return False
        clients = json.loads(subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=2).stdout)
    except Exception:
        return False
    return any(c.get("workspace", {}).get("id") == ws.get("id") and c.get("fullscreen") == 2 for c in clients)


def theo_doi_fullscreen(win, GLib):
    """Nghe socket2 của Hyprland; đổi fullscreen/workspace/màn hình thì ẩn/hiện góc."""
    import socket
    import threading

    def cap_nhat():
        if co_fullscreen_that():
            win.hide()
        else:
            win.show()
        return False

    def nghe():
        path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "hypr",
                            os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", ""), ".socket2.sock")
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(path)
        except OSError:
            return
        buf = b""
        while True:
            data = sock.recv(4096)
            if not data:
                return
            buf += data
            *lines, buf = buf.split(b"\n")
            if any(l.split(b">>")[0] in (b"fullscreen", b"workspace", b"workspacev2", b"focusedmon", b"closewindow") for l in lines):
                GLib.idle_add(cap_nhat)

    threading.Thread(target=nghe, daemon=True).start()
    GLib.idle_add(cap_nhat)


def run_window():
    import cairo
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")   # thiếu dòng này PyGObject nạp nhầm Gdk 4
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GLib, Gtk, Gdk, GtkLayerShell

    class CornerWindow(Gtk.Window):
        def __init__(self):
            super().__init__(title="kafka-corner-fillet")
            screen = self.get_screen()
            visual = screen.get_rgba_visual()
            if visual is not None:
                self.set_visual(visual)
            self.set_app_paintable(True)
            self.set_size_request(CORNER_SIZE, CORNER_SIZE)
            self.set_default_size(CORNER_SIZE, CORNER_SIZE)
            self.set_resizable(False)
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_namespace(self, "kafka-corner-fillet")
            # OVERLAY: lớp TOP luôn nằm dưới Waybar (layer rule order không đổi được), nên dùng overlay
            # và tự ẩn khi có cửa sổ toàn màn hình thật (xem theo_doi_fullscreen).
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)

            width = SCREEN_WIDTH
            try:
                monitor = Gdk.Display.get_default().get_primary_monitor()
                if monitor is not None:
                    width = monitor.get_geometry().width
            except Exception:
                pass
            top, right, _w, _h = geometry_for_width(width)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, top)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, right)
            GtkLayerShell.set_exclusive_zone(self, -1)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)

            # Region rỗng: mọi click xuyên qua góc.
            self.connect("draw", self.on_draw)
            self.connect("destroy", lambda *_: Gtk.main_quit())
            self.realize_signal = self.connect("realize", self.on_realize)

        def on_realize(self, _window):
            region = cairo.Region()
            self.get_window().input_shape_combine_region(region, 0, 0)

        def on_draw(self, _window, ctx):
            ctx.set_operator(cairo.OPERATOR_CLEAR)   # xoá nền (cửa sổ RGBA mặc định có thể tô đen)
            ctx.paint()
            ctx.set_operator(cairo.OPERATOR_OVER)
            draw_corner(ctx)
            return True

    win = CornerWindow()
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        add_signal = GLibUnix.signal_add
    except (ValueError, ImportError):
        add_signal = GLib.unix_signal_add
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGTERM,
               lambda *_: Gtk.main_quit() or False)
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGINT,
               lambda *_: Gtk.main_quit() or False)
    win.show()
    theo_doi_fullscreen(win, GLib)
    Gtk.main()


def main():
    if "--selftest" in sys.argv:
        assert geometry_for_width(1920) == (39, 47, 15, 15)
        assert geometry_for_width(2560) == (39, 47, 15, 15)
        print("selftest ok")
        return 0
    if "--png" in sys.argv:
        try:
            path = sys.argv[sys.argv.index("--png") + 1]
        except (ValueError, IndexError):
            print("dùng: --png out.png", file=sys.stderr)
            return 2
        render_png(path)
        return 0

    pid = already_running()
    if pid:
        print(f"corner-fillet.py đã chạy (pid {pid})", file=sys.stderr)
        return 0
    with open(PIDFILE, "w") as pidfile:
        pidfile.write(str(os.getpid()))
    try:
        run_window()
    finally:
        remove_pidfile()
    return 0


if __name__ == "__main__":
    sys.exit(main())
