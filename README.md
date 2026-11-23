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

*Tùy chọn hữu ích*: `--dry-run` (thử nghiệm không ghi), `--only a,b` (chỉ chạy bước chỉ định), `--skip a,b` (bỏ qua bước), `--greetd` (cài greetd), `-y` (tự động đồng ý).

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
