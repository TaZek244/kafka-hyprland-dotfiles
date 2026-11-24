#!/usr/bin/env python3
"""Hộp cảnh báo Kafka ở giữa màn hình, kiểu cảnh báo trong game."""

import argparse
import fcntl
import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time

RUNDIR = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
PIDFILE = os.path.join(RUNDIR, "kafka-alert-popup.pid")
QUEUEFILE = os.path.join(RUNDIR, "kafka-alert-popup.queue")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

LEVELS = {"warn", "critical", "ok"}
KINDS = {"battery", "device", "wifi", "internet", "test"}


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="alert-popup.py", add_help=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--selftest", action="store_true")
    group.add_argument("--close", action="store_true")
    group.add_argument("--title")
    parser.add_argument("--body", default="")
    parser.add_argument("--level", default="warn")
    parser.add_argument("--kind", choices=sorted(KINDS), default="test")
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--sound", action="store_true")
    parser.add_argument("--volume", type=float, default=80)
    parser.add_argument("--test-tag", action="store_true")
    parser.add_argument("--value", type=float, default=None)       # % pin / sóng -> đồng hồ đo
    parser.add_argument("--device-kind", default="")              # mouse|keyboard|headset|... (device-battery.py)
    ns = parser.parse_args(argv)
    if ns.title is None and not (ns.selftest or ns.close):
        parser.error("cần có --title")
    if ns.level not in LEVELS:
        raise ValueError("mức cảnh báo không hợp lệ")
    if ns.kind not in KINDS:
        raise ValueError("loại cảnh báo không hợp lệ")
    return {"title": ns.title or "", "body": ns.body, "level": ns.level,
            "kind": ns.kind, "seconds": max(3.0, min(120.0, ns.seconds)),
            "sound": bool(ns.sound), "volume": max(0.0, min(100.0, ns.volume)),
            "test_tag": bool(ns.test_tag), "selftest": ns.selftest, "close": ns.close,
            "value": None if ns.value is None else max(0.0, min(100.0, ns.value)), "device_kind": ns.device_kind}


# Mỗi loại cảnh báo một "bộ mặt" riêng: màu, tiêu đề (bản phẳng / dải pixel chỉ chữ HOA ASCII), kiểu đồng hồ đo.
STYLES = {
    "battery":  {"colour": "#f2c46d", "header": "PIN YẾU",        "px": "LOW BATTERY",    "gauge": "cells"},
    "device":   {"colour": "#b99cff", "header": "PIN THIẾT BỊ",   "px": "DEVICE BATTERY", "gauge": "cells"},
    "wifi":     {"colour": "#6fd3ff", "header": "SÓNG WI-FI YẾU", "px": "WEAK SIGNAL",    "gauge": "bars"},
    "internet": {"colour": "#ff9a5c", "header": "MẤT KẾT NỐI",    "px": "NO CONNECTION",  "gauge": None},
    "test":     {"colour": "#f08cbb", "header": "THỬ",            "px": "TEST",           "gauge": None},
}
OK_STYLE = {"colour": "#7be0a0", "header": "ĐÃ KẾT NỐI", "px": "CONNECTED"}
CRIT_COLOUR = "#ff5c7a"
DEVICE_ICONS = {"mouse": "\U000f037d", "keyboard": "\U000f030c", "headset": "\U000f02ce", "headphones": "\U000f02cb",
                "gaming": "\U000f02b4", "phone": "\U000f03f2", "speakers": "\U000f04c3", "tablet": "\U000f04f6"}


def style_for(kind, level):
    """Màu + tiêu đề theo loại; mức ok/critical ghi đè màu (khẩn cấp giữ tên loại để vẫn nhận ra)."""
    st = dict(STYLES.get(kind, STYLES["test"]))
    if level == "ok":
        st.update(OK_STYLE, gauge=None)
    elif level == "critical":
        st.update(colour=CRIT_COLOUR, header="KHẨN CẤP · " + st["header"], px="CRITICAL " + st["px"])
    return st


