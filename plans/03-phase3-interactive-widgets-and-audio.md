# Kế hoạch 03 (Phase 3): Âm nhạc, Sóng nhạc & Tiện ích Tương tác ("Boom!" Audio & Interactive Widgets)

> **Trạng thái:** 🟡 Triển khai một phần — Đã hoàn thành mục A (`mpris` trên Waybar), mục B (`cava/config`) và mục C (`cliphist` + Rofi); còn mục D (SwayNC/AGS Control Center) để mở rộng trong tương lai.

## 1. Mục tiêu
Kafka gắn liền với âm nhạc cổ điển (khúc Violin/Canon trong trailer) và câu thần chú *"Boom!"*. Phase 3 tập trung vào việc biến màn hình Desktop thành một không gian âm nhạc sống động và bổ sung các tiện ích nhanh (Clipboard, Emoji, Bảng màu động).

---

## 2. Các Ý tưởng & Hạng mục Triển khai

### A. Đảo Âm nhạc trên Thanh Waybar (`custom/media` / `mpris`)
* **Gói cài đặt:** `sudo pacman -S playerctl`
* **Thiết kế:**
  * Thêm một viên thuốc (pill) nằm ở cụm giữa của Waybar (bên cạnh Đồng hồ).
  * Khi bạn bật nhạc trên Spotify, YouTube (Firefox/Chrome), hoặc trình phát nhạc nội bộ, viên thuốc sẽ hiện lên với biểu tượng `󰎆  Tên bài hát - Nghệ sĩ`.
  * **Tương tác chuột:**
    * Click trái: Tạm dừng / Phát tiếp (`playerctl play-pause`).
    * Cuộn chuột lên/xuống: Chuyển bài kế tiếp / bài trước (`playerctl next` / `previous`).
  * **Hiệu ứng CSS:** Khi nhạc đang phát (`class="playing"`), viên thuốc có viền chuyển màu tím hồng `#c77dff` và bóng phát sáng nhẹ.

### B. Sóng nhạc Terminal `cava` theo Tông màu Kafka (`cava/config`)
* **Gói cài đặt:** `sudo pacman -S cava`
* **Cấu hình Gradient trong `cava/config`:**
  * Thiết lập dải màu sóng nhạc 6 nấc từ thấp lên cao:
    1. `#382b47` (Tím trầm)
    2. `#8f2456` (Đỏ rượu đậm)
    3. `#b8326a` (Hồng Burgundy Kafka)
    4. `#9b4dca` (Tím Violet)
    5. `#c77dff` (Tím tia chớp)
    6. `#d4af6a` (Đỉnh sóng màu Vàng đồng)
* **Phím tắt kích hoạt:** Sử dụng `Super + A` để mở nhanh một cửa sổ Kitty nổi (floating) nhỏ gọn chạy `cava` *(phím `Super + M` được dành cho việc mở Power Menu)*.

### C. Quản lý Lịch sử Clipboard thông minh (`cliphist`)
* **Gói cài đặt:** `sudo pacman -S cliphist`
* **Lợi ích:** Lưu lại toàn bộ lịch sử văn bản và hình ảnh đã copy (tương tự `Win + V` trên Windows).
* **Tích hợp với Rofi Kafka:**
  * Thêm vào `hyprland.conf`:
    ```ini
    exec-once = wl-paste --type text --watch cliphist store
    exec-once = wl-paste --type image --watch cliphist store
    bind = $mainMod, V, exec, cliphist list | rofi -dmenu -theme ~/.config/rofi/kafka.rasi | cliphist decode | wl-copy
    ```
  * **Quyết định phím tắt cuối cùng:** `Super + V` dùng để mở lịch sử Clipboard (`cliphist` + Rofi), còn `Super + Shift + V` dùng để bật/tắt chế độ cửa sổ nổi (`togglefloating`).

### D. Trung tâm Điều khiển Nhanh (SwayNC hoặc AGS) – Tùy chọn Nâng cao (Chưa triển khai)
* Nếu sau này muốn có bảng trượt bên phải (Notification Center + Công tắc Wifi, Bluetooth, Không làm phiền, Thanh trượt âm lượng/độ sáng giống macOS/GNOME Quick Settings):
  * Có thể thay `dunst` bằng `swaync` (`sudo pacman -S swaync`) và viết file `swaync/style.css` theo đúng bảng màu Kafka.
