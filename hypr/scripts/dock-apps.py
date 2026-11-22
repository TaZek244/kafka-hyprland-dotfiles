#!/usr/bin/env python3
"""Dock ứng dụng gộp theo class cho Waybar và Hyprland."""

import json
import os
import subprocess
import sys
import tempfile
import time
from collections import OrderedDict
from pathlib import Path


MAX_SLOTS = 4      # ngăn RUN: TỐI ĐA 4 ô (người dùng 2026-11-22); > 4 app → ô 4 = "+N" mở dock-more.py
VISIBLE_MIN = 50
OUT_PX = 40   # cỡ ảnh thật trên dock (dock rộng 48 = lề 4 + 40 + 4); vẽ ở 48 rồi thu   # px: cột chỉ thò mép vào màn hình vẫn tính là khuất
IGNORE = {"kafka-cava"}
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "kafka-dock"


def pixel_theme_enabled():
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    try:
        return (state_home / "kafka" / "ui-theme").read_text(encoding="utf-8").strip() == "pixel"
    except OSError:
        return False


def workspace_an(n):
    """True nếu cửa sổ nằm ở workspace đặc biệt (special:, ví dụ cửa sổ đang ẩn) -> không hiện."""
    workspace = n.get("workspace") or {}
    try:
        workspace_id = int(workspace.get("id", -1))
    except (TypeError, ValueError):
        return True
    return workspace_id < 0 or str(workspace.get("name", "")).startswith("special:")


def hop_le(n):
    """Kiểm tra một client có thuộc danh sách cần hiển thị không."""
    cls = str(n.get("class") or "").strip()
    return (
        not workspace_an(n)
        and bool(cls)
        and cls not in IGNORE
        and n.get("mapped") is not False
    )


def loc_clients(clients):
    """Lọc client hợp lệ và gộp thành các nhóm theo class."""
    groups = OrderedDict()
    for client in clients:
        if not hop_le(client):
            continue
        cls = str(client["class"])
        group = groups.setdefault(cls, {"class": cls, "clients": []})
        group["clients"].append(client)
    return list(groups.values())


def sap_xep_nhom(groups, old_order):
    """Sắp nhóm theo cột, dùng thứ tự cũ để phá hòa."""
    old_position = {cls: index for index, cls in enumerate(old_order)}
    return [group for _index, group in sorted(
        enumerate(groups),
        key=lambda item: (khoa_cot(item[1]), old_position.get(item[1]["class"], len(old_order)), item[0]),
    )]   # KHÔNG cắt ở đây: chon_nhom_hien cần đủ danh sách để tính ô "+N"


def khoa_cot(group):
    """Khóa cột nhỏ nhất của các cửa sổ trong nhóm."""
    keys = []
    for client in group.get("clients", []):
        workspace = client.get("workspace") or {}
        at = client.get("at") or []
        try:
            keys.append((int(workspace.get("id", 10**9)), float(at[0])))
        except (TypeError, ValueError, IndexError):
            continue
    return min(keys, default=(10**9, float("inf")))


def khuat_man_hinh(client, monitors):
    """Trả về bên khuất của client, hoặc None nếu không khuất màn hình."""
    if client.get("floating"):
        return None
    workspace = client.get("workspace") or {}
    try:
        workspace_id = int(workspace.get("id", -1))
        monitor_id = int(client.get("monitor", -1))
    except (TypeError, ValueError):
        return None
    monitor = next((item for item in monitors if item.get("id") == monitor_id), None)
    if not monitor:
        return None
    active_workspace = monitor.get("activeWorkspace") or {}
    try:
        if int(active_workspace.get("id", -1)) != workspace_id:
            return None
        scale = float(monitor.get("scale", 1))
        x = float((client.get("at") or [])[0])
        width = float((client.get("size") or [])[0])
        monitor_x = float(monitor.get("x", 0))
        monitor_width = float(monitor.get("width", 0)) / scale
        reserved = monitor.get("reserved") or [0, 0, 0, 0]
        left = float(reserved[0])
        right = float(reserved[2])
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None
    # Lộ ra < VISIBLE_MIN px vẫn coi là khuất (giống column-map.sh trên thanh trên)
    if x + width <= monitor_x + left + VISIBLE_MIN:
        return "left"
    if x >= monitor_x + monitor_width - right - VISIBLE_MIN:
        return "right"
    return None


