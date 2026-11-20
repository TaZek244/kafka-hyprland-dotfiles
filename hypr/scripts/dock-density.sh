#!/usr/bin/env bash
# Co giãn thẻ app trên dock theo số cửa sổ đang mở, để dock KHÔNG BAO GIỜ dài quá
# màn hình (Waybar không cuộn được: quá nhiều app thì đáy dock chìm xuống dưới).
# Hyprland gọi script này mỗi khi mở/đóng cửa sổ (hl.on trong hyprland.lua).
# Nó ghi waybar/dock-density.css; Waybar tự nạp lại nhờ reload_style_on_change.
#
# Mỗi ô app là ảnh 40px (image#wN do dock-apps.py vẽ) + 2*lề 2px = 44px/ô (dock phẳng 48px, 2026-11-18).
# Khi chật: lề âm + thu nhỏ hình ảnh bằng -gtk-icon-transform.

css="$HOME/.config/waybar/dock-density.css"

# Chiều cao các khối KHÁC thẻ app trên dock (đo thật trên màn 1080p, khay 1 icon):
#   F_NORMAL  = 571px : các nút cố định ở cỡ thường (dock phẳng 48px: ô 42px, 2 nút đáy 46px). Trước 625 khi dock 61px
#   F_COMPACT = 523px : chỉ thu gọn 5 app ghim (36px/nút) + khay + thẻ app. KHÔNG thu các nút từ
#                       nút tiện ích trở lên: vùng rê chuột của tools-popup.py đặt theo toạ độ cố định.
# Nhóm công cụ chỉ còn 1 nút (custom/tools); các công cụ nằm trong popup ngang (tools-popup.py).
# RESERVE chừa chỗ cho khay hệ thống có thêm icon. Dock cao = màn hình - 64.
# Thêm/bớt nút cố định trên dock thì đo lại 2 số này:
#   mở nhiều cửa sổ cho dock tràn nhẹ, đọc chiều cao H ở `hyprctl layers`
#   (namespace dockbar; H bị chặn ở 1080), rồi F = H - số_cửa_sổ * bước_nút.
F_NORMAL=613 F_COMPACT=565 RESERVE=20   # dock phẳng 48px (ô 42px); +42 cho nút thông báo chuyển xuống dock (2026-11-20)
mon_h=$(hyprctl monitors -j 2>/dev/null | python3 -c '
import json, sys
try:
    m = next((m for m in json.load(sys.stdin) if m.get("focused")), None)
    print(int(m["height"] / m["scale"]) if m else 1080)
except Exception:
    print(1080)')
dock_h=$(( mon_h - 40 ))   # dock gắn sát mép dưới, ngay dưới thanh trên cao 40 (đo: hyprctl layers, dockbar h=1040)

# Số ô trên thẻ app = số APP (dock gộp cửa sổ cùng class, xem dock-apps.py), cùng bộ lọc:
# bỏ cava, cửa sổ chưa map, cửa sổ ở workspace đặc biệt (đang ẩn); tối đa 10 ô.
n=$(hyprctl clients -j 2>/dev/null | python3 -c '
import json, sys
try:
    cls = {c.get("class") for c in json.load(sys.stdin)
           if c.get("mapped", True) and c.get("class") and c.get("class") != "kafka-cava"
           and (c.get("workspace") or {}).get("id", -1) >= 0
           and not str((c.get("workspace") or {}).get("name", "")).startswith("special:")}
    print(min(len(cls), 10))
except Exception:
    print(0)')
n=${KAFKA_DOCK_TEST_N:-$n}   # thử: KAFKA_DOCK_TEST_N=10 dock-density.sh
[[ "$n" =~ ^[0-9]+$ ]] || exit 0
(( n < 1 )) && n=1

# Bước 1: giữ các nút cố định ở cỡ thường nếu thẻ app vẫn đủ cỡ (44px/ô).
# Bước 2: không đủ thì thu gọn các nút cố định để nhường chỗ, rồi mới thu ô app.
compact=0
pitch=$(( (dock_h - F_NORMAL - RESERVE) / n ))
if (( pitch < 44 )); then
    compact=1
    pitch=$(( (dock_h - F_COMPACT - RESERVE) / n ))
fi
(( pitch > 44 )) && pitch=44
(( pitch < 16 )) && pitch=16

new="/* Tự sinh bởi hypr/scripts/dock-density.sh — đừng sửa tay. $n app: ${pitch}px/ô$( ((compact)) && echo ', nút cố định thu gọn'). */"
if (( compact )); then
    new+="
#custom-pin-browser, #custom-pin-terminal, #custom-pin-files, #custom-pin-code, #custom-pin-editor {
    min-height: 34px; font-size: 17px; padding: 0 12px;
}
window#waybar.dockbar #pinned { padding: 3px 0; }
window#waybar.dockbar #tray { padding: 6px 0 4px; }
window#waybar.dockbar #windows { margin: 2px 0; }"
fi
if (( pitch < 44 )); then
    rest=$(( pitch - 40 ))                 # âm: lề âm để ô thấp hơn ảnh
    mt=$(( rest >= 0 ? rest / 2 : -((-rest + 1) / 2) ))
    mb=$(( rest - mt ))
    scale=$(python3 -c "print(min(1.0, round(($pitch - 4) / 40, 2)))")
    new+="
window#waybar.dockbar #windows #image { margin-top: ${mt}px; margin-bottom: ${mb}px; -gtk-icon-transform: scale($scale); }"
fi

# Chỉ ghi khi nội dung đổi, tránh Waybar nạp lại CSS vô ích
[[ -f "$css" && "$(<"$css")" == "$new" ]] && exit 0
printf '%s\n' "$new" > "$css"
