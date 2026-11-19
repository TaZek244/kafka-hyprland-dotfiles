#!/usr/bin/env bash
# ime-status.sh : trạng thái bộ gõ fcitx5 cho nút bàn phím trên dock (Waybar custom/ime).
# Chạy liên tục (Waybar đọc từng dòng JSON), chỉ in khi trạng thái đổi.
# fcitx không báo sự kiện cho Waybar, nên hỏi fcitx5-remote mỗi 0,4s (lệnh D-Bus rất nhẹ).
#   fcitx5-remote: 2 = đang gõ tiếng Việt (unikey), 1 = tiếng Anh, 0 = fcitx chưa chạy
last=""
while :; do
    # Chỉ hỏi khi fcitx5 đã chạy: fcitx5-remote lúc fcitx5 chưa có sẽ khiến D-Bus tự bật một bản
    # (có thể thiếu môi trường Wayland). Việc bật fcitx5 là của ime-guard.sh.
    st=0; pgrep -x -u "$UID" fcitx5 >/dev/null && st=$(fcitx5-remote 2>/dev/null)
    case "$st" in
        2) out='{"text":"VI","class":"vi","tooltip":"Bộ gõ: Tiếng Việt (Unikey)\nTrái: chuyển sang tiếng Anh · Giữa: khởi động lại bộ gõ · Phải: cấu hình fcitx5"}' ;;
        1) out='{"text":"EN","class":"en","tooltip":"Bộ gõ: Tiếng Anh\nTrái: chuyển sang tiếng Việt · Giữa: khởi động lại bộ gõ · Phải: cấu hình fcitx5"}' ;;
        *) out='{"text":"󰌌","class":"off","tooltip":"fcitx5 chưa chạy\nTrái/giữa: khởi động bộ gõ"}' ;;
    esac
    if [[ "$out" != "$last" ]]; then
        printf '%s\n' "$out" || exit 0   # Waybar đóng ống -> thoát
        last="$out"
    fi
    sleep 0.4
done
