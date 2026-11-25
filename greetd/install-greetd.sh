#!/usr/bin/env bash
# install-greetd.sh            : cài greetd + ReGreet + cage, chép cấu hình/theme Kafka vào /etc/greetd
# install-greetd.sh --switch   : như trên, rồi tắt GDM/gdm3/sddm/lightdm (nếu còn) và bật greetd
#                                (có hiệu lực từ lần khởi động sau)
# install-greetd.sh --cursors  : chỉ chép bộ con trỏ Kafka (~/.local/share/icons/Kafka-BEN, Kafka-Cursor) vào
#                                /usr/share/icons + cấu hình greetd/ReGreet dùng nó (không cài gói, không đổi trình đăng nhập)
# install-greetd.sh --theme    : chỉ chép lại giao diện ReGreet theo giao diện đang dùng (ui-theme.sh):
#                                pixel → regreet-pixel.css + ảnh khung pixel-panel.png ; phẳng → regreet.css
# install-greetd.sh --kafka    : dùng trình đăng nhập pixel tự viết "KAFKA.SYS" (greetd/kafka-greeter/) thay ReGreet:
#                                tạo ảnh (nền pixel hoá + mặt Kafka) từ wallpapers/, chép vào /usr/local/share/kafka-greeter,
#                                đặt /etc/greetd/config.toml = config-kafka.toml (lỗi thì tự mở ReGreet hoặc agreety)
# install-greetd.sh --regreet  : quay lại ReGreet (config.toml thường)
# install-greetd.sh --revert   : bỏ ReGreet, dùng màn hình đăng nhập dạng chữ agreety (vẫn là greetd,
#                                không cần GDM nên dùng được cả khi đã gỡ GNOME)
# install-greetd.sh -h|--help  : in phần mô tả các tuỳ chọn rồi thoát
#
# Hỗ trợ Arch Linux và Ubuntu/Debian. Trên Ubuntu/Debian: user greetd là "_greetd", ReGreet không có trong apt.
#
# Nếu ReGreet hỏng sau khi khởi động lại: Ctrl+Alt+F2 đăng nhập TTY rồi chạy (không cần repo):
#   sudo cp /etc/greetd/config-fallback.toml /etc/greetd/config.toml && sudo systemctl restart greetd
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=SCRIPTDIR/../lib/distro.sh
source "$REPO_DIR/lib/distro.sh"
distro_detect
CURSOR_THEMES=(Kafka-Cursor Kafka-BEN) # Kafka-BEN kế thừa Kafka-Cursor → chép cả hai

usage() {
    cat <<'EOF'
Cài greetd + ReGreet + cage, chép cấu hình/theme Kafka vào /etc/greetd.
Hỗ trợ Arch Linux và Ubuntu/Debian (Ubuntu/Debian dùng user greetd "_greetd").

Tuỳ chọn:
    (không có)  Cài gói, chép cấu hình/theme/con trỏ; chưa đổi trình đăng nhập.
    -h, --help  In trợ giúp này rồi thoát.
    --switch    Như mặc định, rồi tắt gdm/gdm3/sddm/lightdm (nếu có) và bật greetd
                (có hiệu lực từ lần khởi động sau).
    --cursors   Chỉ chép con trỏ Kafka vào /usr/share/icons + cập nhật cấu hình greetd;
                không cài gói, không đổi trình đăng nhập.
    --theme     Chỉ chép lại giao diện ReGreet theo ui-theme.sh (pixel → regreet-pixel.css
                + pixel-panel.png ; phẳng → regreet.css).
    --kafka     Dùng KAFKA.SYS (trình đăng nhập pixel tự viết) thay ReGreet; tạo ảnh từ
                wallpapers/, chép vào /usr/local/share/kafka-greeter rồi đặt làm màn hình đăng nhập.
    --regreet   Quay lại ReGreet (config.toml thường).
    --revert    Bỏ ReGreet, dùng agreety dạng chữ (vẫn là greetd, không cần GDM).

Khôi phục khi ReGreet hỏng: Ctrl+Alt+F2 rồi
    sudo cp /etc/greetd/config-fallback.toml /etc/greetd/config.toml && sudo systemctl restart greetd
EOF
}

