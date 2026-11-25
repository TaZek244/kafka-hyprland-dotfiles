#!/usr/bin/env bash
# Bảng chọn kiểu chia khu làm việc cho workspace đang xem (hypr/kafka-tile.lua).
# Mở bằng Super + G, hoặc từ hộp chức năng trên dock (ô "Chia khu").
# Cửa sổ đang chọn lúc mở bảng trở thành cửa sổ CHÍNH: nằm bên trái / ô đầu tiên.
#   2:1 = cửa sổ chính chiếm 2 phần, các cửa sổ khác xếp chồng ở 1 phần còn lại.
# "Tự động" = trả về layout mặc định (cuộn ngang kiểu niri).

if pidof rofi >/dev/null 2>&1; then
    pkill -x rofi
    exit 0
fi

# Ghi lại cửa sổ đang chọn TRƯỚC khi rofi chiếm focus
addr=$(hyprctl activewindow -j 2>/dev/null |
    python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("address", ""))
except Exception: pass')

cur=$(hyprctl repl 'return kafka_tile_current()' 2>/dev/null | head -n1)

#       kiểu   chữ to   nhãn
modes=("auto|Auto|tự động"
    "1:1|1 : 1|chia đôi"
    "2:1|2 : 1|cửa sổ này to"
    "1:2|1 : 2|cửa sổ này nhỏ"
    "3:1|3 : 1|to hơn nữa"
    "1:3|1 : 3|nhỏ hơn nữa"
    "grid|2 × 2|lưới"
    "cols|1:1:1|các cột đều"
    "rows|═══|các hàng đều")

entries="" sel=0 keys=()
for i in "${!modes[@]}"; do
    IFS='|' read -r key big label <<<"${modes[$i]}"
    keys+=("$key")
    if [[ "$key" == "$cur" ]]; then
        sel=$i
        e="<span font='FiraCode Nerd Font Bold 16' foreground='#d4af6a'>$big</span>
<span size='9pt' foreground='#d4af6a'>đang dùng</span>"
    else
        e="<span font='FiraCode Nerd Font Bold 16'>$big</span>
<span size='9pt' foreground='#a99bbd'>$label</span>"
    fi
    entries+="${entries:+|}$e"
done

choice=$(printf '%s' "$entries" | rofi -dmenu -i -markup-rows -sep '|' -eh 3 \
    -format i -no-custom -p "" -selected-row "$sel" \
    -theme "$HOME/.config/rofi/kafka-actions.rasi" \
    -theme-str 'listview { columns: 5; lines: 2; flow: horizontal; } panel { margin: 0px 98px 40px calc( 100% - 738px ); }')
[[ -z "$choice" ]] && exit 0

hyprctl eval "kafka_tile('${keys[$choice]}', '$addr')" >/dev/null
