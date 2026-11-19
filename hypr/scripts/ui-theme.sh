#!/usr/bin/env bash
# ==============================================================================
# Kafka's Web — Đổi giao diện Waybar & Widget ("flat" / "pixel")
#
# Cách dùng:
#   ui-theme.sh pixel       Chuyển sang giao diện khung pixel art
#   ui-theme.sh flat        Chuyển sang giao diện phẳng mặc định
#   ui-theme.sh toggle      Đảo giữa flat và pixel
#   ui-theme.sh status      In trạng thái hiện tại ("flat" hoặc "pixel")
#   ui-theme.sh ensure      Tạo waybar/theme.css nếu chưa có (không side effect)
#   ui-theme.sh --selftest  Tự kiểm tra logic trong thư mục tạm
# ==============================================================================

set -u

SCRIPT_DIR=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
if [[ -n "${KAFKA_UI_TEST_REPO:-}" ]]; then
    REPO="$KAFKA_UI_TEST_REPO"
else
    REPO=$(cd "$SCRIPT_DIR/../.." && pwd)
fi

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/kafka"
STATE="$STATE_DIR/ui-theme"
THEME_CSS="$REPO/waybar/theme.css"
HEADER_COMMENT="/* Tự sinh bởi hypr/scripts/ui-theme.sh — đừng sửa tay. */"

# In khối hướng dẫn đầu file ra stderr và thoát với mã 2
usage() {
    sed -n '2,12s/^# \{0,1\}//p' "$0" >&2
    exit 2
}

# Ghi nội dung vào file đích một cách nguyên tử (ghi file tạm cùng thư mục rồi mv)
atomic_write() {
    local target="$1"
    local content="$2"
    local dir
    dir=$(dirname "$target")
    mkdir -p "$dir" || return 1

    local tmp
    tmp=$(mktemp "$dir/.tmp.XXXXXX") || return 1
    printf '%s\n' "$content" > "$tmp" || {
        rm -f "$tmp"
        return 1
    }
    mv -f "$tmp" "$target"
}

# Đọc trạng thái hiện tại ("flat" hoặc "pixel", mặc định "flat")
get_status() {
    if [[ -r "$STATE" ]]; then
        local val=""
        IFS= read -r val < "$STATE" || true
        if [[ "$val" == "pixel" || "$val" == "flat" ]]; then
            printf '%s\n' "$val"
            return 0
        fi
    fi
    printf 'flat\n'
}

# Ghi file waybar/theme.css tương ứng với chế độ
ROFI_CSS="$REPO/rofi/theme-current.rasi"
WALKER_CSS="$REPO/walker/themes/kafka/theme-current.css"
DUNST_DROPIN="$REPO/dunst/dunstrc.d/50-ui-theme.conf"

