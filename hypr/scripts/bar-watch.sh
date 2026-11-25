#!/usr/bin/env bash
# bar-watch.sh — biến sự kiện hệ thống thành signal cho Waybar, để các ô không phải hỏi định kỳ.
#
#   * dunst (D-Bus org.dunstproject.cmd0: historyLength / paused / pauseLevel / NotificationHistory*)
#       → RTMIN+10 (số thông báo trên dock) + RTMIN+12 (icon nút công cụ: chuông gạch khi im lặng)
#   * NetworkManager (`nmcli monitor`: kết nối VPN/WireGuard lên xuống, giao diện CloudflareWARP xuất hiện/mất)
#       → RTMIN+16 (ô VPN)
#
#   bar-watch.sh daemon    chạy nền (Hyprland tự chạy trong hyprland.start; một bản nhờ flock)
#   bar-watch.sh status    còn chạy không
#
# Sự kiện dồn dập được gộp: mỗi signal tối đa 1 lần / 0.5s. Lệnh theo dõi chết (dunst/NM khởi động lại) → chạy lại sau 3s.
set -u

LOCK="${XDG_RUNTIME_DIR:-/tmp}/kafka-bar-watch.lock"

fire() { # fire <số signal...>
    local s
    for s in "$@"; do pkill -RTMIN+"$s" -x waybar 2>/dev/null; done
}

# Đọc stdin, dòng nào khớp regex thì bắn signal (gộp 0.5s: đọc tiếp tới khi im 0.5s rồi mới bắn)
pump() { # pump <regex> <signal...>
    local re=$1
    shift
    local line
    while IFS= read -r line; do
        [[ $line =~ $re ]] || continue
        while IFS= read -r -t 0.5 line; do :; done # nuốt loạt sự kiện đi kèm
        fire "$@"
    done
}

watch_dunst() {
    while true; do
        gdbus monitor --session --dest org.freedesktop.Notifications --object-path /org/freedesktop/Notifications 2>/dev/null |
            pump "historyLength|paused|pauseLevel|NotificationHistory" 10 12
        sleep 3
    done
}

watch_nm() {
    while true; do
        nmcli monitor 2>/dev/null | pump "." 16
        sleep 3
    done
}

case "${1:-}" in
    daemon)
        exec 9>"$LOCK"
        flock -n 9 || exit 0 # đã có một bản chạy
        watch_dunst &
        watch_nm &
        trap 'kill 0' EXIT TERM INT
        wait
        ;;
    status)
        if pgrep -f 'scripts/bar-watch[.]sh daemon' >/dev/null; then echo "đang chạy"; else
            echo "không chạy"
            exit 1
        fi
        ;;
    *)
        echo "dùng: $0 daemon|status" >&2
        exit 2
        ;;
esac
