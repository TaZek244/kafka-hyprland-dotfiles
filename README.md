# 🕷 Kafka Hyprland Dotfiles

Bộ cấu hình **Hyprland 0.57+** (viết bằng Lua tại `hypr/hyprland.lua`) lấy cảm hứng từ nhân vật **Kafka (Honkai: Star Rail)**, thiết kế cho **Arch Linux**. Giao diện theo phong cách phẳng hiện đại với hai thanh Waybar ghép thành **khung chữ L** liền khối (thanh trạng thái phía trên nối với dock dọc bên phải qua góc bo lõm), kết hợp hệ thống popup điều khiển trực tiếp mà không cần mở ứng dụng rời.

<!-- ![Ảnh chụp](docs/screenshot.png) -->

---

## ✨ Tính năng chính

### 🪟 Bố cục cửa sổ & Điều hướng
* **Layout cuộn (`scrolling`) & Chế độ Desktop**: Mặc định dùng bố cục cột cuộn ngang của Hyprland 0.57 (xoay vòng độ rộng cột, gộp/tách cột chồng, cuộn 3 ngón). Chuyển tức thì sang **Chế độ Desktop** (mọi cửa sổ nổi tự do, tự giới hạn nằm trọn trong vùng nội dung chừa Waybar, kéo thả ra mép để phóng to) bằng `Super + D` hoặc nút trên thanh trên; trạng thái được nhớ qua các lần đăng nhập.
* **Chia khu theo tỉ lệ (`lua:kafka`)**: Bảng chọn bố cục chia ô cố định cho từng workspace (`Super + Shift + G`), chọn `Auto` để quay về layout cuộn.
* **Bản đồ cột (`custom/columns`)**: Hiển thị ngay bên cạnh số workspace (La Mã `I, II, III...`) trên thanh trên; vẽ **icon ứng dụng** của từng cột trong workspace hiện tại, báo số lượng cửa sổ xếp chồng, phân biệt màu cột đang dùng / đang thấy / bị khuất và hỗ trợ lăn chuột để chuyển cột.
* **Tổng quan & Chuyển cửa sổ (`hyprshell`)**: Nhấn-thả riêng phím `Super` (hoặc bấm ô góc mạng nhện `󰯊` ở góc trên phải) để mở chế độ tổng quan kiểu GNOME; `Alt + Tab` để chuyển nhanh cửa sổ.
* **Cử chỉ touchpad**: 3 ngón ngang = cuộn cột, 3 ngón dọc = đổi workspace, **4 ngón lên = tổng quan**, **4 ngón xuống = chế độ Desktop ⇄ cuộn**, **chụm 3 ngón = kính lúp**.
* **Kính lúp màn hình**: `Super + Ctrl + cuộn chuột` hoặc `Super + Ctrl + =/-` phóng to/thu nhỏ quanh con trỏ (1x–6x), `Super + Ctrl + 0` về bình thường. Dùng tính năng zoom có sẵn của Hyprland, không cần plugin.
* **Ẩn / Hiện & Treo cửa sổ**: Giấu cửa sổ đang dùng vào ngăn ẩn `special:hidden` (`Super + I`), mở bảng quản lý cửa sổ ẩn (`Super + O`), hoặc treo cửa sổ nổi cố định ở góc đi theo mọi workspace (`Super + T`).

