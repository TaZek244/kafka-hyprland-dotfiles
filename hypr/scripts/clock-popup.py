#!/usr/bin/env python3
"""clock-popup.py — popup lịch màu Kafka, hiện ngay dưới đồng hồ ở giữa thanh trên.

Waybar `clock` gọi `clock-popup.py` khi bấm: chưa mở thì mở, đang mở thì đóng (pid ở
$XDG_RUNTIME_DIR/kafka-clock-popup.pid). Popup phủ cả màn hình bằng lớp trong suốt (như popup rofi):
bấm ra ngoài khung lịch (kể cả lên đồng hồ) hoặc Esc là đóng.

Nội dung: giờ lớn (cập nhật từng giây), thứ/ngày tiếng Việt, ngày âm lịch (lunar_vn.py cùng
thư mục), bảng tháng bắt đầu từ thứ Hai (mỗi ô có ngày âm nhỏ; mùng 1 ghi cả tháng âm).
‹ › hoặc cuộn chuột để đổi tháng, "Hôm nay" để quay về, nhấp một ngày để xem âm lịch của ngày đó.
"""

import calendar
import datetime as dt
import json
import os
import signal
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import GLib, Gtk, Gdk, GtkLayerShell  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
try:
    import lunar_vn
except Exception:  # thiếu module âm lịch thì vẫn chạy, chỉ không hiện âm lịch
    lunar_vn = None

RUNDIR = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
PIDFILE = os.path.join(RUNDIR, "kafka-clock-popup.pid")

# Mép trên khung lịch: ngay dưới thanh trên (thanh cao ~46px gồm lề) + khe 8px
POP_TOP = 48   # thanh trên cao 40 (gắn sát mép) + khe 8px

WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
HEAD = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]

CSS = b"""
* { font-family: "FiraCode Nerd Font"; color: #f4eef8; }
window { background-color: transparent; }
.panel {
    padding: 18px 18px 14px 18px;
    border: 2px solid #b8326a;
    border-radius: 20px;
    background-color: rgba(26, 13, 24, 0.97);
}
.time { font-size: 30pt; font-weight: bold; }
.secs { font-size: 14pt; color: #a99bbd; }
.date { font-size: 11pt; }
.lunar { font-size: 10pt; color: #d4af6a; }
.sep { min-height: 1px; background-color: #3b1a33; margin: 4px 0; }
.month { font-size: 12pt; font-weight: bold; }
.nav, .today-btn {
    padding: 2px 10px;
    border: 1px solid #3b1a33;
    border-radius: 999px;
    background-image: none;
    background-color: rgba(58, 21, 48, 0.55);
    box-shadow: none;
    transition: background-color 120ms ease, border-color 120ms ease;
}
.nav:hover, .today-btn:hover { background-color: #3a1530; border-color: #b8326a; }
.head { font-size: 9pt; color: #a99bbd; }
.head.sun { color: #e0708f; }
.day {
    min-width: 46px;
    min-height: 40px;
    padding: 0;
    border: 1px solid transparent;
    border-radius: 12px;
    background-image: none;
    background-color: transparent;
    box-shadow: none;
    transition: background-color 120ms ease, border-color 120ms ease;
}
.day:hover { background-color: #3a1530; border-color: #6b2a52; }
.day .num { font-size: 11pt; }
.day .lun { font-size: 7pt; color: #a99bbd; }
.day .lun.first { color: #d4af6a; }
.day.sun .num { color: #e0708f; }
.day.other .num, .day.other .lun { color: #5a4a66; }
.day.picked { border-color: #b8326a; }
.day.today { background-color: #b8326a; border-color: #d4af6a; }
.day.today .num, .day.today .lun { color: #ffffff; }
.foot { font-size: 9pt; color: #a99bbd; }
"""


def lunar_text(d):
    if not lunar_vn:
        return ""
    try:
        return lunar_vn.lunar_label(d.day, d.month, d.year)
    except Exception:
        return ""


