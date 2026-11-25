#!/usr/bin/env bash
# lib/distro.sh — nhận diện bản phân phối + cài gói, dùng chung cho install.sh và greetd/install-greetd.sh.
#
#   source "$REPO_DIR/lib/distro.sh"
#   distro_detect            # đặt DISTRO = arch | debian | unknown, DISTRO_NAME = tên dễ đọc
#   pkg_list <nhóm>          # in tên gói của nhóm cho DISTRO hiện tại (mỗi dòng một gói)
#   pkg_available <gói>      # gói có trong kho của DISTRO không (0 = có)
#   pkg_install [-y] <gói…>  # cài bằng pacman / apt-get (bỏ qua gói đã có); -y = không hỏi
#   pkg_manual <nhóm>        # in danh sách "lệnh|cách cài" cho phần không có trong kho của DISTRO
#
# Biến DRY=1 (nếu nơi gọi đặt) → chỉ in lệnh, không cài.
# Nhóm gói (tên logic giống nhau ở mọi distro): core tools apps py ime fonts optional greetd

DISTRO="${DISTRO:-}"
DISTRO_NAME="${DISTRO_NAME:-}"

distro_detect() {
    local id="" like="" name=""
    # KAFKA_DISTRO=arch|debian: ép kiểu distro (để thử install.sh --dry-run trên máy khác)
    if [[ -n "${KAFKA_DISTRO:-}" ]]; then
        DISTRO="$KAFKA_DISTRO"
        DISTRO_NAME="$KAFKA_DISTRO (ép bằng KAFKA_DISTRO)"
        return 0
    fi
    if [[ -r /etc/os-release ]]; then
        # Đọc trong subshell (không để biến của os-release lọt ra ngoài): 3 dòng ID / ID_LIKE / tên
        {
            IFS= read -r id
            IFS= read -r like
            IFS= read -r name
        } < <(
            # shellcheck disable=SC1091
            . /etc/os-release
            printf '%s\n%s\n%s\n' "${ID:-}" "${ID_LIKE:-}" "${PRETTY_NAME:-${NAME:-}}"
        )
    fi
    case " $id $like " in
        *" arch "* | *" archlinux "*) DISTRO=arch ;;
        *" ubuntu "* | *" debian "*) DISTRO=debian ;;
        *)
            if command -v pacman >/dev/null 2>&1; then
                DISTRO=arch
            elif command -v apt-get >/dev/null 2>&1; then
                DISTRO=debian
            else
                DISTRO=unknown
            fi
            ;;
    esac
    DISTRO_NAME="${name:-$DISTRO}"
}

# ---------------------------------------------------------------------------
# Bảng gói. Mỗi nhóm: _pkgs_<distro>_<nhóm>. Tên không có trong kho thì đưa vào _manual_<distro>_<nhóm>.
# ---------------------------------------------------------------------------

# --- Arch (kho chính thức) ---
_pkgs_arch_core="hyprland hyprlock hypridle xdg-desktop-portal-hyprland xdg-desktop-portal-gtk
qt5-wayland qt6-wayland qt6ct polkit-gnome gnome-keyring
waybar rofi kitty dunst libnotify fastfetch awww cava btop"
_pkgs_arch_tools="grim slurp wl-clipboard cliphist hyprshot satty wf-recorder imagemagick jq unzip librsvg
networkmanager network-manager-applet bluez blueman util-linux
pipewire pipewire-pulse wireplumber libpulse pavucontrol playerctl
brightnessctl power-profiles-daemon upower"
_pkgs_arch_apps="thunar gvfs gvfs-mtp gvfs-smb gvfs-afc gvfs-gphoto2 tumbler mousepad imv mpv"
_pkgs_arch_py="python python-gobject python-cairo gtk3 gtk4 gtk-layer-shell gtk4-layer-shell gtksourceview4"
_pkgs_arch_ime="fcitx5 fcitx5-unikey fcitx5-gtk fcitx5-qt fcitx5-configtool"
_pkgs_arch_fonts="ttf-firacode-nerd ttf-jetbrains-mono-nerd noto-fonts noto-fonts-emoji
papirus-icon-theme adwaita-icon-theme gsettings-desktop-schemas"
_pkgs_arch_optional="chromium code"
_pkgs_arch_greetd="greetd greetd-regreet cage python-gobject python-cairo"
# AUR (cài qua yay/paru)
_pkgs_arch_aur="hyprshell-bin walker-bin elephant-bin elephant-desktopapplications-bin elephant-runner-bin
elephant-windows-bin elephant-calc-bin elephant-symbols-bin cloudflare-warp-bin"