def dia_chi(client):
    return str(client.get("address", ""))


def dia_chi_focus(clients, active_address):
    """Chọn cửa sổ kế tiếp theo địa chỉ, hoặc cửa sổ có lịch sử focus cao nhất."""
    ordered = sorted(clients, key=dia_chi)
    if not ordered:
        return None
    addresses = [dia_chi(client) for client in ordered]
    if active_address not in addresses:
        return min(ordered, key=lambda c: int(c.get("focusHistoryID", 10**9)))
    return ordered[(addresses.index(active_address) + 1) % len(ordered)]


def cua_so_focus_nhat(clients):
    return min(clients, key=lambda c: int(c.get("focusHistoryID", 10**9)), default=None)


def huy_hieu(count):
    if count < 2:
        return None
    return f"x{count}" if count <= 9 else "9+"


def pixel_count(count):
    """Số stack theo quy ước HUD: chỉ hiện số, tối đa là 9+."""
    return None if count < 2 else (str(count) if count < 10 else "9+")


def json_doc(path, default):
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        return value
    except (OSError, ValueError, TypeError):
        return default


def ghi_json_an_toan(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def doc_hyprctl(*args):
    result = subprocess.run(["hyprctl", *args], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def doc_clients_va_active():
    return (doc_hyprctl("clients", "-j"), doc_hyprctl("activewindow", "-j"),
            doc_hyprctl("monitors", "-j"))


def icon_from_gicon(theme, gicon, size=34):
    if gicon is None:
        return None
    from gi.repository import Gtk
    info = theme.lookup_by_gicon(gicon, size, Gtk.IconLookupFlags.FORCE_SIZE)
    return info.load_icon() if info is not None else None


def icon_candidate(cls, cache, theme):
    """Tìm icon theo thứ tự ưu tiên và lưu tên đã chọn."""
    cached = cache.get(cls)
    if isinstance(cached, str):
        try:
            if cached.startswith("/"):
                from gi.repository import Gio
                return icon_from_gicon(theme, Gio.FileIcon.new(Gio.File.new_for_path(cached)))
            from gi.repository import Gtk
            pixbuf = theme.load_icon(cached, 34, Gtk.IconLookupFlags.FORCE_SIZE)
            if pixbuf:
                return pixbuf
        except Exception:
            pass

    from gi.repository import Gio, Gtk

    try:  # GLib mới chuyển DesktopAppInfo sang GioUnix
        import gi
        gi.require_version("GioUnix", "2.0")
        from gi.repository import GioUnix
        DesktopAppInfo = GioUnix.DesktopAppInfo
    except (ValueError, ImportError):
        DesktopAppInfo = Gio.DesktopAppInfo

    candidates = []
    for desktop_name in (f"{cls}.desktop", f"{cls.lower()}.desktop"):
        try:
            app = DesktopAppInfo.new(desktop_name)
            if app:
                candidates.append((app.get_icon(), None))
        except Exception:
            pass
    try:
        wanted = cls.casefold()
        for app in Gio.AppInfo.get_all():
            try:
                startup = (app.get_startup_wm_class() or "").casefold()
                app_name = (app.get_filename() or "").rsplit("/", 1)[-1][:-8].casefold()
                if startup == wanted or app_name == wanted:
                    candidates.append((app.get_icon(), None))
                    break
            except Exception:
                continue
    except Exception:
        pass
    candidates.extend(((None, cls), (None, cls.lower()), (None, "application-x-executable")))

    for gicon, name in candidates:
        try:
            pixbuf = icon_from_gicon(theme, gicon) if gicon is not None else theme.load_icon(name, 34, Gtk.IconLookupFlags.FORCE_SIZE)
            if pixbuf:
                if name:
                    cache[cls] = name
                elif hasattr(gicon, "get_names"):
                    names = gicon.get_names()
                    if names:
                        cache[cls] = names[0]
                return pixbuf
        except Exception:
            continue
    return None


def _pixel_font():
    repo = Path(__file__).resolve().parents[2]
    greeter = str(repo / "greetd" / "kafka-greeter")
    if greeter not in sys.path:
        sys.path.insert(0, greeter)
    from pixelfont import draw_text
    return draw_text


def _pixel_icon(context, pixbuf):
    if pixbuf is None:
        # Placeholder dùng cho preview hoặc máy không có icon theme.
        context.set_source_rgb(0.78, 0.49, 1.0)
        context.rectangle(13, 12, 14, 14)
        context.fill()
        context.set_source_rgb(0.29, 0.24, 0.35)
        context.rectangle(17, 16, 6, 6)
        context.fill()
        return
    width, height = pixbuf.get_width(), pixbuf.get_height()
    context.save()
    context.translate(7, 6)
    context.scale(26 / width, 26 / height)
    from gi.repository import Gdk
    Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, 0)
    context.get_source().set_filter(__import__("cairo").FILTER_BEST)
    context.paint()
    context.restore()


def _pixel_surface(cls, count, focused, cache, offscreen, theme=None):
    import cairo
    context_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, OUT_PX, OUT_PX)
    context = cairo.Context(context_surface)
    context.set_antialias(cairo.ANTIALIAS_NONE)

    def rect(x, y, w, h, color):
        context.set_source_rgb(*color)
        context.rectangle(x, y, w, h)
        context.fill()

    dark = (20 / 255, 14 / 255, 26 / 255)
    inner = (44 / 255, 34 / 255, 56 / 255) if focused else (29 / 255, 22 / 255, 38 / 255)
    # Bốn góc không được tô: đó là các pixel trong suốt của slot stepped.
    context.set_source_rgb(*dark)
    context.move_to(2, 0); context.line_to(38, 0); context.line_to(40, 2)
    context.line_to(40, 38); context.line_to(38, 40); context.line_to(2, 40)
    context.line_to(0, 38); context.line_to(0, 2); context.close_path(); context.fill()
    rect(2, 2, 36, 36, inner)
    rect(2, 2, 36, 2, (15 / 255, 10 / 255, 20 / 255))
    rect(2, 2, 2, 36, (15 / 255, 10 / 255, 20 / 255))
    rect(2, 38, 36, 2, (74 / 255, 60 / 255, 89 / 255))
    rect(38, 2, 2, 36, (74 / 255, 60 / 255, 89 / 255))

    if theme is not None:
        try:
            pixbuf = icon_candidate(cls, cache, theme)
        except Exception:
            pixbuf = None
    else:
        pixbuf = None
    _pixel_icon(context, pixbuf)

    if focused:
        pink = (240 / 255, 140 / 255, 187 / 255)
        shade = (150 / 255, 47 / 255, 98 / 255)
        # Bốn góc chữ L mở vào giữa slot 40x40, nằm trọn trong viền 2px.
        # Dải shade nằm phía trong cánh ngang (trên: y 4..6; dưới: y 34..36),
        # chỉ phủ phần không bị cánh dọc che.
        bracket_rects = (
            (2, 2, 8, 2, pink),     # trái-trên: cánh ngang
            (2, 2, 2, 8, pink),     # trái-trên: cánh dọc
            (4, 4, 6, 2, shade),    # trái-trên: shade
            (30, 2, 8, 2, pink),    # phải-trên: cánh ngang
            (36, 2, 2, 8, pink),    # phải-trên: cánh dọc
            (30, 4, 6, 2, shade),   # phải-trên: shade
            (2, 36, 8, 2, pink),    # trái-dưới: cánh ngang
            (2, 30, 2, 8, pink),    # trái-dưới: cánh dọc
            (4, 34, 6, 2, shade),   # trái-dưới: shade
            (30, 36, 8, 2, pink),   # phải-dưới: cánh ngang
            (36, 30, 2, 8, pink),   # phải-dưới: cánh dọc
            (30, 34, 6, 2, shade),  # phải-dưới: shade
        )
        for x, y, w, h, color in bracket_rects:
            rect(x, y, w, h, color)

    for side in ("left", "right"):
        if side in offscreen:
            x = 0 if side == "left" else 32
            rect(x, 16, 8, 8, dark)
            rect(x + 2, 18, 4, 4, (199 / 255, 125 / 255, 1.0))

    badge = pixel_count(count)
    if badge:
        try:
            draw_text = _pixel_font()
            width = (len(badge) * 6 - 1) * 2
            draw_text(context, badge, 38 - width, 24, 2,
                      (1.0, 224 / 255, 138 / 255), shadow=dark)
        except (ImportError, OSError):
            # Không để thiếu pixelfont làm hỏng dock; badge fallback tối giản.
            rect(26, 30, 10, 6, (184 / 255, 50 / 255, 106 / 255))
    return context_surface


