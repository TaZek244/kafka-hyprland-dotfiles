#!/usr/bin/env bash
# Bật/tắt chế độ tổng quan của hyprshell từ ngoài (ô góc mạng nhện trên Waybar).
# hyprshell 4.10 chỉ nhận từ ngoài: "OpenOverview" | {"OpenSwitch":{"reverse":bool}} | {"CloseSwitch":{"switch":bool}} | "Reload"
# (ExternalTransferType trong crates/core-lib/src/transfer/structs.rs). Không có lệnh đóng từ ngoài, nhưng gửi
# "OpenOverview" khi đang mở thì nó đóng lại (đã thử) -> dùng như bật/tắt.
exec hyprshell socat -q '"OpenOverview"'