# --- Ubuntu / Debian (apt) ---
# Lưu ý: kho Ubuntu thường có Hyprland CŨ (< 0.57, chưa đọc cấu hình Lua) → xem _manual_debian_core.
_pkgs_debian_core="xdg-desktop-portal-gtk qtwayland5 qt6-wayland qt6ct policykit-1-gnome gnome-keyring
waybar kitty dunst libnotify-bin cava btop"
_pkgs_debian_tools="grim slurp wl-clipboard wf-recorder imagemagick jq unzip librsvg2-bin curl
network-manager network-manager-gnome bluez blueman util-linux rfkill
pipewire pipewire-pulse wireplumber pulseaudio-utils pavucontrol playerctl
brightnessctl power-profiles-daemon upower"
_pkgs_debian_apps="thunar gvfs gvfs-backends tumbler mousepad imv mpv"
_pkgs_debian_py="python3 python3-gi python3-gi-cairo python3-cairo gir1.2-gtk-3.0 gir1.2-gtk-4.0
libgtk-layer-shell0 gir1.2-gtklayershell-0.1 gir1.2-gtksource-4"
_pkgs_debian_ime="fcitx5 fcitx5-unikey fcitx5-frontend-gtk3 fcitx5-frontend-gtk4 fcitx5-frontend-qt5 fcitx5-config-qt"
_pkgs_debian_fonts="fonts-noto-core fonts-noto-color-emoji papirus-icon-theme adwaita-icon-theme gsettings-desktop-schemas"
_pkgs_debian_optional="chromium-browser"
_pkgs_debian_greetd="greetd cage python3-gi python3-gi-cairo python3-cairo"
# Có ở bản Ubuntu mới (24.10+) nhưng chưa chắc có ở bản cũ → thử từng gói, thiếu thì báo
_pkgs_debian_maybe="hyprland hyprlock hypridle xdg-desktop-portal-hyprland fastfetch cliphist rofi
libgtk4-layer-shell0 gir1.2-gtk4layershell-1.0 fcitx5-frontend-qt6"

# Phần không có trong kho apt: "lệnh|cách cài"
_manual_debian="Hyprland ≥ 0.57|Kho Ubuntu thường chỉ có bản cũ (cấu hình .conf). Dựng từ mã nguồn: https://wiki.hypr.land/Getting-Started/Installation/
hyprlock, hypridle|Cùng hệ sinh thái Hyprland (dựng từ mã nguồn nếu apt không có)
rofi ≥ 2.0 (Wayland)|apt có thể chỉ có rofi X11: https://github.com/davatorium/rofi (dựng với -Dxcb=disabled)
awww|Hình nền (tên cũ swww): https://codeberg.org/LGFae/awww (cargo build --release)
hyprshell|Tổng quan + Alt+Tab: https://github.com/H3rmt/hyprshell (cargo install hyprshell)
walker + elephant (+ plugin)|Trình mở app: https://github.com/abenz1267/walker và https://github.com/abenz1267/elephant (bản phát hành dựng sẵn)
hyprshot|Chụp màn hình (một script): https://github.com/Gustash/Hyprshot
satty|Vẽ lên ảnh chụp: https://github.com/gabm/Satty (cargo install satty)
cliphist|Lịch sử clipboard: go install go.senan.xyz/cliphist@latest (nếu apt không có)
cloudflare-warp|VPN của nút VPN: kho apt chính thức https://pkg.cloudflareclient.com/
FiraCode / JetBrainsMono Nerd Font|install.sh tự tải về ~/.local/share/fonts (bước fonts)
ReGreet|Trình đăng nhập GTK: không có trong apt → dùng KAFKA.SYS (install-greetd.sh --kafka) hoặc cargo install"

pkg_list() {
    local var="_pkgs_${DISTRO}_$1"
    [[ -n "${!var:-}" ]] && tr -s ' \n' '\n' <<<"${!var}" | sed '/^$/d'
    return 0
}

pkg_manual() {
    [[ "$DISTRO" == debian ]] && printf '%s\n' "$_manual_debian"
    return 0
}

pkg_available() {
    case "$DISTRO" in
        arch) pacman -Si "$1" >/dev/null 2>&1 ;;
        debian) [[ -n "$(apt-cache policy "$1" 2>/dev/null | awk '/Candidate:/ && $2 != "(none)" {print $2}')" ]] ;;
        *) return 1 ;;
    esac
}

pkg_installed() {
    case "$DISTRO" in
        arch) pacman -Qq "$1" >/dev/null 2>&1 ;;
        debian) dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q 'install ok installed' ;;
        *) return 1 ;;
    esac
}

_pkg_run() {
    if [[ "${DRY:-0}" == 1 ]]; then
        printf '  $ %s\n' "$*"
    else
        "$@"
    fi
}

pkg_install() {
    local yes=0
    [[ "${1:-}" == -y ]] && {
        yes=1
        shift
    }
    (($#)) || return 0
    case "$DISTRO" in
        arch)
            local a=(-S --needed)
            ((yes)) && a+=(--noconfirm)
            _pkg_run sudo pacman "${a[@]}" "$@"
            ;;
        debian)
            local a=(install --no-install-recommends)
            ((yes)) && a+=(-y)
            _pkg_run sudo apt-get "${a[@]}" "$@"
            ;;
        *)
            echo "Không biết cách cài gói trên bản phân phối này. Tự cài: $*" >&2
            return 1
            ;;
    esac
}

# Cài những gói có trong kho, in ra (stdout) những gói không tìm thấy. Dùng cho danh sách "có thể có".
pkg_install_available() {
    local yes_flag=() p ok=() miss=()
    [[ "${1:-}" == -y ]] && {
        yes_flag=(-y)
        shift
    }
    for p in "$@"; do
        if pkg_available "$p"; then ok+=("$p"); else miss+=("$p"); fi
    done
    ((${#ok[@]})) && pkg_install "${yes_flag[@]}" "${ok[@]}" >&2
    ((${#miss[@]})) && printf '%s\n' "${miss[@]}"
    return 0
}
