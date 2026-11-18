# AGENTS.md — Hướng dẫn dành cho AI Agents (Kafka Hyprland Dotfiles)

Tài liệu này cung cấp ngữ cảnh kiến trúc, quy chuẩn thiết kế (Design System), quy tắc an toàn hệ thống và lộ trình phát triển cho mọi AI Agent làm việc trên kho lưu trữ `custom_desktop`.

---

## 1. Tổng quan Dự án (Project Overview)

* **Mục tiêu:** Xây dựng bộ giao diện **Hyprland (Wayland Tiling Window Manager)** từ con số 0 (Custom từ A-Z) trên **Arch Linux**, lấy cảm hứng nghệ thuật từ nhân vật **Kafka (Honkai: Star Rail)**.
* **Không còn phụ thuộc GNOME:** đăng nhập bằng greetd + ReGreet (dự phòng: agreety), GNOME/GDM có thể đã được gỡ. Không gọi app GNOME hay giả định có phiên GNOME. Phải giữ `gnome-keyring`, `gvfs*`, `polkit-gnome` (xem quy tắc 1 trong `CLAUDE.md`). Không tự gỡ gói.
* **Phần cứng mục tiêu:**
  * Laptop Hybrid GPU: Intel TigerLake-H UHD Graphics (iGPU) + NVIDIA GeForce RTX 3050 Ti Mobile (dGPU).
  * Bộ gõ tiếng Việt: `fcitx5` (`fcitx5-unikey`).
  * Font chữ hệ thống: `FiraCode Nerd Font` & `FiraCode Nerd Font Mono`.

---

## 2. Hệ thống Thiết kế "Kafka's Web" (Design System & Color Tokens)

Mọi thành phần giao diện mới (Waybar, Rofi, Kitty, Dunst, Hyprlock, Wlogout, AGS/Eww...) đều phải tuân thủ nghiêm ngặt bảng màu trích xuất từ artwork Kafka cầm ô dưới mưa:

| Token Name | Hex Code | RGBA / Hyprland Format | Vai trò sử dụng |
| :--- | :--- | :--- | :--- |
| `obsidian-base` | `#141118` | `rgba(20, 17, 24, 0.88)` | Nền chính của Terminal, Waybar pills, Rofi, Notification |
| `plum-surface` | `#1e1826` | `rgba(30, 24, 38, 0.92)` | Nền phụ, card, thanh nhập liệu (input bar) |
| `muted-border` | `#382b47` | `rgba(56, 43, 71, 0.67)` | Viền cửa sổ không hoạt động (inactive border) |
| `kafka-burgundy` | `#b8326a` | `rgba(184, 50, 106, 1.0)` | Màu nhấn chính (Primary Accent), nền mục đang chọn |
| `wine-deep` | `#8f2456` | `rgba(143, 36, 86, 1.0)` | Đầu dải màu gradient, trạng thái hover/power |
| `spider-lilac` | `#c77dff` | `rgba(199, 125, 255, 1.0)` | Màu nhấn phụ (Secondary Accent), tia chớp/tơ nhện, glow |
| `violet-neon` | `#9b4dca` | `rgba(155, 77, 202, 1.0)` | Trung gian gradient giữa Burgundy và Lilac |
| `coat-gold` | `#d4af6a` | `rgba(212, 175, 106, 1.0)` | Điểm nhấn kim loại (viền active, icon, con trỏ chuột) |
| `ivory-text` | `#f4eef8` | `rgba(244, 238, 248, 1.0)` | Màu chữ chính trên nền tối |
| `lavender-muted` | `#a99bbd` | `rgba(169, 155, 189, 1.0)` | Màu chữ phụ, placeholder, workspace không hoạt động |

### Quy chuẩn Hình học & Hiệu ứng (Geometry & Motion)
* **Bo góc (Border Radius):**
  * Cửa sổ Hyprland & Notification: `14px`
  * Khung Rofi Launcher: `18px`
  * Waybar Floating Islands / Pills: `999px` (bo tròn hoàn toàn dạng viên thuốc)
* **Độ mờ (Blur & Opacity):**
  * Kính mờ Hyprland: `size = 7`, `passes = 3`, `vibrancy = 0.22`
  * Opacity cửa sổ: `0.96` (active) / `0.90` (inactive)
* **Chuyển động (Animation):**
  * Sử dụng đường cong Bezier `kafkaSnap (0.05, 0.9, 0.1, 1.05)` cho cảm giác dứt khoát như sợi tơ căng và `kafkaSmooth (0.25, 1, 0.5, 1)` khi đóng/chuyển cảnh.

---

## 3. Cấu trúc Kho lưu trữ & Cơ chế Symlink

