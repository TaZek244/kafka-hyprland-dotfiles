# 🕷 Kafka Hyprland Dotfiles

Bộ cấu hình **Hyprland 0.57+** viết bằng Lua (`hypr/hyprland.lua`) lấy cảm hứng từ nhân vật **Kafka (Honkai: Star Rail)** trên Arch Linux. Hệ thống tích hợp hai phong cách giao diện: bản **phẳng** hiện đại và bản **pixel "RPG HUD"** hoài niệm.

---

## ✨ Tính năng chính

* **Bố cục cuộn & Chế độ Desktop**: Sử dụng layout cuộn ngang (`scrolling`) linh hoạt, chuyển đổi tức thì sang chế độ Desktop cửa sổ nổi tự do (`Super + D`).
* **Khung chữ L liền khối**: Thanh trạng thái phía trên và dock dọc bên phải ghép thành khung chữ L, tự động gộp các cửa sổ cùng ứng dụng kèm huy hiệu `xN`.
* **Giao diện Pixel RPG HUD**: Đổi tức thì giữa giao diện phẳng và pixel RPG HUD bằng `Super + Alt + U` (kèm HUD thẻ nhân vật và thanh chỉ số).
* **Trung tâm điều khiển Popup**: Bấm vào cụm trạng thái để mở popup điều chỉnh nhanh Wi-Fi, Bluetooth, VPN (Cloudflare WARP / Proton), âm thanh và độ sáng.
* **Theo dõi pin thiết bị ngoại vi**: Tự động nhận diện và hiển thị mức pin tai nghe, chuột, bàn phím đang kết nối qua UPower, BlueZ và Solaar (Logitech).
* **Popup âm nhạc & Lời bài hát**: Ô "Đang phát" cạnh đồng hồ kèm hiệu ứng sóng nhạc cực quang và popup hiển thị lời bài hát đồng bộ từ LRCLIB.
* **Trình khởi chạy Walker**: Khởi chạy ứng dụng cực nhanh bằng GTK4, hỗ trợ gõ tiếng Việt, tính toán (`=`) và tìm kiếm emoji (`.`).
* **Màn hình khóa & Đăng nhập Pixel**: Màn hình khóa `hyprlock` đồng bộ hình nền hiện tại cùng trình đăng nhập `greetd` pixel "KAFKA.SYS" (kèm dự phòng ReGreet và agreety).
* **Kafka Studio**: Ứng dụng đồ họa trung tâm cho phép xem trước, đổi hình nền, bảng màu và tùy chỉnh các file cấu hình trực quan.
* **Bộ con trỏ & Icon Kafka**: Bộ icon thư mục Papirus gradient hồng–tím độc quyền kết hợp cùng bộ con trỏ chuột Kafka tùy biến.

⌨️ Phím tắt: xem [KEYBINDINGS.md](KEYBINDINGS.md).

---

## 📋 Yêu cầu hệ thống

* **Hệ điều hành**: Arch Linux với Hyprland 0.57+ (cấu hình Lua), quyền `sudo` và trình quản lý AUR (`yay` hoặc `paru`).
* **Độ phân giải tham chiếu**: 1920×1080 (1080p).

---

## 🚀 Cài đặt nhanh

```bash
git clone https://github.com/TaZek244/kafka-hyprland-dotfiles.git ~/kafka-hyprland-dotfiles
cd ~/kafka-hyprland-dotfiles && ./install.sh
```

> **Lưu ý**: **Không** chạy bằng `sudo ./install.sh` (script sẽ tự gọi `sudo` khi cần).

Khi chạy không kèm tham số, `./install.sh` mở menu tương tác:
* **1)** Cài đầy đủ (khuyên dùng cho máy mới)
* **2)** Chỉ liên kết cấu hình + tạo file tự sinh (không cài gói, không cần `sudo`)
* **3)** Chọn từng bước muốn chạy
* **4)** Chạy thử (`--dry-run`, không thay đổi hệ thống)
* **5)** Cài màn hình đăng nhập (`greetd`)
* **q)** Thoát

### 🐧 Hệ điều hành hỗ trợ

