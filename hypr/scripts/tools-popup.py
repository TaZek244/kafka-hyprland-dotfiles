#!/usr/bin/env python3
"""tools-popup.py — popup ngang cho nút công cụ trên đầu dock (Waybar `custom/tools`).

Waybar không có sự kiện "rê chuột" cho module, nên chương trình này tự đặt một vùng
TRONG SUỐT (layer-shell, lớp overlay) phủ đúng lên nút công cụ. Rê chuột vào vùng đó
-> hiện popup ngang bên trái dock; rời khỏi cả nút lẫn popup -> ẩn. Dock giữ nguyên.
Bấm vào nút cũng bật/tắt popup (để dùng được cả khi chỉ bấm).
Ô "Chụp / quay" đổi popup sang trang 6 kiểu chụp/quay (+ Quay lại) thay vì mở rofi;
đang quay thì ô đó thành "Dừng quay".

Chạy nền một bản duy nhất (hyprland.lua tự chạy lúc khởi động):
    tools-popup.py            chạy daemon
    tools-popup.py --toggle   bật/tắt popup của daemon đang chạy (SIGUSR1)

Vị trí nút trên dock (đo bằng ảnh chụp, màn 1080p, dock Waybar `width: 60`, margin-right 12):
nút công cụ (thứ 2: ngay dưới menu ứng dụng) nằm ở x = màn hình - 56 .. -6, y = 105 .. 153 (khung gắn sát mép). Đổi bố cục đầu dock thì đo lại HOT_*.
"""

import os
import signal
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import GLib, Gtk, Gdk, GtkLayerShell  # noqa: E402

SCRIPTS = os.path.expanduser("~/.config/hypr/scripts")
PIDFILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "kafka-tools-popup.pid")

# Vùng nhận chuột phủ lên nút công cụ (tính từ góc trên-phải màn hình)
HOT_TOP, HOT_RIGHT, HOT_W, HOT_H = 91, 4, 40, 40   # nút thứ 2 (sau menu) từ khi wifi/bluetooth/bộ gõ lên thanh trên, 2026-11-18
# Popup: mép phải cách màn hình 98px (dock 62 + lề 12 + hở 24, giống hộp chức năng ở đáy dock),
# mép trên ngang nút công cụ
POP_TOP, POP_RIGHT = 70, 73   # dock 48px phẳng (2026-11-18): nút tiện ích y 91..131
SHOW_DELAY_MS, HIDE_DELAY_MS = 90, 350

CSS = b"""
* { font-family: "FiraCode Nerd Font"; }
window.hotspot { background-color: transparent; }
window.popup { background-color: transparent; }
.panel {
    padding: 12px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 16px;
    background-color: rgba(44, 36, 52, 0.98);
}
.item {
    min-width: 104px;
    padding: 10px 4px 12px 4px;
    border: none;
    border-radius: 14px;
    background-image: none;
    background-color: rgba(255, 255, 255, 0.08);
    box-shadow: none;
    transition: background-color 120ms ease, border-color 120ms ease;
}
.item:hover {
    background-color: rgba(255, 255, 255, 0.17);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.22);
}
.item label { color: #f1eaf6; }
.icon { font-family: "FiraCode Nerd Font Propo"; font-size: 26pt; }
.name { font-size: 10pt; }
.item.on { background-color: rgba(201, 71, 133, 0.40); }
.item.back { min-width: 72px; background-color: transparent; }
.item.rec { background-color: rgba(255, 92, 122, 0.22); }
"""


def run(*cmd, shell=False):
    """Chạy lệnh tách rời (không chờ), không để tiến trình con giữ popup."""
    subprocess.Popen(cmd[0] if shell else list(cmd), shell=shell,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def dnd_on():
    try:
        return subprocess.run(["dunstctl", "is-paused"], capture_output=True, text=True,
                              timeout=2).stdout.strip() == "true"
    except (OSError, subprocess.SubprocessError):
        return False


def recording():
    try:
        out = subprocess.run([f"{SCRIPTS}/capture.sh", "status"], capture_output=True,
                             text=True, timeout=3).stdout
        return '"recording"' in out
    except (OSError, subprocess.SubprocessError):
        return False


def layer_window(css_class, namespace, top, right):
    win = Gtk.Window()
    win.get_style_context().add_class(css_class)
    screen = win.get_screen()
    visual = screen.get_rgba_visual()
    if visual is not None:
        win.set_visual(visual)          # nền trong suốt thật
    win.set_app_paintable(True)
    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_namespace(win, namespace)
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.RIGHT, True)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, top)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.RIGHT, right)
    GtkLayerShell.set_exclusive_zone(win, -1)   # không chiếm chỗ, không đẩy cửa sổ khác
    GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
    win.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
                   | Gdk.EventMask.BUTTON_PRESS_MASK)
    return win


