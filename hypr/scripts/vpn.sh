#!/usr/bin/env bash
# vpn.sh : nút VPN trên Waybar (custom/vpn, signal 16) — bật/tắt VPN để vào các trang chặn IP Việt Nam.
#
# Hai backend: Cloudflare WARP = VPN "có sẵn" dùng chung (mặc định khi chưa chọn), NetworkManager = VPN tự cài:
#   A. NetworkManager: chỉ xét kết nối kiểu 'wireguard' hoặc 'vpn'. Tên kết nối đang dùng được lưu ở
#      ${XDG_STATE_HOME:-$HOME/.local/state}/kafka/vpn-connection (1 dòng); chưa chọn thì lấy kết nối đầu tiên.
#      Lưu ý: nmcli -t escape dấu ':' trong NAME thành '\:' (và '\' thành '\\') → phải giải mã trước khi dùng.
#   B. Cloudflare WARP: dùng khi có warp-cli và chưa chọn kết nối NM nào (hoặc file chọn ghi 'warp').
#      "warp-cli status" chứa "Connected" là đang bật (chú ý "Disconnected" không được tính là bật).
#
# Không gọi mạng ngoài: script chỉ hỏi trạng thái/điều khiển backend có sẵn. Sau mọi lệnh đổi trạng
# thái (toggle/up/down/import/select) bắn pkill -RTMIN+16 waybar để nút cập nhật ngay (bỏ qua lúc selftest).
#
# Lệnh:
#   vpn.sh status              in MỘT dòng JSON cho Waybar (text/class/tooltip)
#   vpn.sh toggle              bật nếu đang tắt, tắt nếu đang bật
#   vpn.sh up | down           bật / tắt một chiều
#   vpn.sh import <file.conf>  nhập file WireGuard, tắt autoconnect rồi chọn kết nối đó
#   vpn.sh list                liệt kê kết nối (dấu * = đang chọn), có cả 'warp' nếu có warp-cli
#   vpn.sh select [tên]        ghi tên vào file chọn; không có tên thì mở rofi để chọn
#   vpn.sh --selftest          thử logic với nmcli/warp giả, không cần NetworkManager thật

ICON='󰖂'

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/kafka"
SELECT_FILE="$STATE_DIR/vpn-connection"

# Có thể thay bằng script giả khi chạy --selftest.
nmcli_bin=${KAFKA_VPN_NMCLI:-nmcli}
warp_bin=${KAFKA_VPN_WARP:-warp-cli}
IN_SELFTEST=0

refresh() {
    ((IN_SELFTEST)) && return 0
    pkill -RTMIN+16 waybar 2>/dev/null || true
}

notify() {
    ((IN_SELFTEST)) && {
        printf '%s\n' "$*" >>"${KAFKA_VPN_NOTIFY_LOG:-/dev/null}"
        return 0
    }
    command -v notify-send >/dev/null 2>&1 && notify-send -a "Kafka" "$@" >/dev/null 2>&1
    return 0
}

# json_escape : thoát \, ", xuống dòng... để tooltip luôn là JSON hợp lệ.
json_escape() {
    local s=$1 out="" i ch
    for ((i = 0; i < ${#s}; i++)); do
        ch=${s:i:1}
        case $ch in
            "\\") out+='\\' ;;
            '"') out+='\"' ;;
            $'\n') out+='\n' ;;
            $'\r') out+='\r' ;;
            $'\t') out+='\t' ;;
            *) out+=$ch ;;
        esac
    done
    printf '%s' "$out"
}

# parse_line : tách dòng "NAME:TYPE:ACTIVE:STATE" của nmcli -t, giải mã '\:' và '\\' trong NAME.
parse_line() {
    local line=$1 i ch esc=0 name="" rest=""
    for ((i = 0; i < ${#line}; i++)); do
        ch=${line:i:1}
        if ((esc)); then
            name+=$ch
            esc=0
            continue
        fi
        case $ch in
            "\\") esc=1 ;;
            ':')
                rest=${line:i+1}
                break
                ;;
            *) name+=$ch ;;
        esac
    done
    V_NAME=$name
    IFS=: read -r V_TYPE V_ACTIVE V_STATE <<<"$rest"
    V_TYPE=${V_TYPE,,}
    V_ACTIVE=${V_ACTIVE,,}
    V_STATE=${V_STATE,,}
    [[ -z $V_STATE ]] && { [[ $V_ACTIVE == yes ]] && V_STATE=activated || V_STATE=deactivated; }
}