# User hệ thống chạy greetd: Arch dùng "greeter", Ubuntu/Debian dùng "_greetd".
greeter_user() {
    if getent passwd greeter >/dev/null 2>&1; then
        echo greeter
    elif getent passwd _greetd >/dev/null 2>&1; then
        echo _greetd
    else
        echo greeter
    fi
}

# Cài gói greetd theo distro. Dừng nếu không nhận diện được distro (trừ chế độ chỉ chép file).
install_greeter_packages() {
    local pkgs=()
    if [ "$DISTRO" = unknown ]; then
        echo "Không nhận diện được distro ($DISTRO_NAME): tự cài greetd + cage (và ReGreet nếu dùng) rồi chạy lại." >&2
        exit 1
    fi
    mapfile -t pkgs < <(pkg_list greetd)
    pkg_install "${pkgs[@]}"
}

# ReGreet không có trong kho apt: báo rõ và dừng, không đụng /etc/greetd/config.toml.
require_regreet() {
    command -v regreet >/dev/null 2>&1 && return 0
    echo "Không tìm thấy ReGreet: gói này không có trong kho Ubuntu/Debian (và chưa được cài tay)." >&2
    echo "Chọn một trong hai:" >&2
    echo "  - Dùng KAFKA.SYS (trình đăng nhập pixel tự viết, chỉ cần python3-gi): $0 --kafka" >&2
    echo "  - Tự cài ReGreet: cargo install --git https://github.com/rharish101/ReGreet" >&2
    exit 1
}