def _write_surface(surface, path, scale=1, filter_mode=None):
    import cairo
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    try:
        if scale == 1:
            surface.write_to_png(temp_name)
        else:
            out = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                      surface.get_width() * scale, surface.get_height() * scale)
            context = cairo.Context(out)
            context.scale(scale, scale)
            context.set_source_surface(surface, 0, 0)
            context.get_source().set_filter(filter_mode or cairo.FILTER_NEAREST)
            context.paint()
            out.write_to_png(temp_name)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def ve_png(path, cls, count, focused, cache, offscreen):
    import cairo
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")   # thiếu dòng này PyGObject tự nạp Gdk 4 -> xung đột với Gtk 3
    from gi.repository import Gdk, Gtk

    if pixel_theme_enabled():
        _write_surface(_pixel_surface(cls, count, focused, cache, offscreen, Gtk.IconTheme.get_default()), path)
        return

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 48, 48)
    context = cairo.Context(surface)

    def hop_bo_goc(x, y, w, h, r):
        """Tạo path hình chữ nhật bo góc bằng 4 cung tròn."""
        r = min(r, w / 2, h / 2)
        context.new_sub_path()
        context.arc(x + w - r, y + r, r, -1.5708, 0)
        context.arc(x + w - r, y + h - r, r, 0, 1.5708)
        context.arc(x + r, y + h - r, r, 1.5708, 3.1416)
        context.arc(x + r, y + r, r, 3.1416, 4.7124)
        context.close_path()

    if focused:
        # Nền trắng rất nhẹ, chỉ tô (phong cách phẳng)
        context.set_source_rgba(1, 1, 1, 0.08)
        hop_bo_goc(1, 1, 46, 46, 12)
        context.fill()
        # Vạch nhấn ở mép trái
        context.set_source_rgba(224 / 255, 85 / 255, 154 / 255, 1)
        hop_bo_goc(0, 15, 3, 18, 1.5)
        context.fill()
    theme = Gtk.IconTheme.get_default()
    pixbuf = icon_candidate(cls, cache, theme)
    if pixbuf is not None:
        Gdk.cairo_set_source_pixbuf(context, pixbuf, 7, 6)
        context.paint()
    badge = huy_hieu(count)
    if badge:
        # Huy hiệu góc dưới-phải: đo chữ trước, rồi vẽ viên thuốc ôm chữ
        import gi as _gi
        _gi.require_version("Pango", "1.0")
        _gi.require_version("PangoCairo", "1.0")
        from gi.repository import Pango, PangoCairo
        layout = PangoCairo.create_layout(context)
        layout.set_font_description(Pango.FontDescription("FiraCode Nerd Font Bold 8"))
        layout.set_text(badge, -1)
        _ink, logical = layout.get_pixel_extents()
        tw, th = logical.width, logical.height
        h = 15
        w = max(h, tw + 7)
        x, y = 48 - w - 0.5, 48 - h - 0.5
        r = h / 2
        context.new_sub_path()
        context.arc(x + w - r, y + r, r, -1.5708, 1.5708)
        context.arc(x + r, y + r, r, 1.5708, 4.7124)
        context.close_path()
        context.set_source_rgb(184 / 255, 50 / 255, 106 / 255)
        context.fill_preserve()
        context.set_source_rgb(22 / 255, 16 / 255, 30 / 255)
        context.set_line_width(1)
        context.stroke()
        context.set_source_rgb(1, 1, 1)
        context.move_to(x + (w - tw) / 2 - logical.x, y + (h - th) / 2 - logical.y)
        PangoCairo.show_layout(context, layout)
    # Chấm báo cửa sổ đang khuất: góc trên trái/phải thay vì hai bên hông
    context.set_source_rgb(199 / 255, 125 / 255, 255 / 255)
    context.set_line_width(1)
    for x in (7, 41):
        side = "left" if x == 7 else "right"
        if side in offscreen:
            context.arc(x, 7, 3, 0, 6.2832)
            context.fill_preserve()
            context.set_source_rgb(22 / 255, 16 / 255, 30 / 255)
            context.stroke()
            context.set_source_rgb(199 / 255, 125 / 255, 255 / 255)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    try:
        # Vẽ ở 48px rồi thu về OUT_PX: Waybar không thu ảnh của module image (ảnh 48px làm dock rộng ra)
        out = cairo.ImageSurface(cairo.FORMAT_ARGB32, OUT_PX, OUT_PX)
        out_ctx = cairo.Context(out)
        out_ctx.scale(OUT_PX / 48, OUT_PX / 48)
        out_ctx.set_source_surface(surface, 0, 0)
        out_ctx.get_source().set_filter(cairo.FILTER_BEST)
        out_ctx.paint()
        out.write_to_png(temp_name)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def chon_nhom_hien(groups, active_address):
    """Chọn nhóm hiện trên 4 ô: ≤ 4 app thì hiện hết; nhiều hơn thì 3 app đầu + ô "+N" (N = số app còn lại).
    App đang focus luôn được hiện (thay vào ô thứ 3 nếu nằm ngoài). Trả về (danh sách hiện, N)."""
    if len(groups) <= MAX_SLOTS:
        return list(groups), 0
    shown = list(groups[:MAX_SLOTS - 1])
    focused = next((g for g in groups if active_address in {dia_chi(c) for c in g["clients"]}), None)
    if focused is not None and focused not in shown:
        shown[-1] = focused
    return shown, len(groups) - len(shown)