* **Arch Linux (đầy đủ)**: Tự động cài toàn bộ gói qua kho chính thức (`pacman`) và AUR (`yay` / `paru`).
* **Ubuntu / Debian (bán phần)**: `apt` tự động cài phần lớn gói nền tảng, tự tải Nerd Font và tạo lệnh `magick` giả trong `~/.local/bin` (tương thích ImageMagick 6). Các thành phần chưa có hoặc quá cũ trên `apt` cần cài tay (script sẽ tự in danh sách kèm link hướng dẫn khi chạy trên Ubuntu):
  * **Bắt buộc**: **Hyprland ≥ 0.57** (hỗ trợ cấu hình Lua), `hyprlock` / `hypridle` (nếu `apt` thiếu), **Rofi ≥ 2.0** (bản hỗ trợ Wayland).
  * **Thành phần phụ trợ**: `awww` (hình nền động), `hyprshell` (`Alt+Tab`), `walker` + `elephant` (launcher), `hyprshot` + `satty` (chụp/chú thích ảnh), `cliphist` (bản trên `apt` quá cũ), **Cloudflare WARP** (cài từ kho `apt` riêng `pkg.cloudflareclient.com`), **ReGreet** (được thay bằng giao diện `KAFKA.SYS`).

### 📦 Các bước cài đặt (`steps`)

| Bước | Mô tả công việc |
| :--- | :--- |
| `packages` | Cài đặt các gói phần mềm theo bản phân phối (Arch hoặc Ubuntu/Debian). |
| `fonts` | Cài đặt bộ phông chữ FiraCode Nerd Font & JetBrainsMono Nerd Font. |
| `link` | Tạo symlink cấu hình vào `~/.config` (tự sao lưu bản cũ vào `~/.config/backup_before_kafka_<thời gian>`). |
| `assets` | Sinh bộ ảnh phụ (banner Rofi, màn hình khóa, avatar) từ thư mục `wallpapers/`. |
| `system` | Cấp quyền chạy script, tạo file tự sinh, cài font pixel, icon, con trỏ, giao diện GTK tối và ứng dụng mặc định. |
| `fcitx` | Cấu hình bộ gõ tiếng Việt `fcitx5` + Unikey (chuyển đổi bằng `Ctrl + Space`). |
| `services` | Kích hoạt dịch vụ `NetworkManager`, `bluetooth`, `power-profiles-daemon`, `warp-svc` và `elephant`. |
| `check` | Kiểm tra toàn diện môi trường và chạy bài tự kiểm tra (`selftest`). |

### 💡 Các lệnh thường dùng

```bash
./install.sh --list                        # Liệt kê danh sách các bước cài đặt
./install.sh --dry-run                     # Chạy thử nghiệm, chỉ in lệnh chứ không ghi file
./install.sh -y                            # Cài đặt đầy đủ và tự động đồng ý mọi câu hỏi
./install.sh --only link,system            # Chỉ chạy bước liên kết cấu hình và thiết lập hệ thống
./install.sh --skip packages               # Chạy mọi bước trừ bước cài đặt gói
./install.sh --only assets --force-assets  # Tạo lại toàn bộ ảnh phụ sau khi thay ảnh trong wallpapers/
./install.sh --greetd                      # Cài đặt màn hình đăng nhập greetd
./install.sh --greetd-switch               # Cài greetd và tắt trình đăng nhập cũ để chuyển hẳn sang greetd
./install.sh --help                        # Xem toàn bộ hướng dẫn tham số dòng lệnh
```

### 🔐 Màn hình đăng nhập (`greetd`)

* **Arch Linux**: Hỗ trợ cả giao diện GTK4 **ReGreet** (mặc định) và giao diện pixel **KAFKA.SYS** (`./greetd/install-greetd.sh --kafka`).
* **Ubuntu / Debian**: Chỉ sử dụng giao diện **KAFKA.SYS** (do kho `apt` không có gói ReGreet).
* Script tự động nhận diện tài khoản hệ thống (`greeter` trên Arch hoặc `_greetd` trên Ubuntu) và tự tắt `gdm` / `gdm3` / `sddm` / `lightdm` khi dùng tùy chọn `--greetd-switch` (hoặc `--switch`).

---

## 🖼️ Ảnh nền

