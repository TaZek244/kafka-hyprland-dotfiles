# 🕷 Kafka Hyprland Dotfiles

Hyprland 0.57+ Lua configuration (`hypr/hyprland.lua`) themed after **Kafka (Honkai: Star Rail)** for Arch Linux and Ubuntu/Debian, with live switching between a modern flat UI and a pixel "RPG HUD" theme.

## Features

* **Scrolling & Desktop Modes**: Horizontal scrolling column layout (`scrolling`) with instant toggle to free-floating Desktop mode (`Super + D`).
* **Unified L-Frame Shell**: Top status bar and right vertical dock (`waybar`) merged into an L-shaped frame with app grouping and `xN` instance badges.
* **Flat & Pixel RPG HUD Themes**: Live toggle (`Super + Alt + U`) between flat styling and a pixel RPG HUD with character card and stat bars.
* **Popups & Daemons**: Control center popup (Wi-Fi, Bluetooth, Cloudflare WARP / WireGuard VPN, audio, brightness), synced LRCLIB lyrics & Cava visualizer pill, peripheral battery monitor (UPower, BlueZ, Solaar), and threshold alerts (`hypr/alerts.json`).
* **Launchers & Greeter**: GTK4 app launcher (`walker` + `elephant` with `=` calc and `.` emoji), `hyprshell` overview/switcher, theme-aware `hyprlock`, and `greetd` login supporting **ReGreet** (GTK4) and **KAFKA.SYS** (custom pixel greeter) with `agreety` fallback.
* **Kafka Studio & Custom Assets**: GUI settings tool (`hypr/scripts/studio.py`), keybind editor (`hypr/scripts/keybinds-editor.py`), custom Papirus folder icons (`Kafka`), and cursor themes (`Kafka-Cursor`, `Kafka-Pixel`, `Kafka-BEN`).

Keybindings reference: [KEYBINDINGS.md](KEYBINDINGS.md).

## Requirements

* **Reference Resolution**: 1920x1080 (1080p).
* **Arch Linux (full support)**: Automated package installation via `pacman` and AUR (`yay` or `paru`; `install.sh` can bootstrap `yay-bin`).
* **Ubuntu / Debian (partial automation)**: `apt` installs base packages, downloads Nerd Fonts to `~/.local/share/fonts/NerdFonts`, and creates a `~/.local/bin/magick` wrapper for ImageMagick 6. Missing/outdated `apt` packages must be installed manually (printed by `install.sh`):
  * **Required**: `Hyprland >= 0.57` (Lua config), `hyprlock`, `hypridle`, `rofi >= 2.0` (Wayland).
  * **Companion tools**: `awww`, `hyprshell`, `walker` + `elephant` (with plugins), `hyprshot`, `satty`, `cliphist`, `cloudflare-warp` (`pkg.cloudflareclient.com`), and `ReGreet` (optional; defaults to `KAFKA.SYS` on Debian/Ubuntu).

## Installation & Usage

```bash
git clone https://github.com/TaZek244/kafka-hyprland-dotfiles.git ~/kafka-hyprland-dotfiles
cd ~/kafka-hyprland-dotfiles && ./install.sh
```

Do **not** run with `sudo`; the script calls `sudo` only when needed. Running `./install.sh` without arguments opens an interactive menu (`1` Full install, `2` Link configs + system + check without `sudo`, `3` Pick steps, `4` `--dry-run`, `5` Install `greetd`, `6` Optional extras `grub`/`health`).

| Step | Action |
| :--- | :--- |
| `packages` | Install packages (`pacman` + AUR on Arch; `apt` + manual checklist on Ubuntu/Debian). |
| `fonts` | Install FiraCode and JetBrainsMono Nerd Fonts (auto-downloaded on Ubuntu/Debian). |
| `link` | Symlink configs into `~/.config` (backs up existing paths to `~/.config/backup_before_kafka_<timestamp>`). |
| `assets` | Generate Rofi banner, Walker background, thumbnail, and greeter background from `wallpapers/`. |
| `system` | Set script permissions, generate runtime stubs, build pixel font, icons, cursors, dark GTK3, and XDG default apps. |
| `fcitx` | Write `fcitx5` + Unikey Vietnamese IME config (`Ctrl + Space` toggle). |
| `services` | Enable `NetworkManager`, `bluetooth`, `power-profiles-daemon`, `warp-svc`, and user service `elephant`. |
| `check` | Verify required binaries, Python GTK/LayerShell modules, `Hyprland --verify-config`, and script selftests. |

```bash
./install.sh --list                        # List steps and optional extras
./install.sh -n / -y                       # Dry run (--dry-run) / non-interactive (--yes)
./install.sh --only link,system,check      # Link configs and build user assets without sudo
./install.sh --skip packages --no-aur      # Skip package step or skip AUR packages on Arch
./install.sh --only assets --force-assets  # Rebuild derived images after changing wallpapers/
./install.sh --only fcitx --force-fcitx    # Overwrite existing fcitx5 profile/config
./install.sh --greetd / --greetd-switch    # Install greetd / also disable gdm/sddm/lightdm & enable greetd
./install.sh --extras grub,health          # Install optional sibling repos (aliases: --grub, --health)
./install.sh --only none --extras health   # Install only an optional extra, skip the main steps
```

