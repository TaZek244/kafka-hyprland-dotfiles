#!/usr/bin/env bash
# Menu nguồn Kafka: popup giữa màn hình (rofi/kafka-power.rasi).
# Mỗi mục = icon to (dòng trên) + nhãn (dòng dưới), tách mục bằng '|'.

# Bấm lại khi menu đang mở thì đóng nó (toggle).
if pidof rofi >/dev/null 2>&1; then
    pkill -x rofi
    exit 0
fi

theme="$HOME/.config/rofi/kafka-power.rasi"

item() { # item <icon> <nhãn>
    printf "<span font='FiraCode Nerd Font 34'>%s</span>\n<span size='11pt'>%s</span>" "$1" "$2"
}

# show <số cột> <lời nhắn> <mục...>  -> in ra chỉ số mục đã chọn
show() {
    local cols=$1 mesg=$2; shift 2
    local entries="" first=1 e
    for e in "$@"; do
        if ((first)); then entries=$e; first=0; else entries+="|$e"; fi
    done
    printf '%s' "$entries" | rofi -dmenu -i -markup-rows -sep '|' -eh 3 \
        -format i -no-custom -p "" -mesg "<span font='FiraCode Nerd Font Bold 14' foreground='#d4af6a'>󰐥  Kafka · Nguồn</span>
<span size='10pt'>$mesg</span>" -theme "$theme" \
        ${sel:+-selected-row $sel} -theme-str "listview { columns: $cols; } panel { margin: 0px calc( 50% - $((cols * 89))px ); }"
}

confirm() { # confirm <hành động>
    local ans
    ans=$(sel=1 show 2 "Chắc chắn muốn $1?" "$(item '󰄬' 'Có')" "$(item '󰅖' 'Không')")
    [[ "$ans" == "0" ]]
}

choice=$(show 5 "Esc hoặc bấm ra ngoài để đóng" \
    "$(item '󰍁' 'Lock')" \
    "$(item '󰤄' 'Suspend')" \
    "$(item '󰍃' 'Logout')" \
    "$(item '󰜉' 'Reboot')" \
    "$(item '󰐥' 'Shutdown')")

case "$choice" in
    0) pidof hyprlock >/dev/null || hyprlock ;;
    1) systemctl suspend ;;
    2) confirm "đăng xuất" && hyprctl dispatch "hl.dsp.exit()" ;;
    3) confirm "khởi động lại" && systemctl reboot ;;
    4) confirm "tắt máy" && systemctl poweroff ;;
esac
