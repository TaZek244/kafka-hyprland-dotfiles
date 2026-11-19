#!/usr/bin/env bash
# lock.sh — khoá màn hình bằng hyprlock theo giao diện đang dùng (hypr/scripts/ui-theme.sh):
#   pixel → hypr/hyprlock-pixel.conf ; còn lại (hoặc thiếu file) → hyprlock.conf mặc định.
# Đã có hyprlock chạy thì thôi. Mọi chỗ khoá (Super + Escape, hypridle, menu nguồn, hộp chức năng) gọi script này.
# `lock.sh config` in đường dẫn file cấu hình sẽ dùng (để thử).
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/kafka/ui-theme"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIXEL_CONF="$HERE/hyprlock-pixel.conf"

conf=""
if [ "$(cat "$STATE" 2>/dev/null)" = "pixel" ] && [ -r "$PIXEL_CONF" ]; then
    conf="$PIXEL_CONF"
fi

if [ "${1:-}" = "config" ]; then
    echo "${conf:-$HERE/hyprlock.conf}"
    exit 0
fi

pidof hyprlock >/dev/null && exit 0
if [ -n "$conf" ]; then
    exec hyprlock -c "$conf"
fi
exec hyprlock
