#!/usr/bin/env bash
# Bản đồ cột của workspace đang xem (layout cuộn) cho Waybar: custom/columns, signal 15.
# Mỗi cột là icon app Nerd Font (theo class của cửa sổ đầu, xếp theo at[1]); n>1 thêm số nhỏ.
# Màu: hồng #e0559a = đang dùng, sáng #fbf7fd = đang thấy, mờ #9284a6 = khuất; cách 2 dấu cách.
# Toàn bộ text bọc trong span font FiraCode Nerd Font Propo; cột xếp (Desktop / trống) -> ẩn.
# Cột suy ra từ hình học: cửa sổ xếp (không nổi) cùng toạ độ x thuộc một cột; lộ < 50px coi như khuất.
# Tối đa KAFKA_COLMAP_MAX (mặc định 5) cột quanh cột đang dùng, phần còn lại ghi "‹N"/"N›".
# Thử: column-map.sh --selftest

set -u

# Icon thật được tạo bằng printf (không nhồi glyph/\u vào chuỗi jq), đưa qua --arg rồi --argjson.
icon_kitty=$(printf '\U000f018d')
icon_chromium=$(printf '\U000f02af')
icon_code=$(printf '\U000f0a1e')
icon_thunar=$(printf '\U000f024b')
icon_mousepad=$(printf '\U000f0dc8')
icon_mpv=$(printf '\U000f040a')
icon_imv=$(printf '\U000f02e9')
icon_btop=$(printf '\U000f029a')
icon_blueman=$(printf '\U000f00af')
icon_cava=$(printf '\U000f0388')
icon_default=$(printf '\U000f08c6')

ICONS=$(jq -n \
    --arg kitty "$icon_kitty" \
    --arg chromium "$icon_chromium" \
    --arg code "$icon_code" \
    --arg thunar "$icon_thunar" \
    --arg mousepad "$icon_mousepad" \
    --arg mpv "$icon_mpv" \
    --arg imv "$icon_imv" \
    --arg btop "$icon_btop" \
    --arg blueman "$icon_blueman" \
    --arg cava "$icon_cava" \
    --arg fallback "$icon_default" \
    '[
        ["kitty", $kitty],
        ["chromium", $chromium],
        ["code-oss|code", $code],
        ["thunar", $thunar],
        ["mousepad|org.xfce.mousepad", $mousepad],
        ["mpv", $mpv],
        ["imv.*", $imv],
        ["kafka-btop", $btop],
        ["blueman.*", $blueman],
        ["kafka-cava", $cava],
        [".*", $fallback]
    ]')

