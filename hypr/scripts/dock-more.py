#!/usr/bin/env python3
"""Popup xem toàn bộ ứng dụng của dock Kafka."""

import argparse
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, Gio, GLib, Gtk, GtkLayerShell, GdkPixbuf, Pango  # noqa: E402


HERE = Path(os.path.realpath(__file__)).parent
REPO = HERE.parent.parent
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "kafka-dock"
PIDFILE = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "kafka-dock-more.pid"
SCRIPTS = str(HERE)
ROMANS = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


def run(cmd, timeout=3):
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def hypr_json(*args):
    p = run(["hyprctl", *args])
    if not p or p.returncode:
        return None
    try:
        return json.loads(p.stdout)
    except (TypeError, ValueError):
        return None


def no_mnemonic(text):
    """Bỏ dấu gạch dưới mnemonic của dbusmenu."""
    return re.sub(r"_([^_])", r"\1", str(text or "")).replace("__", "_")


def roman(number):
    try:
        number = int(number)
    except (TypeError, ValueError):
        return str(number)
    return ROMANS[number] if 0 <= number < len(ROMANS) else str(number)


def unwrap(value):
    return unwrap(value.unpack()) if isinstance(value, GLib.Variant) else value


def menu_tree(layout):
    """Đổi cây GetLayout (ia{sv}av) thành các dict thuần dễ dựng widget."""
    layout = unwrap(layout)
    if not isinstance(layout, (tuple, list)) or len(layout) < 3:
        return None
    ident, props, children = layout[0], unwrap(layout[1]), layout[2]
    props = {str(k): unwrap(v) for k, v in (props or {}).items()}
    node = {"id": int(ident), "label": no_mnemonic(props.get("label", "")),
            "type": str(props.get("type", "standard")),
            "visible": props.get("visible", True) is not False,
            "enabled": props.get("enabled", True) is not False,
            "toggle_type": str(props.get("toggle-type", "")),
            "toggle_state": int(props.get("toggle-state", 0) or 0),
            "children": []}
    for child in unwrap(children) or []:
        item = menu_tree(child)
        if item is not None:
            node["children"].append(item)
    return node


def group_clients(clients):
    """Gộp cửa sổ theo class, giữ cửa sổ có focusHistoryID nhỏ nhất làm đại diện."""
    groups = OrderedDict()
    for client in clients or []:
        cls = str(client.get("class") or "").strip()
        ws = client.get("workspace") or {}
        if not cls or client.get("mapped") is False or str(ws.get("name", "")).startswith("special:"):
            continue
        if cls == "kafka-cava":
            continue
        groups.setdefault(cls, []).append(client)
    return [{"class": cls, "clients": sorted(items, key=lambda c: int(c.get("focusHistoryID", 10**9)))}
            for cls, items in groups.items()]


def hidden_clients(clients):
    return [c for c in clients or [] if (c.get("workspace") or {}).get("name") == "special:hidden"]


def icon_widget(pixbuf, size=28):
    image = Gtk.Image()
    if pixbuf:
        image.set_from_pixbuf(pixbuf.scale_simple(size, size, 2))
    else:
        image.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
    image.set_size_request(size, size)
    return image