# Chỉ giữ wireguard/vpn. Mỗi phần tử: name<TAB>type<TAB>active<TAB>state.
load_connections() {
    CONNS=()
    local line
    while IFS= read -r line; do
        [[ -z $line ]] && continue
        parse_line "$line"
        [[ $V_TYPE == wireguard || $V_TYPE == vpn ]] || continue
        CONNS+=("$V_NAME"$'\t'"$V_TYPE"$'\t'"$V_ACTIVE"$'\t'"$V_STATE")
    done < <("$nmcli_bin" -t -f NAME,TYPE,ACTIVE,STATE connection show 2>/dev/null)
}

state_class() { # <active> <state> -> on | connecting | off
    local active=$1 state=$2
    case $state in
        activated) printf 'on' ;;
        activating) printf 'connecting' ;;
        *) [[ $active == yes ]] && printf 'on' || printf 'off' ;;
    esac
}

warp_available() { command -v "$warp_bin" >/dev/null 2>&1; }
# warp-cli đòi --accept-tos khi không chạy trong terminal (Waybar, notify...) → luôn truyền cờ này
warp_run() { "$warp_bin" --accept-tos "$@"; }

warp_state() {
    local out
    out=$(warp_run status 2>/dev/null) || {
        printf 'off'
        return
    }
    if [[ $out == *Connected* ]]; then
        printf 'on'
    elif [[ $out == *Connecting* ]]; then
        printf 'connecting'
    else printf 'off'; fi
}

selected_name() {
    local sel=""
    [[ -r $SELECT_FILE ]] && { IFS= read -r sel <"$SELECT_FILE" || true; }
    printf '%s' "$sel"
}

write_selection() {
    mkdir -p -- "$STATE_DIR" || return 1
    printf '%s\n' "$1" >"$SELECT_FILE"
}

# Xác định backend: BACKEND = nm | warp | none, kèm BACK_NAME / BACK_STATE.
resolve() {
    load_connections
    local sel entry name type active state
    sel=$(selected_name)

    if [[ -n $sel && $sel != warp ]]; then
        for entry in "${CONNS[@]}"; do
            IFS=$'\t' read -r name type active state <<<"$entry"
            if [[ $name == "$sel" ]]; then
                BACKEND=nm
                BACK_NAME=$name
                BACK_STATE=$(state_class "$active" "$state")
                return 0
            fi
        done
    fi
    if [[ $sel == warp ]] && warp_available; then
        BACKEND=warp
        BACK_NAME="Cloudflare WARP"
        BACK_STATE=$(warp_state)
        return 0
    fi
    # Chưa chọn: WARP là VPN "có sẵn" dùng chung → ưu tiên; VPN tự cài (NM) chỉ khi không có WARP
    if warp_available; then
        BACKEND=warp
        BACK_NAME="Cloudflare WARP"
        BACK_STATE=$(warp_state)
        return 0
    fi
    if ((${#CONNS[@]})); then
        IFS=$'\t' read -r name type active state <<<"${CONNS[0]}"
        BACKEND=nm
        BACK_NAME=$name
        BACK_STATE=$(state_class "$active" "$state")
        return 0
    fi
    BACKEND=none
    BACK_NAME=""
    BACK_STATE=none
}

cmd_status() {
    resolve
    local label tooltip cls=$BACK_STATE
    case $BACK_STATE in
        on) label='Đang bật' ;;
        connecting) label='Đang kết nối…' ;;
        off) label='Đang tắt' ;;
        *) label='' ;;
    esac
    if [[ $BACKEND == none ]]; then
        cls=none
        tooltip='Chưa có VPN. Cài WARP: Arch: yay -S cloudflare-warp-bin, Ubuntu: kho apt pkg.cloudflareclient.com (xem README) hoặc nhập file WireGuard: vpn.sh import <file.conf>'
    else
        tooltip=$(printf '%s — %s\nTrái: bật/tắt · Phải: chọn kết nối' "$BACK_NAME" "$label")
    fi
    printf '{"text":"%s","class":"%s","tooltip":"%s"}\n' \
        "$(json_escape "$ICON")" "$cls" "$(json_escape "$tooltip")"
}

