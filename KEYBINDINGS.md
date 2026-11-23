# ⌨️ Phím tắt — Kafka Hyprland

> Phím chính (`$mainMod`) là **`Super`** (phím Windows / ⌘). Các phím mặc định được định nghĩa trong `hypr/hyprland.lua`. Phím tắt riêng của người dùng có thể thêm/chỉnh sửa qua ứng dụng **Kafka Keybinds** (nút ⌨ trên dock, lưu tại `hypr/keybinds.lua` và tự động nạp sau phím mặc định mà không cần sửa `hypr/hyprland.lua`).

---

### Khởi chạy & Hệ thống
| Phím tắt | Chức năng |
| :--- | :--- |
| **`Super + Q`** | Mở trình giả lập dòng lệnh Terminal (**Kitty**) |
| **`Super + E`** | Mở trình quản lý tệp tin (**Thunar**) |
| **`Super + Space`** / **`Super + R`** | Mở trình tìm & khởi chạy ứng dụng **Walker** |
| **`Nhấn-thả riêng Super`** | Bật/tắt chế độ tổng quan cửa sổ & workspace (**hyprshell**) |
| **`Alt + Tab`** / **`Super + Tab`** | Chuyển nhanh giữa các cửa sổ (**hyprshell**): giữ phím bổ trợ, bấm Tab để sang tiếp, thả ra để nhảy tới (`Shift` = đi ngược) |
| **`Super + V`** | Mở lịch sử Clipboard (`cliphist` + Rofi) |
| **`Super + Alt + U`** | Đổi giao diện Waybar và toàn hệ thống: **phẳng** ⇄ **pixel** ("RPG HUD") |
| **`Super + A`** | Bật/tắt cửa sổ nổi chạy sóng nhạc `cava` (`kitty --class kafka-cava`) |
| **`Super + Shift + A`** | Bật/tắt **sóng nhạc ở đáy màn hình** (`cava-wallpaper.py`, bấm xuyên qua, chỉ hiện khi có tiếng) |
| **`Super + Alt + A`** | Đổi kiểu sóng nhạc: **nổi trên cửa sổ** (mặc định, mỏng, trong mờ) ⇄ **làm hình nền** (cao hơn, nằm dưới cửa sổ, chỉ thấy ở chỗ trống) |
| **`Super + Shift + B`** | Tải lại hoặc khởi động lại thanh trạng thái **Waybar** |
| **`Super + Ctrl + cuộn`** / **`Super + Ctrl + = / -`** / **`Super + Ctrl + 0`** | Kính lúp: phóng to / thu nhỏ / về bình thường (1x–6x quanh con trỏ) |
| **`Super + Escape`** | Khóa màn hình ngay lập tức (`lock.sh` theo giao diện phẳng hoặc pixel) |
| **`Super + M`** | Mở menu nguồn Rofi (`powermenu.sh`) |

---

### Quản lý cửa sổ
| Phím tắt | Chức năng |
| :--- | :--- |
| **`Super + H / J / K / L`** (hoặc mũi tên) | Di chuyển tiêu điểm (focus) giữa các cửa sổ theo kiểu Vim |
| **`Super + C`** | Đóng cửa sổ đang chọn |
| **`Super + Shift + X`** | Buộc đóng (kill) ứng dụng đang bị treo |
| **`Super + Shift + Q`** | Mở menu chọn ứng dụng để đóng (`closemenu.sh`) |
| **`Super + Shift + V`** | Bật/tắt trạng thái nổi (float) cho cửa sổ hiện tại (tự căn vừa vùng nội dung) |
| **`Super + Shift + F`** | Phóng to cửa sổ trong vùng nội dung (chừa thanh trên và dock Waybar) |
| **`Super + F`** | Toàn màn hình thật (che cả Waybar) |
| **`Super + T`** | Treo (pin) cửa sổ nổi ở góc màn hình đi theo mọi workspace |
| **`Super + Shift + T`** | Bỏ treo tất cả cửa sổ đang ghim (`pin-toggle.sh`) |
| **`Super + I`** | Ẩn cửa sổ đang chọn vào ngăn `special:hidden` |
| **`Super + O`** | Mở menu quản lý và khôi phục các cửa sổ đang ẩn (`hide-windows.py`) |
| **`Super + Shift + I`** | Hiện lại tất cả cửa sổ đang ẩn về workspace hiện tại |
| **`Super + S`** | Bật/tắt vùng làm việc ghi chú đặc biệt (Scratchpad `special:magic`) |
| **`Super + Shift + Z`** | Dời cửa sổ đang chọn vào Scratchpad (`special:magic`) |

---

### Bố cục cuộn (`scrolling`), Chế độ Desktop & Chia khu
| Phím tắt | Chức năng |
| :--- | :--- |
| **`Super + D`** | Chuyển đổi giữa **Layout cuộn** và **Chế độ Desktop** (cửa sổ nổi tự do) |
| **`Super + G`** | Xoay vòng độ rộng cột đang chọn (`colresize +conf`: 1/3 → 1/2 → 2/3 → 1.0) |
| **`Super + -`** / **`Super + =`** | Thu hẹp / Nới rộng độ rộng cột hiện tại 10% |
| **`Super + Ctrl + ← / →`** | Dời cột hiện tại sang trái / phải (`swapcol l/r`) |
| **`Super + ,`** / **`Super + .`** | Gộp cửa sổ vào cột bên cạnh hoặc tách ra (`consume_or_expel prev/next`) |
| **`Super + P`** | Tách cửa sổ đang chọn ra khỏi cột chồng thành cột riêng (`promote`) |
| **`Super + Shift + G`** | Mở bảng chia ô cố định theo tỉ lệ cho workspace đang xem (`tile-menu.sh`) |
| **`Vuốt 3 ngón ngang / dọc`** | Cuộn ngang các cột (`scroll_move`) / Chuyển workspace |
| **`Vuốt 4 ngón lên / xuống`** | Bật chế độ tổng quan (`hyprshell`) / Chuyển đổi chế độ Desktop ⇄ cuộn |
| **`Chụm 3 ngón`** | Phóng to kính lúp quanh con trỏ (`cursorZoom`) |

---

### Không gian làm việc (Workspaces) & Thao tác chuột
| Phím tắt | Chức năng |
| :--- | :--- |
| **`Super + 1 .. 9, 0`** | Chuyển đến Workspace 1 đến 10 |
| **`Super + Shift + 1 .. 9, 0`** | Dời cửa sổ đang chọn sang Workspace 1 đến 10 |
| **`Super + Cuộn chuột lên / xuống`** | Chuyển nhanh giữa các Workspace kế tiếp / trước đó |
| **`Super + Chuột trái kéo`** | Di chuyển vị trí cửa sổ nổi (kéo thả ra mép màn hình để phóng to) |
| **`Super + Chuột phải kéo`** | Thay đổi kích thước cửa sổ nổi |

---

### Chụp & Quay màn hình (`capture.sh`)
| Phím tắt | Chức năng |
| :--- | :--- |
| **`Print`** | Mở menu Rofi chọn 6 chế độ chụp / quay màn hình |
| **`Shift + Print`** | Chụp ngay toàn màn hình (lưu vào `~/Pictures/Screenshots`) |
| **`Super + Shift + S`** | Chụp một vùng màn hình |
| **`Super + Shift + R`** | Bắt đầu quay màn hình (hỏi chọn âm thanh) hoặc dừng quay (lưu vào `~/Videos/Recordings`) |
