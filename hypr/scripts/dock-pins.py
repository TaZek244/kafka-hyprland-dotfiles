#!/usr/bin/env python3
"""Vẽ các ứng dụng được ghim trên dock Waybar."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


MAX_SLOTS = 6  # ngăn FAV: TỐI ĐA 6 app ghim (người dùng 2026-11-22); ô không dùng thì ẩn
OUT_PX = 40
SCRIPT = Path(os.path.realpath(__file__))
REPO = SCRIPT.parents[2]
PINS_FILE = Path(os.environ.get("KAFKA_DOCK_PINS", REPO / "waybar" / "dock-pins.json"))
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "kafka-dock"


# GTK phải được yêu cầu đúng phiên bản trước khi nạp các namespace của PyGObject.
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, Gtk

try:
    gi.require_version("GioUnix", "2.0")
    from gi.repository import GioUnix

    DesktopAppInfo = GioUnix.DesktopAppInfo
except (ImportError, ValueError):
    DesktopAppInfo = Gio.DesktopAppInfo


def pixel_theme_enabled():
    """Kiểm tra theme pixel của Kafka."""
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    try:
        return (state_home / "kafka" / "ui-theme").read_text(encoding="utf-8").strip() == "pixel"
    except OSError:
        return False


def load_pins():
    """Đọc tối đa mười desktop ID từ tệp cấu hình."""
    try:
        with PINS_FILE.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError, TypeError):
        return []
    pins = value.get("pins", []) if isinstance(value, dict) else []
    if not isinstance(pins, list):
        return []
    return [str(item).strip() for item in pins[:MAX_SLOTS] if str(item).strip()]


def app_info(desktop_id):
    """Tìm DesktopAppInfo theo ID, ưu tiên GioUnix trên hệ thống mới."""
    try:
        return DesktopAppInfo.new(desktop_id)
    except Exception:
        return None


def app_icon(app):
    """Lấy GIcon của ứng dụng và thông tin tên/đường dẫn cho JSON."""
    if app is None:
        return None
    try:
        icon = app.get_icon()
    except Exception:
        return None
    if icon is None:
        return None
    try:
        names = icon.get_names()
        if names:
            return names[0]
    except (AttributeError, TypeError):
        pass
    try:
        return icon.get_filename()
    except (AttributeError, TypeError):
        return None


def resolve_icon(app, theme):
    """Tra icon theme bằng GIcon, có placeholder chuẩn nếu không tìm thấy."""
    gicon = app.get_icon() if app is not None else None
    if gicon is None:
        gicon = Gio.ThemedIcon.new("application-x-executable")
    info = theme.lookup_by_gicon(gicon, 48, Gtk.IconLookupFlags.FORCE_SIZE)
    if info is None:
        info = theme.lookup_icon("application-x-executable", 48, Gtk.IconLookupFlags.FORCE_SIZE)
    try:
        return info.load_icon() if info is not None else None
    except Exception:
        # Một số môi trường headless không cho phép GdkPixbuf nạp qua D-Bus.
        return None


def write_atomic(path, writer):
    """Ghi file qua file tạm rồi thay thế nguyên tử."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    try:
        writer(temp_name)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def pixel_icon(context, pixbuf, size=26, x=7, y=6):
    """Vẽ icon bằng bộ lọc tốt nhất, giống dock-apps.py."""
    if pixbuf is None:
        return
    context.save()
    context.translate(x, y)
    context.scale(size / pixbuf.get_width(), size / pixbuf.get_height())
    Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, 0)
    context.get_source().set_filter(__import__("cairo").FILTER_BEST)
    context.paint()
    context.restore()


