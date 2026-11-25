#!/usr/bin/env bash
# window-switch.sh : Super + Tab = chuyển cửa sổ (dùng bộ chuyển của hyprshell, như Alt + Tab).
#
# hyprshell chỉ cho MỘT phím bổ trợ cho bộ chuyển. Đặt "super" thì hyprshell bỏ luôn phím tổng quan
# (nhấn-thả Super), vì cả hai cùng nghe sự kiện thả Super_L. Nên hyprshell giữ "alt" (Alt + Tab), còn
# Super + Tab gán trong hyprland.lua gọi script này:
#   open | open-rev   nhấn Super + Tab / Super + Shift + Tab: mở bộ chuyển (hoặc sang cửa sổ kế), ghi cờ
#   release           thả Super (bind release + transparent): có cờ thì đóng bộ chuyển và nhảy tới cửa sổ
#                     đang chọn; không có cờ (nhấn-thả Super một mình) thì không làm gì, để hyprshell
#                     mở tổng quan như cũ.
#   cancel            đóng bộ chuyển, không nhảy

FLAG="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kafka-window-switch"
send() { hyprshell socat "$1" >/dev/null 2>&1; }

case "$1" in
    open)
        : >"$FLAG"
        send '{"OpenSwitch":{"reverse":false}}'
        ;;
    open-rev)
        : >"$FLAG"
        send '{"OpenSwitch":{"reverse":true}}'
        ;;
    release)
        [[ -e "$FLAG" ]] || exit 0
        rm -f "$FLAG"
        send '{"CloseSwitch":{"switch":true}}'
        ;;
    cancel)
        rm -f "$FLAG"
        send '{"CloseSwitch":{"switch":false}}'
        ;;
    *)
        sed -n '2,13p' "$0"
        exit 2
        ;;
esac
