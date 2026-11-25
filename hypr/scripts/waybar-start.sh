#!/usr/bin/env bash
# Bật Waybar lúc đăng nhập, ghi log và tự thử lại nếu nó thoát sớm.
# Lỗi gốc (2026-11-25): đăng nhập xong Waybar + dock không lên, phải bấm Super + Shift + B;
# lệnh cũ trong hyprland.start không ghi log nên không biết vì sao.
# Log: ~/.local/state/kafka/waybar.log (bản lần trước: waybar.log.1).
#   waybar-start.sh          chạy (Hyprland gọi trong hyprland.start)
set -u
REPO="$(cd "$(dirname "$(realpath "$0")")/../.." && pwd)"
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/kafka"
LOG="$STATE/waybar.log"
mkdir -p "$STATE"
[[ -f "$LOG" ]] && mv -f "$LOG" "$LOG.1"

log() { printf '[%(%F %T)T] %s\n' -1 "$*" >>"$LOG"; }

log "start: WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-} HYPRLAND_INSTANCE_SIGNATURE=${HYPRLAND_INSTANCE_SIGNATURE:-} DBUS=${DBUS_SESSION_BUS_ADDRESS:-}"
"$REPO/hypr/scripts/ui-theme.sh" ensure >>"$LOG" 2>&1 || log "ui-theme.sh ensure lỗi ($?)"
timeout 15 python3 "$REPO/hypr/scripts/hud.py" once >>"$LOG" 2>&1 || log "hud.py once lỗi/hết giờ ($?)"

# Thử tối đa 5 lần: Waybar sống quá 20s thì coi là ổn, thoát khỏi vòng (không tự bật lại
# khi người dùng chủ động tắt/khởi động lại Waybar sau đó).
for try in 1 2 3 4 5; do
    if pgrep -x waybar >/dev/null; then
        log "waybar đã chạy (bản khác), thôi"
        exit 0
    fi
    log "lần $try: chạy waybar"
    t0=$SECONDS
    waybar >>"$LOG" 2>&1 &
    pid=$!
    while kill -0 "$pid" 2>/dev/null && ((SECONDS - t0 < 20)); do sleep 1; done
    if kill -0 "$pid" 2>/dev/null; then
        log "waybar ổn định (pid $pid)"
        wait "$pid"
        rc=$?
        log "waybar thoát (mã $rc) sau $((SECONDS - t0))s"
        exit 0
    fi
    wait "$pid"
    rc=$?
    log "waybar thoát sớm (mã $rc) sau $((SECONDS - t0))s"
    sleep 2
done
log "bỏ cuộc sau 5 lần"
command -v notify-send >/dev/null && notify-send -u critical "Waybar" "Không khởi động được, xem $LOG"