def render_surface(app):
    """Tạo ảnh ARGB 40x40 theo theme pixel hoặc flat."""
    import cairo

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, OUT_PX, OUT_PX)
    context = cairo.Context(surface)
    # Khi chạy headless, get_default() có thể không có GdkScreen; theme rỗng
    # vẫn cho phép tạo PNG hợp lệ và sẽ dùng placeholder nếu không tra được icon.
    theme = Gtk.IconTheme.get_default() or Gtk.IconTheme.new()
    pixbuf = resolve_icon(app, theme)
    if pixel_theme_enabled():
        context.set_antialias(cairo.ANTIALIAS_NONE)

        def rect(x, y, w, h, color):
            context.set_source_rgb(*color)
            context.rectangle(x, y, w, h)
            context.fill()

        dark = (20 / 255, 14 / 255, 26 / 255)
        inner = (29 / 255, 22 / 255, 38 / 255)
        context.set_source_rgb(*dark)
        context.move_to(2, 0)
        context.line_to(38, 0)
        context.line_to(40, 2)
        context.line_to(40, 38)
        context.line_to(38, 40)
        context.line_to(2, 40)
        context.line_to(0, 38)
        context.line_to(0, 2)
        context.close_path()
        context.fill()
        rect(2, 2, 36, 36, inner)
        rect(2, 2, 36, 2, (15 / 255, 10 / 255, 20 / 255))
        rect(2, 2, 2, 36, (15 / 255, 10 / 255, 20 / 255))
        rect(2, 38, 36, 2, (74 / 255, 60 / 255, 89 / 255))
        rect(38, 2, 2, 36, (74 / 255, 60 / 255, 89 / 255))
        pixel_icon(context, pixbuf)
    else:
        pixel_icon(context, pixbuf, size=28, x=6, y=6)
    return surface


def write_png(path, app):
    """Ghi PNG qua đường dẫn tạm để Waybar không thấy file dở dang."""
    surface = render_surface(app)
    write_atomic(path, surface.write_to_png)


