#!/usr/bin/env bash
# install-greetd.sh            : cài greetd + ReGreet + cage, chép cấu hình/theme Kafka vào /etc/greetd
# install-greetd.sh --switch   : như trên, rồi tắt GDM (nếu còn) và bật greetd (có hiệu lực từ lần khởi động sau)
# install-greetd.sh --revert   : bỏ ReGreet, dùng màn hình đăng nhập dạng chữ agreety (vẫn là greetd,
#                                không cần GDM nên dùng được cả khi đã gỡ GNOME)
#
# Nếu ReGreet hỏng sau khi khởi động lại: Ctrl+Alt+F2 đăng nhập TTY rồi chạy (không cần repo):
#   sudo cp /etc/greetd/config-fallback.toml /etc/greetd/config.toml && sudo systemctl restart greetd
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "${1:-}" = "--revert" ]; then
    [ -f /etc/greetd/config.toml ] && [ ! -f /etc/greetd/config.toml.bak ] && sudo cp /etc/greetd/config.toml /etc/greetd/config.toml.bak
    sudo install -Dm644 "$REPO_DIR/greetd/config-fallback.toml" /etc/greetd/config-fallback.toml
    sudo install -Dm644 "$REPO_DIR/greetd/config-fallback.toml" /etc/greetd/config.toml
    sudo systemctl enable greetd
    echo "Đã chuyển greetd sang agreety (đăng nhập dạng chữ, gõ start-hyprland sau khi vào)."
    echo "Áp dụng ngay: sudo systemctl restart greetd (đóng phiên hiện tại!) hoặc khởi động lại."
    echo "Dùng lại ReGreet: $0"
    exit 0
fi

# Ảnh nền không nằm trong repo (bản quyền): install.sh --only assets tạo từ wallpapers/ (hoặc ảnh gradient)
if [ ! -f "$REPO_DIR/greetd/greeter-bg.jpg" ]; then
    echo "Thiếu greetd/greeter-bg.jpg. Chạy trước: $REPO_DIR/install.sh --only assets" >&2
    exit 1
fi

sudo pacman -S --needed greetd greetd-regreet cage

for f in config.toml regreet.toml regreet.css config-fallback.toml; do
    [ -f "/etc/greetd/$f" ] && [ ! -f "/etc/greetd/$f.bak" ] && sudo cp "/etc/greetd/$f" "/etc/greetd/$f.bak"
    sudo install -Dm644 "$REPO_DIR/greetd/$f" "/etc/greetd/$f"
done
sudo install -Dm644 "$REPO_DIR/greetd/greeter-bg.jpg" /usr/share/backgrounds/kafka-greeter.jpg
echo "Đã chép cấu hình vào /etc/greetd/ và ảnh nền vào /usr/share/backgrounds/kafka-greeter.jpg"

if [ "${1:-}" = "--switch" ]; then
    # Tắt GDM trước (nếu còn cài), nếu không systemd báo trùng display-manager.service.
    if systemctl list-unit-files gdm.service >/dev/null 2>&1; then sudo systemctl disable gdm; fi
    sudo systemctl enable greetd
    echo "Đã đổi sang greetd. Khởi động lại để dùng."
else
    echo "Chưa đổi trình đăng nhập. Xem thử: regreet --demo   ·   đổi hẳn: $0 --switch"
fi
