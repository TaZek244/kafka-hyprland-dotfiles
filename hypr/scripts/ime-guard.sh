#!/usr/bin/env bash
# ime-guard.sh : giữ cho bộ gõ fcitx5 luôn chạy đúng trong phiên Hyprland (cho MỌI app, một trạng thái chung).
#
# Vì sao cần: fcitx5 có thể bị bật từ 2 nơi: Hyprland (`fcitx5 -d`) và D-Bus (bất kỳ ai gọi
# `fcitx5-remote`, vd ô VI/EN của Waybar, sẽ khiến D-Bus tự chạy /usr/bin/fcitx5). Bản do D-Bus bật
# lấy môi trường của trình quản lý D-Bus; nếu nó bật trước khi Hyprland xuất WAYLAND_DISPLAY thì
# fcitx5 không nối được vào Wayland → mọi app Wayland gõ không dấu, còn `fcitx5 -d` của Hyprland
# thấy đã có bản chạy nên tự thoát. Đúng/sai tùy lần đăng nhập ("lúc gõ được lúc không").
#
# Cách xử lý:
#   1. Xuất môi trường phiên (WAYLAND_DISPLAY, biến IM...) cho D-Bus/systemd TRƯỚC khi mọi thứ khác chạy,
#      để bản fcitx5 nào được bật cũng có môi trường đúng.
#   2. Kiểm tra sức khỏe: fcitx5 chạy đúng 1 bản, cùng WAYLAND_DISPLAY với phiên, và đã nối frontend
#      Wayland (DebugInfo có "Group [wayland:"). Sai thì diệt hẳn (-9, để không ghi đè profile) và bật lại.
#   3. Chạy nền, kiểm tra mỗi 5s; fcitx5 chết hay mất Wayland thì tự bật lại và báo bằng dunst.
#
# Lệnh:
#   ime-guard.sh daemon    chạy giám sát (Hyprland gọi đầu tiên trong hyprland.start; chỉ 1 bản)
#   ime-guard.sh restart   diệt và bật lại fcitx5 ngay (bấm giữa ô VI/EN)
#   ime-guard.sh status    in tình trạng; mã thoát 0 = khỏe
#   ime-guard.sh env       chỉ xuất môi trường cho D-Bus/systemd

RUN="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
LOCK="$RUN/kafka-ime-guard.lock"
INTERVAL=5
ENV_VARS=(WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE HYPRLAND_INSTANCE_SIGNATURE
          GTK_IM_MODULE QT_IM_MODULE XMODIFIERS SDL_IM_MODULE)

log() { echo "ime-guard: $*" >&2; }

export_env() {
    local present=()
    for v in "${ENV_VARS[@]}"; do [[ -n "${!v}" ]] && present+=("$v"); done
    ((${#present[@]})) || return 0
    dbus-update-activation-environment --systemd "${present[@]}" 2>/dev/null \
        || systemctl --user import-environment "${present[@]}" 2>/dev/null
}

# Lý do không khỏe (rỗng = khỏe)
problem() {
    local pids n pid wd
    pids=$(pgrep -x -u "$(id -u)" fcitx5)
    n=$(wc -w <<<"$pids")
    ((n == 0)) && { echo "fcitx5 không chạy"; return; }
    ((n > 1)) && { echo "có $n bản fcitx5"; return; }
    pid=$pids
    wd=$(tr '\0' '\n' <"/proc/$pid/environ" 2>/dev/null | sed -n 's/^WAYLAND_DISPLAY=//p')
    [[ -n "$WAYLAND_DISPLAY" && "$wd" != "$WAYLAND_DISPLAY" ]] \
        && { echo "fcitx5 (pid $pid) chạy với WAYLAND_DISPLAY='${wd}' thay vì '$WAYLAND_DISPLAY'"; return; }
    if ! busctl --user --timeout=2 call org.fcitx.Fcitx5 /controller org.fcitx.Fcitx.Controller1 DebugInfo \
            2>/dev/null | grep -q 'Group \[wayland:'; then
        echo "fcitx5 (pid $pid) chưa nối frontend Wayland"; return
    fi
}

start_fcitx() {
    pkill -9 -x -u "$(id -u)" fcitx5 2>/dev/null && sleep 0.3
    setsid -f fcitx5 -d >/dev/null 2>&1
    # chờ fcitx5 nối xong (tối đa ~6s)
    for _ in $(seq 30); do sleep 0.2; [[ -z "$(problem)" ]] && { activate_vi; return 0; }; done
    return 1
}

# Bật sẵn tiếng Việt. Với ShareInputState=All, fcitx5 vừa khởi động lại có thể để trạng thái chung là
# EN dù ActiveByDefault=True; "-o" bật cho mọi cửa sổ (một trạng thái dùng chung).
activate_vi() { sleep 0.3; fcitx5-remote -o 2>/dev/null; }

notify() { command -v notify-send >/dev/null && notify-send -a "Bộ gõ" -i fcitx "$@"; }

case "${1:-status}" in
    env) export_env ;;
    status)
        p=$(problem)
        if [[ -z "$p" ]]; then echo "OK: fcitx5 $(fcitx5-remote -n 2>/dev/null) (trạng thái $(fcitx5-remote 2>/dev/null))"; exit 0
        else echo "LỖI: $p"; exit 1; fi ;;
    restart)
        export_env
        if start_fcitx; then notify "Đã khởi động lại bộ gõ" "Cửa sổ terminal mở từ trước nếu gõ không dấu thì mở cửa sổ mới."
        else notify -u critical "Bộ gõ chưa chạy được" "$(problem)"; exit 1; fi ;;
    daemon)
        exec 9>"$LOCK"
        flock -n 9 || { log "đã có một bản đang chạy"; exit 0; }
        export_env
        p=$(problem)
        if [[ -n "$p" ]]; then
            log "lúc khởi động: $p → bật lại"
            start_fcitx || log "chưa ổn: $(problem)"
        else
            activate_vi
        fi
        bad=0
        while sleep "$INTERVAL"; do
            # Hyprland đã thoát (đăng xuất) → dừng giám sát
            [[ -n "$HYPRLAND_INSTANCE_SIGNATURE" && ! -S "$RUN/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket.sock" ]] && exit 0
            p=$(problem)
            if [[ -z "$p" ]]; then bad=0; continue; fi
            # 2 lần liên tiếp mới xử lý (tránh lúc fcitx5 đang tự khởi động lại)
            ((++bad < 2)) && continue
            log "$p → bật lại"
            if start_fcitx; then
                notify "Bộ gõ đã được tự khởi động lại" "Lý do: $p. Terminal mở từ trước nếu gõ không dấu thì mở cửa sổ mới."
            else
                notify -u critical "Bộ gõ gặp lỗi" "$(problem). Bấm giữa ô VI/EN để thử lại."
            fi
            bad=0
        done ;;
    *) sed -n '2,22p' "$0"; exit 2 ;;
esac