def render(signal=True):
    """Vẽ các pin hiện có và dọn các slot thừa."""
    pins = [(desktop_id, app_info(desktop_id)) for desktop_id in load_pins()]
    pins = [(desktop_id, app) for desktop_id, app in pins if app is not None]
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    for index, (desktop_id, app) in enumerate(pins, 1):
        write_png(RUNTIME_DIR / f"pin{index}.png", app)
        name = app.get_name() or desktop_id
        write_atomic(
            RUNTIME_DIR / f"pin{index}.txt",
            lambda path, value=str(name): Path(path).write_text(value.replace("\n", " "), encoding="utf-8"),
        )
    for index in range(len(pins) + 1, MAX_SLOTS + 1):
        # 6 là GIỚI HẠN: ô không có app thì xoá ảnh → Waybar ẩn ô
        for suffix in ("png", "txt"):
            try:
                (RUNTIME_DIR / f"pin{index}.{suffix}").unlink()
            except FileNotFoundError:
                pass
    if signal and not os.environ.get("KAFKA_DOCK_NO_SIGNAL"):
        subprocess.run(
            ["pkill", "-RTMIN+19", "waybar"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
    return pins


def command_slot(index):
    """In đường dẫn ảnh và tooltip cho module image của Waybar."""
    if not (RUNTIME_DIR / f"pin{index}.png").exists():
        render(signal=False)
    png = RUNTIME_DIR / f"pin{index}.png"
    txt = RUNTIME_DIR / f"pin{index}.txt"
    if not png.exists() or not txt.exists():
        print()
        return
    print(png)
    print(txt.read_text(encoding="utf-8").replace("\n", " ").strip())


def command_click(index):
    """Khởi chạy pin tách khỏi tiến trình Waybar."""
    pins = load_pins()
    valid = [(desktop_id, app_info(desktop_id)) for desktop_id in pins]
    valid = [(desktop_id, app) for desktop_id, app in valid if app is not None]
    if not 1 <= index <= len(valid):
        return
    desktop_id, app = valid[index - 1]
    try:
        subprocess.Popen(
            ["gtk-launch", desktop_id[:-8] if desktop_id.endswith(".desktop") else desktop_id],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, FileNotFoundError):
        try:
            app.launch([], None)
        except Exception:
            pass


def command_list():
    """In thông tin pin, bao gồm cả ID không tồn tại."""
    result = []
    for desktop_id in load_pins():
        app = app_info(desktop_id)
        result.append(
            {
                "id": desktop_id,
                "name": app.get_name() if app else desktop_id,
                "icon": app_icon(app),
                "exists": app is not None,
            }
        )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


def command_apps():
    """In danh sách ứng dụng hiện được để giao diện chọn app sử dụng."""
    result = []
    for app in Gio.AppInfo.get_all():
        try:
            if not app.should_show():
                continue
            result.append(
                {
                    "id": app.get_id() or "",
                    "name": app.get_name() or "",
                    "icon": app_icon(app),
                    "generic": app.get_generic_name() or "",
                    "exec": app.get_commandline() or "",
                }
            )
        except Exception:
            continue
    result.sort(key=lambda item: item["name"].casefold())
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


def selftest():
    """Tự kiểm tra độc lập, không phát tín hiệu làm Waybar reload."""
    with tempfile.TemporaryDirectory(prefix="kafka-dock-test-") as temp:
        root = Path(temp)
        old_pins, old_runtime = os.environ.get("KAFKA_DOCK_PINS"), os.environ.get("XDG_RUNTIME_DIR")
        try:
            apps = [app.get_id() for app in Gio.AppInfo.get_all() if app.get_id() and app.should_show()]
            existing = next((item for item in apps if item.endswith(".desktop")), "application-x-executable.desktop")
            pins = root / "pins.json"
            pins.write_text(json.dumps({"pins": [existing, "definitely-missing-kafka.desktop"]}), encoding="utf-8")
            os.environ["KAFKA_DOCK_PINS"] = str(pins)
            os.environ["XDG_RUNTIME_DIR"] = str(root / "runtime")
            os.environ["KAFKA_DOCK_NO_SIGNAL"] = "1"
            globals()["PINS_FILE"] = Path(os.environ["KAFKA_DOCK_PINS"])
            globals()["RUNTIME_DIR"] = Path(os.environ["XDG_RUNTIME_DIR"]) / "kafka-dock"
            rendered = render(signal=False)
            assert len(rendered) == 1
            assert (RUNTIME_DIR / "pin1.png").exists()
            assert not (RUNTIME_DIR / "pin2.png").exists()
            import struct

            png_header = (RUNTIME_DIR / "pin1.png").read_bytes()
            assert png_header[:8] == b"\x89PNG\r\n\x1a\n"
            width, height = struct.unpack(">II", png_header[16:24])
            assert (width, height) == (40, 40)
            slot = subprocess.run(
                [sys.executable, str(SCRIPT), "slot", "2"], capture_output=True, text=True, env=os.environ, check=True
            )
            assert slot.stdout.strip() == ""
            list_result = subprocess.run(
                [sys.executable, str(SCRIPT), "list"], capture_output=True, text=True, env=os.environ, check=True
            )
            apps_result = subprocess.run(
                [sys.executable, str(SCRIPT), "apps"], capture_output=True, text=True, env=os.environ, check=True
            )
            listed = json.loads(list_result.stdout)
            installed = json.loads(apps_result.stdout)
            assert isinstance(listed, list) and len(listed) == 2
            assert listed[1]["exists"] is False
            assert isinstance(installed, list)
            print("dock-pins.py selftest OK")
        finally:
            if old_pins is None:
                os.environ.pop("KAFKA_DOCK_PINS", None)
            else:
                os.environ["KAFKA_DOCK_PINS"] = old_pins
            if old_runtime is None:
                os.environ.pop("XDG_RUNTIME_DIR", None)
            else:
                os.environ["XDG_RUNTIME_DIR"] = old_runtime
            os.environ.pop("KAFKA_DOCK_NO_SIGNAL", None)


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        selftest()
        return
    command = sys.argv[1] if len(sys.argv) > 1 else "render"
    if command == "render":
        render()
    elif command in {"slot", "click"} and len(sys.argv) == 3 and sys.argv[2].isdigit():
        index = int(sys.argv[2])
        if 1 <= index <= MAX_SLOTS:
            command_slot(index) if command == "slot" else command_click(index)
    elif command == "list":
        command_list()
    elif command == "apps":
        command_apps()
    else:
        raise SystemExit("Cách dùng: render | slot N | click N | list | apps | --selftest")


if __name__ == "__main__":
    main()