def icon_for(kind, level, value=None, device_kind=""):
    if level == "ok":
        return "\U000f0789" if kind == "internet" else "\U000f05e0"     # web-check / check-circle
    if kind == "battery":
        if level == "critical" or (value is not None and value < 10):
            return "\U000f0083"                                           # battery-alert
        if value is None:
            return "\U000f007a"
        return chr(0xF007A + min(8, int(value // 10) - 1)) if value < 95 else "\U000f0079"   # battery-10..90 / đầy
    if kind == "device":
        return DEVICE_ICONS.get(device_kind, "\U000f02cb")
    if kind == "wifi":
        if value is None or value <= 25:
            return "\U000f0920"                                           # wifi-strength-1-alert
        return "\U000f0922" if value <= 50 else "\U000f0925" if value <= 75 else "\U000f0928"
    if kind == "internet":
        return "\U000f0a8e"                                               # web-off
    return "\U000f009e"                                                   # bell-ring


def header_for(kind, level, pixel=False):
    st = style_for(kind, level)
    return st["px"] if pixel else st["header"]


def gauge_fill(gauge, value):
    """Số ô sáng: pin 10 ô (làm tròn lên, còn chút pin vẫn thấy 1 ô), sóng 4 vạch."""
    if value is None:
        return 0
    if gauge == "cells":
        return max(1 if value > 0 else 0, min(10, int(-(-value // 10))))
    return 0 if value <= 0 else 1 if value <= 25 else 2 if value <= 50 else 3 if value <= 75 else 4


def sound_cmd(path, volume, have_pw_play):
    if have_pw_play:
        return ["pw-play", "--volume", str(float(volume) / 100), path]
    return ["paplay", "--volume", str(int(float(volume) / 100 * 65536)), path]


def queue_append(path, item):
    with open(path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0, os.SEEK_END)
        handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def queue_read(path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        result = []
        for line in handle:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    result.append(value)
            except json.JSONDecodeError:
                continue
        handle.seek(0)
        handle.truncate()
        handle.flush()
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return result


def merge_queue(current, incoming):
    """Gộp cảnh báo: loại cùng loại mới nhất thay thế cảnh báo đang hiện."""
    current = dict(current) if current else None
    pending = []
    for item in incoming:
        if current and item.get("kind") == current.get("kind"):
            current = dict(item)
        else:
            pending.append(dict(item))
    return current, pending


def pid_is_popup(pid):
    if not pid or not str(pid).isdigit() or int(pid) == os.getpid():
        return False
    try:
        os.kill(int(pid), 0)
        with open("/proc/%s/cmdline" % pid, "rb") as handle:
            return b"alert-popup.py" in handle.read()
    except (OSError, ValueError):
        return False


def live_pid():
    try:
        with open(PIDFILE, encoding="ascii") as handle:
            pid = handle.read().strip()
        return int(pid) if pid_is_popup(pid) else None
    except (OSError, ValueError):
        return None


def write_pid():
    os.makedirs(os.path.dirname(PIDFILE) or ".", exist_ok=True)
    with open(PIDFILE, "w", encoding="ascii") as handle:
        handle.write(str(os.getpid()))


def run_selftest():
    assert parse_args(["--title", "x"])["seconds"] == 8
    assert parse_args(["--title", "x", "--seconds", "1", "--volume", "140"])["seconds"] == 3
    assert parse_args(["--title", "x", "--seconds", "999"])["seconds"] == 120
    assert icon_for("wifi", "warn", 20) == "\U000f0920" and icon_for("internet", "ok") == "\U000f0789"
    assert icon_for("battery", "warn", 50) == "\U000f007e" and icon_for("battery", "warn", 30) == "\U000f007c"
    assert icon_for("device", "warn", 30, "mouse") == "\U000f037d"
    assert header_for("battery", "critical") == "KHẨN CẤP · PIN YẾU" and header_for("wifi", "warn", True) == "WEAK SIGNAL"
    assert style_for("internet", "ok")["colour"] == "#7be0a0" and style_for("device", "critical")["colour"] == CRIT_COLOUR
    assert [gauge_fill("cells", v) for v in (0, 3, 30, 31, 100)] == [0, 1, 3, 4, 10]
    assert [gauge_fill("bars", v) for v in (10, 40, 60, 90)] == [1, 2, 3, 4]
    assert sound_cmd("a.wav", 80, True) == ["pw-play", "--volume", "0.8", "a.wav"]
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "queue")
        item = {"title": "Pin", "body": "Còn 30%", "level": "warn", "kind": "battery",
                "seconds": 8, "sound": False, "volume": 80}
        queue_append(path, item)
        assert queue_read(path) == [item] and queue_read(path) == []
    current, pending = merge_queue(item, [{**item, "title": "Pin mới"}, {**item, "kind": "wifi"}])
    assert current["title"] == "Pin mới" and pending[0]["kind"] == "wifi"
    print("alert-popup.py selftest OK")


LOCKFILE = os.path.join(RUNDIR, "kafka-alert-popup.lock")


def css_for(colour):
    return ("* { color: #fbf7fd; font-family: 'FiraCode Nerd Font'; } window { background: transparent; }"
            ".panel { background-color: rgba(44,36,52,0.97); border: 2px solid %(c)s; border-radius: 16px; padding: 18px; }"
            ".panel.pulse { border-color: #fbf7fd; }"
            ".badge { background-color: alpha(%(c)s, 0.16); border-radius: 14px; padding: 6px 12px; min-width: 64px; }"
            ".stripe { background-color: %(c)s; min-width: 4px; border-radius: 2px; }"
            ".gauge-text { color: %(c)s; font-weight: 800; font-size: 13px; }"
            ".header { color: %(c)s; font-size: 12px; font-weight: 800; letter-spacing: 2px; }"
            ".title { font-size: 21px; font-weight: 800; } .body { color: #d4cade; font-size: 13px; }"
            ".icon { font-family: 'FiraCode Nerd Font Propo'; font-size: 56px; color: %(c)s; }"
            ".counter { color: #a99bbd; font-size: 11px; font-weight: 700; }"
            "button { color: #fbf7fd; background: #382b47; background-image: none; border: 1px solid %(c)s;"
            "  border-radius: 8px; padding: 5px 16px; font-weight: 700; }"
            "button:hover { background: #4a3c59; }"
            ) % {"c": colour}


class AlertPopup:
    """Một cửa sổ layer-shell; nội dung dựng lại cho từng cảnh báo trong hàng đợi."""

    TICK_MS = 40            # đủ mượt cho rung/thanh đếm ngược, không tốn CPU

    def __init__(self, item):
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GLib, Gtk, Gdk, GtkLayerShell as L
        sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
        import kafka_theme
        self.GLib, self.Gtk, self.Gdk, self.theme = GLib, Gtk, Gdk, kafka_theme
        self.item, self.pending, self.panel, self.provider = item, [], None, None
        self.pixel = kafka_theme.is_pixel()

        w = self.window = Gtk.Window(title="kafka-alert-popup")
        L.init_for_window(w)
        L.set_namespace(w, "kafka-alert-popup")
        L.set_layer(w, L.Layer.OVERLAY)
        L.set_exclusive_zone(w, 0)
        # không neo cạnh nào -> compositor đặt giữa màn hình; ON_DEMAND: không giành bàn phím của app đang gõ
        L.set_keyboard_mode(w, L.KeyboardMode.ON_DEMAND)
        screen = Gdk.Screen.get_default()
        visual = screen.get_rgba_visual()
        if visual:
            w.set_visual(visual)
        w.set_size_request(540, -1)
        w.connect("key-press-event", self.key_press)
        w.connect("destroy", lambda *_: Gtk.main_quit())
        w.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        w.connect("button-press-event", lambda *_: self.dismiss())
        w.connect("enter-notify-event", lambda *_: self.pause(True))
        w.connect("leave-notify-event", lambda *_: self.pause(False))
        try:                            # PyGObject mới: GLibUnix.signal_add; cũ: GLib.unix_signal_add
            gi.require_version("GLibUnix", "2.0")
            from gi.repository import GLibUnix
            signal_add = GLibUnix.signal_add
        except (ValueError, ImportError):
            signal_add = GLib.unix_signal_add
        signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.read_queue)
        signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.quit)
        signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.quit)
        self.show_item()
        self.read_queue()                   # gom cảnh báo gửi tới trong lúc đang khởi động
        GLib.timeout_add(self.TICK_MS, self.animate)
        Gtk.main()

    def quit(self, *_):
        self.window.destroy()
        return False

    def set_css(self, colour):
        Gtk, screen = self.Gtk, self.Gdk.Screen.get_default()
        if self.provider is None:
            self.provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_screen(screen, self.provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self.provider.load_from_data(css_for(colour).encode())
        if self.pixel and not getattr(self, "pixel_applied", False):
            self.theme.apply(self.theme.panel(".panel", padding="14px", titled=True)
                             + " .ok { " + self.theme.CARD + " } .ok:hover { " + self.theme.CARD_HOVER + " }", screen)
            self.pixel_applied = True

    def show_item(self):
        """Dựng nội dung cho self.item (thay khung cũ), đặt lại đồng hồ, phát âm thanh."""
        Gtk, item = self.Gtk, self.item
        st = style_for(item["kind"], item["level"])
        self.set_css(st["colour"])
        if self.panel is not None:
            self.panel.destroy()
        panel = self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.get_style_context().add_class("panel")
        if self.pixel:              # dải tiêu đề hồng của cửa sổ game: nhãn phải là con ĐẦU TIÊN
            panel.pack_start(self.theme.title_label(st["px"]), False, False, 0)
        else:
            header = Gtk.Label(label=st["header"], xalign=0)
            header.get_style_context().add_class("header")
            panel.pack_start(header, False, False, 0)

        self.inner = Gtk.Box(spacing=14)
        stripe = Gtk.Box()                  # vạch màu của loại cảnh báo (nhận ra loại cả ở bản pixel khung hồng)
        stripe.get_style_context().add_class("stripe")
        self.inner.pack_start(stripe, False, False, 0)
        badge = Gtk.Box()
        badge.get_style_context().add_class("badge")
        badge.set_valign(Gtk.Align.CENTER)
        icon = Gtk.Label(label=icon_for(item["kind"], item["level"], item.get("value"), item.get("device_kind", "")))
        icon.get_style_context().add_class("icon")
        badge.pack_start(icon, True, True, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        text.set_valign(Gtk.Align.CENTER)
        title = Gtk.Label(label=item["title"], xalign=0)
        title.set_line_wrap(True)
        title.get_style_context().add_class("title")
        text.pack_start(title, False, False, 0)
        if item["body"]:
            body = Gtk.Label(label=item["body"], xalign=0)
            body.set_line_wrap(True)
            body.set_max_width_chars(44)
            body.get_style_context().add_class("body")
            text.pack_start(body, False, False, 0)
        if st.get("gauge") and item.get("value") is not None:
            text.pack_start(self.make_gauge(st["gauge"], item["value"], st["colour"]), False, False, 2)
        self.inner.pack_start(badge, False, False, 0)
        self.inner.pack_start(text, True, True, 0)
        panel.pack_start(self.inner, False, False, 0)

        foot = Gtk.Box(spacing=10)
        self.bar = self.make_countdown(st["colour"])     # tự vẽ: GtkProgressBar bị gtk.css chung tô hồng
        self.counter = Gtk.Label()
        self.counter.get_style_context().add_class("counter")
        button = Gtk.Button(label="[ OK ]" if self.pixel else "OK")
        button.get_style_context().add_class("ok")
        button.connect("clicked", lambda *_: self.dismiss())
        foot.pack_start(self.bar, True, True, 0)        # khẩn cấp: không đếm ngược -> không thêm thanh
        foot.pack_end(button, False, False, 0)
        foot.pack_end(self.counter, False, False, 0)
        panel.pack_start(foot, False, False, 0)
        self.window.add(panel)
        self.window.show_all()
        self.bar.set_visible(item["level"] != "critical")
        self.update_counter()

        now = time.monotonic()
        self.shake = now        # hiện ra: dùng hiệu ứng mở layer của Hyprland (set_opacity của GTK3 kẹt trên layer-shell)
        self.deadline, self.paused, self.paused_at = now + item["seconds"], False, None
        self.sound_count, self.next_sound = 0, now + 30
        self.play_sound()

    def make_countdown(self, colour):
        Gdk = self.Gdk
        on, off = Gdk.RGBA(), Gdk.RGBA()
        on.parse(colour)
        off.parse("#3a2f46")
        bar = self.Gtk.DrawingArea()
        bar.set_size_request(-1, 4)
        bar.set_valign(self.Gtk.Align.CENTER)
        bar.frac = 1.0

        def draw(w, cr):
            width, h = w.get_allocated_width(), w.get_allocated_height()
            cr.set_source_rgba(off.red, off.green, off.blue, 1.0)
            cr.rectangle(0, 0, width, h)
            cr.fill()
            cr.set_source_rgba(on.red, on.green, on.blue, 1.0)
            cr.rectangle(0, 0, width * bar.frac, h)
            cr.fill()
            return False

        def set_fraction(f):
            if abs(f - bar.frac) >= 0.002:
                bar.frac = f
                bar.queue_draw()
        bar.connect("draw", draw)
        bar.set_fraction = set_fraction
        return bar

    def make_gauge(self, gauge, value, colour):
        """Đồng hồ đo vẽ bằng cairo: pin = 10 ô, sóng = 4 vạch cao dần; kèm số %."""
        Gtk, Gdk = self.Gtk, self.Gdk
        on, off = Gdk.RGBA(), Gdk.RGBA()
        on.parse(colour)
        off.parse("#3a2f46")
        filled = gauge_fill(gauge, value)
        n, cw, gap, h = (10, 14, 3, 16) if gauge == "cells" else (4, 9, 4, 18)
        area = Gtk.DrawingArea()
        area.set_size_request(n * cw + (n - 1) * gap, h)

        def draw(_w, cr):
            for i in range(n):
                c = on if i < filled else off
                cr.set_source_rgba(c.red, c.green, c.blue, 1.0)
                bh = h if gauge == "cells" else h * (i + 1) / n
                cr.rectangle(i * (cw + gap), h - bh, cw, bh)
                cr.fill()
            return False
        area.connect("draw", draw)
        row = Gtk.Box(spacing=10)
        row.pack_start(area, False, False, 0)
        lab = Gtk.Label(label="%d%%" % round(value))
        lab.get_style_context().add_class("gauge-text")
        row.pack_start(lab, False, False, 0)
        return row

    def update_counter(self):
        self.counter.set_text("+%d" % len(self.pending) if self.pending else "")

    def animate(self):
        now, critical = time.monotonic(), self.item["level"] == "critical"
        if critical:
            offsets = (0, 10, -10, 8, -8, 5, -5, 2, 0)
            i = min(len(offsets) - 1, int((now - self.shake) / 0.045))
            self.inner.set_margin_start(max(0, offsets[i]))
            self.inner.set_margin_end(max(0, -offsets[i]))
            ctx = self.panel.get_style_context()
            (ctx.add_class if int((now - self.shake) / 0.6) % 2 else ctx.remove_class)("pulse")
            if now >= self.next_sound and self.sound_count < 3:
                self.play_sound()
                self.next_sound = now + 30
        elif not self.paused:
            self.bar.set_fraction(max(0.0, (self.deadline - now) / self.item["seconds"]))
            if now >= self.deadline:
                self.dismiss()
        return True

    def pause(self, entering):
        """Rê chuột lên bảng thì dừng đếm ngược (đang đọc)."""
        if entering and not self.paused:
            self.paused, self.paused_at = True, time.monotonic()
        elif not entering and self.paused:
            self.deadline += time.monotonic() - self.paused_at
            self.paused = False

    def key_press(self, _window, event):
        if event.keyval in (self.Gdk.KEY_Return, self.Gdk.KEY_KP_Enter, self.Gdk.KEY_Escape, self.Gdk.KEY_space):
            self.dismiss()
        return True

    def dismiss(self):
        self.read_queue(redraw=False)       # gom cảnh báo vừa tới trước khi quyết định đóng
        if self.pending:
            self.item = self.pending.pop(0)
            self.show_item()
        else:
            self.window.destroy()

    def read_queue(self, *_args, redraw=True):
        old = self.item
        self.item, self.pending = merge_queue(self.item, self.pending + queue_read(QUEUEFILE))
        if redraw and self.item != old:     # cùng loại (vd pin tụt tiếp) -> thay nội dung đang hiện
            self.show_item()
        else:
            self.update_counter()
        return True

    def play_sound(self):
        item = self.item
        if not item["sound"] or (item["level"] == "critical" and self.sound_count >= 3):
            return
        path = os.path.join(REPO, "hypr", "sounds", "alert-%s.wav" % item["level"])
        if not os.path.isfile(path):
            return
        try:
            subprocess.Popen(sound_cmd(path, item["volume"], shutil.which("pw-play") is not None),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.sound_count += 1
        except OSError:
            pass


def main(argv):
    args = parse_args(argv)
    if args["selftest"]:
        run_selftest()
        return 0
    if args["close"]:
        pid = live_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        return 0
    item = {k: args[k] for k in ("title", "body", "level", "kind", "seconds", "sound", "volume", "value", "device_kind")}
    # khoá 1 bản bằng flock (hai cảnh báo tới cùng lúc không mở 2 bảng); không giữ được khoá -> xếp hàng
    os.makedirs(RUNDIR, exist_ok=True)
    lock = open(LOCKFILE, "w")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        queue_append(QUEUEFILE, item)
        for _ in range(20):                 # bản đang chạy có thể chưa kịp ghi pid
            pid = live_pid()
            if pid:
                os.kill(pid, signal.SIGUSR1)
                break
            time.sleep(0.1)
        return 0
    # bản khác có thể gửi SIGUSR1 ngay khi thấy pid, TRƯỚC khi GLib cài hàm xử lý: mặc định SIGUSR1 = chết
    signal.signal(signal.SIGUSR1, signal.SIG_IGN)
    write_pid()
    try:
        AlertPopup(item)
    finally:
        try:
            if open(PIDFILE, encoding="ascii").read().strip() == str(os.getpid()):
                os.unlink(PIDFILE)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except ValueError as exc:
        print("Lỗi: %s" % exc, file=sys.stderr)
        sys.exit(2)
