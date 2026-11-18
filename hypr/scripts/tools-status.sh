#!/usr/bin/env bash
# tools-status.sh : icon cho nút công cụ trên đầu dock (rê chuột mở popup tools-popup.py).
# Nút này báo trạng thái quan trọng:
#   đang quay màn hình  -> icon quay, class "recording" (đỏ)
#   Không làm phiền bật -> icon chuông gạch, class "dnd"
#   bình thường         -> icon dụng cụ, class "idle"
# Waybar cập nhật qua `signal: 12` (capture.sh và nút DND đều gửi RTMIN+12).
scripts="$HOME/.config/hypr/scripts"

if "$scripts/capture.sh" status 2>/dev/null | grep -q '"class": "recording"'; then
    printf '%s\n' '{"text":"󰑋","class":"recording","tooltip":"Đang quay màn hình\nRê chuột để mở công cụ · bấm nút chụp để dừng"}'
elif [ "$(dunstctl is-paused 2>/dev/null)" = true ]; then
    printf '%s\n' '{"text":"󰂛","class":"dnd","tooltip":"Không làm phiền: BẬT\nRê chuột để mở công cụ"}'
else
    printf '%s\n' '{"text":"󱁤","class":"idle","tooltip":"Công cụ: clipboard · chụp/quay · phím tắt · không làm phiền"}'
fi
