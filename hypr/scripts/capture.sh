#!/usr/bin/env bash
# Chụp ảnh, chú thích và quay màn hình cho Hyprland.
# Trạng thái quay được giữ trong XDG_RUNTIME_DIR để Waybar và script dùng chung.

set -u

runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
state_file="$runtime_dir/kafka-rec.state"
log_file="$runtime_dir/kafka-rec.log"
screenshots_dir="$HOME/Pictures/Screenshots"
recordings_dir="$HOME/Videos/Recordings"
theme="$HOME/.config/rofi/kafka-actions.rasi"

pid=""
video_file=""
modules=""
start_epoch=""

load_state() {
    pid=""
    video_file=""
    modules=""
    start_epoch=""

    [[ -r "$state_file" ]] || return 1
    while IFS='=' read -r key value; do
        case "$key" in
            PID) pid="$value" ;;
            FILE) video_file="$value" ;;
            MODULES) modules="$value" ;;
            START) start_epoch="$value" ;;
        esac
    done < "$state_file"
    [[ -n "$pid" && -n "$video_file" && -n "$start_epoch" ]]
}

recording_alive() {
    load_state && kill -0 "$pid" 2>/dev/null
}

remove_modules() {
    local module_id
    for module_id in $modules; do
        [[ "$module_id" =~ ^[0-9]+$ ]] && pactl unload-module "$module_id" >/dev/null 2>&1 || true
    done
}

clear_state() {
    rm -f -- "$state_file"
}

notify_error() {
    local details
    details=$(tail -n 3 "$log_file" 2>/dev/null || true)
    notify-send "Không thể quay màn hình" "${details:-wf-recorder đã dừng ngay sau khi khởi động.}" >/dev/null 2>&1 || true
}

json_status() {
    local text class tooltip

    if ! recording_alive; then
        # State cũ sót lại sau khi tiến trình chết không được coi là đang quay.
        if [[ -f "$state_file" ]]; then
            remove_modules
            clear_state
        fi
        python3 -c 'import json; print(json.dumps({"text": "󰄀", "class": "idle", "tooltip": "Chụp / quay màn hình\nBấm: mở menu · Chuột phải: chụp vùng"}, ensure_ascii=False))'
        return 0
    fi

    # Waybar chỉ hỏi lại mỗi 30s (và khi nhận signal 12), nên không hiện bộ đếm giây
    # (sẽ đứng yên); hiện icon đỏ, giờ bắt đầu nằm trong tooltip.
    text="󰑋"
    class="recording"
    tooltip=$(printf 'Đang quay từ %s: %s\nBấm để dừng (hoặc Super + Shift + R)' "$(date -d "@$start_epoch" +%H:%M:%S)" "${video_file##*/}")
    python3 - "$text" "$class" "$tooltip" <<'PY'
import json
import sys
print(json.dumps({"text": sys.argv[1], "class": sys.argv[2], "tooltip": sys.argv[3]}, ensure_ascii=False))
PY
}

item() { # item <icon> <màu> <nhãn>
    printf "<span font='FiraCode Nerd Font Propo 26' foreground='%s'>%s</span>\n<span size='10pt'>%s</span>" "$2" "$1" "$3"
}

show_menu() {
    if recording_alive; then
        stop_recording
        return $?
    fi
    if pidof rofi >/dev/null 2>&1; then
        pkill -x rofi >/dev/null 2>&1 || true
        return 0
    fi

    local entries choice
    entries="$(item $'\U000f0e51' '#c77dff' 'Toàn màn hình')"
    entries+="|$(item $'\U000f05b2' '#d4af6a' 'Cửa sổ')"
    entries+="|$(item $'\U000f019f' '#a8e6cf' 'Vùng')"
    entries+="|$(item $'\U000f0f49' '#7cc4ff' 'Vùng + vẽ')"
    entries+="|$(item $'\U000f0ec2' '#ff4d6d' 'Quay màn hình')"
    entries+="|$(item $'\U000f0567' '#ff7aa2' 'Quay vùng')"

    choice=$(printf '%s' "$entries" | rofi -dmenu -i -markup-rows -sep '|' -eh 3 \
        -format i -no-custom -p "" -theme "$theme" \
        -theme-str 'listview { columns: 6; } mainbox { children: [ "panel", "pad-top" ]; } panel { margin: 190px 98px 0px calc( 100% - 868px ); }') || true
    [[ -n "$choice" ]] || return 0
    sleep 0.2

    case "$choice" in
        0) capture_image full ;;
        1) capture_image window ;;
        2) capture_image region ;;
        3) edit_image ;;
        4) start_recording full ;;
        5) start_recording region ;;
    esac
}

capture_image() {
    local mode="$1"
    mkdir -p -- "$screenshots_dir" || return 1
    if [[ "$mode" == "full" ]]; then
        hyprshot -m output -m active -o "$screenshots_dir" -f "${mode}_$(date +%Y%m%d_%H%M%S).png"
    else
        hyprshot -m "$mode" -o "$screenshots_dir" -f "${mode}_$(date +%Y%m%d_%H%M%S).png"
    fi
}

edit_image() {
    local output="$screenshots_dir/edit_$(date +%Y%m%d_%H%M%S).png"
    local raw_status satty_status=0 raw_file="$runtime_dir/kafka-capture-raw-$$.png"
    mkdir -p -- "$screenshots_dir" || return 1

    set +e
    hyprshot -m region --raw >"$raw_file"
    raw_status=$?
    if (( raw_status == 0 )) && [[ -s "$raw_file" ]]; then
        satty --filename "$raw_file" --output-filename "$output" \
        --copy-command wl-copy --early-exit
        satty_status=$?
    fi
    rm -f -- "$raw_file"
    set -u
    # hyprshot trả lỗi khi người dùng hủy; satty không được mở trong trường hợp đó.
    if (( raw_status != 0 || satty_status != 0 )); then
        rm -f -- "$output"
        return "$satty_status"
    fi
}