def lunar_small(d):
    """Chữ nhỏ dưới mỗi ô: ngày âm; mùng 1 thì 'ngày/tháng' (tháng nhuận thêm N)."""
    if not lunar_vn:
        return "", False
    try:
        ld, lm, _ly, leap = lunar_vn.solar_to_lunar(d.day, d.month, d.year)
    except Exception:
        return "", False
    if ld == 1:
        return f"1/{lm}{'N' if leap else ''}", True
    return str(ld), False


class ClockPopup(Gtk.Window):
    def __init__(self):
        super().__init__(title="kafka-clock")
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, "kafka-clock")
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        # Phủ cả màn hình (kể cả thanh trên) bằng lớp trong suốt, giống các popup rofi: bấm ra ngoài
        # khung (cả lên đồng hồ) = đóng. Không dựa vào focus-out: layer-shell nhận focus-out ngay khi hiện.
        for e in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                  GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, e, True)
        GtkLayerShell.set_exclusive_zone(self, -1)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)

        today = dt.date.today()
        self.view = today.replace(day=1)
        self.picked = None

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                        halign=Gtk.Align.CENTER, valign=Gtk.Align.START, margin_top=POP_TOP)
        # Đồng hồ không cố định giữa màn hình (có nhạc thì mpris đẩy nó sang trái) -> place()
        # canh khung theo vị trí con trỏ lúc bấm.
        panel.get_style_context().add_class("panel")
        self.panel = panel
        self.add(panel)

        # Giờ + ngày + âm lịch
        trow = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        self.time_lbl = Gtk.Label()
        self.time_lbl.get_style_context().add_class("time")
        self.secs_lbl = Gtk.Label(valign=Gtk.Align.END, margin_bottom=8)
        self.secs_lbl.get_style_context().add_class("secs")
        trow.pack_start(self.time_lbl, False, False, 0)
        trow.pack_start(self.secs_lbl, False, False, 0)
        panel.pack_start(trow, False, False, 0)
        self.date_lbl = Gtk.Label()
        self.date_lbl.get_style_context().add_class("date")
        panel.pack_start(self.date_lbl, False, False, 0)
        self.lunar_lbl = Gtk.Label()
        self.lunar_lbl.get_style_context().add_class("lunar")
        panel.pack_start(self.lunar_lbl, False, False, 0)

        sep = Gtk.Box()
        sep.get_style_context().add_class("sep")
        panel.pack_start(sep, False, False, 4)

        # Thanh tháng: ‹  Tháng 11, 2026  ›   Hôm nay
        nav = Gtk.Box(spacing=8)
        prev_b = Gtk.Button(label="‹")
        next_b = Gtk.Button(label="›")
        for b in (prev_b, next_b):
            b.get_style_context().add_class("nav")
            b.set_relief(Gtk.ReliefStyle.NONE)
        prev_b.connect("clicked", lambda *_: self.shift(-1))
        next_b.connect("clicked", lambda *_: self.shift(1))
        self.month_lbl = Gtk.Label(hexpand=True, xalign=0)
        self.month_lbl.get_style_context().add_class("month")
        today_b = Gtk.Button(label="Hôm nay")
        today_b.get_style_context().add_class("today-btn")
        today_b.set_relief(Gtk.ReliefStyle.NONE)
        today_b.connect("clicked", lambda *_: self.go_today())
        nav.pack_start(self.month_lbl, True, True, 4)
        nav.pack_start(prev_b, False, False, 0)
        nav.pack_start(next_b, False, False, 0)
        nav.pack_start(today_b, False, False, 0)
        panel.pack_start(nav, False, False, 2)

        # Bảng ngày (cuộn chuột để đổi tháng)
        self.grid = Gtk.Grid(column_spacing=2, row_spacing=2, halign=Gtk.Align.CENTER)
        ev = Gtk.EventBox()
        ev.add(self.grid)
        ev.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        ev.connect("scroll-event", self.on_scroll)
        panel.pack_start(ev, False, False, 0)

        self.foot_lbl = Gtk.Label()
        self.foot_lbl.get_style_context().add_class("foot")
        panel.pack_start(self.foot_lbl, False, False, 2)

        self.connect("key-press-event", self.on_key)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.on_click_outside)
        self.connect("destroy", lambda *_: self.quit())

        self.tick()
        GLib.timeout_add(1000, self.tick)
        self.build_month()

    def place(self):
        """Đặt khung lịch thẳng dưới con trỏ (= dưới đồng hồ vừa bấm), không tràn mép màn hình."""
        try:
            out = subprocess.run(["hyprctl", "cursorpos", "-j"], capture_output=True,
                                 text=True, timeout=1).stdout
            cx = json.loads(out)["x"]
            mon = Gdk.Display.get_default().get_monitor_at_point(int(cx), 0).get_geometry()
        except Exception:
            return  # không lấy được thì để giữa màn hình
        w = self.panel.get_preferred_width()[1]
        left = int(min(max(cx - mon.x - w / 2, 12), mon.width - w - 12))
        self.panel.set_halign(Gtk.Align.START)
        self.panel.set_margin_start(left)

    # --- cập nhật ---
    def tick(self):
        now = dt.datetime.now()
        self.time_lbl.set_text(now.strftime("%H:%M"))
        self.secs_lbl.set_text(now.strftime(":%S"))
        self.date_lbl.set_text(f"{WEEKDAYS[now.weekday()]}, {now.day} tháng {now.month}, {now.year}")
        lt = lunar_text(now.date())
        self.lunar_lbl.set_text(f"󰽥  Âm lịch: {lt}" if lt else "")
        self.lunar_lbl.set_visible(bool(lt))
        return True

    def build_month(self):
        for c in self.grid.get_children():
            self.grid.remove(c)
        y, m = self.view.year, self.view.month
        self.month_lbl.set_text(f"Tháng {m}, {y}")
        for i, h in enumerate(HEAD):
            lbl = Gtk.Label(label=h)
            lbl.get_style_context().add_class("head")
            if i == 6:
                lbl.get_style_context().add_class("sun")
            self.grid.attach(lbl, i, 0, 1, 1)
        today = dt.date.today()
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(y, m)
        for r, week in enumerate(weeks, start=1):
            for c, d in enumerate(week):
                self.grid.attach(self.day_button(d, d.month != m, d == today, c == 6), c, r, 1, 1)
        self.grid.show_all()
        self.update_foot()

    def day_button(self, d, other, is_today, sunday):
        b = Gtk.Button()
        b.set_relief(Gtk.ReliefStyle.NONE)
        ctx = b.get_style_context()
        ctx.add_class("day")
        for flag, name in ((other, "other"), (is_today, "today"), (sunday, "sun"),
                           (d == self.picked, "picked")):
            if flag:
                ctx.add_class(name)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, valign=Gtk.Align.CENTER)
        num = Gtk.Label(label=str(d.day))
        num.get_style_context().add_class("num")
        box.pack_start(num, False, False, 0)
        small, first = lunar_small(d)
        if small:
            lun = Gtk.Label(label=small)
            lun.get_style_context().add_class("lun")
            if first:
                lun.get_style_context().add_class("first")
            box.pack_start(lun, False, False, 0)
        b.add(box)
        b.connect("clicked", lambda *_: self.pick(d))
        return b

    def update_foot(self):
        if self.picked:
            d = self.picked
            lt = lunar_text(d)
            txt = f"{WEEKDAYS[d.weekday()]} {d.day}/{d.month}/{d.year}"
            self.foot_lbl.set_text(f"{txt}  ·  {lt}" if lt else txt)
        else:
            self.foot_lbl.set_text("Cuộn chuột hoặc ‹ › để đổi tháng · Esc để đóng")

    # --- thao tác ---
    def pick(self, d):
        self.picked = None if self.picked == d else d
        if d.month != self.view.month or d.year != self.view.year:
            self.view = d.replace(day=1)
        self.build_month()

    def shift(self, n):
        y, m = self.view.year, self.view.month + n
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        self.view = dt.date(y, m, 1)
        self.build_month()

    def go_today(self):
        self.view = dt.date.today().replace(day=1)
        self.picked = None
        self.build_month()

    def on_scroll(self, _w, ev):
        if ev.direction == Gdk.ScrollDirection.UP:
            self.shift(-1)
        elif ev.direction == Gdk.ScrollDirection.DOWN:
            self.shift(1)
        elif ev.direction == Gdk.ScrollDirection.SMOOTH:
            _ok, _dx, dy = ev.get_scroll_deltas()
            self._acc = getattr(self, "_acc", 0.0) + dy
            if abs(self._acc) >= 1.0:
                self.shift(1 if self._acc > 0 else -1)
                self._acc = 0.0
        return True

    def on_click_outside(self, _w, ev):
        a = self.panel.get_allocation()
        if not (a.x <= ev.x < a.x + a.width and a.y <= ev.y < a.y + a.height):
            self.quit()
        return False

    def on_key(self, _w, ev):
        k = ev.keyval
        if k == Gdk.KEY_Escape:
            self.quit()
        elif k in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
            self.shift(-1)
        elif k in (Gdk.KEY_Right, Gdk.KEY_Page_Down):
            self.shift(1)
        elif k in (Gdk.KEY_Home, Gdk.KEY_t):
            self.go_today()
        return True

    def quit(self):
        if getattr(self, "_quitting", False):
            return
        self._quitting = True
        try:
            if os.path.exists(PIDFILE) and open(PIDFILE).read().strip() == str(os.getpid()):
                os.remove(PIDFILE)
        except OSError:
            pass
        Gtk.main_quit()


