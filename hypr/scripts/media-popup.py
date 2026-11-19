#!/usr/bin/env python3
"""media-popup.py — Popup "Đang phát" (Now Playing) phong cách Kafka cho Waybar/Hyprland.

Mở khi bấm ô nhạc (mpris) trên thanh trên. Hiển thị ảnh bìa, thông tin bài hát,
thanh tiến độ kéo thả, nút điều khiển, sóng nhạc cava kiểu gương đối xứng và lời bài hát
đồng bộ thời gian thực (qua lyrics_lrclib).

Cách dùng:
  media-popup.py              Bật/tắt popup (chạy lại khi đang mở = đóng)
  media-popup.py --x <tâm_x>  Mở popup canh tâm ngang tại toạ độ màn hình <tâm_x>
  media-popup.py --close      Đóng popup nếu đang mở
  media-popup.py --selftest   Kiểm tra các hàm thuần không cần màn hình / GTK (in PASS/FAIL)
"""

import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
try:
    import lyrics_lrclib
except Exception:
    lyrics_lrclib = None

# Hằng số giao diện & cấu hình
NAMESPACE = "kafka-media-popup"
PANEL_W = 560
POP_TOP = 48
SCREEN_MARGIN = 12
DOCK_W = 48
ART_SIZE = 96
ART_RADIUS = 12
CAVA_HEIGHT = 90
CAVA_BARS = 48
CAVA_FPS = 60
ASCII_MAX = 1000
LYRICS_HEIGHT = 260

RUNDIR = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
PIDFILE = os.path.join(RUNDIR, "kafka-media-popup.pid")

CACHE_BASE = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
ART_CACHE_DIR = os.path.join(CACHE_BASE, "kafka", "art")

# Glyph Nerd Font (FiraCode Nerd Font Propo)
G_PREV = "\U000f04ae"   # 󰒮
G_PLAY = "\U000f040a"   # 󰐊
G_PAUSE = "\U000f03e4"  # 󰏤
G_NEXT = "\U000f04ad"   # 󰒭
G_MUSIC = "\U000f0387"  # 󰎇

CSS = """
/* Đồng bộ bảng màu phẳng Waybar Kafka */
* {
    font-family: "FiraCode Nerd Font", sans-serif;
    color: #fbf7fd;
    font-size: 11pt;
    font-weight: 600;
}
window {
    background-color: transparent;
}
.panel {
    background-color: rgba(44, 36, 52, 0.96);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 16px;
    padding: 16px;
}
.song-title {
    font-size: 15pt;
    font-weight: 800;
    color: #fbf7fd;
}
.song-artist {
    font-size: 11.5pt;
    font-weight: 600;
    color: #d4cade;
}
.song-player {
    font-size: 9.5pt;
    font-weight: 600;
    color: #a091b1;
}
.empty-title {
    font-size: 13pt;
    font-weight: 700;
    color: #d4cade;
}
.time-lbl {
    font-size: 9.5pt;
    font-weight: 600;
    color: #d4cade;
}
button.ctrl-btn {
    font-family: "FiraCode Nerd Font Propo";
    font-size: 18pt;
    color: #fbf7fd;
    background-image: none;
    background-color: rgba(255, 255, 255, 0.08);
    border: none;
    border-radius: 999px;
    min-width: 42px;
    min-height: 42px;
    padding: 0;
    box-shadow: none;
    transition: background-color 120ms ease, box-shadow 120ms ease;
}
button.ctrl-btn:hover {
    background-color: rgba(255, 255, 255, 0.17);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.22);
}
button.play-btn {
    font-family: "FiraCode Nerd Font Propo";
    font-size: 22pt;
    color: #fbf7fd;
    background-image: none;
    background-color: #c94785;
    border: none;
    border-radius: 999px;
    min-width: 54px;
    min-height: 54px;
    padding: 0;
    box-shadow: none;
    transition: background-color 120ms ease, box-shadow 120ms ease;
}
button.play-btn:hover {
    background-color: #e0559a;
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.25);
}
scale {
    padding: 4px 0;
}
scale trough {
    min-height: 6px;
    background-color: rgba(255, 255, 255, 0.14);
    border: none;
    border-radius: 4px;
}
scale highlight {
    min-height: 6px;
    background-color: #e0559a;
    background-image: none;
    border: none;
    border-radius: 4px;
}
scale slider {
    min-width: 14px;
    min-height: 14px;
    margin: -4px;
    border-radius: 50%;
    background-color: #fbf7fd;
    background-image: none;
    border: none;
    box-shadow: none;
}
scale slider:hover {
    background-color: #ffffff;
}
scrolledwindow, viewport {
    background-color: transparent;
    border: none;
}
scrollbar {
    opacity: 0;
    min-width: 0;
    min-height: 0;
}
.lyrics-box {
    background-color: rgba(255, 255, 255, 0.04);
    border-radius: 12px;
    padding: 8px 12px;
}
.lyric-line {
    font-size: 12pt;
    font-weight: 600;
    color: #a091b1;
    padding: 4px 6px;
}
.lyric-line.active {
    font-size: 14pt;
    font-weight: 800;
    color: #fbf7fd;
}
.lyric-plain {
    font-size: 12pt;
    font-weight: 600;
    color: #d4cade;
    padding: 6px;
}
.lyric-status {
    font-size: 12pt;
    font-weight: 600;
    color: #a091b1;
    padding: 16px;
}
button.lyric-btn {
    background-image: none;
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 2px 4px;
    box-shadow: none;
    transition: background-color 120ms ease;
}
button.lyric-btn:hover {
    background-color: rgba(255, 255, 255, 0.08);
}
"""


# ==============================================================================
# Các hàm thuần (Pure Functions) — Kiểm thử qua --selftest
# ==============================================================================

def fmt_time(sec):
    """Định dạng số giây thành chuỗi 'm:ss' hoặc 'h:mm:ss' (ví dụ: '0:00', '3:07', '1:02:03')."""
    if sec is None:
        return "0:00"
    try:
        val = float(sec)
        if math.isnan(val) or math.isinf(val) or val < 0:
            total = 0
        else:
            total = int(val)
    except (ValueError, TypeError):
        total = 0
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def parse_metadata_line(line):
    """Phân tích dòng tab-separated từ playerctl metadata.

    Định dạng: '{{playerName}}\\t{{title}}\\t{{artist}}\\t{{album}}\\t{{mpris:length}}\\t{{mpris:artUrl}}\\t{{status}}'
    - length từ micro-giây (µs) đổi sang giây (float).
    - Thiếu trường hoặc dữ liệu lỗi không văng ngoại lệ.
    """
    if not isinstance(line, str):
        line = ""
    line = line.rstrip("\r\n")
    parts = line.split("\t") if line else []

    def get_part(idx):
        return parts[idx].strip() if idx < len(parts) else ""

    player = get_part(0)
    title = get_part(1)
    artist = get_part(2)
    album = get_part(3)
    raw_len = get_part(4)
    art_url = get_part(5)
    status = get_part(6)

    length_sec = 0.0
    if raw_len:
        try:
            us = float(raw_len)
            if us > 0 and not math.isnan(us) and not math.isinf(us):
                length_sec = us / 1_000_000.0
        except (ValueError, TypeError):
            length_sec = 0.0

    return {
        "player": player,
        "playerName": player,
        "title": title,
        "artist": artist,
        "album": album,
        "length": length_sec,
        "artUrl": art_url,
        "art_url": art_url,
        "status": status,
    }


