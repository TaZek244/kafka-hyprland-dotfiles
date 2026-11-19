"""kafka_theme.py — kiểu "pixel mềm" dùng chung cho các popup GTK3 (đồng bộ với Waybar theme pixel).

Popup gọi `kafka_theme.apply(EXTRA_CSS)` SAU khi nạp CSS của mình: nếu giao diện đang là pixel
(`hypr/scripts/ui-theme.sh`, trạng thái ở ~/.local/state/kafka/ui-theme) thì thêm một provider ưu tiên cao
(USER + 5) gồm CSS chung + CSS riêng của popup; bản phẳng thì không làm gì.

  • Khung popup (.panel): ảnh 9-slice waybar/pixel/panel.png (bo 12, cắt 14) — cùng bộ với khung Waybar.
  • Ô con (ô bật/tắt, dòng, ngày lịch, nút): KHÔNG dùng border-image (cộng 14px mỗi ô làm popup phình ra),
    mà vẽ viền tối + mép sáng trên-trái + bóng dưới-phải bằng box-shadow inset (biến CARD/CARD_HOVER/CARD_ON).
"""

import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIXEL_DIR = os.path.join(REPO, "waybar", "pixel")
STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "kafka", "ui-theme")

# bảng màu (khớp waybar/pixel/make-frames.py và waybar/theme-pixel.css)
EDGE, HI, SH = "#140e1a", "#56466a", "#1d1626"
CARD_BG, HOVER_BG = "#30263c", "#4a3c59"
TEXT, DIM, FAINT = "#fbf7fd", "#d4cade", "#9a8bab"
PINK, PINK_HI, PINK_SH, PINK_EDGE, PINK_FG = "#c94785", "#f08cbb", "#962f62", "#3d1028", "#f08cbb"
CRIT = "#e0506e"

CARD = (f"background-color: {CARD_BG}; background-image: none; border: none; border-radius: 7px; "
        f"box-shadow: inset 0 0 0 1px {EDGE}, inset 2px 2px 0 -1px {HI}, inset -2px -2px 0 -1px {SH};")
CARD_HOVER = (f"background-color: {HOVER_BG}; "
              f"box-shadow: inset 0 0 0 1px {EDGE}, inset 2px 2px 0 -1px #7a6890, inset -2px -2px 0 -1px #2a2034;")
CARD_ON = (f"background-color: {PINK}; background-image: none; "
           f"box-shadow: inset 0 0 0 1px {PINK_EDGE}, inset 2px 2px 0 -1px {PINK_HI}, inset -2px -2px 0 -1px {PINK_SH};")
CARD_FLAT = f"background-color: rgba(20, 14, 26, 0.35); box-shadow: inset 0 0 0 1px {EDGE};"   # vùng chìm


def is_pixel():
    try:
        return open(STATE).read().strip() == "pixel"
    except OSError:
        return False


def panel(selector=".panel", padding="4px"):
    """CSS khung popup bằng ảnh 9-slice (viền ảnh 14px đã gồm lề trong, nên padding nhỏ lại)."""
    url = "file://" + os.path.join(PIXEL_DIR, "panel.png")
    # GTK3 KHÔNG vẽ phần giữa của border-image → tô nền bằng background-color giới hạn trong padding-box
    # (bên trong viền 14px), viền ảnh phủ phần mép + góc bo.
    return (f"{selector} {{ background-color: rgba(38, 30, 48, 0.95); background-clip: padding-box; "
            f"background-image: none; border-radius: 0; "
            f"border-style: solid; border-width: 14px; border-color: transparent; "
            f'border-image: url("{url}") 14 stretch; box-shadow: none; padding: {padding}; }}\n')


COMMON = f"""
* {{ text-shadow: 1px 1px 0 rgba(10, 6, 14, 0.5); }}
button {{ border-radius: 7px; }}
button:hover {{ {CARD_HOVER} }}
scale trough {{ min-height: 6px; border-radius: 3px; background-color: {CARD_BG};
                box-shadow: inset 0 0 0 1px {EDGE}; border: none; }}
scale highlight {{ min-height: 6px; border-radius: 3px; background-color: {PINK}; background-image: none;
                   box-shadow: inset 0 0 0 1px {PINK_EDGE}, inset 0 1px 0 0 {PINK_HI}; border: none; }}
scale slider {{ border-radius: 4px; background-color: {TEXT}; background-image: none; border: none;
                box-shadow: 0 0 0 1px {EDGE}, inset -1px -1px 0 0 #c9bcd8; }}
switch {{ border-radius: 7px; background-color: {CARD_BG}; background-image: none; border: none;
          box-shadow: inset 0 0 0 1px {EDGE}; }}
switch:checked {{ background-color: {PINK}; box-shadow: inset 0 0 0 1px {PINK_EDGE}, inset 0 1px 0 0 {PINK_HI}; }}
switch slider {{ border-radius: 5px; background-color: {TEXT}; box-shadow: 0 0 0 1px {EDGE}; }}
entry {{ background-color: {CARD_BG}; border: none; border-radius: 7px; color: {TEXT};
         box-shadow: inset 0 0 0 1px {EDGE}, inset 1px 1px 0 0 {SH}; }}
entry:focus {{ box-shadow: inset 0 0 0 1px {PINK}, inset 1px 1px 0 0 {SH}; }}
"""


def apply(extra="", screen=None):
    """Thêm CSS pixel (chung + riêng) nếu đang ở giao diện pixel. Trả về True nếu đã áp."""
    if not is_pixel():
        return False
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, Gtk
    prov = Gtk.CssProvider()
    prov.load_from_data((COMMON + extra).encode())
    Gtk.StyleContext.add_provider_for_screen(screen or Gdk.Screen.get_default(), prov,
                                             Gtk.STYLE_PROVIDER_PRIORITY_USER + 5)
    return True
