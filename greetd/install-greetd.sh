#!/usr/bin/env bash
# install-greetd.sh            : cài greetd + ReGreet + cage, chép cấu hình/theme Kafka vào /etc/greetd
# install-greetd.sh --switch   : như trên, rồi tắt GDM (nếu còn) và bật greetd (có hiệu lực từ lần khởi động sau)
# install-greetd.sh --cursors  : chỉ chép bộ con trỏ Kafka (~/.local/share/icons/Kafka-BEN, Kafka-Cursor) vào
#                                /usr/share/icons + cấu hình greetd/ReGreet dùng nó (không cài gói, không đổi trình đăng nhập)
# install-greetd.sh --theme    : chỉ chép lại giao diện ReGreet theo giao diện đang dùng (ui-theme.sh):
#                                pixel → regreet-pixel.css + ảnh khung pixel-panel.png ; phẳng → regreet.css
# install-greetd.sh --kafka    : dùng trình đăng nhập pixel tự viết "KAFKA.SYS" (greetd/kafka-greeter/) thay ReGreet:
#                                tạo ảnh (nền pixel hoá + mặt Kafka) từ wallpapers/, chép vào /usr/local/share/kafka-greeter,
#                                đặt /etc/greetd/config.toml = config-kafka.toml (lỗi thì tự mở ReGreet)
# install-greetd.sh --regreet  : quay lại ReGreet (config.toml thường)
# install-greetd.sh --revert   : bỏ ReGreet, dùng màn hình đăng nhập dạng chữ agreety (vẫn là greetd,
#                                không cần GDM nên dùng được cả khi đã gỡ GNOME)
#
# Nếu ReGreet hỏng sau khi khởi động lại: Ctrl+Alt+F2 đăng nhập TTY rồi chạy (không cần repo):
#   sudo cp /etc/greetd/config-fallback.toml /etc/greetd/config.toml && sudo systemctl restart greetd
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CURSOR_THEMES=(Kafka-Cursor Kafka-BEN)   # Kafka-BEN kế thừa Kafka-Cursor → chép cả hai

# Con trỏ cho màn hình đăng nhập: user greeter không đọc được ~/ nên chép bộ con trỏ (sinh bởi install.sh /
# cursors/*.py) vào /usr/share/icons. Chỉ xoá/ghi đè đúng các thư mục tên trong CURSOR_THEMES.
install_cursors() {
    local t src n=0
    for t in "${CURSOR_THEMES[@]}"; do
        src="$HOME/.local/share/icons/$t"
        if [ ! -f "$src/index.theme" ]; then
            echo "Bỏ qua $t: chưa có $src (chạy ./install.sh trước)" >&2
            continue
        fi
        sudo rm -rf -- "/usr/share/icons/$t"
        sudo cp -a -- "$src" "/usr/share/icons/$t"
        sudo chown -R root:root "/usr/share/icons/$t"
        sudo chmod -R a+rX "/usr/share/icons/$t"
        n=$((n + 1))
    done
    echo "Đã chép $n bộ con trỏ vào /usr/share/icons (${CURSOR_THEMES[*]})"
}

# Giao diện ReGreet theo ~/.local/state/kafka/ui-theme (đổi theme xong chạy lại `--theme`, cần sudo)
install_greeter_theme() {
    local mode css="$REPO_DIR/greetd/regreet.css"
    mode=$(cat "${XDG_STATE_HOME:-$HOME/.local/state}/kafka/ui-theme" 2>/dev/null || echo flat)
    if [ "$mode" = "pixel" ] && [ -f "$REPO_DIR/greetd/regreet-pixel.css" ]; then
        css="$REPO_DIR/greetd/regreet-pixel.css"
        sudo install -Dm644 "$REPO_DIR/waybar/pixel/panel.png" /etc/greetd/pixel-panel.png
    fi
    [ -f /etc/greetd/regreet.css ] && [ ! -f /etc/greetd/regreet.css.bak ] && sudo cp /etc/greetd/regreet.css /etc/greetd/regreet.css.bak
    sudo install -Dm644 "$css" /etc/greetd/regreet.css
    echo "Giao diện màn hình đăng nhập: $mode ($(basename "$css"))"
}

KG_SRC="$REPO_DIR/greetd/kafka-greeter"
KG_DST=/usr/local/share/kafka-greeter

