#!/usr/bin/env bash
# Menu đóng chương trình (Super + Shift + Q, hoặc bấm vào tên cửa sổ trên Waybar).
# Liệt kê mọi cửa sổ đang mở; bấm 1 lần để đóng. Esc để thoát.

if pidof rofi >/dev/null 2>&1; then
    pkill -x rofi
    exit 0
fi

mapfile -t rows < <(hyprctl clients -j | python3 -c '
import json, sys, html
try:
    clients = json.load(sys.stdin)
except (json.JSONDecodeError, TypeError):
    sys.exit(1)
for c in clients:
    if not c.get("mapped", True):
        continue
    address = c.get("address", "")
    if not address:
        continue
    workspace = c.get("workspace") or {}
    ws = workspace.get("name", "") if isinstance(workspace, dict) else ""
    cls = c.get("class", "") or ""
    title = (c.get("title") or cls)[:60]
    print(address + "\t" + html.escape(cls) + "\t" + ws + "\t" + html.escape(title))
')

if ((${#rows[@]} == 0)); then
    notify-send "Kafka" "Không có cửa sổ nào đang mở."
    exit 0
fi

entries=""
for r in "${rows[@]}"; do
    IFS=$'\t' read -r _addr cls ws title <<<"$r"
    entries+="<b>$cls</b>  <span foreground='#a99bbd'>· $ws · $title</span>"$'\n'
done

idx=$(printf '%s' "$entries" | rofi -dmenu -i -markup-rows -format i -no-custom \
    -p "󰅙  Đóng" -mesg "Bấm vào chương trình muốn đóng · Esc để thoát" \
    -theme "$HOME/.config/rofi/kafka.rasi" \
    -theme-str 'entry { placeholder: "  Lọc chương trình cần đóng..."; }')

[[ -z "$idx" ]] && exit 0
addr=${rows[$idx]%%$'\t'*}
hyprctl dispatch "hl.dsp.window.close({ window = \"address:$addr\" })" >/dev/null
