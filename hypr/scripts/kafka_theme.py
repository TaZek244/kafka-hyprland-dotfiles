"""kafka_theme.py — kiểu pixel "KAFKA.SYS" dùng chung cho các popup GTK3 (đồng bộ Waybar theme pixel và
màn hình đăng nhập greetd/kafka-greeter).

Popup gọi `kafka_theme.apply(EXTRA_CSS)` SAU khi nạp CSS của mình: nếu giao diện đang là pixel
(`hypr/scripts/ui-theme.sh`, trạng thái ở ~/.local/state/kafka/ui-theme) thì thêm một provider ưu tiên cao
(USER + 5) gồm CSS chung + CSS riêng của popup; bản phẳng thì không làm gì.

  • Khung popup (.panel): ảnh 9-slice waybar/pixel/win.png vẽ trên lưới ô 3px (góc bậc thang, viền tối,
    mép sáng/bóng, bóng cứng), cắt 6 9 9 6; DẢI TIÊU ĐỀ hồng (win-title.png) + 3 ô vuông (win-dots.png)
    như cửa sổ game là LỚP NỀN trong padding-box (GTK3 vẽ border-image đè nền). panel() tự cộng chỗ cho dải
    vào padding. Sinh ảnh bằng waybar/pixel/make-frames.py.
  • Ô con (ô bật/tắt, dòng, ngày lịch, nút): KHÔNG dùng border-image (cộng 14px mỗi ô làm popup phình ra)
    mà vẽ bằng box-shadow inset: viền tối 2px + mép sáng trên-trái + bóng dưới-phải 2px (CARD/CARD_HOVER/CARD_ON).
  • Mọi `border-radius` trong CSS riêng của popup bị ép về 0 (ô vuông = chất pixel), không cần sửa từng popup.
"""

import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIXEL_DIR = os.path.join(REPO, "waybar", "pixel")
STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "kafka", "ui-theme")

# bảng màu (khớp waybar/pixel/make-frames.py và waybar/theme-pixel.css)
EDGE, HI, SH = "#140e1a", "#56466a", "#1d1626"
CARD_BG, HOVER_BG = "#30263c", "#4a3c59"
TEXT, DIM, FAINT = "#fbf7fd", "#d4cade", "#9a8bab"
PINK, PINK_HI, PINK_SH, PINK_EDGE, PINK_FG = "#c94785", "#f08cbb", "#962f62", "#3d1028", "#f08cbb"
CRIT = "#e0506e"
# font pixel dựng từ font 5×7 của trình đăng nhập (fonts/build-kafka-pixel-font.py, unitsPerEm 700):
# cỡ px chia hết cho 7 thì nét sắc (14px = 2px/điểm, 28 = 4, 42 = 6). Chỉ có chữ HOA không dấu + số.
PIXEL_FONT = "Kafka Pixel"

def _bevel(edge, hi, sh):
    """Viền tối 2px + mép sáng trên-trái 2px + bóng dưới-phải 2px (vuông, không blur)."""
    return (f"box-shadow: inset 0 0 0 2px {edge}, inset 4px 4px 0 -2px {hi}, inset -4px -4px 0 -2px {sh};")


CARD = f"background-color: {CARD_BG}; background-image: none; border: none; border-radius: 0; " + _bevel(EDGE, HI, SH)
CARD_HOVER = f"background-color: {HOVER_BG}; " + _bevel(EDGE, "#7a6890", "#2a2034")
CARD_ON = f"background-color: {PINK}; background-image: none; color: #ffffff; " + _bevel(PINK_EDGE, PINK_HI, PINK_SH)
CARD_FLAT = f"background-color: rgba(20, 14, 26, 0.45); border-radius: 0; box-shadow: inset 0 0 0 2px {EDGE}, inset 4px 4px 0 -2px {SH};"   # vùng chìm


def is_pixel():
    try:
        return open(STATE).read().strip() == "pixel"
    except OSError:
        return False


WIN_CUT = (6, 9, 9, 6)          # trên phải dưới trái — khớp make_win() trong make-frames.py
WIN_TITLE_H = 24                # cao dải tiêu đề (win-title.png)
WIN_FILL = "rgba(34, 26, 43, 0.985)"   # gần đục: popup hay nằm trên chữ sáng (terminal), 0.96 còn lộ


