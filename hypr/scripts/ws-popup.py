#!/usr/bin/env python3
"""ws-popup.py — vùng hotspot trong suốt và popup chọn workspace cho Waybar.

Mục đích:
    Waybar (thanh trên cao 40px) chỉ hiện ô workspace ĐANG DÙNG (số La Mã I..X)
    và không hỗ trợ sự kiện rê chuột. Chương trình này đặt một vùng trong suốt
    (layer-shell OVERLAY) phủ lên ô workspace đó; rê chuột vào sẽ hiện popup
    lưới 5×2 chọn workspace ngay bên dưới, rời khỏi cả hotspot lẫn popup sau
    350ms sẽ tự ẩn.

Cách dò vị trí:
    Mỗi 1500ms (khi popup đang ẩn), luồng phụ chụp dải y 6..33 (`grim -g "0,6 640x28"`),
    gộp theo cột (cột có điểm hồng = hồng, để chữ không cắt đoạn), rồi tìm các đoạn
    màu hồng `#c94785` (0xc9, 0x47, 0x85) dài >= 10px trong 640px đầu. Đoạn đầu là khối
    "Kafka" (bản phẳng bị vạch ngăn tách 2 đoạn), đoạn CUỐI là ô workspace đang chọn. Hotspot đặt tại
    `x = start - 12`, rộng `(end - start + 1) + 24`.

Phím chuột:
    • Trên hotspot: rê vào = mở popup; bấm trái = bật/tắt popup;
      cuộn lên/xuống = chuyển workspace trước/sau (1..10).
    • Trên ô workspace trong popup: bấm trái = chuyển tới workspace đó;
      bấm phải = chuyển cửa sổ đang chọn sang workspace đó.

Đường dẫn & tham số:
    • PID file: $XDG_RUNTIME_DIR/kafka-ws-popup.pid
    • ws-popup.py            chạy daemon (Hyprland tự chạy trong hyprland.start)
    • ws-popup.py --toggle   bật/tắt popup qua SIGUSR1
    • ws-popup.py --selftest chạy kiểm thử tự động các hàm thuần (không cần màn hình)
"""

import json
import os
import signal
import subprocess
import sys
import threading

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

PIDFILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "kafka-ws-popup.pid")

HOT_TOP, HOT_H = 2, 36
POP_TOP = 44
SHOW_DELAY_MS, HIDE_DELAY_MS = 90, 350
PROBE_INTERVAL_MS = 1500
TARGET_RGB = (0xC9, 0x47, 0x85)
PROBE_Y, PROBE_W, PROBE_H = 6, 640, 28  # dải dò y 6..33, x < 640 (gộp theo cột, xem collapse_rows)
LEFT_LIMIT = 640
MERGE_GAP = 6  # đoạn hồng cách nhau ≤ 6px là cùng một ô (bị chữ cắt)

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")

CSS = b"""
* { font-family: "FiraCode Nerd Font"; }
window.hotspot { background-color: transparent; }
window.popup { background-color: transparent; }
.panel {
    background-color: rgba(44, 36, 52, 0.98);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 16px;
    padding: 10px;
}
.title {
    color: #a091b1;
    font-size: 9pt;
    font-weight: bold;
    margin-bottom: 6px;
}
.ws {
    min-width: 58px;
    min-height: 50px;
    border-radius: 12px;
    background-color: rgba(255, 255, 255, 0.08);
    border: none;
    background-image: none;
    box-shadow: none;
    padding: 4px 6px;
}
.ws:hover {
    background-color: rgba(255, 255, 255, 0.17);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.22);
}
.ws.active {
    background-color: #c94785;
}
.ws.empty .num {
    color: #8a7c9c;
}
.num {
    font-family: "FiraCode Nerd Font";
    font-size: 15pt;
    font-weight: bold;
    color: #fbf7fd;
}
.apps {
    font-family: "FiraCode Nerd Font Propo";
    font-size: 11pt;
    color: #d4cade;
}
"""


def roman(n):
    """Đổi số nguyên 1..10 sang số La Mã I..X."""
    if 1 <= n <= len(ROMAN):
        return ROMAN[n - 1]
    return str(n)


def find_runs(row_bytes, color=TARGET_RGB, min_len=10):
    """Tìm các đoạn pixel liên tiếp có màu `color` dài >= `min_len`.

    Trả về danh sách tuple `(start, end)` theo toạ độ pixel (bao gồm cả hai đầu).
    """
    target = bytes(color)
    n = len(row_bytes) // 3
    runs = []
    start = None
    for x in range(n):
        if row_bytes[x * 3 : x * 3 + 3] == target:
            if start is None:
                start = x
        elif start is not None:
            if x - start >= min_len:
                runs.append((start, x - 1))
            start = None
    if start is not None and n - start >= min_len:
        runs.append((start, n - 1))
    return runs