def load_dock_apps():
    path = HERE / "dock-apps.py"
    spec = importlib.util.spec_from_file_location("kafka_dock_apps", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def desktop_name(cls):
    try:
        for name in (f"{cls}.desktop", f"{cls.lower()}.desktop"):
            app = Gio.DesktopAppInfo.new(name)
            if app:
                return app.get_name() or cls
    except Exception:
        pass
    return cls


def dispatch_focus(address):
    expr = f'hl.dsp.focus({{ window = {json.dumps("address:" + str(address))} }})'
    run(["hyprctl", "dispatch", expr])


def dispatch_close(address):
    expr = f'hl.dsp.window.close({{ window = {json.dumps("address:" + str(address))} }})'
    run(["hyprctl", "dispatch", expr])


def no_warps_enabled():
    result = run(["hyprctl", "repl", 'return hl.get_config("cursor.no_warps")'])
    return bool(result and result.returncode == 0 and result.stdout.strip().startswith("true"))


def focus_group(cls):
    """Focus cửa sổ kế tiếp của class, cùng quy tắc với dispatch_for()."""
    clients = hypr_json("clients", "-j") or []
    members = [c for c in clients if c.get("class") == cls and c.get("mapped") is not False
               and not str((c.get("workspace") or {}).get("name", "")).startswith("special:")]
    if not members:
        return
    active = hypr_json("activewindow", "-j") or {}
    members.sort(key=lambda c: str(c.get("address", "")))
    addresses = [str(c.get("address", "")) for c in members]
    current = str(active.get("address", ""))
    target = members[(addresses.index(current) + 1) % len(members)] if current in addresses else min(
        members, key=lambda c: int(c.get("focusHistoryID", 10**9)))
    if no_warps_enabled():
        dispatch_focus(target.get("address"))
        return
    run(["hyprctl", "eval", 'hl.config({ cursor = { no_warps = true } })'])
    try:
        dispatch_focus(target.get("address"))
    finally:
        time.sleep(0.15)
        run(["hyprctl", "eval", 'hl.config({ cursor = { no_warps = false } })'])


def close_group(cls):
    clients = hypr_json("clients", "-j") or []
    members = [c for c in clients if c.get("class") == cls and c.get("mapped") is not False]
    target = min(members, key=lambda c: int(c.get("focusHistoryID", 10**9)), default=None)
    if target:
        dispatch_close(target.get("address"))


def show_hidden(address):
    ws = hypr_json("activeworkspace") or {}
    workspace = ws.get("name") or ws.get("id")
    if workspace is None:
        return
    expr = (f'hl.dsp.window.move({{ workspace = {json.dumps(workspace)}, '
            f'window = {json.dumps("address:" + str(address))}, follow = false }})')
    run(["hyprctl", "dispatch", expr])


def tray_items():
    try:
        value = json.loads((RUNTIME / "tray.json").read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, ValueError, TypeError):
        return []


def daemon_action(fn):
    threading.Thread(target=fn, daemon=True).start()


class Popup(Gtk.Window):
    def __init__(self, section=None, menu_key=None):
        super().__init__(title="kafka-dock-more")
        self.section = section
        self.menu_key = menu_key
        self.menu_stack = []
        self.apps = None
        self.provider = Gtk.CssProvider()
        self.provider.load_from_data(self.css().encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        import kafka_theme as kt
        self.pixel = kt.apply(kt.panel(".panel", "8px", titled=True) + f"""
            .panel {{ {kt.CARD_FLAT} }} .row {{ {kt.CARD} }} .row:hover {{ {kt.CARD_HOVER} }}
            .back {{ {kt.CARD_ON} }} .muted {{ color: {kt.FAINT}; }}
        """)
        self.kt = kt
        self.set_decorated(False)
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, "kafka-dock-more")
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)
        GtkLayerShell.set_exclusive_zone(self, -1)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("button-press-event", self.outside_click)
        self.connect("key-press-event", self.key_press)
        self.build()

    @staticmethod
    def css():
        return """
        * { font-family: 'FiraCode Nerd Font'; color: #fbf7fd; }
        window { background: transparent; }
        .panel { min-width: 380px; margin: 48px 56px 0 0; padding: 12px; background: rgba(30,24,38,.96);
                 border: 1px solid #382b47; border-radius: 14px; }
        .title { font-size: 14px; font-weight: bold; color: #f4eef8; padding: 2px 4px 8px; }
        .section { font-size: 11px; font-weight: bold; color: #c77dff; padding: 9px 4px 4px; }
        .row { min-height: 40px; padding: 4px 7px; border-radius: 10px; background: rgba(255,255,255,.06); }
        .row:hover { background: rgba(199,125,255,.18); }
        .name { font-weight: bold; } .sub, .muted { color: #a99bbd; font-size: 10px; }
        button { border: none; background: transparent; padding: 2px 7px; }
        button:hover { background: rgba(199,125,255,.22); }
        scrolledwindow { background: transparent; }
        """

    def outside_click(self, _widget, event):
        # Cửa sổ phủ toàn màn hình; chỉ đóng khi click vùng ngoài panel.
        a = self.outer.get_allocation()
        if not (a.x <= event.x <= a.x + a.width and a.y <= event.y <= a.y + a.height):
            Gtk.main_quit()
        return False

    def key_press(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            if self.menu_stack:
                self.menu_stack.pop()
                self.build_menu(self.menu_stack[-1] if self.menu_stack else self.menu_key)
            else:
                Gtk.main_quit()
            return True
        return False

    def add_label(self, box, text, css=""):
        label = Gtk.Label(label=text, xalign=0)
        if css:
            label.get_style_context().add_class(css)
        box.pack_start(label, False, False, 0)
        return label

    def build(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.get_style_context().add_class("panel")
        # cửa sổ phủ cả màn hình → khung phải canh góc phải-trên, rộng cố định, không thì giãn hết màn hình
        outer.set_halign(Gtk.Align.END)
        outer.set_valign(Gtk.Align.START)
        outer.set_size_request(380, -1)
        self.outer = outer
        self.add(outer)
        title = self.kt.title_label("APPS") if self.pixel else None
        if title:
            outer.pack_start(title, False, False, 0)
        else:
            self.add_label(outer, "APPS", "title")
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_max_content_height(700)
        scroll.set_propagate_natural_height(True)     # cao theo nội dung, tối đa 700 rồi cuộn
        scroll.add(self.content)
        outer.pack_start(scroll, True, True, 0)
        if self.menu_key:
            self.build_menu(self.menu_key)
        else:
            self.build_sections()

    def section_title(self, text):
        self.add_label(self.content, text, "section")

    def row(self, pixbuf, title, subtitle, left=None, right=None, right_text=""):
        """Một dòng: bấm CẢ dòng = hành động chính (left); nút nhỏ bên phải = hành động phụ (right: đóng / menu)."""
        ev = Gtk.EventBox()
        ev.set_above_child(False)
        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        line.get_style_context().add_class("row")
        line.pack_start(icon_widget(pixbuf), False, False, 0)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        labels.set_valign(Gtk.Align.CENTER)
        self.add_label(labels, title, "name")
        if subtitle:
            self.add_label(labels, subtitle, "sub")
        line.pack_start(labels, True, True, 0)
        if right:
            b = Gtk.Button(label=right_text or "×")
            b.set_tooltip_text("Menu của app" if right_text == "⋮" else "Đóng")
            b.connect("clicked", lambda *_: right() if right_text == "⋮" else daemon_action(right))
            line.pack_end(b, False, False, 0)
        ev.add(line)

        def on_press(_w, e):
            if e.button == 1 and left:
                daemon_action(left)
            elif e.button == 2 and right and right_text != "⋮":
                daemon_action(right)
            elif e.button == 3 and right and right_text == "⋮":
                right()
            return True
        ev.connect("button-press-event", on_press)
        ev.connect("enter-notify-event", lambda *_: line.set_state_flags(Gtk.StateFlags.PRELIGHT, False))
        ev.connect("leave-notify-event", lambda *_: line.unset_state_flags(Gtk.StateFlags.PRELIGHT))
        self.content.pack_start(ev, False, False, 0)

    def build_sections(self):
        clients = hypr_json("clients", "-j") or []
        hidden = hidden_clients(clients)
        groups = group_clients(clients)
        apps = None
        try:
            apps = load_dock_apps()
            theme = Gtk.IconTheme.get_default()
        except Exception:
            theme = Gtk.IconTheme.get_default()
        self.section_title("Đang mở")
        if not groups:
            self.add_label(self.content, "Không có", "muted")
        for group in groups:
            cls, items = group["class"], group["clients"]
            c = items[0]
            pix = None
            if apps:
                try:
                    pix = apps.icon_candidate(cls, {}, theme)
                except Exception:
                    pass
            ws = (c.get("workspace") or {}).get("id", "?")
            title = desktop_name(cls) + (f" ×{len(items)}" if len(items) > 1 else "")
            self.row(pix, title, f"Khu {roman(ws)}", lambda name=cls: (focus_group(name), GLib.idle_add(Gtk.main_quit)),
                     lambda name=cls: (close_group(name), GLib.idle_add(Gtk.main_quit)))

        self.section_title("Chạy ngầm")
        tray = tray_items()
        if self.section == "bg":
            tray = tray
        if not tray:
            self.add_label(self.content, "Không có", "muted")
        for item in tray:
            key = str(item.get("key", ""))
            pix = None
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(item.get("icon_png", ""), 28, 28, True)
            except Exception:
                pass
            self.row(pix, item.get("title") or item.get("id") or key, "", 
                     lambda k=key: (run([str(HERE / "sni-tray.py"), "activate", k]), GLib.idle_add(Gtk.main_quit)),
                     lambda k=key: self.show_item_menu(k), "⋮")

        self.section_title("Đang ẩn")
        if not hidden:
            self.add_label(self.content, "Không có", "muted")
        for c in hidden:
            self.row(None, c.get("title") or c.get("class") or "?", "Đang ẩn — bấm để hiện",
                     lambda a=c.get("address"): (show_hidden(a), GLib.idle_add(Gtk.main_quit)))

    def show_item_menu(self, key):
        self.menu_key = key
        self.menu_stack = []
        self.build_menu(key)

    def clear_content(self):
        for child in self.content.get_children():
            self.content.remove(child)
            child.destroy()

    def menu_proxy(self, key):
        for item in tray_items():
            if item.get("key") == key:
                bus, path = item.get("bus"), item.get("path")
                try:
                    return Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE,
                        None, bus, item.get("menu") or path, "com.canonical.dbusmenu", None)
                except Exception:
                    return None
        return None

    def build_menu(self, key_or_node):
        self.clear_content()
        back = Gtk.Button(label="‹ Quay lại")
        back.connect("clicked", lambda *_: (self.menu_stack.pop() if self.menu_stack else None,
                                              (self.clear_content(), self.build_sections(), self.show_all()) if not self.menu_stack
                                              else self.build_menu(self.menu_stack[-1])))
        self.content.pack_start(back, False, False, 0)
        key = self.menu_key
        node_id = 0 if not isinstance(key_or_node, dict) else key_or_node["id"]
        proxy = self.menu_proxy(key)
        if not proxy:
            self.add_label(self.content, "Không có menu", "muted")
            self.show_all()
            return
        try:
            try:
                proxy.call_sync("AboutToShow", GLib.Variant("(i)", (node_id,)), Gio.DBusCallFlags.NONE, 1000, None)
            except Exception:
                pass
            result = proxy.call_sync("GetLayout", GLib.Variant("(iias)", (node_id, -1, [])), Gio.DBusCallFlags.NONE, 3000, None)
            root = menu_tree(result.unpack()[1])   # GetLayout trả (u revision, (ia{sv}av) layout)
        except Exception:
            root = None
        for item in (root or {}).get("children", []):
            if not item.get("visible"):
                continue
            if item["type"] == "separator":
                self.add_label(self.content, "────────", "muted")
                continue
            label = item["label"] or "(không tên)"
            if item["toggle_type"] in ("checkmark", "radio"):
                label = ("☑ " if item["toggle_state"] else "☐ ") + label
            b = Gtk.Button(label=label, xalign=0)
            if not item["enabled"]:
                b.set_sensitive(False)
            if item["children"]:
                b.set_label(label + "  ›")
                b.connect("clicked", lambda _b, n=item: (self.menu_stack.append(n), self.build_menu(n)))
            else:
                b.connect("clicked", lambda _b, ident=item["id"]: self.menu_click(proxy, ident))
            self.content.pack_start(b, False, False, 0)
        self.show_all()

    def menu_click(self, proxy, ident):
        def click():
            try:
                proxy.call_sync("Event", GLib.Variant("(isvu)", (ident, "clicked", GLib.Variant("i", 0), int(time.time()))),
                                Gio.DBusCallFlags.NONE, 2000, None)
            except Exception:
                pass
            GLib.idle_add(Gtk.main_quit)
        daemon_action(click)


def acquire_singleton():
    """Một bản: đang mở (pid còn sống VÀ đúng là dock-more) → đóng bản đó, trả False. Pid cũ đã chết → bỏ qua."""
    try:
        old = int(PIDFILE.read_text().strip())
    except (OSError, ValueError):
        old = 0
    if old and old != os.getpid():
        try:
            with open(f"/proc/{old}/cmdline", "rb") as f:
                alive = b"dock-more" in f.read()
        except OSError:
            alive = False
        if alive:
            try:
                os.kill(old, signal.SIGTERM)
            except ProcessLookupError:
                pass
            return False
    PIDFILE.write_text(str(os.getpid()), encoding="ascii")
    import atexit

    def _cleanup():
        try:
            if PIDFILE.read_text().strip() == str(os.getpid()):
                PIDFILE.unlink()
        except OSError:
            pass
    atexit.register(_cleanup)
    return True


def selftest():
    assert no_mnemonic("E_xit __now") == "Exit _now"
    assert roman(1) == "I" and roman(10) == "X"
    sample = GLib.Variant("(ia{sv}av)", (0, {"label": GLib.Variant("s", "_File")}, []))
    assert menu_tree(sample)["label"] == "File"
    grouped = group_clients([{"class": "a", "workspace": {"id": 1}, "focusHistoryID": 2},
                             {"class": "a", "workspace": {"id": 1}, "focusHistoryID": 1}])
    assert len(grouped) == 1 and len(grouped[0]["clients"]) == 2
    assert hidden_clients([{"workspace": {"name": "special:hidden"}}])
    print("dock-more.py selftest OK")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", choices=("run", "bg", "hidden"))
    parser.add_argument("--menu")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not acquire_singleton():
        return
    try:
        win = Popup(args.section, args.menu)
        win.show_all()
        Gtk.main()
    finally:
        try:
            if PIDFILE.read_text().strip() == str(os.getpid()):
                PIDFILE.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
