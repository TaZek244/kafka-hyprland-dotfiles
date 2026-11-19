#!/usr/bin/env python3
"""cava-wallpaper.py — Sóng nhạc cava vẽ như "hình nền động" phong cách Kafka.

Các cột sóng nằm trên lớp ảnh nền (lớp BOTTOM của layer-shell) nhưng DƯỚI mọi cửa sổ,
cho phép chuột bấm xuyên qua hoàn toàn.

Cách dùng:
  cava-wallpaper.py             Chạy sóng nhạc nền (nếu chưa chạy)
  cava-wallpaper.py --toggle    Bật/tắt sóng nhạc nền
  cava-wallpaper.py --stop      Dừng bản đang chạy
  cava-wallpaper.py --status    In "on" nếu đang chạy, "off" nếu không
  cava-wallpaper.py --selftest  Kiểm tra logic thuần không cần màn hình (in PASS/FAIL)
"""

import math
import os
import signal
import subprocess
import sys
import tempfile
import time

# Hằng số hình học và cấu hình sóng nhạc
NAMESPACE = "kafka-cava-wallpaper"
HEIGHT = 260
DOCK_W = 48
BARS = 64
FRAMERATE = 60
ASCII_MAX = 1000
BAR_GAP = 4
SILENCE_TIMEOUT = 2.0  # giây im lặng trước khi ngưng vẽ để tiết kiệm CPU
DECAY = 0.85

# Màu gradient dọc: từ đỉnh #e0559a (alpha 0.85) xuống đáy #c94785 (alpha 0.35)
TOP_COLOR = (0xE0 / 255.0, 0x55 / 255.0, 0x9A / 255.0, 0.85)
BOT_COLOR = (0xC9 / 255.0, 0x47 / 255.0, 0x85 / 255.0, 0.35)

RUNDIR = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
PIDFILE = os.path.join(RUNDIR, "kafka-cava-wallpaper.pid")


def build_cava_config(bars=BARS, framerate=FRAMERATE):
    """Sinh nội dung file cấu hình tạm cho tiến trình cava."""
    return (
        "[general]\n"
        f"bars = {int(bars)}\n"
        f"framerate = {int(framerate)}\n"
        "sleep_timer = 3\n"   # im lặng 3s thì cava tự ngủ (đỡ ~4% CPU)
        "\n"
        "[input]\n"
        "method = pulse\n"
        "\n"
        "[output]\n"
        "method = raw\n"
        "raw_target = /dev/stdout\n"
        "data_format = ascii\n"
        f"ascii_max_range = {ASCII_MAX}\n"
        "bar_delimiter = 59\n"
        "frame_delimiter = 10\n"
    )


def parse_frame(line):
    """Phân tích một dòng stdout từ cava thành danh sách số nguyên 0..1000.

    Chuỗi hợp lệ dạng "1;500;1000;" -> [1, 500, 1000].
    Trả về None nếu dòng rỗng hoặc chứa dữ liệu hỏng.
    """
    if not isinstance(line, str):
        return None
    s = line.strip()
    if not s:
        return None
    if s.endswith(";"):
        s = s[:-1]
    if not s:
        return None
    parts = s.split(";")
    values = []
    for p in parts:
        if not p:
            return None
        try:
            v = int(p)
        except ValueError:
            return None
        if v < 0:
            v = 0
        elif v > ASCII_MAX:
            v = ASCII_MAX
        values.append(v)
    return values if values else None


def smooth_bars(new_vals, old_vals, decay=DECAY):
    """Làm mượt cột sóng: giá trị hiển thị = max(mới, cũ * 0.85)."""
    if not old_vals or len(old_vals) != len(new_vals):
        return [float(v) for v in new_vals]
    return [max(float(n), float(o) * decay) for n, o in zip(new_vals, old_vals)]


