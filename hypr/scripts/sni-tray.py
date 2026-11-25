#!/usr/bin/env python3
"""Khay StatusNotifierItem tối giản cho dock Kafka."""

import base64
import fcntl
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, Gio, GLib, Gtk
    import cairo
except ImportError:
    Gdk = Gio = GLib = Gtk = cairo = None


REPO = Path(os.path.realpath(__file__)).parents[2]
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "kafka-dock"
TRAY_JSON = RUNTIME / "tray.json"
ICON_DIR = RUNTIME / "tray-icons"
IGNORE_IDS = {"nm-applet", "fcitx", "fcitx5"}  # đã có nút riêng (Wi-Fi trong Cài đặt nhanh, VI/EN trên thanh trên)
WATCHER = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
HOST = "org.kde.StatusNotifierHost-" + str(os.getpid())
XML = """<node>
 <interface name='org.kde.StatusNotifierWatcher'>
  <method name='RegisterStatusNotifierItem'><arg direction='in' type='s'/></method>
  <method name='RegisterStatusNotifierHost'><arg direction='in' type='s'/></method>
  <property name='RegisteredStatusNotifierItems' type='as' access='read'/>
  <property name='IsStatusNotifierHostRegistered' type='b' access='read'/>
  <property name='ProtocolVersion' type='i' access='read'/>
  <signal name='StatusNotifierItemRegistered'><arg type='s'/></signal>
  <signal name='StatusNotifierItemUnregistered'><arg type='s'/></signal>
  <signal name='StatusNotifierHostRegistered'/>
 </interface>
</node>"""


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def pixel_theme():
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    try:
        return (state / "kafka" / "ui-theme").read_text(encoding="utf-8").strip() == "pixel"
    except OSError:
        return False


def registration_key(bus, path):
    return f"{bus}|{path}"


def parse_registration(argument, sender):
    """Chuẩn hóa cả dạng bus name lẫn object path của KDE SNI."""
    value = str(argument)
    if value.startswith("/"):
        return sender, value
    return value, "/StatusNotifierItem"


def choose_pixmap(pixmaps, wanted=48):
    valid = [p for p in pixmaps if len(p) == 3 and p[0] > 0 and p[1] > 0]
    return min(valid, key=lambda p: abs(max(p[0], p[1]) - wanted), default=None)


def argb_surface(width, height, payload):
    """Đổi ARGB32 big-endian của SNI sang bộ nhớ BGRA native của cairo."""
    raw = bytes(payload)
    if width <= 0 or height <= 0 or len(raw) < width * height * 4 or cairo is None:
        return None
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    data = surface.get_data()
    out = bytearray(width * height * 4)
    for pos in range(width * height):
        a, r, g, b = raw[pos * 4 : pos * 4 + 4]
        out[pos * 4 : pos * 4 + 4] = bytes((b, g, r, a))
    data[: len(out)] = out
    surface.mark_dirty()
    return surface


def slot_plan(count):
    """Ba ô cố định; ô cuối là +N khi danh sách vượt quá sức chứa."""
    if count <= 0:
        return [None, None, None]
    if count <= 3:
        return [i + 1 if i < count else None for i in range(3)]
    return [1, 2, -(count - 2)]


def _rect(ctx, x, y, w, h, rgb):
    ctx.set_source_rgb(*rgb)
    ctx.rectangle(x, y, w, h)
    ctx.fill()


def empty_surface(pixel=True):
    if cairo is None:
        return None
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 40, 40)
    ctx = cairo.Context(surface)
    if not pixel:
        return surface
    dark = (20 / 255, 14 / 255, 26 / 255)
    inner = (29 / 255, 22 / 255, 38 / 255)
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    ctx.move_to(2, 0)
    ctx.line_to(38, 0)
    ctx.line_to(40, 2)
    ctx.line_to(40, 38)
    ctx.line_to(38, 40)
    ctx.line_to(2, 40)
    ctx.line_to(0, 38)
    ctx.line_to(0, 2)
    ctx.close_path()
    ctx.set_source_rgb(*dark)
    ctx.fill()
    _rect(ctx, 2, 2, 36, 36, inner)
    _rect(ctx, 2, 2, 36, 2, (15 / 255, 10 / 255, 20 / 255))
    _rect(ctx, 2, 2, 2, 36, (15 / 255, 10 / 255, 20 / 255))
    _rect(ctx, 2, 38, 36, 2, (74 / 255, 60 / 255, 89 / 255))
    _rect(ctx, 38, 2, 2, 36, (74 / 255, 60 / 255, 89 / 255))
    return surface