def collapse_rows(rgb, width, rows, color=TARGET_RGB):
    """Gộp `rows` hàng ảnh thành 1 hàng: cột nào có ÍT NHẤT một điểm `color` thì thành `color`.
    Dò trên 1 hàng thì chữ trắng dày (VIII) cắt ô hồng thành các đoạn < 10px → không thấy ô."""
    target = bytes(color)
    other = b"\x00\x00\x00"
    out = bytearray()
    for x in range(width):
        hit = any(rgb[(y * width + x) * 3 : (y * width + x) * 3 + 3] == target for y in range(rows))
        out += target if hit else other
    return bytes(out)


def pick_ws_run(runs, limit=LEFT_LIMIT):
    """Ô workspace = đoạn hồng CUỐI CÙNG bắt đầu trước `limit` và không phải đoạn đầu tiên.
    Khối Kafka (đứng đầu) có thể bị vạch ngăn tách làm 2 đoạn (bản phẳng), nên không lấy "đoạn thứ hai";
    giới hạn `limit` để không bắt nhầm vạch hồng của ô nhạc giữa thanh."""
    merged = []
    for r in runs:  # nối đoạn bị nét chữ cắt (thân chữ "I" + bóng phủ hết chiều cao)
        if merged and r[0] - merged[-1][1] <= MERGE_GAP:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(r)
    left = [r for r in merged if r[0] < limit]
    return left[-1] if len(left) >= 2 else None


def parse_ppm_row(ppm_bytes):
    """Tách dữ liệu RGB từ ảnh PPM (P6) trả về bởi grim."""
    if not ppm_bytes.startswith(b"P6"):
        return b""
    idx = 0
    tokens = []
    n = len(ppm_bytes)
    while len(tokens) < 4 and idx < n:
        while idx < n and ppm_bytes[idx] in b" \t\r\n":
            idx += 1
        if idx < n and ppm_bytes[idx : idx + 1] == b"#":
            while idx < n and ppm_bytes[idx : idx + 1] != b"\n":
                idx += 1
            continue
        start = idx
        while idx < n and ppm_bytes[idx] not in b" \t\r\n#":
            idx += 1
        if idx > start:
            tokens.append(ppm_bytes[start:idx])
    if len(tokens) < 4:
        return b""
    idx += 1  # bỏ đúng 1 ký tự trắng sau maxval (255)
    return ppm_bytes[idx:]


def summarize(clients, active_id):
    """Tổng hợp trạng thái 10 workspace từ danh sách `clients` của Hyprland.

    Trả về list 10 dict: `{id, roman, classes, extra, apps_text, tooltip,
    active, empty}`.
    """
    by_ws = {i: [] for i in range(1, 11)}
    for c in clients or []:
        ws_id = (c.get("workspace") or {}).get("id", 0)
        if not isinstance(ws_id, int) or ws_id < 1 or ws_id > 10:
            continue
        by_ws[ws_id].append(c)

    result = []
    for ws_id in range(1, 11):
        ws_clients = by_ws[ws_id]
        empty = len(ws_clients) == 0
        classes = []
        for c in ws_clients:
            cls = (c.get("class") or "").strip() or "?"
            if cls not in classes:
                classes.append(cls)

        if empty:
            apps_text = "·"
            tooltip = "Trống"
        else:
            shown = " ".join(classes[:3])
            extra = len(classes) - 3
            apps_text = f"{shown} +{extra}" if extra > 0 else shown
            counts = {}
            for c in ws_clients:
                cls = (c.get("class") or "").strip() or "?"
                counts[cls] = counts.get(cls, 0) + 1
            tooltip = ", ".join(f"{k} ×{v}" if v > 1 else k for k, v in counts.items())

        result.append(
            {
                "id": ws_id,
                "roman": roman(ws_id),
                "classes": classes[:3],
                "extra": max(0, len(classes) - 3),
                "apps_text": apps_text,
                "tooltip": tooltip,
                "active": ws_id == active_id,
                "empty": empty,
            }
        )
    return result