def panel(selector=".panel", padding="4px"):
    """CSS khung popup kiểu cửa sổ game: khung lưới win.png + dải tiêu đề hồng + 3 ô vuông (lớp nền)."""
    win, title, dots = ("file://" + os.path.join(PIXEL_DIR, f) for f in ("win.png", "win-title.png", "win-dots.png"))
    t, r, b, l = WIN_CUT
    p = [int(x.rstrip("px") or 0) for x in padding.split()]
    if len(p) == 1:
        p = p * 4
    elif len(p) == 2:
        p = p * 2
    elif len(p) == 3:
        p = p + [p[1]]
    pad = f"{p[0] + WIN_TITLE_H + 6}px {p[1] + 4}px {p[2] + 4}px {p[3] + 4}px"   # chừa dải tiêu đề + lề trong
    # GTK3 vẽ border-image ĐÈ nền và KHÔNG vẽ phần giữa → nền = 3 lớp trong padding-box (trên cùng trước):
    # 3 ô vuông (phải-trên), dải tiêu đề lặp ngang (trên), màu nền (gradient một màu).
    return (f"{selector} {{ background-color: transparent; border-radius: 0; box-shadow: none; "
            f'background-image: url("{dots}"), url("{title}"), linear-gradient({WIN_FILL}, {WIN_FILL}); '
            f"background-repeat: no-repeat, repeat-x, no-repeat; background-position: right top, left top, center; "
            f"background-origin: padding-box, padding-box, padding-box; "
            f"background-clip: padding-box, padding-box, padding-box; "
            f"border-style: solid; border-width: {t}px {r}px {b}px {l}px; border-color: transparent; "
            f'border-image: url("{win}") {t} {r} {b} {l} stretch; padding: {pad}; }}\n')


COMMON = f"""
* {{ text-shadow: 2px 2px 0 rgba(11, 7, 16, 0.85); }}
button {{ border-radius: 0; }}
button:hover {{ {CARD_HOVER} }}
scale trough {{ min-height: 8px; border-radius: 0; background-color: #1a1422; border: none;
                box-shadow: inset 0 0 0 2px {EDGE}; }}
scale highlight {{ min-height: 8px; border-radius: 0; background-color: {PINK}; background-image: none; border: none;
                   box-shadow: inset 0 0 0 2px {PINK_EDGE}, inset 0 4px 0 -2px {PINK_HI}; }}
scale slider {{ min-width: 14px; min-height: 18px; border-radius: 0; background-color: {TEXT}; background-image: none;
                border: none; box-shadow: inset 0 0 0 2px {EDGE}, inset -4px -4px 0 -2px #c9bcd8, 2px 2px 0 0 {EDGE}; }}
switch {{ border-radius: 0; background-color: #1a1422; background-image: none; border: none;
          box-shadow: inset 0 0 0 2px {EDGE}; }}
switch:checked {{ background-color: {PINK}; box-shadow: inset 0 0 0 2px {PINK_EDGE}, inset 0 4px 0 -2px {PINK_HI}; }}
switch slider {{ border-radius: 0; background-color: {TEXT}; box-shadow: inset 0 0 0 2px {EDGE}, inset -4px -4px 0 -2px #c9bcd8; }}
entry {{ background-color: #1a1422; border: none; border-radius: 0; color: {TEXT};
         box-shadow: inset 0 0 0 2px {EDGE}, inset 4px 4px 0 -2px {SH}; }}
entry:focus {{ box-shadow: inset 0 0 0 2px {PINK}, inset 4px 4px 0 -2px {SH}; }}
scrollbar slider {{ border-radius: 0; }}
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
    extra = re.sub(r"border-radius:\s*[^;}]+", "border-radius: 0", extra)   # ô vuông ở mọi popup
    prov.load_from_data((COMMON + extra).encode())
    Gtk.StyleContext.add_provider_for_screen(screen or Gdk.Screen.get_default(), prov,
                                             Gtk.STYLE_PROVIDER_PRIORITY_USER + 5)
    return True