change_state() {
    local want=$1 rc=0 out action=$1
    resolve
    if [[ $BACKEND == none ]]; then
        notify "Chưa có VPN" "Nhập file WireGuard: vpn.sh import <file.conf>"
        refresh
        return 0
    fi

    if [[ $want == toggle ]]; then
        if [[ $BACK_STATE == on || $BACK_STATE == connecting ]]; then action=down; else action=up; fi
    fi
    # Đúng trạng thái đích thì khỏi gọi backend (warp-cli connect lặp dễ báo lỗi).
    if [[ $action == up && ($BACK_STATE == on || $BACK_STATE == connecting) ]] ||
        [[ $action == down && $BACK_STATE == off ]]; then
        refresh
        return 0
    fi

    if [[ $BACKEND == warp ]]; then
        # warp-cli dùng connect/disconnect, không phải up/down
        out=$(warp_run "$([[ $action == up ]] && echo connect || echo disconnect)" 2>&1)
        rc=$?
    else
        out=$("$nmcli_bin" connection "$action" id "$BACK_NAME" 2>&1)
        rc=$?
    fi
    if ((rc != 0)); then
        notify -u critical "VPN: lỗi $action" "$out"
    elif [[ $action == up ]]; then
        notify "VPN đã bật" "$BACK_NAME"
    fi
    refresh
    return $rc
}

cmd_toggle() { change_state toggle; }
cmd_up() { change_state up; }
cmd_down() { change_state down; }

cmd_import() {
    local file=$1 out rc=0 name
    if [[ -z $file || ! -f $file ]]; then
        printf '%s\n' "Không tìm thấy file WireGuard: $file" >&2
        refresh
        return 1
    fi
    name=${file##*/}
    name=${name%.*} # nmcli đặt tên kết nối = tên file bỏ đuôi
    out=$("$nmcli_bin" connection import type wireguard file "$file" 2>&1)
    rc=$?
    if ((rc != 0)); then
        notify -u critical "VPN: nhập file thất bại" "$out"
        refresh
        return $rc
    fi
    "$nmcli_bin" connection modify "$name" connection.autoconnect no >/dev/null 2>&1 || true
    write_selection "$name" || rc=1
    ((rc == 0)) && notify "Đã nhập cấu hình VPN" "$name"
    refresh
    return $rc
}

cmd_list() {
    load_connections
    local sel entry name type active state mark shown=0
    sel=$(selected_name)
    for entry in "${CONNS[@]}"; do
        IFS=$'\t' read -r name type active state <<<"$entry"
        [[ $name == "$sel" ]] && mark='*' || mark=' '
        printf '%s %s\t%s\t%s\n' "$mark" "$name" "$type" "$(state_class "$active" "$state")"
        shown=1
    done
    if warp_available; then
        [[ $sel == warp ]] && mark='*' || mark=' '
        printf '%s %s\t%s\t%s\n' "$mark" "warp" "warp-cli" "$(warp_state)"
        shown=1
    fi
    ((shown)) || printf '%s\n' 'Chưa có kết nối VPN nào. Nhập file WireGuard: vpn.sh import <file.conf>'
}

cmd_select() {
    local name=$1 rc=0 chosen entry n
    if [[ -z $name ]]; then
        load_connections
        local items=()
        for entry in "${CONNS[@]}"; do
            IFS=$'\t' read -r n _ <<<"$entry"
            items+=("$n")
        done
        warp_available && items+=("warp")
        if ((${#items[@]} == 0)); then
            notify "Chưa có VPN để chọn" "Nhập file WireGuard trước: vpn.sh import <file.conf>"
            refresh
            return 1
        fi
        if ! command -v rofi >/dev/null 2>&1; then
            notify -u critical "Không có rofi" "Không thể mở menu chọn VPN."
            refresh
            return 1
        fi
        chosen=$(printf '%s\n' "${items[@]}" | rofi -dmenu -theme "${XDG_CONFIG_HOME:-$HOME/.config}/rofi/kafka.rasi" -p VPN) || rc=1
        [[ -z $chosen ]] && rc=1
        name=$chosen
    fi
    ((rc == 0)) && { write_selection "$name" || rc=1; }
    refresh
    return $rc
}

# selftest chạy trong subshell: mọi thứ (biến, file chọn, fake) nằm trong thư mục tạm.
selftest() (
    IN_SELFTEST=1
    local tmp fake_nm fake_warp no_warp nm_out nm_log warp_log notify_log conf
    tmp=$(mktemp -d) || {
        printf 'FAIL: không tạo được thư mục tạm\n'
        return 1
    }
    trap 'rm -rf -- "$tmp"' EXIT

    fake_nm="$tmp/nmcli-gia"
    fake_warp="$tmp/warp-gia"
    no_warp="$tmp/khong-co-warp-cli"
    nm_out="$tmp/nm.out"
    nm_log="$tmp/nm.log"
    warp_log="$tmp/warp.log"
    notify_log="$tmp/notify.log"
    mkdir -p -- "$tmp/state"
    : >"$nm_out"
    : >"$nm_log"
    : >"$warp_log"
    : >"$notify_log"

    cat >"$fake_nm" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FAKE_NM_LOG:-/dev/null}"
prev=""; sub=""
for a in "$@"; do
    [[ $prev == connection ]] && { sub=$a; break; }
    prev=$a
done
case "$sub" in
    show) cat "${FAKE_NM_OUT:-/dev/null}" ;;
    up|down|import|modify) printf 'ok\n' ;;
esac
exit 0
FAKE
    cat >"$fake_warp" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FAKE_WARP_LOG:-/dev/null}"
[[ ${1:-} == --accept-tos ]] && shift
case "${1:-}" in
    status) printf '%s\n' "${FAKE_WARP_STATUS:-Disconnected}" ;;
    connect|disconnect) printf 'ok\n' ;;
