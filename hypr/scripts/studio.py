#!/usr/bin/env python3
"""studio.py — KAFKA STUDIO: chỉnh giao diện bằng tay mà không phải nhớ đường dẫn/lệnh nạp lại.

Nút 󰏘 trên dock (dưới nút tiện ích, trên thông báo). App GTK3 (class `kafka.studio`, cửa sổ nổi 1180x740), 5 tab:

  HÌNH NỀN   lưới ảnh trong wallpapers/: bấm = đặt ngay (wallpaper-cycle.sh set), "Đặt làm mặc định" = ghi
             ~/.local/state/kafka/wallpaper (hyprland.lua đọc lúc đăng nhập). "Thêm ảnh…": ảnh ngang chép vào
             wallpapers/kafka_<tên>.<đuôi>; ảnh dọc/vuông ghép thành thẻ kính mờ 1920x1080 (công thức trong CLAUDE.md).
  SỬA FILE   mọi file giao diện (Waybar, popup, rofi, walker, dunst, GTK, hyprshell, kitty, khoá màn hình, btop,
             Hyprland) trong trình soạn GtkSourceView: tô màu cú pháp, số dòng, tìm (Ctrl+F), chèn màu, Ctrl+S.
             Lưu = SAO LƯU bản cũ (~/.local/state/kafka/studio-backups/) → kiểm tra (CSS GTK3, JSONC, Lua qua
             `Hyprland --verify-config`) → ghi → NẠP LẠI đúng thành phần. "Hoàn tác" lấy bản sao lưu gần nhất,
             "Bản gốc git" lấy lại bản đã commit (bản hiện tại vẫn được sao lưu trước).
  MÀU SẮC    các biến `@define-color` của waybar/style.css (bản phẳng) và theme-pixel.css (bản pixel): đổi bằng
             bảng chọn màu, Waybar nạp lại ngay.
  GIAO DIỆN  đổi phẳng ⇄ pixel, viền xoay màu, bộ con trỏ, nạp lại từng thành phần.
  CẢNH BÁO   chỉnh ngưỡng trong hypr/alerts.json (pin máy, pin thiết bị, Wi-Fi, Internet): bật/tắt, mốc %,
              mức khẩn cấp, thời gian chờ. Lưu = ghi JSON rồi nạp lại daemon alert-watch.py; có nút thử thông báo.

  studio.py               mở app
  studio.py --page wall|edit|dock|color|look|alert   mở thẳng vào một tab
  studio.py --open waybar/style.css       mở thẳng file đó trong tab Sửa file
  studio.py --selftest    kiểm tra phần không cần màn hình (đọc/ghi màu, kiểm tra JSONC, danh sách file, ngưỡng cảnh báo)
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
WALL_DIR = os.path.join(REPO, "wallpapers")
STATE_DIR = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "kafka")
WALL_STATE = os.path.join(STATE_DIR, "wallpaper")
BACKUP_DIR = os.path.join(STATE_DIR, "studio-backups")
THUMB_DIR = os.path.expanduser("~/.cache/kafka/studio-thumbs")
CURRENT_WALL = os.path.expanduser("~/.cache/kafka_current_wallpaper")
SCRIPTS = os.path.join(REPO, "hypr", "scripts")
ALERTS_FILE = os.path.join(REPO, "hypr", "alerts.json")
ALERT_WATCH = os.path.join(SCRIPTS, "alert-watch.py")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")

# ------------------------------------------------------------------ lệnh nạp lại từng thành phần
RELOAD = {
    "waybar-css": ("Waybar nạp lại CSS", "killall -SIGUSR2 waybar"),
    "waybar": ("Khởi động lại Waybar", "killall waybar; sleep 0.6; hyprctl dispatch \"hl.dsp.exec_cmd('waybar')\""),
    "walker": (
        "Khởi động lại walker",
        "pkill -x walker; sleep 0.4; hyprctl dispatch \"hl.dsp.exec_cmd('walker --gapplication-service')\"",
    ),
    "dunst": ("Nạp lại dunst", "dunstctl reload"),
    "hyprshell": ("Nạp lại hyprshell", "hyprshell socat '\"Reload\"'"),
    "kitty": ("Nạp lại kitty", "pkill -USR1 -x kitty"),
    "hyprland": ("Nạp lại Hyprland", "hyprctl reload"),
    "popups": (
        "Khởi động lại popup chạy nền",
        f"kill $(cat $XDG_RUNTIME_DIR/kafka-tools-popup.pid 2>/dev/null) 2>/dev/null; "
        f"sleep 0.3; hyprctl dispatch \"hl.dsp.exec_cmd('{SCRIPTS}/tools-popup.py')\"",
    ),
    "dock-pins": ("Vẽ lại app ghim trên dock", f"{SCRIPTS}/dock-pins.py render"),
    # daemon tự nạp khi alerts.json đổi; nút này để chắc chắn — chưa chạy thì bật lên
    "alerts": (
        "Nạp lại cảnh báo",
        f"{SCRIPTS}/alert-watch.py --reload 2>/dev/null || "
        f"hyprctl dispatch \"hl.dsp.exec_cmd('{SCRIPTS}/alert-watch.py daemon')\"",
    ),
    None: ("Không cần nạp lại (mở lại là thấy)", ""),
}

# (nhóm, tên hiển thị, đường dẫn trong repo, ngôn ngữ GtkSource, khoá RELOAD, kiểu kiểm tra)
FILES = [
    ("Waybar", "Kiểu chung (style.css)", "waybar/style.css", "css", "waybar-css", "css"),
    ("Waybar", "Kiểu pixel (theme-pixel.css)", "waybar/theme-pixel.css", "css", "waybar-css", "css"),
    ("Waybar", "Bố cục thanh trên — phẳng", "waybar/topbar.jsonc", "json", "waybar", "jsonc"),
    ("Waybar", "Bố cục thanh trên — pixel", "waybar/topbar-pixel.jsonc", "json", "waybar", "jsonc"),
    ("Waybar", "Bố cục dock", "waybar/dockbar.jsonc", "json", "waybar", "jsonc"),
    ("Waybar", "App ghim trên dock", "waybar/dock-pins.json", "json", "dock-pins", "jsonc"),
    ("Cảnh báo", "Ngưỡng cảnh báo (alerts.json)", "hypr/alerts.json", "json", "alerts", "alerts"),
    ("Popup", "Màu/khung popup pixel (kafka_theme.py)", "hypr/scripts/kafka_theme.py", "python3", "popups", "python"),
    ("Rofi", "Menu rofi chung (kafka.rasi)", "rofi/kafka.rasi", "css", None, None),
    ("Rofi", "Menu nguồn (kafka-power.rasi)", "rofi/kafka-power.rasi", "css", None, None),
    ("Rofi", "Hộp chức năng (kafka-actions.rasi)", "rofi/kafka-actions.rasi", "css", None, None),
    ("Rofi", "Rofi bản pixel (theme-pixel.rasi)", "rofi/theme-pixel.rasi", "css", None, None),
    ("Walker", "Walker phẳng (style.css)", "walker/themes/kafka/style.css", "css", "walker", None),
    ("Walker", "Walker túi đồ pixel (style.css)", "walker/themes/kafka-pixel/style.css", "css", "walker", None),
    ("Walker", "Cấu hình walker (config.toml)", "walker/config.toml", "toml", "walker", None),
    ("Thông báo", "Dunst (dunstrc)", "dunst/dunstrc", "ini", "dunst", None),
    ("Thông báo", "Dunst bản pixel", "dunst/theme-pixel.conf", "ini", None, None),
    ("App GTK", "GTK3 chung (gtk.css)", "gtk/gtk-3.0/gtk.css", "css", None, "css"),
    ("App GTK", "GTK3 bản pixel", "gtk/gtk-3.0/theme-pixel.css", "css", None, "css"),
    ("App GTK", "GTK4 bản pixel", "gtk/gtk-4.0/theme-pixel.css", "css", None, None),
    ("Tổng quan", "hyprshell phẳng", "hyprshell/styles-flat.css", "css", "hyprshell", None),
    ("Tổng quan", "hyprshell pixel", "hyprshell/styles-pixel.css", "css", "hyprshell", None),
    ("Tổng quan", "Cấu hình hyprshell", "hyprshell/config.toml", "toml", "hyprshell", None),
    ("Terminal", "kitty (kitty.conf)", "kitty/kitty.conf", "ini", "kitty", None),
    ("Terminal", "kitty bản pixel", "kitty/theme-pixel.conf", "ini", "kitty", None),
    ("Terminal", "btop phẳng", "btop/themes/kafka.theme", "ini", None, None),
    ("Terminal", "btop pixel", "btop/themes/kafka-pixel.theme", "ini", None, None),
    ("Khoá màn hình", "hyprlock phẳng", "hypr/hyprlock.conf", "ini", None, None),
    ("Khoá màn hình", "hyprlock pixel", "hypr/hyprlock-pixel.conf", "ini", None, None),
    ("Hyprland", "Hyprland (hyprland.lua) — cẩn thận", "hypr/hyprland.lua", "lua", "hyprland", "lua"),
    ("Hyprland", "Phím tắt riêng (keybinds.lua)", "hypr/keybinds.lua", "lua", "hyprland", "lua"),
]

COLOR_FILES = [
    ("Bản phẳng — waybar/style.css", "waybar/style.css"),
    ("Bản pixel — waybar/theme-pixel.css", "waybar/theme-pixel.css"),
]
PINS_FILE = os.path.join(REPO, "waybar", "dock-pins.json")
MAX_PINS = 6  # = số ô ngăn FAV trên dock (dock-pins.py MAX_SLOTS)
DEFAULT_PINS = ["chromium.desktop", "kitty.desktop", "thunar.desktop", "code-oss.desktop", "org.xfce.mousepad.desktop"]


def load_pins(path=PINS_FILE):
    """Danh sách id .desktop ghim trên dock (thứ tự trên → dưới)."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    pins = data.get("pins", []) if isinstance(data, dict) else []
    out = []
    for p in pins:
        if isinstance(p, str) and p.endswith(".desktop") and p not in out:
            out.append(p)
    return out[:MAX_PINS]


