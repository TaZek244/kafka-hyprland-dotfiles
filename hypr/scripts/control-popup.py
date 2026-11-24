#!/usr/bin/env python3
"""control-popup.py — Trung tâm điều khiển (cài đặt nhanh) màu Kafka cho Waybar/Hyprland.

Dùng: control-popup.py [main|wifi|bluetooth|audio] [--fake]
  Waybar gọi khi bấm cụm group/control (bản phẳng) hoặc nút custom/settings (bản pixel, settings-pill.py) ở thanh trên.
  Chưa mở -> mở đúng trang. Đang mở cùng trang (hoặc không ghi trang) -> đóng. Đang mở trang khác -> chuyển trang
  (ghi $XDG_RUNTIME_DIR/kafka-control-popup.page + SIGUSR1). Pid ở $XDG_RUNTIME_DIR/kafka-control-popup.pid.
  --fake: dữ liệu giả (fake_backends.py) để thử giao diện. --selftest: dựng mọi trang bằng dữ liệu giả rồi thoát.

Cửa sổ OVERLAY trong suốt phủ cả màn hình (như clock-popup.py): bấm ra ngoài khung = đóng; Esc ở trang con = về
trang chính, ở trang chính = đóng. Khung neo góc trên-phải, ngay dưới thanh trên và bên trái dock (POP_TOP/POP_RIGHT).

Dữ liệu: control_backends.py (libnm/nmcli, D-Bus bluez, pactl, brightnessctl, powerprofilesctl, dunstctl, fcitx5).
Mọi lệnh backend chạy ở luồng phụ, kết quả về luồng GTK bằng GLib.idle_add. Làm mới định kỳ trang đang xem nhưng
KHÔNG khi đang kéo thanh trượt hay đang gõ mật khẩu; danh sách chỉ vẽ lại khi dữ liệu đổi.
"""

import json
import os
import signal
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")   # thiếu dòng này PyGObject có thể nạp nhầm Gdk 4
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import GLib, Gtk, Gdk, GtkLayerShell  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

RUNDIR = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
PIDFILE = os.path.join(RUNDIR, "kafka-control-popup.pid")
PAGEFILE = os.path.join(RUNDIR, "kafka-control-popup.page")
PAGES = ("main", "wifi", "bluetooth", "audio")

# Góc khung: thanh trên cao 40 (gắn sát mép) + khe 8; dock rộng 48 + khe 8. Đổi Waybar thì đo lại.
POP_TOP, POP_RIGHT = 48, 56
PANEL_W = 470   # cố định cho mọi trang (chữ 11.5pt đậm cần ~470 cho chữ trong ô), đổi trang không nhảy bề rộng
PILL_W = 72     # ô ON/OFF/giá trị ở cột phải (bản pixel): rộng cố định để thẳng cột
REFRESH_MS = {"main": 2000, "wifi": 5000, "bluetooth": 2500, "audio": 2000}

# Glyph Nerd Font (ghi bằng mã, không dán ký tự)
G = {
    "wifi": "\U000f0928", "wifi_off": "\U000f092e", "wifi_lv": ("\U000f091f", "\U000f0922", "\U000f0925", "\U000f0928"),
    "bt": "\U000f00af", "bt_off": "\U000f00b2", "bt_on": "\U000f00b1",
    "headphones": "\U000f02cb", "headset": "\U000f02ce", "mouse": "\U000f037d", "keyboard": "\U000f030c",
    "phone": "\U000f03f2", "speaker": "\U000f04c3", "mic": "\U000f036c",
    "dnd": "\U000f009b", "idle": "\U000f0176", "saver": "\U000f0f86", "balanced": "\U000f0f85", "perf": "\U000f04c5",
    "vol": "\U000f057e", "mute": "\U000f075f", "bright": "\U000f00e0", "bat": "\U000f0079", "bat_chg": "\U000f0084",
    "lock": "\U000f033e", "refresh": "\U000f0450", "next": "\U000f0142", "back": "\U000f0141", "check": "\U000f012c",
}
POWER_NAME = {"power-saver": ("Tiết kiệm", G["saver"]), "balanced": ("Cân bằng", G["balanced"]),
              "performance": ("Hiệu năng", G["perf"])}

CSS = """
/* ĐỒNG BỘ với waybar/style.css: màu nhấn = màu khối Kafka @accent #c94785 (chữ trắng 4.5:1), chữ màu Kafka trên nền
   tối = @accent_fg #e0559a. Ô tắt = xám trung tính (để popup không ngập hồng), ô bật = nền Kafka đặc + chữ trắng. */
* { font-family: "FiraCode Nerd Font"; color: #ffffff; font-size: 11.5pt; font-weight: 600; }   /* chữ dày hơn: bản 500 bị chê "mờ" */
window { background: transparent; }
.panel { padding: 14px; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 16px; background-color: rgba(44, 36, 52, 0.98); }
.title { font-size: 14.5pt; font-weight: 800; }
.sub { color: #f1e9f7; font-size: 10pt; font-weight: 600; }
.icon { font-family: "FiraCode Nerd Font Propo"; font-size: 18pt; }
.section { color: #e0559a; font-weight: 800; font-size: 10pt; margin-top: 6px; }
.error { color: #ff7a93; font-size: 10pt; }
.status { color: #f1e9f7; font-size: 10pt; }

button { background-image: none; background-color: transparent; border: none; border-radius: 10px;
         box-shadow: none; padding: 4px 8px; transition: background-color 150ms ease, box-shadow 150ms ease; }
button:hover { background-color: rgba(255, 255, 255, 0.14); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.20); }
button.flat-icon { padding: 2px 8px; }
button.flat-icon label { font-family: "FiraCode Nerd Font Propo"; font-size: 16pt; color: #ece4f2; }

/* Ô cài đặt nhanh: tắt = xám nhạt chữ sáng; bật = nền sáng trung tính chữ tối */
.tile { border-radius: 14px; background-color: rgba(255, 255, 255, 0.09); }
.tile .icon { color: #ece4f2; }
.tile.on { background-color: #c94785; }
.tile.on label, .tile.on button.flat-icon label { color: #ffffff; }
.tile.on .sub { color: #fff0f6; }
.tile.on .icon { color: #ffffff; }
.tile button { border-radius: 14px; min-height: 56px; }
.tile button:hover { background-color: rgba(255, 255, 255, 0.10); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.18); }
.tile.on button:hover { background-color: rgba(255, 255, 255, 0.12); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.25); }
.tile button.half-right { border-radius: 0 14px 14px 0; border-left: 1px solid rgba(255, 255, 255, 0.18); padding: 0 6px; }
.tile button.half-left { border-radius: 14px 0 0 14px; }
.tile .name { font-weight: 800; }
.tile .sub { font-size: 9.5pt; }

.row { border-radius: 10px; background-color: rgba(255, 255, 255, 0.07); padding: 6px 8px; min-height: 32px; }
.row:hover { background-color: rgba(255, 255, 255, 0.14); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.20); }
.row.active { background-color: rgba(201, 71, 133, 0.40); box-shadow: inset 3px 0 0 0 #e0559a; }
.row.active .icon { color: #ffffff; }
.row .sub { font-size: 9.5pt; }

scale { padding: 0; }
scale trough { min-height: 6px; background-color: rgba(255, 255, 255, 0.14); border: none; border-radius: 4px; }
scale highlight { min-height: 6px; background-color: #c94785; background-image: none; border: none; border-radius: 4px; }
scale slider { min-width: 16px; min-height: 16px; margin: -5px; border-radius: 50%; background-color: #ffffff;
               background-image: none; border: none; box-shadow: none; }
scale slider:hover { background-color: #ffe6f1; }
switch { background-color: rgba(255, 255, 255, 0.16); border: none; border-radius: 12px; background-image: none; }
switch:checked { background-color: #c94785; }
switch slider { background-color: #ffffff; border-radius: 50%; background-image: none; border: none; }
entry { background-color: rgba(255, 255, 255, 0.08); border: 1px solid transparent; border-radius: 8px; color: #fbf7fd; padding: 4px 8px; }
entry:focus { border-color: #e0559a; }
scrolledwindow, viewport { background: transparent; border: none; }
"""