def parse_frame(line):
    """Phân tích một dòng stdout từ cava thành danh sách số nguyên 0..1000.

    Chuỗi hợp lệ dạng "1;500;1000;" -> [1, 500, 1000].
    Trả về None nếu dòng rỗng hoặc chứa dữ liệu hỏng.
    """
    if not isinstance(line, str):
        return None
    s = line.strip()
    if not s:
        return None
    if s.endswith(";"):
        s = s[:-1]
    if not s:
        return None
    parts = s.split(";")
    values = []
    for p in parts:
        if not p:
            return None
        try:
            v = int(p)
        except ValueError:
            return None
        if v < 0:
            v = 0
        elif v > ASCII_MAX:
            v = ASCII_MAX
        values.append(v)
    return values if values else None


def clamp_x(center, width, screen_w, margin=SCREEN_MARGIN, dock_w=DOCK_W):
    """Tính toạ độ x (mép trái khung) sao cho tâm tại `center` và nằm gọn trong màn hình.

    Giữ khoảng cách lề trái `margin` (12px) và chừa dock phải `dock_w` (48px) + lề `margin` (12px).
    """
    try:
        c = float(center)
        w = int(width)
        sw = int(screen_w)
    except (ValueError, TypeError):
        return margin
    left = int(round(c - w / 2.0))
    lo = int(margin)
    hi = max(lo, sw - w - int(dock_w) - int(margin))
    return max(lo, min(left, hi))


def build_cava_config(bars=CAVA_BARS, framerate=CAVA_FPS):
    """Sinh nội dung file cấu hình tạm cho tiến trình cava."""
    return (
        "[general]\n"
        f"bars = {int(bars)}\n"
        f"framerate = {int(framerate)}\n"
        "sleep_timer = 3\n"
        "\n"
        "[input]\n"
        "method = pulse\n"
        "\n"
        "[output]\n"
        "method = raw\n"
        "raw_target = /dev/stdout\n"
        "data_format = ascii\n"
        f"ascii_max_range = {ASCII_MAX}\n"
        "bar_delimiter = 59\n"
        "frame_delimiter = 10\n"
    )


def normalize_lyrics_result(res):
    """Chuẩn hoá kết quả trả về từ lyrics_lrclib.fetch_lyrics thành (kind, payload).

    kind có thể là:
      - 'instrumental': nhạc không lời
      - 'synced': danh sách [(sec, text), ...]
      - 'plain': chuỗi lời bài hát không có thời gian
      - 'none': không tìm thấy lời
    """
    if res is None:
        return ("none", None)

    if isinstance(res, dict):
        if res.get("instrumental"):
            return ("instrumental", None)
        synced = res.get("synced") or res.get("lines") or res.get("syncedLyrics")
        if isinstance(synced, list) and synced:
            return ("synced", synced)
        plain = res.get("plain") or res.get("plainLyrics") or res.get("lyrics") or res.get("text")
        if isinstance(plain, str) and plain.strip():
            return ("plain", plain.strip())
        return ("none", None)

    if isinstance(res, tuple):
        if len(res) == 2:
            a, b = res
            if isinstance(a, str) and a.lower() in ("instrumental", "synced", "plain", "none", "empty", "not_found"):
                k = a.lower()
                if k == "instrumental":
                    return ("instrumental", None)
                if k == "synced" and isinstance(b, list) and b:
                    return ("synced", b)
                if k == "plain" and isinstance(b, str) and b.strip():
                    return ("plain", b.strip())
                return ("none", None)
            if isinstance(a, bool) and a and not b:
                return ("instrumental", None)
            if isinstance(a, list) and a:
                return ("synced", a)
            if isinstance(b, list) and b:
                return ("synced", b)
            if isinstance(a, str) and a.strip():
                return ("plain", a.strip())
            if isinstance(b, str) and b.strip():
                return ("plain", b.strip())
        elif len(res) >= 3:
            for item in res:
                if isinstance(item, bool) and item:
                    return ("instrumental", None)
                if isinstance(item, list) and item:
                    return ("synced", item)
                if isinstance(item, str) and item.strip() and item not in ("synced", "plain", "none"):
                    return ("plain", item.strip())
        return ("none", None)

    if isinstance(res, list):
        return ("synced", res) if res else ("none", None)

    if isinstance(res, str):
        s = res.strip()
        if not s:
            return ("none", None)
        if s.lower() == "instrumental":
            return ("instrumental", None)
        return ("plain", s)

    # Đối tượng tuỳ chỉnh (dataclass / SimpleNamespace / class)
    if getattr(res, "instrumental", False):
        return ("instrumental", None)
    synced = getattr(res, "synced", None) or getattr(res, "lines", None)
    if isinstance(synced, list) and synced:
        return ("synced", synced)
    plain = getattr(res, "plain", None) or getattr(res, "text", None)
    if isinstance(plain, str) and plain.strip():
        return ("plain", plain.strip())

    return ("none", None)


def fallback_line_index_at(lines, t):
    """Dự phòng tìm chỉ số dòng lời tại thời điểm t (giây) nếu lyrics_lrclib.line_index_at thiếu."""
    if not lines:
        return -1
    if lyrics_lrclib is not None and hasattr(lyrics_lrclib, "line_index_at"):
        try:
            idx = lyrics_lrclib.line_index_at(lines, t)
            if idx is not None and isinstance(idx, int):
                return idx
        except Exception:
            pass
    idx = -1
    for i, item in enumerate(lines):
        try:
            sec = float(item[0])
        except (IndexError, TypeError, ValueError):
            continue
        if sec <= t:
            idx = i
        else:
            break
    return idx


# ==============================================================================
# Quản lý PID (Single Instance)
# ==============================================================================

