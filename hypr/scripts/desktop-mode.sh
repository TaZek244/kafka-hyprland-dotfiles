#!/usr/bin/env bash
# Chuyển toàn bộ màn hình giữa chế độ cuộn và chế độ Desktop tự do.
# Phím Super + D, nút trên thanh trên (custom/layoutmode, signal 14). Hàm kafka_desktop() nằm trong hyprland.lua.

set -u

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/kafka"
state_file="$state_dir/layout-mode"
runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
prefloat_file="$runtime_dir/kafka-desktop-prefloat"
lock_file="$runtime_dir/kafka-desktop-mode.lock"

current_mode() {
    local mode="scroll"
    if [[ -r "$state_file" ]]; then
        IFS= read -r mode <"$state_file" || true
    fi
    [[ "$mode" == desktop ]] && printf 'desktop\n' || printf 'scroll\n'
}

write_mode() {
    mkdir -p -- "$state_dir" || return 1
    printf '%s\n' "$1" >"$state_file"
}

hyprland_ready() {
    command -v hyprctl >/dev/null 2>&1 && [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]
}

usage() {
    printf '%s\n' 'Dùng: desktop-mode.sh toggle | on | off | status | apply | --selftest' >&2
}

status() {
    local mode text tooltip
    mode=$(current_mode)
    if [[ "$mode" == desktop ]]; then
        text=$'\U0000f108'
        tooltip=$'Chế độ Desktop (cửa sổ tự do)\nBấm: chuyển sang cuộn · Super + D'
    else
        text=$'\U000f0db'
        tooltip=$'Chế độ cuộn (cột)\nBấm: chuyển sang Desktop · Super + D'
    fi
    jq -cn --arg text "$text" --arg alt "$mode" --arg tooltip "$tooltip" \
        '{text:$text,alt:$alt,class:$alt,tooltip:$tooltip}'
}