class ToolsPopup:
    def __init__(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        import kafka_theme as kt          # giao diện pixel mềm (đồng bộ Waybar) nếu đang bật
        kt.apply(kt.panel(".panel", "2px") + f"""
.item {{ {kt.CARD} }}
.item:hover {{ {kt.CARD_HOVER} }}
.item.on {{ {kt.CARD_ON} }}
.item.rec {{ background-color: {kt.CRIT}; box-shadow: inset 0 0 0 1px #3d0f1a, inset 2px 2px 0 -1px #ff9aae; }}
.item.back {{ background-color: transparent; box-shadow: none; }}
.item.back:hover {{ {kt.CARD_HOVER} }}
""")

        # Đang ở trong vùng nào (nút / popup); ẩn khi rời cả hai
        self.in_hot = False
        self.in_pop = False
        self.timer = None

        self.hot = layer_window("hotspot", "kafka-tools-hotspot", HOT_TOP, HOT_RIGHT)
        self.hot.set_size_request(HOT_W, HOT_H)
        self.hot.connect("enter-notify-event", self.on_enter, "hot")
        self.hot.connect("leave-notify-event", self.on_leave, "hot")
        self.hot.connect("button-press-event", lambda *_: self.toggle())
        self.hot.show_all()

        self.pop = layer_window("popup", "kafka-tools-popup", POP_TOP, POP_RIGHT)
        self.pop.connect("enter-notify-event", self.on_enter, "pop")
        self.pop.connect("leave-notify-event", self.on_leave, "pop")
        panel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        panel.get_style_context().add_class("panel")
        self.pop.add(panel)
        # 2 trang: "main" (4 tiện ích) và "shot" (6 kiểu chụp/quay). Bấm "Chụp / quay" chỉ đổi
        # trang trong chính popup, KHÔNG mở rofi: rofi hiện ngay dưới con trỏ và nhận nhầm cú bấm
        # (chọn luôn ô "Toàn màn hình" -> bấm là chụp). Popup neo mép phải nên đổi trang thì giãn sang trái.
        self.stack = Gtk.Stack(hhomogeneous=False, vhomogeneous=False)
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        panel.pack_start(self.stack, False, False, 0)
        main = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        shot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.stack.add_named(main, "main")
        self.stack.add_named(shot, "shot")

        self.buttons = {}
        for key, icon, color, name in (
            ("clip", "\U000f014c", "#f1eaf6", "Clipboard"),
            ("shot", "\U000f0100", "#f1eaf6", "Chụp / quay"),
            ("keys", "\U000f030c", "#f1eaf6", "Phím tắt"),
            ("dnd",  "\U000f009a", "#f1eaf6", "Không làm phiền"),
        ):
            main.pack_start(self.make_item(key, icon, color, name), False, False, 0)

        # Trang chụp/quay: nút quay lại + 6 kiểu (giống menu `capture.sh menu`)
        for key, icon, color, name in (
            ("back",       "\U000f004d", "#ab9fba", "Quay lại"),
            ("cap:full",   "\U000f0e51", "#f1eaf6", "Toàn màn hình"),
            ("cap:window", "\U000f05b2", "#f1eaf6", "Cửa sổ"),
            ("cap:region", "\U000f019f", "#f1eaf6", "Vùng"),
            ("cap:edit",   "\U000f0f49", "#f1eaf6", "Vùng + vẽ"),
            ("rec:full",   "\U000f0ec2", "#ff5c7a", "Quay màn hình"),
            ("rec:region", "\U000f0567", "#ff5c7a", "Quay vùng"),
        ):
            btn = self.make_item(key, icon, color, name)
            if key == "back":
                btn.get_style_context().add_class("back")
            shot.pack_start(btn, False, False, 0)

    def make_item(self, key, icon, color, name):
        btn = Gtk.Button()
        btn.get_style_context().add_class("item")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        ic = Gtk.Label()
        ic.get_style_context().add_class("icon")
        nm = Gtk.Label(label=name)
        nm.get_style_context().add_class("name")
        box.pack_start(ic, False, False, 0)
        box.pack_start(nm, False, False, 0)
        btn.add(box)
        btn.connect("clicked", self.on_click, key)
        self.buttons[key] = (btn, ic, nm, icon, color)
        self.set_item(key, icon, color, name)
        return btn

    # ---------- hiển thị ----------
    def set_item(self, key, icon, color, name, cls=None):
        btn, ic, nm, _icon, _color = self.buttons[key]
        ic.set_markup(f"<span foreground='{color}'>{GLib.markup_escape_text(icon)}</span>")
        nm.set_text(name)
        ctx = btn.get_style_context()
        for c in ("on", "rec"):
            ctx.remove_class(c)
        if cls:
            ctx.add_class(cls)

    def refresh_state(self):
        if dnd_on():
            self.set_item("dnd", "\U000f009b", "#e0559a", "Đang im lặng", "on")
        else:
            self.set_item("dnd", "\U000f009a", "#b9a3c4", "Không làm phiền")
        if recording():
            self.set_item("shot", "\U000f044a", "#ff4d6d", "Dừng quay", "rec")
        else:
            self.set_item("shot", "\U000f0100", "#f1eaf6", "Chụp / quay")

    def show(self):
        if not self.pop.get_visible():
            self.refresh_state()
            self.pop.show_all()
            self.stack.set_visible_child_name("main")

    def hide(self):
        self.pop.hide()
        self.stack.set_visible_child_name("main")

    def toggle(self):
        if self.pop.get_visible():
            self.hide()
        else:
            self.show()
        return True

    # ---------- rê chuột ----------
    def schedule(self, delay, fn):
        if self.timer:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add(delay, self._fire, fn)

    def _fire(self, fn):
        self.timer = None
        fn()
        return False

    def on_enter(self, _w, event, where):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        if where == "hot":
            self.in_hot = True
            if not self.pop.get_visible():
                self.schedule(SHOW_DELAY_MS, self.show)
            elif self.timer:
                GLib.source_remove(self.timer); self.timer = None
        else:
            self.in_pop = True
            if self.timer:
                GLib.source_remove(self.timer); self.timer = None
        return False

    def on_leave(self, _w, event, where):
        # Rời sang widget con bên trong (nút) không tính là rời popup
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        if where == "hot":
            self.in_hot = False
        else:
            self.in_pop = False
        if not self.in_hot and not self.in_pop:
            self.schedule(HIDE_DELAY_MS, self.hide_if_outside)
        return False

    def hide_if_outside(self):
        if not self.in_hot and not self.in_pop:
            self.hide()

    # ---------- hành động ----------
    def on_click(self, _btn, key):
        if key == "shot" and not recording():
            self.stack.set_visible_child_name("shot")   # giữ popup, đổi sang trang chụp/quay
            return
        if key == "back":
            self.stack.set_visible_child_name("main")
            return
        self.hide()
        if key.startswith(("cap:", "rec:")):
            kind, mode = key.split(":")
            args = ["rec", mode] if kind == "rec" else [mode]
            # Chờ popup biến mất và cú bấm kết thúc, kẻo popup lọt vào ảnh / slurp nhận nhầm cú bấm
            GLib.timeout_add(250, lambda: run(f"{SCRIPTS}/capture.sh", *args) and False)
            return
        if key == "clip":
            run("pkill -x rofi || (cliphist list | rofi -dmenu -theme ~/.config/rofi/kafka.rasi"
                " | cliphist decode | wl-copy)", shell=True)
        elif key == "shot":
            run(f"{SCRIPTS}/capture.sh", "stop")   # chỉ tới đây khi đang quay ("Dừng quay")
        elif key == "keys":
            run(f"{SCRIPTS}/toggle-app.sh", r"kafka\.keybinds", f"{SCRIPTS}/keybinds-editor.py")
        elif key == "dnd":
            run("dunstctl set-paused toggle; pkill -RTMIN+10 waybar; pkill -RTMIN+12 waybar",
                shell=True)


def already_running():
    try:
        pid = int(open(PIDFILE).read().strip())
        os.kill(pid, 0)
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return pid if b"tools-popup.py" in f.read() else None
    except (OSError, ValueError):
        return None


def main():
    pid = already_running()
    if "--toggle" in sys.argv:
        if pid:
            os.kill(pid, signal.SIGUSR1)
        return 0
    if pid:
        print("tools-popup.py đã chạy (pid %d)" % pid, file=sys.stderr)
        return 0
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))

    app = ToolsPopup()
    try:  # PyGObject mới: GLibUnix.signal_add; bản cũ: GLib.unix_signal_add
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        add_signal = GLibUnix.signal_add
    except (ValueError, ImportError):
        add_signal = GLib.unix_signal_add
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, app.toggle)
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: Gtk.main_quit() or False)
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: Gtk.main_quit() or False)
    try:
        Gtk.main()
    finally:
        try:
            os.unlink(PIDFILE)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
