#!/usr/bin/env bash
# Hộp chức năng nhanh: popup nhỏ nằm ngang, mở ra bên TRÁI đáy dock
# (rofi/kafka-actions.rasi). Thay cho ngăn kéo cũ của Waybar, vốn bung dọc
# và đè lên thẻ app đang mở. Bấm 1 lần để chạy, Esc / bấm ra ngoài để đóng.

# Bấm lại khi menu đang mở thì đóng nó (toggle).
if pidof rofi >/dev/null 2>&1; then
    pkill -x rofi
    exit 0
fi

scripts="$HOME/.config/hypr/scripts"

# Ghi lại cửa sổ đang chọn TRƯỚC khi rofi chiếm focus (dùng cho treo / nổi).
addr=$(hyprctl activewindow -j 2>/dev/null |
    python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("address", ""))
except Exception: pass')

item() { # item <icon> <màu> <nhãn>
    printf "<span font='FiraCode Nerd Font Propo 26' foreground='%s'>%s</span>\n<span size='10pt'>%s</span>" "$2" "$1" "$3"
}

entries="$(item $'\U000f075a' '#c77dff' 'Sóng nhạc')"
entries+="|$(item $'\U000f0403' '#e2c07d' 'Treo góc')"
entries+="|$(item $'\U000f0404' '#b9a3c4' 'Bỏ treo hết')"
entries+="|$(item $'\U000f05b2' '#7cc4ff' 'Nổi ⇄ xếp')"
entries+="|$(item $'\U000f0159' '#ff7aa2' 'Đóng app')"
entries+="|$(item $'\U000f0570' '#a8e6cf' 'Chia khu')"
entries+="|$(item $'\U000f033e' '#d8b4f8' 'Khóa')"

choice=$(printf '%s' "$entries" | rofi -dmenu -i -markup-rows -sep '|' -eh 3 \
    -format i -no-custom -p "" -theme "$HOME/.config/rofi/kafka-actions.rasi" \
    -theme-str 'listview { columns: 7; } panel { margin: 0px 98px 40px calc( 100% - 844px ); }')  # 7 ô: khung rộng 746px

[[ -z "$choice" ]] && exit 0
sleep 0.15   # chờ rofi đóng hẳn, focus trở lại cửa sổ cũ

case "$choice" in
    0) "$scripts/toggle-app.sh" kafka-cava kitty --class kafka-cava -e cava ;;
    1) "$scripts/pin-toggle.sh" ;;
    2) "$scripts/pin-toggle.sh" all ;;
    3) if [[ -n "$addr" ]]; then
           hyprctl dispatch "hl.dsp.window.float({ action = \"toggle\", window = \"address:$addr\" })" >/dev/null
       else
           hyprctl dispatch 'hl.dsp.window.float({ action = "toggle" })' >/dev/null
       fi ;;
    4) "$scripts/closemenu.sh" ;;
    5) "$scripts/tile-menu.sh" ;;
    6) pidof hyprlock >/dev/null || hyprlock ;;
esac