# Ghi mọi file "theme-current" (Waybar, rofi, walker) + file bổ sung của dunst theo chế độ.
# Các file này tự sinh (gitignore); thiếu file nào thì Waybar/rofi/walker có thể lỗi CSS → `ensure` tạo lại.
write_theme_css() {
    local mode="$1"
    if [[ "$mode" == "pixel" ]]; then
        atomic_write "$THEME_CSS" "$HEADER_COMMENT
@import \"theme-pixel.css\";"
        atomic_write "$ROFI_CSS" "$HEADER_COMMENT
@import \"theme-pixel.rasi\""
        atomic_write "$WALKER_CSS" "$HEADER_COMMENT
@import url(\"theme-pixel.css\");"
        mkdir -p "$(dirname "$DUNST_DROPIN")"
        cp -f "$REPO/dunst/theme-pixel.conf" "$DUNST_DROPIN" 2>/dev/null || true
    else
        atomic_write "$THEME_CSS" "$HEADER_COMMENT"
        atomic_write "$ROFI_CSS" "$HEADER_COMMENT"
        atomic_write "$WALKER_CSS" "$HEADER_COMMENT"
        rm -f "$DUNST_DROPIN"
    fi
}

check_pidfile_proc() {
    local pidfile="$1"
    local needle="$2"

    [[ -r "$pidfile" ]] || return 1
    local pid=""
    IFS= read -r pid < "$pidfile" || true

    # Chỉ chấp nhận PID là số nguyên dương
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    [[ -r "/proc/$pid/cmdline" ]] || return 1

    local cmdline=""
    cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
    if [[ "$cmdline" == *"$needle"* ]]; then
        printf '%s\n' "$pid"
        return 0
    fi
    return 1
}

# Áp dụng các hiệu ứng phụ lên widget & gửi thông báo
apply_side_effects() {
    local mode="$1"
    if [[ "${KAFKA_UI_NO_SIDE_EFFECTS:-0}" == "1" ]]; then
        return 0
    fi

    local runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    local fillet_pidfile="$runtime_dir/kafka-corner-fillet.pid"
    local media_pidfile="$runtime_dir/kafka-media-pill.pid"
    local pid=""

    # 1. Góc lõm corner-fillet (chỉ hợp với bản phẳng)
    if [[ "$mode" == "pixel" ]]; then
        if pid=$(check_pidfile_proc "$fillet_pidfile" "corner-fillet"); then
            kill "$pid" 2>/dev/null || true
        fi
    else
        if ! check_pidfile_proc "$fillet_pidfile" "corner-fillet" >/dev/null; then
            if command -v hyprctl >/dev/null 2>&1; then
                hyprctl dispatch "hl.dsp.exec_cmd('$REPO/hypr/scripts/corner-fillet.py')" >/dev/null 2>&1 || true
            fi
        fi
    fi

    # 2. Ô nhạc media-pill (khởi động lại nếu đang chạy để nhận kiểu vẽ mới)
    if pid=$(check_pidfile_proc "$media_pidfile" "media-pill"); then
        kill "$pid" 2>/dev/null || true
        local i=0
        while (( i < 20 )); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.1
            (( i++ ))
        done
        if command -v hyprctl >/dev/null 2>&1; then
            hyprctl dispatch "hl.dsp.exec_cmd('$REPO/hypr/scripts/media-pill.py')" >/dev/null 2>&1 || true
        fi
    fi

    # 2b. Popup tiện ích (chạy nền, CSS pixel chỉ nạp lúc khởi động) → khởi động lại nếu đang chạy
    if pid=$(check_pidfile_proc "$runtime_dir/kafka-tools-popup.pid" "tools-popup"); then
        kill "$pid" 2>/dev/null || true
        sleep 0.3
        command -v hyprctl >/dev/null 2>&1 && \
            hyprctl dispatch "hl.dsp.exec_cmd('$REPO/hypr/scripts/tools-popup.py')" >/dev/null 2>&1 || true
    fi

    # 3. dunst nạp lại cấu hình (đọc dunstrc.d/), walker khởi động lại dịch vụ (CSS chỉ nạp lúc chạy)
    command -v dunstctl >/dev/null 2>&1 && dunstctl reload >/dev/null 2>&1 || true
    if pgrep -x walker >/dev/null 2>&1; then
        local wp
        for wp in $(pgrep -x walker); do kill "$wp" 2>/dev/null || true; done
        sleep 0.3
        command -v hyprctl >/dev/null 2>&1 && \
            hyprctl dispatch "hl.dsp.exec_cmd('walker --gapplication-service')" >/dev/null 2>&1 || true
    fi

    # 4. Thông báo Dunst
    if command -v notify-send >/dev/null 2>&1; then
        if [[ "$mode" == "pixel" ]]; then
            notify-send -a "Giao diện" "Giao diện: Pixel" "Super + Alt + U để đổi lại" 2>/dev/null || true
        else
            notify-send -a "Giao diện" "Giao diện: Phẳng" "Super + Alt + U để đổi lại" 2>/dev/null || true
        fi
    fi
}

# Chuyển sang chế độ chỉ định ("flat" hoặc "pixel")
set_mode() {
    local mode="$1"
    mkdir -p "$STATE_DIR"
    write_theme_css "$mode"
    atomic_write "$STATE" "$mode"
    apply_side_effects "$mode"
}

# Tự kiểm tra toàn bộ luồng trong thư mục tạm cô lập
run_selftest() {
    local tmp
    tmp=$(mktemp -d) || {
        printf 'FAIL: không tạo được thư mục tạm\n' >&2
        return 1
    }
    mkdir -p "$tmp/waybar" "$tmp/state"

    local fails=0
    local out=""
    local css="$tmp/waybar/theme.css"

    check() {
        local desc="$1"
        local cond="$2"
        if [[ "$cond" == "ok" ]]; then
            printf 'PASS: %s\n' "$desc"
        else
            printf 'FAIL: %s\n' "$desc"
            (( fails++ ))
        fi
    }

    # 1. Mặc định khi chưa có state -> status phải là flat
    out=$(KAFKA_UI_TEST_REPO="$tmp" XDG_STATE_HOME="$tmp/state" KAFKA_UI_NO_SIDE_EFFECTS=1 bash "$0" status)
    if [[ "$out" == "flat" ]]; then
        check "status mặc định là flat" "ok"
    else
        check "status mặc định là flat (nhận: $out)" "fail"
    fi

    # 2. Chuyển sang pixel
    KAFKA_UI_TEST_REPO="$tmp" XDG_STATE_HOME="$tmp/state" KAFKA_UI_NO_SIDE_EFFECTS=1 bash "$0" pixel
    if [[ -f "$css" ]] && grep -q '@import "theme-pixel.css";' "$css" && grep -qF "$HEADER_COMMENT" "$css"; then
        check "pixel tạo theme.css có @import theme-pixel.css" "ok"
    else
        check "pixel tạo theme.css có @import theme-pixel.css" "fail"
    fi

    # 3. Kiểm tra status sau khi đặt pixel
    out=$(KAFKA_UI_TEST_REPO="$tmp" XDG_STATE_HOME="$tmp/state" KAFKA_UI_NO_SIDE_EFFECTS=1 bash "$0" status)
    if [[ "$out" == "pixel" ]]; then
        check "status sau pixel là pixel" "ok"
    else
        check "status sau pixel là pixel (nhận: $out)" "fail"
    fi

    # 4. Toggle từ pixel -> flat
    KAFKA_UI_TEST_REPO="$tmp" XDG_STATE_HOME="$tmp/state" KAFKA_UI_NO_SIDE_EFFECTS=1 bash "$0" toggle
    if [[ -f "$css" ]] && ! grep -q '@import "theme-pixel.css";' "$css" && grep -qF "$HEADER_COMMENT" "$css"; then
        check "toggle sang flat bỏ @import khỏi theme.css" "ok"
    else
        check "toggle sang flat bỏ @import khỏi theme.css" "fail"
    fi

    # 5. Kiểm tra status sau khi toggle
    out=$(KAFKA_UI_TEST_REPO="$tmp" XDG_STATE_HOME="$tmp/state" KAFKA_UI_NO_SIDE_EFFECTS=1 bash "$0" status)
    if [[ "$out" == "flat" ]]; then
        check "status sau toggle là flat" "ok"
    else
        check "status sau toggle là flat (nhận: $out)" "fail"
    fi

    # 6. Xoá theme.css và kiểm tra ensure với state=flat
    rm -f "$css"
    KAFKA_UI_TEST_REPO="$tmp" XDG_STATE_HOME="$tmp/state" KAFKA_UI_NO_SIDE_EFFECTS=1 bash "$0" ensure
    if [[ -f "$css" ]] && ! grep -q '@import "theme-pixel.css";' "$css" && grep -qF "$HEADER_COMMENT" "$css"; then
        check "ensure tạo lại theme.css theo state=flat" "ok"
    else
        check "ensure tạo lại theme.css theo state=flat" "fail"
    fi

    # 7. Đặt pixel, xoá theme.css và kiểm tra ensure với state=pixel
    KAFKA_UI_TEST_REPO="$tmp" XDG_STATE_HOME="$tmp/state" KAFKA_UI_NO_SIDE_EFFECTS=1 bash "$0" pixel
    rm -f "$css"
    KAFKA_UI_TEST_REPO="$tmp" XDG_STATE_HOME="$tmp/state" KAFKA_UI_NO_SIDE_EFFECTS=1 bash "$0" ensure
    if [[ -f "$css" ]] && grep -q '@import "theme-pixel.css";' "$css"; then
        check "ensure tạo lại theme.css theo state=pixel" "ok"
    else
        check "ensure tạo lại theme.css theo state=pixel" "fail"
    fi

    rm -rf "$tmp"
    (( fails == 0 ))
}

cmd="${1:-}"
case "$cmd" in
    pixel)
        set_mode "pixel"
        ;;
    flat)
        set_mode "flat"
        ;;
    toggle)
        current=$(get_status)
        if [[ "$current" == "pixel" ]]; then
            set_mode "flat"
        else
            set_mode "pixel"
        fi
        ;;
    status)
        get_status
        ;;
    ensure)
        mkdir -p "$STATE_DIR"
        if [[ ! -e "$THEME_CSS" || ! -e "$ROFI_CSS" || ! -e "$WALKER_CSS" ]]; then
            current=$(get_status)
            write_theme_css "$current"
        fi
        ;;
    --selftest)
        run_selftest
        ;;
    *)
        usage
        ;;
esac
