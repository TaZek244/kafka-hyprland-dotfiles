#!/usr/bin/env bash
# power-profile.sh : xoay vòng chế độ nguồn (tiết kiệm → cân bằng → hiệu năng) qua power-profiles-daemon.
# Thay bảng "Power" của GNOME Settings cho nút pin trên Waybar.
cur=$(powerprofilesctl get) || exit 1
case "$cur" in
    power-saver) next=balanced;    label="󰾅  Cân bằng" ;;
    balanced)    next=performance; label="󰓅  Hiệu năng" ;;
    *)           next=power-saver; label="󰾆  Tiết kiệm pin" ;;
esac
powerprofilesctl set "$next" && notify-send -a "Kafka" -h string:x-dunst-stack-tag:power-profile "Chế độ nguồn" "$label"