* **Login Manager (`greetd`)**: Arch installs **ReGreet** by default (use `./greetd/install-greetd.sh --kafka` for **KAFKA.SYS**, `--regreet` to switch back, `--theme` to sync CSS, `--cursors` to copy cursors). Ubuntu/Debian uses **KAFKA.SYS** automatically if `regreet` is absent. Auto-detects `greeter` (Arch) or `_greetd` (Ubuntu/Debian).
* **Optional Extras (`--extras`)**: Searches `KAFKA_GRUB_REPO` / `KAFKA_HEALTH_REPO`, sibling directories, `~/Desktop`, `~`, and `~/.local/src`, prompting to clone if missing:
  * `grub` ([**grub-theme-3os**](https://github.com/TaZek244/grub-theme-3os)): `KAFKA.SYS` Plymouth splash and GRUB theme (`sudo`; passes `--ubuntu` on Debian/Ubuntu, extra args via `KAFKA_GRUB_ARGS`; check partition UUIDs in its `lib/config.sh` first).
  * `health` (**pc-health-watch**): Freeze pre-warning and post-reset blackbox (`systemd --user`; private repo requiring `gh auth login` or pre-cloned `KAFKA_HEALTH_REPO`; run `install.sh --setup-system` in its repo for system hooks).

## Configuration & Troubleshooting

* **Wallpapers**: No copyrighted Kafka artwork is bundled. Place `kafka_landscape_3.jpg` (16:9) and `kafka_main.jpg` (portrait) in `wallpapers/` and run `./install.sh --only assets --force-assets` (generates gradient placeholders if empty).
* **Kafka Studio & Keybinds**: Run `python3 ~/.config/hypr/scripts/studio.py` (or from the dock) to configure wallpapers, `@define-color` palettes (`waybar/style.css`, `waybar/theme-pixel.css`), themes, configs, and alerts. Edit custom keybinds via `python3 ~/.config/hypr/scripts/keybinds-editor.py` (`hypr/keybinds.lua`).
* **Troubleshooting**:
  * **Vietnamese IME**: Run `~/.config/hypr/scripts/ime-guard.sh status` or middle-click `VI / EN` on the topbar to restart `fcitx5` (reopen existing terminals).
  * **Waybar / Reload**: Reload config with `hyprctl reload` or `killall -SIGUSR2 waybar`. If the system tray disappears, restart via Hyprland: `killall waybar; hyprctl dispatch "hl.dsp.exec_cmd('waybar')"`.
  * **Walker empty list**: Match `elephant` and plugin versions, then run `systemctl --user restart elephant.service; pkill -x walker; setsid -f walker --gapplication-service`.
  * **Broken `greetd`**: In TTY (`Ctrl + Alt + F2`), run `~/kafka-hyprland-dotfiles/greetd/install-greetd.sh --revert` (or copy `/etc/greetd/config-fallback.toml` to `/etc/greetd/config.toml`) to fall back to `agreety`.

## Uninstall

Remove symlinks in `~/.config` (`hypr`, `waybar`, `rofi`, `kitty`, `dunst`, `fastfetch`, `cava`, `hyprshell`, `btop`, `walker`, `imv`, `mpv`, `gtk-3.0/{settings.ini,gtk.css}`), restore `~/.config/backup_before_kafka_<timestamp>/`, remove `~/.local/share/icons/{Kafka,Kafka-Cursor,Kafka-Pixel,Kafka-BEN}` and `~/.local/share/fonts/KafkaPixel.ttf`, and run `./greetd/install-greetd.sh --revert` if `greetd` was enabled.

## Project Layout

* `install.sh`, `lib/distro.sh`: Installer and distro package definitions (Arch & Ubuntu/Debian).
* `hypr/`: `hyprland.lua`, `hyprlock*.conf`, `hypridle.conf`, `alerts.json`, and helper scripts (`hypr/scripts/`).
* `waybar/`, `walker/`, `rofi/`, `greetd/`: Bar/dock configs, launcher themes, Rofi menus, ReGreet & `KAFKA.SYS` greeter.
* `cursors/`, `icons/`, `fonts/`, `gtk/`: Builders for Kafka cursors, Papirus folder icons, `KafkaPixel.ttf`, and GTK3 dark theme.
* `kitty/`, `dunst/`, `cava/`, `fastfetch/`, `hyprshell/`, `btop/`, `imv/`, `mpv/`: Component configs.

## Credits

Built on [Hyprland](https://hypr.land/), [Waybar](https://github.com/Alexays/Waybar), [Walker](https://github.com/abenz1267/walker) & [Elephant](https://github.com/abenz1267/elephant), [hyprshell](https://github.com/H3rmt/hyprshell), [Rofi](https://github.com/davatorium/rofi), [ReGreet](https://github.com/rharish101/ReGreet), [Kitty](https://sw.kovidgoyal.net/kitty/), [Dunst](https://dunst-project.org/), [Cava](https://github.com/karlstav/cava) and [Fcitx5-Unikey](https://github.com/fcitx/fcitx5-unikey). Cava shaders `cava/shaders/orion_*.frag` by **rezky_nightky**; Vietnamese lunar calendar algorithm by **Hồ Ngọc Đức**.

## License

Released under the [MIT License](LICENSE), except `cava/shaders/orion_*.frag` (MIT, copyright **rezky_nightky**) and `hypr/scripts/lunar_vn.py` (port of **Hồ Ngọc Đức**'s Vietnamese lunar calendar algorithm; personal, non-commercial use only). **Kafka** and **Honkai: Star Rail** are trademarks of **HoYoverse / COGNOSPHERE PTE. LTD.**; this is an unofficial fan project and ships no game assets.