# $1 = clients JSON, $2 = monitors JSON, $3 = địa chỉ cửa sổ đang focus
render() {
    jq -cn --argjson c "$1" --argjson m "$2" --arg act "$3" --argjson icons "$ICONS" --argjson max "${KAFKA_COLMAP_MAX:-5}" '
        ($m | map(select(.focused)) | .[0] // $m[0] // {}) as $mon |
        ($mon.scale // 1) as $s |
        (($mon.x // 0) + ($mon.reserved[0] // 0)) as $left |
        (($mon.x // 0) + ($mon.width // 0) / $s - ($mon.reserved[2] // 0)) as $right |
        [ $c[] | select(.workspace.id == ($mon.activeWorkspace.id // -99) and .floating == false and .mapped != false) ] |
        group_by(.at[0]) | map({
            x: .[0].at[0], w: .[0].size[0], n: length,
            focus: (map(.address) | index($act) != null),
            cls: (map(.class) | unique | join(", ")),
            icon: (
                ((sort_by(.at[1]) | .[0].class) // "") as $firstcls |
                ($icons | map(select(. as $e | $firstcls | test("^(" + $e[0] + ")$"; "i"))) | .[0][1])
            )
        }) | sort_by(.x) |
        if length == 0 then {text: "", tooltip: "", class: "empty"} else
        map(. + {pos: (if .x + .w <= $left + 50 then "left" elif .x >= $right - 50 then "right" else "on" end)}) as $cols |
        ($cols | map(select(.pos == "left")) | length) as $nl |
        ($cols | map(select(.pos == "right")) | length) as $nr |
        # Chỉ hiện tối đa $max cột quanh cột đang dùng (không thì nhiều cửa sổ làm cụm trái dài ra, đẩy đồng hồ
        # và bóp ô trống của ô nhạc); cột bị bỏ bớt ghi gọn "‹N" / "N›". Tooltip vẫn liệt kê đủ.
        ($cols | length) as $len |
        (($cols | map(.focus) | index(true)) // ($cols | map(.pos == "on") | index(true)) // 0) as $fi |
        ([0, ([($fi - (($max - 1) / 2 | floor)), ($len - $max)] | min)] | max) as $st |
        ($cols[$st:$st + $max]) as $shown |
        ($len - $st - ($shown | length)) as $after |
        {
            text: ("<span font_family=\"FiraCode Nerd Font Propo\">"
                + (if $st > 0 then "<span color=\"#9284a6\" size=\"small\">‹\($st)</span>  " else "" end)
                + ($shown | map(
                    (.icon + (if .n > 1 then "<span size=\"small\" rise=\"4000\">\(.n)</span>" else "" end)) as $g |
                    if .focus then "<span color=\"#e0559a\">\($g)</span>"
                    elif .pos == "on" then "<span color=\"#fbf7fd\">\($g)</span>"
                    else "<span color=\"#9284a6\">\($g)</span>" end
                  ) | join("  "))
                + (if $after > 0 then "  <span color=\"#9284a6\" size=\"small\">\($after)›</span>" else "" end)
                + "</span>"),
            tooltip: ("\($cols | length) cột"
                + (if $nl > 0 then " · \($nl) khuất trái" else "" end)
                + (if $nr > 0 then " · \($nr) khuất phải" else "" end)
                + "\n" + ($cols | to_entries | map(
                    "\(.key + 1). \(.value.cls)" + (if .value.n > 1 then " (\(.value.n) cửa sổ)" else "" end)
                    + (if .value.focus then "  ◂ đang dùng" elif .value.pos != "on" then "  (khuất)" else "" end)
                  ) | join("\n"))
                + "\nLăn: chuyển cột · Bấm: đổi độ rộng cột (Super + G)"),
            class: (if ($nl + $nr) > 0 then "hidden-cols" else "all-visible" end)
        } end'
}

selftest() {
    local mons='[{"focused":true,"x":0,"width":1920,"height":1080,"scale":1,"reserved":[0,48,74,0],"activeWorkspace":{"id":1}}]'
    local cl='[
      {"address":"0xa","class":"code-oss","workspace":{"id":1},"floating":false,"at":[-1802,62],"size":[1806,1004]},
      {"address":"0xb","class":"kitty","workspace":{"id":1},"floating":false,"at":[20,62],"size":[900,500]},
      {"address":"0xc","class":"kitty","workspace":{"id":1},"floating":false,"at":[20,570],"size":[900,500]},
      {"address":"0xd","class":"chromium","workspace":{"id":1},"floating":false,"at":[1842,62],"size":[1806,1004]},
      {"address":"0xe","class":"pavucontrol","workspace":{"id":1},"floating":true,"at":[300,300],"size":[500,400]},
      {"address":"0xf","class":"mpv","workspace":{"id":2},"floating":false,"at":[20,62],"size":[1806,1004]}]'
    local out; out=$(render "$cl" "$mons" "0xb")
    local text; text=$(jq -r '.text' <<<"$out")
    local ok=1
    # (a) kitty focus, chồng 2 cửa sổ: icon + số nhỏ trong cùng span màu
    [[ $text == *"<span color=\"#e0559a\">${icon_kitty}<span size=\"small\" rise=\"4000\">2</span></span>"* ]] || ok=0
    [[ $text == *'<span size="small" rise="4000">2</span>'* ]] || ok=0
    # (b) code và chromium khuất (#9284a6)
    [[ $text == *"<span color=\"#9284a6\">${icon_code}</span>"* ]] || ok=0
    [[ $text == *"<span color=\"#9284a6\">${icon_chromium}</span>"* ]] || ok=0
    # (c) class
    [[ $(jq -r '.class' <<<"$out") == hidden-cols ]] || ok=0
    # (d) tooltip giữ như cũ
    jq -e '.tooltip | startswith("3 cột · 1 khuất trái · 1 khuất phải")' <<<"$out" >/dev/null || ok=0
    # (e) clients rỗng -> text ""
    [[ $(render '[]' "$mons" "" | jq -r '.text') == "" ]] || ok=0
    # (f) 9 cột, focus ở cột 9 → hiện 5 cột cuối + "‹4", không có "›"
    local many='[' i
    for i in 1 2 3 4 5 6 7 8 9; do many+="{\"address\":\"0x$i\",\"class\":\"thunar\",\"workspace\":{\"id\":1},\"floating\":false,\"at\":[$((i*100)),62],\"size\":[90,500]},"; done
    many="${many%,}]"
    text=$(render "$many" "$mons" "0x9" | jq -r '.text')
    [[ $text == *'‹4</span>'* && $text != *'›</span>'* ]] || ok=0
    [[ $(grep -o "$icon_thunar" <<<"$text" | wc -l) -eq 5 ]] || ok=0
    # (g) focus ở cột 1 → 5 cột đầu + "4›"
    text=$(render "$many" "$mons" "0x1" | jq -r '.text')
    [[ $text == *'4›</span>'* && $text != *'‹'* ]] || ok=0
    if (( ok )); then echo PASS; else echo FAIL; echo "$out" >&2; return 1; fi
}

case "${1:-}" in
    --selftest) selftest; exit $? ;;
esac
clients=$(hyprctl clients -j 2>/dev/null) || clients='[]'
monitors=$(hyprctl monitors -j 2>/dev/null) || monitors='[]'
active=$(hyprctl activewindow -j 2>/dev/null | jq -r '.address // ""' 2>/dev/null)
render "${clients:-[]}" "${monitors:-[]}" "${active:-}"