esac
exit 0
FAKE
    chmod +x "$fake_nm" "$fake_warp"

    export FAKE_NM_OUT="$nm_out" FAKE_NM_LOG="$nm_log" FAKE_WARP_LOG="$warp_log" \
        KAFKA_VPN_NOTIFY_LOG="$notify_log"
    nmcli_bin=$fake_nm
    STATE_DIR="$tmp/state"
    SELECT_FILE="$STATE_DIR/vpn-connection"

    local pass=0 fail=0 out cls tip
    ok() {
        printf 'PASS: %s\n' "$1"
        pass=$((pass + 1))
    }
    bad() {
        printf 'FAIL: %s%s\n' "$1" "${2:+ — $2}"
        fail=$((fail + 1))
    }
    has() { [[ $1 == *"$2"* ]]; }
    json_ok() { printf '%s\n' "$1" | python3 -c 'import json,sys;json.loads(sys.stdin.read())' >/dev/null 2>&1; }
    jfield() { printf '%s\n' "$1" | python3 -c 'import json,sys;print(json.loads(sys.stdin.read())[sys.argv[1]])' "$2" 2>/dev/null; }
    set_nm() {
        printf '%s\n' "$1" >"$nm_out"
        : >"$nm_log"
    }
    set_warp() {
        warp_bin=$1
        export FAKE_WARP_STATUS=$2
        : >"$warp_log"
    }
    clear_sel() { rm -f -- "$SELECT_FILE"; }

    # Ca 1 — không có kết nối nào, cũng không có warp-cli
    set_nm ''
    set_warp "$no_warp" Disconnected
    clear_sel
    : >"$notify_log"
    out=$(cmd_status)
    if json_ok "$out" && [[ $(jfield "$out" class) == none ]] && has "$(jfield "$out" tooltip)" 'Chưa có VPN'; then
        ok 'status: chưa có VPN → JSON đúng, class none'
    else bad 'status: chưa có VPN' "$out"; fi
    out=$(cmd_list)
    if has "$out" 'Chưa có kết nối VPN'; then ok 'list: danh sách trống'; else bad 'list: danh sách trống' "$out"; fi
    : >"$nm_log"
    cmd_toggle >/dev/null 2>&1
    if ! grep -Eq 'connection (up|down)' "$nm_log"; then ok 'toggle: không bật/tắt gì khi chưa có VPN'; else bad 'toggle: không bật/tắt gì khi chưa có VPN'; fi
    if has "$(<"$notify_log")" 'Nhập file WireGuard'; then ok 'toggle: nhắc import'; else bad 'toggle: nhắc import'; fi

    # Ca 2 — một WireGuard đang tắt (và thêm trạng thái activating)
    set_nm 'KafkaVPN:wireguard:no:deactivated'
    set_warp "$no_warp" Disconnected
    clear_sel
    out=$(cmd_status)
    cls=$(jfield "$out" class)
    tip=$(jfield "$out" tooltip)
    if json_ok "$out" && [[ $cls == off ]] && has "$tip" KafkaVPN && has "$tip" 'Trái: bật/tắt · Phải: chọn kết nối'; then
        ok 'status: WireGuard tắt → class off'
    else bad 'status: WireGuard tắt' "$out"; fi
    out=$(cmd_list)
    if has "$out" KafkaVPN && has "$out" wireguard; then ok 'list: hiện kết nối WireGuard'; else bad 'list: hiện kết nối WireGuard' "$out"; fi
    : >"$nm_log"
    cmd_toggle >/dev/null 2>&1
    if grep -Fq 'connection up id KafkaVPN' "$nm_log"; then ok 'toggle: bật kết nối đang tắt'; else bad 'toggle: bật kết nối đang tắt'; fi
    : >"$nm_log"
    cmd_up >/dev/null 2>&1
    if grep -Fq 'connection up id KafkaVPN' "$nm_log"; then ok 'up: bật kết nối'; else bad 'up: bật kết nối'; fi
    set_nm 'KafkaVPN:wireguard:no:activating'
    out=$(cmd_status)
    if [[ $(jfield "$out" class) == connecting ]]; then ok 'status: activating → connecting'; else bad 'status: activating → connecting' "$out"; fi

    # Ca 3 — một WireGuard đang bật
    set_nm 'KafkaVPN:wireguard:yes:activated'
    set_warp "$no_warp" Disconnected
    clear_sel
    out=$(cmd_status)
    if [[ $(jfield "$out" class) == on ]] && has "$(jfield "$out" tooltip)" 'Đang bật'; then
        ok 'status: WireGuard bật → class on'
    else bad 'status: WireGuard bật' "$out"; fi
    : >"$nm_log"
    cmd_toggle >/dev/null 2>&1
    if grep -Fq 'connection down id KafkaVPN' "$nm_log"; then ok 'toggle: tắt kết nối đang bật'; else bad 'toggle: tắt kết nối đang bật'; fi
    : >"$nm_log"
    cmd_down >/dev/null 2>&1
    if grep -Fq 'connection down id KafkaVPN' "$nm_log"; then ok 'down: tắt kết nối'; else bad 'down: tắt kết nối'; fi

    # Ca 4 — tên có dấu ':' và dấu cách (nmcli -t ghi thành '\:')
    set_nm 'Kafka\: VPN\: đỏ:wireguard:no:deactivated'
    set_warp "$no_warp" Disconnected
    clear_sel
    out=$(cmd_status)
    tip=$(jfield "$out" tooltip)
    if json_ok "$out" && has "$tip" 'Kafka: VPN: đỏ'; then
        ok "status: giải mã tên có ':' và dấu cách"
    else bad "status: giải mã tên có ':' và dấu cách" "$out"; fi
    : >"$nm_log"
    cmd_toggle >/dev/null 2>&1
    if grep -Fq 'connection up id Kafka: VPN: đỏ' "$nm_log"; then ok 'toggle: dùng tên đã giải mã'; else bad 'toggle: dùng tên đã giải mã'; fi

    # Ca 4b — tên có dấu ngoặc kép và dấu '\' → vẫn phải là JSON hợp lệ
    set_nm 'Kafka "Web" \\ đỏ:wireguard:no:deactivated'
    out=$(cmd_status)
    tip=$(jfield "$out" tooltip)
    if json_ok "$out" && has "$tip" 'Kafka "Web" \ đỏ'; then
        ok 'status: escape " và \ trong JSON'
    else bad 'status: escape " và \ trong JSON' "$out"; fi

    # Ca 5 — chỉ có warp-cli
    set_nm ''
    set_warp "$fake_warp" Connected
    clear_sel
    out=$(cmd_status)
    if [[ $(jfield "$out" class) == on ]] && has "$(jfield "$out" tooltip)" WARP; then
        ok 'status: WARP Connected → on'
    else bad 'status: WARP Connected → on' "$out"; fi
    export FAKE_WARP_STATUS=Disconnected
    out=$(cmd_status)
    if [[ $(jfield "$out" class) == off ]]; then ok 'status: WARP Disconnected → off'; else bad 'status: WARP Disconnected → off' "$out"; fi
    : >"$warp_log"
    cmd_toggle >/dev/null 2>&1
    if grep -Fq connect "$warp_log"; then ok 'toggle WARP: connect'; else bad 'toggle WARP: connect'; fi
    export FAKE_WARP_STATUS=Connected
    : >"$warp_log"
    cmd_toggle >/dev/null 2>&1
    if grep -Fq disconnect "$warp_log"; then ok 'toggle WARP: disconnect'; else bad 'toggle WARP: disconnect'; fi
    # có cả WARP lẫn kết nối NM, chưa chọn → WARP (VPN có sẵn)
    set_nm 'KafkaVPN:wireguard:no:deactivated'
    clear_sel
    out=$(cmd_status)
    if has "$(jfield "$out" tooltip)" WARP; then ok 'chưa chọn + có WARP → WARP mặc định'; else bad 'chưa chọn + có WARP → WARP mặc định' "$out"; fi
    # chọn kết nối NM thì dùng NM dù có WARP
    printf 'KafkaVPN\n' >"$SELECT_FILE"
    out=$(cmd_status)
    if has "$(jfield "$out" tooltip)" KafkaVPN; then ok 'chọn VPN tự cài → dùng NM'; else bad 'chọn VPN tự cài → dùng NM' "$out"; fi
    # file chọn 'warp' được ưu tiên dù vẫn còn kết nối NM
    set_nm 'KafkaVPN:wireguard:no:deactivated'
    printf 'warp\n' >"$SELECT_FILE"
    out=$(cmd_status)
    if [[ $(jfield "$out" class) == on ]] && has "$(jfield "$out" tooltip)" WARP; then
        ok 'file chọn "warp" → ưu tiên WARP'
    else bad 'file chọn "warp" → ưu tiên WARP' "$out"; fi

    # Ca 6 — chọn kết nối / đánh dấu list / import
    set_nm $'A:wireguard:no:deactivated\nB:wireguard:yes:activated'
    set_warp "$no_warp" Disconnected
    clear_sel
    out=$(cmd_status)
    if [[ $(jfield "$out" class) == off ]] && has "$(jfield "$out" tooltip)" A; then
        ok 'chưa chọn → lấy kết nối đầu tiên'
    else bad 'chưa chọn → lấy kết nối đầu tiên' "$out"; fi
    printf 'B\n' >"$SELECT_FILE"
    out=$(cmd_status)
    if [[ $(jfield "$out" class) == on ]] && has "$(jfield "$out" tooltip)" B; then
        ok 'đã chọn → dùng tên trong file'
    else bad 'đã chọn → dùng tên trong file' "$out"; fi
    out=$(cmd_list)
    if has "$out" '* B'; then ok 'list: đánh dấu * ở kết nối đang chọn'; else bad 'list: đánh dấu *' "$out"; fi
    cmd_select A >/dev/null 2>&1
    if [[ $(<"$SELECT_FILE") == A ]]; then ok 'select <tên>: ghi file chọn'; else bad 'select <tên>: ghi file chọn'; fi
    conf="$tmp/kafka.conf"
    printf '[Interface]\n' >"$conf"
    : >"$nm_log"
    cmd_import "$conf" >/dev/null 2>&1
    if [[ $(<"$SELECT_FILE") == kafka ]]; then ok 'import: ghi tên vào file chọn'; else bad 'import: ghi tên vào file chọn'; fi
    if grep -Fq 'connection import type wireguard file' "$nm_log"; then ok 'import: gọi nmcli import'; else bad 'import: gọi nmcli import'; fi
    if grep -Fq 'connection modify kafka connection.autoconnect no' "$nm_log"; then ok 'import: tắt autoconnect'; else bad 'import: tắt autoconnect'; fi

    printf '\nTổng: %d PASS, %d FAIL\n' "$pass" "$fail"
    ((fail == 0))
)

usage() {
    printf '%s\n' 'Dùng: vpn.sh status | toggle | up | down | import <file.conf> | list | select [tên] | --selftest' >&2
}

cmd=${1:-status}
case "$cmd" in
    --selftest)
        selftest
        exit $?
        ;;
    status)
        cmd_status
        exit $?
        ;;
    toggle)
        cmd_toggle
        exit $?
        ;;
    up)
        cmd_up
        exit $?
        ;;
    down)
        cmd_down
        exit $?
        ;;
    import)
        cmd_import "${2:-}"
        exit $?
        ;;
    list)
        cmd_list
        exit $?
        ;;
    select)
        cmd_select "${2:-}"
        exit $?
        ;;
    *)
        usage
        exit 2
        ;;
esac
