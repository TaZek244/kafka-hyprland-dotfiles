#!/usr/bin/env python3
"""cava-wallpaper.py — Sóng nhạc cava vẽ như "hình nền động" phong cách Kafka.

Hai chế độ (chuột luôn bấm xuyên qua):
  overlay    (mặc định) dải sóng thấp, trong mờ, NỔI TRÊN cửa sổ (lớp TOP) → luôn thấy khi có nhạc
  wallpaper  cột sóng cao nằm trên ảnh nền nhưng DƯỚI mọi cửa sổ (lớp BOTTOM) → chỉ thấy ở chỗ trống
Chế độ lưu ở ${XDG_STATE_HOME:-~/.local/state}/kafka/cava-mode. Khi im lặng không vẽ gì.

Cách dùng:
  cava-wallpaper.py             Chạy sóng nhạc nền (nếu chưa chạy)
  cava-wallpaper.py --toggle    Bật/tắt sóng nhạc nền
  cava-wallpaper.py --stop      Dừng bản đang chạy
  cava-wallpaper.py --status    In "on" nếu đang chạy, "off" nếu không
  cava-wallpaper.py --mode overlay|wallpaper   Đổi chế độ (đang chạy thì chạy lại ngay)
  cava-wallpaper.py --cycle-mode               Đổi qua lại hai chế độ (Super + Alt + A)
  cava-wallpaper.py --style wave|bars          Kiểu vẽ: sóng cực quang (mặc định) hoặc cột cũ
  cava-wallpaper.py --overlay                  Chạy ở chế độ nổi bất kể chế độ đã lưu (rê chuột lên ô nhạc)
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

# Chế độ overlay: thấp hơn, mờ hơn để không che nội dung khi nổi trên cửa sổ
OVERLAY_HEIGHT = 150
OVERLAY_TOP_COLOR = (0xE0 / 255.0, 0x55 / 255.0, 0x9A / 255.0, 0.60)
OVERLAY_BOT_COLOR = (0xC9 / 255.0, 0x47 / 255.0, 0x85 / 255.0, 0.12)
MODES = ("overlay", "wallpaper")
MODE_FILE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "kafka", "cava-mode")
MODE = "overlay"
WAVE_DOWNSCALE = 3  # sóng vẽ ở 1/3 độ phân giải rồi phóng lên (vẽ thẳng ~56% CPU, 1/2 ~20%, 1/3 ~10%)
WAVE_FPS = 30  # sóng mềm, 30 khung/giây là đủ mượt
STYLE = os.environ.get("KAFKA_CAVA_STYLE", "wave")  # "wave" (sóng cực quang) | "bars" (cột cũ)


def read_mode():
    try:
        with open(MODE_FILE, encoding="utf-8") as f:
            m = f.read().strip()
        return m if m in MODES else "overlay"
    except OSError:
        return "overlay"


def write_mode(m):
    os.makedirs(os.path.dirname(MODE_FILE), exist_ok=True)
    with open(MODE_FILE, "w", encoding="utf-8") as f:
        f.write(m + "\n")


def apply_mode(m):
    """Đặt các hằng hình dạng/màu theo chế độ (gọi trước khi dựng cửa sổ)."""
    global MODE, HEIGHT, TOP_COLOR, BOT_COLOR
    MODE = m
    if m == "overlay":
        HEIGHT, TOP_COLOR, BOT_COLOR = OVERLAY_HEIGHT, OVERLAY_TOP_COLOR, OVERLAY_BOT_COLOR


RUNDIR = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
PIDFILE = os.path.join(RUNDIR, "kafka-cava-wallpaper.pid")


def build_cava_config(bars=BARS, framerate=FRAMERATE):
    """Sinh nội dung file cấu hình tạm cho tiến trình cava."""
    return (
        "[general]\n"
        f"bars = {int(bars)}\n"
        f"framerate = {int(framerate)}\n"
        "sleep_timer = 3\n"  # im lặng 3s thì cava tự ngủ (đỡ ~4% CPU)
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
    from gi.repository import GLib, Gtk, GtkLayerShell

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
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP if MODE == "overlay" else GtkLayerShell.Layer.BOTTOM)
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
                f.write(build_cava_config(BARS, WAVE_FPS if STYLE == "wave" else FRAMERATE))

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
            """Vẽ sóng nhạc. Kiểu mặc định "wave" (sóng cực quang), "bars" = cột bo tròn cũ."""
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
            if STYLE == "bars":
                return self._draw_bars(ctx, width, height)
            # Sóng vẽ ở nửa độ phân giải rồi phóng lên: tô ít điểm ảnh hơn 4 lần (vẽ thẳng ~56% CPU),
            # hình mềm nên phóng lên không thấy khác.
            sw, sh = max(1, width // WAVE_DOWNSCALE), max(1, height // WAVE_DOWNSCALE)
            surf = getattr(self, "_wave_surf", None)
            if surf is None or surf.get_width() != sw or surf.get_height() != sh:
                surf = self._wave_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, sw, sh)
            c2 = cairo.Context(surf)
            c2.set_operator(cairo.OPERATOR_CLEAR)
            c2.paint()
            c2.set_operator(cairo.OPERATOR_OVER)
            self._draw_wave(c2, sw, sh)
            ctx.save()
            ctx.scale(width / sw, height / sh)
            ctx.set_source_surface(surf, 0, 0)
            ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
            ctx.paint()
            ctx.restore()
            return True

        def _draw_wave(self, ctx, width, height):
            """Sóng cực quang: 3 lớp sóng cong (Catmull-Rom) màu hồng→tím đổi sắc theo thời gian,
            viền phát sáng và chấm đỉnh rơi chậm."""
            vals = [min(v, float(ASCII_MAX)) / float(ASCII_MAX) for v in self.bars]
            k_px = 1.0 / WAVE_DOWNSCALE  # đơn vị nét/chấm theo độ phân giải vẽ
            max_h = max(1.0, float(height - 12 * k_px))
            t = time.monotonic()
            # chấm đỉnh: giữ đỉnh rồi rơi dần
            peaks = getattr(self, "_peaks", None)
            if not peaks or len(peaks) != len(vals):
                peaks = [0.0] * len(vals)
            peaks = [max(v, p - 0.012) for v, p in zip(vals, peaks)]
            self._peaks = peaks

            shift = 0.5 + 0.5 * math.sin(t * 0.35)  # sắc màu trôi chậm
            pink = (0xE0 / 255, 0x55 / 255, 0x9A / 255)
            violet = (0xC7 / 255, 0x7D / 255, 0xFF / 255)
            rose = (0xFF / 255, 0x7A / 255, 0xA2 / 255)

            def mix(a, b, k):
                return tuple(a[i] + (b[i] - a[i]) * k for i in range(3))

            c_left, c_mid, c_right = mix(pink, violet, shift), mix(rose, pink, shift), mix(violet, rose, shift)
            a_top = TOP_COLOR[3]
            a_bot = BOT_COLOR[3]

            def points(scale, phase):
                n = len(vals)
                pts = []
                for i, v in enumerate(vals):
                    wob = 0.06 * math.sin(t * 2.2 + i * 0.45 + phase) * (0.3 + v)
                    h = max(0.0, (v * scale + wob * scale)) * max_h
                    x = (i + 0.5) * width / n
                    pts.append((x, height - h))
                return [(0.0, pts[0][1])] + pts + [(float(width), pts[-1][1])]

            def curve(pts):
                ctx.move_to(*pts[0])
                for i in range(len(pts) - 1):
                    p0 = pts[i - 1] if i > 0 else pts[i]
                    p1, p2 = pts[i], pts[i + 1]
                    p3 = pts[i + 2] if i + 2 < len(pts) else p2
                    ctx.curve_to(
                        p1[0] + (p2[0] - p0[0]) / 6,
                        p1[1] + (p2[1] - p0[1]) / 6,
                        p2[0] - (p3[0] - p1[0]) / 6,
                        p2[1] - (p3[1] - p1[1]) / 6,
                        p2[0],
                        p2[1],
                    )

            def hgrad(alpha):
                g = cairo.LinearGradient(0, 0, width, 0)
                g.add_color_stop_rgba(0.0, *c_left, alpha)
                g.add_color_stop_rgba(0.5, *c_mid, alpha)
                g.add_color_stop_rgba(1.0, *c_right, alpha)
                return g

            # 3 lớp: sau (to, mờ) → trước (vừa, đậm hơn)
            for scale, phase, k in ((1.05, 1.7, 0.45), (0.85, 3.1, 0.7), (0.65, 0.0, 1.0)):
                pts = points(scale, phase)
                curve(pts)
                ctx.line_to(width, height)
                ctx.line_to(0, height)
                ctx.close_path()
                fill = cairo.LinearGradient(0, height - max_h, 0, height)
                cl = mix(c_left, c_right, 0.5)
                fill.add_color_stop_rgba(0.0, *cl, a_top * 0.55 * k)
                fill.add_color_stop_rgba(1.0, *cl, a_bot * k)
                ctx.set_source(fill)
                ctx.fill()
                # viền sáng: lớp mờ rộng (phát quang) + nét mảnh
                curve(pts)
                ctx.set_line_join(cairo.LINE_JOIN_ROUND)
                ctx.set_source(hgrad(a_top * 0.3 * k))
                ctx.set_line_width(4.0 * k_px)
                ctx.stroke_preserve()
                ctx.set_source(hgrad(min(1.0, a_top * 1.1) * k))
                ctx.set_line_width(1.8 * k_px)
                ctx.stroke()

            # chấm đỉnh
            n = len(peaks)
            for i, pk in enumerate(peaks):
                if pk < 0.04:
                    continue
                x = (i + 0.5) * width / n
                y = height - pk * max_h * 1.05 - 5 * k_px
                col = mix(c_left, c_right, i / max(1, n - 1))
                ctx.set_source_rgba(*col, a_top * 0.35)
                ctx.arc(x, y, 3.2 * k_px, 0, 2 * math.pi)
                ctx.fill()
                ctx.set_source_rgba(1, 1, 1, min(1.0, a_top * 0.9))
                ctx.arc(x, y, 1.4 * k_px, 0, 2 * math.pi)
                ctx.fill()
            return True

        def _draw_bars(self, ctx, width, height):
            """Kiểu cũ: cột bo tròn đầu, gradient dọc."""
            n = len(self.bars)
            max_bar_h = max(1.0, float(height - 10))
            total_gaps = BAR_GAP * (n - 1)
            bar_w = max(1.0, (width - total_gaps) / float(n))
            step = bar_w + BAR_GAP
            radius = bar_w / 2.0
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

    if "--mode" in args or "--cycle-mode" in args:
        if "--cycle-mode" in args:
            m = "wallpaper" if read_mode() == "overlay" else "overlay"
        else:
            i = args.index("--mode")
            m = args[i + 1] if i + 1 < len(args) else ""
            if m not in MODES:
                print("Dùng: --mode overlay|wallpaper", file=sys.stderr)
                return 2
        write_mode(m)
        print(m)
        if running_pid():  # đang chạy → chạy lại với chế độ mới
            stop_running()
            for _ in range(30):
                if not running_pid():
                    break
                time.sleep(0.1)
            subprocess.Popen(
                [sys.executable, os.path.abspath(__file__)],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if subprocess.call(["which", "notify-send"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
            subprocess.Popen(
                [
                    "notify-send",
                    "-a",
                    "Sóng nhạc",
                    "Sóng nhạc: " + ("nổi trên cửa sổ" if m == "overlay" else "làm hình nền"),
                ]
            )
        return 0

    if "--toggle" in args:
        if running_pid():
            stop_running()
            return 0

    pid = running_pid()
    if pid:
        print(f"cava-wallpaper.py đã chạy (pid {pid})", file=sys.stderr)
        return 0

    global STYLE
    if "--style" in args:
        i = args.index("--style")
        if i + 1 < len(args) and args[i + 1] in ("wave", "bars"):
            STYLE = args[i + 1]
    # --overlay: luôn nổi trên cửa sổ, không theo chế độ đã lưu (media-pill.py dùng khi rê chuột lên ô nhạc)
    apply_mode("overlay" if "--overlay" in args else read_mode())
    write_pidfile()
    try:
        run_visualizer()
    finally:
        remove_pidfile()
    return 0


if __name__ == "__main__":
    sys.exit(main())