def running_pid():
    try:
        pid = int(open(PIDFILE).read().strip())
        os.kill(pid, 0)
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if b"clock-popup" not in f.read():
                return None
        return pid
    except (OSError, ValueError):
        return None


def main():
    pid = running_pid()
    if pid:  # đang mở -> bấm lần nữa là đóng
        os.kill(pid, signal.SIGTERM)
        return
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    prov = Gtk.CssProvider()
    prov.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                             Gtk.STYLE_PROVIDER_PRIORITY_USER)
    import kafka_theme as kt              # giao diện pixel KAFKA.SYS (đồng bộ Waybar) nếu đang bật
    kt.apply(kt.panel(".panel", "6px 6px 2px 6px") + f"""
.time {{ font-family: "{kt.PIXEL_FONT}"; font-size: 42px; font-weight: normal;
         text-shadow: 6px 6px 0 rgba(11, 7, 16, 0.9); }}  /* chữ pixel như đồng hồ màn hình đăng nhập (6px/điểm) */
.secs {{ font-family: "{kt.PIXEL_FONT}"; font-size: 14px; }}
.secs, .head, .foot, .day .lun {{ color: {kt.FAINT}; }}
.lunar, .day .lun.first {{ color: {kt.PINK_FG}; }}
.head.sun, .day.sun .num {{ color: #ff9aae; }}
.sep {{ background-color: #3a2f46; }}
.nav, .today-btn {{ {kt.CARD} }}
.nav:hover, .today-btn:hover {{ {kt.CARD_HOVER} }}
.day {{ background-color: transparent; border-color: transparent; border-radius: 7px; box-shadow: none; }}
.day:hover {{ {kt.CARD_HOVER} border-color: transparent; }}
.day.other .num, .day.other .lun {{ color: #55486a; }}
.day.picked {{ border-color: transparent; box-shadow: inset 0 0 0 1px {kt.PINK}, inset 0 0 0 2px {kt.EDGE}; }}
.day.today {{ {kt.CARD_ON} border-color: transparent; }}
.day.today .num, .day.today .lun {{ color: #ffffff; }}
""")
    win = ClockPopup()
    try:  # PyGObject mới: GLibUnix; bản cũ: GLib.unix_signal_add
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        add_sig = GLibUnix.signal_add
    except (ValueError, ImportError):
        add_sig = GLib.unix_signal_add
    add_sig(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda *_: win.quit() or False)
    win.show_all()
    win.tick()
    win.place()
    Gtk.main()


if __name__ == "__main__":
    main()