Repo **không đính kèm ảnh nhân vật Kafka** do bản quyền thuộc HoYoverse và các họa sĩ. Tải ảnh của bạn vào `wallpapers/` (`kafka_landscape_3.jpg` cho màn hình 16:9, `kafka_main.jpg` cho banner dọc) rồi chạy `./install.sh --only assets --force-assets`. Nếu để trống, hệ thống sẽ tự sinh ảnh dải màu thay thế.

---

## 🎨 Tùy biến

Mở **Kafka Studio** từ dock (`scripts/studio.py`) để chỉnh hình nền và tùy chọn hệ thống trực quan. Bảng màu giao diện được định nghĩa tập trung qua các biến `@define-color` tại `waybar/style.css` (bản phẳng) và `waybar/theme-pixel.css` (bản pixel).

---

## 🛠️ Khắc phục sự cố

* **Không gõ được tiếng Việt**: Kiểm tra bằng `~/.config/hypr/scripts/ime-guard.sh status` hoặc bấm giữa ô `VI / EN` trên thanh trên để khởi động lại bộ gõ (mở terminal mới nếu cửa sổ cũ kẹt kết nối).
* **Waybar mất khay hệ thống**: Khởi động lại qua Hyprland để nhận đầy đủ môi trường D-Bus: `killall waybar; hyprctl dispatch "hl.dsp.exec_cmd('waybar')"`.
* **Màn hình đăng nhập greetd bị lỗi**: Nhấn `Ctrl + Alt + F2` vào TTY và chạy `~/kafka-hyprland-dotfiles/greetd/install-greetd.sh --revert` để chuyển về chế độ dòng lệnh `agreety`.
* **Walker hiển thị danh sách trống**: Đảm bảo cài đặt đồng bộ bản `-bin` (`elephant-bin` và các plugin), sau đó chạy `systemctl --user restart elephant.service; pkill -x walker; setsid -f walker --gapplication-service`.
* **Tải lại giao diện sau khi sửa cấu hình**: Dùng `hyprctl reload` để nạp lại Hyprland hoặc `killall -SIGUSR2 waybar` để nạp lại Waybar.

---

## 🙏 Ghi công (Credits)

* **Shaders sóng nhạc Cava**: Các shader OpenGL `orion_circle.frag`, `orion_circle_rotate.frag`, `orion_saturn_core.frag`, `orion_saturn_subring.frag` trong `cava/shaders/` thuộc bản quyền của tác giả **rezky_nightky** (giữ nguyên ghi chú bản quyền và giấy phép SPDX trong từng file nguồn).
* **Phần mềm nguồn mở**: Xây dựng trên nền tảng [Hyprland](https://hypr.land/), [Waybar](https://github.com/Alexays/Waybar), [Walker](https://github.com/abenz1267/walker) & [Elephant](https://github.com/abenz1267/elephant), [hyprshell](https://github.com/H3rmt/hyprshell), [Rofi](https://github.com/davatorium/rofi), [ReGreet](https://github.com/rharish101/ReGreet), [Kitty](https://sw.kovidgoyal.net/kitty/), [Dunst](https://dunst-project.org/), [Cava](https://github.com/karlstav/cava), [Fcitx5-Unikey](https://github.com/fcitx/fcitx5-unikey) và thuật toán âm lịch Việt Nam của **Hồ Ngọc Đức**.
* **Tuyên bố miễn trừ**: Nhân vật **Kafka** và trò chơi **Honkai: Star Rail** là tài sản trí tuệ và thương hiệu của **HoYoverse / COGNOSPHERE PTE. LTD.** Đây là dự án cấu hình máy tính do người hâm mộ thực hiện (fan-made), hoàn toàn phi thương mại và không có bất kỳ liên kết chính thức nào với HoYoverse.

---

## 📄 Giấy phép (License)

Mã nguồn script và các file cấu hình trong kho lưu trữ này được phát hành theo giấy phép **MIT** (xem chi tiết trong file [`LICENSE`](LICENSE)), ngoại trừ các file có ghi chú bản quyền và giấy phép riêng ở đầu file: bộ shader `cava/shaders/orion_*` (MIT, rezky_nightky) và `hypr/scripts/lunar_vn.py` (chuyển ngữ thuật toán âm lịch của Hồ Ngọc Đức, chỉ dùng cá nhân, phi thương mại).
