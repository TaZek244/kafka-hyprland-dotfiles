#!/usr/bin/env bash
# ==============================================================================
#  install.sh — Cài bộ dotfiles Hyprland · Kafka (Honkai: Star Rail) Edition
#  Hỗ trợ: Arch Linux (đầy đủ) và Ubuntu/Debian (apt + danh sách cài tay).
#  Chạy được nhiều lần: cái đã đúng thì bỏ qua, cái cũ bị thay thì sao lưu vào
#  ~/.config/backup_before_kafka_<ngày giờ>/. Xem: ./install.sh --help
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$CONFIG/backup_before_kafka_$STAMP"

STEPS=(packages fonts link assets system fcitx services check)
declare -A STEP_DESC=(
    [packages]="Cài gói (pacman + AUR trên Arch, apt trên Ubuntu/Debian)"
    [fonts]="Nerd Font (Ubuntu/Debian: tự tải về ~/.local/share/fonts)"
    [link]="Symlink cấu hình vào ~/.config, sao lưu bản cũ"
    [assets]="Tạo ảnh phụ (banner rofi, nền walker, nền đăng nhập…) từ wallpapers/"
    [system]="Quyền chạy, file tự sinh, font pixel, icon, con trỏ, GTK tối, app mặc định"
    [fcitx]="Bộ gõ tiếng Việt fcitx5 + Unikey (Ctrl+Space)"
    [services]="Bật NetworkManager, bluetooth, power-profiles-daemon, WARP, elephant"
    [check]="Kiểm tra lệnh còn thiếu, Hyprland --verify-config, selftest"
)
# Thư mục cấu hình được symlink nguyên khối vào ~/.config/<tên>
LINK_DIRS=(hypr waybar rofi kitty dunst fastfetch cava hyprshell btop walker imv mpv)

DRY=0 YES=0 NO_AUR=0 FORCE_FCITX=0 FORCE_ASSETS=0 LIST_ONLY=0
GREETD="" ONLY="" SKIP=""
WARNINGS=0 STEP_WARN=0
declare -A RESULT
HAD_ARGS=$#

# ==============================================================================
#  Giao diện terminal
# ==============================================================================
c_pink=$'\033[1;35m' c_yel=$'\033[1;33m' c_grn=$'\033[1;32m' c_red=$'\033[1;31m' c_dim=$'\033[2m' c_off=$'\033[0m'
if [[ ! -t 1 ]]; then
    c_pink="" c_yel="" c_grn="" c_red="" c_dim="" c_off=""
fi

