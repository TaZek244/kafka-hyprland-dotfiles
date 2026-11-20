#!/usr/bin/env bash
# ==============================================================================
#  install.sh — Cài đặt bộ dotfiles Hyprland · Kafka (Honkai: Star Rail) Edition
# ==============================================================================
#  Dùng cho Arch Linux (hoặc dẫn xuất) + Hyprland 0.57+ (cấu hình Lua).
#  Chạy được nhiều lần (idempotent): cái gì đã đúng thì bỏ qua, cái cũ bị thay
#  thì sao lưu vào ~/.config/backup_before_kafka_<ngày giờ>/.
#
#  ./install.sh                 chạy mọi bước: packages link assets system fcitx services check
#  ./install.sh --only a,b      chỉ chạy các bước liệt kê
#  ./install.sh --skip a,b      bỏ qua các bước liệt kê
#  ./install.sh --greetd        cài thêm màn hình đăng nhập greetd + ReGreet (chưa đổi trình đăng nhập)
#  ./install.sh --greetd-switch cài và đổi hẳn sang greetd (tắt GDM nếu có)
#  ./install.sh --dry-run       chỉ in lệnh, không làm gì
#  ./install.sh -y | --yes      không hỏi xác nhận
#  ./install.sh --no-aur        bỏ qua gói AUR
#  ./install.sh --force-fcitx   ghi đè cấu hình fcitx5 đang có
#  ./install.sh --force-assets  tạo lại cả ảnh phụ đã có (mặc định chỉ tạo ảnh còn thiếu)
#
#  Các bước:
#    packages  cài gói pacman + AUR (yay/paru; không có thì đề nghị cài yay-bin)
#    link      symlink từng thư mục cấu hình vào ~/.config (sao lưu cái cũ)
#    assets    tạo ảnh phụ (banner rofi, nền walker, nền đăng nhập, ảnh vuông) từ ảnh nền trong wallpapers/;
#              không có ảnh nền thì tạo ảnh gradient màu Kafka để mọi thứ vẫn chạy
#    system    quyền chạy script, file tự sinh, GTK tối, app mặc định (xdg-mime)
#    fcitx     cấu hình fcitx5 + Unikey (tiếng Việt) — không nằm trong repo vì fcitx5 tự ghi đè file
#    services  bật NetworkManager, bluetooth, power-profiles-daemon, warp-svc (VPN), elephant (nguồn dữ liệu của walker)
#    check     Hyprland --verify-config + selftest các script, liệt kê lệnh còn thiếu
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$CONFIG/backup_before_kafka_$STAMP"
ALL_STEPS=(packages link assets system fcitx services check)

DRY=0 YES=0 NO_AUR=0 FORCE_FCITX=0 FORCE_ASSETS=0 GREETD=""
ONLY="" SKIP=""

# ---------- giao diện ----------
c_pink=$'\033[1;35m' c_yel=$'\033[1;33m' c_grn=$'\033[1;32m' c_red=$'\033[1;31m' c_dim=$'\033[2m' c_off=$'\033[0m'
[ -t 1 ] || { c_pink="" c_yel="" c_grn="" c_red="" c_dim="" c_off=""; }
step() { printf '\n%s━━ %s%s\n' "$c_yel" "$*" "$c_off"; }
info() { printf '  %s\n' "$*"; }
ok()   { printf '  %s✓%s %s\n' "$c_grn" "$c_off" "$*"; }
warn() { printf '  %s!%s %s\n' "$c_yel" "$c_off" "$*" >&2; }
die()  { printf '%s✗ %s%s\n' "$c_red" "$*" "$c_off" >&2; exit 1; }
# run: chạy lệnh (hoặc chỉ in ở --dry-run)
run()  { if (( DRY )); then printf '  %s$ %s%s\n' "$c_dim" "$*" "$c_off"; else "$@"; fi; }
ask()  { (( YES )) && return 0; local a; read -r -p "  $* [Y/n] " a; [[ -z "$a" || "$a" =~ ^[YyCc] ]]; }

usage() { awk '/^set -euo/{exit} NR>1 && !/^# =====/{sub(/^# ?/,""); print}' "$0"; exit 0; }