# Chép cấu hình greetd qua file tạm: đổi dòng user = "greeter" thành user thật nếu cần.
# $1: tên file trong greetd/, $2: đích, các đối số sau: tham số sed bổ sung (nếu cần).
install_conf() {
    local src="$REPO_DIR/greetd/$1" dst="$2" user tmp
    shift 2
    user=$(greeter_user)
    tmp=$(mktemp)
    sed -e "s/^user = \"greeter\"/user = \"$user\"/" "$@" "$src" >"$tmp"
    sudo install -Dm644 "$tmp" "$dst"
    rm -f -- "$tmp"
}

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
    local user fallback_sed=()
    command -v magick >/dev/null && make_kafka_assets
    install_greeter_packages
    python3 "$KG_SRC/kafka-greeter.py" --selftest >/dev/null || {
        echo "kafka-greeter --selftest lỗi, không cài" >&2
        exit 1
    }
    python3 "$KG_SRC/greetd_ipc.py" --selftest >/dev/null || {
        echo "greetd_ipc --selftest lỗi, không cài" >&2
        exit 1
    }
    sudo rm -rf -- "$KG_DST"
    sudo install -d "$KG_DST"
    sudo install -m644 "$KG_SRC"/*.py "$KG_DST"/
    for f in "$KG_SRC"/*.png; do [ -f "$f" ] && sudo install -m644 "$f" "$KG_DST"/; done
    user=$(greeter_user)
    sudo install -d -o "$user" -g "$user" /var/cache/kafka-greeter # nhớ người dùng/phiên lần trước
    [ -f /etc/greetd/config.toml ] && [ ! -f /etc/greetd/config.toml.bak ] && sudo cp /etc/greetd/config.toml /etc/greetd/config.toml.bak
    install_conf config-fallback.toml /etc/greetd/config-fallback.toml
    if ! command -v regreet >/dev/null 2>&1; then
        # Trên Ubuntu/Debian không có ReGreet: fallback trong config-kafka.toml chuyển sang agreety.
        echo "Không có ReGreet: fallback của KAFKA.SYS đổi sang agreety." >&2
        # agreety là chương trình dạng chữ, cần TTY → phải chạy NGOÀI cage (cage không có terminal):
        #   sh -c 'cage … -- python3 kafka-greeter.py || exec agreety --cmd start-hyprland'
        fallback_sed=(-e 's/tự mở ReGreet thay (|| exec regreet)/tự mở agreety (đăng nhập dạng chữ) thay/'
            -e "s#cage -s -m last -- sh -c 'python3 \\([^ ']*\\) || exec regreet'#sh -c 'cage -s -m last -- python3 \\1 || exec agreety --cmd start-hyprland'#")
    fi
    install_conf config-kafka.toml /etc/greetd/config.toml "${fallback_sed[@]}"
    echo "Đã cài KAFKA.SYS vào $KG_DST và đặt làm màn hình đăng nhập (từ lần khởi động sau)."
    if ((${#fallback_sed[@]})); then
        echo "Lỗi thì tự mở agreety; quay lại hẳn: $0 --regreet"
    else
        echo "Lỗi thì tự mở ReGreet; quay lại hẳn: $0 --regreet"
    fi
}

if [ "$#" -gt 1 ]; then
    echo "Chỉ nhận một tuỳ chọn." >&2
    usage
    exit 1
fi

case "${1:-}" in
    -h | --help)
        usage
        exit 0
        ;;
    --kafka)
        install_kafka_greeter
        exit 0
        ;;
    --regreet)
        require_regreet
        [ -f /etc/greetd/config.toml ] && [ ! -f /etc/greetd/config.toml.bak ] && sudo cp /etc/greetd/config.toml /etc/greetd/config.toml.bak
        install_conf config.toml /etc/greetd/config.toml
        echo "Đã quay lại ReGreet (từ lần khởi động sau)."
        exit 0
        ;;
    --theme)
        install_greeter_theme
        exit 0
        ;;
    --cursors)
        install_cursors
        for f in config.toml regreet.toml; do
            install_conf "$f" "/etc/greetd/$f"
        done
        echo "Đã cập nhật /etc/greetd (config.toml, regreet.toml). Màn hình đăng nhập dùng con trỏ mới từ lần khởi động sau."
        exit 0
        ;;
    --revert)
        [ -f /etc/greetd/config.toml ] && [ ! -f /etc/greetd/config.toml.bak ] && sudo cp /etc/greetd/config.toml /etc/greetd/config.toml.bak
        install_conf config-fallback.toml /etc/greetd/config-fallback.toml
        install_conf config-fallback.toml /etc/greetd/config.toml
        sudo systemctl enable greetd
        echo "Đã chuyển greetd sang agreety (đăng nhập dạng chữ, gõ start-hyprland sau khi vào)."
        echo "Áp dụng ngay: sudo systemctl restart greetd (đóng phiên hiện tại!) hoặc khởi động lại."
        echo "Dùng lại ReGreet: $0"
        exit 0
        ;;
    "" | --switch)
        # Cài gói + chép cấu hình ở phần dưới; --switch đổi trình đăng nhập ở cuối.
        ;;
    *)
        echo "Tuỳ chọn lạ: ${1:-}" >&2
        usage
        exit 1
        ;;
esac

# Ảnh nền không nằm trong repo (bản quyền): install.sh --only assets tạo từ wallpapers/ (hoặc ảnh gradient)
if [ ! -f "$REPO_DIR/greetd/greeter-bg.jpg" ]; then
    echo "Thiếu greetd/greeter-bg.jpg. Chạy trước: $REPO_DIR/install.sh --only assets" >&2
    exit 1
fi

install_greeter_packages
require_regreet

for f in config.toml regreet.toml config-fallback.toml; do
    [ -f "/etc/greetd/$f" ] && [ ! -f "/etc/greetd/$f.bak" ] && sudo cp "/etc/greetd/$f" "/etc/greetd/$f.bak"
    install_conf "$f" "/etc/greetd/$f"
done
sudo install -Dm644 "$REPO_DIR/greetd/greeter-bg.jpg" /usr/share/backgrounds/kafka-greeter.jpg
install_greeter_theme
install_cursors
echo "Đã chép cấu hình vào /etc/greetd/ và ảnh nền vào /usr/share/backgrounds/kafka-greeter.jpg"

if [ "${1:-}" = "--switch" ]; then
    # Tắt các trình đăng nhập khác trước (nếu còn cài), nếu không systemd báo trùng display-manager.service.
    # list-unit-files trên Ubuntu trả mã 0 cả khi không có unit → phải grep.
    for dm in gdm gdm3 sddm lightdm; do
        if systemctl list-unit-files "$dm.service" 2>/dev/null | grep -qF "$dm.service"; then
            sudo systemctl disable "$dm.service"
        fi
    done
    sudo systemctl enable greetd
    echo "Đã đổi sang greetd. Khởi động lại để dùng."
else
    echo "Chưa đổi trình đăng nhập. Xem thử: regreet --demo   ·   đổi hẳn: $0 --switch"
fi
