#!/usr/bin/env bash
# ime-status.sh : trạng thái bộ gõ fcitx5 cho nút bàn phím trên dock (Waybar custom/ime).
# Chạy liên tục (Waybar đọc từng dòng JSON), chỉ in khi trạng thái đổi.
# fcitx không báo sự kiện cho Waybar, nên hỏi fcitx5-remote mỗi 0,4s (lệnh D-Bus rất nhẹ).
#   fcitx5-remote: 2 = đang gõ tiếng Việt (unikey), 1 = tiếng Anh, 0 = fcitx chưa chạy
last=""
while :; do
    case "$(fcitx5-remote 2>/dev/null)" in
        2) out='{"text":"VI","class":"vi","tooltip":"Bộ gõ: Tiếng Việt (Unikey)\nTrái: chuyển sang tiếng Anh · Phải: cấu hình fcitx5"}' ;;
        1) out='{"text":"EN","class":"en","tooltip":"Bộ gõ: Tiếng Anh\nTrái: chuyển sang tiếng Việt · Phải: cấu hình fcitx5"}' ;;
        *) out='{"text":"󰌌","class":"off","tooltip":"fcitx5 chưa chạy\nTrái: khởi động fcitx5"}' ;;
    esac
    if [[ "$out" != "$last" ]]; then
        printf '%s\n' "$out" || exit 0   # Waybar đóng ống -> thoát
        last="$out"
    fi
    sleep 0.4
done