### 🎛️ Khung chữ L, Dock & Hệ thống Popup (GTK3 Layer-Shell)
* **Khung chữ L liền khối**: Thanh trên (`topbar`) và dock dọc bên phải (`dockbar`, rộng 48px) dùng chung nền phẳng tối nhẹ (`rgba(44,36,52,0.93)`), nối với nhau bằng góc bo lõm (`corner-fillet.py`, tự ẩn khi có cửa sổ toàn màn hình thật).
* **Dock phải gộp theo ứng dụng**: Tự động gộp nhiều cửa sổ cùng ứng dụng thành **1 icon kèm huy hiệu `xN`** (`dock-apps.py`), có vạch nhấn hồng cho app đang dùng và chấm tím báo cửa sổ bị khuất trái/phải; bấm trái để chuyển/xoay vòng giữa các cửa sổ cùng app, bấm giữa để đóng. Khi mở nhiều ứng dụng, `dock-density.sh` tự động thu gọn kích thước ô để dock không bao giờ tràn màn hình.
* **Trung tâm điều khiển (`control-popup.py`)**: Bấm vào cụm điều khiển trên thanh trên để mở popup đa trang ngay dưới thanh:
  * **Trang chính**: Công tắc bật/tắt nhanh Wi-Fi & Bluetooth (kèm nút `›` mở trang chi tiết), Không làm phiền (Dunst), Giữ màn hình sáng (`systemd-inhibit`), Chế độ nguồn (`powerprofilesctl`), Bộ gõ (` VI / EN `), cùng thanh trượt âm lượng và độ sáng.
  * **Trang Wi-Fi**: Quét mạng nền, bấm để kết nối/ngắt, nhập mật khẩu mạng mới ngay tại chỗ, chuột phải để quên mạng.
  * **Trang Bluetooth**: Quản lý thiết bị đã ghép, quét tìm thiết bị mới trong 20s, bấm để kết nối/ghép, chuột phải để gỡ.
  * **Trang Âm thanh**: Chọn thiết bị đầu ra (loa/tai nghe) & đầu vào (micro), chỉnh âm lượng tổng và âm lượng riêng từng ứng dụng.