choose_audio() {
    local entries choice
    entries="$(item $'\U000f075f' '#a99bbd' 'Không tiếng')"
    entries+="|$(item $'\U000f057e' '#c77dff' 'Tiếng máy')"
    entries+="|$(item $'\U000f036c' '#d4af6a' 'Máy + micro')"
    choice=$(printf '%s' "$entries" | rofi -dmenu -i -markup-rows -sep '|' -eh 3 \
        -format i -no-custom -p "" -theme "$theme" \
        -theme-str 'listview { columns: 3; } mainbox { children: [ "panel", "pad-top" ]; } panel { margin: 190px 98px 0px calc( 100% - 488px ); }') || true
    printf '%s' "$choice"
}

start_recording() {
    local mode="$1" audio_choice geometry output_name monitor source
    local null_id loop_sink_id loop_mic_id recorder_pid

    recording_alive && { stop_recording; return 0; }
    audio_choice=$(choose_audio)
    [[ -n "$audio_choice" ]] || return 0

    if [[ "$mode" == "region" ]]; then
        geometry=$(slurp 2>/dev/null) || return 0
        [[ -n "$geometry" ]] || return 0
    else
        monitor=$(hyprctl monitors -j 2>/dev/null | python3 -c 'import json,sys
try:
    print(next(m["name"] for m in json.load(sys.stdin) if m.get("focused") is True))
except (StopIteration, KeyError, TypeError, json.JSONDecodeError):
    pass')
        [[ -n "$monitor" ]] || return 1
    fi

    mkdir -p -- "$recordings_dir" || return 1
    output_name="$recordings_dir/rec_$(date +%Y%m%d_%H%M%S).mp4"
    modules=""
    case "$audio_choice" in
        1) source=$(pactl get-default-sink).monitor
           audio_args=("--audio=$source") ;;
        2) source=$(pactl get-default-sink).monitor
           null_id=$(pactl load-module module-null-sink sink_name=kafka_rec_mix sink_properties=device.description=KafkaRecMix) || return 1
           loop_sink_id=$(pactl load-module module-loopback source="$source" sink=kafka_rec_mix latency_msec=20) || { pactl unload-module "$null_id" >/dev/null 2>&1 || true; return 1; }
           loop_mic_id=$(pactl load-module module-loopback source="$(pactl get-default-source)" sink=kafka_rec_mix latency_msec=20) || { pactl unload-module "$loop_sink_id" >/dev/null 2>&1 || true; pactl unload-module "$null_id" >/dev/null 2>&1 || true; return 1; }
           modules="$null_id $loop_sink_id $loop_mic_id"
           audio_args=("--audio=kafka_rec_mix.monitor") ;;
        *) audio_args=() ;;
    esac

    if [[ "$mode" == "region" ]]; then
        setsid wf-recorder -f "$output_name" -g "$geometry" "${audio_args[@]}" \
            -c libx264 -p preset=veryfast -p crf=23 >"$log_file" 2>&1 &
    else
        setsid wf-recorder -f "$output_name" -o "$monitor" "${audio_args[@]}" \
            -c libx264 -p preset=veryfast -p crf=23 >"$log_file" 2>&1 &
    fi
    recorder_pid=$!
    video_file="$output_name"
    start_epoch=$(date +%s)
    printf 'PID=%s\nFILE=%s\nMODULES=%s\nSTART=%s\n' "$recorder_pid" "$video_file" "$modules" "$start_epoch" >"$state_file"

    sleep 0.5
    if ! kill -0 "$recorder_pid" 2>/dev/null; then
        remove_modules
        clear_state
        notify_error
        return 1
    fi
    notify-send "Đang quay" "Bấm nút chụp trên dock hoặc Super + Shift + R để dừng" >/dev/null 2>&1 || true
    pkill -RTMIN+12 waybar >/dev/null 2>&1 || true
}

stop_recording() {
    local elapsed minutes seconds waited=0
    load_state || { clear_state; return 0; }
    if kill -0 "$pid" 2>/dev/null; then
        kill -INT "$pid" 2>/dev/null || true
        while kill -0 "$pid" 2>/dev/null && (( waited < 25 )); do
            sleep 0.2
            waited=$((waited + 1))
        done
        kill -TERM "$pid" 2>/dev/null || true
    fi
    remove_modules
    elapsed=$(( $(date +%s) - start_epoch ))
    (( elapsed < 0 )) && elapsed=0
    minutes=$((elapsed / 60))
    seconds=$((elapsed % 60))
    clear_state
    pkill -RTMIN+12 waybar >/dev/null 2>&1 || true
    notify-send "Đã lưu video" "${video_file/#$HOME/\~}"$'\n'"Thời lượng: $(printf '%02d:%02d' "$minutes" "$seconds")" >/dev/null 2>&1 || true
}

usage() {
    printf '%s\n' 'Dùng: capture.sh menu | full | window | region | edit | rec full | rec region | stop | status' >&2
}

case "${1:-}" in
    menu) show_menu ;;
    full|window|region) capture_image "$1" ;;
    edit) edit_image ;;
    rec) [[ "${2:-}" == "full" || "${2:-}" == "region" ]] && start_recording "$2" || { usage; exit 2; } ;;
    stop) stop_recording ;;
    status) json_status ;;
    *) usage; exit 2 ;;
esac