def lbl(text="", cls=None, xalign=0.0, ellipsize=False):
    w = Gtk.Label(label=text, xalign=xalign)
    if ellipsize:
        from gi.repository import Pango
        w.set_ellipsize(Pango.EllipsizeMode.END)
        w.set_max_width_chars(24)
    for c in (cls or "").split():
        w.get_style_context().add_class(c)
    return w


def status_lbl():
    """Dòng trạng thái: tự ẩn khi rỗng (khỏi chiếm chỗ ở đáy khung)."""
    w = lbl("", "status")
    w.set_line_wrap(True)
    w.set_no_show_all(True)
    w.connect("notify::label", lambda l, _p: l.set_visible(bool(l.get_text())))
    return w


def add_cls(widget, *classes):
    for c in classes:
        widget.get_style_context().add_class(c)
    return widget


def set_cls(widget, cls, on):
    ctx = widget.get_style_context()
    (ctx.add_class if on else ctx.remove_class)(cls)


def clear(box):
    for c in box.get_children():
        box.remove(c)
        c.destroy()


def wifi_glyph(strength):
    s = strength or 0
    return G["wifi_lv"][0 if s < 25 else 1 if s < 50 else 2 if s < 75 else 3]


def bt_glyph(icon):
    icon = icon or ""
    if "headset" in icon:
        return G["headset"]
    if "headphone" in icon or icon.startswith("audio"):
        return G["headphones"]
    if "mouse" in icon:
        return G["mouse"]
    if "keyboard" in icon:
        return G["keyboard"]
    if "phone" in icon:
        return G["phone"]
    return G["bt"]