def render():
    # Hyprland gọi render ở nhiều sự kiện liền nhau (mở + focus...): khóa để chạy lần lượt,
    # mỗi lần đọc trạng thái mới nhất, không ghi đè file của nhau.
    import fcntl
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUNTIME_DIR / "render.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _render()


def preview_pixel(path):
    """Tạo sample sheet pixel mà không cần Hyprland hay state file."""
    import cairo
    theme = None
    cache = {}
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        theme = Gtk.IconTheme.get_default()
    except Exception:
        pass
    samples = [
        ("kitty", 1, False, []),
        ("kitty", 3, True, []),
        ("chromium", 12, False, []),
        ("unknown-class", 1, False, []),
        ("kitty", 2, False, ["left", "right"]),
    ]
    sheet = cairo.ImageSurface(cairo.FORMAT_ARGB32, OUT_PX * len(samples), OUT_PX)
    context = cairo.Context(sheet)
    context.set_operator(cairo.OPERATOR_CLEAR)
    context.paint()
    context.set_operator(cairo.OPERATOR_OVER)
    for index, (cls, count, focused, offscreen) in enumerate(samples):
        context.set_source_surface(_pixel_surface(cls, count, focused, cache, offscreen, theme), index * OUT_PX, 0)
        context.paint()
    _write_surface(sheet, Path(path), scale=4, filter_mode=cairo.FILTER_NEAREST)