info() { printf '  %s\n' "$*"; }
ok() { printf '  %s✓%s %s\n' "$c_grn" "$c_off" "$*"; }
warn() {
    WARNINGS=$((WARNINGS + 1))
    STEP_WARN=$((STEP_WARN + 1))
    printf '  %s!%s %s\n' "$c_yel" "$c_off" "$*" >&2
}
die() {
    printf '%s✗ %s%s\n' "$c_red" "$*" "$c_off" >&2
    exit 1
}
# run: chạy lệnh, hoặc chỉ in ra ở --dry-run
run() {
    if ((DRY)); then
        printf '  %s$ %s%s\n' "$c_dim" "$*" "$c_off"
    else
        "$@"
    fi
}
# ask: hỏi có/không (Enter = có). -y hoặc --dry-run thì luôn "có".
ask() {
    ((YES || DRY)) && return 0
    local a
    read -r -p "  $* [Y/n] " a
    [[ -z "$a" || "$a" =~ ^[YyCc] ]]
}
# heading <bước> <tiêu đề>: in "━━ [3/8] link — …"
heading() {
    local i=0 total=${#STEPS[@]} s
    for s in "${STEPS[@]}"; do
        i=$((i + 1))
        [[ "$s" == "$1" ]] && break
    done
    if [[ "$1" == greetd ]]; then
        printf '\n%s━━ [+] %s — %s%s\n' "$c_yel" "$1" "$2" "$c_off"
    else
        printf '\n%s━━ [%d/%d] %s — %s%s\n' "$c_yel" "$i" "$total" "$1" "$2" "$c_off"
    fi
}

usage() {
    cat <<'EOF'
Cài bộ dotfiles Hyprland · Kafka (Arch Linux, Ubuntu/Debian).
Đừng chạy bằng sudo: script tự gọi sudo khi cần.

CÁCH DÙNG
  ./install.sh                  Mở menu chọn cách cài (khi chạy trong terminal)
  ./install.sh [tuỳ chọn]       Chạy thẳng, không menu

VÍ DỤ
  ./install.sh -y                         Cài đầy đủ, không hỏi
  ./install.sh --dry-run                  Xem trước sẽ làm gì, không đổi gì
  ./install.sh --only link,system,check   Chỉ liên kết cấu hình (không cài gói, không sudo)
  ./install.sh --skip packages,services   Tự cài gói rồi, chỉ cấu hình
  ./install.sh --only assets --force-assets   Tạo lại ảnh sau khi đổi ảnh trong wallpapers/
  ./install.sh --greetd-switch            Cài và chuyển hẳn sang màn hình đăng nhập greetd

CÁC BƯỚC (chạy theo thứ tự)
  packages  Cài gói (pacman + AUR trên Arch, apt trên Ubuntu/Debian)
  fonts     Nerd Font (Ubuntu/Debian: tự tải về ~/.local/share/fonts)
  link      Symlink cấu hình vào ~/.config, sao lưu bản cũ
  assets    Tạo ảnh phụ từ wallpapers/ (không có ảnh thì tạo ảnh gradient)
  system    Quyền chạy, file tự sinh, font pixel, icon, con trỏ, GTK tối, app mặc định
  fcitx     Bộ gõ tiếng Việt fcitx5 + Unikey (Ctrl+Space)
  services  Bật NetworkManager, bluetooth, power-profiles-daemon, WARP, elephant
  check     Kiểm tra lệnh còn thiếu, Hyprland --verify-config, selftest

TUỲ CHỌN
  --only <a,b>       Chỉ chạy các bước liệt kê
  --skip <a,b>       Bỏ qua các bước liệt kê
  --greetd           Cài thêm màn hình đăng nhập greetd (chưa đổi trình đăng nhập)
  --greetd-switch    Cài greetd và đổi hẳn sang nó (tắt gdm/gdm3/sddm/lightdm)
  -n, --dry-run      Chỉ in lệnh, không làm gì
  -y, --yes          Không hỏi xác nhận
  --no-aur           (Arch) Bỏ qua gói AUR
  --force-fcitx      Ghi đè cấu hình fcitx5 đang có
  --force-assets     Tạo lại cả ảnh phụ đã có
  --list             In danh sách bước rồi thoát
  -h, --help         In trợ giúp này
EOF
    exit 0
}

list_steps() {
    local s
    printf 'Các bước của install.sh:\n'
    for s in "${STEPS[@]}"; do printf '  %-9s %s\n' "$s" "${STEP_DESC[$s]}"; done
}

# ==============================================================================
#  Tham số, distro, menu
# ==============================================================================
while (($#)); do
    case "$1" in
        --only)
            ONLY="${2:?--only cần danh sách bước}"
            shift
            ;;
        --only=*) ONLY="${1#*=}" ;;
        --skip)
            SKIP="${2:?--skip cần danh sách bước}"
            shift
            ;;
        --skip=*) SKIP="${1#*=}" ;;
        --greetd) GREETD=install ;;
        --greetd-switch) GREETD=switch ;;
        -n | --dry-run) DRY=1 ;;
        -y | --yes) YES=1 ;;
        --no-aur) NO_AUR=1 ;;
        --force-fcitx) FORCE_FCITX=1 ;;
        --force-assets) FORCE_ASSETS=1 ;;
        --list) LIST_ONLY=1 ;;
        -h | --help) usage ;;
        *) die "Tham số lạ: $1 (xem ./install.sh --help)" ;;
    esac
    shift
done

if ((LIST_ONLY)); then
    list_steps
    exit 0
fi
for s in ${ONLY//,/ } ${SKIP//,/ }; do
    [[ " ${STEPS[*]} " == *" $s "* ]] || die "Bước không tồn tại: $s (có: ${STEPS[*]})"
done
((EUID == 0)) && die "Đừng chạy bằng root/sudo: script tự gọi sudo khi cần."

# shellcheck source=SCRIPTDIR/lib/distro.sh
source "$REPO_DIR/lib/distro.sh"
distro_detect
export DRY # lib/distro.sh đọc DRY để chỉ in lệnh

# want <bước>: bước này có được chạy không
want() {
    [[ -n "$ONLY" && ",$ONLY," != *",$1,"* ]] && return 1
    [[ ",$SKIP," == *",$1,"* ]] && return 1
    return 0
}

banner() {
    printf '%s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n' "$c_pink"
    printf '  🕷  HYPRLAND · KAFKA (HONKAI: STAR RAIL) EDITION\n'
    printf '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n' "$c_off"
    info "Bản phân phối: $DISTRO_NAME"
    info "Repo:          $REPO_DIR"
    info "Cấu hình:      $CONFIG"
}

# Menu chỉ hiện khi chạy không tham số, trong terminal
menu() {
    local choice s
    printf '\nChọn cách cài:\n'
    printf '  1) Cài đầy đủ (mọi bước)                    — máy mới\n'
    printf '  2) Chỉ liên kết cấu hình + file tự sinh     — không cài gói, không sudo\n'
    printf '  3) Chọn từng bước\n'
    printf '  4) Chạy thử (--dry-run)                     — chỉ in lệnh\n'
    printf '  5) Cài màn hình đăng nhập (greetd)\n'
    printf '  q) Thoát\n'
    read -r -p 'Lựa chọn [1-5/q]: ' choice
    case "$choice" in
        1 | "") ;;
        2) ONLY=link,system,check ;;
        3)
            for s in "${STEPS[@]}"; do
                ask "Chạy bước $s (${STEP_DESC[$s]})?" || SKIP="${SKIP:+$SKIP,}$s"
            done
            ;;
        4) DRY=1 YES=1 ;;
        5) GREETD=install ONLY=none ;;
        q | Q) exit 0 ;;
        *) die "Lựa chọn không hợp lệ: $choice" ;;
    esac
}