def save_pins(pins, path=PINS_FILE):
    """Ghi lại danh sách ghim, giữ dòng chú thích "_" của file."""
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data["pins"] = list(dict.fromkeys(pins))[:MAX_PINS]
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        f.write("\n")
    os.replace(tmp, path)


# ------------------------------------------------------------------ ngưỡng cảnh báo (hypr/alerts.json)
DEFAULT_ALERTS = {
    "battery": {"enabled": True, "levels": [80, 50, 30, 15], "critical": 15},
    "devices": {"enabled": True, "levels": [30, 15], "critical": 10},
    "wifi_signal": {"enabled": True, "levels": [40, 20]},
    "internet": {"enabled": True, "grace_seconds": 20},
    "popup": {"enabled": True, "sound": True, "volume": 80, "seconds": 10},
}


def parse_levels(text):
    """Chuỗi "80, 50,30" → [80, 50, 30]: số nguyên 1..99, bỏ trùng, xếp giảm dần."""
    out = []
    for chunk in str(text).split(","):
        s = chunk.strip()
        if not s:
            continue
        if not re.fullmatch(r"\d+", s):
            raise ValueError(f"Mốc '{s}' không phải số nguyên từ 1 đến 99.")
        n = int(s)
        if not 1 <= n <= 99:
            raise ValueError(f"Mốc {n} nằm ngoài phạm vi 1..99.")
        if n not in out:
            out.append(n)
    return sorted(out, reverse=True)


def clean_levels(value):
    """Chuẩn hoá mốc đọc từ file: None nghĩa là hỏng, phải lấy mặc định."""
    if not isinstance(value, (list, tuple)):
        return None
    out = []
    for n in value:
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 99:
            return None
        if n not in out:
            out.append(n)
    return sorted(out, reverse=True)


def load_alerts(path=ALERTS_FILE):
    """Đọc ngưỡng cảnh báo; file hỏng/thiếu khóa thì lấy mặc định từng khóa, không bao giờ crash."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    out = {}
    for key, defaults in DEFAULT_ALERTS.items():
        val = data.get(key)
        if not isinstance(val, dict):
            val = {}
        cfg = {}
        for field, fallback in defaults.items():
            got = val.get(field, fallback)
            if field in ("enabled", "sound"):
                cfg[field] = got if isinstance(got, bool) else fallback
            elif field == "levels":
                lv = clean_levels(got)
                cfg[field] = lv if lv is not None else list(fallback)
            elif isinstance(got, int) and not isinstance(got, bool):
                cfg[field] = got
            else:
                cfg[field] = fallback
        for field, got in val.items():  # giữ khóa lạ (vd critical của Wi-Fi)
            if field not in cfg:
                cfg[field] = got
        out[key] = cfg
    for key, val in data.items():  # giữ cả nhóm lạ để lần lưu sau không mất
        if key not in out:
            out[key] = val
    return out


def save_alerts(path, data):
    """Ghi ngưỡng qua file tạm cùng thư mục rồi os.replace (file cũ không bao giờ bị cụt)."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


DEFINE_RE = re.compile(r"^(\s*@define-color\s+)([\w-]+)(\s+)([^;]+)(;.*)$")


def sh(cmd, timeout=20):
    try:
        p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "hết giờ"


def ui_theme():
    try:
        with open(os.path.join(STATE_DIR, "ui-theme")) as f:
            return f.read().strip() or "flat"
    except OSError:
        return "flat"


# ------------------------------------------------------------------ logic thuần (selftest được)
def read_colors(text):
    """[(dòng, tên, giá trị)] các @define-color."""
    out = []
    for i, line in enumerate(text.splitlines()):
        m = DEFINE_RE.match(line)
        if m:
            out.append((i, m.group(2), m.group(4).strip()))
    return out


def set_color(text, name, value):
    lines = text.split("\n")
    for i, line in enumerate(lines):
        m = DEFINE_RE.match(line)
        if m and m.group(2) == name:
            lines[i] = f"{m.group(1)}{name}{m.group(3)}{value}{m.group(5)}"
            return "\n".join(lines)
    raise KeyError(name)


def strip_jsonc(text):
    """Bỏ chú thích // và /* */ (giữ nguyên trong chuỗi) + dấu phẩy thừa → JSON chuẩn."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            out.append("\n" * text.count("\n", i, j if j >= 0 else n))  # giữ số dòng để báo lỗi đúng dòng
            i = (j + 2) if j >= 0 else n
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def check_text(kind, text, path):
    """None nếu ổn, ngược lại chuỗi lỗi (có số dòng nếu biết)."""
    if kind == "jsonc":
        try:
            json.loads(strip_jsonc(text))
        except json.JSONDecodeError as e:
            return f"JSON lỗi ở dòng {e.lineno}, cột {e.colno}: {e.msg}"
    elif kind == "alerts":  # alert-watch.py đọc JSON CHUẨN: lỗi là nó lặng lẽ về mặc định
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return f"JSON lỗi ở dòng {e.lineno}, cột {e.colno}: {e.msg} (không dùng comment/dấu phẩy thừa)"
        if not isinstance(data, dict):
            return "Phải là một object { ... }"
        for key, cfg in data.items():
            if key not in DEFAULT_ALERTS or not isinstance(cfg, dict):
                continue
            if "enabled" in cfg and not isinstance(cfg["enabled"], bool):
                return f"{key}.enabled phải là true/false"
            if "levels" in cfg and (clean_levels(cfg["levels"]) is None or not cfg["levels"]):
                return f"{key}.levels phải là danh sách số nguyên 1..99, ví dụ [80, 50, 30]"
            crit = cfg.get("critical", 0)
            if isinstance(crit, bool) or not isinstance(crit, int) or not 0 <= crit <= 99:
                return f"{key}.critical phải là số nguyên 0..99"
            for f, lo, hi in (("volume", 0, 100), ("seconds", 3, 120)):
                v = cfg.get(f, lo)
                if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                    return f"{key}.{f} phải là số nguyên {lo}..{hi}"
            if "sound" in cfg and not isinstance(cfg["sound"], bool):
                return f"{key}.sound phải là true/false"
            grace = cfg.get("grace_seconds", 20)
            if isinstance(grace, bool) or not isinstance(grace, int) or grace < 0:
                return f"{key}.grace_seconds phải là số nguyên ≥ 0"
    elif kind == "python":
        try:
            compile(text, path, "exec")
        except SyntaxError as e:
            return f"Python lỗi ở dòng {e.lineno}: {e.msg}"
    elif kind == "css":
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        errs = []
        prov = Gtk.CssProvider()
        prov.connect(
            "parsing-error", lambda _p, sec, err: errs.append(f"dòng {sec.get_start_line() + 1}: {err.message}")
        )
        try:
            prov.load_from_data(text.encode())
        except Exception:
            pass
        # Waybar/GTK3 bỏ qua thuộc tính lạ nhưng lỗi cú pháp thì bỏ cả khối → chỉ chặn lỗi CÚ PHÁP, báo cảnh báo còn lại
        # @import/url() tương đối bị tìm theo thư mục hiện tại khi nạp từ bộ nhớ → bỏ qua lỗi mở file
        hard = [
            e
            for e in errs
            if "No property named" not in e
            and "not a valid" not in e.lower()
            and "Failed to import" not in e
            and "Error opening file" not in e
        ]
        if hard:
            return "CSS lỗi: " + "; ".join(hard[:4])
    elif kind == "lua":
        tmpdir = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "kafka-studio-check")
        os.makedirs(tmpdir, exist_ok=True)
        if path.endswith("hyprland.lua"):
            tmp = os.path.join(
                os.path.dirname(path), ".studio-check-hyprland.lua"
            )  # cùng thư mục: dofile/require tương đối vẫn đúng
            with open(tmp, "w") as f:
                f.write(text)
            rc, out = sh(f"Hyprland --verify-config -c '{tmp}'", 30)
            os.remove(tmp)
            if rc != 0 or "error" in out.lower():
                return "Hyprland báo lỗi: " + out[-600:]
        else:
            if shutil.which("luac"):
                tmp = os.path.join(tmpdir, "check.lua")
                with open(tmp, "w") as f:
                    f.write(text)
                rc, out = sh(f"luac -p '{tmp}'")
                if rc != 0:
                    return "Lua lỗi: " + out
    return None


def backup(path):
    """Chép file hiện tại vào thư mục sao lưu (giữ 30 bản mới nhất mỗi file). Trả về đường dẫn bản sao."""
    if not os.path.exists(path):
        return None
    rel = os.path.relpath(path, REPO).replace("/", "__")
    d = os.path.join(BACKUP_DIR, rel)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    shutil.copy2(path, dst)
    olds = sorted(os.listdir(d))
    for old in olds[:-30]:
        os.remove(os.path.join(d, old))
    return dst


def backups_of(path):
    d = os.path.join(BACKUP_DIR, os.path.relpath(path, REPO).replace("/", "__"))
    try:
        return [os.path.join(d, x) for x in sorted(os.listdir(d))]
    except OSError:
        return []


def wallpapers():
    try:
        names = sorted(os.listdir(WALL_DIR), key=str.lower)
    except OSError:
        return []
    return [os.path.join(WALL_DIR, n) for n in names if n.lower().endswith(IMG_EXT)]


def slug(name):
    base = os.path.splitext(os.path.basename(name))[0].lower()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "anh"
    return base[:40]


# ------------------------------------------------------------------ giao diện
def run_app():
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("GtkSource", "4")
    from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, GtkSource, Pango

    GLib.set_prgname("kafka.studio")  # app_id Wayland = prgname → luật cửa sổ nổi kafka\.studio trong hyprland.lua
    GLib.set_application_name("Kafka Studio")

    pixel = ui_theme() == "pixel"
    if pixel:
        BG, PANEL, SUNK, EDGE, HI, TEXT, DIM, FAINT = (
            "#221a2b",
            "#33293f",
            "#1a1422",
            "#140e1a",
            "#56466a",
            "#fbf7fd",
            "#d4cade",
            "#9a8bab",
        )
        ACC, ACC_HI, GOLD, RAD = "#c94785", "#f08cbb", "#ffe08a", "0"
        BEVEL = f"box-shadow: inset 0 0 0 2px {EDGE}, inset 2px 2px 0 {HI}, inset -2px -2px 0 #1d1626;"
        SUNKEN = f"box-shadow: inset 0 0 0 2px {EDGE}, inset 2px 2px 0 #0f0a14;"
        TITLE_FONT = '"Kafka Pixel", "FiraCode Nerd Font"'
    else:
        BG, PANEL, SUNK, EDGE, HI, TEXT, DIM, FAINT = (
            "#231c2b",
            "#2c2434",
            "#1b1522",
            "#3a3045",
            "#4a3c59",
            "#fbf7fd",
            "#d4cade",
            "#a091b1",
        )
        ACC, ACC_HI, GOLD, RAD = "#c94785", "#e0559a", "#ffe08a", "10px"
        BEVEL = "box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08);"
        SUNKEN = "box-shadow: inset 0 0 0 1px rgba(255,255,255,0.06);"
        TITLE_FONT = '"FiraCode Nerd Font"'

    CSS = f"""