* **Nút VPN (`vpn.sh`)**: Nằm giữa Wi-Fi và Bluetooth trên thanh trên. Bấm trái để bật/tắt, bấm phải để chọn kết nối. Dùng mọi kết nối WireGuard/VPN của NetworkManager (khuyên dùng **Proton VPN Free**: ra Internet bằng IP nước ngoài nên vào được các trang chặn IP Việt Nam), hoặc Cloudflare WARP nếu có `warp-cli`. Icon màu hồng = đang bật, vàng = đang nối, mờ = tắt/chưa có. Xem mục [Cài VPN](#3b-cài-vpn-proton-vpn-free).
* **Popup công cụ khi rê chuột (`tools-popup.py`)**: Rê chuột vào nút tiện ích `󱁤` trên dock để mở nhanh thanh ngang bên trái dock: **Clipboard**, **Chụp/Quay màn hình** (chuyển ngay sang 6 chế độ chụp toàn màn / cửa sổ / vùng / vùng + vẽ Satty / quay toàn màn / quay vùng, có tuỳ chọn thu tiếng máy hoặc ghép tiếng máy + micro qua sink ảo), **Phím tắt**, **Không làm phiền**. Khi đang quay, nút trên dock chuyển sang báo đỏ (`REC`), bấm vào để dừng.
* **Lịch Âm lịch Việt Nam (`clock-popup.py`)**: Bấm vào đồng hồ giữa thanh trên để mở popup lịch tháng (bắt đầu từ thứ Hai) kèm **ngày âm lịch** dưới mỗi ngày dương (thuật toán Hồ Ngọc Đức UTC+7, đánh dấu mùng 1 `1/tháng` và ngày Tết).

### 🚀 Trình khởi chạy, Giao diện & Hệ thống
* **Tiết kiệm pin (`power-watch.sh`)**: Viền cửa sổ xoay màu (~3–4% CPU) tự tắt khi rút sạc hoặc ở chế độ `power-saver`, tự bật lại khi cắm sạc. Ghi đè: `~/.config/hypr/scripts/power-watch.sh set on|off|auto`.
* **Trình mở ứng dụng `walker` (GTK4 + `elephant`)**: Giao diện một khung 600px giữa màn hình với nền ảnh Kafka làm mờ, gợi ý tiếng Việt; hỗ trợ tiền tố `>` để chạy lệnh shell, `$` để chuyển cửa sổ, `=` để tính toán (vd `=2+3*4`, plugin `elephant-calc`), `.` để tìm emoji/ký tự (vd `.heart`, plugin `elephant-symbols`), `;` để liệt kê chế độ.
* **Bảng chọn `rofi`**: Thiết kế 2 cột kèm banner dọc của Kafka (`rofi/kafka.rasi`) cho lịch sử clipboard (`cliphist`), menu đóng ứng dụng và danh sách cửa sổ ẩn; cùng các popup `kafka-power.rasi` (menu nguồn) và `kafka-actions.rasi` (hộp thao tác nhanh ở đáy dock).
* **Trình sửa phím tắt đồ hoạ (`keybinds-editor.py`)**: Ứng dụng GTK4 cho phép xem toàn bộ phím tắt, thêm mới, ghi đè hoặc vô hiệu hoá phím mặc định. Cấu hình riêng được lưu tách biệt vào `hypr/keybinds.lua` và nạp bằng `pcall` sau phím mặc định nên không cần chạm vào `hypr/hyprland.lua`.
* **Gõ tiếng Việt ổn định (`fcitx5-unikey`)**: Cấu hình sẵn biến môi trường Wayland/XWayland, tự bật tiếng Việt (`ActiveByDefault=True`, `ShareInputState=All` — một trạng thái dùng chung cho mọi app) kèm chế độ tự khôi phục từ tiếng Anh (`AutoNonVnRestore`) và nút chỉ báo `VI / EN` trên thanh trên. Bộ giám sát `ime-guard.sh` chạy đầu tiên khi Hyprland khởi động (trước Waybar): xuất môi trường phiên (`WAYLAND_DISPLAY`, `GTK_IM_MODULE`, `QT_IM_MODULE`, `XMODIFIERS`...) cho D-Bus/systemd, bật sẵn tiếng Việt và tự hồi phục sau mỗi 5 giây nếu `fcitx5` chết, chạy nhiều bản, sai `WAYLAND_DISPLAY` hoặc chưa nối frontend Wayland (báo qua `dunst`). Các lệnh hỗ trợ: `ime-guard.sh status` (mã `0` = khỏe), `restart`, `daemon`, `env`.
* **Màn hình khóa & Đăng nhập đồng bộ**:
  * **Khóa màn hình (`hyprlock` + `hypridle`)**: Đồng bộ hình nền hiện tại qua `~/.cache/kafka_current_wallpaper`, tự giảm sáng, khóa màn hình và tắt màn hình khi nghỉ.
  * **Đăng nhập (`greetd` + `ReGreet`)**: Giao diện đăng nhập tối giản chạy trong `cage` với nền Kafka phủ mờ tối và cơ chế dự phòng an toàn (`agreety`).

---

## 📋 Yêu cầu hệ thống

* **Hệ điều hành**: **Arch Linux** (hoặc bản phân phối dẫn xuất từ Arch) với **Hyprland 0.57+** (sử dụng cấu hình Lua `hypr/hyprland.lua`).
* **Quyền hạn**: Tài khoản có quyền `sudo` để cài đặt gói hệ thống và kích hoạt dịch vụ.
* **Trình quản lý AUR**: `yay` hoặc `paru` để cài các gói AUR (`hyprshell-bin`, `walker-bin`, `elephant-bin` cùng các plugin `elephant-*-bin`). Chưa có thì `install.sh` đề nghị cài `yay-bin`.
* **Độ phân giải tham chiếu**: **1920×1080 (1080p)**. Tọa độ các popup (`control-popup.py`, `tools-popup.py`), vùng rê chuột trên dock (`HOT_*`), góc bo lõm (`corner-fillet.py`) và chiều cao dock (`dock-density.sh`) được đo chuẩn theo màn hình 1080p.

---

## 🚀 Cài đặt nhanh

```bash
git clone https://github.com/TaZek244/kafka-hyprland-dotfiles.git ~/kafka-hyprland-dotfiles
cd ~/kafka-hyprland-dotfiles && ./install.sh
```

---

## ⚙️ Tùy chọn `install.sh`

| Tùy chọn | Mô tả |
| :--- | :--- |
| *(không tham số)* | Chạy tất cả các bước: `packages, link, assets, system, fcitx, services, check` |
| `--only a,b` | Chỉ chạy các bước được liệt kê (phân cách bằng dấu phẩy) |
| `--skip a,b` | Bỏ qua các bước được liệt kê |
| `--greetd` | Cài thêm màn hình đăng nhập `greetd` + `ReGreet` (chưa đổi trình đăng nhập hiện tại) |
| `--greetd-switch` | Cài và chuyển hẳn sang `greetd` (tắt GDM nếu đang bật) |
| `--dry-run` | Chỉ in các lệnh sẽ chạy mà không thực thi |
| `-y`, `--yes` | Không hỏi xác nhận trước khi chạy |
| `--no-aur` | Bỏ qua việc cài đặt các gói AUR |
| `--force-fcitx` | Ghi đè cấu hình `fcitx5` hiện có của người dùng |
| `--force-assets` | Tạo lại cả các ảnh phụ đã có (mặc định chỉ tạo ảnh còn thiếu) |
| `-h`, `--help` | Hiển thị hướng dẫn sử dụng |

### Chi tiết các bước cài đặt

1. **`packages`**: Cài đặt toàn bộ gói phụ thuộc từ kho chính thức (`pacman`) và AUR (`yay`/`paru`).
2. **`link`**: Tạo symlink từ các thư mục cấu hình trong repo vào `~/.config/`; tự động sao lưu cấu hình cũ của bạn vào `~/.config/backup_before_kafka_<ngày>`.
3. **`assets`**: Cắt và tạo các ảnh phụ (banner Rofi, nền mờ Walker, nền ReGreet, ảnh vuông Fastfetch) từ ảnh nền gốc trong `wallpapers/`; chỉ tạo ảnh còn thiếu (thêm `--force-assets` để tạo lại).
4. **`system`**: Thiết lập theme GTK3 tối (`Adwaita` với `prefer-dark` và màu nhấn), gán ứng dụng mặc định qua `xdg-mime` (`thunar`, `imv`, `mpv`, `mousepad`) và cấp quyền thực thi (`+x`) cho toàn bộ script.
5. **`fcitx`**: Tạo cấu hình chuẩn cho `fcitx5` + `unikey` trong `~/.config/fcitx5/` (`keyboard-us` ở vị trí 0, `unikey` làm `DefaultIM`, `ShareInputState=All`).
6. **`services`**: Kích hoạt các dịch vụ hệ thống và người dùng cần thiết (`NetworkManager`, `bluetooth`, `power-profiles-daemon`, `elephant`).
7. **`check`**: Kiểm tra cú pháp cấu hình Hyprland (`Hyprland --verify-config`) và chạy `--selftest` cho các script thành phần.

---

## 🖼️ Ảnh nền (Quan trọng)

> [!IMPORTANT]
> Repo này **KHÔNG** đính kèm các hình ảnh nhân vật Kafka vì bản quyền hình ảnh thuộc về **HoYoverse** và các **tác giả fan art**.

Để giao diện hiển thị đầy đủ hình nền và banner như thiết kế:

1. Tự tải hình ảnh mà bạn có quyền sử dụng và đặt vào thư mục `wallpapers/` với đúng tên file sau:
   * **`wallpapers/kafka_landscape_3.jpg`**: Ảnh ngang tỉ lệ 16:9 (khuyến nghị `1920x1080`), dùng làm hình nền màn hình chính, màn hình khóa `hyprlock` và tạo nền mờ cho màn hình đăng nhập `ReGreet`.
   * **`wallpapers/kafka_main.jpg`**: Ảnh dọc, dùng để script cắt tự động thành banner cột trái của Rofi (`rofi/kafka-banner.jpg`, `300x476`), nền mờ của Walker (`walker/themes/kafka/bg.jpg`, `600x480`) và ảnh vuông hiển thị trong Fastfetch / màn hình khóa (`Kafka_thumbail.jpg`).
2. Chạy lệnh tạo tài nguyên ảnh phụ:
   ```bash
   ./install.sh --only assets --force-assets
   ```

Nếu bạn **chưa bỏ ảnh** vào `wallpapers/`, bước `assets` sẽ tự động sinh các tấm ảnh nền **gradient màu chủ đề Kafka** làm ảnh thay thế để mọi thành phần (Waybar, Hyprlock, Walker, Rofi, ReGreet, Fastfetch) vẫn hoạt động bình thường ngay từ lần chạy đầu tiên. Xem thêm hướng dẫn chi tiết trong `wallpapers/README.md`.

---

## ⌨️ Bảng phím tắt chính

> Phím chính (`$mainMod`) là **`Super`** (phím Windows / ⌘). Các phím dưới đây được định nghĩa trong `hypr/hyprland.lua` và `hyprshell`.

### Khởi chạy & Hệ thống
| Phím tắt | Chức năng |
| :--- | :--- |
| **`Super + Space`** / **`Super + R`** | Mở trình tìm & khởi chạy ứng dụng **Walker** |
| **`Nhấn-thả riêng Super`** | Bật/tắt chế độ tổng quan cửa sổ & workspace (**hyprshell**) |
| **`Alt + Tab`** / **`Super + Tab`** | Chuyển nhanh giữa các cửa sổ (**hyprshell**): giữ phím bổ trợ, bấm Tab để sang tiếp, thả ra để nhảy tới (`Shift` = đi ngược) |
| **`Super + V`** | Mở lịch sử Clipboard (`cliphist` + Rofi) |
| **`Super + A`** | Bật/tắt cửa sổ nổi chạy sóng nhạc `cava` (`kitty --class kafka-cava`) |
| **`Super + Shift + A`** | Bật/tắt **sóng nhạc làm hình nền** (`cava-wallpaper.py`: lớp layer-shell nằm dưới mọi cửa sổ, bấm xuyên qua, tự ngủ khi im lặng) |
| **`Super + Ctrl + cuộn`** / **`Super + Ctrl + = / -`** / **`Super + Ctrl + 0`** | Kính lúp: phóng to / thu nhỏ / về bình thường |
| **`Super + Escape`** | Khóa màn hình ngay lập tức (`hyprlock`) |
| **`Super + M`** | Mở menu nguồn (`powermenu.sh`) |

### Quản lý cửa sổ
| Phím tắt | Chức năng |
| :--- | :--- |
| **`Super + H / J / K / L`** | Di chuyển tiêu điểm (focus) giữa các cửa sổ theo kiểu Vim |
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

### Bố cục cuộn (`scrolling`), Chế độ Desktop & Chia khu
| Phím tắt | Chức năng |
| :--- | :--- |
| **`Super + D`** | Chuyển đổi giữa **Layout cuộn** và **Chế độ Desktop** (cửa sổ nổi tự do) |
| **`Super + G`** | Xoay vòng độ rộng cột đang chọn (`colresize +conf`) |
| **`Super + -`** / **`Super + =`** | Thu hẹp / Nới rộng độ rộng cột hiện tại 10% |
| **`Super + Ctrl + ← / →`** | Dời cột hiện tại sang trái / phải (`swapcol l/r`) |
| **`Super + ,`** / **`Super + .`** | Gộp cửa sổ vào cột bên cạnh hoặc tách ra (`consume_or_expel prev/next`) |
| **`Super + P`** | Tách cửa sổ đang chọn ra khỏi cột chồng thành cột riêng (`promote`) |
| **`Super + Shift + G`** | Mở bảng chia ô cố định theo tỉ lệ cho workspace đang xem (`tile-menu.sh`) |
| **Vuốt 3 ngón ngang / dọc** | Cuộn ngang các cột (`scroll_move`) / Chuyển workspace |

### Chụp & Quay màn hình (`capture.sh`)
| Phím tắt | Chức năng |
| :--- | :--- |
| **`Print`** | Mở menu Rofi chọn 6 chế độ chụp / quay màn hình |
| **`Shift + Print`** | Chụp ngay toàn màn hình (lưu vào `~/Pictures/Screenshots`) |
| **`Super + Shift + S`** | Chụp một vùng màn hình |
| **`Super + Shift + R`** | Bắt đầu quay màn hình (có hỏi nguồn âm thanh) hoặc dừng quay (lưu vào `~/Videos/Recordings`) |

---

## 📂 Cấu trúc thư mục

| Thư mục | Mô tả |
| :--- | :--- |
| `hypr/` | Cấu hình Hyprland 0.57+ (`hyprland.lua`), layout chia khu (`kafka-tile.lua`), phím tắt người dùng (`keybinds.lua`), `hyprlock.conf`, `hypridle.conf` và toàn bộ script/popup trong `hypr/scripts/`. |
| `waybar/` | Cấu hình 2 thanh khung chữ L (`config.jsonc`), bảng màu & giao diện phẳng (`style.css`), cùng file mật độ dock tự sinh (`dock-density.css`). |
| `walker/` | Cấu hình trình mở ứng dụng Walker 2.x (`config.toml`) và theme `kafka` (`layout.xml`, `style.css`, `item.xml`). |
| `rofi/` | Theme Rofi 2 cột có banner (`kafka.rasi`), menu nguồn (`kafka-power.rasi`) và hộp thao tác nhanh cạnh dock (`kafka-actions.rasi`). |
| `kitty/` | Cấu hình terminal Kitty (`kitty.conf`) nền mờ `0.88`, phím `Ctrl+C` (`copy_or_interrupt`) / `Ctrl+V` thông minh và cỡ cửa sổ chuẩn cho chế độ Desktop. |
| `dunst/` | Cấu hình thông báo nổi góc trên bên phải (`dunstrc`); số thông báo hiện trên Waybar (`custom/notifications`). |
| `greetd/` | Cấu hình màn hình đăng nhập `greetd` + `ReGreet` (`config.toml`, `regreet.toml`, `regreet.css`), cấu hình dự phòng `agreety` (`config-fallback.toml`) và script `install-greetd.sh`. |
| `gtk/` | Thiết lập giao diện tối và màu nhấn cho ứng dụng GTK3 (`gtk-3.0/settings.ini`, `gtk-3.0/gtk.css`). |
| `hyprshell/` | Cấu hình tổng quan cửa sổ kiểu GNOME và bộ chuyển `Alt + Tab` (`config.toml`, `styles.css`). |
| `cava/` | Cấu hình sóng nhạc terminal (`config`), bảng màu và bộ shader OpenGL (`cava/shaders/`). |
| `btop/` | Cấu hình trình theo dõi tài nguyên hệ thống (`btop.conf`) kèm bảng màu `themes/kafka.theme`. |
| `imv/` | Cấu hình trình xem ảnh nhẹ `imv` (`imv/config`), hỗ trợ duyệt cả thư mục bằng phím mũi tên. |
| `mpv/` | Cấu hình trình phát video/nhạc `mpv` (`mpv/mpv.conf`). |
| `fastfetch/` | Cấu hình hiển thị thông tin hệ thống kèm ảnh vuông của Kafka qua giao thức đồ họa Kitty (`config.jsonc`). |
| `wallpapers/` | Nơi đặt ảnh nền người dùng (`kafka_landscape_3.jpg`, `kafka_main.jpg`) và hướng dẫn chuẩn bị ảnh. |

---

## 🎨 Tùy biến

### 1. Đổi bảng màu giao diện
Toàn bộ màu sắc của thanh trên, dock và trạng thái được gom tập trung ở đầu file `waybar/style.css` qua các biến `@define-color`:
* `@bg`: Màu nền chung của khung chữ L (`rgba(44, 36, 52, 0.93)`).
* `@accent` (`#c94785`): Màu nhấn làm **nền** (khối Kafka, workspace đang chọn, nút bật/thanh trượt trong popup — đảm bảo độ tương phản chữ trắng).
* `@accent_fg` (`#e0559a`): Màu nhấn sáng hơn cùng sắc độ dùng cho **chữ và icon** trên nền tối (chỉ báo bộ gõ `VI`, icon góc mạng nhện, cột đang dùng, vạch ứng dụng trên dock).

Sau khi sửa `waybar/style.css`, tải lại giao diện bằng lệnh:
```bash
killall -SIGUSR2 waybar
```
*(Nếu đổi màu nền `@bg` hoặc viền `@line`, hãy đồng bộ lại hằng số `BG`/`BORDER` trong `hypr/scripts/corner-fillet.py` và chuỗi CSS ở đầu `control-popup.py`, `tools-popup.py`).*

### 2. Thêm hoặc sửa phím tắt riêng
Mở **Trình sửa phím tắt** từ nút `󰌌` trong popup công cụ trên dock (hoặc chạy `~/.config/hypr/scripts/keybinds-editor.py`). Mọi thay đổi sẽ được ghi vào `hypr/keybinds.lua` dưới dạng bảng Lua và tự động ghi đè lên phím mặc định khi `hyprctl reload` mà không làm bẩn `hypr/hyprland.lua`.

### 3b. Cài VPN (Proton VPN Free)
1. Tạo tài khoản miễn phí tại [account.protonvpn.com](https://account.protonvpn.com), vào **Downloads → WireGuard configuration**.
2. Chọn **Platform: GNU/Linux**, chọn một máy chủ **Free** (Hà Lan/Mỹ/Nhật...), bấm **Create** rồi **Download** để tải file `.conf` (ví dụ `~/Downloads/proton-free.conf`).
3. Nhập vào NetworkManager và chọn làm VPN mặc định của nút:
   ```bash
   ~/.config/hypr/scripts/vpn.sh import ~/Downloads/proton-free.conf
   ```
4. Bấm nút VPN trên thanh trên để bật/tắt. Kiểm tra: `~/.config/hypr/scripts/vpn.sh list`. Muốn đổi máy chủ thì tải thêm file `.conf` khác, nhập tương tự rồi bấm phải vào nút để chọn.

File `.conf` chứa khoá riêng của bạn: **đừng** đưa vào repo.

### 3. Đổi hình nền
* Đặt ảnh ngang 16:9 mới vào `wallpapers/` (tên bắt đầu bằng `kafka_`, ví dụ `kafka_custom_1080p.jpg`) rồi đặt làm hình nền hiện tại:
  ```bash
  ~/.config/hypr/scripts/wallpaper-cycle.sh set ~/.config/hypr/wallpapers/kafka_custom_1080p.jpg
  ```
* Nếu có ảnh dọc và muốn ghép thành ảnh ngang 1920×1080 có nền kính mờ viền hồng, dùng ImageMagick theo công thức trong `CLAUDE.md` hoặc cập nhật `kafka_landscape_3.jpg` / `kafka_main.jpg` rồi chạy lại `./install.sh --only assets`.

---

## 🛠️ Khắc phục sự cố

* **Waybar mất khay hệ thống (System Tray) sau khi khởi động lại từ terminal**:
  Không chạy trực tiếp `setsid -f waybar` từ một shell thiếu biến môi trường D-Bus của phiên. Hãy khởi động Waybar thông qua Hyprland để nhận đầy đủ môi trường:
  ```bash
  killall waybar
  hyprctl dispatch "hl.dsp.exec_cmd('waybar')"
  ```
* **Không gõ được dấu**:
  Kiểm tra tình trạng bộ gõ trước tiên (mã thoát `0` nghĩa là khỏe):
  ```bash
  ~/.config/hypr/scripts/ime-guard.sh status
  ```
  Nếu báo lỗi, **bấm giữa ô `VI / EN`** trên thanh trên để khởi động lại bộ gõ (bên trái để chuyển `VI / EN`, bên phải để cấu hình `fcitx5`), hoặc chạy tay:
  ```bash
  ~/.config/hypr/scripts/ime-guard.sh restart
  ```
  Terminal mở từ trước nếu vẫn gõ không dấu thì **mở cửa sổ mới**, vì cửa sổ cũ còn giữ Input Context cũ. Nếu file `profile` của `fcitx5` bị ghi đè sai thứ tự bộ gõ, chạy lại `./install.sh --only fcitx --force-fcitx`.
  Nguyên nhân gốc đã được xử lý: trước đây Waybar chạy trước `fcitx5`, ô `VI / EN` gọi `fcitx5-remote` khiến D-Bus tự bật một bản `fcitx5` có thể thiếu môi trường Wayland, rồi lệnh `fcitx5 -d` của Hyprland thấy đã có bản chạy nên thoát — nên có lúc đăng nhập gõ được, lúc không. Nay `ime-guard.sh` xuất môi trường cho D-Bus ngay từ đầu, còn `ime-status.sh` chỉ gọi `fcitx5-remote` khi `fcitx5` đã chạy; trạng thái gõ dùng chung cho mọi app (`ShareInputState=All`).
* **Màn hình đăng nhập `greetd` / `ReGreet` gặp sự cố không đăng nhập được**:
  Nhấn `Ctrl + Alt + F2` để chuyển sang TTY, đăng nhập bằng tài khoản của bạn và chạy:
  ```bash
  ~/kafka-hyprland-dotfiles/greetd/install-greetd.sh --revert
  ```
  *(Hoặc nếu không còn thư mục repo: `sudo cp /etc/greetd/config-fallback.toml /etc/greetd/config.toml && sudo systemctl restart greetd`)*. Lệnh này sẽ chuyển `greetd` về trình đăng nhập dạng chữ **`agreety`**; sau khi đăng nhập chỉ cần gõ `start-hyprland`.
* **Trình mở ứng dụng `walker` hiển thị danh sách trống**:
  Nguyên nhân thường do `elephant` và các gói plugin (`elephant-desktopapplications`, `elephant-runner`, `elephant-windows`) không khớp phiên bản biên dịch Go. Hãy đảm bảo cài đặt **cùng loại gói `-bin`** cho cả `elephant-bin` lẫn tất cả plugin, sau đó khởi động lại dịch vụ:
  ```bash
  systemctl --user restart elephant.service
  pkill -x walker; setsid -f walker --gapplication-service
  ```
  Xem log chi tiết bằng `journalctl --user -u elephant -n 20`.

---

## 🙏 Ghi công (Credits)

* **Shaders sóng nhạc Cava**: Các shader OpenGL `orion_circle.frag`, `orion_circle_rotate.frag`, `orion_saturn_core.frag`, `orion_saturn_subring.frag` trong `cava/shaders/` thuộc bản quyền của tác giả **rezky_nightky** (giữ nguyên ghi chú bản quyền và giấy phép SPDX trong từng file nguồn).
* **Phần mềm nguồn mở**: Xây dựng trên nền tảng [Hyprland](https://hypr.land/), [Waybar](https://github.com/Alexays/Waybar), [Walker](https://github.com/abenz1267/walker) & [Elephant](https://github.com/abenz1267/elephant), [hyprshell](https://github.com/H3rmt/hyprshell), [Rofi](https://github.com/davatorium/rofi), [ReGreet](https://github.com/rharish101/ReGreet), [Kitty](https://sw.kovidgoyal.net/kitty/), [Dunst](https://dunst-project.org/), [Cava](https://github.com/karlstav/cava), [Fcitx5-Unikey](https://github.com/fcitx/fcitx5-unikey) và thuật toán âm lịch Việt Nam của **Hồ Ngọc Đức**.
* **Tuyên bố miễn trừ**: Nhân vật **Kafka** và trò chơi **Honkai: Star Rail** là tài sản trí tuệ và thương hiệu của **HoYoverse / COGNOSPHERE PTE. LTD.** Đây là dự án cấu hình máy tính do người hâm mộ thực hiện (fan-made), hoàn toàn phi thương mại và không có bất kỳ liên kết chính thức nào với HoYoverse.

---

## 📄 Giấy phép (License)

Mã nguồn script và các file cấu hình trong kho lưu trữ này được phát hành theo giấy phép **MIT** (xem chi tiết trong file [`LICENSE`](LICENSE)), ngoại trừ các file có ghi chú bản quyền và giấy phép riêng ở đầu file: bộ shader `cava/shaders/orion_*` (MIT, rezky_nightky) và `hypr/scripts/lunar_vn.py` (chuyển ngữ thuật toán âm lịch của Hồ Ngọc Đức, chỉ dùng cá nhân, phi thương mại).