# Ảnh cho kafka-greeter sinh từ wallpapers/ (bản quyền, không nằm trong repo); thiếu thì greeter tự vẽ nền/biểu tượng thay.
make_kafka_assets() {
    local wp="$REPO_DIR/wallpapers"
    if [ -f "$wp/kafka_landscape_3.jpg" ]; then
        magick "$wp/kafka_landscape_3.jpg" -resize 240x135^ -gravity center -extent 240x135 -modulate 95,115 \
            -dither FloydSteinberg -colors 40 -fill "#140e1c" -colorize 35% "$KG_SRC/bg-pixel.png"
    fi
    if [ -f "$wp/Kafka_thumbail.jpg" ]; then
        magick "$wp/Kafka_thumbail.jpg" -crop 500x500+118+10 +repage -filter Lanczos -resize 400x400 \
            -unsharp 0x0.5 "$KG_SRC/avatar.png"
    fi
}

install_kafka_greeter() {
    command -v magick >/dev/null && make_kafka_assets
    python3 "$KG_SRC/kafka-greeter.py" --selftest >/dev/null || { echo "kafka-greeter --selftest lỗi, không cài" >&2; exit 1; }
    python3 "$KG_SRC/greetd_ipc.py" --selftest >/dev/null || { echo "greetd_ipc --selftest lỗi, không cài" >&2; exit 1; }
    sudo pacman -S --needed greetd greetd-regreet cage python-gobject python-cairo
    sudo rm -rf -- "$KG_DST"
    sudo install -d "$KG_DST"
    sudo install -m644 "$KG_SRC"/*.py "$KG_DST"/
    for f in "$KG_SRC"/*.png; do [ -f "$f" ] && sudo install -m644 "$f" "$KG_DST"/; done
    sudo install -d -o greeter -g greeter /var/cache/kafka-greeter     # nhớ người dùng/phiên lần trước
    [ -f /etc/greetd/config.toml ] && [ ! -f /etc/greetd/config.toml.bak ] && sudo cp /etc/greetd/config.toml /etc/greetd/config.toml.bak
    sudo install -Dm644 "$REPO_DIR/greetd/config-fallback.toml" /etc/greetd/config-fallback.toml
    sudo install -Dm644 "$REPO_DIR/greetd/config-kafka.toml" /etc/greetd/config.toml
    echo "Đã cài KAFKA.SYS vào $KG_DST và đặt làm màn hình đăng nhập (từ lần khởi động sau)."
    echo "Lỗi thì tự mở ReGreet; quay lại hẳn: $0 --regreet"
}

if [ "${1:-}" = "--kafka" ]; then
    install_kafka_greeter
    exit 0
fi

if [ "${1:-}" = "--regreet" ]; then
    sudo install -Dm644 "$REPO_DIR/greetd/config.toml" /etc/greetd/config.toml
    echo "Đã quay lại ReGreet (từ lần khởi động sau)."
    exit 0
fi

if [ "${1:-}" = "--theme" ]; then
    install_greeter_theme
    exit 0
fi

if [ "${1:-}" = "--cursors" ]; then
    install_cursors
    for f in config.toml regreet.toml; do
        sudo install -Dm644 "$REPO_DIR/greetd/$f" "/etc/greetd/$f"
    done
    echo "Đã cập nhật /etc/greetd (config.toml, regreet.toml). Màn hình đăng nhập dùng con trỏ mới từ lần khởi động sau."
    exit 0
fi

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

for f in config.toml regreet.toml config-fallback.toml; do
    [ -f "/etc/greetd/$f" ] && [ ! -f "/etc/greetd/$f.bak" ] && sudo cp "/etc/greetd/$f" "/etc/greetd/$f.bak"
    sudo install -Dm644 "$REPO_DIR/greetd/$f" "/etc/greetd/$f"
done
sudo install -Dm644 "$REPO_DIR/greetd/greeter-bg.jpg" /usr/share/backgrounds/kafka-greeter.jpg
install_greeter_theme
install_cursors
echo "Đã chép cấu hình vào /etc/greetd/ và ảnh nền vào /usr/share/backgrounds/kafka-greeter.jpg"

if [ "${1:-}" = "--switch" ]; then
    # Tắt GDM trước (nếu còn cài), nếu không systemd báo trùng display-manager.service.
    if systemctl list-unit-files gdm.service >/dev/null 2>&1; then sudo systemctl disable gdm; fi
    sudo systemctl enable greetd
    echo "Đã đổi sang greetd. Khởi động lại để dùng."
else
    echo "Chưa đổi trình đăng nhập. Xem thử: regreet --demo   ·   đổi hẳn: $0 --switch"
fi