def run(*cmd):
    """Chạy lệnh tách rời (không chờ), không để tiến trình con giữ popup."""
    subprocess.Popen(
        list(cmd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def focus_workspace(ws_id):
    """Chuyển sang workspace `ws_id` bằng biểu thức Lua của Hyprland 0.57."""
    run("hyprctl", "dispatch", f"hl.dsp.focus({{ workspace = {int(ws_id)} }})")


def move_window_to_workspace(ws_id):
    """Đưa cửa sổ đang chọn sang workspace `ws_id`."""
    run("hyprctl", "dispatch", f"hl.dsp.window.move({{ workspace = {int(ws_id)} }})")


def hypr_json(subcmd, default):
    """Gọi `hyprctl <subcmd> -j` với timeout 2s, lỗi trả về `default`."""
    try:
        out = subprocess.run(
            ["hyprctl", subcmd, "-j"],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
        return json.loads(out) if out.strip() else default
    except (OSError, subprocess.SubprocessError, ValueError):
        return default


def active_workspace_id():
    """Lấy ID workspace hiện hành (trả về 0 nếu lỗi)."""
    data = hypr_json("activeworkspace", {})
    ws_id = data.get("id", 0) if isinstance(data, dict) else 0
    return ws_id if isinstance(ws_id, int) else 0


def already_running():
    """Kiểm tra daemon đã chạy chưa qua PIDFILE và /proc/<pid>/cmdline."""
    try:
        pid = int(open(PIDFILE).read().strip())
        os.kill(pid, 0)
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return pid if b"ws-popup.py" in f.read() else None
    except (OSError, ValueError):
        return None


def run_daemon():
    """Khởi tạo giao diện GTK Layer Shell và chạy vòng lặp sự kiện."""
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")  # thiếu dòng này có thể nạp nhầm Gdk 4 → ImportError
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, Gio, GLib, Gtk, GtkLayerShell

    try:
        gi.require_version("GioUnix", "2.0")
        from gi.repository import GioUnix
    except (ValueError, ImportError):
        GioUnix = None

    def layer_window(css_class, namespace, top, side_margin, edge="left"):
        """Tạo cửa sổ layer-shell lớp OVERLAY neo theo TOP và cạnh `edge` ('left'/'right')."""
        win = Gtk.Window()
        win.get_style_context().add_class(css_class)
        screen = win.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            win.set_visual(visual)
        win.set_app_paintable(True)
        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_namespace(win, namespace)
        GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
        side_edge = GtkLayerShell.Edge.LEFT if edge == "left" else GtkLayerShell.Edge.RIGHT
        GtkLayerShell.set_anchor(win, side_edge, True)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, top)
        GtkLayerShell.set_margin(win, side_edge, side_margin)
        GtkLayerShell.set_exclusive_zone(win, -1)
        GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
        win.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK | Gdk.EventMask.BUTTON_PRESS_MASK
        )
        return win

    class WsPopup:
        def __init__(self):
            provider = Gtk.CssProvider()
            provider.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            import kafka_theme as kt

            kt.apply(
                kt.panel(".panel", "2px", titled=True)
                + f"""
.ws {{ {kt.CARD} }}
.ws:hover {{ {kt.CARD_HOVER} }}
.ws.active {{ {kt.CARD_ON} }}
.num {{ font-family: "{kt.PIXEL_FONT}"; font-size: 21px; font-weight: normal; }}  /* 3px/điểm */
.title {{ color: {kt.PINK_FG}; }}
"""
            )

            self.in_hot = False
            self.in_pop = False
            self.timer = None
            self.probing = False
            self.hot_x = None
            self.hot_w = None
            self.scroll_acc = 0.0
            self.icon_cache = {}
            self.app_info_cache = None

            # Hotspot trong suốt neo TOP + LEFT (ẩn cho tới khi dò được vị trí lần đầu)
            self.hot = layer_window("hotspot", "kafka-ws-hotspot", HOT_TOP, 0, edge="left")
            self.hot.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
            self.hot.connect("enter-notify-event", self.on_enter, "hot")
            self.hot.connect("leave-notify-event", self.on_leave, "hot")
            self.hot.connect("button-press-event", self.on_hot_press)
            self.hot.connect("scroll-event", self.on_hot_scroll)

            # Popup chọn workspace neo TOP + LEFT
            self.pop = layer_window("popup", "kafka-ws-popup", POP_TOP, 0, edge="left")
            self.pop.connect("enter-notify-event", self.on_enter, "pop")
            self.pop.connect("leave-notify-event", self.on_leave, "pop")

            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            panel.get_style_context().add_class("panel")
            self.pop.add(panel)

            title = kt.title_label("STAGE SELECT")
            if title is None:
                title = Gtk.Label(label="Khu làm việc", xalign=0)
                title.get_style_context().add_class("title")
            panel.pack_start(title, False, False, 0)

            grid = Gtk.Grid(row_spacing=6, column_spacing=6)
            grid.set_column_homogeneous(True)  # VIII rộng hơn I → cột đều nhau
            panel.pack_start(grid, False, False, 0)

            self.cells = {}
            for i in range(1, 11):
                btn = Gtk.Button()
                btn.get_style_context().add_class("ws")
                btn.set_relief(Gtk.ReliefStyle.NONE)
                btn.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                box.set_valign(Gtk.Align.CENTER)
                num_lbl = Gtk.Label(label=roman(i))
                num_lbl.get_style_context().add_class("num")
                apps_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
                apps_box.set_halign(Gtk.Align.CENTER)
                apps_lbl = Gtk.Label(label="·")
                apps_lbl.get_style_context().add_class("apps")
                apps_box.pack_start(apps_lbl, False, False, 0)
                box.pack_start(num_lbl, False, False, 0)
                box.pack_start(apps_box, False, False, 0)
                btn.add(box)
                btn.connect("button-press-event", self.on_ws_press, i)
                btn.connect("clicked", self.on_ws_clicked, i)
                grid.attach(btn, (i - 1) % 5, (i - 1) // 5, 1, 1)
                self.cells[i] = (btn, num_lbl, apps_box, (None, None))

            self.trigger_probe()
            GLib.timeout_add(PROBE_INTERVAL_MS, self.trigger_probe)

        # ---------- dò vị trí ngang bằng grim ----------
        def trigger_probe(self):
            if self.pop.get_visible() or self.probing:
                return True
            self.probing = True
            threading.Thread(target=self._probe_worker, daemon=True).start()
            return True

        def _probe_worker(self):
            found = None
            try:
                res = subprocess.run(
                    ["grim", "-g", f"0,{PROBE_Y} {PROBE_W}x{PROBE_H}", "-t", "ppm", "-"],
                    capture_output=True,
                    timeout=2,
                )
                if res.returncode == 0 and res.stdout:
                    row = collapse_rows(parse_ppm_row(res.stdout), PROBE_W, PROBE_H, TARGET_RGB)
                    runs = find_runs(row, TARGET_RGB, 10)
                    start_end = pick_ws_run(runs)
                    if start_end:
                        start, end = start_end
                        found = (max(0, start - 12), (end - start + 1) + 24)
            except (OSError, subprocess.SubprocessError):
                pass
            GLib.idle_add(self._apply_probe, found)

        def _apply_probe(self, found):
            self.probing = False
            if found is None:
                # Không thấy ô (cửa sổ toàn màn hình che thanh, đang rê chuột trên khối Kafka…) → ẩn vùng
                # trong suốt, kẻo nó chặn chuột của app bên dưới; lần dò sau thấy lại thì hiện.
                if self.hot.get_visible() and not self.in_hot:
                    self.hot.hide()
                return False
            x, w = found
            if (x, w) != (self.hot_x, self.hot_w):
                self.hot_x, self.hot_w = x, w
                GtkLayerShell.set_margin(self.hot, GtkLayerShell.Edge.LEFT, x)
                self.hot.set_size_request(w, HOT_H)
                GtkLayerShell.set_margin(self.pop, GtkLayerShell.Edge.LEFT, x)
            if not self.hot.get_visible():
                self.hot.show_all()
            return False

        def _app_infos_by_wm_class(self):
            """Quét Gio.AppInfo.get_all() đúng một lần, lập chỉ mục theo WM class."""
            if self.app_info_cache is not None:
                return self.app_info_cache
            self.app_info_cache = {}
            for info in Gio.AppInfo.get_all():
                keys = []
                try:
                    startup_class = info.get_startup_wm_class()
                except (AttributeError, TypeError):
                    startup_class = None
                if startup_class:
                    keys.append(startup_class)
                try:
                    app_id = info.get_id()
                except (AttributeError, TypeError):
                    app_id = None
                if app_id:
                    keys.append(os.path.splitext(app_id)[0])
                for key in keys:
                    self.app_info_cache.setdefault(key.lower(), info)
            return self.app_info_cache

        def _icon_from_desktop(self, desktop_id):
            """Lấy DesktopAppInfo theo thứ tự GioUnix rồi Gio."""
            constructors = []
            if GioUnix is not None and hasattr(GioUnix, "DesktopAppInfo"):
                constructors.append(GioUnix.DesktopAppInfo)
            if hasattr(Gio, "DesktopAppInfo"):
                constructors.append(Gio.DesktopAppInfo)
            for constructor in constructors:
                try:
                    info = constructor.new(desktop_id)
                except (AttributeError, TypeError, GLib.Error):
                    info = None
                if info is not None and info.get_icon() is not None:
                    return info.get_icon()
            return None

        def app_icon(self, cls):
            """Tra Gio.Icon theo WM class, có cache cho từng class."""
            key = (cls or "").strip()
            cache_key = key.lower()
            if cache_key in self.icon_cache:
                return self.icon_cache[cache_key]

            icon = None
            for desktop_id in (f"{key}.desktop", f"{key.lower()}.desktop"):
                icon = self._icon_from_desktop(desktop_id)
                if icon is not None:
                    break
            if icon is None:
                info = self._app_infos_by_wm_class().get(cache_key)
                if info is not None:
                    icon = info.get_icon()
            if icon is None:
                theme = Gtk.IconTheme.get_default()
                for name in (key, key.lower()):
                    if name and theme.has_icon(name):
                        icon = Gio.ThemedIcon.new(name)
                        break
            if icon is None:
                icon = Gio.ThemedIcon.new("application-x-executable")
            self.icon_cache[cache_key] = icon
            return icon

        def _set_apps_box(self, apps_box, classes, extra, previous):
            signature = (tuple(classes), extra)
            if signature == previous:
                return signature
            for child in apps_box.get_children():
                apps_box.remove(child)
            if not classes:
                label = Gtk.Label(label="·")
                label.get_style_context().add_class("apps")
                apps_box.pack_start(label, False, False, 0)
            else:
                for cls in classes:
                    image = Gtk.Image.new_from_gicon(self.app_icon(cls), Gtk.IconSize.MENU)
                    image.set_pixel_size(18)
                    apps_box.pack_start(image, False, False, 0)
                if extra > 0:
                    label = Gtk.Label(label=f"+{extra}")
                    label.get_style_context().add_class("apps")
                    apps_box.pack_start(label, False, False, 0)
            apps_box.show_all()
            return signature

        # ---------- hiển thị popup ----------
        def refresh_state(self):
            clients = hypr_json("clients", [])
            act_id = active_workspace_id()
            for item in summarize(clients, act_id):
                btn, _num_lbl, apps_box, previous = self.cells[item["id"]]
                current = self._set_apps_box(apps_box, item["classes"], item["extra"], previous)
                self.cells[item["id"]] = (btn, _num_lbl, apps_box, current)
                btn.set_tooltip_text(item["tooltip"])
                ctx = btn.get_style_context()
                if item["active"]:
                    ctx.add_class("active")
                else:
                    ctx.remove_class("active")
                if item["empty"]:
                    ctx.add_class("empty")
                else:
                    ctx.remove_class("empty")

        def show(self):
            if not self.pop.get_visible():
                self.refresh_state()
                self.pop.show_all()

        def hide(self):
            self.pop.hide()

        def toggle(self):
            if self.pop.get_visible():
                self.hide()
            else:
                self.show()
            return True

        # ---------- rê chuột & bấm ----------
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
                    GLib.source_remove(self.timer)
                    self.timer = None
            else:
                self.in_pop = True
                if self.timer:
                    GLib.source_remove(self.timer)
                    self.timer = None
            return False

        def on_leave(self, _w, event, where):
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

        def on_hot_press(self, _w, event):
            if event.button == 1:
                self.toggle()
                return True
            return False

        def on_hot_scroll(self, _w, event):
            step = 0
            if event.direction == Gdk.ScrollDirection.UP:
                step = -1
            elif event.direction == Gdk.ScrollDirection.DOWN:
                step = 1
            elif event.direction == Gdk.ScrollDirection.SMOOTH:
                self.scroll_acc += event.delta_y
                if abs(self.scroll_acc) < 1.0:
                    return True
                step = 1 if self.scroll_acc > 0 else -1
                self.scroll_acc = 0.0
            if step == 0:
                return False
            cur = active_workspace_id()
            if cur < 1:
                return True
            target = max(1, min(10, cur + step))
            if target != cur:
                focus_workspace(target)
            return True

        def on_ws_press(self, _btn, event, ws_id):
            if event.button == 3:
                self.hide()
                move_window_to_workspace(ws_id)
                return True
            return False

        def on_ws_clicked(self, _btn, ws_id):
            self.hide()
            focus_workspace(ws_id)

    app = WsPopup()
    try:
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


def selftest():
    """Kiểm thử tự động các hàm thuần find_runs, summarize, roman."""
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"{'PASS' if cond else 'FAIL'}: {name}")
        if not cond:
            ok = False

    # 1. Kiểm thử roman
    check(
        "roman",
        [roman(i) for i in range(1, 11)] == ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"],
    )

    # 2. Kiểm thử find_runs: 2 đoạn hồng >= 10px + 1 đoạn ngắn < 10px bị bỏ
    bg = bytes((0x14, 0x11, 0x18))
    pk = bytes(TARGET_RGB)
    row = bg * 10 + pk * 15 + bg * 5 + pk * 7 + bg * 8 + pk * 20 + bg * 10
    runs = find_runs(row, TARGET_RGB, 10)
    check("find_runs", runs == [(10, 24), (45, 64)])

    # 2a. pick_ws_run: Kafka tách 2 đoạn + ô ws → lấy đoạn cuối; ô nhạc ở x ≥ 640 bị bỏ
    check(
        "pick_ws_run",
        pick_ws_run([(4, 90), (100, 140), (170, 210), (900, 920)]) == (170, 210)
        and pick_ws_run([(4, 90), (170, 210)]) == (170, 210)
        and pick_ws_run([(4, 90)]) is None
        and pick_ws_run([(10, 155), (183, 198), (201, 218)]) == (183, 218),
    )

    # 2b. collapse_rows: ô hồng bị chữ cắt ở hàng giữa vẫn thành 1 đoạn liền
    r0 = pk * 12
    r1 = pk * 3 + bg * 2 + pk * 2 + bg * 2 + pk * 3  # hàng có chữ
    merged = collapse_rows(r0 + r1 + r1, 12, 3)
    check("collapse_rows", find_runs(merged, TARGET_RGB, 10) == [(0, 11)] and find_runs(r1, TARGET_RGB, 10) == [])

    # 3. Kiểm thử summarize: 4 cửa sổ ở ws 1 và 3 + 1 cửa sổ ws -98 bị bỏ, và trường hợp > 3 app (+N)
    fake_clients = [
        {"class": "kitty", "workspace": {"id": 1}, "floating": False},
        {"class": "chromium", "workspace": {"id": 1}, "floating": False},
        {"class": "thunar", "workspace": {"id": 1}, "floating": True},
        {"class": "mpv", "workspace": {"id": 3}, "floating": False},
        {"class": "kitty", "workspace": {"id": -98}, "floating": True},
    ]
    summary = summarize(fake_clients, active_id=1)
    ws1, ws2, ws3 = summary[0], summary[1], summary[2]

    # Thêm kiểm thử +N khi một workspace có > 3 app khác nhau
    many_clients = fake_clients + [
        {"class": "code-oss", "workspace": {"id": 1}, "floating": False},
        {"class": "imv", "workspace": {"id": 1}, "floating": False},
    ]
    ws1_many = summarize(many_clients, active_id=1)[0]

    cond_summarize = (
        len(summary) == 10
        and ws1["active"] is True
        and ws1["empty"] is False
        and ws1["classes"] == ["kitty", "chromium", "thunar"]
        and ws1["extra"] == 0
        and ws1["apps_text"] == "kitty chromium thunar"
        and ws1["tooltip"] == "kitty, chromium, thunar"
        and summarize(fake_clients + [{"class": "kitty", "workspace": {"id": 1}}], 1)[0]["tooltip"]
        == "kitty ×2, chromium, thunar"
        and ws2["active"] is False
        and ws2["empty"] is True
        and ws2["apps_text"] == "·"
        and ws2["tooltip"] == "Trống"
        and ws3["empty"] is False
        and ws3["classes"] == ["mpv"]
        and ws3["extra"] == 0
        and ws3["apps_text"] == "mpv"
        and ws1_many["classes"] == ["kitty", "chromium", "thunar"]
        and ws1_many["extra"] == 2
        and ws1_many["apps_text"] == "kitty chromium thunar +2"
    )
    check("summarize", cond_summarize)

    if ok:
        print("OK")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()

    pid = already_running()
    if "--toggle" in sys.argv:
        if pid:
            os.kill(pid, signal.SIGUSR1)
        return 0
    if pid:
        print(f"ws-popup.py đã chạy (pid {pid})", file=sys.stderr)
        return 0

    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    return run_daemon()


if __name__ == "__main__":
    sys.exit(main())