def _render():
    clients, active, monitors = doc_clients_va_active()
    if not isinstance(monitors, list):
        monitors = []
    old_order = json_doc(RUNTIME_DIR / "order.json", [])
    if not isinstance(old_order, list):
        old_order = []
    groups = sap_xep_nhom(loc_clients(clients), [str(x) for x in old_order])
    ghi_json_an_toan(RUNTIME_DIR / "order.json", [g["class"] for g in groups])
    cache = json_doc(RUNTIME_DIR / "icons.json", {})
    if not isinstance(cache, dict):
        cache = {}
    active_address = str((active or {}).get("address", ""))
    draw_keys = json_doc(RUNTIME_DIR / "draw-keys.json", {})
    if not isinstance(draw_keys, dict):
        draw_keys = {}
    import dock_slots
    shown, extra = chon_nhom_hien(groups, active_address)
    for index in range(1, MAX_SLOTS + 1):
        png = RUNTIME_DIR / f"slot{index}.png"
        meta = RUNTIME_DIR / f"slot{index}.json"
        if index > len(shown):
            # ô trống hoặc ô "+N": vẫn vẽ để ngăn RUN luôn đủ 4 ô (ngăn bên dưới không xê dịch)
            if extra and index == MAX_SLOTS:
                key = {"more": extra, "pixel": pixel_theme_enabled()}
                if draw_keys.get(str(index)) != key or not png.exists():
                    dock_slots.write_png(dock_slots.more_surface(extra), png)
                draw_keys[str(index)] = key
                ghi_json_an_toan(meta, {"more": extra})
            else:
                # 4 là GIỚI HẠN, không phải số ô luôn hiện (người dùng): ô không dùng thì ẩn
                for path in (png, meta):
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                draw_keys.pop(str(index), None)
            continue
        group = shown[index - 1]
        members = group["clients"]
        focused = active_address in {dia_chi(c) for c in members}
        offscreen = sorted({side for client in members
                            if (side := khuat_man_hinh(client, monitors)) is not None})
        key = {"class": group["class"], "count": len(members), "focused": focused, "offscreen": offscreen,
               "pixel": pixel_theme_enabled()}   # đổi theme phải vẽ lại
        if draw_keys.get(str(index)) != key or not png.exists():
            ve_png(png, group["class"], len(members), focused, cache, offscreen)
        draw_keys[str(index)] = key
        ghi_json_an_toan(meta, {"class": group["class"], "addresses": [dia_chi(c) for c in members],
                                "titles": [str(c.get("title", "")) for c in members], "offscreen": offscreen})
    ghi_json_an_toan(RUNTIME_DIR / "draw-keys.json", draw_keys)
    ghi_json_an_toan(RUNTIME_DIR / "icons.json", cache)
    subprocess.run(["pkill", "-RTMIN+13", "waybar"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def slot(index):
    try:
        meta = json_doc(RUNTIME_DIR / f"slot{index}.json", {})
        png = RUNTIME_DIR.joinpath(f"slot{index}.png").resolve()
        if meta.get("more") and png.exists():
            print(png)
            print(f"Còn {meta['more']} app đang mở khác — bấm để xem hết")
            return
        cls = meta.get("class")
        if not cls:
            return
        titles = [str(title).replace("\n", " ")[:40] for title in meta.get("titles", [])]
        print(RUNTIME_DIR.joinpath(f"slot{index}.png").resolve())
        count = len(meta.get("addresses", titles))
        print(f"{cls} · {count} cửa sổ: " + " | ".join(titles))
        for side, message in (("left", "◂ khuất bên trái"), ("right", "khuất bên phải ▸")):
            if side in meta.get("offscreen", []):
                print(message)
    except Exception:
        return


def no_warps_enabled():
    """Đọc cursor.no_warps hiện tại; lỗi hoặc giá trị không rõ -> coi như đang bật warp."""
    try:
        result = subprocess.run(
            ["hyprctl", "repl", 'return hl.get_config("cursor.no_warps")'],
            check=False, capture_output=True, text=True,
        )
        return result.returncode == 0 and result.stdout.strip().startswith("true")
    except Exception:
        return False


def dispatch_for(index, close=False):
    try:
        meta = json_doc(RUNTIME_DIR / f"slot{index}.json", {})
        if meta.get("more"):
            subprocess.Popen([str(Path(__file__).resolve().parent / "dock-more.py"), "--section", "run"],
                             start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        cls = meta.get("class")
        if not cls:
            return
        clients, active, _monitors = doc_clients_va_active()
        members = [client for client in clients if hop_le(client) and str(client.get("class")) == cls]
        if not members:
            return
        target = cua_so_focus_nhat(members) if close else dia_chi_focus(members, str((active or {}).get("address", "")))
        if target:
            address = dia_chi(target)
            action = "window.close" if close else "focus"
            command = ["hyprctl", "dispatch", f'hl.dsp.{action}({{ window = "address:{address}" }})']
            if close or no_warps_enabled():
                subprocess.run(command, check=False)
                return
            # Người dùng: bấm thẻ app chỉ chuyển tới app, không kéo chuột vào giữa cửa sổ.
            # Tắt no_warps tạm thời khi focus rồi khôi phục (chờ warp kết thúc).
            subprocess.run(["hyprctl", "eval", "hl.config({ cursor = { no_warps = true } })"], check=False)
            try:
                subprocess.run(command, check=False)
            finally:
                time.sleep(0.15)
                subprocess.run(["hyprctl", "eval", "hl.config({ cursor = { no_warps = false } })"], check=False)
    except Exception as error:
        print(f"dock-apps: {error}", file=sys.stderr)


def selftest():
    g = [{"class": f"c{i}", "clients": [{"address": f"0x{i}"}]} for i in range(6)]
    assert chon_nhom_hien(g[:4], "0x0") == (g[:4], 0)
    shown, extra = chon_nhom_hien(g, "0x5")
    assert [x["class"] for x in shown] == ["c0", "c1", "c5"] and extra == 3, (shown, extra)
    assert chon_nhom_hien(g, "0x1") == (g[:3], 3)
    fake = [
        {"address": "0x2", "class": "kitty", "title": "A", "mapped": True, "at": [300, 0], "workspace": {"id": 1, "name": "1"}, "focusHistoryID": 2},
        {"address": "0x1", "class": "kitty", "title": "B", "mapped": True, "at": [250, 0], "workspace": {"id": 1, "name": "1"}, "focusHistoryID": 0},
        {"address": "0x3", "class": "firefox", "mapped": True, "at": [-100, 0], "workspace": {"id": 1, "name": "1"}, "focusHistoryID": 1},
        {"address": "0x4", "class": "bad", "mapped": False, "workspace": {"id": 2, "name": "2"}},
        {"address": "0x5", "class": "hide", "mapped": True, "workspace": {"id": -1, "name": "special:x"}},
    ]
    assert [g["class"] for g in loc_clients(fake)] == ["kitty", "firefox"]
    assert [g["class"] for g in sap_xep_nhom(loc_clients(fake), ["kitty", "firefox"])] == ["firefox", "kitty"]
    assert [dia_chi_focus(loc_clients(fake)[0]["clients"], "0x1")["address"], dia_chi_focus(loc_clients(fake)[0]["clients"], "nope")["address"]] == ["0x2", "0x1"]
    assert [huy_hieu(n) for n in (1, 2, 12)] == [None, "x2", "9+"]
    assert [pixel_count(n) for n in (1, 2, 9, 10, 12)] == [None, "2", "9", "9+", "9+"]
    monitors = [{"id": 0, "x": 100, "width": 1600, "scale": 1.25,
                 "activeWorkspace": {"id": 1}, "reserved": [10, 20, 30, 0]}]
    left = {"monitor": 0, "at": [80, 30], "size": [20, 20], "floating": False,
            "workspace": {"id": 1}}
    right = {"monitor": 0, "at": [1350, 30], "size": [20, 20], "floating": False,
             "workspace": {"id": 1}}
    inside = {"monitor": 0, "at": [400, 30], "size": [400, 20], "floating": False,
              "workspace": {"id": 1}}
    floating = dict(left, floating=True)
    inactive = dict(left, workspace={"id": 2})
    assert khuat_man_hinh(left, monitors) == "left"
    assert khuat_man_hinh(right, monitors) == "right"
    assert khuat_man_hinh(inside, monitors) is None
    assert khuat_man_hinh(floating, monitors) is None
    assert khuat_man_hinh(inactive, monitors) is None
    print("selftest ok")


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        selftest()
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "--preview-pixel":
        preview_pixel(sys.argv[2])
        return 0
    if not ((len(sys.argv) == 2 and sys.argv[1] == "render") or
            (len(sys.argv) == 3 and sys.argv[1] in {"slot", "click", "close"})):
        print("Sử dụng: dock-apps.py render|slot N|click N|close N|--selftest|--preview-pixel OUT.png", file=sys.stderr)
        return 2
    try:
        if sys.argv[1] == "render":
            render()
        else:
            index = int(sys.argv[2])
            if not 1 <= index <= MAX_SLOTS:
                raise ValueError("slot không hợp lệ")
            if sys.argv[1] == "slot":
                slot(index)
            else:
                dispatch_for(index, sys.argv[1] == "close")
        return 0
    except Exception as error:
        if sys.argv[1] == "slot":
            return 0
        print(f"dock-apps: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