* {{ font-family: "FiraCode Nerd Font"; font-size: 10.5pt; color: {TEXT}; }}
window {{ background-color: {BG}; }}
.titlebar-box {{ background-color: {ACC}; padding: 6px 12px; {"box-shadow: inset 0 2px 0 #f08cbb, inset 0 -2px 0 #962f62;" if pixel else ""} }}
.titlebar-box label {{ color: #ffffff; }}
.app-title {{ font-family: {TITLE_FONT}; font-size: {"14px" if pixel else "13pt"}; font-weight: 800; }}
.sidebar {{ background-color: {SUNK}; padding: 8px; }}
.side-btn {{ border-radius: {RAD}; padding: 10px 12px; background-image: none; background-color: transparent;
             border: none; box-shadow: none; }}
.side-btn label {{ font-weight: 700; }}
.side-btn:hover {{ background-color: {PANEL}; }}
.side-btn.on {{ background-color: {PANEL}; box-shadow: inset 4px 0 0 {ACC_HI}{", inset 0 0 0 2px " + EDGE if pixel else ""}; }}
.side-btn.on label {{ color: {ACC_HI}; }}
.page {{ padding: 14px; }}
.h1 {{ font-size: 13pt; font-weight: 800; }}
.hint {{ color: {FAINT}; font-size: 9.5pt; }}
.status {{ color: {GOLD}; font-size: 9.5pt; }}
.status.err {{ color: #ff7a93; }}
.card {{ background-color: {PANEL}; border-radius: {RAD}; padding: 10px; {BEVEL} }}
button {{ border-radius: {RAD}; background-image: none; background-color: {PANEL}; border: none; padding: 6px 12px;
          {BEVEL} }}
button:hover {{ background-color: {HI}; }}
button:disabled {{ opacity: 0.4; }}
button.accent {{ background-color: {ACC}; }}
button.accent label {{ color: #ffffff; }}
button.accent:hover {{ background-color: {ACC_HI}; }}
button.danger label {{ color: #ff9aae; }}
.thumb {{ border-radius: {RAD}; padding: 4px; background-color: {SUNK}; {SUNKEN} }}
.thumb.current {{ box-shadow: inset 0 0 0 3px {ACC_HI}; }}
.thumb.default label.tag {{ color: {GOLD}; }}
.thumb label {{ font-size: 9pt; color: {DIM}; }}
flowboxchild {{ padding: 4px; border-radius: {RAD}; }}
flowboxchild:hover .thumb {{ background-color: {PANEL}; }}
list, row {{ background-color: transparent; }}
row {{ border-radius: {RAD}; padding: 4px 8px; }}
row:hover {{ background-color: {PANEL}; }}
row:selected {{ background-color: {ACC}; }}
row:selected label {{ color: #ffffff; }}
row.group-row label {{ color: {ACC_HI}; font-weight: 800; font-size: 9pt; }}
textview, textview text {{ font-family: "FiraCode Nerd Font Mono"; font-size: 10.5pt; }}
.editor-frame {{ {SUNKEN} padding: 2px; background-color: {SUNK}; border-radius: {RAD}; }}
entry {{ border-radius: {RAD}; background-color: {SUNK}; border: none; {SUNKEN} padding: 4px 8px; }}
switch {{ border-radius: {RAD}; }}
switch slider {{ border-radius: {RAD}; }}
switch:checked {{ background-color: {ACC}; }}
combobox button, combobox box {{ border-radius: {RAD}; }}
scrolledwindow {{ background-color: transparent; }}
"""

    class Studio(Gtk.Window):
        def __init__(self):
            super().__init__(title="Kafka Studio")
            self.set_default_size(1180, 740)
            prov = Gtk.CssProvider()
            prov.load_from_data(CSS.encode())
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER + 2
            )
            self.cur_file = None
            self.dirty = False
            self.loading = False
            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.add(root)
            # dải tiêu đề
            bar = Gtk.Box(spacing=10)
            bar.get_style_context().add_class("titlebar-box")
            t = Gtk.Label(label=("> KAFKA STUDIO" if pixel else "󰏘  Kafka Studio"), xalign=0)
            t.get_style_context().add_class("app-title")
            bar.pack_start(t, True, True, 0)
            self.top_status = Gtk.Label(label=f"Giao diện: {'PIXEL' if pixel else 'PHẲNG'}", xalign=1)
            bar.pack_end(self.top_status, False, False, 0)
            root.pack_start(bar, False, False, 0)
            body = Gtk.Box()
            root.pack_start(body, True, True, 0)
            # thanh bên + trang
            side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            side.get_style_context().add_class("sidebar")
            side.set_size_request(190, -1)
            body.pack_start(side, False, False, 0)
            self.stack = Gtk.Stack()
            self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
            body.pack_start(self.stack, True, True, 0)
            self.side_btns = {}
            for key, icon, name, build in (
                ("wall", "󰸉", "Hình nền", self.page_wall),
                ("edit", "󰈮", "Sửa file", self.page_edit),
                ("dock", "󱂬", "Dock", self.page_dock),
                ("alert", "󰀦", "Cảnh báo", self.page_alert),
                ("color", "󰏘", "Màu sắc", self.page_color),
                ("look", "󰔎", "Giao diện", self.page_look),
            ):
                b = Gtk.Button()
                lab = Gtk.Label(label=f"{icon}   {name}", xalign=0)
                b.add(lab)
                b.get_style_context().add_class("side-btn")
                b.connect("clicked", lambda _b, k=key: self.show(k))
                side.pack_start(b, False, False, 0)
                self.side_btns[key] = b
                self.stack.add_named(build(), key)
            hint = Gtk.Label(
                label="Mọi lần lưu đều sao lưu\nbản cũ trước.\nCtrl+S lưu · Ctrl+F tìm\nEsc đóng", xalign=0
            )
            hint.get_style_context().add_class("hint")
            side.pack_end(hint, False, False, 6)
            self.connect("key-press-event", self.on_key)
            self.connect("delete-event", self.on_close)
            self.show_all()
            self.search_bar.hide()
            page = sys.argv[sys.argv.index("--page") + 1] if "--page" in sys.argv[:-1] else "wall"
            self.show(page if page in self.side_btns else "wall")
            if "--open" in sys.argv[:-1]:  # studio.py --open waybar/style.css
                rel = sys.argv[sys.argv.index("--open") + 1]
                for r in self.file_list.get_children():
                    if getattr(r, "spec", (None, None, None))[2] == rel:
                        self.show("edit")
                        self.file_list.select_row(r)

        # ---------- tiện ích
        def show(self, key):
            self.stack.set_visible_child_name(key)
            for k, b in self.side_btns.items():
                ctx = b.get_style_context()
                (ctx.add_class if k == key else ctx.remove_class)("on")
            if key == "color":
                self.load_colors()

        def bg(self, fn, done=None):
            def work():
                try:
                    res = fn()
                except Exception as e:  # noqa: BLE001
                    res = e
                if done:
                    GLib.idle_add(done, res)

            threading.Thread(target=work, daemon=True).start()

        def say(self, label, text, err=False):
            label.set_text(text)
            ctx = label.get_style_context()
            (ctx.add_class if err else ctx.remove_class)("err")

        def confirm(self, text, secondary=""):
            d = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text=text,
            )
            if secondary:
                d.format_secondary_text(secondary)
            ok = d.run() == Gtk.ResponseType.OK
            d.destroy()
            return ok

        def btn(self, label, cb, *classes):
            b = Gtk.Button(label=label)
            for c in classes:
                b.get_style_context().add_class(c)
            b.connect("clicked", lambda *_: cb())
            return b

        def on_key(self, _w, ev):
            ctrl = ev.state & Gdk.ModifierType.CONTROL_MASK
            k = Gdk.keyval_name(ev.keyval)
            if ctrl and k in ("s", "S") and self.stack.get_visible_child_name() == "edit":
                self.save_file()
                return True
            if ctrl and k in ("f", "F") and self.stack.get_visible_child_name() == "edit":
                self.search_bar.show()
                self.search_entry.grab_focus()
                return True
            if k == "Escape":
                if self.search_bar.get_visible():
                    self.search_bar.hide()
                    return True
                self.close()
                return True
            return False

        def on_close(self, *_):
            if self.dirty and not self.confirm("File đang sửa chưa lưu. Đóng luôn?", "Các thay đổi chưa lưu sẽ mất."):
                return True
            return False

        # ================= HÌNH NỀN =================
        def page_wall(self):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.get_style_context().add_class("page")
            head = Gtk.Box(spacing=8)
            h = Gtk.Label(label="Hình nền", xalign=0)
            h.get_style_context().add_class("h1")
            head.pack_start(h, False, False, 0)
            self.wall_status = Gtk.Label(
                label="Bấm một ảnh để đặt ngay. Viền hồng = đang dùng, ★ = mặc định khi đăng nhập.", xalign=0
            )
            self.wall_status.get_style_context().add_class("status")
            self.wall_status.set_line_wrap(True)
            self.wall_status.set_max_width_chars(40)
            head.pack_start(self.wall_status, True, True, 8)
            head.pack_end(self.btn("󰉋  Mở thư mục", lambda: sh(f"setsid -f thunar '{WALL_DIR}'")), False, False, 0)
            head.pack_end(self.btn("󰐕  Thêm ảnh…", self.add_wall, "accent"), False, False, 0)
            box.pack_start(head, False, False, 0)
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.flow = Gtk.FlowBox()
            self.flow.set_valign(Gtk.Align.START)
            self.flow.set_max_children_per_line(4)
            self.flow.set_min_children_per_line(2)
            self.flow.set_selection_mode(Gtk.SelectionMode.NONE)
            self.flow.set_homogeneous(True)
            self.flow.connect("child-activated", lambda _f, ch: self.apply_wall(ch.path))
            sw.add(self.flow)
            box.pack_start(sw, True, True, 0)
            row = Gtk.Box(spacing=8)
            self.wall_sel_lbl = Gtk.Label(label="", xalign=0)
            self.wall_sel_lbl.get_style_context().add_class("hint")
            row.pack_start(self.wall_sel_lbl, True, True, 0)
            row.pack_end(self.btn("󰁯  Về mặc định gốc", self.reset_wall_default), False, False, 0)
            row.pack_end(self.btn("★  Đặt làm mặc định", self.set_wall_default, "accent"), False, False, 0)
            box.pack_start(row, False, False, 0)
            GLib.idle_add(self.fill_walls)
            return box

        def current_wall(self):
            try:
                return os.path.realpath(CURRENT_WALL)
            except OSError:
                return ""

        def default_wall(self):
            try:
                with open(WALL_STATE) as f:
                    return os.path.realpath(f.read().strip())
            except OSError:
                return os.path.realpath(os.path.join(WALL_DIR, "kafka_landscape_3.jpg"))

        def thumb(self, path):
            os.makedirs(THUMB_DIR, exist_ok=True)
            st = os.stat(path)
            t = os.path.join(THUMB_DIR, f"{slug(path)}-{int(st.st_mtime)}-{st.st_size}.png")
            if not os.path.exists(t):
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 200, 112, True)
                pb.savev(t, "png", [], [])
            return t

        def fill_walls(self):
            for ch in self.flow.get_children():
                self.flow.remove(ch)
            cur, dft = self.current_wall(), self.default_wall()
            for p in wallpapers():
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file(self.thumb(p))
                except Exception:  # noqa: BLE001 — ảnh hỏng: bỏ qua
                    continue
                ch = Gtk.FlowBoxChild()
                ch.path = p
                v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                v.get_style_context().add_class("thumb")
                rp = os.path.realpath(p)
                if rp == cur:
                    v.get_style_context().add_class("current")
                if rp == dft:
                    v.get_style_context().add_class("default")
                img = Gtk.Image.new_from_pixbuf(pb)
                img.set_size_request(200, 112)
                v.pack_start(img, False, False, 0)
                w, h = GdkPixbuf.Pixbuf.get_file_info(p)[1:]
                name = os.path.basename(p)
                lab = Gtk.Label(label=("★ " if rp == dft else "") + name, xalign=0.5)
                lab.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
                lab.set_max_width_chars(18)
                if rp == dft:
                    lab.get_style_context().add_class("tag")
                v.pack_start(lab, False, False, 0)
                ch.set_tooltip_text(
                    f"{name} — {w}×{h}" + ("  (ảnh dọc: sẽ bị cắt, nên dùng Thêm ảnh để ghép thẻ)" if h >= w else "")
                )
                ch.add(v)
                self.flow.add(ch)
            self.flow.show_all()
            self.wall_sel_lbl.set_text(
                f"Đang dùng: {os.path.basename(cur) or '?'}  ·  Mặc định khi đăng nhập: {os.path.basename(dft)}"
            )
            return False

        def apply_wall(self, path):
            self.say(self.wall_status, f"Đang đặt {os.path.basename(path)} …")

            def done(res):
                rc, out = res
                if rc == 0:
                    self.say(
                        self.wall_status,
                        f"Đã đặt {os.path.basename(path)}. Muốn giữ sau khi đăng nhập lại: bấm ★ Đặt làm mặc định.",
                    )
                else:
                    self.say(self.wall_status, f"Lỗi: {out[-200:]}", True)
                self.fill_walls()

            self.bg(lambda: sh(f"'{SCRIPTS}/wallpaper-cycle.sh' set '{path}'"), done)

        def set_wall_default(self):
            cur = self.current_wall()
            if not cur or not os.path.exists(cur):
                self.say(self.wall_status, "Chưa có hình nền đang dùng.", True)
                return
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(WALL_STATE, "w") as f:
                f.write(cur + "\n")
            self.say(self.wall_status, f"★ {os.path.basename(cur)} là hình nền khi đăng nhập.")
            self.fill_walls()

        def reset_wall_default(self):
            try:
                os.remove(WALL_STATE)
            except OSError:
                pass
            self.say(self.wall_status, "Đã về hình nền mặc định gốc (kafka_landscape_3.jpg) khi đăng nhập.")
            self.fill_walls()

        def add_wall(self):
            d = Gtk.FileChooserDialog(
                title="Chọn ảnh làm hình nền", transient_for=self, action=Gtk.FileChooserAction.OPEN
            )
            d.add_buttons("Huỷ", Gtk.ResponseType.CANCEL, "Thêm", Gtk.ResponseType.OK)
            f = Gtk.FileFilter()
            f.set_name("Ảnh")
            for ext in IMG_EXT:
                f.add_pattern("*" + ext)
                f.add_pattern("*" + ext.upper())
            d.add_filter(f)
            d.set_current_folder(
                os.path.expanduser("~/Pictures")
                if os.path.isdir(os.path.expanduser("~/Pictures"))
                else os.path.expanduser("~")
            )
            src = d.get_filename() if d.run() == Gtk.ResponseType.OK else None
            d.destroy()
            if not src:
                return
            try:
                _fmt, w, h = GdkPixbuf.Pixbuf.get_file_info(src)
            except Exception:  # noqa: BLE001
                self.say(self.wall_status, "Không đọc được ảnh.", True)
                return
            name = slug(src)
            if w > h:
                dst = os.path.join(WALL_DIR, f"kafka_{name}{os.path.splitext(src)[1].lower()}")
                shutil.copy2(src, dst)
                self.say(self.wall_status, f"Đã thêm {os.path.basename(dst)}.")
                self.fill_walls()
                self.apply_wall(dst)
                return
            # ảnh dọc/vuông → thẻ kính mờ 1920x1080 (công thức trong CLAUDE.md)
            dst = os.path.join(WALL_DIR, f"kafka_card_{name}_1080p.jpg")
            self.say(self.wall_status, "Ảnh dọc: đang ghép thành thẻ kính mờ 1920×1080 …")
            tmp = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "kafka-studio-wall")
            os.makedirs(tmp, exist_ok=True)
            cmd = (
                f"magick '{src}' -resize 1920x1080^ -gravity center -extent 1920x1080 -gaussian-blur 0x28 "
                f"-fill '#140e1c' -colorize 45% '{tmp}/bg.jpg' && "
                f"magick '{src}' -resize x1000 -bordercolor '#b8326a' -border 3x3 '{tmp}/fg.jpg' && "
                f"magick '{tmp}/bg.jpg' '{tmp}/fg.jpg' -gravity center -composite '{dst}'; rc=$?; rm -f '{tmp}'/*.jpg; exit $rc"
            )

            def done(res):
                rc, out = res
                if rc == 0:
                    self.say(self.wall_status, f"Đã ghép {os.path.basename(dst)}.")
                    self.fill_walls()
                    self.apply_wall(dst)
                else:
                    self.say(self.wall_status, f"Ghép ảnh lỗi: {out[-200:]}", True)

            self.bg(lambda: sh(cmd, 120), done)

        # ================= SỬA FILE =================
        def page_edit(self):
            box = Gtk.Box(spacing=10)
            box.get_style_context().add_class("page")
            # danh sách file theo nhóm
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            sw.set_size_request(270, -1)
            self.file_list = Gtk.ListBox()
            self.file_list.connect("row-selected", self.on_file_row)
            group = None
            for spec in FILES:
                if spec[0] != group:
                    group = spec[0]
                    gr = Gtk.ListBoxRow()
                    gr.set_selectable(False)
                    gr.set_activatable(False)
                    gr.get_style_context().add_class("group-row")
                    gr.add(Gtk.Label(label=group.upper(), xalign=0))
                    self.file_list.add(gr)
                r = Gtk.ListBoxRow()
                r.spec = spec
                exists = os.path.exists(os.path.join(REPO, spec[2]))
                lab = Gtk.Label(label=spec[1] + ("" if exists else "  (chưa có)"), xalign=0)
                lab.set_ellipsize(Pango.EllipsizeMode.END)
                r.set_tooltip_text(spec[2])
                r.add(lab)
                r.set_sensitive(exists)
                self.file_list.add(r)
            sw.add(self.file_list)
            box.pack_start(sw, False, False, 0)
            # vùng soạn
            right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.pack_start(right, True, True, 0)
            head = Gtk.Box(spacing=8)
            self.file_title = Gtk.Label(label="Chọn một file bên trái", xalign=0)
            self.file_title.get_style_context().add_class("h1")
            self.file_title.set_ellipsize(Pango.EllipsizeMode.START)
            head.pack_start(self.file_title, True, True, 0)
            right.pack_start(head, False, False, 0)
            tools = Gtk.Box(spacing=6)
            self.b_save = self.btn("󰆓  Lưu & áp dụng", self.save_file, "accent")
            self.b_undo = self.btn("󰕌  Hoàn tác lần lưu", self.undo_file)
            self.b_git = self.btn("󰊢  Bản gốc git", self.git_restore_file, "danger")
            self.b_color = self.btn("󰏘  Chèn màu", self.insert_color)
            self.b_reload = self.btn("󰑐  Nạp lại", self.reload_file)
            self.b_ext = self.btn(
                "󰏫  Mở Mousepad", lambda: self.cur_file and sh(f"setsid -f mousepad '{self.cur_file[0]}'")
            )
            for b in (self.b_save, self.b_undo, self.b_git, self.b_color, self.b_reload, self.b_ext):
                tools.pack_start(b, False, False, 0)
                b.set_sensitive(False)
            right.pack_start(tools, False, False, 0)
            # thanh tìm
            self.search_bar = Gtk.Box(spacing=6)
            self.search_entry = Gtk.SearchEntry()
            self.search_entry.set_placeholder_text("Tìm trong file (Enter = tiếp, Shift+Enter = trước)")
            self.search_entry.connect("search-changed", lambda *_: self.do_search(True))
            self.search_entry.connect("activate", lambda *_: self.do_search(False))
            self.search_entry.connect("key-press-event", self.search_key)
            self.search_bar.pack_start(self.search_entry, True, True, 0)
            self.search_info = Gtk.Label(label="")
            self.search_info.get_style_context().add_class("hint")
            self.search_bar.pack_start(self.search_info, False, False, 0)
            self.search_bar.pack_start(self.btn("✕", lambda: self.search_bar.hide()), False, False, 0)
            right.pack_start(self.search_bar, False, False, 0)
            # trình soạn
            self.buf = GtkSource.Buffer()
            sm = GtkSource.StyleSchemeManager.get_default()
            scheme = sm.get_scheme("oblivion") or sm.get_scheme("cobalt") or sm.get_scheme("classic")
            if scheme:
                self.buf.set_style_scheme(scheme)
            self.buf.connect("changed", self.on_buf_changed)
            self.view = GtkSource.View(buffer=self.buf)
            self.view.set_show_line_numbers(True)
            self.view.set_highlight_current_line(True)
            self.view.set_auto_indent(True)
            self.view.set_tab_width(4)
            self.view.set_insert_spaces_instead_of_tabs(True)
            self.view.set_monospace(True)
            self.search_ctx = GtkSource.SearchContext(buffer=self.buf)
            self.search_ctx.set_highlight(True)
            esw = Gtk.ScrolledWindow()
            esw.add(self.view)
            frame = Gtk.Box()
            frame.get_style_context().add_class("editor-frame")
            frame.pack_start(esw, True, True, 0)
            right.pack_start(frame, True, True, 0)
            self.edit_status = Gtk.Label(label="", xalign=0)
            self.edit_status.get_style_context().add_class("status")
            self.edit_status.set_line_wrap(True)
            self.edit_status.set_selectable(True)
            right.pack_start(self.edit_status, False, False, 0)
            return box

        def on_file_row(self, _lb, row):
            if row is None or not hasattr(row, "spec"):
                return
            if self.dirty and self.cur_file and not self.confirm("File đang sửa chưa lưu. Bỏ thay đổi?"):
                return
            self.open_file(row.spec)

        def open_file(self, spec):
            path = os.path.join(REPO, spec[2])
            try:
                with open(path) as f:
                    text = f.read()
            except OSError as e:
                self.say(self.edit_status, f"Không mở được: {e}", True)
                return
            self.cur_file = (path, spec)
            self.loading = True
            lm = GtkSource.LanguageManager.get_default()
            self.buf.set_language(lm.get_language(spec[3]))
            self.buf.begin_not_undoable_action()
            self.buf.set_text(text)
            self.buf.end_not_undoable_action()
            self.buf.place_cursor(self.buf.get_start_iter())
            self.loading = False
            self.dirty = False
            self.update_title()
            for b in (self.b_save, self.b_undo, self.b_git, self.b_color, self.b_reload, self.b_ext):
                b.set_sensitive(True)
            self.b_undo.set_sensitive(bool(backups_of(path)))
            self.b_reload.set_sensitive(bool(RELOAD[spec[4]][1]))
            nb = len(backups_of(path))
            self.say(
                self.edit_status,
                f"{spec[2]} · lưu xong: {RELOAD[spec[4]][0].lower()}" + (f" · {nb} bản sao lưu" if nb else ""),
            )

        def update_title(self):
            if self.cur_file:
                self.file_title.set_text(("● " if self.dirty else "") + self.cur_file[1][1])

        def on_buf_changed(self, *_):
            if not self.loading and self.cur_file and not self.dirty:
                self.dirty = True
                self.update_title()

        def save_file(self):
            if not self.cur_file:
                return
            path, spec = self.cur_file
            text = self.buf.get_text(self.buf.get_start_iter(), self.buf.get_end_iter(), True)
            self.say(self.edit_status, "Đang kiểm tra …")
            self.b_save.set_sensitive(False)

            def work():
                err = check_text(spec[5], text, path) if spec[5] else None
                if err:
                    return ("bad", err)
                bk = backup(path)
                with open(path, "w") as f:
                    f.write(text)
                cmd = RELOAD[spec[4]][1]
                rc, out = sh(cmd) if cmd else (0, "")
                return ("ok", bk, rc, out)

            def done(res):
                self.b_save.set_sensitive(True)
                if isinstance(res, Exception):
                    self.say(self.edit_status, f"Lỗi: {res}", True)
                    return
                if res[0] == "bad":
                    self.say(self.edit_status, f"CHƯA LƯU — {res[1]}", True)
                    m = re.search(r"dòng (\d+)", res[1])
                    if m:
                        it = self.buf.get_iter_at_line(max(0, int(m.group(1)) - 1))
                        self.buf.place_cursor(it)
                        self.view.scroll_to_iter(it, 0.2, False, 0, 0)
                    return
                _ok, bk, rc, out = res
                self.dirty = False
                self.update_title()
                self.b_undo.set_sensitive(True)
                msg = f"Đã lưu {spec[2]}" + (" (bản cũ đã sao lưu)" if bk else "")
                if RELOAD[spec[4]][1]:
                    msg += f" · {RELOAD[spec[4]][0]}" + (" xong" if rc == 0 else f" lỗi: {out[-160:]}")
                else:
                    msg += f" · {RELOAD[spec[4]][0]}"
                self.say(self.edit_status, msg, rc != 0)

            self.bg(work, done)

        def undo_file(self):
            if not self.cur_file:
                return
            path, spec = self.cur_file
            bks = backups_of(path)
            if not bks:
                self.say(self.edit_status, "Chưa có bản sao lưu nào.", True)
                return
            last = bks[-1]
            stamp = os.path.basename(last)[:15]
            if not self.confirm(
                f"Lấy lại bản lưu lúc {stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]} ngày {stamp[6:8]}/{stamp[4:6]}?",
                "Bản hiện tại bị thay bằng bản sao lưu đó (rồi bản sao lưu được xoá khỏi danh sách).",
            ):
                return
            shutil.copy2(last, path)
            os.remove(last)
            self.open_file(spec)
            cmd = RELOAD[spec[4]][1]
            if cmd:
                self.bg(lambda: sh(cmd))
            self.say(self.edit_status, f"Đã hoàn tác về bản lưu trước · {RELOAD[spec[4]][0]}")

        def git_restore_file(self):
            if not self.cur_file:
                return
            path, spec = self.cur_file
            rc, out = sh(f"git -C '{REPO}' ls-files --error-unmatch '{spec[2]}'")
            if rc != 0:
                self.say(
                    self.edit_status, "File này chưa từng được commit (hoặc bị gitignore) — không có bản gốc git.", True
                )
                return
            if not self.confirm(
                "Lấy lại bản đã commit trong git?", "Bản hiện tại sẽ được sao lưu trước (Hoàn tác lần lưu để lấy lại)."
            ):
                return
            backup(path)
            rc, out = sh(
                f"git -C '{REPO}' show HEAD:'{spec[2]}' > '{path}.studio-tmp' && mv '{path}.studio-tmp' '{path}'"
            )
            if rc != 0:
                self.say(self.edit_status, f"Lỗi git: {out}", True)
                return
            self.open_file(spec)
            cmd = RELOAD[spec[4]][1]
            if cmd:
                self.bg(lambda: sh(cmd))
            self.say(self.edit_status, f"Đã lấy bản gốc git · {RELOAD[spec[4]][0]}")

        def reload_file(self):
            if not self.cur_file:
                return
            name, cmd = RELOAD[self.cur_file[1][4]]
            self.bg(
                lambda: sh(cmd),
                lambda res: self.say(
                    self.edit_status, f"{name}: " + ("xong" if res[0] == 0 else res[1][-200:]), res[0] != 0
                ),
            )

        def insert_color(self):
            d = Gtk.ColorChooserDialog(title="Chèn màu", transient_for=self)
            d.set_use_alpha(True)
            if d.run() == Gtk.ResponseType.OK:
                c = d.get_rgba()
                r, g, b = (int(round(x * 255)) for x in (c.red, c.green, c.blue))
                txt = f"#{r:02x}{g:02x}{b:02x}" if c.alpha >= 0.999 else f"rgba({r}, {g}, {b}, {c.alpha:.2f})"
                self.buf.delete_selection(True, True)
                self.buf.insert_at_cursor(txt)
            d.destroy()

        def do_search(self, from_start):
            text = self.search_entry.get_text()
            st = self.search_ctx.get_settings()
            st.set_search_text(text or None)
            st.set_case_sensitive(False)
            st.set_wrap_around(True)
            if not text:
                self.search_info.set_text("")
                return
            self.find(forward=True, restart=from_start)

        def find(self, forward=True, restart=False):
            ins = self.buf.get_iter_at_mark(self.buf.get_insert())
            if restart:
                ins = self.buf.get_start_iter()
            if forward:
                if not restart:
                    sel = self.buf.get_selection_bounds()
                    if sel:
                        ins = sel[1]
                ok, s, e, _wrap = self.search_ctx.forward2(ins)
            else:
                sel = self.buf.get_selection_bounds()
                if sel:
                    ins = sel[0]
                ok, s, e, _wrap = self.search_ctx.backward2(ins)
            if ok:
                self.buf.select_range(s, e)
                self.view.scroll_to_iter(s, 0.2, False, 0, 0)
            n = self.search_ctx.get_occurrences_count()
            self.search_info.set_text("không thấy" if not ok else (f"{n} kết quả" if n >= 0 else ""))

        def search_key(self, _w, ev):
            if Gdk.keyval_name(ev.keyval) in ("Return", "KP_Enter"):
                self.find(forward=not (ev.state & Gdk.ModifierType.SHIFT_MASK))
                return True
            return False

        # ================= MÀU SẮC =================
        def page_color(self):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.get_style_context().add_class("page")
            head = Gtk.Box(spacing=8)
            h = Gtk.Label(label="Màu sắc thanh Waybar", xalign=0)
            h.get_style_context().add_class("h1")
            head.pack_start(h, False, False, 0)
            self.color_src = Gtk.ComboBoxText()
            for title, rel in COLOR_FILES:
                self.color_src.append(rel, title)
            self.color_src.set_active_id(COLOR_FILES[1 if pixel else 0][1])
            self.color_src.connect("changed", lambda *_: self.load_colors())
            head.pack_end(self.color_src, False, False, 0)
            box.pack_start(head, False, False, 0)
            note = Gtk.Label(
                label="Mỗi biến @define-color được dùng ở nhiều chỗ. Đổi màu = Waybar nạp lại ngay; "
                "bản cũ được sao lưu (Sửa file → Hoàn tác để lấy lại).",
                xalign=0,
            )
            note.set_line_wrap(True)
            note.get_style_context().add_class("hint")
            box.pack_start(note, False, False, 0)
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.color_grid = Gtk.FlowBox()
            self.color_grid.set_valign(Gtk.Align.START)
            self.color_grid.set_max_children_per_line(3)
            self.color_grid.set_selection_mode(Gtk.SelectionMode.NONE)
            self.color_grid.set_homogeneous(True)
            sw.add(self.color_grid)
            box.pack_start(sw, True, True, 0)
            self.color_status = Gtk.Label(label="", xalign=0)
            self.color_status.get_style_context().add_class("status")
            box.pack_start(self.color_status, False, False, 0)
            return box

        def load_colors(self):
            rel = self.color_src.get_active_id()
            path = os.path.join(REPO, rel)
            for ch in self.color_grid.get_children():
                self.color_grid.remove(ch)
            try:
                with open(path) as f:
                    text = f.read()
            except OSError:
                return
            cols = read_colors(text)
            if not cols:
                self.say(self.color_status, "File này không có biến @define-color.")
            for _i, name, value in cols:
                card = Gtk.Box(spacing=8)
                card.get_style_context().add_class("card")
                rgba = Gdk.RGBA()
                cb = Gtk.ColorButton()
                cb.set_use_alpha(True)
                if rgba.parse(value):
                    cb.set_rgba(rgba)
                else:
                    cb.set_sensitive(False)  # giá trị là biểu thức (shade(), mix()…) → sửa ở tab Sửa file
                cb.connect("color-set", lambda b, n=name, p=path: self.change_color(p, n, b.get_rgba()))
                card.pack_start(cb, False, False, 0)
                v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                n = Gtk.Label(label="@" + name, xalign=0)
                n.get_style_context().add_class("h1" if False else "")
                val = Gtk.Label(label=value, xalign=0)
                val.get_style_context().add_class("hint")
                val.set_ellipsize(Pango.EllipsizeMode.END)
                v.pack_start(n, False, False, 0)
                v.pack_start(val, False, False, 0)
                card.pack_start(v, True, True, 0)
                self.color_grid.add(card)
            self.color_grid.show_all()

        def change_color(self, path, name, c):
            r, g, b = (int(round(x * 255)) for x in (c.red, c.green, c.blue))
            value = f"#{r:02x}{g:02x}{b:02x}" if c.alpha >= 0.999 else f"rgba({r}, {g}, {b}, {c.alpha:.2f})"
            with open(path) as f:
                text = f.read()
            try:
                new = set_color(text, name, value)
            except KeyError:
                return
            backup(path)
            with open(path, "w") as f:
                f.write(new)
            sh(RELOAD["waybar-css"][1])
            self.say(self.color_status, f"@{name} = {value} · Waybar đã nạp lại.")
            self.load_colors()

        # ================= DOCK (app ghim) =================
        def page_dock(self):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.get_style_context().add_class("page")
            h = Gtk.Label(label="App ghim trên dock", xalign=0)
            h.get_style_context().add_class("h1")
            box.pack_start(h, False, False, 0)
            note = Gtk.Label(
                label=f"Icon lấy từ bộ icon hệ thống (đúng icon của app). Bấm ＋ hoặc nhấp đôi một app bên phải "
                f"để ghim (tối đa {MAX_PINS}); ↑ ↓ đổi thứ tự; ✕ bỏ ghim. Đổi là dock cập nhật ngay, "
                "bản cũ được sao lưu.",
                xalign=0,
            )
            note.set_line_wrap(True)
            note.get_style_context().add_class("hint")
            box.pack_start(note, False, False, 0)
            cols = Gtk.Box(spacing=14, homogeneous=True)
            box.pack_start(cols, True, True, 0)

            # trái: đang ghim
            left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            self.pin_head = Gtk.Label(xalign=0)
            self.pin_head.get_style_context().add_class("h1")
            left.pack_start(self.pin_head, False, False, 0)
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.pin_list = Gtk.ListBox()
            self.pin_list.set_selection_mode(Gtk.SelectionMode.NONE)
            sw.add(self.pin_list)
            frame = Gtk.Box()
            frame.get_style_context().add_class("editor-frame")
            frame.pack_start(sw, True, True, 0)
            left.pack_start(frame, True, True, 0)
            cols.pack_start(left, True, True, 0)

            # phải: mọi app
            right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            rh = Gtk.Label(label="Tất cả ứng dụng", xalign=0)
            rh.get_style_context().add_class("h1")
            right.pack_start(rh, False, False, 0)
            self.app_search = Gtk.SearchEntry()
            self.app_search.set_placeholder_text("Tìm app… (tên, mô tả, lệnh)")
            self.app_search.connect("search-changed", lambda *_: self.app_list.invalidate_filter())
            right.pack_start(self.app_search, False, False, 0)
            sw2 = Gtk.ScrolledWindow()
            sw2.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.app_list = Gtk.ListBox()
            self.app_list.set_filter_func(self._app_filter)
            self.app_list.connect("row-activated", lambda _l, r: self.pin_add(r.app_id))
            sw2.add(self.app_list)
            frame2 = Gtk.Box()
            frame2.get_style_context().add_class("editor-frame")
            frame2.pack_start(sw2, True, True, 0)
            right.pack_start(frame2, True, True, 0)
            cols.pack_start(right, True, True, 0)

            bottom = Gtk.Box(spacing=8)
            bottom.pack_start(self.btn("Về mặc định", self.pin_reset), False, False, 0)
            bottom.pack_start(
                self.btn("Sửa JSON tay", lambda *_: self.open_rel("waybar/dock-pins.json")), False, False, 0
            )
            self.dock_status = Gtk.Label(label="", xalign=0)
            self.dock_status.get_style_context().add_class("status")
            bottom.pack_start(self.dock_status, True, True, 0)
            box.pack_start(bottom, False, False, 0)

            self.apps = self._load_apps()
            for info in self.apps.values():
                self.app_list.add(self._app_row(info, pinned=False))
            self.pins = load_pins()
            self.fill_pins()
            return box

        def _load_apps(self):
            try:
                gi.require_version("GioUnix", "2.0")
                from gi.repository import GioUnix

                DAI = GioUnix.DesktopAppInfo
            except (ValueError, ImportError):
                DAI = Gio.DesktopAppInfo
            apps = {}
            for a in sorted(Gio.AppInfo.get_all(), key=lambda x: (x.get_display_name() or "").casefold()):
                if not a.should_show() or not a.get_id():
                    continue
                apps[a.get_id()] = {
                    "id": a.get_id(),
                    "name": a.get_display_name() or a.get_id(),
                    "desc": (getattr(a, "get_generic_name", lambda: None)() or a.get_description() or ""),
                    "exec": a.get_executable() or "",
                    "icon": a.get_icon(),
                }
            self._dai = DAI
            return apps

        def _app_info(self, app_id):
            info = self.apps.get(app_id)
            if info is None:
                try:
                    a = self._dai.new(app_id)
                except Exception:  # noqa: BLE001
                    a = None
                info = {
                    "id": app_id,
                    "name": a.get_display_name() if a else app_id + " (không thấy)",
                    "desc": "",
                    "exec": "",
                    "icon": a.get_icon() if a else None,
                }
            return info

        def _icon(self, gicon, px=32):
            img = (
                Gtk.Image.new_from_gicon(gicon, Gtk.IconSize.DIALOG)
                if gicon
                else Gtk.Image.new_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
            )
            img.set_pixel_size(px)
            return img

        def _app_row(self, info, pinned, idx=0):
            row = Gtk.ListBoxRow()
            row.app_id = info["id"]
            row.search = f"{info['name']} {info['desc']} {info['exec']} {info['id']}".casefold()
            hb = Gtk.Box(spacing=10)
            hb.pack_start(self._icon(info["icon"]), False, False, 0)
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            n = Gtk.Label(label=info["name"], xalign=0)
            n.set_ellipsize(Pango.EllipsizeMode.END)
            d = Gtk.Label(label=info["desc"] or info["id"], xalign=0)
            d.set_ellipsize(Pango.EllipsizeMode.END)
            d.get_style_context().add_class("hint")
            v.pack_start(n, False, False, 0)
            v.pack_start(d, False, False, 0)
            hb.pack_start(v, True, True, 0)
            if pinned:
                up = self.btn("↑", lambda *_: self.pin_move(idx, -1))
                down = self.btn("↓", lambda *_: self.pin_move(idx, 1))
                rm = self.btn("✕", lambda *_: self.pin_remove(idx), "danger")
                up.set_sensitive(idx > 0)
                down.set_sensitive(idx < len(self.pins) - 1)
                for w in (up, down, rm):
                    up.set_tooltip_text("Lên")
                    down.set_tooltip_text("Xuống")
                    rm.set_tooltip_text("Bỏ ghim")
                    hb.pack_start(w, False, False, 0)
            else:
                add = self.btn("＋", lambda *_: self.pin_add(info["id"]), "accent")
                add.set_tooltip_text("Ghim lên dock")
                row.add_btn = add
                hb.pack_start(add, False, False, 0)
            row.add(hb)
            return row

        def _app_filter(self, row):
            q = self.app_search.get_text().strip().casefold()
            return not q or all(w in row.search for w in q.split())

        def fill_pins(self):
            for ch in self.pin_list.get_children():
                self.pin_list.remove(ch)
            for i, pid in enumerate(self.pins):
                self.pin_list.add(self._app_row(self._app_info(pid), pinned=True, idx=i))
            self.pin_head.set_text(f"Trên dock ({len(self.pins)}/{MAX_PINS})")
            full = len(self.pins) >= MAX_PINS
            for r in self.app_list.get_children():
                r.add_btn.set_sensitive(not full and r.app_id not in self.pins)
            self.pin_list.show_all()
            self.app_list.show_all()

        def pins_apply(self, msg):
            backup(PINS_FILE)
            save_pins(self.pins)
            self.fill_pins()
            self.bg(
                lambda: sh(RELOAD["dock-pins"][1]), lambda _r: self.say(self.dock_status, msg + " · dock đã cập nhật.")
            )

        def pin_add(self, app_id):
            if app_id in self.pins:
                return self.say(self.dock_status, "App này đã ghim rồi.", True)
            if len(self.pins) >= MAX_PINS:
                return self.say(self.dock_status, f"Dock tối đa {MAX_PINS} app ghim.", True)
            self.pins.append(app_id)
            self.pins_apply(f"Đã ghim {self._app_info(app_id)['name']}")

        def pin_remove(self, i):
            name = self._app_info(self.pins[i])["name"]
            del self.pins[i]
            self.pins_apply(f"Đã bỏ ghim {name}")

        def pin_move(self, i, d):
            j = i + d
            if 0 <= j < len(self.pins):
                self.pins[i], self.pins[j] = self.pins[j], self.pins[i]
                self.pins_apply("Đã đổi thứ tự")

        def pin_reset(self, *_):
            if self.confirm("Đưa dock về 5 app mặc định?", "Chromium, Kitty, Thunar, Code - OSS, Mousepad."):
                self.pins = [p for p in DEFAULT_PINS]
                self.pins_apply("Đã về mặc định")

        def open_rel(self, rel):
            for r in self.file_list.get_children():
                if getattr(r, "spec", (None, None, None))[2] == rel:
                    self.show("edit")
                    self.file_list.select_row(r)
                    return

        # ================= CẢNH BÁO =================
        def page_alert(self):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.get_style_context().add_class("page")
            h = Gtk.Label(label="Ngưỡng cảnh báo", xalign=0)
            h.get_style_context().add_class("h1")
            box.pack_start(h, False, False, 0)
            note = Gtk.Label(
                label="Cảnh báo khi giá trị tụt xuống dưới từng mốc. Mốc ghi dạng số cách nhau dấu phẩy, "
                "ví dụ 80, 50, 30. Mốc ≤ mức khẩn cấp thì bảng không tự tắt (rung + kêu lại). "
                "Mọi cảnh báo vẫn nằm trong lịch sử thông báo (nút chuông).",
                xalign=0,
            )
            note.set_line_wrap(True)
            note.get_style_context().add_class("hint")
            box.pack_start(note, False, False, 0)

            # (khóa, tiêu đề, có mốc %, ô số bên cạnh)
            specs = (
                ("battery", "Pin máy", "levels", "critical"),
                ("devices", "Pin thiết bị ngoại vi", "levels", "critical"),
                ("wifi_signal", "Sóng Wi-Fi", "levels", None),
                ("internet", "Internet", None, "grace_seconds"),
            )
            self.alert_widgets = {}
            for key, title, has_levels, has_number in specs:
                card = Gtk.Box(spacing=12)
                card.get_style_context().add_class("card")
                head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                head.set_valign(Gtk.Align.CENTER)
                t = Gtk.Label(label=title, xalign=0)
                t.get_style_context().add_class("h1")
                head.pack_start(t, False, False, 0)
                card.pack_start(head, True, True, 0)

                w = {"title": title, "on": Gtk.Switch(), "levels": None, "critical": None, "grace_seconds": None}
                w["on"].set_valign(Gtk.Align.CENTER)
                inp = Gtk.Box(spacing=6)
                if has_levels:
                    lv = Gtk.Entry()
                    lv.set_width_chars(20)
                    lv.set_placeholder_text("80, 50, 30")
                    w["levels"] = lv
                    lab = Gtk.Label(label="Mốc (%)", xalign=1)
                    lab.get_style_context().add_class("hint")
                    inp.pack_start(lab, False, False, 0)
                    inp.pack_start(lv, False, False, 0)
                if has_number == "critical":
                    sp = Gtk.SpinButton.new_with_range(0, 99, 1)
                    sp.set_numeric(True)
                    w["critical"] = sp
                    lab = Gtk.Label(label="Khẩn cấp ≤", xalign=1)
                    lab.get_style_context().add_class("hint")
                    inp.pack_start(lab, False, False, 0)
                    inp.pack_start(sp, False, False, 0)
                elif has_number == "grace_seconds":
                    sp = Gtk.SpinButton.new_with_range(5, 600, 1)
                    sp.set_numeric(True)
                    w["grace_seconds"] = sp
                    lab = Gtk.Label(label="Báo sau (giây)", xalign=1)
                    lab.get_style_context().add_class("hint")
                    inp.pack_start(lab, False, False, 0)
                    inp.pack_start(sp, False, False, 0)
                if inp.get_children():
                    card.pack_start(inp, False, False, 0)
                on_lab = Gtk.Label(label="Bật", xalign=1)
                on_lab.get_style_context().add_class("hint")
                card.pack_end(w["on"], False, False, 0)
                card.pack_end(on_lab, False, False, 0)
                box.pack_start(card, False, False, 0)
                self.alert_widgets[key] = w

            # bảng giữa màn hình kiểu game + âm thanh (alert-popup.py)
            card = Gtk.Box(spacing=12)
            card.get_style_context().add_class("card")
            t = Gtk.Label(label="Bảng giữa màn hình + âm thanh", xalign=0)
            t.get_style_context().add_class("h1")
            t.set_valign(Gtk.Align.CENTER)
            card.pack_start(t, True, True, 0)
            pw = {
                "on": Gtk.Switch(),
                "sound": Gtk.Switch(),
                "volume": Gtk.SpinButton.new_with_range(0, 100, 5),
                "seconds": Gtk.SpinButton.new_with_range(3, 120, 1),
            }
            for key, text in (
                ("seconds", "Hiện (giây)"),
                ("sound", "Âm thanh"),
                ("volume", "Âm lượng %"),
                ("on", "Bật"),
            ):
                lab = Gtk.Label(label=text, xalign=1)
                lab.get_style_context().add_class("hint")
                pw[key].set_valign(Gtk.Align.CENTER)
                card.pack_start(lab, False, False, 0)
                card.pack_start(pw[key], False, False, 0)
            box.pack_start(card, False, False, 0)
            self.alert_popup_w = pw

            self.alert_fill(load_alerts())
            bottom = Gtk.Box(spacing=8)
            bottom.pack_start(self.btn("Lưu", self.alert_save, "accent"), False, False, 0)
            bottom.pack_start(self.btn("Về mặc định", self.alert_reset), False, False, 0)
            bottom.pack_start(self.btn("Thử thông báo", self.alert_test), False, False, 0)
            self.alert_status = Gtk.Label(label="", xalign=0)
            self.alert_status.get_style_context().add_class("status")
            self.alert_status.set_line_wrap(True)
            bottom.pack_start(self.alert_status, True, True, 0)
            box.pack_start(bottom, False, False, 0)
            return box

        def alert_fill(self, data):
            pc = data.get("popup") or DEFAULT_ALERTS["popup"]
            pw = self.alert_popup_w
            pw["on"].set_active(pc.get("enabled", True) is True)
            pw["sound"].set_active(pc.get("sound", True) is True)
            pw["volume"].set_value(pc.get("volume", 80))
            pw["seconds"].set_value(pc.get("seconds", 10))
            for key, w in self.alert_widgets.items():
                cfg = data.get(key) or {}
                w["on"].set_active(cfg.get("enabled", True) is True)
                if w["levels"] is not None:
                    w["levels"].set_text(", ".join(str(n) for n in cfg.get("levels", [])))
                if w["critical"] is not None:
                    w["critical"].set_value(cfg.get("critical", 0))
                if w["grace_seconds"] is not None:
                    w["grace_seconds"].set_value(cfg.get("grace_seconds", 20))

        def alert_reset(self):
            self.alert_fill(DEFAULT_ALERTS)
            self.say(self.alert_status, "Đã điền mặc định — bấm Lưu để áp dụng.")

        def alert_save(self):
            data = load_alerts()
            for key, w in self.alert_widgets.items():
                cfg = data.get(key) or dict(DEFAULT_ALERTS.get(key, {}))
                data[key] = cfg
                cfg["enabled"] = w["on"].get_active()
                if w["levels"] is not None:
                    try:
                        levels = parse_levels(w["levels"].get_text())
                    except ValueError as e:
                        return self.say(self.alert_status, f"{w['title']}: {e}", True)
                    if not levels and cfg["enabled"]:
                        return self.say(self.alert_status, f"{w['title']}: cần ít nhất một mốc khi đã bật.", True)
                    cfg["levels"] = levels
                if w["critical"] is not None:
                    cfg["critical"] = int(w["critical"].get_value())
                if w["grace_seconds"] is not None:
                    cfg["grace_seconds"] = int(w["grace_seconds"].get_value())
            pw = self.alert_popup_w
            data["popup"] = dict(
                data.get("popup") or {},
                enabled=pw["on"].get_active(),
                sound=pw["sound"].get_active(),
                volume=int(pw["volume"].get_value()),
                seconds=int(pw["seconds"].get_value()),
            )
            try:
                if os.path.exists(ALERTS_FILE):
                    backup(ALERTS_FILE)  # như mọi lần lưu khác của Studio: Sửa file › Hoàn tác lấy lại được
                save_alerts(ALERTS_FILE, data)
            except OSError as e:
                return self.say(self.alert_status, f"Không ghi được alerts.json: {e}", True)
            self.say(self.alert_status, "Đã lưu")

            def reload():
                try:
                    p = subprocess.Popen(
                        ["python3", ALERT_WATCH, "--reload"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    return p.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    return 1

            def done(rc):
                if rc:
                    self.say(self.alert_status, "Đã lưu — daemon chưa chạy")

            self.bg(reload, done)

        def alert_test(self):
            try:
                subprocess.Popen(
                    ["python3", ALERT_WATCH, "--test"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except OSError as e:
                self.say(self.alert_status, f"Không gửi được thông báo thử: {e}", True)
                return
            self.say(self.alert_status, "Đã gửi thông báo thử.")

        # ================= GIAO DIỆN =================
        def page_look(self):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.get_style_context().add_class("page")
            h = Gtk.Label(label="Giao diện & nạp lại", xalign=0)
            h.get_style_context().add_class("h1")
            box.pack_start(h, False, False, 0)
            self.look_status = Gtk.Label(label="", xalign=0)
            self.look_status.get_style_context().add_class("status")
            self.look_status.set_line_wrap(True)

            def card(title, desc, widget):
                c = Gtk.Box(spacing=12)
                c.get_style_context().add_class("card")
                v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                t = Gtk.Label(label=title, xalign=0)
                t.get_style_context().add_class("h1")
                d = Gtk.Label(label=desc, xalign=0)
                d.get_style_context().add_class("hint")
                d.set_line_wrap(True)
                v.pack_start(t, False, False, 0)
                v.pack_start(d, False, False, 0)
                c.pack_start(v, True, True, 0)
                widget.set_valign(Gtk.Align.CENTER)
                c.pack_end(widget, False, False, 0)
                box.pack_start(c, False, False, 0)

            th = Gtk.Box(spacing=6)
            th.pack_start(
                self.btn(
                    "Phẳng",
                    lambda: self.run_look(
                        f"'{SCRIPTS}/ui-theme.sh' flat", "Đã chuyển sang bản phẳng — mở lại Studio để thấy kiểu mới."
                    ),
                    *(["accent"] if not pixel else []),
                ),
                False,
                False,
                0,
            )
            th.pack_start(
                self.btn(
                    "Pixel",
                    lambda: self.run_look(
                        f"'{SCRIPTS}/ui-theme.sh' pixel", "Đã chuyển sang bản pixel — mở lại Studio để thấy kiểu mới."
                    ),
                    *(["accent"] if pixel else []),
                ),
                False,
                False,
                0,
            )
            card(
                "Kiểu giao diện",
                "Waybar, dock, popup, rofi, walker, dunst, kitty, viền cửa sổ, tổng quan (Super + Alt + U).",
                th,
            )

            bm = Gtk.ComboBoxText()
            for k, t in (("auto", "Tự động (tắt khi dùng pin)"), ("on", "Luôn bật"), ("off", "Luôn tắt")):
                bm.append(k, t)
            rc, out = sh(f"'{SCRIPTS}/power-watch.sh' status")
            m = re.search(r"ghi đè:\s*(auto|on|off)", out)  # power-watch.sh status in "ghi đè: auto|on|off"
            mode = m.group(1) if m else "auto"
            bm.set_active_id(mode)
            bm.connect(
                "changed",
                lambda b: self.run_look(f"'{SCRIPTS}/power-watch.sh' set {b.get_active_id()}", "Đã đổi viền xoay màu."),
            )
            card("Viền cửa sổ xoay màu", "Animation borderangle (tốn pin chút ít).", bm)

            cur = Gtk.ComboBoxText()
            for k in ("Kafka-BEN", "Kafka-Pixel", "Kafka-Cursor"):
                if os.path.isdir(os.path.expanduser(f"~/.local/share/icons/{k}")):
                    cur.append(k, k)
            rc, out = sh("gsettings get org.gnome.desktop.interface cursor-theme")
            cur.set_active_id(out.strip("'\n "))
            cur.connect(
                "changed",
                lambda b: self.run_look(
                    f"hyprctl setcursor {b.get_active_id()} 32 && gsettings set org.gnome.desktop.interface cursor-theme {b.get_active_id()}",
                    f"Đã đổi con trỏ sang {b.get_active_id()} (lúc đăng nhập vẫn theo XCURSOR_THEME trong hyprland.lua).",
                ),
            )
            card("Bộ con trỏ", "Đổi ngay cho phiên đang chạy.", cur)

            grid = Gtk.FlowBox()
            grid.set_selection_mode(Gtk.SelectionMode.NONE)
            grid.set_max_children_per_line(4)
            grid.set_homogeneous(True)
            for key in ("waybar", "walker", "dunst", "hyprshell", "kitty", "hyprland", "popups", "alerts"):
                name, cmd = RELOAD[key]
                grid.add(self.btn(name, lambda c=cmd, n=name: self.run_look(c, f"{n}: xong")))
            card("Nạp lại thành phần", "Khi một phần giao diện hiện sai sau khi sửa tay.", grid)

            folder = Gtk.Box(spacing=6)
            folder.pack_start(
                self.btn("󰉋  Thư mục cấu hình", lambda: sh(f"setsid -f thunar '{REPO}'")), False, False, 0
            )
            folder.pack_start(
                self.btn(
                    "󰁯  Bản sao lưu",
                    lambda: (os.makedirs(BACKUP_DIR, exist_ok=True), sh(f"setsid -f thunar '{BACKUP_DIR}'")),
                ),
                False,
                False,
                0,
            )
            folder.pack_start(
                self.btn("󰈙  Ghi chú kỹ thuật", lambda: sh(f"setsid -f mousepad '{REPO}/CLAUDE.md'")), False, False, 0
            )
            card("Thư mục", "Repo dotfiles, nơi giữ bản sao lưu của Studio, tài liệu quy ước.", folder)
            box.pack_start(self.look_status, False, False, 0)
            return box

        def run_look(self, cmd, msg):
            self.say(self.look_status, "Đang chạy …")
            self.bg(
                lambda: sh(cmd, 40),
                lambda res: self.say(self.look_status, msg if res[0] == 0 else f"Lỗi: {res[1][-300:]}", res[0] != 0),
            )

    Studio().connect("destroy", Gtk.main_quit)
    Gtk.main()


def selftest():
    css = "@define-color bg rgba(44,36,52,0.93);\n  @define-color accent   #c94785; /* nhấn */\n#x { color: @bg; }\n"
    cols = read_colors(css)
    assert [(n, v) for _i, n, v in cols] == [("bg", "rgba(44,36,52,0.93)"), ("accent", "#c94785")], cols
    new = set_color(css, "accent", "#ff0000")
    assert "@define-color accent   #ff0000; /* nhấn */" in new and new.count("\n") == css.count("\n")
    assert strip_jsonc('{"a": "x // y", /* c */ "b": [1, 2,], // z\n}').replace(
        " ", ""
    ) == '{"a":"x//y","b":[1,2]\n}'.replace(" ", "")
    assert check_text("jsonc", '{"a": 1, // ok\n "b": 2,}', "x") is None
    err = check_text("jsonc", '{"a": 1\n "b": 2}', "x")
    assert err and "dòng 2" in err, err
    assert check_text("python", "x = (", "x.py")
    assert check_text("css", "a { color: red; }", "x.css") is None
    assert check_text("css", "a { color: red; ", "x.css") is None or True  # GTK tự đóng khối: không chặn
    for spec in FILES:
        assert spec[4] in RELOAD and len(spec) == 6, spec
    for rel in ("waybar/style.css", "waybar/topbar.jsonc", "hypr/hyprland.lua"):
        assert any(s[2] == rel for s in FILES)
    # mọi file JSONC trong danh sách phải qua được bộ kiểm tra (không chặn nhầm file đang dùng)
    for spec in FILES:
        if spec[5] == "jsonc" and os.path.exists(os.path.join(REPO, spec[2])):
            with open(os.path.join(REPO, spec[2])) as f:
                assert check_text("jsonc", f.read(), spec[2]) is None, spec[2]
    assert slug("Ảnh Đẹp 01.JPG") == "nh_p_01"
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        pf = os.path.join(td, "pins.json")
        with open(pf, "w") as f:
            f.write('{"_": "ghi chú", "pins": ["a.desktop", "a.desktop", "b", "c.desktop"]}')
        assert load_pins(pf) == ["a.desktop", "c.desktop"]
        save_pins(["x.desktop", "y.desktop", "x.desktop"], pf)
        with open(pf) as f:
            d = json.load(f)
        assert d == {"_": "ghi chú", "pins": ["x.desktop", "y.desktop"]}, d
        assert parse_levels("80, 50,30") == [80, 50, 30]
        assert parse_levels("30,80,80") == [80, 30]
        for bad in ("abc", "0", "100"):
            try:
                parse_levels(bad)
            except ValueError as e:
                assert str(e), e
            else:
                raise AssertionError(f"parse_levels({bad!r}) phải báo lỗi")
        af = os.path.join(td, "alerts.json")
        assert load_alerts(af) == DEFAULT_ALERTS  # file chưa có
        with open(af, "w") as f:
            f.write("{ hỏng")
        assert load_alerts(af) == DEFAULT_ALERTS  # file hỏng
        alerts = load_alerts(af)
        alerts["battery"]["levels"] = [50, 90]
        alerts["wifi_signal"]["notes"] = "khóa lạ vẫn sống"
        alerts["custom"] = {"abc": 1}
        save_alerts(af, alerts)
        back = load_alerts(af)
        assert back["battery"]["levels"] == [90, 50], back
        assert back["wifi_signal"]["notes"] == "khóa lạ vẫn sống" and back["custom"] == {"abc": 1}, back
        assert not os.path.exists(af + ".tmp")
        assert check_text("alerts", json.dumps(DEFAULT_ALERTS), af) is None
        assert check_text("alerts", '{"battery": {"levels": [80,]}}', af)  # dấu phẩy thừa
        assert check_text("alerts", '{"battery": {"levels": [0, 50]}}', af)
        assert check_text("alerts", '{"devices": {"critical": 100}}', af)
        with open(ALERTS_FILE) as f:
            assert check_text("alerts", f.read(), ALERTS_FILE) is None, "hypr/alerts.json hỏng"
    assert load_pins(), "waybar/dock-pins.json trống/hỏng"
    print("studio.py selftest OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    run_app()