# Tính hình chữ nhật hợp lệ cho cửa sổ, có xét phần màn hình dành cho Waybar.
geometry() {
    local client_json="$1" monitor_json="$2" cascade="$3"
    jq -r --argjson k "$cascade" --argjson c "$client_json" --argjson m "$monitor_json" '
        def n: (tonumber | floor);
        ($m.scale // 1) as $scale |
        (($m.x // 0) + (($m.reserved[0] // 0) | n)) as $ux |
        (($m.y // 0) + (($m.reserved[1] // 0) | n)) as $uy |
        (($m.width / $scale - (($m.reserved[0] // 0) + ($m.reserved[2] // 0))) | n) as $uw |
        (($m.height / $scale - (($m.reserved[1] // 0) + ($m.reserved[3] // 0))) | n) as $uh |
        ($c.at[0] // 0) as $cx | ($c.at[1] // 0) as $cy |
        ($c.size[0] // 0) as $cw | ($c.size[1] // 0) as $ch |
        if ($cx >= $ux and $cy >= $uy and $cx + $cw <= $ux + $uw and $cy + $ch <= $uy + $uh)
        then [($cx|n), ($cy|n), ($cw|n), ($ch|n)] | @tsv
        else
            (($uw * 60 / 100)|n) as $w | (($uh * 65 / 100)|n) as $h |
            [(($ux + (($uw - $w) / 2) + (32 * $k))|n),
             (($uy + (($uh - $h) / 2) + (32 * $k))|n), $w, $h] | @tsv
        end
    ' <<<'{}'
}

monitor_for() {
    local monitor_id="$1" monitors_json="$2"
    jq -c --argjson id "$monitor_id" 'map(select(.id == $id))[0] // {}' <<<"$monitors_json"
}

on_mode() {
    local clients monitors client address monitor geometry_values x y w h k=0
    if [[ "$(current_mode)" == desktop ]]; then
        hyprctl eval 'kafka_desktop(true)' >/dev/null || return 1
        return 0
    fi
    mkdir -p -- "$runtime_dir" || return 1
    clients=$(hyprctl clients -j) || return 1
    monitors=$(hyprctl monitors -j) || return 1
    jq -r '.[] | select(.workspace.id > 0 and .floating == true) | .address' <<<"$clients" >"$prefloat_file" || return 1
    write_mode desktop || return 1
    hyprctl eval 'kafka_desktop(true)' >/dev/null || return 1

    while IFS= read -r client; do
        address=$(jq -r '.address' <<<"$client")
        monitor=$(monitor_for "$(jq -r '.monitor' <<<"$client")" "$monitors")
        geometry_values=$(geometry "$client" "$monitor" "$k")
        read -r x y w h <<<"$geometry_values"
        hyprctl --batch "dispatch hl.dsp.window.float({ action = 'enable', window = 'address:$address' }); dispatch hl.dsp.window.resize({ x = $w, y = $h, relative = false, window = 'address:$address' }); dispatch hl.dsp.window.move({ x = $x, y = $y, relative = false, window = 'address:$address' })" >/dev/null || true
        k=$(((k + 1) % 8))
    done < <(jq -c '.[] | select(.workspace.id > 0 and .floating == false)' <<<"$clients")
    # Thu/đẩy mọi cửa sổ nổi vào trong vùng nội dung (chừa Waybar, lề 12px) — hàm trong hyprland.lua
    hyprctl eval 'kafka_fit_all_floats()' >/dev/null 2>&1 || true
    pkill -RTMIN+14 waybar >/dev/null 2>&1 || true
    notify-send -a 'Kafka' -i preferences-desktop 'Chế độ Desktop' 'Cửa sổ tự do — kéo bằng Super + chuột trái' >/dev/null 2>&1 || true
}

off_mode() {
    local clients client address class title
    [[ "$(current_mode)" == scroll ]] && return 0
    write_mode scroll || return 1
    hyprctl eval 'kafka_desktop(false)' >/dev/null || return 1
    clients=$(hyprctl clients -j) || return 1
    while IFS= read -r client; do
        address=$(jq -r '.address' <<<"$client")
        class=$(jq -r '.class // ""' <<<"$client")
        title=$(jq -r '.title // ""' <<<"$client")
        [[ -f "$prefloat_file" ]] && grep -Fqx -- "$address" "$prefloat_file" && continue
        [[ "$class" =~ ^(org\.pulseaudio\.pavucontrol|pavucontrol|nm-connection-editor|blueman-manager|kafka\.keybinds|kafka\.studio|kafka-btop|com\.gabm\.satty|kafka-cava|kafka-nmtui)$ ]] && continue
        [[ "$title" =~ ^(Open\ File|Save\ File|Confirm)$ ]] && continue
        hyprctl --batch "dispatch hl.dsp.window.float({ action = 'disable', window = 'address:$address' })" >/dev/null || true
    done < <(jq -c '.[] | select(.workspace.id > 0 and .floating == true and .pinned == false)' <<<"$clients")
    rm -f -- "$prefloat_file"
    pkill -RTMIN+14 waybar >/dev/null 2>&1 || true
    notify-send 'Chế độ cuộn' 'Cửa sổ xếp thành cột' >/dev/null 2>&1 || true
}

selftest() {
    local inside outside expected_inside expected_outside
    inside=$(geometry '{"at":[120,80],"size":[400,300]}' '{"x":0,"y":0,"width":1920,"height":1080,"scale":1,"reserved":[0,48,74,0]}' 0)
    outside=$(geometry '{"at":[-20,20],"size":[2200,1200]}' '{"x":0,"y":0,"width":1920,"height":1080,"scale":1,"reserved":[0,48,74,0]}' 1)
    expected_inside=$'120\t80\t400\t300'
    expected_outside=$'401\t261\t1107\t670'
    if [[ "$inside" == "$expected_inside" && "$outside" == "$expected_outside" ]]; then
        printf 'PASS\n'
        return 0
    fi
    printf 'FAIL\n'
    printf 'inside: %s\noutside: %s\n' "$inside" "$outside" >&2
    return 1
}

command=${1:-}
if [[ "$command" == --selftest ]]; then
    selftest
    exit $?
fi
case "$command" in
    on | off | toggle | status | apply) ;;
    *)
        usage
        exit 2
        ;;
esac
if [[ "$command" == status ]]; then
    status
    exit 0
fi
if ! hyprland_ready; then
    printf '%s\n' 'Hyprland hoặc hyprctl không khả dụng.' >&2
    exit 1
fi
if [[ "$command" != apply ]]; then
    exec 9>"$lock_file"
    flock -n 9 || {
        printf '%s\n' 'Thao tác khác đang chạy.' >&2
        exit 1
    }
fi
case "$command" in
    on) on_mode ;;
    off) off_mode ;;
    toggle) if [[ "$(current_mode)" == scroll ]]; then on_mode; else off_mode; fi ;;
    apply) [[ "$(current_mode)" == desktop ]] && hyprctl eval 'kafka_desktop(true)' >/dev/null ;;
    *)
        usage
        exit 2
        ;;
esac