```text
custom_desktop/
├── AGENTS.md / agent.md           # Hướng dẫn dành cho AI Agents
├── CLAUDE.md / claude.md           # Ngữ cảnh nhanh, lệnh thực thi & quy chuẩn code
├── README.md                       # Tài liệu hướng dẫn người dùng
├── install.sh                      # Script cài đặt gói & tạo symlink an toàn
├── hypr/
│   ├── hyprland.conf               # Cấu hình trung tâm của Hyprland
│   ├── hyprlock.conf               # Cấu hình màn hình khóa (Lockscreen) phong cách Kafka
│   ├── hypridle.conf               # Cấu hình tự động giảm sáng, khóa máy & tiết kiệm pin
│   ├── wallpapers -> ../wallpapers # Symlink nội bộ trỏ tới thư mục ảnh nền
│   └── scripts/
│       ├── wallpaper-cycle.sh      # Script đổi hình nền với hiệu ứng awww
│       └── powermenu.sh            # Script menu nguồn Rofi (Lock/Suspend/Logout/Reboot/Shutdown)
├── waybar/
│   ├── config.jsonc                # Bố cục Floating Island / Pill (Số La Mã I-X, mpris, power)
│   └── style.css                   # CSS styling theo bảng màu Kafka
├── rofi/
│   ├── kafka.rasi                  # Giao diện Rofi 2 cột (Ảnh Kafka + Danh sách App)
│   └── kafka-power.rasi            # Giao diện Rofi cho Power Menu & hộp thoại xác nhận
├── cava/
│   └── config                      # Cấu hình sóng nhạc 6 nấc màu gradient Kafka
├── kitty/
│   └── kitty.conf                  # Cấu hình Terminal trong suốt + màu ANSI Kafka
├── dunst/
│   └── dunstrc                     # Cấu hình thông báo nổi góc phải trên
├── fastfetch/
│   └── config.jsonc                # Cấu hình hiển thị ảnh Kafka trong Kitty
├── wallpapers/                     # Chứa ảnh gốc kafka_main.jpg & các bản 16:9 (kafka_*.jpg/png)
└── plans/                          # Các bản kế hoạch kiến trúc & mở rộng tính năng
```

### Nguyên tắc Vàng khi sửa đổi:
1. **Chỉnh sửa tại nguồn (`custom_desktop/`):** Luôn sửa file trong repo `custom_desktop/...`. Nhờ cơ chế symlink trong `~/.config/`, thay đổi sẽ áp dụng trực tiếp.
2. **Bảo toàn tính năng Laptop & Tiếng Việt:** Không xóa `exec-once = fcitx5 -d`, các biến môi trường `GTK_IM_MODULE=fcitx`, `QT_IM_MODULE=fcitx`, hoặc các phím media (`wpctl`, `brightnessctl`).
3. **Kiểm tra cú pháp trước khi hoàn tất:**
   * JSONC (`waybar/config.jsonc`, `fastfetch/config.jsonc`): Đảm bảo cặp dấu ngoặc và dấu phẩy hợp lệ.
   * Shell scripts (`*.sh`): Luôn có `#!/usr/bin/env bash` và chạy `chmod +x`.

---

## 4. Danh sách Kế hoạch Phát triển (`plans/`)

Khi người dùng yêu cầu nâng cấp hoặc thêm tính năng mới, hãy tham khảo các tài liệu kế hoạch trong thư mục [`plans/`](plans):
1. [`plans/01-architecture-and-design-system.md`](plans/01-architecture-and-design-system.md): Kiến trúc chi tiết và cách thức các thành phần giao tiếp với nhau.
2. [`plans/02-phase2-lockscreen-idle-and-power.md`](plans/02-phase2-lockscreen-idle-and-power.md) — **✅ Đã triển khai**: Màn hình khóa (`hyprlock`), tự động tắt màn hình (`hypridle`), và menu nguồn (`rofi` power menu) mang phong cách Kafka.
3. [`plans/03-phase3-interactive-widgets-and-audio.md`](plans/03-phase3-interactive-widgets-and-audio.md) — **🟡 Triển khai một phần (còn mục D)**: Tích hợp sóng nhạc (`cava`), trình phát nhạc (`playerctl`/`mpris`) trên Waybar, và quản lý lịch sử clipboard (`cliphist`).
4. [`plans/04-gnome-coexistence-and-gtk-qt-theming.md`](plans/04-gnome-coexistence-and-gtk-qt-theming.md): Chiến lược đồng bộ Dark Mode cho ứng dụng GTK/Qt bên trong Hyprland mà không làm hỏng giao diện GNOME.