class ControlPopup(Gtk.Window):
    def __init__(self, be, page):
        super().__init__(title="kafka-control")
        self.be = be
        self.dragging = 0            # số thanh trượt đang bị kéo
        self.updating = False        # đang cập nhật công tắc từ dữ liệu -> bỏ qua tín hiệu
        self.loading = set()         # trang đang tải (tránh chồng lệnh)
        self.sig = {}                # chữ ký dữ liệu danh sách đã vẽ
        self.wifi_open = None        # SSID đang mở ô mật khẩu
        self.bt_menu = None          # path thiết bị đang hiện nút "Gỡ"
        self.wifi_menu = None        # SSID đang hiện nút "Quên"
        self.power_cur = None
        self.state = {}
        self._build_window()
        self._build_pages()
        self.show_all()
        self.go(page)
        GLib.timeout_add(250, self._tick)
        self._since = 0

    # ---------- cửa sổ ----------
    def _build_window(self):
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)   # trên ~/.config/gtk-3.0/gtk.css (màu nhấn hồng chung) để thanh trượt ra màu tím
        import kafka_theme as kt          # giao diện pixel mềm (đồng bộ Waybar) nếu đang bật
        self.pixel = kt.apply(kt.panel(".panel", "2px", titled=True) + f"""
.section {{ color: {kt.PINK_FG}; }}
.tile {{ {kt.CARD} }}
.tile.on {{ {kt.CARD_ON} }}
.tile button {{ border-radius: 7px; }}
.tile button:hover {{ background-color: rgba(255, 255, 255, 0.08); box-shadow: none; }}
.tile button.half-left {{ border-radius: 7px 0 0 7px; }}
.tile button.half-right {{ border-radius: 0 7px 7px 0; border-left: 1px solid {kt.EDGE};
                           box-shadow: inset 1px 0 0 0 rgba(255, 255, 255, 0.10); }}
.row {{ {kt.CARD} }}
.row:hover {{ {kt.CARD_HOVER} }}
.row.active {{ {kt.CARD_ON} }}
.sub, .status {{ color: {kt.DIM}; }}
.tile.on .sub {{ color: #fff0f6; }}
.pixel-header .system {{ font-family: "Kafka Pixel"; font-size: 14px; color: #f08cbb; }}
.pixel-header .battery {{ font-family: "FiraCode Nerd Font"; font-size: 10pt; color: {kt.DIM}; }}
.opt-row {{ min-height: 34px; padding: 0 8px; background-color: #1a1422; background-image: none;
            border: none; border-radius: 0; box-shadow: inset 0 0 0 2px #140e1a; }}
.opt-row:hover, .opt-row:focus {{ background-color: #2c2238; box-shadow: inset 0 0 0 2px #140e1a; }}
.opt-row .opt-cursor {{ font-family: "Kafka Pixel"; font-size: 14px; color: #f08cbb; opacity: 0; }}
.opt-row .opt-icon {{ font-family: "FiraCode Nerd Font Propo"; font-size: 16pt; color: #fbf7fd; }}
.opt-row .opt-name {{ font-family: "FiraCode Nerd Font"; font-size: 11.5pt; font-weight: 700; color: #fbf7fd; }}
.opt-row .opt-dim {{ color: #9a8bab; font-size: 10pt; }}
.opt-row .opt-value {{ font-family: "FiraCode Nerd Font"; font-size: 10pt; color: #ffe08a; }}
.opt-pill {{ font-family: "Kafka Pixel"; font-size: 14px; padding: 2px 6px; }}
.opt-pill.opt-on {{ color: #ffffff; background-color: #c94785;
                    box-shadow: inset 0 0 0 2px #3d1028, inset 0 2px 0 #f08cbb; }}
.opt-pill.opt-off {{ color: #9a8bab; background-color: #1a1422;
                     box-shadow: inset 0 0 0 2px #140e1a; }}
.pixel-gauge-label {{ font-family: "FiraCode Nerd Font"; font-size: 11.5pt; font-weight: 700; color: #fbf7fd; }}  /* nhãn tiếng Việt: font pixel không có dấu */
.pixel-gauge-value {{ font-family: "Kafka Pixel"; font-size: 14px; color: #ffe08a; }}
scale.pixel-gauge trough {{ min-height: 12px; border-radius: 0; background-color: #1a1422; border: none;
                             box-shadow: inset 0 0 0 2px #140e1a; }}
scale.pixel-gauge highlight {{ min-height: 12px; border-radius: 0; background-color: #c94785;
                                background-image: repeating-linear-gradient(90deg, #c94785 0px, #c94785 8px, #1a1422 8px, #1a1422 10px);
                                border: none; box-shadow: none; }}
scale.pixel-gauge slider {{ min-width: 10px; min-height: 16px; border-radius: 0; background-color: #ffffff;
                            background-image: none; border: none; box-shadow: inset 0 0 0 2px #140e1a; }}
.opt-pill {{ min-width: 60px; }}   /* [ON] và [OFF] cùng rộng → thẳng cột */

/* ---- TRANG CON (Wi-Fi / Bluetooth / Âm thanh) cùng ngôn ngữ với trang STATUS ---- */
.title {{ font-family: "FiraCode Nerd Font"; font-size: 12.5pt; font-weight: 800; color: #fbf7fd; }}
.section {{ color: #f08cbb; font-size: 9.5pt; font-weight: 800; margin-top: 6px; }}
button.flat-icon, button.flat-icon:hover {{ border-radius: 0; }}
button.flat-icon:hover {{ background-color: #2c2238; box-shadow: inset 0 0 0 2px #140e1a; }}
.row, .row:hover, .row.active {{ border-radius: 0; background-image: none; }}
.row {{ background-color: #1a1422; box-shadow: inset 0 0 0 2px #140e1a; padding: 6px 10px; }}
.row:hover {{ background-color: #2c2238; box-shadow: inset 0 0 0 2px #140e1a; }}
.row.active {{ background-color: #2c2238; box-shadow: inset 0 0 0 2px #f08cbb, inset 6px 0 0 0 #c94785; }}
.row.active label {{ color: #ffffff; }}
.row.active .icon {{ color: #f08cbb; }}
.row button {{ border-radius: 0; }}
.row button:hover {{ background-color: rgba(240, 140, 187, 0.08); box-shadow: none; }}
.row .sub {{ color: #9a8bab; }}
.row.active .sub {{ color: #d4cade; }}
scale trough {{ min-height: 10px; border-radius: 0; background-color: #120d18; border: none;
                box-shadow: inset 0 0 0 2px #140e1a; }}
scale highlight {{ min-height: 10px; border-radius: 0; background-color: #c94785;
                   background-image: repeating-linear-gradient(90deg, #c94785 0px, #c94785 8px, #1a1422 8px, #1a1422 10px);
                   border: none; box-shadow: none; }}
scale slider {{ min-width: 10px; min-height: 16px; margin: -3px; border-radius: 0; background-color: #ffffff;
                background-image: none; border: none; box-shadow: inset 0 0 0 2px #140e1a; }}
entry {{ border-radius: 0; background-color: #120d18; border: none; box-shadow: inset 0 0 0 2px #140e1a; }}
entry:focus {{ box-shadow: inset 0 0 0 2px #f08cbb; }}
button.px-toggle {{ border-radius: 0; padding: 2px 6px; background-image: none; border: none; }}
button.px-toggle label {{ font-family: "Kafka Pixel"; font-size: 14px; }}
button.px-toggle.opt-off {{ background-color: #1a1422; box-shadow: inset 0 0 0 2px #140e1a; }}
button.px-toggle.opt-off label {{ color: #9a8bab; }}
button.px-toggle.opt-on {{ background-color: #c94785; box-shadow: inset 0 0 0 2px #3d1028, inset 0 2px 0 #f08cbb; }}
button.px-toggle.opt-on label {{ color: #ffffff; }}
button.px-toggle:hover {{ box-shadow: inset 0 0 0 2px #f08cbb; }}
""")
        self.set_app_paintable(True)
        vis = self.get_screen().get_rgba_visual()
        if vis:
            self.set_visual(vis)
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, "kafka-control")
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        for e in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, e, True)
        GtkLayerShell.set_exclusive_zone(self, -1)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self._outside)
        self.connect("key-press-event", self._key)
        self.connect("destroy", lambda *_: Gtk.main_quit())

        self.panel = add_cls(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "panel")
        self.panel.set_halign(Gtk.Align.END)
        self.panel.set_valign(Gtk.Align.START)
        self.panel.set_margin_top(POP_TOP)
        self.panel.set_margin_end(POP_RIGHT)
        self.panel.set_size_request(PANEL_W, -1)
        self.add(self.panel)
        self.px_title = kt.title_label("STATUS") if self.pixel else None
        if self.px_title:
            self.panel.pack_start(self.px_title, False, False, 0)
        self.stack = Gtk.Stack()
        self.stack.set_vhomogeneous(False)
        self.stack.set_interpolate_size(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(150)
        self.panel.pack_start(self.stack, False, False, 0)

    def _outside(self, _w, ev):
        a = self.panel.get_allocation()
        if not (a.x <= ev.x <= a.x + a.width and a.y <= ev.y <= a.y + a.height):
            self.quit()
        return False

    def _key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            if self.page != "main":
                self.go("main")
            else:
                self.quit()
            return True
        return False

    def quit(self, *_):
        try:
            with open(PIDFILE) as f:
                if f.read().strip() == str(os.getpid()):
                    os.unlink(PIDFILE)
        except OSError:
            pass
        Gtk.main_quit()

    # ---------- luồng phụ ----------
    def bg(self, fn, *args, done=None):
        def work():
            try:
                res = fn(*args)
            except Exception as exc:  # backend không được ném, nhưng phòng hờ
                res = (False, str(exc))
            if done:
                GLib.idle_add(lambda: (done(res), False)[1])
        threading.Thread(target=work, daemon=True).start()

    def act(self, fn, *args, then=None, status=None):
        """Chạy một hành động; xong thì tải lại trang đang xem (và báo lỗi nếu có)."""
        if status is not None:
            status.set_text("Đang thực hiện …")

        def done(res):
            ok, msg = res if isinstance(res, tuple) and len(res) == 2 else (True, "")
            if status is not None:
                status.set_text("" if ok else (msg or "Không thực hiện được"))
                set_cls(status, "error", not ok)
            if then:
                then(res)
            self.refresh(force=True)
        self.bg(fn, *args, done=done)

    # ---------- trang ----------
    def _build_pages(self):
        self.stack.add_named(self._page_main_pixel() if self.pixel else self._page_main(), "main")
        self.stack.add_named(self._page_wifi(), "wifi")
        self.stack.add_named(self._page_bt(), "bluetooth")
        self.stack.add_named(self._page_audio(), "audio")

    def go(self, page):
        self.page = page if page in PAGES else "main"
        if self.page == "main":
            self.wifi_open = self.wifi_menu = self.bt_menu = None
        self.stack.set_visible_child_name(self.page)
        if self.px_title:
            self.px_title.set_text({"main": "> STATUS", "wifi": "> WI-FI",
                                    "bluetooth": "> BLUETOOTH", "audio": "> AUDIO"}[self.page])
        self.refresh(force=True)
        if self.page == "wifi":
            self.wifi_rescan()

    def wifi_rescan(self):
        """Quét lại mạng (~4s) ở nền; trong lúc đó vẫn hiện danh sách cũ."""
        self.wifi_status.set_text("Đang quét mạng …")
        set_cls(self.wifi_status, "error", False)

        def done(rows):
            if self.wifi_status.get_text().startswith("Đang quét"):
                self.wifi_status.set_text("")
            self.refresh(force=True)
        self.bg(self.be.wifi_list, True, done=done)

    def _tick(self):
        self._since += 250
        if self._since >= REFRESH_MS.get(self.page, 2000):
            self.refresh()
        return True

    def busy_ui(self):
        if self.dragging:
            return True
        if self.page == "wifi" and self.wifi_open:
            return True
        return False

    def refresh(self, force=False, rescan=False):
        self._since = 0
        if (not force and self.busy_ui()) or self.page in self.loading:
            return
        page = self.page
        self.loading.add(page)
        loader = {"main": self._load_main, "wifi": lambda: self._load_wifi(rescan),
                  "bluetooth": self._load_bt, "audio": self._load_audio}[page]

        def done(data):
            self.loading.discard(page)
            if self.page == page and not self.dragging:
                {"main": self._show_main, "wifi": self._show_wifi,
                 "bluetooth": self._show_bt, "audio": self._show_audio}[page](data)
        self.bg(loader, done=done)

    def header(self, box, title, back=True):
        row = Gtk.Box(spacing=6)
        if back:
            b = add_cls(Gtk.Button(label=G["back"]), "flat-icon")
            b.set_tooltip_text("Quay lại (Esc)")
            b.connect("clicked", lambda *_: self.go("main"))
            row.pack_start(b, False, False, 0)
        row.pack_start(lbl(title, "title"), True, True, 0)
        box.pack_start(row, False, False, 0)
        return row

    def make_slider(self, lo, hi, on_change):
        s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
        s.set_draw_value(False)
        s.set_hexpand(True)
        s._timer = None
        s._quiet = False

        def changed(scale):
            if scale._quiet:
                return
            if scale._timer:
                GLib.source_remove(scale._timer)

            def fire():
                scale._timer = None
                self.bg(on_change, int(scale.get_value()))
                return False
            scale._timer = GLib.timeout_add(80, fire)
        s.connect("value-changed", changed)
        s.connect("button-press-event", lambda *_: setattr(self, "dragging", self.dragging + 1) or False)
        s.connect("button-release-event", lambda *_: setattr(self, "dragging", max(0, self.dragging - 1)) or False)
        s.connect("scroll-event", lambda *_: False)
        return s

    @staticmethod
    def set_slider(s, value):
        if s._timer:     # đang gửi giá trị người dùng vừa kéo
            return
        s._quiet = True
        s.set_value(value)
        s._quiet = False

    def make_switch(self):
        """Gtk.Switch (phẳng) hoặc nút bật/tắt [ON]/[OFF] (pixel, giống trang STATUS). Cả hai có
        thuộc tính `active` + tín hiệu notify::active nên code gọi không cần phân biệt."""
        if not self.pixel:
            return Gtk.Switch()
        b = add_cls(Gtk.ToggleButton(label="[OFF]"), "px-toggle", "opt-off")
        b.set_size_request(PILL_W, -1)

        def paint(btn, *_):
            on = btn.get_active()
            btn.set_label("[ON]" if on else "[OFF]")
            set_cls(btn, "opt-on", on)
            set_cls(btn, "opt-off", not on)
        b.connect("notify::active", paint)
        return b

    def set_switch(self, sw, on):
        self.updating = True
        sw.set_active(bool(on))
        self.updating = False

    # ===== Trang chính =====
    def _page_main(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        top = Gtk.Box(spacing=8)
        top.pack_start(lbl("Cài đặt nhanh", "title"), True, True, 0)
        self.bat_lbl = lbl("", "sub", 1.0)
        top.pack_end(self.bat_lbl, False, False, 0)
        box.pack_start(top, False, False, 0)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        self.tiles = {}
        specs = [("wifi", G["wifi"], "Wi-Fi", True), ("bluetooth", G["bt"], "Bluetooth", True),
                 ("dnd", G["dnd"], "Không làm phiền", False), ("idle", G["idle"], "Giữ màn hình sáng", False),
                 ("power", G["balanced"], "Chế độ nguồn", False), ("ime", G["keyboard"], "Bộ gõ", False)]
        for i, (key, glyph, name, split) in enumerate(specs):
            tile = self._tile(key, glyph, name, split)
            grid.attach(tile, i % 2, i // 2, 1, 1)
        box.pack_start(grid, False, False, 0)

        # thanh trượt âm lượng + độ sáng
        vrow = Gtk.Box(spacing=6)
        self.mute_btn = add_cls(Gtk.Button(label=G["vol"]), "flat-icon")
        self.mute_btn.set_tooltip_text("Tắt/mở tiếng")
        self.mute_btn.connect("clicked", lambda *_: self.act(self.be.audio_toggle_mute, "output"))
        self.vol_scale = self.make_slider(0, 100, lambda v: self.be.audio_set_volume("output", v))
        self.vol_lbl = lbl("", "sub", 1.0)
        self.vol_lbl.set_width_chars(5)
        more = add_cls(Gtk.Button(label=G["next"]), "flat-icon")
        more.set_tooltip_text("Thiết bị ra/vào, âm lượng từng ứng dụng")
        more.connect("clicked", lambda *_: self.go("audio"))
        for w, expand in ((self.mute_btn, False), (self.vol_scale, True), (self.vol_lbl, False), (more, False)):
            vrow.pack_start(w, expand, expand, 0)
        box.pack_start(vrow, False, False, 0)

        brow = Gtk.Box(spacing=6)
        bicon = add_cls(Gtk.Button(label=G["bright"]), "flat-icon")
        bicon.set_sensitive(False)
        self.bri_scale = self.make_slider(1, 100, self.be.brightness_set)
        self.bri_lbl = lbl("", "sub", 1.0)
        self.bri_lbl.set_width_chars(5)
        spacer = Gtk.Box()
        spacer.set_size_request(38, -1)
        for w, expand in ((bicon, False), (self.bri_scale, True), (self.bri_lbl, False), (spacer, False)):
            brow.pack_start(w, expand, expand, 0)
        box.pack_start(brow, False, False, 0)
        self.main_status = status_lbl()
        box.pack_start(self.main_status, False, False, 0)
        return box

    def _page_main_pixel(self):
        """Trang chính kiểu menu option của RPG; nhánh flat ở _page_main không đổi."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        top = add_cls(Gtk.Box(spacing=8), "pixel-header")
        top.pack_start(lbl("SYSTEM", "system"), True, True, 0)
        self.pixel_bat_lbl = lbl("", "battery", 1.0)
        top.pack_end(self.pixel_bat_lbl, False, False, 0)
        box.pack_start(top, False, False, 0)

        self.opt_rows = {}
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        specs = [("wifi", G["wifi"], "Wi-Fi"), ("bluetooth", G["bt"], "Bluetooth"),
                 ("vpn", G["lock"], "VPN"), ("dnd", G["dnd"], "Không làm phiền"),
                 ("idle", G["idle"], "Giữ màn hình sáng"), ("power", G["balanced"], "Chế độ nguồn"),
                 ("ime", G["keyboard"], "Bộ gõ")]
        for key, glyph, name in specs:
            row = self._pixel_option_row(key, glyph, name)
            menu.pack_start(row, False, False, 0)
        box.pack_start(menu, False, False, 0)

        self.main_status = status_lbl()
        box.pack_start(self.main_status, False, False, 0)
        self._pixel_gauge(box, "vol", G["vol"], "Âm lượng")
        self._pixel_gauge(box, "bri", G["bright"], "Độ sáng")
        return box

    def _pixel_option_row(self, key, glyph, name):
        row = add_cls(Gtk.Button(), "opt-row")
        row.set_can_focus(True)
        row.set_size_request(-1, 34)
        h = Gtk.Box(spacing=7)
        cursor = lbl(">", "opt-cursor")
        icon = lbl(glyph, "opt-icon")
        title = lbl(name, "opt-name", ellipsize=True)
        value = Gtk.Box(spacing=6)           # [chữ mờ co giãn][ô cố định 64px: pill hoặc giá trị vàng]
        value.set_halign(Gtk.Align.END)      # KHÔNG hexpand: GTK3 coi hexpand = giãn → chia chỗ trống với tên, cột lệch
        row.add(h)
        h.pack_start(cursor, False, False, 0)
        h.pack_start(icon, False, False, 0)
        h.pack_start(title, True, True, 0)
        h.pack_end(value, False, False, 0)
        row.connect("enter-notify-event", lambda *_: cursor.set_opacity(1.0) or False)
        row.connect("leave-notify-event", lambda *_: cursor.set_opacity(0.0) or False)
        row.connect("focus-in-event", lambda *_: cursor.set_opacity(1.0) or False)
        row.connect("focus-out-event", lambda *_: cursor.set_opacity(0.0) or False)
        row.connect("clicked", lambda *_: self._pixel_option_click(key))
        if key in ("wifi", "bluetooth"):
            row.connect("button-press-event", lambda _w, ev: self._pixel_option_right(key, ev))
        self.opt_rows[key] = {"row": row, "cursor": cursor, "icon": icon, "value": value}
        return row

    def _pixel_option_right(self, key, ev):
        if ev.button == 3:
            st = self.state
            if key == "wifi":
                self.act(self.be.wifi_set_enabled, not st.get("wifi", {}).get("enabled"), status=self.main_status)
            else:
                self.act(self.be.bt_set_powered, not st.get("bt", {}).get("powered"), status=self.main_status)
            return True
        return False

    def _pixel_option_click(self, key):
        if key == "wifi":
            self.go("wifi")
        elif key == "bluetooth":
            self.go("bluetooth")
        elif key == "vpn":
            self.act(self._vpn_toggle, status=self.main_status)
        else:
            self._tile_click(key)

    def _pixel_gauge(self, box, key, glyph, name):
        row = Gtk.Box(spacing=6)
        icon = add_cls(Gtk.Button(label=glyph), "flat-icon")
        icon.set_tooltip_text("Tắt/mở tiếng" if key == "vol" else name)
        if key == "vol":
            icon.connect("clicked", lambda *_: self.act(self.be.audio_toggle_mute, "output"))
        else:
            icon.set_sensitive(False)
        text = add_cls(lbl(name), "pixel-gauge-label")
        value = add_cls(lbl("0%", "pixel-gauge-value", 1.0), "pixel-gauge-value")
        row.pack_start(icon, False, False, 0)
        row.pack_start(text, True, True, 0)
        # cuối dòng: [số %][nút › hoặc ô trống cùng rộng] → số % hai dòng thẳng nhau, › luôn ở mép phải
        if key == "vol":
            more = add_cls(Gtk.Button(label=G["next"]), "flat-icon")
            more.set_tooltip_text("Thiết bị ra/vào, âm lượng từng ứng dụng")
            more.connect("clicked", lambda *_: self.go("audio"))
        else:
            more = Gtk.Box()
        more.set_size_request(36, -1)
        row.pack_end(more, False, False, 0)
        row.pack_end(value, False, False, 0)
        scale = self.make_slider(0 if key == "vol" else 1, 100,
                                 (lambda v: self.be.audio_set_volume("output", v)) if key == "vol" else self.be.brightness_set)
        add_cls(scale, "pixel-gauge")
        box.pack_start(row, False, False, 0)
        box.pack_start(scale, False, False, 0)
        if key == "vol":
            self.mute_btn, self.vol_scale, self.vol_lbl = icon, scale, value
        else:
            self.bri_scale, self.bri_lbl = scale, value

    def _vpn_status(self):
        path = os.path.expanduser("~/.config/hypr/scripts/vpn.sh")
        try:
            out = subprocess.run([path, "status"], text=True, capture_output=True, timeout=3, check=True).stdout
            data = json.loads(out)
            return data if isinstance(data, dict) else {"class": "none", "tooltip": ""}
        except (OSError, ValueError, subprocess.SubprocessError):
            return {"class": "none", "tooltip": ""}

    def _vpn_toggle(self):
        path = os.path.expanduser("~/.config/hypr/scripts/vpn.sh")
        try:
            p = subprocess.run([path, "toggle"], text=True, capture_output=True, timeout=8)
            return p.returncode == 0, p.stderr.strip() if p.returncode else ""
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)

    def _tile(self, key, glyph, name, split):
        frame = add_cls(Gtk.Box(), "tile")
        left = Gtk.Button()
        inner = Gtk.Box(spacing=8)
        icon = lbl(glyph, "icon")
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        texts.set_valign(Gtk.Align.CENTER)
        texts.pack_start(lbl(name, "name", ellipsize=True), False, False, 0)
        sub = lbl("…", "sub", ellipsize=True)
        texts.pack_start(sub, False, False, 0)
        inner.pack_start(icon, False, False, 0)
        inner.pack_start(texts, True, True, 0)
        left.add(inner)
        left.connect("clicked", lambda *_: self._tile_click(key))
        frame.pack_start(left, True, True, 0)
        if split:
            add_cls(left, "half-left")
            right = add_cls(Gtk.Button(label=G["next"]), "half-right", "flat-icon")
            right.set_tooltip_text("Mở danh sách")
            right.connect("clicked", lambda *_: self.go(key))
            frame.pack_start(right, False, False, 0)
        self.tiles[key] = (frame, icon, sub)
        return frame

    def _tile_click(self, key):
        st = self.state
        if key == "wifi":
            self.act(self.be.wifi_set_enabled, not st.get("wifi", {}).get("enabled"), status=self.main_status)
        elif key == "bluetooth":
            self.act(self.be.bt_set_powered, not st.get("bt", {}).get("powered"), status=self.main_status)
        elif key == "dnd":
            self.act(self.be.dnd_set, not st.get("dnd"), status=self.main_status)
        elif key == "idle":
            self.act(self.be.idle_inhibit_set, not st.get("idle"), status=self.main_status)
        elif key == "ime":
            self.act(self.be.ime_toggle, status=self.main_status)
        elif key == "power":
            profiles = st.get("profiles") or ["power-saver", "balanced", "performance"]
            cur = st.get("power")
            nxt = profiles[(profiles.index(cur) + 1) % len(profiles)] if cur in profiles else profiles[0]
            self.act(self.be.power_profile_set, nxt, status=self.main_status)

    def _load_main(self):
        be = self.be
        data = {"wifi": be.wifi_state(), "bt": be.bt_state(), "dnd": be.dnd_get(), "idle": be.idle_inhibit_get(),
                "power": be.power_profile_get(), "profiles": be.power_profiles(), "ime": be.ime_get(),
                "bat": be.battery(), "vol": be.audio_volume("output"), "bri": be.brightness_get()}
        if self.pixel:
            data["vpn"] = self._vpn_status()
        return data

    def _show_main(self, d):
        if self.pixel:
            self._show_main_pixel(d)
            return
        self.state = d
        wifi, bt = d["wifi"], d["bt"]
        conn = next((x for x in bt.get("devices", []) if x.get("connected")), None)
        power_name, power_glyph = POWER_NAME.get(d["power"], (d["power"] or "?", G["balanced"]))
        values = {
            "wifi": (wifi.get("enabled"), (wifi.get("ssid") or "Chưa kết nối") if wifi.get("enabled") else ("Khoá phần cứng" if wifi.get("hw_blocked") else "Đã tắt"),
                     wifi_glyph(wifi.get("strength")) if wifi.get("ssid") else (G["wifi"] if wifi.get("enabled") else G["wifi_off"])),
            "bluetooth": (bt.get("powered"), conn["name"] if conn else ("Bật" if bt.get("powered") else "Đã tắt"),
                          G["bt_on"] if conn else (G["bt"] if bt.get("powered") else G["bt_off"])),
            "dnd": (d["dnd"], "Đang bật" if d["dnd"] else "Tắt", G["dnd"]),
            "idle": (d["idle"], "Không tự khoá" if d["idle"] else "Tắt", G["idle"]),
            "power": (d["power"] == "performance", power_name, power_glyph),
            "ime": (d["ime"] == "vi", {"vi": "Tiếng Việt", "en": "English"}.get(d["ime"], "Tắt"), G["keyboard"]),
        }
        for key, (on, sub, glyph) in values.items():
            frame, icon, sublbl = self.tiles[key]
            set_cls(frame, "on", bool(on))
            sublbl.set_text(sub)
            icon.set_text(glyph)
        bat = d["bat"]
        if bat.get("present") and bat.get("percent") is not None:
            g = G["bat_chg"] if bat.get("state") in ("charging", "full") else G["bat"]
            extra = {"charging": " · đang sạc", "full": " · đầy"}.get(bat.get("state"), "")
            t = f" · {bat['time']}" if bat.get("time") else ""
            self.bat_lbl.set_text(f"{g} {bat['percent']}%{extra}{t}")
        vol = d["vol"]
        self.set_slider(self.vol_scale, min(100, vol.get("volume", 0)))
        self.vol_lbl.set_text("tắt" if vol.get("muted") else f"{vol.get('volume', 0)}%")
        self.mute_btn.set_label(G["mute"] if vol.get("muted") else G["vol"])
        self.set_slider(self.bri_scale, d["bri"])
        self.bri_lbl.set_text(f"{d['bri']}%")

    def _show_main_pixel(self, d):
        self.state = d
        sig = json.dumps(d, sort_keys=True)
        if sig == self.sig.get("main-pixel"):
            return
        self.sig["main-pixel"] = sig
        wifi, bt = d["wifi"], d["bt"]
        conn = next((x for x in bt.get("devices", []) if x.get("connected")), None)
        power = {"power-saver": "TIẾT KIỆM", "balanced": "CÂN BẰNG", "performance": "HIỆU NĂNG"}.get(d.get("power"), "?")
        ime = "VI" if d.get("ime") == "vi" else "EN"
        vpn = d.get("vpn") or {}
        tooltip = vpn.get("tooltip") or ""
        vpn_name = tooltip.split(" — ", 1)[0].strip() if tooltip else "Không kết nối"
        values = {
            "wifi": (wifi.get("enabled"), wifi.get("ssid") or "Chưa kết nối", wifi_glyph(wifi.get("strength")) if wifi.get("ssid") else G["wifi"]),
            "bluetooth": (bt.get("powered"), conn["name"] if conn else "Chưa kết nối", G["bt_on"] if conn else G["bt"]),
            "vpn": (vpn.get("class") == "on", vpn_name, G["lock"]),
            "dnd": (d.get("dnd"), "", G["dnd"]), "idle": (d.get("idle"), "", G["idle"]),
            "power": (False, power, G["balanced"]), "ime": (d.get("ime") == "vi", ime, G["keyboard"]),
        }
        for key, (on, value, glyph) in values.items():
            item = self.opt_rows[key]
            item["icon"].set_text(glyph)
            set_cls(item["row"], "active", bool(on))
            clear(item["value"])
            slot = Gtk.Box()                    # ô phải CỐ ĐỊNH: mọi pill/giá trị thẳng một cột
            slot.set_size_request(PILL_W, -1)
            if key in ("wifi", "bluetooth", "vpn") and value:
                dim = lbl(value, "opt-dim", 1.0, ellipsize=True)
                dim.set_max_width_chars(16)
                item["value"].pack_start(dim, False, False, 0)
            if key in ("wifi", "bluetooth", "vpn", "dnd", "idle"):
                pill = add_cls(lbl("[ON]" if on else "[OFF]", xalign=0.5), "opt-pill", "opt-on" if on else "opt-off")
                pill.set_size_request(PILL_W, -1)
                slot.pack_end(pill, False, False, 0)
            else:
                slot.pack_end(lbl(value, "opt-value", 1.0), True, True, 0)
            item["value"].pack_end(slot, False, False, 0)
            item["value"].show_all()

        bat = d["bat"]
        if bat.get("present") and bat.get("percent") is not None:
            g = G["bat_chg"] if bat.get("state") in ("charging", "full") else G["bat"]
            extra = {"charging": " · đang sạc", "full": " · đầy"}.get(bat.get("state"), "")
            t = f" · {bat['time']}" if bat.get("time") else ""
            self.pixel_bat_lbl.set_text(f"{g} {bat['percent']}%{extra}{t}")
        vol = d["vol"]
        self.set_slider(self.vol_scale, min(100, vol.get("volume", 0)))
        self.vol_lbl.set_text("TẮT" if vol.get("muted") else f"{vol.get('volume', 0)}%")
        self.mute_btn.set_label(G["mute"] if vol.get("muted") else G["vol"])
        self.set_slider(self.bri_scale, d["bri"])
        self.bri_lbl.set_text(f"{d['bri']}%")

    # ===== Wi-Fi =====
    def _page_wifi(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        row = self.header(box, "Wi-Fi")
        scan = add_cls(Gtk.Button(label=G["refresh"]), "flat-icon")
        scan.set_tooltip_text("Quét lại")
        scan.connect("clicked", lambda *_: self.wifi_rescan())
        self.wifi_sw = self.make_switch()
        self.wifi_sw.set_valign(Gtk.Align.CENTER)
        self.wifi_sw.connect("notify::active", self._wifi_toggle)
        row.pack_end(self.wifi_sw, False, False, 0)
        row.pack_end(scan, False, False, 0)
        self.wifi_status = status_lbl()
        box.pack_start(self.wifi_status, False, False, 0)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_propagate_natural_height(True)
        sw.set_max_content_height(380)
        self.wifi_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        sw.add(self.wifi_list)
        box.pack_start(sw, False, False, 0)
        return box

    def _wifi_toggle(self, sw, _p):
        if not self.updating:
            self.act(self.be.wifi_set_enabled, sw.get_active(), status=self.wifi_status)

    def _load_wifi(self, rescan=False):
        st = self.be.wifi_state()
        return {"state": st, "list": self.be.wifi_list(rescan) if st.get("enabled") else []}

    def _show_wifi(self, d):
        self.set_switch(self.wifi_sw, d["state"].get("enabled"))
        sig = json.dumps([d["state"].get("enabled"), d["list"], self.wifi_open, self.wifi_menu], sort_keys=True)
        if sig == self.sig.get("wifi"):
            return
        self.sig["wifi"] = sig
        clear(self.wifi_list)
        if not d["state"].get("enabled"):
            self.wifi_list.pack_start(lbl("Wi-Fi đang tắt", "sub"), False, False, 0)
        elif not d["list"]:
            self.wifi_list.pack_start(lbl("Không thấy mạng nào — bấm quét lại", "sub"), False, False, 0)
        for net in d["list"]:
            self.wifi_list.pack_start(self._wifi_row(net), False, False, 0)
        self.wifi_list.show_all()

    def _wifi_row(self, net):
        ssid = net["ssid"]
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        btn = add_cls(Gtk.Button(), "row")
        set_cls(btn, "active", net.get("active"))
        h = Gtk.Box(spacing=8)
        h.pack_start(lbl(wifi_glyph(net.get("strength")), "icon"), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        texts.pack_start(lbl(ssid, ellipsize=True), False, False, 0)
        sub = "Đã kết nối · bấm để ngắt" if net.get("active") else ("Đã lưu" if net.get("known") else ("Bảo mật" if net.get("secure") else "Mở"))
        texts.pack_start(lbl(sub, "sub"), False, False, 0)
        h.pack_start(texts, True, True, 0)
        if net.get("secure"):
            h.pack_end(lbl(G["lock"], "sub"), False, False, 0)
        if net.get("active"):
            h.pack_end(lbl(G["check"], "icon"), False, False, 0)
        btn.add(h)
        btn.connect("clicked", lambda *_: self._wifi_click(net))
        btn.connect("button-press-event", lambda _b, ev: self._wifi_right(ev, net))
        outer.pack_start(btn, False, False, 0)
        if self.wifi_menu == ssid and net.get("known"):
            forget = add_cls(Gtk.Button(label="Quên mạng này"), "row")
            forget.connect("clicked", lambda *_: (setattr(self, "wifi_menu", None),
                                                 self.act(self.be.wifi_forget, ssid, status=self.wifi_status)))
            outer.pack_start(forget, False, False, 0)
        if self.wifi_open == ssid:
            pw = Gtk.Box(spacing=6)
            entry = Gtk.Entry()
            entry.set_visibility(False)
            entry.set_placeholder_text("Mật khẩu")
            entry.set_hexpand(True)
            eye = add_cls(Gtk.Button(label="\U000f0208"), "flat-icon")   # 󰈈 hiện/ẩn
            eye.connect("clicked", lambda *_: entry.set_visibility(not entry.get_visibility()))
            go = add_cls(Gtk.Button(label="Kết nối"), "row")

            def connect(*_):
                password = entry.get_text()
                self.wifi_open = None
                self.wifi_status.set_text(f"Đang kết nối {ssid} …")
                self.act(self.be.wifi_connect, ssid, password, status=self.wifi_status)
            go.connect("clicked", connect)
            entry.connect("activate", connect)
            for w, e in ((entry, True), (eye, False), (go, False)):
                pw.pack_start(w, e, e, 0)
            outer.pack_start(pw, False, False, 0)
            GLib.idle_add(lambda: (entry.grab_focus(), False)[1])
        return outer

    def _wifi_click(self, net):
        ssid = net["ssid"]
        if net.get("active"):
            self.act(self.be.wifi_disconnect, status=self.wifi_status)
        elif net.get("known") or not net.get("secure"):
            self.wifi_status.set_text(f"Đang kết nối {ssid} …")
            self.act(self.be.wifi_connect, ssid, None, status=self.wifi_status)
        else:
            self.wifi_open = None if self.wifi_open == ssid else ssid
            self.sig.pop("wifi", None)
            self.refresh(force=True)

    def _wifi_right(self, ev, net):
        if ev.button == 3 and net.get("known"):
            self.wifi_menu = None if self.wifi_menu == net["ssid"] else net["ssid"]
            self.sig.pop("wifi", None)
            self.refresh(force=True)
            return True
        return False

    # ===== Bluetooth =====
    def _page_bt(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        row = self.header(box, "Bluetooth")
        self.bt_scan = add_cls(Gtk.Button(label="Tìm"), "row")
        self.bt_scan.set_tooltip_text("Tìm thiết bị mới (20 giây)")
        self.bt_scan.connect("clicked", self._bt_discover)
        self.bt_sw = self.make_switch()
        self.bt_sw.set_valign(Gtk.Align.CENTER)
        self.bt_sw.connect("notify::active", self._bt_toggle)
        row.pack_end(self.bt_sw, False, False, 0)
        row.pack_end(self.bt_scan, False, False, 0)
        self.bt_status = status_lbl()
        box.pack_start(self.bt_status, False, False, 0)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_propagate_natural_height(True)
        sw.set_max_content_height(400)
        self.bt_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        sw.add(self.bt_list)
        box.pack_start(sw, False, False, 0)
        return box

    def _bt_toggle(self, sw, _p):
        if not self.updating:
            self.act(self.be.bt_set_powered, sw.get_active(), status=self.bt_status)

    def _bt_discover(self, *_):
        self.bt_scan.set_sensitive(False)
        self.bt_status.set_text("Đang tìm thiết bị …")
        self.bg(self.be.bt_set_discovering, True, done=lambda _r: self.refresh(force=True))

        def stop():
            self.bg(self.be.bt_set_discovering, False, done=lambda _r: self.refresh(force=True))
            self.bt_scan.set_sensitive(True)
            self.bt_status.set_text("")
            return False
        GLib.timeout_add_seconds(20, stop)

    def _load_bt(self):
        return self.be.bt_state()

    def _show_bt(self, st):
        self.set_switch(self.bt_sw, st.get("powered"))
        sig = json.dumps([st, self.bt_menu], sort_keys=True)
        if sig == self.sig.get("bt"):
            return
        self.sig["bt"] = sig
        clear(self.bt_list)
        if not st.get("available"):
            self.bt_list.pack_start(lbl("Không có Bluetooth", "sub"), False, False, 0)
        elif not st.get("powered"):
            self.bt_list.pack_start(lbl("Bluetooth đang tắt", "sub"), False, False, 0)
        else:
            devs = st.get("devices", [])
            for title, paired in (("Đã ghép", True), ("Thiết bị mới", False)):
                group = [x for x in devs if bool(x.get("paired")) == paired]
                if not group and not paired and not st.get("discovering"):
                    continue
                self.bt_list.pack_start(lbl(title, "section"), False, False, 0)
                if not group:
                    self.bt_list.pack_start(lbl("Đang tìm …", "sub"), False, False, 0)
                for dev in group:
                    self.bt_list.pack_start(self._bt_row(dev), False, False, 0)
        self.bt_list.show_all()

    def _bt_row(self, dev):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        btn = add_cls(Gtk.Button(), "row")
        set_cls(btn, "active", dev.get("connected"))
        h = Gtk.Box(spacing=8)
        h.pack_start(lbl(bt_glyph(dev.get("icon")), "icon"), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        texts.pack_start(lbl(dev.get("name") or dev.get("address", "?"), ellipsize=True), False, False, 0)
        if dev.get("connected"):
            sub = "Đã kết nối · bấm để ngắt"
        elif dev.get("paired"):
            sub = "Bấm để kết nối · chuột phải để gỡ"
        else:
            sub = "Bấm để ghép đôi"
        texts.pack_start(lbl(sub, "sub"), False, False, 0)
        h.pack_start(texts, True, True, 0)
        if dev.get("battery") is not None:
            h.pack_end(lbl(f"{G['bat']} {dev['battery']}%", "sub"), False, False, 0)
        btn.add(h)
        path = dev["path"]
        if dev.get("connected"):
            fn, msg = self.be.bt_disconnect, "Đang ngắt …"
        elif dev.get("paired"):
            fn, msg = self.be.bt_connect, "Đang kết nối …"
        else:
            fn, msg = self.be.bt_pair, "Đang ghép đôi …"

        def click(*_):
            self.bt_status.set_text(msg)
            self.act(fn, path, status=self.bt_status)
        btn.connect("clicked", click)

        def right(_b, ev):
            if ev.button == 3 and dev.get("paired"):
                self.bt_menu = None if self.bt_menu == path else path
                self.sig.pop("bt", None)
                self.refresh(force=True)
                return True
            return False
        btn.connect("button-press-event", right)
        outer.pack_start(btn, False, False, 0)
        if self.bt_menu == path:
            rm = add_cls(Gtk.Button(label="Gỡ thiết bị này"), "row")
            rm.connect("clicked", lambda *_: (setattr(self, "bt_menu", None),
                                             self.act(self.be.bt_remove, path, status=self.bt_status)))
            outer.pack_start(rm, False, False, 0)
        return outer

    # ===== Âm thanh =====
    def _page_audio(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.header(box, "Âm thanh")
        self.audio_status = status_lbl()
        box.pack_start(self.audio_status, False, False, 0)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_propagate_natural_height(True)
        sw.set_max_content_height(460)
        self.audio_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        sw.add(self.audio_list)
        box.pack_start(sw, False, False, 0)
        self.audio_sliders = {}
        return box

    def _load_audio(self):
        be = self.be
        return {"out": be.audio_outputs(), "in": be.audio_inputs(), "apps": be.audio_streams()}

    def _show_audio(self, d):
        # Cấu trúc (danh sách thiết bị/app, cái nào mặc định) đổi -> vẽ lại; chỉ âm lượng đổi -> cập nhật thanh trượt.
        shape = json.dumps([[(x["name"], x["default"], x["muted"]) for x in d["out"]],
                            [(x["name"], x["default"], x["muted"]) for x in d["in"]],
                            [(x["index"], x["app"], x["muted"]) for x in d["apps"]]])
        if shape != self.sig.get("audio"):
            self.sig["audio"] = shape
            self._build_audio(d)
        for x in d["out"] + d["in"]:
            s = self.audio_sliders.get(("dev", x["name"]))
            if s:
                self.set_slider(s, x["volume"])
        for x in d["apps"]:
            s = self.audio_sliders.get(("app", x["index"]))
            if s:
                self.set_slider(s, x["volume"])

    def _build_audio(self, d):
        clear(self.audio_list)
        self.audio_sliders = {}
        for title, kind, items, glyph in (("Loa / tai nghe", "output", d["out"], G["speaker"]),
                                          ("Micro", "input", d["in"], G["mic"])):
            self.audio_list.pack_start(lbl(title, "section"), False, False, 0)
            if not items:
                self.audio_list.pack_start(lbl("Không có thiết bị", "sub"), False, False, 0)
            for dev in items:
                self.audio_list.pack_start(self._audio_dev(dev, kind, glyph), False, False, 0)
        self.audio_list.pack_start(lbl("Ứng dụng", "section"), False, False, 0)
        if not d["apps"]:
            self.audio_list.pack_start(lbl("Không có ứng dụng nào phát âm thanh", "sub"), False, False, 0)
        for app in d["apps"]:
            row = add_cls(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "row")
            row.pack_start(lbl(app["app"] + (" (tắt tiếng)" if app.get("muted") else ""), "sub", ellipsize=True), False, False, 0)
            s = self.make_slider(0, 150, lambda v, i=app["index"]: self.be.audio_set_stream_volume(i, v))
            s.set_value(app["volume"])
            row.pack_start(s, False, False, 0)
            self.audio_sliders[("app", app["index"])] = s
            self.audio_list.pack_start(row, False, False, 0)
        self.audio_list.show_all()

    def _audio_dev(self, dev, kind, glyph):
        outer = add_cls(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "row")
        set_cls(outer, "active", dev.get("default"))
        btn = Gtk.Button()
        h = Gtk.Box(spacing=8)
        h.pack_start(lbl(G["check"] if dev.get("default") else glyph, "icon"), False, False, 0)
        h.pack_start(lbl(dev.get("description") or dev["name"], ellipsize=True), True, True, 0)
        if dev.get("muted"):
            h.pack_end(lbl("tắt tiếng", "sub"), False, False, 0)
        btn.add(h)
        btn.set_tooltip_text("Đang dùng" if dev.get("default") else "Bấm để dùng thiết bị này")
        btn.connect("clicked", lambda *_: self.act(self.be.audio_set_default, kind, dev["name"], status=self.audio_status))
        outer.pack_start(btn, False, False, 0)
        if dev.get("default"):   # chỉ thiết bị đang dùng mới có thanh âm lượng cho gọn
            s = self.make_slider(0, 150, lambda v, n=dev["name"]: self.be.audio_set_volume(kind, v, n))
            s.set_value(dev["volume"])
            outer.pack_start(s, False, False, 0)
            self.audio_sliders[("dev", dev["name"])] = s
        return outer


# ---------- một bản duy nhất ----------
def other_instance():
    try:
        with open(PIDFILE) as f:
            pid = int(f.read().strip())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if b"control-popup" in f.read():
                return pid
    except (OSError, ValueError):
        pass
    return None


def current_page_of_running():
    try:
        with open(PAGEFILE) as f:
            return f.read().strip()
    except OSError:
        return None


def selftest():
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        print("selftest bỏ qua: không có display")
        return 0
    import fake_backends as be
    Gtk.init([])
    w = ControlPopup.__new__(ControlPopup)
    Gtk.Window.__init__(w, title="kafka-control-test")
    w.be, w.dragging, w.updating, w.loading, w.sig = be, 0, False, set(), {}
    w.wifi_open = w.bt_menu = w.wifi_menu = None
    w.state, w.page, w._since = {}, "main", 0
    w.pixel = False
    w.stack = Gtk.Stack()
    w._build_pages()
    w._show_main(w._load_main())
    # nhánh pixel (menu tùy chọn kiểu game) cũng phải dựng + đổ dữ liệu được
    wp = ControlPopup.__new__(ControlPopup)
    Gtk.Window.__init__(wp, title="kafka-control-test-pixel")
    wp.be, wp.dragging, wp.updating, wp.loading, wp.sig = be, 0, False, set(), {}
    wp.wifi_open = wp.bt_menu = wp.wifi_menu = None
    wp.state, wp.page, wp._since, wp.pixel = {}, "main", 0, True
    wp.stack = Gtk.Stack()
    wp._build_pages()
    wp._show_main(wp._load_main())
    w._show_wifi(w._load_wifi())
    w.wifi_open = be.wifi_list()[1]["ssid"] if len(be.wifi_list()) > 1 else None
    w.sig.clear()
    w._show_wifi(w._load_wifi())
    w._show_bt(w._load_bt())
    w._show_audio(w._load_audio())
    w._show_audio(w._load_audio())   # lần 2: chỉ cập nhật thanh trượt
    print("selftest ok")
    return 0


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(selftest())
    page = next((a for a in args if a in PAGES), None)
    pid = other_instance()
    if pid:
        if page is None or page == current_page_of_running():
            os.kill(pid, signal.SIGTERM)          # bấm lại cùng nút = đóng
        else:
            with open(PAGEFILE, "w") as f:
                f.write(page)
            os.kill(pid, signal.SIGUSR1)          # bấm nút khác = chuyển trang
        return
    if "--fake" in args:
        import fake_backends as be
    else:
        import control_backends as be
    page = page or "main"
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    win = ControlPopup(be, page)

    # ghi trang đang xem để lần bấm sau biết "cùng trang" hay "trang khác"
    def remember(*_):
        try:
            with open(PAGEFILE, "w") as f:
                f.write(win.page)
        except OSError:
            pass
    win.stack.connect("notify::visible-child-name", remember)
    remember()

    def on_usr1():
        req = current_page_of_running()
        if req in PAGES:
            win.go(req)
        return True
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        add_signal = GLibUnix.signal_add
    except (ValueError, ImportError):
        add_signal = GLib.unix_signal_add
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, on_usr1)
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (win.quit(), False)[1])
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: (win.quit(), False)[1])
    try:
        Gtk.main()
    finally:
        try:
            with open(PIDFILE) as f:
                if f.read().strip() == str(os.getpid()):
                    os.unlink(PIDFILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
