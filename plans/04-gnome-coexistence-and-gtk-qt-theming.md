# Kế hoạch 04 (Phase 4): Sống chung Hòa bình với GNOME & Đồng bộ Theme GTK/Qt

## 1. Bài toán Thực tế
Khi chạy song song **GNOME** và **Hyprland** trên cùng một tài khoản người dùng (`<user>`):
* Nếu dùng các công cụ ép đổi theme GTK toàn cục một cách thô bạo (ghi đè `~/.config/gtk-4.0/gtk.css`), khi quay lại phiên làm việc **GNOME**, các ứng dụng mặc định của GNOME (Cài đặt, Lịch, Tệp tin...) có thể bị lỗi hiển thị hoặc mất giao diện chuẩn Libadwaita.
* Ngược lại, nếu không cấu hình gì, một số ứng dụng mở trong Hyprland (như `Nautilus`, `Pavucontrol`) có thể hiển thị nền trắng chói mắt (Light Mode), lệch tông với giao diện tối của Kafka.

---

## 2. Giải pháp Đồng bộ An toàn (Non-Destructive Theming)

### A. Kích hoạt Dark Mode chuẩn cho GTK4 / Libadwaita (Tương thích cả GNOME & Hyprland)
Thay vì ghi đè file CSS hệ thống, sử dụng chuẩn `gsettings` chính thức của GNOME để bật chế độ Tối (Dark Style):

```bash
gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'
```
* **Ưu điểm:** Cả GNOME lẫn Hyprland đều đọc chung khóa cấu hình này thông qua `xdg-desktop-portal`. Toàn bộ ứng dụng như `Nautilus` sẽ chuyển sang màu tối sang trọng mà không làm hỏng bất kỳ thành phần nào của GNOME.

### B. Đồng bộ Con trỏ chuột (Cursor) và Biểu tượng (Icon Theme)
* Cài đặt bộ Icon và Con trỏ chuột đẹp cho cả 2 môi trường:
  ```bash
  sudo pacman -S papirus-icon-theme
  yay -S bibata-cursor-theme-bin
  ```
* Tạo biến môi trường chỉ áp dụng riêng trong phiên Hyprland (trong `hypr/hyprland.conf`):
  ```ini
  env = HYPRCURSOR_THEME,Bibata-Modern-Classic
  env = HYPRCURSOR_SIZE,24
  env = XCURSOR_THEME,Bibata-Modern-Classic
  env = XCURSOR_SIZE,24
  ```

### C. Đồng bộ Giao diện cho Ứng dụng Qt (`qt5ct` / `qt6ct` & `kvantum`)
Các ứng dụng viết bằng Qt (như VLC, OBS Studio, qBittorrent) không đọc cấu hình của GNOME mà đọc qua biến `QT_QPA_PLATFORMTHEME=qt6ct` (đã được khai báo sẵn trong `hypr/hyprland.conf`).
* **Các bước thực hiện:**
  1. Cài đặt: `sudo pacman -S qt5ct qt6ct kvantum`
  2. Chọn style `kvantum-dark` hoặc tạo bảng màu tối `#141118` / `#b8326a` trong `~/.config/qt6ct/colors/kafka.conf` — việc này **chỉ tác động khi chạy trong Hyprland**, hoàn toàn tách biệt với GNOME.

---

## 3. Quy trình Quản lý Dotfiles bằng Git & Khôi phục Nhanh

Để biến thư mục `<thư mục repo>` thành một kho lưu trữ cá nhân chuyên nghiệp:

1. **Khởi tạo Git (nếu chưa có):**
   ```bash
   cd <thư mục repo>
   git init
   git add .
   git commit -m "feat: initial Kafka (HSR) Hyprland floating island desktop"
   ```
2. **Thử nghiệm tính năng mới qua nhánh (Branching):**
   * Mỗi khi thử nghiệm một Phase mới trong thư mục `plans/` (ví dụ: thử `swaync` thay cho `dunst`), chỉ cần tạo nhánh `git checkout -b exp/swaync`.
   * Nếu không ưng ý, chạy `git checkout main` là giao diện quay về trạng thái ổn định ngay lập tức!
