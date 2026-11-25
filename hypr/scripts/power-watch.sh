#!/usr/bin/env bash
# power-watch.sh : tự bật/tắt animation viền cửa sổ (borderangle) theo nguồn điện và chế độ nguồn.
#
# Vì sao cần: hiệu ứng xoay màu viền kiểu loop (`style = "loop"`) chạy mỗi khung hình, tốn ~3-4% CPU
# dù máy đang dùng pin. Ta giữ nó khi cắm sạc, tắt hẳn khi rút sạc hoặc khi đang power-saver.
#
# Cách xử lý:
#   1. Dò AC: file online đầu tiên trong /sys/class/power_supply/* có type = "Mains";
#      không tìm thấy thì coi như đã cắm sạc (máy không có pin).
#   2. Đọc profile bằng powerprofilesctl get (thiếu lệnh thì bỏ qua) và ghi đè từ
#      ${XDG_STATE_HOME:-$HOME/.local/state}/kafka/border-anim (on/off/auto).
#   3. Hàm thuần desired_state quyết định: ghi đè thắng; power-saver → off;
#      auto → on khi có AC, off khi dùng pin.
#   4. Chỉ gọi hyprctl lúc trạng thái đổi (lần đầu luôn áp); chạy mỗi 10s, một bản nhờ flock,
#      thoát khi socket Hyprland biến mất. KAFKA_HYPRCTL cho phép thay lệnh để thử nghiệm.
#
# Lệnh:
#   power-watch.sh daemon             giám sát (Hyprland gọi lúc khởi động; chỉ 1 bản)
#   power-watch.sh apply             áp một lần rồi thoát
#   power-watch.sh status            in nguồn ac/battery, profile, ghi đè, trạng thái mong muốn
#   power-watch.sh set on|off|auto   ghi file ghi đè rồi áp ngay
#   power-watch.sh --selftest        kiểm tra hàm quyết định (không gọi hyprctl)

RUN="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
LOCK="$RUN/kafka-power-watch.lock"
INTERVAL=10
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/kafka"
OVERRIDE_FILE="$STATE_DIR/border-anim"

log() { echo "power-watch: $*" >&2; }

