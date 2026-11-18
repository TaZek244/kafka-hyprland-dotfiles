# Kế hoạch 02 (Phase 2): Màn hình Khóa, Quản lý Năng lượng & Menu Nguồn (Lockscreen, Idle & Power Menu)

> **Trạng thái:** ✅ Đã triển khai (`hypr/hyprlock.conf`, `hypr/hypridle.conf`, `hypr/scripts/powermenu.sh`, `rofi/kafka-power.rasi`).

## 1. Mục tiêu
Hiện tại bộ giao diện đã hoàn chỉnh cho nhu cầu làm việc trực tiếp. Bước nâng cấp tiếp theo (Phase 2) là hoàn thiện trải nghiệm khi **rời máy tạm thời (Lockscreen)**, **tự động tiết kiệm pin (Idle Daemon)** và **bảng tùy chọn Tắt máy/Khởi động lại/Ngủ đông (Power Menu)** mang đậm dấu ấn Kafka.

---

## 2. Các Thành phần Dự kiến Xây dựng

### A. Màn hình khóa `hyprlock` (`hypr/hyprlock.conf`)
* **Gói cài đặt:** `sudo pacman -S hyprlock`
* **Ý tưởng thiết kế:**
  * **Nền (Background):** Lấy hình nền `kafka_landscape_1.png` hoặc `kafka_umbrella_1080p.jpg` với hiệu ứng `blur_passes = 3`, `vibrancy = 0.2`.
  * **Ảnh đại diện (Image Avatar):** Hiển thị khung tròn ở giữa màn hình cắt từ khuôn mặt đeo kính râm của Kafka trong `kafka_main.jpg`, viền vàng đồng `#d4af6a`.
  * **Đồng hồ lớn (Clock Label):** Phông chữ lớn ở phía trên màu trắng ngà `#f4eef8`, bên dưới là câu thoại đặc trưng của Kafka: *"Listen... Paterson's rain is falling."* (màu tím `#c77dff`).
  * **Ô nhập mật khẩu (Input Field):** Viên thuốc bo tròn nền `#141118`, viền `#b8326a`, khi gõ sai mật khẩu sẽ chuyển sang màu đỏ rực `#ff4d6d`.
* **Phím tắt kích hoạt:** `Super + Escape` $\rightarrow$ `exec, hyprlock` *(phím `Super + L` được giữ nguyên để di chuyển tiêu điểm cửa sổ sang phải theo phong cách Vim)*.

### B. Trình quản lý trạng thái nghỉ `hypridle` (`hypr/hypridle.conf`)
* **Gói cài đặt:** `sudo pacman -S hypridle`
* **Kịch bản hoạt động (Tối ưu cho Laptop):**
  1. **Sau 2.5 phút (150s) không thao tác:** Tự động giảm độ sáng màn hình xuống 15% (`brightnessctl -s set 15%`) để tiết kiệm pin. Khi di chuột lại sẽ khôi phục độ sáng cũ (`brightnessctl -r`).
  2. **Sau 5 phút (300s) không thao tác:** Tự động khóa màn hình bằng `hyprlock`.
  3. **Sau 5.5 phút (330s) không thao tác:** Tắt tín hiệu màn hình (`hyprctl dispatch dpms off`).
  4. **Sau 15 phút (900s, chỉ khi dùng pin):** Đưa máy vào trạng thái Sleep (`systemctl suspend`).

### C. Menu Nguồn Đồ họa `wlogout` hoặc `rofi-powermenu`
* **Ý tưởng 1 (Nhẹ nhất - Dùng Rofi sẵn có – Đã chọn):**
  * Viết script `hypr/scripts/powermenu.sh` gọi Rofi với giao diện `rofi/kafka-power.rasi` hiển thị 5 nút lớn ở giữa màn hình (có bước xác nhận cho `Logout`, `Reboot` và `Shutdown`):
    * `󰌾  Lock` (`hyprlock`)
    * `󰤄  Suspend` (`systemctl suspend`)
    * `󰍃  Logout` (`hyprctl dispatch exit`)
    * `󰜉  Reboot` (`systemctl reboot`)
    * `⏻  Shutdown` (`systemctl poweroff`)
* **Liên kết với Waybar & Phím tắt:** Thay hành động `on-click` của nút `custom/power` (`⏻`) ở góc phải trên cùng Waybar và phím tắt `Super + M` để mở bảng Power Menu này thay vì thoát trực tiếp.

---

## 3. Các bước Triển khai (Khi bắt đầu Phase 2)
1. Cài đặt `hyprlock` và `hypridle`.
2. Tạo file `hypr/hyprlock.conf`, `hypr/hypridle.conf`, `hypr/scripts/powermenu.sh` và `rofi/kafka-power.rasi`.
3. Thêm `exec-once = hypridle` và `bind = $mainMod, Escape, exec, hyprlock` vào `hypr/hyprland.conf`.
4. Cập nhật `waybar/config.jsonc` cho nút `custom/power`.