def text_surface(label, pixel=True):
    surface = empty_surface(pixel)
    if surface is None:
        return None
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*((255 / 255, 224 / 255, 138 / 255) if pixel else (251 / 255, 247 / 255, 253 / 255)))
    ctx.select_font_face("FiraCode Nerd Font", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(13)
    ext = ctx.text_extents(label)
    ctx.move_to(20 - (ext.width / 2 + ext.x_bearing), 20 - (ext.height / 2 + ext.y_bearing))
    ctx.show_text(label)
    return surface


def save_surface(surface, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    surface.write_to_png(str(path))


def _shared_slots():
    sys.path.insert(0, str(Path(os.path.realpath(__file__)).parent))
    import dock_slots

    return dock_slots


def compose_icon(item, pixel):
    """Vẽ icon cache vào ô, ở đúng vị trí 26px/28px của hai theme."""
    surface = empty_surface(pixel)
    if surface is None:
        return None
    icon_path = item.get("icon_png", "")
    if icon_path and os.path.exists(icon_path):
        try:
            icon = cairo.ImageSurface.create_from_png(icon_path)
            size = 26 if pixel else 28
            ctx = cairo.Context(surface)
            ctx.save()
            ctx.translate(7 if pixel else 6, 6)
            ctx.scale(size / icon.get_width(), size / icon.get_height())
            ctx.set_source_surface(icon, 0, 0)
            ctx.paint()
            ctx.restore()
        except Exception:
            pass
    return surface


def pixmap_icon(item):
    selected = choose_pixmap(item.get("pixmaps", []))
    if not selected:
        return None
    return argb_surface(selected[0], selected[1], selected[2])


class Tray:
    def __init__(self):
        self.items = {}
        self.bus = None
        self.node = Gio.DBusNodeInfo.new_for_xml(XML)
        self.interface = self.node.interfaces[0]
        self.subscriptions = {}

    def proxy(self, bus, path, interface="org.kde.StatusNotifierItem"):
        return Gio.DBusProxy.new_sync(self.bus, Gio.DBusProxyFlags.NONE, None, bus, path, interface, None)

    def prop(self, proxy, name, default=None):
        try:
            value = proxy.get_cached_property(name)
            return value.unpack() if value is not None else default
        except Exception:
            return default

    def read_item(self, key):
        item = self.items.get(key)
        if not item:
            return
        try:
            proxy = self.proxy(item["bus"], item["path"])
            pixmaps = []
            for entry in self.prop(proxy, "IconPixmap", []) or []:
                try:
                    w, h, data = entry
                    pixmaps.append((int(w), int(h), bytes(data)))
                except (TypeError, ValueError):
                    pass
            item.update(
                {
                    "id": str(self.prop(proxy, "Id", "")),
                    "title": str(self.prop(proxy, "Title", "")),
                    "status": str(self.prop(proxy, "Status", "Active")),
                    "icon_name": str(self.prop(proxy, "IconName", "")),
                    "icon_theme": str(self.prop(proxy, "IconThemePath", "")),
                    "pixmaps": pixmaps,
                    "menu": str(self.prop(proxy, "Menu", "/")),
                    "item_is_menu": bool(self.prop(proxy, "ItemIsMenu", False)),
                }
            )
            if not item["title"]:
                item["title"] = self.friendly_name(proxy, item)
            self.save_icon(item)
        except Exception:
            return

    def friendly_name(self, proxy, item):
        """Title rỗng (vd Discord) → tiêu đề ToolTip → tên tiến trình sở hữu bus → Id làm gọn."""
        tip = self.prop(proxy, "ToolTip", None)
        try:
            if tip and str(tip[2]).strip():
                return str(tip[2]).strip()
        except (TypeError, IndexError):
            pass
        try:
            pid = self.bus.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "GetConnectionUnixProcessID",
                GLib.Variant("(s)", (item["bus"],)),
                None,
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            ).unpack()[0]
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()
            if comm:
                return comm[:1].upper() + comm[1:]
        except Exception:
            pass
        ident = str(item.get("id") or "").split("_status_icon")[0].replace("_", " ").strip()
        return ident[:1].upper() + ident[1:]

    def save_icon(self, item):
        surface = pixmap_icon(item)
        if surface is None and Gtk is not None:
            try:
                theme = Gtk.IconTheme.get_default()
                if item.get("icon_theme") and os.path.isdir(item["icon_theme"]):
                    theme.append_search_path(item["icon_theme"])
                pixbuf = theme.load_icon(item.get("icon_name") or "application-x-executable", 48, 0)
                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 48, 48)
                Gdk.cairo_set_source_pixbuf(cairo.Context(surface), pixbuf, 0, 0)
                ctx = cairo.Context(surface)
                Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
                ctx.paint()
            except Exception:
                surface = None
        if surface is not None:
            name = base64.urlsafe_b64encode(item["key"].encode()).decode().rstrip("=") + ".png"
            item["icon_png"] = str(ICON_DIR / name)
            save_surface(surface, Path(item["icon_png"]))
        else:
            item["icon_png"] = ""

    def render(self):
        RUNTIME.mkdir(parents=True, exist_ok=True)
        ordered = sorted(
            (i for i in self.items.values() if str(i.get("id", "")).lower() not in IGNORE_IDS),
            key=lambda x: x.get("status") == "Passive",
        )
        rows = [
            {
                k: item.get(k, "")
                for k in ("key", "bus", "path", "id", "title", "status", "icon_png", "menu", "item_is_menu")
            }
            for item in ordered
        ]
        atomic_json(TRAY_JSON, rows)
        plan = slot_plan(len(ordered))
        for n, value in enumerate(plan, 1):
            image = RUNTIME / f"bg{n}.png"
            tooltip = RUNTIME / f"bg{n}.txt"
            if value is None:
                for f in (image, tooltip):  # 3 là GIỚI HẠN: ô không dùng thì ẩn
                    try:
                        f.unlink()
                    except FileNotFoundError:
                        pass
            elif value < 0:
                save_surface(_shared_slots().more_surface(-value, pixel_theme()), image)
                tooltip.write_text(f"Còn {-value} app chạy ngầm khác — bấm để xem hết", encoding="utf-8")
            else:
                item = ordered[value - 1]
                save_surface(compose_icon(item, pixel_theme()), image)
                tooltip.write_text(item.get("title") or item.get("id") or "", encoding="utf-8")
        if os.environ.get("KAFKA_DOCK_NO_SIGNAL") != "1":
            subprocess.run(
                ["pkill", "-RTMIN+20", "waybar"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

    def register(self, argument, sender):
        bus, path = parse_registration(argument, sender)
        key = registration_key(bus, path)
        if key not in self.items:
            self.items[key] = {"key": key, "bus": bus, "path": path}
            self.subscriptions[key] = self.bus.signal_subscribe(
                bus,
                "org.kde.StatusNotifierItem",
                None,
                path,
                None,
                Gio.DBusSignalFlags.NONE,
                lambda *a: self.changed(key),
            )
        self.read_item(key)
        self.render()
        self.bus.emit_signal(
            None,
            WATCHER_PATH,
            "org.kde.StatusNotifierWatcher",
            "StatusNotifierItemRegistered",
            GLib.Variant("(s)", (bus + path,)),
        )

    def changed(self, key):
        self.read_item(key)
        self.render()

    def remove_name(self, name):
        for key in list(self.items):
            if self.items[key]["bus"] == name:
                self.items.pop(key, None)
                sub = self.subscriptions.pop(key, None)
                if sub:
                    self.bus.signal_unsubscribe(sub)
                self.render()

    def method(self, connection, sender, path, interface, method, params, invocation):
        if method == "RegisterStatusNotifierItem":
            arg = params.unpack()[0]
            invocation.return_value(None)
            GLib.idle_add(lambda: (self.register(arg, sender), False)[1])
        elif method == "RegisterStatusNotifierHost":
            invocation.return_value(None)
            self.bus.emit_signal(
                None, WATCHER_PATH, "org.kde.StatusNotifierWatcher", "StatusNotifierHostRegistered", None
            )

    def get_property(self, connection, sender, path, interface, name):
        if name == "RegisteredStatusNotifierItems":
            return GLib.Variant("as", list(self.items))
        if name == "IsStatusNotifierHostRegistered":
            return GLib.Variant("b", True)
        return GLib.Variant("i", 0)

    def own(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.bus.register_object(WATCHER_PATH, self.interface, self.method, self.get_property, None)
        self.bus.signal_subscribe(
            "org.freedesktop.DBus",
            "org.freedesktop.DBus",
            "NameOwnerChanged",
            "/org/freedesktop/DBus",
            None,
            Gio.DBusSignalFlags.NONE,
            self.owner_changed,
        )
        self.bus.emit_signal(None, WATCHER_PATH, "org.kde.StatusNotifierWatcher", "StatusNotifierHostRegistered", None)
        self.render()

    def owner_changed(self, _bus, _sender, _path, _iface, _signal, params):
        name, old, new = params.unpack()
        if old and not new:
            self.remove_name(name)


def run_dbus_call(bus, path, method, signature="", args=()):
    if Gio is None:
        return False
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        connection.call_sync(
            bus,
            path,
            "org.kde.StatusNotifierItem",
            method,
            GLib.Variant("(" + signature + ")", args),
            None,
            Gio.DBusCallFlags.NONE,
            1500,
            None,
        )
        return True
    except Exception:
        return False


def dock_more(*args):
    subprocess.Popen([sys.executable, str(REPO / "hypr/scripts/dock-more.py"), *args], start_new_session=True)


def read_rows():
    try:
        return json.loads(TRAY_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def action(slot, right=False):
    rows = read_rows()
    plan = slot_plan(len(rows))
    if not 1 <= slot <= 3:
        return
    value = plan[slot - 1]
    if value is None:
        return
    if value < 0:
        return dock_more("--section", "bg")
    item = rows[value - 1]
    if right or item.get("item_is_menu"):
        return dock_more("--menu", item.get("key", ""))
    bus, path = item.get("bus"), item.get("path")
    if not run_dbus_call(bus, path, "Activate", "ii", (0, 0)):
        dock_more("--menu", item.get("key", ""))


def selftest():
    assert argb_surface(1, 1, bytes((255, 255, 0, 0))) is not None
    assert choose_pixmap([(32, 32, b""), (48, 48, b""), (64, 64, b"")])[0] == 48
    assert parse_registration("org.example.App", ":1.5") == ("org.example.App", "/StatusNotifierItem")
    assert parse_registration("/Custom", ":1.5") == (":1.5", "/Custom")
    assert slot_plan(0) == [None, None, None]
    assert slot_plan(3) == [1, 2, 3]
    assert slot_plan(7) == [1, 2, -5]
    # Một số sandbox mount XDG_RUNTIME_DIR chỉ đọc; khi đó dùng /tmp nhưng
    # vẫn kiểm tra đúng thao tác ghi PNG mà daemon dùng.
    target_dir = RUNTIME if os.access(RUNTIME, os.W_OK) else Path(tempfile.gettempdir())
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp = target_dir / f".sni-selftest-{os.getpid()}.png"
    save_surface(empty_surface(True), tmp)
    assert tmp.stat().st_size > 0
    tmp.unlink()
    print("sni-tray.py selftest OK")


def daemon():
    if Gio is None:
        raise RuntimeError("PyGObject/cairo không khả dụng")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    lock = open(Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "kafka-sni-tray.lock", "w", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0
    tray = Tray()
    loop = GLib.MainLoop()
    import signal as _signal

    # SIGUSR1 = vẽ lại 3 ô (ui-theme.sh gửi khi đổi phẳng ⇄ pixel)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, _signal.SIGUSR1, lambda: (tray.bus and tray.render(), True)[1])
    Gio.bus_own_name(Gio.BusType.SESSION, WATCHER, Gio.BusNameOwnerFlags.NONE, lambda *_: tray.own(), None)
    Gio.bus_own_name(Gio.BusType.SESSION, HOST, Gio.BusNameOwnerFlags.NONE, lambda *_: None, None)
    loop.run()
    return 0


def main(argv):
    if argv == ["--selftest"]:
        selftest()
        return 0
    if argv == ["daemon"]:
        return daemon()
    if len(argv) == 2 and argv[0] in {"slot", "click", "rclick"}:
        n = int(argv[1])
        if argv[0] == "slot":
            path = RUNTIME / f"bg{n}.png"
            tip = RUNTIME / f"bg{n}.txt"
            if path.exists():
                print(path)
                print(tip.read_text(encoding="utf-8") if tip.exists() else "")
            else:
                print()
        else:
            action(n, argv[0] == "rclick")
        return 0
    if len(argv) == 2 and argv[0] == "activate":
        for row in read_rows():
            if row.get("key") == argv[1]:
                if not run_dbus_call(row.get("bus"), row.get("path"), "Activate", "ii", (0, 0)):
                    dock_more("--menu", argv[1])
                return 0
    if argv == ["list"]:
        try:
            print(TRAY_JSON.read_text(encoding="utf-8"), end="")
        except OSError:
            print("[]")
        return 0
    print("Sử dụng: daemon | slot N | click N | rclick N | activate KEY | list | --selftest", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