# ---------- tham số ----------
while (($#)); do
    case "$1" in
        --only) ONLY="${2:?--only cần danh sách bước}"; shift ;;
        --only=*) ONLY="${1#*=}" ;;
        --skip) SKIP="${2:?--skip cần danh sách bước}"; shift ;;
        --skip=*) SKIP="${1#*=}" ;;
        --greetd) GREETD="install" ;;
        --greetd-switch) GREETD="switch" ;;
        --dry-run|-n) DRY=1 ;;
        -y|--yes) YES=1 ;;
        --no-aur) NO_AUR=1 ;;
        --force-fcitx) FORCE_FCITX=1 ;;
        --force-assets) FORCE_ASSETS=1 ;;
        -h|--help) usage ;;
        *) die "Tham số lạ: $1 (xem --help)" ;;
    esac
    shift
done

want() {   # want <bước>: bước này có được chạy không
    local s="$1"
    if [[ -n "$ONLY" ]]; then [[ ",$ONLY," == *",$s,"* ]] || return 1; fi
    [[ ",$SKIP," == *",$s,"* ]] && return 1
    return 0
}
NOCONF=(); (( YES )) && NOCONF=(--noconfirm)
for s in ${ONLY//,/ } ${SKIP//,/ }; do
    [[ " ${ALL_STEPS[*]} " == *" $s "* ]] || die "Bước không tồn tại: $s (có: ${ALL_STEPS[*]})"
done

# ---------- danh sách gói ----------
PKGS_CORE=(   # Hyprland và các thành phần màn hình
    hyprland hyprlock hypridle xdg-desktop-portal-hyprland xdg-desktop-portal-gtk
    qt5-wayland qt6-wayland qt6ct polkit-gnome gnome-keyring
    waybar rofi kitty dunst libnotify fastfetch awww cava btop
)
PKGS_TOOLS=(  # chụp/quay, clipboard, phần cứng (dùng bởi popup điều khiển và Waybar)
    grim slurp wl-clipboard cliphist hyprshot satty wf-recorder imagemagick jq
    networkmanager network-manager-applet bluez blueman util-linux
    pipewire pipewire-pulse wireplumber libpulse pavucontrol playerctl
    brightnessctl power-profiles-daemon upower
)
PKGS_APPS=(   # app thay thế GNOME
    thunar gvfs gvfs-mtp gvfs-smb gvfs-afc gvfs-gphoto2 tumbler mousepad imv mpv
)
PKGS_PY=(     # popup GTK (control-popup, clock-popup, tools-popup, dock-apps, keybinds-editor...)
    python python-gobject python-cairo gtk3 gtk4 gtk-layer-shell gtk4-layer-shell
)
PKGS_IME=( fcitx5 fcitx5-unikey fcitx5-gtk fcitx5-qt fcitx5-configtool )
PKGS_FONTS=(
    ttf-firacode-nerd ttf-jetbrains-mono-nerd noto-fonts noto-fonts-emoji
    papirus-icon-theme adwaita-icon-theme gsettings-desktop-schemas
)
PKGS_OPTIONAL=( chromium code )   # 2 app ghim trên dock (hỏi trước khi cài)
PKGS_AUR=(
    hyprshell-bin            # chế độ tổng quan (nhấn-thả Super) + Alt+Tab
    walker-bin elephant-bin  # trình mở app + nguồn dữ liệu (plugin phải cùng loại -bin)
    elephant-desktopapplications-bin elephant-runner-bin elephant-windows-bin
    elephant-calc-bin elephant-symbols-bin   # walker: "=" máy tính (libqalculate), "." emoji/ký tự
    cloudflare-warp-bin      # VPN có sẵn của nút VPN (miễn phí, không cần tài khoản)
)

# Thư mục cấu hình được symlink nguyên khối vào ~/.config/<tên>
LINK_DIRS=(hypr waybar rofi kitty dunst fastfetch cava hyprshell btop walker imv mpv)

# ==============================================================================
preflight() {
    printf '%s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n' "$c_pink"
    printf '  🕷  HYPRLAND · KAFKA (HONKAI: STAR RAIL) EDITION\n'
    printf '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n' "$c_off"
    (( EUID == 0 )) && die "Đừng chạy bằng root/sudo: script tự gọi sudo khi cần."
    info "Repo:      $REPO_DIR"
    info "Cấu hình:  $CONFIG"
    if [[ -n "$ONLY" ]]; then info "Chỉ chạy:  $ONLY"; fi
    if [[ -n "$SKIP" ]]; then info "Bỏ qua:    $SKIP"; fi
    (( DRY )) && info "${c_yel}Chế độ thử (--dry-run): không thay đổi gì.${c_off}"
    if ! command -v pacman >/dev/null; then
        want packages && die "Không thấy pacman: script này dành cho Arch Linux. Dùng --skip packages,services nếu tự cài gói."
    fi
}

# ---------- 1. gói ----------
aur_helper() {
    for h in yay paru; do command -v "$h" >/dev/null && { echo "$h"; return; }; done
}

install_yay() {
    ask "Chưa có yay/paru để cài gói AUR. Cài yay-bin bây giờ?" || return 1
    if (( DRY )); then
        run sudo pacman -S --needed --noconfirm git base-devel
        run git clone --depth 1 https://aur.archlinux.org/yay-bin.git /tmp/yay-bin
        run makepkg -si --noconfirm   # trong /tmp/yay-bin
        return 1
    fi
    sudo pacman -S --needed --noconfirm git base-devel
    local tmp; tmp="$(mktemp -d)"
    git clone --depth 1 https://aur.archlinux.org/yay-bin.git "$tmp/yay-bin"
    (cd "$tmp/yay-bin" && makepkg -si --noconfirm)
    [[ -n "$tmp" && -d "$tmp" ]] && rm -rf -- "$tmp"
}

step_packages() {
    step "[packages] Cài gói"
    local pkgs=("${PKGS_CORE[@]}" "${PKGS_TOOLS[@]}" "${PKGS_APPS[@]}" "${PKGS_PY[@]}" "${PKGS_IME[@]}" "${PKGS_FONTS[@]}")
    info "Gói chính thức (${#pkgs[@]}): ${pkgs[*]}"
    run sudo pacman -S --needed "${NOCONF[@]}" "${pkgs[@]}"
    if ask "Cài thêm app ghim trên dock (${PKGS_OPTIONAL[*]})?"; then
        run sudo pacman -S --needed "${NOCONF[@]}" "${PKGS_OPTIONAL[@]}"
    fi
    if (( NO_AUR )); then
        warn "Bỏ qua AUR (--no-aur). Tự cài sau: ${PKGS_AUR[*]}"
        return
    fi
    local h; h="$(aur_helper)"
    if [[ -z "$h" ]]; then install_yay && h="$(aur_helper)"; fi
    if [[ -z "$h" ]]; then
        (( DRY )) && h=yay || { warn "Không có yay/paru: tự cài ${PKGS_AUR[*]}"; return; }
    fi
    info "Gói AUR qua $h: ${PKGS_AUR[*]}"
    if [[ "$h" == yay ]]; then
        run yay -S --needed --answerclean None --answerdiff None "${NOCONF[@]}" "${PKGS_AUR[@]}"
    else
        run paru -S --needed "${NOCONF[@]}" "${PKGS_AUR[@]}"
    fi
    ok "Xong phần gói"
}

# ---------- 2. symlink ----------
link_one() {   # link_one <nguồn trong repo> <đích>
    local src="$1" dst="$2"
    if [[ -L "$dst" && "$(readlink -f "$dst")" == "$(readlink -f "$src")" ]]; then
        info "${c_dim}đã đúng: $dst${c_off}"; return
    fi
    if [[ -e "$dst" || -L "$dst" ]]; then
        run mkdir -p "$BACKUP_DIR"
        run mv "$dst" "$BACKUP_DIR/"
        warn "Đã sao lưu $dst -> $BACKUP_DIR/"
    fi
    run mkdir -p "$(dirname "$dst")"
    run ln -sfn "$src" "$dst"
    ok "$dst -> $src"
}

step_link() {
    step "[link] Liên kết cấu hình vào $CONFIG"
    for d in "${LINK_DIRS[@]}"; do link_one "$REPO_DIR/$d" "$CONFIG/$d"; done
    # GTK3: chỉ liên kết từng file để giữ bookmarks và các file khác của GTK
    link_one "$REPO_DIR/gtk/gtk-3.0/settings.ini" "$CONFIG/gtk-3.0/settings.ini"
    link_one "$REPO_DIR/gtk/gtk-3.0/gtk.css"      "$CONFIG/gtk-3.0/gtk.css"
    # hypr/wallpapers -> ../wallpapers (hyprland.lua, hyprlock, fastfetch đọc ảnh qua ~/.config/hypr/wallpapers)
    if [[ ! -L "$REPO_DIR/hypr/wallpapers" ]]; then run ln -sfn ../wallpapers "$REPO_DIR/hypr/wallpapers"; fi
    ok "hypr/wallpapers -> ../wallpapers"
}

# ---------- 3. ảnh ----------
WP="$REPO_DIR/wallpapers"
MAIN_WP="$WP/kafka_landscape_3.jpg"   # hình nền chính (ngang)
PORTRAIT="$WP/kafka_main.jpg"         # ảnh dọc: cắt banner rofi / nền walker / ảnh vuông

make_placeholder() {   # make_placeholder <file> <WxH>: gradient màu Kafka, dùng khi chưa có ảnh nền
    run magick -size "$2" gradient:'#2c2434'-'#c94785' -rotate 90 -resize "$2!" \
        -fill '#140f19' -colorize 35% "$1"
}

step_assets() {
    step "[assets] Ảnh nền và ảnh phụ"
    command -v magick >/dev/null || { (( DRY )) || { warn "Thiếu imagemagick (lệnh magick): bỏ qua bước ảnh."; return; }; }
    run mkdir -p "$WP"
    if [[ ! -f "$MAIN_WP" ]]; then
        warn "Chưa có $MAIN_WP — repo không kèm ảnh Kafka (bản quyền). Tạo ảnh gradient tạm."
        warn "Đặt ảnh của bạn vào wallpapers/ rồi chạy: ./install.sh --only assets   (xem wallpapers/README.md)"
        make_placeholder "$MAIN_WP" 1920x1080
    else
        ok "Hình nền chính: wallpapers/kafka_landscape_3.jpg"
    fi
    local src="$PORTRAIT"
    if [[ ! -f "$src" ]]; then
        warn "Chưa có wallpapers/kafka_main.jpg (ảnh dọc) — cắt ảnh phụ từ hình nền chính."
        src="$MAIN_WP"
    fi
    # Mỗi ảnh phụ chỉ tạo khi còn thiếu (hoặc --force-assets)
    need() { [[ $FORCE_ASSETS -eq 1 || ! -f "$1" ]] || { info "${c_dim}đã có: ${1#"$REPO_DIR"/}${c_off}"; return 1; }; }
    # Banner rofi: đúng 300x476 (= khung, không để rofi tự co)
    need "$REPO_DIR/rofi/kafka-banner.jpg" && run magick "$src" -filter Lanczos -resize 300x476^ -gravity north -extent 300x476 -unsharp 0x0.6 -quality 92 \
        "$REPO_DIR/rofi/kafka-banner.jpg"
    # Nền khung walker: 600x480, nhòe sẵn
    need "$REPO_DIR/walker/themes/kafka/bg.jpg" && run magick "$src" -resize 600x480^ -gravity north -extent 600x480 -gaussian-blur 0x14 \
        "$REPO_DIR/walker/themes/kafka/bg.jpg"
    # Ảnh vuông cho fastfetch + hyprlock
    need "$WP/Kafka_thumbail.jpg" && run magick "$src" -resize 512x512^ -gravity north -extent 512x512 -quality 92 "$WP/Kafka_thumbail.jpg"
    # Nền màn hình đăng nhập (greetd/ReGreet): nhòe + phủ tối
    need "$REPO_DIR/greetd/greeter-bg.jpg" && run magick "$MAIN_WP" -resize 1920x1080^ -gravity center -extent 1920x1080 -resize 25% -gaussian-blur 0x18 \
        -resize 1920x1080 -fill '#120c18' -colorize 62% "$REPO_DIR/greetd/greeter-bg.jpg"
    ok "Ảnh phụ: rofi/kafka-banner.jpg, walker/themes/kafka/bg.jpg, wallpapers/Kafka_thumbail.jpg, greetd/greeter-bg.jpg"
    # Ảnh đang dùng (màn hình khóa đọc symlink này)
    run mkdir -p "$HOME/.cache"
    [[ -e "$HOME/.cache/kafka_current_wallpaper" ]] || run ln -sfn "$MAIN_WP" "$HOME/.cache/kafka_current_wallpaper"
}

# ---------- 4. hệ thống ----------
step_system() {
    step "[system] Quyền chạy, file tự sinh, GTK, app mặc định"
    run chmod +x "$REPO_DIR"/hypr/scripts/*.sh "$REPO_DIR"/hypr/scripts/*.py "$REPO_DIR"/greetd/*.sh
    ok "chmod +x hypr/scripts/*, greetd/*.sh"
    # waybar/style.css @import file này; dock-density.sh ghi lại theo số cửa sổ
    if [[ ! -f "$REPO_DIR/waybar/dock-density.css" ]]; then
        if (( DRY )); then info "\$ tạo waybar/dock-density.css rỗng"
        else printf '/* Tự sinh bởi hypr/scripts/dock-density.sh — đừng sửa tay. */\n' > "$REPO_DIR/waybar/dock-density.css"; fi
    fi
    # Phím tắt riêng của người dùng (trình sửa phím ghi file này); thiếu thì tạo bảng rỗng
    if [[ ! -f "$REPO_DIR/hypr/keybinds.lua" ]]; then
        if (( DRY )); then info "\$ tạo hypr/keybinds.lua rỗng"
        else printf -- '-- Phím tắt riêng, do hypr/scripts/keybinds-editor.py ghi\nreturn {\n}\n' > "$REPO_DIR/hypr/keybinds.lua"; fi
    fi
    # waybar/style.css @import theme.css (theme phẳng/pixel do ui-theme.sh chọn); thiếu file thì Waybar mất CSS
    run "$REPO_DIR/hypr/scripts/ui-theme.sh" ensure
    ok "File tự sinh: waybar/dock-density.css, waybar/theme.css, hypr/keybinds.lua"
    # Font "Kafka Pixel" (font 5×7 của trình đăng nhập KAFKA.SYS) cho theme pixel: dựng TTF rồi liên kết vào ~/.local/share/fonts
    run python3 "$REPO_DIR/fonts/build-kafka-pixel-font.py"
    run mkdir -p "$HOME/.local/share/fonts"
    run ln -sfn "$REPO_DIR/fonts/KafkaPixel.ttf" "$HOME/.local/share/fonts/KafkaPixel.ttf"
    command -v fc-cache >/dev/null && run fc-cache -f "$HOME/.local/share/fonts"
    ok "Font Kafka Pixel"
    # GTK3 tối: theme PHẢI là "Adwaita" + prefer-dark (không có theme tên "Adwaita-dark" cho GTK3 → quay về sáng)
    if command -v gsettings >/dev/null; then
        run gsettings set org.gnome.desktop.interface gtk-theme 'Adwaita'
        run gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'
        ok "GTK: Adwaita + prefer-dark"
    fi
    # Icon "Kafka" (Papirus-Dark + thư mục hồng tím, mạng nhện) và con trỏ "Kafka-Cursor": dựng từ script trong repo
    run python3 "$REPO_DIR/icons/build-kafka-icons.py"
    run python3 "$REPO_DIR/cursors/build-kafka-cursor.py"
    run python3 "$REPO_DIR/cursors/build-kafka-pixel-cursor.py"   # bản pixel (đổi bằng hyprctl setcursor Kafka-Pixel 32)
    if command -v gsettings >/dev/null; then
        run gsettings set org.gnome.desktop.interface icon-theme 'Kafka'
        cur=Kafka-Cursor
        # bộ con trỏ tự tải (Windows .ani trong example/Kafka.zip, KHÔNG nằm trong git) → chuyển sang theme Kafka-BEN
        if [[ -f "$REPO_DIR/example/Kafka.zip" ]] && (( ! DRY )); then
            tmpd=$(mktemp -d); unzip -q -o "$REPO_DIR/example/Kafka.zip" -d "$tmpd" \
                && python3 "$REPO_DIR/cursors/ani2theme.py" "$(dirname "$(find "$tmpd" -iname '*.ani' | head -1)")" --name Kafka-BEN \
                && cur=Kafka-BEN; rm -rf "$tmpd"
        fi
        run gsettings set org.gnome.desktop.interface cursor-theme "$cur"
        run gsettings set org.gnome.desktop.interface cursor-size 32
    fi
    # app X/XWayland đọc con trỏ mặc định ở ~/.icons/default
    if (( DRY )); then info "\$ ghi ~/.icons/default/index.theme (Inherits=Kafka-Cursor)"
    else mkdir -p "$HOME/.icons/default"; printf '[Icon Theme]\nInherits=Kafka-Cursor\n' > "$HOME/.icons/default/index.theme"; fi
    ok "Icon Kafka + con trỏ Kafka-Cursor"
    if command -v xdg-mime >/dev/null; then
        local m
        for m in image/jpeg image/png image/gif image/webp image/bmp image/tiff image/svg+xml image/avif image/heif image/jxl; do
            run xdg-mime default imv-dir.desktop "$m"; done
        for m in video/mp4 video/x-matroska video/webm video/quicktime video/x-msvideo video/mpeg video/ogg video/x-flv \
                 audio/mpeg audio/flac audio/ogg audio/x-wav audio/mp4; do
            run xdg-mime default mpv.desktop "$m"; done
        for m in text/plain text/markdown text/x-log application/x-shellscript text/x-python application/json application/xml text/x-csrc; do
            run xdg-mime default org.xfce.mousepad.desktop "$m"; done
        run xdg-mime default thunar.desktop inode/directory
        ok "App mặc định: ảnh imv, video/nhạc mpv, văn bản mousepad, thư mục thunar"
    fi
}

# ---------- 5. fcitx5 ----------
step_fcitx() {
    step "[fcitx] Bộ gõ tiếng Việt (fcitx5 + Unikey)"
    local dir="$CONFIG/fcitx5"
    if [[ -f "$dir/profile" && $FORCE_FCITX -eq 0 ]] && grep -q 'Name=unikey' "$dir/profile"; then
        ok "Đã có cấu hình fcitx5 với unikey (ghi đè: --force-fcitx)"; return
    fi
    if (( DRY )); then info "\$ ghi $dir/profile, $dir/config, $dir/conf/unikey.conf"; return; fi
    mkdir -p "$dir/conf"
    for f in profile config conf/unikey.conf; do
        [[ -f "$dir/$f" ]] && cp "$dir/$f" "$dir/$f.bak-$STAMP"
    done
    # Bộ gõ ĐỨNG ĐẦU nhóm = trạng thái TẮT → keyboard-us trước, unikey sau (để ngược thì "bật" lại ra tiếng Anh)
    cat > "$dir/profile" <<'EOF'
[Groups/0]
Name=Default
Default Layout=us
DefaultIM=unikey

[Groups/0/Items/0]
Name=keyboard-us
Layout=

[Groups/0/Items/1]
Name=unikey
Layout=

[GroupOrder]
0=Default
EOF
    # Một trạng thái cho mọi cửa sổ; bật sẵn tiếng Việt (Unikey tự trả chữ tiếng Anh khi gõ sai dấu)
    cat > "$dir/config" <<'EOF'
[Hotkey]
EnumerateWithTriggerKeys=True

[Hotkey/TriggerKeys]
0=Control+space

[Behavior]
ActiveByDefault=True
ShareInputState=All
PreeditEnabledByDefault=True
EOF
    cat > "$dir/conf/unikey.conf" <<'EOF'
InputMethod=Telex
OutputCharset=Unicode
SpellCheck=True
Macro=False
AutoNonVnRestore=True
EOF
    ok "Đã ghi cấu hình fcitx5 (Ctrl+Space bật/tắt; bản cũ: *.bak-$STAMP)"
    # fcitx5 đang chạy sẽ ghi đè profile bằng bản trong bộ nhớ khi thoát thường → diệt hẳn rồi chạy lại
    local real_home; real_home="$(getent passwd "$(id -un)" | cut -d: -f6)"
    if [[ "$dir" == "$real_home/.config/fcitx5" ]] && pgrep -x fcitx5 >/dev/null; then
        pkill -9 -x fcitx5 || true
        if command -v hyprctl >/dev/null && [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
            hyprctl dispatch "hl.dsp.exec_cmd('fcitx5 -d')" >/dev/null || true
        fi
        info "Đã khởi động lại fcitx5 (cửa sổ đang mở có thể cần mở lại mới gõ có dấu)."
    fi
}

# ---------- 6. dịch vụ ----------
step_services() {
    step "[services] Dịch vụ hệ thống"
    local s
    for s in NetworkManager bluetooth power-profiles-daemon warp-svc; do
        if systemctl list-unit-files "$s.service" >/dev/null 2>&1; then
            run sudo systemctl enable --now "$s.service" && ok "$s"
        else
            warn "Không có $s.service (chưa cài gói?)"
        fi
    done
    if systemctl --user list-unit-files elephant.service >/dev/null 2>&1; then
        run systemctl --user enable elephant.service && ok "elephant (user) — Hyprland tự start khi đăng nhập"
    else
        warn "Không có elephant.service (cài elephant-bin từ AUR)"
    fi
    # WARP: đăng ký thiết bị miễn phí 1 lần (không cần tài khoản), chế độ toàn máy
    if command -v warp-cli >/dev/null 2>&1; then
        if warp-cli --accept-tos registration show >/dev/null 2>&1; then
            ok "WARP đã đăng ký"
        else
            run warp-cli --accept-tos registration new && run warp-cli --accept-tos mode warp && ok "WARP đã đăng ký (bật/tắt bằng nút VPN)"
        fi
    fi
}

step_greetd() {
    step "[greetd] Màn hình đăng nhập greetd + ReGreet"
    local args=(); [[ "$GREETD" == switch ]] && args=(--switch)
    run "$REPO_DIR/greetd/install-greetd.sh" "${args[@]}"
}

# ---------- 7. kiểm tra ----------
step_check() {
    step "[check] Kiểm tra"
    local fail=0 c
    local need=(Hyprland hyprctl waybar rofi walker hyprshell kitty dunst awww hyprlock hypridle grim slurp hyprshot satty
                wf-recorder cliphist wl-copy jq magick nmcli pactl wpctl brightnessctl powerprofilesctl upower playerctl
                fcitx5 fcitx5-remote python3 thunar mousepad imv mpv btop cava fastfetch)
    local missing=()
    for c in "${need[@]}"; do command -v "$c" >/dev/null || missing+=("$c"); done
    if ((${#missing[@]})); then warn "Còn thiếu lệnh: ${missing[*]}"; fail=1; else ok "Đủ ${#need[@]} lệnh cần thiết"; fi
    if python3 -c 'import gi; gi.require_version("Gtk","3.0"); gi.require_version("GtkLayerShell","0.1"); from gi.repository import Gtk, GtkLayerShell; import cairo' 2>/dev/null; then
        ok "Python: GTK3 + gtk-layer-shell + cairo"
    else
        warn "Thiếu python-gobject / gtk-layer-shell / python-cairo"; fail=1
    fi
    (( DRY )) && { info "(--dry-run: bỏ qua phần chạy thử)"; return; }
    if command -v Hyprland >/dev/null; then
        # KHÔNG dùng -c với .conf: Hyprland 0.57 hiểu nhầm là Lua. --verify-config đọc ~/.config/hypr/hyprland.lua
        if Hyprland --verify-config >/tmp/kafka-verify.$$ 2>&1; then ok "Hyprland --verify-config"
        else warn "Hyprland --verify-config lỗi:"; tail -n 5 /tmp/kafka-verify.$$ >&2; fail=1; fi
        rm -f /tmp/kafka-verify.$$
    fi
    local S="$REPO_DIR/hypr/scripts"
    local tests=("$S/column-map.sh --selftest" "python3 $S/control_backends.py --selftest" "python3 $S/dock-apps.py --selftest"
                 "python3 $S/lunar_vn.py --selftest" "python3 $S/corner-fillet.py --selftest" "$S/desktop-mode.sh --selftest"
                 "python3 $S/keybinds-editor.py --selftest")
    for c in "${tests[@]}"; do
        if bash -c "$c" >/dev/null 2>&1; then ok "selftest: ${c##*/}"; else warn "selftest LỖI: $c"; fail=1; fi
    done
    (( fail )) && warn "Có mục chưa đạt (xem ở trên)." || ok "Mọi kiểm tra đều đạt"
}

# ==============================================================================
preflight
want packages && step_packages
want link     && step_link
want assets   && step_assets
want system   && step_system
want fcitx    && step_fcitx
want services  && step_services
[[ -n "$GREETD" ]] && step_greetd
want check    && step_check

printf '\n%s━━ Hoàn tất ━━%s\n' "$c_grn" "$c_off"
info "• Đăng xuất rồi chọn phiên Hyprland (hoặc gõ start-hyprland ở TTY). Đang trong Hyprland: hyprctl reload"
info "• Ảnh nền riêng: đặt vào wallpapers/ rồi ./install.sh --only assets (xem wallpapers/README.md)"
info "• Màn hình đăng nhập Kafka: ./install.sh --only assets --greetd   (đổi hẳn: --greetd-switch)"
[[ -d "$BACKUP_DIR" ]] && info "• Cấu hình cũ đã sao lưu ở: $BACKUP_DIR"
exit 0