def running_pid():
    """Trả về PID nếu cava-wallpaper.py đang chạy, ngược lại None."""
    try:
        with open(PIDFILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read()
        if b"cava-wallpaper" not in cmd and b"python" not in cmd:
            return None
        return pid
    except (OSError, ValueError):
        return None


def write_pidfile():
    """Ghi PID của tiến trình hiện tại vào PIDFILE."""
    try:
        with open(PIDFILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def remove_pidfile():
    """Xoá PIDFILE nếu nó thuộc về tiến trình hiện tại."""
    try:
        if os.path.exists(PIDFILE):
            with open(PIDFILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content == str(os.getpid()):
                os.unlink(PIDFILE)
    except OSError:
        pass


def stop_running():
    """Dừng tiến trình đang chạy (nếu có). Trả về True nếu đã gửi tín hiệu dừng."""
    pid = running_pid()
    if not pid:
        try:
            if os.path.exists(PIDFILE):
                os.unlink(PIDFILE)
        except OSError:
            pass
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    return True


def run_selftest():
    """Kiểm tra các hàm thuần không cần màn hình / GTK."""
    try:
        # 1. Kiểm tra parse_frame
        assert parse_frame("1;500;1000;") == [1, 500, 1000], "parse_frame chuẩn thất bại"
        assert parse_frame("0;250;1000\n") == [0, 250, 1000], "parse_frame không dấu ';' cuối thất bại"
        assert parse_frame("") is None, "parse_frame chuỗi rỗng phải trả về None"
        assert parse_frame("   \n") is None, "parse_frame khoảng trắng phải trả về None"
        assert parse_frame("1;abc;3;") is None, "parse_frame chữ cái phải trả về None"
        assert parse_frame("1;;3;") is None, "parse_frame phần tử rỗng phải trả về None"
        assert parse_frame(";") is None, "parse_frame chỉ dấu ';' phải trả về None"

        # 2. Kiểm tra build_cava_config
        cfg = build_cava_config(bars=64, framerate=60)
        required_keys = [
            "[general]",
            "bars = 64",
            "framerate = 60",
            "[input]",
            "method = pulse",
            "[output]",
            "method = raw",
            "raw_target = /dev/stdout",
            "data_format = ascii",
            "ascii_max_range = 1000",
            "bar_delimiter = 59",
            "frame_delimiter = 10",
        ]
        for key in required_keys:
            assert key in cfg, f"Thiếu cấu hình cava: {key}"

        # 3. Kiểm tra smooth_bars
        res = smooth_bars([100, 50, 800], [200, 100, 500])
        assert abs(res[0] - 170.0) < 1e-6, f"Sai làm mượt phần tử 0: {res[0]}"
        assert abs(res[1] - 85.0) < 1e-6, f"Sai làm mượt phần tử 1: {res[1]}"
        assert abs(res[2] - 800.0) < 1e-6, f"Sai làm mượt phần tử 2: {res[2]}"

        print("PASS")
        return 0
    except AssertionError as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:
        print(f"FAIL: {e}")
        return 1


def run_visualizer():
    """Khởi tạo cửa sổ GTK Layer Shell lớp BOTTOM và chạy tiến trình cava."""
    import cairo
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

    class CavaWallpaperWindow(Gtk.Window):
        def __init__(self):
            super().__init__(title=NAMESPACE)
            self._quitting = False
            self.bars = [0.0] * BARS
            self.raw_silent_since = time.monotonic()
            self.is_silent = True
            self.cava_proc = None
            self.cfg_path = None
            self._rx_buf = b""

            # Nền trong suốt RGBA
            screen = self.get_screen()
            visual = screen.get_rgba_visual()
            if visual is not None:
                self.set_visual(visual)
            self.set_app_paintable(True)
            self.set_size_request(-1, HEIGHT)
            self.set_default_size(1, HEIGHT)

            # Cấu hình Layer Shell: lớp BOTTOM (trên hình nền, dưới mọi cửa sổ)
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_namespace(self, NAMESPACE)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.BOTTOM)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, DOCK_W)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, 0)
            GtkLayerShell.set_exclusive_zone(self, -1)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)

            self.connect("draw", self.on_draw)
            self.connect("realize", self.on_realize)
            self.connect("size-allocate", self.on_size_allocate)
            self.connect("destroy", lambda *_: self.cleanup_and_quit())

            self.start_cava()

        def _apply_passthrough(self):
            """Đặt vùng nhận chuột rỗng để mọi cú nhấp chuột xuyên qua hoàn toàn."""
            gdk_win = self.get_window()
            if gdk_win is not None:
                gdk_win.input_shape_combine_region(cairo.Region(), 0, 0)

        def on_realize(self, _widget):
            self._apply_passthrough()

        def on_size_allocate(self, _widget, _allocation):
            self._apply_passthrough()

        def start_cava(self):
            """Tạo file cấu hình tạm và khởi chạy tiến trình con cava."""
            fd, self.cfg_path = tempfile.mkstemp(prefix="kafka-cava-", suffix=".conf")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(build_cava_config(BARS, FRAMERATE))

            try:
                self.cava_proc = subprocess.Popen(
                    ["cava", "-p", self.cfg_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                     close_fds=True,
                )
            except OSError as e:
                print(f"Không thể chạy cava: {e}", file=sys.stderr)
                GLib.idle_add(self.cleanup_and_quit)
                return

            stdout_fd = self.cava_proc.stdout.fileno()
            os.set_blocking(stdout_fd, False)
            GLib.io_add_watch(
                stdout_fd,
                GLib.PRIORITY_DEFAULT,
                GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR,
                self.on_cava_io,
            )

        def on_cava_io(self, fd, condition):
            """Đọc dữ liệu khung sóng nhạc từ stdout của cava không chặn."""
            if self._quitting:
                return False

            if condition & GLib.IO_IN:
                try:
                    chunk = os.read(fd, 65536)
                except BlockingIOError:
                    return True
                except OSError:
                    self.cleanup_and_quit()
                    return False

                if not chunk:
                    self.cleanup_and_quit()
                    return False

                self._rx_buf += chunk
                if b"\n" in self._rx_buf:
                    lines = self._rx_buf.split(b"\n")
                    self._rx_buf = lines.pop()
                    # Lấy khung mới nhất nhận được trong đợt đọc này để tránh trễ khung
                    latest_vals = None
                    for raw_line in lines:
                        vals = parse_frame(raw_line.decode("ascii", errors="ignore"))
                        if vals is not None:
                            latest_vals = vals
                    if latest_vals is not None:
                        self.process_frame(latest_vals)

            if condition & (GLib.IO_HUP | GLib.IO_ERR):
                self.cleanup_and_quit()
                return False

            return True

        def process_frame(self, vals):
            """Cập nhật mức độ cột sóng, kiểm tra im lặng và yêu cầu vẽ lại khi cần."""
            now = time.monotonic()
            if any(v > 0 for v in vals):
                self.raw_silent_since = now
                was_silent = self.is_silent
                self.is_silent = False
                self.bars = smooth_bars(vals, self.bars, DECAY)
                self.queue_draw()
            else:
                self.bars = smooth_bars(vals, self.bars, DECAY)
                if (now - self.raw_silent_since) > SILENCE_TIMEOUT:
                    if not self.is_silent:
                        # Vẽ thêm một khung rỗng cuối cùng để xoá sạch sóng rồi nghỉ
                        self.is_silent = True
                        self.bars = [0.0] * len(vals)
                        self.queue_draw()
                else:
                    # Trong 2s đầu mới im lặng: tiếp tục vẽ hiệu ứng rơi mượt
                    self.queue_draw()

        def on_draw(self, _widget, ctx):
            """Vẽ các cột sóng bo tròn đầu với màu gradient dọc bằng Cairo."""
            ctx.set_operator(cairo.OPERATOR_CLEAR)
            ctx.paint()
            ctx.set_operator(cairo.OPERATOR_OVER)

            if self.is_silent:
                return True

            width = self.get_allocated_width()
            height = self.get_allocated_height()
            n = len(self.bars)
            if n == 0 or width <= 0 or height <= 0:
                return True

            max_bar_h = max(1.0, float(height - 10))
            total_gaps = BAR_GAP * (n - 1)
            bar_w = max(1.0, (width - total_gaps) / float(n))
            step = bar_w + BAR_GAP
            radius = bar_w / 2.0

            # Gradient dọc từ đỉnh (y = height - max_bar_h) xuống đáy (y = height)
            grad = cairo.LinearGradient(0, height - max_bar_h, 0, height)
            grad.add_color_stop_rgba(0.0, *TOP_COLOR)
            grad.add_color_stop_rgba(1.0, *BOT_COLOR)
            ctx.set_source(grad)

            for i, val in enumerate(self.bars):
                if val <= 0.5:
                    continue
                bar_h = (min(val, float(ASCII_MAX)) / float(ASCII_MAX)) * max_bar_h
                if bar_h < 1.0:
                    continue

                x = i * step
                y_top = height - bar_h
                r = min(radius, bar_h / 2.0)

                # Cột có đỉnh bo tròn nửa hình tròn, chân phẳng sát mép dưới
                ctx.new_sub_path()
                ctx.move_to(x, height)
                ctx.line_to(x, y_top + r)
                ctx.arc(x + radius, y_top + r, r, math.pi, 0.0)
                ctx.line_to(x + bar_w, height)
                ctx.close_path()

            ctx.fill()
            return True

        def cleanup_and_quit(self, *_args):
            """Diệt tiến trình cava con, xoá file cấu hình tạm + pidfile và thoát vòng lặp GTK."""
            if self._quitting:
                return False
            self._quitting = True

            if self.cava_proc is not None:
                try:
                    if self.cava_proc.poll() is None:
                        self.cava_proc.terminate()
                        try:
                            self.cava_proc.wait(timeout=0.5)
                        except subprocess.TimeoutExpired:
                            self.cava_proc.kill()
                except OSError:
                    pass
                self.cava_proc = None

            if self.cfg_path and os.path.exists(self.cfg_path):
                try:
                    os.unlink(self.cfg_path)
                except OSError:
                    pass
                self.cfg_path = None

            remove_pidfile()
            if Gtk.main_level() > 0:
                Gtk.main_quit()
            return False

    win = CavaWallpaperWindow()
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        add_signal = GLibUnix.signal_add
    except (ValueError, ImportError):
        add_signal = GLib.unix_signal_add

    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGTERM, win.cleanup_and_quit)
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGINT, win.cleanup_and_quit)

    win.show_all()
    try:
        Gtk.main()
    finally:
        win.cleanup_and_quit()


def main():
    args = sys.argv[1:]

    if "--selftest" in args:
        return run_selftest()

    if "--status" in args:
        print("on" if running_pid() else "off")
        return 0

    if "--stop" in args:
        stop_running()
        return 0

    if "--toggle" in args:
        if running_pid():
            stop_running()
            return 0

    pid = running_pid()
    if pid:
        print(f"cava-wallpaper.py đã chạy (pid {pid})", file=sys.stderr)
        return 0

    write_pidfile()
    try:
        run_visualizer()
    finally:
        remove_pidfile()
    return 0


if __name__ == "__main__":
    sys.exit(main())