show_plan() {
    local s n=0
    printf '\nSẽ chạy:\n'
    for s in "${STEPS[@]}"; do
        want "$s" || continue
        n=$((n + 1))
        printf '  %d. %-9s %s\n' "$n" "$s" "${STEP_DESC[$s]}"
    done
    [[ -n "$GREETD" ]] && printf '  +  %-9s %s\n' greetd "Màn hình đăng nhập greetd$([[ $GREETD == switch ]] && echo ' (đổi hẳn)')"
    ((DRY)) && info "${c_yel}Chế độ thử (--dry-run): không thay đổi gì.${c_off}"
    printf '\n'
}

# ==============================================================================
#  1. packages
# ==============================================================================
# install_group <nhóm…>: gom gói của các nhóm rồi cài một lần
install_groups() {
    local g p pkgs=() y=()
    ((YES || DRY)) && y=(-y)
    for g in "$@"; do
        while IFS= read -r p; do pkgs+=("$p"); done < <(pkg_list "$g")
    done
    ((${#pkgs[@]})) || return 0
    info "Gói (${#pkgs[@]}): ${pkgs[*]}"
    pkg_install "${y[@]}" "${pkgs[@]}"
}

aur_helper() {
    local h
    for h in yay paru; do
        command -v "$h" >/dev/null 2>&1 && {
            echo "$h"
            return 0
        }
    done
    return 0
}

install_yay() {
    ask "Chưa có yay/paru để cài gói AUR. Cài yay-bin bây giờ?" || return 1
    run sudo pacman -S --needed --noconfirm git base-devel
    if ((DRY)); then
        run git clone --depth 1 https://aur.archlinux.org/yay-bin.git /tmp/yay-bin
        run makepkg -si --noconfirm
        return 1
    fi
    local tmp
    tmp="$(mktemp -d)"
    git clone --depth 1 https://aur.archlinux.org/yay-bin.git "$tmp/yay-bin"
    (cd "$tmp/yay-bin" && makepkg -si --noconfirm)
    rm -rf -- "$tmp"
}

packages_arch() {
    install_groups core tools apps py ime fonts || return 1
    ask "Cài thêm app ghim trên dock ($(pkg_list optional | tr '\n' ' '))?" && install_groups optional

    local aur=() h
    mapfile -t aur < <(pkg_list aur)
    if ((NO_AUR)); then
        warn "Bỏ qua AUR (--no-aur). Tự cài sau: ${aur[*]}"
        return 0
    fi
    h="$(aur_helper)"
    if [[ -z "$h" ]]; then
        install_yay && h="$(aur_helper)"
    fi
    if [[ -z "$h" ]]; then
        if ((! DRY)); then
            warn "Không có yay/paru: tự cài ${aur[*]}"
            return 0
        fi
        h=yay # --dry-run: vẫn in lệnh như thể có yay
    fi
    info "Gói AUR qua $h: ${aur[*]}"
    local args=(-S --needed)
    ((YES)) && args+=(--noconfirm)
    [[ "$h" == yay ]] && args+=(--answerclean None --answerdiff None)
    run "$h" "${args[@]}" "${aur[@]}"
}

packages_debian() {
    local maybe=() missing=() y=()
    ((YES || DRY)) && y=(-y)
    run sudo apt-get update || return 1
    install_groups core tools apps py ime fonts || return 1
    ask "Cài thêm trình duyệt ghim trên dock ($(pkg_list optional | tr '\n' ' '))?" && install_groups optional

    # Gói chỉ có ở bản Ubuntu mới: cài cái có, ghi lại cái thiếu
    mapfile -t maybe < <(pkg_list maybe)
    mapfile -t missing < <(pkg_install_available "${y[@]}" "${maybe[@]}")
    ((${#missing[@]})) && warn "Không có trong apt (cần cài tay): ${missing[*]}"
    print_manual_list "${missing[@]}"
}

# print_manual_list [gói thiếu…]: khung "Cần cài thủ công" (Ubuntu/Debian)
print_manual_list() {
    local name how p
    printf '\n  %s┌─ Cần cài thủ công (kho apt không có hoặc quá cũ) ──────────────%s\n' "$c_yel" "$c_off"
    while IFS='|' read -r name how; do
        printf '  │ %s%s%s\n  │     %s\n' "$c_pink" "$name" "$c_off" "$how"
    done < <(pkg_manual)
    for p in "$@"; do
        printf '  │ %s%s%s\n  │     gói apt không có ở bản Ubuntu này\n' "$c_pink" "$p" "$c_off"
    done
    printf '  %s└────────────────────────────────────────────────────────────────%s\n' "$c_yel" "$c_off"
}

step_packages() {
    heading packages "Cài gói"
    case "$DISTRO" in
        arch) packages_arch ;;
        debian) packages_debian ;;
        *)
            warn "Không nhận diện được bản phân phối ($DISTRO_NAME): bỏ qua bước cài gói."
            warn "Tự cài các gói tương đương rồi chạy lại với --skip packages. Danh sách (tên trên Arch):"
            local g
            for g in core tools apps py ime fonts aur; do
                info "$g: $(DISTRO=arch pkg_list "$g" | tr '\n' ' ')"
            done
            return 0
            ;;
    esac
}

# ==============================================================================
#  2. fonts
# ==============================================================================
NERD_URL="https://github.com/ryanoasis/nerd-fonts/releases/latest/download"

step_fonts() {
    heading fonts "Nerd Font"
    if [[ "$DISTRO" != debian ]]; then
        ok "Nerd Font đến từ gói hệ thống (bước packages)"
        return 0
    fi
    if command -v fc-list >/dev/null && fc-list | grep -qi 'FiraCode Nerd'; then
        ok "Đã có FiraCode Nerd Font"
        return 0
    fi
    local need
    for need in curl unzip fc-cache; do
        command -v "$need" >/dev/null || ((DRY)) || {
            warn "Thiếu lệnh $need: không tải được Nerd Font."
            return 1
        }
    done

    local dest="$HOME/.local/share/fonts/NerdFonts" tmp="" font
    ((DRY)) || tmp="$(mktemp -d)"
    run mkdir -p "$dest"
    for font in FiraCode JetBrainsMono; do
        run curl -fL --retry 2 -o "${tmp:-/tmp}/$font.zip" "$NERD_URL/$font.zip"
        run unzip -q -o "${tmp:-/tmp}/$font.zip" '*.ttf' -d "$dest"
    done
    run fc-cache -f "$dest"
    [[ -n "$tmp" ]] && rm -rf -- "$tmp"
    ok "Nerd Font (FiraCode, JetBrainsMono) → $dest"
}

# ==============================================================================
#  3. link
# ==============================================================================
# link_one <nguồn trong repo> <đích>: symlink, sao lưu cái đang có
link_one() {
    local src="$1" dst="$2"
    if [[ -L "$dst" && "$(readlink -f "$dst")" == "$(readlink -f "$src")" ]]; then
        info "${c_dim}đã đúng: $dst${c_off}"
        return 0
    fi
    if [[ -e "$dst" || -L "$dst" ]]; then
        run mkdir -p "$BACKUP_DIR"
        run mv "$dst" "$BACKUP_DIR/"
        info "đã sao lưu $dst → $BACKUP_DIR/"
    fi
    run mkdir -p "$(dirname "$dst")"
    run ln -sfn "$src" "$dst"
    ok "$dst → $src"
}

step_link() {
    heading link "Liên kết cấu hình vào $CONFIG"
    local d
    for d in "${LINK_DIRS[@]}"; do
        link_one "$REPO_DIR/$d" "$CONFIG/$d"
    done
    # GTK3: chỉ liên kết từng file để giữ bookmarks và các file khác của GTK
    link_one "$REPO_DIR/gtk/gtk-3.0/settings.ini" "$CONFIG/gtk-3.0/settings.ini"
    link_one "$REPO_DIR/gtk/gtk-3.0/gtk.css" "$CONFIG/gtk-3.0/gtk.css"
    # hyprland.lua, hyprlock, fastfetch đọc ảnh qua ~/.config/hypr/wallpapers
    [[ -L "$REPO_DIR/hypr/wallpapers" ]] || run ln -sfn ../wallpapers "$REPO_DIR/hypr/wallpapers"
    ok "hypr/wallpapers → ../wallpapers"
}

# ==============================================================================
#  4. assets
# ==============================================================================
WP="$REPO_DIR/wallpapers"
MAIN_WP="$WP/kafka_landscape_3.jpg" # hình nền chính (ngang)
PORTRAIT="$WP/kafka_main.jpg"       # ảnh dọc: cắt banner rofi / nền walker / ảnh vuông

# Ubuntu/Debian có thể chỉ có ImageMagick 6 (lệnh convert, không có magick). Các script trong repo
# gọi magick → tạo ~/.local/bin/magick chuyển sang convert.
ensure_magick() {
    command -v magick >/dev/null && return 0
    command -v convert >/dev/null || ((DRY)) || return 1
    local shim="$HOME/.local/bin/magick"
    if ((DRY)); then
        info "\$ tạo $shim (exec convert \"\$@\")"
    else
        mkdir -p "$HOME/.local/bin"
        printf '#!/bin/sh\n# ImageMagick 6 không có lệnh magick (install.sh tạo)\nexec convert "$@"\n' >"$shim"
        chmod +x "$shim"
    fi
    export PATH="$HOME/.local/bin:$PATH"
    ok "Đã tạo $shim (ImageMagick 6)"
    if ! grep -qs '\.local/bin' "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc" 2>/dev/null; then
        warn "\$HOME/.local/bin có thể chưa nằm trong PATH: thêm export PATH=\"\$HOME/.local/bin:\$PATH\" vào ~/.profile"
    fi
}

# make_placeholder <file> <WxH>: gradient màu Kafka, dùng khi chưa có ảnh nền
make_placeholder() {
    run magick -size "$2" 'gradient:#2c2434-#c94785' -rotate 90 -resize "$2!" \
        -fill '#140f19' -colorize 35% "$1"
}

# need <file>: file chưa có (hoặc --force-assets) thì tạo
need() {
    if ((FORCE_ASSETS)) || [[ ! -f "$1" ]]; then return 0; fi
    info "${c_dim}đã có: ${1#"$REPO_DIR"/}${c_off}"
    return 1
}

step_assets() {
    heading assets "Ảnh nền và ảnh phụ"
    ensure_magick || {
        warn "Thiếu ImageMagick (magick/convert): bỏ qua bước ảnh."
        return 0
    }
    run mkdir -p "$WP"
    if [[ ! -f "$MAIN_WP" ]]; then
        warn "Chưa có wallpapers/kafka_landscape_3.jpg — repo không kèm ảnh Kafka (bản quyền). Tạo ảnh gradient tạm."
        info "Đặt ảnh của bạn vào wallpapers/ rồi chạy: ./install.sh --only assets --force-assets"
        make_placeholder "$MAIN_WP" 1920x1080
    else
        ok "Hình nền chính: wallpapers/kafka_landscape_3.jpg"
    fi
    local src="$PORTRAIT"
    if [[ ! -f "$src" ]]; then
        info "Chưa có wallpapers/kafka_main.jpg (ảnh dọc) — cắt ảnh phụ từ hình nền chính."
        src="$MAIN_WP"
    fi
    # Banner rofi: đúng 300x476 (= khung, không để rofi tự co)
    need "$REPO_DIR/rofi/kafka-banner.jpg" &&
        run magick "$src" -filter Lanczos -resize 300x476^ -gravity north -extent 300x476 \
            -unsharp 0x0.6 -quality 92 "$REPO_DIR/rofi/kafka-banner.jpg"
    # Nền khung walker: 600x480, nhòe sẵn
    need "$REPO_DIR/walker/themes/kafka/bg.jpg" &&
        run magick "$src" -resize 600x480^ -gravity north -extent 600x480 -gaussian-blur 0x14 \
            "$REPO_DIR/walker/themes/kafka/bg.jpg"
    # Ảnh vuông cho fastfetch + hyprlock
    need "$WP/Kafka_thumbail.jpg" &&
        run magick "$src" -resize 512x512^ -gravity north -extent 512x512 -quality 92 "$WP/Kafka_thumbail.jpg"
    # Nền màn hình đăng nhập (greetd): nhòe + phủ tối
    need "$REPO_DIR/greetd/greeter-bg.jpg" &&
        run magick "$MAIN_WP" -resize 1920x1080^ -gravity center -extent 1920x1080 -resize 25% \
            -gaussian-blur 0x18 -resize 1920x1080 -fill '#120c18' -colorize 62% "$REPO_DIR/greetd/greeter-bg.jpg"
    ok "Ảnh phụ: rofi/kafka-banner.jpg, walker/themes/kafka/bg.jpg, wallpapers/Kafka_thumbail.jpg, greetd/greeter-bg.jpg"
    # Ảnh đang dùng (màn hình khoá đọc symlink này)
    run mkdir -p "$HOME/.cache"
    [[ -e "$HOME/.cache/kafka_current_wallpaper" ]] || run ln -sfn "$MAIN_WP" "$HOME/.cache/kafka_current_wallpaper"
}

# ==============================================================================
#  5. system
# ==============================================================================
# write_file <đường dẫn> <nội dung>: ghi file nếu chưa có (in ra ở --dry-run)
write_if_missing() {
    [[ -f "$1" ]] && return 0
    if ((DRY)); then
        info "\$ tạo ${1#"$REPO_DIR"/}"
    else
        printf '%b' "$2" >"$1"
    fi
}

set_default_apps() {
    command -v xdg-mime >/dev/null || return 0
    local m
    for m in image/jpeg image/png image/gif image/webp image/bmp image/tiff image/svg+xml image/avif image/heif image/jxl; do
        run xdg-mime default imv-dir.desktop "$m"
    done
    for m in video/mp4 video/x-matroska video/webm video/quicktime video/x-msvideo video/mpeg video/ogg video/x-flv \
        audio/mpeg audio/flac audio/ogg audio/x-wav audio/mp4; do
        run xdg-mime default mpv.desktop "$m"
    done
    for m in text/plain text/markdown text/x-log application/x-shellscript text/x-python application/json \
        application/xml text/x-csrc; do
        run xdg-mime default org.xfce.mousepad.desktop "$m"
    done
    run xdg-mime default thunar.desktop inode/directory
    ok "App mặc định: ảnh imv, video/nhạc mpv, văn bản mousepad, thư mục thunar"
}

step_system() {
    heading system "Quyền chạy, file tự sinh, GTK, icon, con trỏ"
    if ((DRY)); then
        info "\$ chmod +x hypr/scripts/*.sh hypr/scripts/*.py greetd/*.sh"
    else
        chmod +x "$REPO_DIR"/hypr/scripts/*.sh "$REPO_DIR"/hypr/scripts/*.py "$REPO_DIR"/greetd/*.sh
    fi
    ok "chmod +x hypr/scripts/*, greetd/*.sh"
    ensure_magick || warn "Thiếu ImageMagick: hình nền/ảnh phụ có thể không tạo được."

    # File tự sinh: style.css @import dock-density.css; keybinds-editor.py ghi keybinds.lua
    write_if_missing "$REPO_DIR/waybar/dock-density.css" '/* Tự sinh bởi hypr/scripts/dock-density.sh — đừng sửa tay. */\n'
    write_if_missing "$REPO_DIR/hypr/keybinds.lua" '-- Phím tắt riêng, do hypr/scripts/keybinds-editor.py ghi\nreturn {\n}\n'
    # style.css @import theme.css (phẳng/pixel do ui-theme.sh chọn); thiếu file thì Waybar mất CSS
    run "$REPO_DIR/hypr/scripts/ui-theme.sh" ensure
    ok "File tự sinh: waybar/dock-density.css, waybar/theme.css, hypr/keybinds.lua"

    # Font "Kafka Pixel" (theme pixel): dựng TTF rồi liên kết vào ~/.local/share/fonts
    run python3 "$REPO_DIR/fonts/build-kafka-pixel-font.py"
    run mkdir -p "$HOME/.local/share/fonts"
    run ln -sfn "$REPO_DIR/fonts/KafkaPixel.ttf" "$HOME/.local/share/fonts/KafkaPixel.ttf"
    command -v fc-cache >/dev/null && run fc-cache -f "$HOME/.local/share/fonts"
    ok "Font Kafka Pixel"

    # Icon "Kafka" (Papirus-Dark + thư mục hồng tím) và con trỏ: dựng từ script trong repo
    run python3 "$REPO_DIR/icons/build-kafka-icons.py"
    run python3 "$REPO_DIR/cursors/build-kafka-cursor.py"
    run python3 "$REPO_DIR/cursors/build-kafka-pixel-cursor.py"
    local cur=Kafka-Cursor
    # Bộ con trỏ tự tải (Windows .ani trong example/Kafka.zip, KHÔNG nằm trong git) → theme Kafka-BEN
    if [[ -f "$REPO_DIR/example/Kafka.zip" ]] && ((! DRY)); then
        local tmpd
        tmpd="$(mktemp -d)"
        if unzip -q -o "$REPO_DIR/example/Kafka.zip" -d "$tmpd" &&
            python3 "$REPO_DIR/cursors/ani2theme.py" "$(dirname "$(find "$tmpd" -iname '*.ani' | head -1)")" --name Kafka-BEN; then
            cur=Kafka-BEN
        fi
        rm -rf -- "$tmpd"
    fi
    # GTK3 tối: theme PHẢI là "Adwaita" + prefer-dark ("Adwaita-dark" không có cho GTK3 → quay về sáng)
    if command -v gsettings >/dev/null; then
        run gsettings set org.gnome.desktop.interface gtk-theme 'Adwaita'
        run gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'
        run gsettings set org.gnome.desktop.interface icon-theme 'Kafka'
        run gsettings set org.gnome.desktop.interface cursor-theme "$cur"
        run gsettings set org.gnome.desktop.interface cursor-size 32
    fi
    # App X/XWayland đọc con trỏ mặc định ở ~/.icons/default
    run mkdir -p "$HOME/.icons/default"
    if ((DRY)); then
        info "\$ ghi ~/.icons/default/index.theme (Inherits=Kafka-Cursor)"
    else
        printf '[Icon Theme]\nInherits=Kafka-Cursor\n' >"$HOME/.icons/default/index.theme"
    fi
    ok "GTK tối, icon Kafka, con trỏ $cur"
    set_default_apps
}

# ==============================================================================
#  6. fcitx (cấu hình không nằm trong repo vì fcitx5 tự ghi đè file, phá symlink)
# ==============================================================================
step_fcitx() {
    heading fcitx "Bộ gõ tiếng Việt (fcitx5 + Unikey)"
    local dir="$CONFIG/fcitx5" f
    if [[ -f "$dir/profile" ]] && ((! FORCE_FCITX)) && grep -q 'Name=unikey' "$dir/profile"; then
        ok "Đã có cấu hình fcitx5 với unikey (ghi đè: --force-fcitx)"
        return 0
    fi
    if ((DRY)); then
        info "\$ ghi $dir/profile, $dir/config, $dir/conf/unikey.conf"
        return 0
    fi
    mkdir -p "$dir/conf"
    for f in profile config conf/unikey.conf; do
        [[ -f "$dir/$f" ]] && cp "$dir/$f" "$dir/$f.bak-$STAMP"
    done
    # Bộ gõ ĐỨNG ĐẦU nhóm = trạng thái TẮT → keyboard-us trước, unikey sau
    # (để ngược thì "bật" lại ra tiếng Anh)
    cat >"$dir/profile" <<'EOF'
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
    # Một trạng thái cho mọi cửa sổ; bật sẵn tiếng Việt (Unikey tự trả chữ tiếng Anh)
    cat >"$dir/config" <<'EOF'
[Hotkey]
EnumerateWithTriggerKeys=True

[Hotkey/TriggerKeys]
0=Control+space

[Behavior]
ActiveByDefault=True
ShareInputState=All
PreeditEnabledByDefault=True
EOF
    cat >"$dir/conf/unikey.conf" <<'EOF'
InputMethod=Telex
OutputCharset=Unicode
SpellCheck=True
Macro=False
AutoNonVnRestore=True
EOF
    ok "Đã ghi cấu hình fcitx5 (Ctrl+Space bật/tắt; bản cũ: *.bak-$STAMP)"
    # fcitx5 đang chạy sẽ ghi đè profile bằng bản trong bộ nhớ khi thoát thường → diệt hẳn rồi chạy lại
    local real_home
    real_home="$(getent passwd "$(id -un)" | cut -d: -f6)"
    if [[ "$dir" == "$real_home/.config/fcitx5" ]] && pgrep -x fcitx5 >/dev/null; then
        pkill -9 -x fcitx5 || true
        if command -v hyprctl >/dev/null && [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
            hyprctl dispatch "hl.dsp.exec_cmd('fcitx5 -d')" >/dev/null || true
        fi
        info "Đã khởi động lại fcitx5 (cửa sổ đang mở có thể cần mở lại mới gõ có dấu)."
    fi
}

# ==============================================================================
#  7. services
# ==============================================================================
# has_unit [--user] <tên>: unit có tồn tại không (Ubuntu: list-unit-files trả 0 cả khi không có → grep)
has_unit() {
    local scope=()
    [[ "$1" == --user ]] && {
        scope=(--user)
        shift
    }
    systemctl "${scope[@]}" list-unit-files "$1.service" 2>/dev/null | grep -qF "$1.service"
}

step_services() {
    heading services "Dịch vụ hệ thống"
    local s
    for s in NetworkManager bluetooth power-profiles-daemon warp-svc; do
        if has_unit "$s"; then
            run sudo systemctl enable --now "$s.service" && ok "$s"
        else
            warn "Không có $s.service (chưa cài gói?)"
        fi
    done
    if has_unit --user elephant; then
        run systemctl --user enable elephant.service && ok "elephant (user) — Hyprland tự start khi đăng nhập"
    else
        warn "Không có elephant.service (nguồn dữ liệu của walker, xem danh sách cài tay)"
    fi
    # WARP: đăng ký thiết bị miễn phí 1 lần (không cần tài khoản), chế độ toàn máy
    if command -v warp-cli >/dev/null; then
        if warp-cli --accept-tos registration show >/dev/null 2>&1; then
            ok "WARP đã đăng ký"
        else
            run warp-cli --accept-tos registration new && run warp-cli --accept-tos mode warp &&
                ok "WARP đã đăng ký (bật/tắt bằng nút VPN)"
        fi
    fi
}

# ==============================================================================
#  greetd (tuỳ chọn --greetd / --greetd-switch / menu 5)
# ==============================================================================
step_greetd() {
    heading greetd "Màn hình đăng nhập greetd"
    local args=()
    if [[ "$DISTRO" == debian ]] && ! command -v regreet >/dev/null; then
        # Kho apt không có ReGreet → trình đăng nhập pixel tự viết KAFKA.SYS (chỉ cần python3-gi)
        info "Ubuntu/Debian không có ReGreet: dùng KAFKA.SYS (greetd/kafka-greeter)."
        args=(--kafka)
    elif [[ "$GREETD" == switch ]]; then
        args=(--switch)
    fi
    run "$REPO_DIR/greetd/install-greetd.sh" "${args[@]}"
    if [[ "${args[0]:-}" == --kafka && "$GREETD" == switch ]]; then
        info "Bật greetd (tắt trình đăng nhập cũ):"
        local dm
        for dm in gdm gdm3 sddm lightdm; do
            has_unit "$dm" && run sudo systemctl disable "$dm.service"
        done
        run sudo systemctl enable greetd.service
    fi
}

# ==============================================================================
#  8. check
# ==============================================================================
# hint_for <lệnh>: cách có lệnh đó trên Ubuntu/Debian
hint_for() {
    local cmd="$1" name how
    while IFS='|' read -r name how; do
        [[ "${name,,}" == *"${cmd,,}"* ]] && {
            printf '%s' "$how"
            return 0
        }
    done < <(pkg_manual)
    case "$cmd" in
        Hyprland | hyprctl) cmd="Hyprland ≥ 0.57" ;;
        nmcli) cmd=network-manager ;;
        wl-copy) cmd=wl-clipboard ;;
        pactl) cmd=pulseaudio-utils ;;
        wpctl) cmd=wireplumber ;;
        powerprofilesctl) cmd=power-profiles-daemon ;;
        fcitx5-remote) cmd=fcitx5 ;;
    esac
    printf 'apt: %s' "$cmd"
}