# Hyprland còn sống? Ưu tiên signature của phiên này; không có thì tìm socket bất kỳ.
hyprland_alive() {
    local sig="${HYPRLAND_INSTANCE_SIGNATURE:-}" s
    if [[ -n "$sig" ]]; then
        [[ -S "$RUN/hypr/$sig/.socket.sock" ]]
    else
        for s in "$RUN"/hypr/*/.socket.sock; do
            [[ -S "$s" ]] && return 0
        done
        return 1
    fi
}

# 1 = cắm sạc, 0 = dùng pin; không có nguồn Mains thì coi như cắm sạc.
detect_ac() {
    local supply type value
    for supply in /sys/class/power_supply/*; do
        [[ -r "$supply/type" && -r "$supply/online" ]] || continue
        type=$(tr -d '[:space:]' <"$supply/type")
        [[ "$type" == "Mains" ]] || continue
        value=$(tr -d '[:space:]' <"$supply/online")
        [[ "$value" == "1" ]] && echo 1 || echo 0
        return 0
    done
    echo 1
}

# Chế độ nguồn; rỗng khi không có powerprofilesctl.
detect_profile() {
    command -v powerprofilesctl >/dev/null 2>&1 || return 0
    powerprofilesctl get 2>/dev/null | tr -d '[:space:]'
}

# File thiếu hoặc giá trị lạ đều xem như auto.
read_override() {
    local value=""
    [[ -r "$OVERRIDE_FILE" ]] && value=$(tr -d '[:space:]' <"$OVERRIDE_FILE")
    case "$value" in
        on | off) echo "$value" ;;
        *) echo auto ;;
    esac
}

# HÀM THUẦN: <ac 0|1> <profile> <override> → in on/off (không đụng hệ thống).
desired_state() {
    local ac=$1 profile=$2 override=$3
    case "$override" in
        on)
            echo on
            return
            ;;
        off)
            echo off
            return
            ;;
    esac
    [[ "$profile" == "power-saver" ]] && {
        echo off
        return
    }
    [[ "$ac" == "1" ]] && echo on || echo off
}

# Ảnh chụp trạng thái hiện tại, dùng chung cho status/apply/set/daemon.
snapshot() {
    AC=$(detect_ac)
    PROFILE=$(detect_profile)
    OVERRIDE=$(read_override)
    WANT=$(desired_state "$AC" "$PROFILE" "$OVERRIDE")
}

# Thay hyprctl bằng KAFKA_HYPRCTL (có thể kèm tham số) để thử nghiệm.
hyprctl_call() {
    local -a cmd
    read -r -a cmd <<<"${KAFKA_HYPRCTL:-hyprctl}"
    "${cmd[@]}" "$@"
}

apply_now() {
    log "áp $WANT (ac=$AC, profile=${PROFILE:-(rỗng)}, ghi đè=$OVERRIDE)"
    if [[ "$WANT" == "on" ]]; then
        # Phải truyền lại đủ tham số, nếu không hiệu ứng không chạy đúng dạng loop.
        hyprctl_call eval 'hl.animation({ leaf = "borderangle", enabled = true, speed = 60, bezier = "linear", style = "loop" })' ||
            log "không áp được 'on' qua hyprctl"
    else
        hyprctl_call eval 'hl.animation({ leaf = "borderangle", enabled = false })' ||
            log "không áp được 'off' qua hyprctl"
    fi
}

case "${1:-status}" in
    status)
        snapshot
        [[ "$AC" == "1" ]] && src=ac || src=battery
        echo "nguồn: $src"
        echo "profile: ${PROFILE:-(không có)}"
        echo "ghi đè: $OVERRIDE"
        echo "mong muốn: $WANT"
        ;;
    apply)
        snapshot
        apply_now
        ;;
    set)
        case "${2:-}" in
            on | off | auto) ;;
            *)
                sed -n '2,22p' "$0"
                exit 2
                ;;
        esac
        mkdir -p "$STATE_DIR" || {
            log "không tạo được $STATE_DIR"
            exit 1
        }
        printf '%s\n' "$2" >"$OVERRIDE_FILE" || {
            log "không ghi được $OVERRIDE_FILE"
            exit 1
        }
        snapshot
        apply_now
        ;;
    --selftest)
        pass=0 fail=0
        check() { # <mô tả> <ac> <profile> <override> <kỳ vọng>
            local desc=$1 ac=$2 profile=$3 override=$4 expect=$5 got
            got=$(desired_state "$ac" "$profile" "$override")
            if [[ "$got" == "$expect" ]]; then
                echo "PASS: $desc → $got"
                pass=$((pass + 1))
            else
                echo "FAIL: $desc → mong '$expect', được '$got'"
                fail=$((fail + 1))
            fi
        }
        check "cắm sạc / balanced / auto" 1 balanced auto on
        check "dùng pin / balanced / auto" 0 balanced auto off
        check "cắm sạc / power-saver / auto" 1 power-saver auto off
        check "dùng pin / ghi đè on" 0 balanced on on
        check "cắm sạc / ghi đè off" 1 balanced off off
        check "profile rỗng / cắm sạc" 1 "" auto on
        check "profile rỗng / dùng pin" 0 "" auto off
        check "power-saver / ghi đè on" 1 power-saver on on
        printf 'selftest: %d PASS, %d FAIL\n' "$pass" "$fail"
        ((fail == 0)) && exit 0
        exit 1
        ;;
    daemon)
        exec 9>"$LOCK"
        flock -n 9 || {
            log "đã có một bản đang chạy"
            exit 0
        }
        prev=""
        while :; do
            # Hyprland đã thoát (đăng xuất) → dừng giám sát
            hyprland_alive || {
                log "không thấy socket Hyprland → thoát"
                exit 0
            }
            snapshot
            # Lần đầu luôn áp; những lần sau chỉ gọi hyprctl khi trạng thái đổi.
            if [[ -z "$prev" || "$WANT" != "$prev" ]]; then
                apply_now
                prev="$WANT"
            fi
            sleep "$INTERVAL"
        done
        ;;
    *)
        sed -n '2,22p' "$0"
        exit 2
        ;;
esac
