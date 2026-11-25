#!/usr/bin/env bash
# toggle-app.sh <class-regex> <lệnh...>
# Có cửa sổ khớp class -> đóng nó; chưa có -> mở. Dùng cho các nút Waybar.
class=$1
shift
if hyprctl clients -j | grep -qE "\"class\": \"($class)\""; then
    hyprctl dispatch "hl.dsp.window.close({ window = \"class:^($class)$\" })" >/dev/null
else
    setsid -f "$@" >/dev/null 2>&1
fi