step_check() {
    heading check "Kiểm tra"
    local fail=0 c missing=()
    local need=(Hyprland hyprctl waybar rofi walker hyprshell kitty dunst awww hyprlock hypridle grim slurp hyprshot
        satty wf-recorder cliphist wl-copy jq magick nmcli pactl wpctl brightnessctl powerprofilesctl upower playerctl
        fcitx5 fcitx5-remote python3 thunar mousepad imv mpv btop cava fastfetch)
    for c in "${need[@]}"; do
        command -v "$c" >/dev/null || missing+=("$c")
    done
    if ((${#missing[@]})); then
        warn "Còn thiếu lệnh: ${missing[*]}"
        if [[ "$DISTRO" == debian ]]; then
            for c in "${missing[@]}"; do info "  $c — $(hint_for "$c")"; done
        fi
        fail=1
    else
        ok "Đủ ${#need[@]} lệnh cần thiết"
    fi
    if python3 -c 'import gi; gi.require_version("Gtk","3.0"); gi.require_version("GtkLayerShell","0.1"); from gi.repository import Gtk, GtkLayerShell; import cairo' 2>/dev/null; then
        ok "Python: GTK3 + gtk-layer-shell + cairo"
    else
        warn "Thiếu PyGObject / gtk-layer-shell / pycairo"
        fail=1
    fi
    if ((DRY)); then
        info "(--dry-run: bỏ qua phần chạy thử)"
        return 0
    fi
    if command -v Hyprland >/dev/null; then
        # KHÔNG dùng -c với .conf: Hyprland 0.57 hiểu nhầm là Lua. --verify-config đọc ~/.config/hypr/hyprland.lua
        local out
        out="$(mktemp)"
        if Hyprland --verify-config >"$out" 2>&1; then
            ok "Hyprland --verify-config"
        else
            warn "Hyprland --verify-config lỗi:"
            tail -n 5 "$out" >&2
            fail=1
        fi
        rm -f "$out"
    fi
    local S="$REPO_DIR/hypr/scripts"
    local tests=("$S/column-map.sh --selftest" "python3 $S/control_backends.py --selftest"
        "python3 $S/dock-apps.py --selftest" "python3 $S/lunar_vn.py --selftest"
        "python3 $S/corner-fillet.py --selftest" "$S/desktop-mode.sh --selftest"
        "python3 $S/keybinds-editor.py --selftest")
    for c in "${tests[@]}"; do
        if bash -c "$c" >/dev/null 2>&1; then ok "selftest: ${c##*/}"; else
            warn "selftest LỖI: $c"
            fail=1
        fi
    done
    ((fail)) && return 1
    ok "Mọi kiểm tra đều đạt"
}

# ==============================================================================
#  Chạy
# ==============================================================================
# run_step <bước>: lỗi ở một bước không chặn các bước sau; ghi kết quả cho bảng tổng kết
run_step() {
    local s="$1"
    STEP_WARN=0
    if "step_$s"; then
        ((STEP_WARN)) && RESULT[$s]="cảnh báo ($STEP_WARN)" || RESULT[$s]="ok"
    else
        RESULT[$s]="lỗi"
        warn "Bước $s chưa xong, chạy tiếp các bước sau."
    fi
}

summary() {
    local s r color
    printf '\n%s━━ Tổng kết ━━%s\n' "$c_pink" "$c_off"
    for s in "${STEPS[@]}" greetd; do
        [[ "$s" == greetd && -z "$GREETD" ]] && continue
        r="${RESULT[$s]:-bỏ qua}"
        case "$r" in
            ok) color="$c_grn" ;;
            lỗi) color="$c_red" ;;
            "bỏ qua") color="$c_dim" ;;
            *) color="$c_yel" ;;
        esac
        printf '  %-9s %s%s%s\n' "$s" "$color" "$r" "$c_off"
    done

    printf '\n%sViệc tiếp theo%s\n' "$c_pink" "$c_off"
    info "• Đăng xuất rồi chọn phiên Hyprland (hoặc gõ start-hyprland ở TTY). Đang trong Hyprland: hyprctl reload"
    info "• Ảnh nền riêng: đặt vào wallpapers/ rồi ./install.sh --only assets --force-assets"
    [[ -z "$GREETD" ]] && info "• Màn hình đăng nhập Kafka: ./install.sh --greetd   (đổi hẳn: --greetd-switch)"
    if [[ "$DISTRO" == debian && "${RESULT[packages]:-bỏ qua}" != "bỏ qua" ]]; then
        info "• Ubuntu/Debian: cài tay các thành phần trong khung \"Cần cài thủ công\" ở trên, rồi ./install.sh --only check"
    fi
    [[ -d "$BACKUP_DIR" ]] && info "• Cấu hình cũ đã sao lưu ở: $BACKUP_DIR"
    ((DRY)) && info "• Đây là chạy thử: chưa có gì thay đổi."
    return 0
}

banner
if ((HAD_ARGS == 0)) && [[ -t 0 && -t 1 ]]; then
    menu
fi
show_plan
if ((! YES && ! DRY)); then
    ask "Bắt đầu?" || exit 0
fi

for s in "${STEPS[@]}"; do
    want "$s" && run_step "$s"
done
[[ -n "$GREETD" ]] && run_step greetd
summary