def running_pid():
    """Trả về PID nếu media-popup.py đang chạy, ngược lại None."""
    try:
        with open(PIDFILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read()
        if b"media-popup" not in cmd and b"python" not in cmd:
            return None
        return pid
    except (OSError, ValueError):
        return None


def write_pidfile():
    try:
        with open(PIDFILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def remove_pidfile():
    try:
        if os.path.exists(PIDFILE):
            with open(PIDFILE, "r", encoding="utf-8") as f:
                if f.read().strip() == str(os.getpid()):
                    os.unlink(PIDFILE)
    except OSError:
        pass


# ==============================================================================
# Kiểm thử tự động (--selftest)
# ==============================================================================

def run_selftest():
    """Kiểm tra các hàm thuần không cần màn hình và không import Gtk."""
    try:
        # 1. Kiểm tra fmt_time
        assert fmt_time(0) == "0:00", f"fmt_time(0) = {fmt_time(0)}"
        assert fmt_time(187) == "3:07", f"fmt_time(187) = {fmt_time(187)}"
        assert fmt_time(3723) == "1:02:03", f"fmt_time(3723) = {fmt_time(3723)}"
        assert fmt_time(-5) == "0:00", "fmt_time(-5) phải về 0:00"
        assert fmt_time(None) == "0:00", "fmt_time(None) phải về 0:00"

        # 2. Kiểm tra parse_metadata_line
        line = "spotify\tKafka Theme\tHOYO-MiX\tHonkai: Star Rail\t187500000\thttps://example.com/art.jpg\tPlaying"
        meta = parse_metadata_line(line)
        assert meta["player"] == "spotify", f"Sai player: {meta}"
        assert meta["title"] == "Kafka Theme", f"Sai title: {meta}"
        assert meta["artist"] == "HOYO-MiX", f"Sai artist: {meta}"
        assert meta["album"] == "Honkai: Star Rail", f"Sai album: {meta}"
        assert abs(meta["length"] - 187.5) < 1e-6, f"Sai length: {meta['length']}"
        assert meta["artUrl"] == "https://example.com/art.jpg", f"Sai artUrl: {meta}"
        assert meta["status"] == "Playing", f"Sai status: {meta}"

        # Thiếu trường không lỗi
        short_meta = parse_metadata_line("mpv\tOnly Title")
        assert short_meta["player"] == "mpv"
        assert short_meta["title"] == "Only Title"
        assert short_meta["artist"] == ""
        assert short_meta["length"] == 0.0
        assert short_meta["status"] == ""

        empty_meta = parse_metadata_line("")
        assert empty_meta["title"] == "" and empty_meta["length"] == 0.0

        bad_len_meta = parse_metadata_line("vlc\tSong\tArtist\tAlbum\tnot_a_number\t\tPaused")
        assert bad_len_meta["length"] == 0.0 and bad_len_meta["status"] == "Paused"

        # 3. Kiểm tra parse_frame
        assert parse_frame("1;500;1000;") == [1, 500, 1000], "parse_frame chuẩn thất bại"
        assert parse_frame("0;250;1000\n") == [0, 250, 1000], "parse_frame không dấu ';' cuối thất bại"
        assert parse_frame("") is None, "parse_frame chuỗi rỗng phải trả về None"
        assert parse_frame("   \n") is None, "parse_frame khoảng trắng phải trả về None"
        assert parse_frame("1;abc;3;") is None, "parse_frame chữ cái phải trả về None"
        assert parse_frame("1;;3;") is None, "parse_frame phần tử rỗng phải trả về None"

        # 4. Kiểm tra clamp_x
        # Màn 1920, khung 560, lề 12, dock 48 -> min = 12, max = 1920 - 560 - 48 - 12 = 1300
        assert clamp_x(960, 560, 1920) == 680, f"clamp_x giữa màn sai: {clamp_x(960, 560, 1920)}"
        assert clamp_x(100, 560, 1920) == 12, f"clamp_x sát trái sai: {clamp_x(100, 560, 1920)}"
        assert clamp_x(1850, 560, 1920) == 1300, f"clamp_x sát phải sai: {clamp_x(1850, 560, 1920)}"

        print("PASS")
        return 0
    except AssertionError as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:
        print(f"FAIL: {e}")
        return 1


# ==============================================================================
# Giao diện GTK3 + GtkLayerShell
# ==============================================================================

def run_app(arg_x=None):
    import cairo
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, GtkLayerShell, Pango

    class MediaPopup(Gtk.Window):
        def __init__(self, target_x=None):
            super().__init__(title=NAMESPACE)
            self.target_x = target_x
            self._quitting = False

            # Trạng thái trình phát & thời gian
            self.meta = {}
            self.meta_sig = None
            self.has_player = False
            self.is_playing = False
            self.duration = 0.0
            self.base_pos = 0.0
            self.base_mono = time.monotonic()
            self.dragging_scale = False
            self._meta_busy = False
            self._pos_busy = False

            # Ảnh bìa
            self.art_pixbuf = None
            self.current_art_url = ""
            self._art_req_id = 0

            # Cava visualizer (48 cột, gương đối xứng, chấm đỉnh rơi chậm)
            self.bars = [0.0] * CAVA_BARS
            self.peaks = [0.0] * CAVA_BARS
            self.cava_proc = None
            self.cava_cfg_path = None
            self.cava_watch_id = None
            self._cava_rx_buf = b""

            # Lời bài hát
            self.song_key = None
            self._lyrics_req_id = 0
            self.lyric_lines = []      # [(sec, text), ...]
            self.lyric_widgets = []    # [Gtk.Label, ...]
            self.lyric_buttons = []    # [Gtk.Button, ...]
            self.active_lyric_idx = -1
            self._scroll_anim_id = None
            self._scroll_start = 0.0
            self._scroll_target = 0.0
            self._scroll_t0 = 0.0

            self._init_window()
            self._build_ui()
            self._place_panel()

            self.connect("map-event", self._on_map)
            self.connect("unmap-event", self._on_unmap)

            # Tải dữ liệu ngay khi mở và đặt bộ đếm định kỳ
            self._poll_metadata()
            self._poll_position()
            self._timer_1s = GLib.timeout_add(1000, self._on_tick_1s)
            self._timer_100ms = GLib.timeout_add(100, self._on_tick_100ms)

        # ---------- Cửa sổ & Layer Shell ----------
        def _init_window(self):
            prov = Gtk.CssProvider()
            prov.load_from_data(CSS.encode("utf-8"))
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                prov,
                Gtk.STYLE_PROVIDER_PRIORITY_USER + 1,
            )

            self.set_app_paintable(True)
            vis = self.get_screen().get_rgba_visual()
            if vis is not None:
                self.set_visual(vis)

            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_namespace(self, NAMESPACE)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            for edge in (
                GtkLayerShell.Edge.TOP,
                GtkLayerShell.Edge.BOTTOM,
                GtkLayerShell.Edge.LEFT,
                GtkLayerShell.Edge.RIGHT,
            ):
                GtkLayerShell.set_anchor(self, edge, True)
            GtkLayerShell.set_exclusive_zone(self, -1)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)

            self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            self.connect("button-press-event", self._on_button_press)
            self.connect("key-press-event", self._on_key_press)
            self.connect("destroy", lambda *_: self.quit())

        def _build_ui(self):
            self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            self.panel.get_style_context().add_class("panel")
            self.panel.set_halign(Gtk.Align.START)
            self.panel.set_valign(Gtk.Align.START)
            self.panel.set_margin_top(POP_TOP)
            self.panel.set_size_request(PANEL_W, -1)
            self.add(self.panel)

            # 1. Hàng đầu: Ảnh bìa 96x96 bo 12px + Thông tin bài hát
            top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            self.art_area = Gtk.DrawingArea()
            self.art_area.set_size_request(ART_SIZE, ART_SIZE)
            self.art_area.set_valign(Gtk.Align.CENTER)
            self.art_area.connect("draw", self._draw_art)
            top_row.pack_start(self.art_area, False, False, 0)

            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            info_box.set_valign(Gtk.Align.CENTER)

            self.title_lbl = Gtk.Label(label="Không có nhạc đang phát", xalign=0.0)
            self.title_lbl.get_style_context().add_class("song-title")
            self.title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            self.title_lbl.set_max_width_chars(28)
            self.title_lbl.set_hexpand(True)

            self.artist_lbl = Gtk.Label(label="", xalign=0.0)
            self.artist_lbl.get_style_context().add_class("song-artist")
            self.artist_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            self.artist_lbl.set_max_width_chars(34)
            self.artist_lbl.set_hexpand(True)

            self.player_lbl = Gtk.Label(label="", xalign=0.0)
            self.player_lbl.get_style_context().add_class("song-player")
            self.player_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            self.player_lbl.set_max_width_chars(34)

            info_box.pack_start(self.title_lbl, False, False, 0)
            info_box.pack_start(self.artist_lbl, False, False, 0)
            info_box.pack_start(self.player_lbl, False, False, 0)
            top_row.pack_start(info_box, True, True, 0)
            self.panel.pack_start(top_row, False, False, 0)

            # 2. Thanh tiến độ (Gtk.Scale) + thời gian hiện tại / tổng
            prog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 100.0, 1.0)
            self.scale.set_draw_value(False)
            self.scale.set_hexpand(True)
            self.scale.connect("button-press-event", self._on_scale_press)
            self.scale.connect("button-release-event", self._on_scale_release)
            self.scale.connect("value-changed", self._on_scale_changed)
            prog_box.pack_start(self.scale, False, False, 0)

            time_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            self.pos_lbl = Gtk.Label(label="0:00", xalign=0.0)
            self.pos_lbl.get_style_context().add_class("time-lbl")
            self.len_lbl = Gtk.Label(label="0:00", xalign=1.0)
            self.len_lbl.get_style_context().add_class("time-lbl")
            time_row.pack_start(self.pos_lbl, False, False, 0)
            time_row.pack_end(self.len_lbl, False, False, 0)
            prog_box.pack_start(time_row, False, False, 0)
            self.panel.pack_start(prog_box, False, False, 0)

            # 3. Nút điều khiển: trước · phát/dừng · sau
            ctrl_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=22)
            ctrl_row.set_halign(Gtk.Align.CENTER)

            self.prev_btn = Gtk.Button(label=G_PREV)
            self.prev_btn.get_style_context().add_class("ctrl-btn")
            self.prev_btn.set_valign(Gtk.Align.CENTER)
            self.prev_btn.connect("clicked", lambda *_: self._playerctl("previous"))

            self.play_btn = Gtk.Button(label=G_PLAY)
            self.play_btn.get_style_context().add_class("play-btn")
            self.play_btn.set_valign(Gtk.Align.CENTER)
            self.play_btn.connect("clicked", lambda *_: self._playerctl("play-pause"))

            self.next_btn = Gtk.Button(label=G_NEXT)
            self.next_btn.get_style_context().add_class("ctrl-btn")
            self.next_btn.set_valign(Gtk.Align.CENTER)
            self.next_btn.connect("clicked", lambda *_: self._playerctl("next"))

            ctrl_row.pack_start(self.prev_btn, False, False, 0)
            ctrl_row.pack_start(self.play_btn, False, False, 0)
            ctrl_row.pack_start(self.next_btn, False, False, 0)
            self.panel.pack_start(ctrl_row, False, False, 0)

            # 4. Vùng sóng nhạc cao 90px (Gtk.DrawingArea)
            self.cava_area = Gtk.DrawingArea()
            self.cava_area.set_size_request(-1, CAVA_HEIGHT)
            self.cava_area.set_hexpand(True)
            self.cava_area.connect("draw", self._draw_cava)
            self.panel.pack_start(self.cava_area, False, False, 0)

            # 5. Lời bài hát (Gtk.ScrolledWindow cao 260px, ẩn thanh cuộn)
            self.lyrics_sw = Gtk.ScrolledWindow()
            self.lyrics_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
            self.lyrics_sw.set_size_request(-1, LYRICS_HEIGHT)
            self.lyrics_sw.set_min_content_height(LYRICS_HEIGHT)
            self.lyrics_sw.set_max_content_height(LYRICS_HEIGHT)
            self.lyrics_sw.get_style_context().add_class("lyrics-box")

            self.lyrics_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            self.lyrics_box.set_valign(Gtk.Align.START)
            self.lyrics_sw.add(self.lyrics_box)
            self.panel.pack_start(self.lyrics_sw, False, False, 0)

            self._set_lyrics_message("Không có nhạc đang phát")

        def _place_panel(self):
            """Đặt vị trí ngang của khung theo --x hoặc hyprctl cursorpos."""
            cx = self.target_x
            mon_x = 0
            screen_w = 1920
            try:
                disp = Gdk.Display.get_default()
                if cx is None:
                    out = subprocess.run(
                        ["hyprctl", "cursorpos", "-j"],
                        capture_output=True,
                        text=True,
                        timeout=0.8,
                    ).stdout
                    cx = float(json.loads(out)["x"])
                if disp is not None:
                    mon = disp.get_monitor_at_point(int(cx), POP_TOP)
                    if mon is not None:
                        geom = mon.get_geometry()
                        mon_x = geom.x
                        screen_w = geom.width
            except Exception:
                if disp is not None and disp.get_n_monitors() > 0:
                    geom = disp.get_monitor(0).get_geometry()
                    mon_x = geom.x
                    screen_w = geom.width
                if cx is None:
                    cx = mon_x + screen_w / 2.0

            local_center = float(cx) - mon_x
            left = clamp_x(local_center, PANEL_W, screen_w, SCREEN_MARGIN, DOCK_W)
            self.panel.set_margin_start(left)

        # ---------- Chạy lệnh nền ----------
        def _bg(self, fn, *args, done=None):
            def worker():
                try:
                    res = fn(*args)
                except Exception:
                    res = None
                if done is not None and not self._quitting:
                    GLib.idle_add(lambda: (done(res) if not self._quitting else None, False)[1])

            threading.Thread(target=worker, daemon=True).start()

        def _playerctl(self, *cmd_args):
            def run_cmd():
                try:
                    subprocess.run(
                        ["playerctl", *cmd_args],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=1.5,
                    )
                except Exception:
                    pass

            def after(_):
                self._poll_metadata()
                self._poll_position()

            self._bg(run_cmd, done=after)

        # ---------- Cập nhật Metadata & Thời gian phát ----------
        def _on_tick_1s(self):
            if self._quitting:
                return False
            self._poll_metadata()
            self._poll_position()
            return True

        def _on_tick_100ms(self):
            if self._quitting:
                return False
            if self.has_player:
                pos = self._current_position()
                if not self.dragging_scale:
                    self.pos_lbl.set_text(fmt_time(pos))
                    if self.duration > 0:
                        self.scale.set_value(min(self.duration, max(0.0, pos)))
                self._update_active_lyric(pos)
            return True

        def _current_position(self):
            if not self.has_player:
                return 0.0
            pos = self.base_pos
            if self.is_playing:
                pos += max(0.0, time.monotonic() - self.base_mono)
            if self.duration > 0:
                pos = min(pos, self.duration)
            return max(0.0, pos)

        def _poll_position(self):
            if self._pos_busy:
                return
            self._pos_busy = True

            def fetch_pos():
                try:
                    r = subprocess.run(
                        ["playerctl", "position"],
                        capture_output=True,
                        text=True,
                        timeout=0.8,
                    )
                    if r.returncode == 0 and r.stdout.strip():
                        return float(r.stdout.strip())
                except Exception:
                    pass
                return None

            def on_pos(val):
                self._pos_busy = False
                if val is not None and not math.isnan(val) and not math.isinf(val):
                    self.base_pos = max(0.0, val)
                    self.base_mono = time.monotonic()
                    if not self.dragging_scale:
                        self.pos_lbl.set_text(fmt_time(self.base_pos))
                        if self.duration > 0:
                            self.scale.set_value(min(self.duration, self.base_pos))
                    self._update_active_lyric(self.base_pos)

            self._bg(fetch_pos, done=on_pos)

        def _poll_metadata(self):
            if self._meta_busy:
                return
            self._meta_busy = True
            fmt = "{{playerName}}\t{{title}}\t{{artist}}\t{{album}}\t{{mpris:length}}\t{{mpris:artUrl}}\t{{status}}"

            def fetch_meta():
                try:
                    r = subprocess.run(
                        ["playerctl", "metadata", "--format", fmt],
                        capture_output=True,
                        text=True,
                        timeout=0.8,
                    )
                    if r.returncode == 0:
                        line = r.stdout.splitlines()[0] if r.stdout else ""
                        if line.strip():
                            return parse_metadata_line(line)
                except Exception:
                    pass
                return None

            def on_meta(data):
                self._meta_busy = False
                self._apply_metadata(data)

            self._bg(fetch_meta, done=on_meta)

        def _apply_metadata(self, data):
            if not data or (not data.get("player") and not data.get("title") and not data.get("status")):
                sig = "NO_PLAYER"
                if sig == self.meta_sig:
                    return
                self.meta_sig = sig
                self.meta = {}
                self.has_player = False
                self.is_playing = False
                self.duration = 0.0
                self.base_pos = 0.0
                self.song_key = None

                self.title_lbl.set_text("Không có nhạc đang phát")
                self.artist_lbl.set_text("")
                self.player_lbl.set_text("")
                self.play_btn.set_label(G_PLAY)
                self.pos_lbl.set_text("0:00")
                self.len_lbl.set_text("0:00")
                self.scale.set_range(0.0, 100.0)
                self.scale.set_value(0.0)
                self.scale.set_sensitive(False)
                self.art_pixbuf = None
                self.current_art_url = ""
                self.art_area.queue_draw()
                self._set_lyrics_message("Không có nhạc đang phát")
                return

            sig = json.dumps(data, sort_keys=True)
            if sig == self.meta_sig:
                return
            self.meta_sig = sig
            self.meta = data
            self.has_player = True

            status = data.get("status", "")
            self.is_playing = status.lower() == "playing"
            self.base_mono = time.monotonic()

            title = data.get("title") or "Không rõ tên bài"
            artist = data.get("artist") or ""
            album = data.get("album") or ""
            player = data.get("player") or ""
            length = data.get("length", 0.0)

            self.title_lbl.set_text(title)
            self.artist_lbl.set_text(artist)
            self.player_lbl.set_text(player)
            self.play_btn.set_label(G_PAUSE if self.is_playing else G_PLAY)

            self.duration = max(0.0, float(length))
            self.len_lbl.set_text(fmt_time(self.duration))
            if self.duration > 0:
                self.scale.set_range(0.0, self.duration)
                self.scale.set_sensitive(True)
                if not self.dragging_scale:
                    self.scale.set_value(min(self.duration, self.base_pos))
            else:
                self.scale.set_range(0.0, 100.0)
                self.scale.set_value(0.0)
                self.scale.set_sensitive(False)

            # Ảnh bìa
            art_url = data.get("artUrl") or ""
            if art_url != self.current_art_url:
                self.current_art_url = art_url
                self._load_art(art_url)

            # Lời bài hát khi đổi bài
            new_song_key = (data.get("title", ""), artist, album, round(self.duration))
            if new_song_key != self.song_key:
                self.song_key = new_song_key
                self._fetch_lyrics(data.get("title", ""), artist, album, self.duration)

        # ---------- Thanh tiến độ kéo thả ----------
        def _on_scale_press(self, _widget, _event):
            self.dragging_scale = True
            return False

        def _on_scale_changed(self, scale):
            if self.dragging_scale:
                self.pos_lbl.set_text(fmt_time(scale.get_value()))

        def _on_scale_release(self, scale, _event):
            if self.dragging_scale:
                target_sec = max(0.0, float(scale.get_value()))
                self.dragging_scale = False
                self.base_pos = target_sec
                self.base_mono = time.monotonic()
                self.pos_lbl.set_text(fmt_time(target_sec))
                self._update_active_lyric(target_sec)
                self._seek_to(target_sec)
            return False

        def _seek_to(self, sec):
            sec_val = max(0.0, float(sec))
            self.base_pos = sec_val
            self.base_mono = time.monotonic()
            if not self.dragging_scale:
                self.pos_lbl.set_text(fmt_time(sec_val))
                if self.duration > 0:
                    self.scale.set_value(min(self.duration, sec_val))
            self._update_active_lyric(sec_val)
            self._playerctl("position", f"{sec_val:.2f}")

        # ---------- Ảnh bìa 96x96 bo 12px ----------
        def _load_art(self, url):
            self._art_req_id += 1
            req_id = self._art_req_id
            if not url:
                self.art_pixbuf = None
                self.art_area.queue_draw()
                return

            def worker():
                local_path = None
                if url.startswith("file://"):
                    parsed = urllib.parse.urlparse(url)
                    local_path = urllib.parse.unquote(parsed.path)
                elif url.startswith("http://") or url.startswith("https://"):
                    os.makedirs(ART_CACHE_DIR, exist_ok=True)
                    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
                    cached = os.path.join(ART_CACHE_DIR, f"{digest}.img")
                    if not os.path.exists(cached):
                        try:
                            req = urllib.request.Request(
                                url,
                                headers={"User-Agent": "KafkaMediaPopup/1.0"},
                            )
                            with urllib.request.urlopen(req, timeout=5) as resp:
                                data = resp.read()
                            tmp_path = f"{cached}.tmp.{os.getpid()}"
                            with open(tmp_path, "wb") as f:
                                f.write(data)
                            os.replace(tmp_path, cached)
                        except Exception:
                            return None
                    local_path = cached
                elif os.path.isabs(url) and os.path.exists(url):
                    local_path = url

                if not local_path or not os.path.exists(local_path):
                    return None
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file(local_path)
                    w, h = pb.get_width(), pb.get_height()
                    if w <= 0 or h <= 0:
                        return None
                    # Cắt vuông ở tâm rồi co về ART_SIZE x ART_SIZE
                    side = min(w, h)
                    ox = (w - side) // 2
                    oy = (h - side) // 2
                    sub = pb.new_subpixbuf(ox, oy, side, side)
                    return sub.scale_simple(ART_SIZE, ART_SIZE, GdkPixbuf.InterpType.BILINEAR)
                except Exception:
                    return None

            def done(pixbuf):
                if req_id != self._art_req_id:
                    return
                self.art_pixbuf = pixbuf
                self.art_area.queue_draw()

            self._bg(worker, done=done)

        def _draw_art(self, _widget, ctx):
            r = float(ART_RADIUS)
            s = float(ART_SIZE)

            # Đường cắt bo góc 12px
            ctx.new_sub_path()
            ctx.arc(s - r, r, r, -math.pi / 2, 0)
            ctx.arc(s - r, s - r, r, 0, math.pi / 2)
            ctx.arc(r, s - r, r, math.pi / 2, math.pi)
            ctx.arc(r, r, r, math.pi, 3 * math.pi / 2)
            ctx.close_path()

            ctx.save()
            ctx.clip()
            if self.art_pixbuf is not None:
                Gdk.cairo_set_source_pixbuf(ctx, self.art_pixbuf, 0, 0)
                ctx.paint()
            else:
                # Nền mặc định khi chưa có ảnh bìa
                grad = cairo.LinearGradient(0, 0, s, s)
                grad.add_color_stop_rgba(0.0, 0xC9 / 255.0, 0x47 / 255.0, 0x85 / 255.0, 0.32)
                grad.add_color_stop_rgba(1.0, 0x38 / 255.0, 0x2B / 255.0, 0x47 / 255.0, 0.55)
                ctx.set_source(grad)
                ctx.paint()

                # Vẽ nốt nhạc ở giữa
                ctx.select_font_face("FiraCode Nerd Font Propo", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                ctx.set_font_size(34)
                ext = ctx.text_extents(G_MUSIC)
                tx = (s - ext.width) / 2.0 - ext.x_bearing
                ty = (s - ext.height) / 2.0 - ext.y_bearing
                ctx.set_source_rgba(0xFB / 255.0, 0xF7 / 255.0, 0xFD / 255.0, 0.65)
                ctx.move_to(tx, ty)
                ctx.show_text(G_MUSIC)
            ctx.restore()

            # Viền mảnh quanh ảnh bìa
            ctx.new_sub_path()
            ctx.arc(s - r, r, r, -math.pi / 2, 0)
            ctx.arc(s - r, s - r, r, 0, math.pi / 2)
            ctx.arc(r, s - r, r, math.pi / 2, math.pi)
            ctx.arc(r, r, r, math.pi, 3 * math.pi / 2)
            ctx.close_path()
            ctx.set_source_rgba(1.0, 1.0, 1.0, 0.12)
            ctx.set_line_width(1.0)
            ctx.stroke()
            return True

        # ---------- Sóng nhạc Cava kiểu Gương (48 cột, 60fps) ----------
        def _on_map(self, *_args):
            self._start_cava()
            return False

        def _on_unmap(self, *_args):
            self._stop_cava()
            return False

        def _start_cava(self):
            if self.cava_proc is not None or self._quitting:
                return
            try:
                fd, self.cava_cfg_path = tempfile.mkstemp(prefix="kafka-media-cava-", suffix=".conf")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(build_cava_config(CAVA_BARS, CAVA_FPS))
                self.cava_proc = subprocess.Popen(
                    ["cava", "-p", self.cava_cfg_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    close_fds=True,
                )
                stdout_fd = self.cava_proc.stdout.fileno()
                os.set_blocking(stdout_fd, False)
                self.cava_watch_id = GLib.io_add_watch(
                    stdout_fd,
                    GLib.PRIORITY_DEFAULT,
                    GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR,
                    self._on_cava_io,
                )
            except OSError:
                self._stop_cava()

        def _stop_cava(self):
            if self.cava_watch_id is not None:
                try:
                    GLib.source_remove(self.cava_watch_id)
                except Exception:
                    pass
                self.cava_watch_id = None

            if self.cava_proc is not None:
                try:
                    if self.cava_proc.poll() is None:
                        self.cava_proc.terminate()
                        try:
                            self.cava_proc.wait(timeout=0.3)
                        except subprocess.TimeoutExpired:
                            self.cava_proc.kill()
                except OSError:
                    pass
                self.cava_proc = None

            if self.cava_cfg_path and os.path.exists(self.cava_cfg_path):
                try:
                    os.unlink(self.cava_cfg_path)
                except OSError:
                    pass
                self.cava_cfg_path = None
            self._cava_rx_buf = b""

        def _on_cava_io(self, fd, condition):
            if self._quitting:
                return False
            if condition & GLib.IO_IN:
                try:
                    chunk = os.read(fd, 65536)
                except BlockingIOError:
                    return True
                except OSError:
                    return False
                if not chunk:
                    return False
                self._cava_rx_buf += chunk
                if b"\n" in self._cava_rx_buf:
                    lines = self._cava_rx_buf.split(b"\n")
                    self._cava_rx_buf = lines.pop()
                    latest = None
                    for raw in lines:
                        vals = parse_frame(raw.decode("ascii", errors="ignore"))
                        if vals is not None:
                            latest = vals
                    if latest is not None:
                        self._update_cava_bars(latest)
            if condition & (GLib.IO_HUP | GLib.IO_ERR):
                return False
            return True

        def _update_cava_bars(self, vals):
            if not self.get_mapped():
                return
            n = CAVA_BARS
            if len(vals) < n:
                vals = list(vals) + [0] * (n - len(vals))
            elif len(vals) > n:
                vals = vals[:n]

            for i in range(n):
                v = float(vals[i])
                # Làm mượt cột sóng
                cur = max(v, self.bars[i] * 0.80)
                self.bars[i] = cur
                # Chấm đỉnh rơi chậm (peak hold)
                if cur >= self.peaks[i]:
                    self.peaks[i] = cur
                else:
                    self.peaks[i] = max(0.0, self.peaks[i] * 0.965 - 4.0)

            self.cava_area.queue_draw()

        @staticmethod
        def _add_capsule_path(ctx, cx, cy, half_w, half_h):
            """Tạo đường bao viên thuốc đối xứng quanh tâm (cx, cy)."""
            r = min(half_w, half_h)
            if r <= 0.2:
                return
            top_c = cy - half_h + r
            bot_c = cy + half_h - r
            ctx.new_sub_path()
            ctx.arc(cx, top_c, r, math.pi, 0.0)
            ctx.line_to(cx + half_w, bot_c)
            ctx.arc(cx, bot_c, r, 0.0, math.pi)
            ctx.close_path()

        def _draw_cava(self, widget, ctx):
            if not self.get_mapped():
                return True
            width = float(widget.get_allocated_width())
            height = float(widget.get_allocated_height())
            if width <= 0 or height <= 0:
                return True

            mid_y = height / 2.0
            max_half = max(4.0, mid_y - 6.0)
            n = len(self.bars)
            gap = 3.0
            bar_w = max(2.0, (width - gap * (n - 1)) / float(n))
            step = bar_w + gap
            half_w = bar_w / 2.0

            # Gradient ngang #e0559a -> #c77dff
            r1, g1, b1 = 0xE0 / 255.0, 0x55 / 255.0, 0x9A / 255.0
            r2, g2, b2 = 0xC7 / 255.0, 0x7D / 255.0, 0xFF / 255.0

            # Đường trục giữa mảnh
            line_grad = cairo.LinearGradient(0, 0, width, 0)
            line_grad.add_color_stop_rgba(0.0, r1, g1, b1, 0.18)
            line_grad.add_color_stop_rgba(1.0, r2, g2, b2, 0.18)
            ctx.set_source(line_grad)
            ctx.set_line_width(1.0)
            ctx.move_to(0, mid_y)
            ctx.line_to(width, mid_y)
            ctx.stroke()

            # 1. Lớp phát sáng mờ phía sau (alpha 0.25 và rộng hơn 3px)
            glow_grad = cairo.LinearGradient(0, 0, width, 0)
            glow_grad.add_color_stop_rgba(0.0, r1, g1, b1, 0.25)
            glow_grad.add_color_stop_rgba(1.0, r2, g2, b2, 0.25)
            ctx.set_source(glow_grad)

            glow_half_w = half_w + 1.5  # rộng hơn 3px tổng cộng
            for i, val in enumerate(self.bars):
                cx = i * step + half_w
                half_h = max(1.5, (min(val, float(ASCII_MAX)) / float(ASCII_MAX)) * max_half)
                self._add_capsule_path(ctx, cx, mid_y, glow_half_w, half_h + 1.5)
            ctx.fill()

            # 2. Cột sóng chính bo tròn đối xứng quanh đường giữa
            main_grad = cairo.LinearGradient(0, 0, width, 0)
            main_grad.add_color_stop_rgba(0.0, r1, g1, b1, 0.95)
            main_grad.add_color_stop_rgba(1.0, r2, g2, b2, 0.95)
            ctx.set_source(main_grad)

            for i, val in enumerate(self.bars):
                cx = i * step + half_w
                half_h = max(1.5, (min(val, float(ASCII_MAX)) / float(ASCII_MAX)) * max_half)
                self._add_capsule_path(ctx, cx, mid_y, half_w, half_h)
            ctx.fill()

            # 3. Chấm đỉnh rơi chậm (peak hold) đối xứng trên và dưới
            peak_grad = cairo.LinearGradient(0, 0, width, 0)
            peak_grad.add_color_stop_rgba(0.0, 0xFB / 255.0, 0xF7 / 255.0, 0xFD / 255.0, 0.90)
            peak_grad.add_color_stop_rgba(1.0, r2, g2, b2, 0.95)
            ctx.set_source(peak_grad)

            dot_r = max(1.2, min(2.2, half_w * 0.75))
            for i, pval in enumerate(self.peaks):
                if pval <= 15.0:
                    continue
                cx = i * step + half_w
                ph = (min(pval, float(ASCII_MAX)) / float(ASCII_MAX)) * max_half
                top_y = max(dot_r, mid_y - ph - dot_r - 1.5)
                bot_y = min(height - dot_r, mid_y + ph + dot_r + 1.5)
                ctx.new_sub_path()
                ctx.arc(cx, top_y, dot_r, 0.0, 2 * math.pi)
                ctx.close_path()
                ctx.new_sub_path()
                ctx.arc(cx, bot_y, dot_r, 0.0, 2 * math.pi)
                ctx.close_path()
            ctx.fill()
            return True

        # ---------- Lời bài hát (lyrics_lrclib) ----------
        def _clear_lyrics_box(self):
            for child in self.lyrics_box.get_children():
                self.lyrics_box.remove(child)
                child.destroy()
            self.lyric_lines = []
            self.lyric_widgets = []
            self.lyric_buttons = []
            self.active_lyric_idx = -1

        def _set_lyrics_message(self, text):
            self._clear_lyrics_box()
            lbl = Gtk.Label(label=text, xalign=0.5)
            lbl.get_style_context().add_class("lyric-status")
            lbl.set_justify(Gtk.Justification.CENTER)
            lbl.set_line_wrap(True)
            lbl.set_hexpand(True)
            lbl.set_valign(Gtk.Align.CENTER)
            self.lyrics_box.pack_start(lbl, True, True, 24)
            self.lyrics_box.show_all()

        def _fetch_lyrics(self, title, artist, album, duration_sec):
            self._lyrics_req_id += 1
            req_id = self._lyrics_req_id

            if not title:
                self._set_lyrics_message("Không tìm thấy lời cho bài này")
                return

            self._set_lyrics_message("Đang tìm lời…")

            def worker():
                if lyrics_lrclib is None or not hasattr(lyrics_lrclib, "fetch_lyrics"):
                    return ("none", None)
                try:
                    raw = lyrics_lrclib.fetch_lyrics(title, artist, album, duration_sec)
                    return normalize_lyrics_result(raw)
                except Exception:
                    return ("none", None)

            def done(res):
                if req_id != self._lyrics_req_id:
                    return
                kind, payload = res if isinstance(res, tuple) and len(res) == 2 else ("none", None)
                if kind == "instrumental":
                    self._set_lyrics_message("Nhạc không lời")
                elif kind == "synced" and payload:
                    self._render_synced_lyrics(payload)
                elif kind == "plain" and payload:
                    self._render_plain_lyrics(payload)
                else:
                    self._set_lyrics_message("Không tìm thấy lời cho bài này")

            self._bg(worker, done=done)

        def _render_plain_lyrics(self, text):
            self._clear_lyrics_box()
            lbl = Gtk.Label(label=text, xalign=0.5)
            lbl.get_style_context().add_class("lyric-plain")
            lbl.set_justify(Gtk.Justification.CENTER)
            lbl.set_line_wrap(True)
            lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            lbl.set_max_width_chars(46)
            lbl.set_hexpand(True)
            self.lyrics_box.pack_start(lbl, False, False, 4)
            self.lyrics_box.show_all()
            adj = self.lyrics_sw.get_vadjustment()
            if adj is not None:
                adj.set_value(0.0)

        def _render_synced_lyrics(self, lines):
            self._clear_lyrics_box()
            cleaned = []
            for item in lines:
                try:
                    sec = float(item[0])
                    txt = str(item[1]).strip()
                    cleaned.append((sec, txt))
                except (IndexError, TypeError, ValueError):
                    continue

            if not cleaned:
                self._set_lyrics_message("Không tìm thấy lời cho bài này")
                return

            self.lyric_lines = cleaned

            # Đệm đầu & cuối để dòng đầu/cuối cũng cuộn tới vùng 40% được
            top_pad = Gtk.Box()
            top_pad.set_size_request(-1, int(LYRICS_HEIGHT * 0.32))
            self.lyrics_box.pack_start(top_pad, False, False, 0)

            for sec, txt in cleaned:
                btn = Gtk.Button()
                btn.get_style_context().add_class("lyric-btn")
                btn.set_relief(Gtk.ReliefStyle.NONE)
                btn.set_hexpand(True)

                lbl = Gtk.Label(label=txt if txt else "♪", xalign=0.5)
                lbl.get_style_context().add_class("lyric-line")
                lbl.set_justify(Gtk.Justification.CENTER)
                lbl.set_line_wrap(True)
                lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                lbl.set_max_width_chars(44)
                lbl.set_hexpand(True)

                btn.add(lbl)
                btn.connect("clicked", lambda _b, s=sec: self._seek_to(s))
                self.lyrics_box.pack_start(btn, False, False, 0)
                self.lyric_widgets.append(lbl)
                self.lyric_buttons.append(btn)

            bot_pad = Gtk.Box()
            bot_pad.set_size_request(-1, int(LYRICS_HEIGHT * 0.55))
            self.lyrics_box.pack_start(bot_pad, False, False, 0)

            self.lyrics_box.show_all()
            GLib.idle_add(lambda: (self._update_active_lyric(self._current_position(), force=True), False)[1])

        def _update_active_lyric(self, pos_sec, force=False):
            if not self.lyric_lines or not self.lyric_widgets:
                return
            idx = fallback_line_index_at(self.lyric_lines, pos_sec)
            if idx == self.active_lyric_idx and not force:
                return

            if 0 <= self.active_lyric_idx < len(self.lyric_widgets):
                self.lyric_widgets[self.active_lyric_idx].get_style_context().remove_class("active")

            self.active_lyric_idx = idx
            if 0 <= idx < len(self.lyric_widgets):
                lbl = self.lyric_widgets[idx]
                lbl.get_style_context().add_class("active")
                btn = self.lyric_buttons[idx]
                self._scroll_to_lyric_widget(btn)

        def _scroll_to_lyric_widget(self, widget):
            adj = self.lyrics_sw.get_vadjustment()
            if adj is None:
                return
            alloc = widget.get_allocation()
            if alloc.height <= 1 and alloc.y <= 0:
                return

            # Đặt tâm dòng đang hát ở khoảng 40% chiều cao khung lời (260px * 0.40)
            view_h = float(self.lyrics_sw.get_allocated_height() or LYRICS_HEIGHT)
            line_center = float(alloc.y) + float(alloc.height) / 2.0
            desired = line_center - view_h * 0.40
            max_scroll = max(0.0, adj.get_upper() - adj.get_page_size())
            target = max(0.0, min(desired, max_scroll))

            self._scroll_start = adj.get_value()
            self._scroll_target = target
            self._scroll_t0 = time.monotonic()

            if self._scroll_anim_id is None:
                self._scroll_anim_id = GLib.timeout_add(16, self._step_scroll_anim)

        def _step_scroll_anim(self):
            if self._quitting:
                self._scroll_anim_id = None
                return False
            adj = self.lyrics_sw.get_vadjustment()
            if adj is None:
                self._scroll_anim_id = None
                return False

            elapsed = (time.monotonic() - self._scroll_t0) * 1000.0
            duration_ms = 250.0
            if elapsed >= duration_ms:
                adj.set_value(self._scroll_target)
                self._scroll_anim_id = None
                return False

            # Ease-out cubic mượt trong ~250ms
            t = elapsed / duration_ms
            ease = 1.0 - (1.0 - t) ** 3
            val = self._scroll_start + (self._scroll_target - self._scroll_start) * ease
            adj.set_value(val)
            return True

        # ---------- Đóng khi bấm ra ngoài / Esc / SIGTERM ----------
        def _on_button_press(self, _widget, ev):
            alloc = self.panel.get_allocation()
            inside = (
                alloc.x <= ev.x <= alloc.x + alloc.width
                and alloc.y <= ev.y <= alloc.y + alloc.height
            )
            if not inside:
                self.quit()
                return True
            return False

        def _on_key_press(self, _widget, ev):
            if ev.keyval == Gdk.KEY_Escape:
                self.quit()
                return True
            return False

        def quit(self, *_args):
            if self._quitting:
                return False
            self._quitting = True

            for attr in ("_timer_1s", "_timer_100ms", "_scroll_anim_id"):
                tid = getattr(self, attr, None)
                if tid is not None:
                    try:
                        GLib.source_remove(tid)
                    except Exception:
                        pass
                    setattr(self, attr, None)

            self._stop_cava()
            remove_pidfile()
            if Gtk.main_level() > 0:
                Gtk.main_quit()
            return False

    win = MediaPopup(target_x=arg_x)
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        add_signal = GLibUnix.signal_add
    except (ValueError, ImportError):
        add_signal = GLib.unix_signal_add

    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda *_: win.quit() or False)
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda *_: win.quit() or False)

    win.show_all()
    try:
        Gtk.main()
    finally:
        win.quit()
    return 0


def main():
    args = sys.argv[1:]

    if "--selftest" in args:
        return run_selftest()

    if "--close" in args:
        pid = running_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        return 0

    arg_x = None
    if "--x" in args:
        idx = args.index("--x")
        if idx + 1 < len(args):
            try:
                arg_x = float(args[idx + 1])
            except ValueError:
                arg_x = None

    # Chạy lại khi đang mở = đóng (toggle)
    pid = running_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        return 0

    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    gi.require_version("GdkPixbuf", "2.0")

    write_pidfile()
    try:
        return run_app(arg_x=arg_x)
    finally:
        remove_pidfile()


if __name__ == "__main__":
    sys.exit(main())
