# Báo Cáo Khảo Sát Thiết Kế Desktop Shell / Dotfiles Cho Niri & Đề Xuất Cho Bộ "Kafka" (HSR)

> Báo cáo do Gemini (Antigravity) tìm trên web ngày 2026-11-18, Claude đọc lại. Tên/đường dẫn dự án chưa được kiểm chứng từng cái (ví dụ việc DankMaterialShell đổi tên) — mở link để xác nhận trước khi dựa vào.

## 1. Phân Tích Nhanh Thiết Kế Hiện Tại Của Bộ "Kafka" (Hyprland)

Dựa trên `config.jsonc`, `style.css` và ảnh chụp `hien-tai.png`:
* **Cấu trúc tổng thể:** Hai thanh Waybar độc lập (`topbar` ngang ở trên cao 40px và `dockbar` dọc bên phải rộng 60px) cùng dùng nền rượu vang `rgba(34, 16, 29, 0.95)` và viền hồng `#b8326a` (1px).
* **Điểm nối chữ L thông minh:** Góc dưới-phải của `topbar` để vuông (`border-radius: 14px 14px 0 14px`), `padding-right: 0`, đặt module `#custom-corner` (icon mạng nhện `󰯊`, nền gradient `#9b4dca -> #b8326a -> #8f2456`, viền trái vàng `#d4af6a`) khớp từng pixel với đỉnh của `dockbar` (`margin-top: 0`, `border-top: none`, `border-radius: 0 0 20px 20px`), tạo cảm giác một khung chữ L liền mạch.
* **Cách tổ chức module:**
  * **Thanh trên (`topbar`):** Các "viên thuốc" (floating islands/pills) nền `#1f1629` bo góc 9px: cụm `group/kafka` (launcher + nút chuyển chế độ cuộn/Desktop), `hyprland/workspaces` (số La Mã I–V), `network#speed`, giữa là `clock` + `mpris`, phải là `pulseaudio`, `backlight`, `group/system` (CPU · RAM · Temp ngăn bằng vạch dọc `#3b1a33`), `battery`, `idle_inhibitor`, `custom/notifications`, và chốt bằng `custom/corner`.
  * **Thanh phải (`dockbar`):** Chia khối bằng vạch ngang `#3b1a33`: đầu dock là `group/status` (Wi-Fi, Bluetooth, bộ gõ `VI`/`EN` thay cho tray để không nhảy vị trí), nút `custom/apps` nổi bật, `custom/tools` (hover mở popup ngang bên trái dock), `group/pinned` (5 app ghim), `tray`, giữa là thẻ `group/windows` (`custom/hidden` + 10 slot `image#w1..w10` do `dock-apps.py` vẽ icon gộp kèm badge `xN` và viền vàng khi active, kèm `dock-density.sh` tự co giãn CSS), đáy là `group/actions` (nút menu nhanh + nút nguồn lớn 52px).

---

## 2. Khảo Sát Các Bộ Dotfiles / Desktop Shell Nổi Tiếng Cho Niri (Và Tham Khảo Từ Hyprland)

### Bảng Tổng Hợp Nhanh (8 Dự Án)

| # | Tên dự án | Công cụ Bar/Dock | Bố cục chính | Tận dụng đặc trưng Niri (Overview, Cột cuộn, Workspace dọc, IPC) |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Noctalia Shell** | Quickshell (QtQuick/QML) | Thanh ngang + Dock + Control Center | **Rất sâu:** Có plugin vẽ minimap cột/cửa sổ, khớp layer-rule với Niri Overview, đọc `niri msg` event-stream. |
| 2 | **DankMaterialShell (Dux Shell / DMS)** | Quickshell + Go | Top bar Material 3 + Dux Dash popup | **Sâu:** Tương thích native với workspace động & cột cuộn của Niri, `dms setup` tự chèn keybind vào `config.kdl`, lớp phủ khớp Overview. |
| 3 | **iNiR (`snowarch/inir`)** | Quickshell (fork từ end-4 cho Niri) | Top bar + Dock + 2 Sidebar + Overview riêng | **Rất sâu:** Port chuyên biệt cho Niri, nhận diện cột cuộn, tích hợp Overview riêng có live icon & quản lý đa màn hình theo Niri IPC. |
| 4 | **Caelestia Shell** | Quickshell (QML + C++20) | Khung viền bao quanh màn hình ("Picture Frame") + Bar/Dock morphing | *(Thiết kế gốc cho Hyprland)* Không dùng IPC Niri mặc định, nhưng **kiến trúc khung viền liền mạch** là mẫu mực cho kiểu chữ L của Kafka. |
| 5 | **end-4 `illogical-impulse`** | Quickshell (trước đây là AGS) | Top bar viên thuốc Material You + Floating Dock + 2 Sidebar | *(Thiết kế gốc cho Hyprland, đã có bản port sang Niri là iNiR)* Nổi tiếng về cách nhóm module pill, sidebar trượt và dock tự ẩn/hiện. |
| 6 | **waybar-niri-windows (`calico32` & `Qweasd123tg`)** | Waybar + Module/Script ngoài | Thanh Waybar ngang kèm **Minimap cột cuộn** | **Đặc thù 100% Niri:** Biến dải cột cuộn ngang (scrolling columns) và ngăn xếp cửa sổ thành bản đồ thu nhỏ ngay trên Waybar qua Niri IPC. |
| 7 | **Delta Shell (`Sinomor/delta-shell`)** | AGS (Aylur's Gtk Shell) | Top bar kiểu macOS + Quick Settings + Dock/Taskbar | **Tốt:** Hỗ trợ cả Niri và Hyprland qua IPC, hiển thị workspace động và trạng thái cửa sổ theo thời gian thực. |
| 8 | **Eww / Waybar Niri Rices (`druskus20/eww-niri-workspaces`, `okyashgajjar/Low-Spec-Niri-Dotfiles`)** | Waybar / Eww + Rust IPC helper | Bar viên thuốc tối giản hoặc Bar chuyển đổi nhiều layout | **Tốt:** Dùng `niri/workspaces` native của Waybar hoặc binary Rust đọc `niri-ipc` event-stream để hiển thị dải workspace động dọc. |

---

### Chi Tiết Từng Dự Án

#### 1. Noctalia Shell
* **Link:** [github.com/noctalia-dev/noctalia](https://github.com/noctalia-dev/noctalia) | Trang chủ: [noctalia.dev](https://noctalia.dev) (Các bản rice Niri tiêu biểu dùng Noctalia: [sirine-zanina/niri-dotfiles](https://github.com/sirine-zanina/niri-dotfiles), [noclueatthis/niri-noctalia-dotfiles](https://github.com/noclueatthis/niri-noctalia-dotfiles), [CachyOS/cachyos-niri-settings](https://github.com/CachyOS/cachyos-niri-settings))
* **Công cụ:** **Quickshell** (QML).
* **Bố trí & Phong cách Bar/Dock:**
  * Thanh trạng thái hiện đại, sắc nét với 3 chế độ hiển thị workspace: *Regular* (viên thuốc có hiệu ứng chuyển động), *Minimal* (nhãn tối giản không nền), và **Focus Hint** (các workspace không dùng hiện chấm nhỏ, riêng workspace đang dùng nở rộng thành viên thuốc chứa icon của ứng dụng đang focus).
  * Hệ thống widget và plugin phong phú (`niri-ribbon`, control center, notification, launcher đồng bộ màu theo hình nền).
* **Tận dụng tính năng riêng của Niri:**
  * **Niri Workspace Preview / Stack:** Có tiện ích mở rộng vẽ **bản đồ thu nhỏ (minimap)** theo đúng tỷ lệ các cột (columns) và cửa sổ xếp chồng (stacks) trong workspace của Niri mà không cần chụp ảnh màn hình nặng nề. Bấm hoặc cuộn chuột trên widget sẽ đổi focus cột hoặc bật Niri Overview.
  * **Tích hợp Niri Overview:** Hỗ trợ cấu hình `layer-rule` trong `config.kdl` của Niri để lớp nền (backdrop) của Noctalia lùi vào trong Overview của Niri, giúp thanh bar và hình nền thu phóng mượt cùng các cột cửa sổ.
  * **IPC Event-stream:** Lắng nghe trực tiếp luồng sự kiện từ `niri msg` để xử lý cả workspace trống tự sinh ở cuối danh sách (trailing empty workspace đặc trưng của Niri).

#### 2. DankMaterialShell (nay là Dux Modular Shell / DMS)
* **Link:** [github.com/duxlabs-dev/dux-shell](https://github.com/duxlabs-dev/dux-shell) (trước đây là `AvengeMedia/DankMaterialShell`)
* **Công cụ:** **Quickshell** (QtQuick) kết hợp backend **Go**.
* **Bố trí & Phong cách Bar/Dock:**
  * Được tài liệu chính thức của Niri giới thiệu như giải pháp trọn gói thay thế Waybar + Fuzzel + Mako + Swaylock.
  * Thanh trên (Top Bar) mang ngôn ngữ **Material Design 3**, hiển thị các viên thuốc (pills) chỉ báo workspace, tiêu đề cửa sổ đang mở, điều khiển nhạc, khay hệ thống (hỗ trợ menu chuột phải), mạng/Bluetooth và đồng hồ.
  * Điểm nhấn là **Dux Dash** (bảng điều khiển thả xuống từ thanh bar) gom lịch, thời tiết, đồ thị CPU/RAM, âm thanh và chế độ nguồn vào một mặt phẳng nổi có độ mờ (blur) và mật độ giao diện tùy chỉnh.
* **Tận dụng tính năng riêng của Niri:**
  * Lệnh `dms setup` tự động ghi các phím tắt tích hợp vào `config.kdl` của Niri.
  * Theo dõi workspace động và bố cục cột cuộn của Niri theo thời gian thực; các lớp phủ (launcher, control center) được thiết kế để bật đè lên chế độ **Overview** (zoom-out) của Niri mà không phá vỡ hoạt ảnh chuyển cột.

#### 3. iNiR (`snowarch/inir`)
* **Link:** [github.com/snowarch/inir](https://github.com/snowarch/inir)
* **Công cụ:** **Quickshell** (bản đại tu và thiết kế riêng cho Niri từ nhánh `illogical-impulse` của end-4).
* **Bố trí & Phong cách Bar/Dock:**
  * Chạy toàn bộ bar, dock, 2 sidebar (trái: app launcher, phải: quick settings & thông báo) trong một tiến trình Quickshell duy nhất.
  * Cho phép chuyển nóng giữa 2 họ bố cục: **`ii` (Material nổi)** và **`waffle` (thanh tác vụ kiểu Windows 11)**, cùng 5 phong cách thị giác: *Material* (đặc), *Cards* (đổ bóng nhẹ), *Aurora* (kính mờ), *iNiR* (viền sắc kiểu TUI — rất gần với thẩm mỹ viền 1px của bộ Kafka), và *Angel* (neo-brutalism).
  * **Dock riêng biệt:** Hỗ trợ ghim ứng dụng, chỉ báo ứng dụng đang mở và kéo-thả để sắp xếp lại vị trí.
* **Tận dụng tính năng riêng của Niri:**
  * Xây dựng **Overview chuyên biệt cho Niri**: hiển thị toàn cảnh các workspace xếp dọc và các cột cửa sổ ngang kèm icon ứng dụng trực tiếp, lịch và lịch sử thông báo.
  * Giao tiếp trực tiếp với Niri IPC để quản lý workspace độc lập trên từng màn hình (multi-monitor awareness).

#### 4. Caelestia Shell (`caelestia-dots/shell`)
* **Link:** [github.com/caelestia-dots/shell](https://github.com/caelestia-dots/shell) (cùng bộ dotfiles chính [github.com/caelestia-dots/caelestia](https://github.com/caelestia-dots/caelestia))
* **Công cụ:** **Quickshell** (`quickshell-git`, Qt6/QML, C++20).
* **Bố trí & Phong cách Bar/Dock:**
  * **Điểm độc đáo nhất — "Picture Frame" (Khung tranh ôm sát màn hình):** Thanh bar và các cạnh màn hình được vẽ nối liền với nhau bằng đường viền bo cong mềm mại ôm trọn lấy vùng làm việc (rất tương đồng về mặt ý tưởng với **khung chữ L nối `topbar` và `dockbar`** của bộ Kafka hiện tại, nhưng Caelestia vẽ trên một bề mặt QML liền khối nên có góc bo lõm — *inverted rounded corner* — tại điểm giao nhau).
  * **Hiệu ứng Morphing:** Khi bấm vào module trên bar (như media, dashboard, launcher), hộp module không bật cửa sổ rời mà "nở" (morph) trực tiếp từ viền thanh bar ra ngoài.
* **Tận dụng tính năng riêng của Niri:**
  * Dự án gốc viết cho Hyprland (chưa hỗ trợ Niri IPC mặc định, dù cộng đồng Niri thường tham khảo cách vẽ khung viền của nó). Tuy nhiên, đây là hình mẫu trực quan nhất để nâng cấp mối nối chữ L giữa thanh trên và dock phải của Kafka.

#### 5. end-4 `dots-hyprland` (`illogical-impulse`)
* **Link:** [github.com/end-4/dots-hyprland](https://github.com/end-4/dots-hyprland)
* **Công cụ:** **Quickshell** (các phiên bản cũ dùng AGS).
* **Bố trí & Phong cách Bar/Dock:**
  * **Thanh trên:** Chia 3 cụm rõ rệt bằng các khung viên thuốc (pills) bo tròn hoàn toàn: cụm trái (tiêu đề cửa sổ / thông tin hệ thống), cụm giữa (workspaces dạng chấm/viên thuốc biến thiên độ rộng + thanh tìm kiếm/đồng hồ), cụm phải (chỉ báo trạng thái hệ thống gộp gọn + nút mở sidebar).
  * **Dock nổi ở đáy:** Tự động ẩn/hiện khi rê chuột sát mép (hover-to-reveal), tách biệt nhóm app ghim và app đang chạy bằng vạch ngăn mảnh, có chấm sáng dưới chân app đang mở.
* **Tận dụng tính năng riêng của Niri:**
  * Bản gốc dành cho Hyprland; khi đưa sang Niri (qua dự án `iNiR` ở mục 3), toàn bộ cơ chế nhóm viên thuốc (pill grouping) và sidebar trượt bên phải được giữ nguyên để phối hợp với cử chỉ vuốt cuộn ngang của Niri.

#### 6. Nhóm Module Taskbar & Minimap Cho Waybar Trên Niri (`waybar-niri-windows`, `waybar-niri-windows_x_taskbar`, `niri-taskbar`)
* **Link:**
  * [github.com/calico32/waybar-niri-windows](https://github.com/calico32/waybar-niri-windows)
  * [github.com/Qweasd123tg/waybar-niri-windows_x_taskbar](https://github.com/Qweasd123tg/waybar-niri-windows_x_taskbar)
  * [github.com/LawnGnome/niri-taskbar](https://github.com/LawnGnome/niri-taskbar)
* **Công cụ:** **Waybar** + Module C/Rust hoặc Script kết nối `niri-ipc`.
* **Bố trí & Phong cách Bar/Dock:**
  * Giữ nguyên thanh Waybar truyền thống nhưng biến khu vực danh sách cửa sổ/workspace thành một **dải bản đồ thu nhỏ (minimap)** hoặc **taskbar theo thứ tự cột**.
  * Thay vì `wlr/taskbar` (vốn sắp xếp cửa sổ lộn xộn theo thứ tự mở và không hiểu khái niệm "cột" của Niri), `niri-taskbar` và `waybar-niri-windows_x_taskbar` sắp xếp các icon ứng dụng **đúng theo thứ tự cột từ trái sang phải** trên dải băng cuộn của Niri, đồng thời làm nổi bật cửa sổ đang nằm trong vùng nhìn thấy (viewport).
* **Tận dụng tính năng riêng của Niri:**
  * **Khai thác triệt để cột cuộn (scrollable columns) & IPC event-stream:** Trong Niri, người dùng rất dễ "quên" các cửa sổ đang nằm khuất bên trái hoặc bên phải màn hình. Các module này đọc tọa độ cột (`column index` / `tile position`) từ `niri msg --json event-stream` để báo cho người dùng biết bên trái/bên phải màn hình còn bao nhiêu cột hoặc app nào đang khuất.

#### 7. Delta Shell (`Sinomor/delta-shell`)
* **Link:** [github.com/Sinomor/delta-shell](https://github.com/Sinomor/delta-shell)
* **Công cụ:** **AGS (Aylur's Gtk Shell)**.
* **Bố trí & Phong cách Bar/Dock:**
  * Phong cách lấy cảm hứng từ macOS kết hợp tiling WM: thanh bar mỏng ở trên cùng, bo góc nhẹ, kết hợp bảng Quick Settings (Control Center) thả xuống ở góc phải và thông báo nổi.
* **Tận dụng tính năng riêng của Niri:**
  * Có backend viết sẵn cho Niri IPC bên cạnh Hyprland, tự động cập nhật danh sách workspace động theo chiều dọc và trạng thái cửa sổ đang focus mà không cần polling thủ công.

#### 8. Các Bộ Dotfiles Waybar & Eww Thuần Niri (`Low-Spec-Niri-Dotfiles` & `eww-niri-workspaces`)
* **Link:**
  * [github.com/okyashgajjar/Low-Spec-Niri-Dotfiles](https://github.com/okyashgajjar/Low-Spec-Niri-Dotfiles) (Waybar)
  * [github.com/o0travaa/niri-dotfiles](https://github.com/o0travaa/niri-dotfiles) (Waybar)
  * [github.com/druskus20/eww-niri-workspaces](https://github.com/druskus20/eww-niri-workspaces) (Eww + Rust IPC)
* **Công cụ:** **Waybar** (sử dụng các module tích hợp sẵn `niri/workspaces`, `niri/window`, `niri/language`) hoặc **Eww**.
* **Bố trí & Phong cách Bar/Dock:**
  * Sử dụng thiết kế nhẹ, ít tốn tài nguyên: thanh đơn hoặc 2 thanh tách rời, dùng CSS tạo các viên thuốc (`border-radius`) và phân biệt trạng thái workspace bằng màu viền/nền (`focused`, `active`, `empty`).
* **Tận dụng tính năng riêng của Niri:**
  * Tận dụng module native `niri/workspaces` của Waybar (phân biệt được workspace đang focus trên màn hình hiện tại `focused`, workspace đang hiển thị trên màn hình khác `active`, và workspace trống ở cuối `empty`), cùng `niri/language` để bắt trạng thái layout bàn phím do chính Niri quản lý.

---

## 3. Gợi Ý Thiết Kế & Nâng Cấp Cho Bộ "Kafka" Khi Chuyển Sang Niri (7 Ý Tưởng Cụ Thể)

Bộ Kafka hiện tại của bạn đã có trình độ hoàn thiện rất cao trên Waybar (đặc biệt là kỹ thuật ghép khung chữ L bằng `#custom-corner`, script `dock-apps.py` vẽ ảnh PNG 44px cho từng slot `image#w1..w10` để gộp cửa sổ kèm badge `xN`, và `dock-density.sh` tự sinh CSS).

Khi chuyển sang **Niri**, khác biệt lớn nhất về tư duy không gian là:
1. **Workspace của Niri xếp theo chiều dọc** (cuộn lên/xuống giữa các workspace) và được tạo/xóa **động** (luôn có 1 workspace trống ở dưới cùng).
2. **Cửa sổ trong 1 workspace xếp thành dải cột cuộn ngang vô tận** (cuộn trái/phải), nên cửa sổ rất dễ trôi ra ngoài mép màn hình mà không cần "ẩn vào scratchpad" như Hyprland.
3. **Niri có chế độ Overview gốc** (zoom-out toàn bộ các dải ngang và workspace dọc) cực mượt.

Dưới đây là **7 ý tưởng cụ thể** được thiết kế riêng cho bảng màu Kafka (`#141118`, `#22101d`, `#b8326a`, `#c77dff`, `#d4af6a`, `#f4eef8`) và tôn trọng tuyệt đối giới hạn của Waybar/GTK3 (không `box-shadow` có blur, không định vị tự do, chỉ transition màu 120ms):

### Bảng Tóm Tắt 7 Ý Tưởng Đề Xuất

| # | Tên ý tưởng | Cảm hứng từ | Công cụ thực hiện | Độ khó |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Biến Ô Góc `#custom-corner` (Mạng nhện) thành Nút Bật/Tắt Niri Overview & Báo Trạng Thái Overview** | Noctalia Shell & DankMaterialShell | **Waybar thuần CSS + `niri msg` script** | **Thấp** |
| **2** | **Chuyển `dock-apps.py` sang đọc `niri msg event-stream`: Sắp xếp theo Thứ Tự Cột & Vẽ Chỉ Báo "Khuất Màn Hình"** | `LawnGnome/niri-taskbar` & `waybar-niri-windows_x_taskbar` | **Waybar + sửa script Python `dock-apps.py` hiện có** | **Vừa** |
| **3** | **Module "Dải Băng Cột Cuộn" (Column Ribbon / Minimap) trên Thanh Trên (`topbar`)** | `calico32/waybar-niri-windows` & Noctalia Preview | **Waybar thuần CSS + script đọc `niri msg --json`** | **Thấp – Vừa** |
| **4** | **Dời hoặc Đồng Bộ Chỉ Báo Workspace Theo Chiều Dọc & Ẩn Workspace Trống Cuối Cùng** | `niri/workspaces` (Waybar Wiki) & Noctalia Focus Hint | **Waybar thuần CSS (`niri/workspaces`)** | **Thấp** |
| **5** | **Đổi Nút Chuyển Chế Độ `#custom-layoutmode` (Trong Cụm Kafka) Thành Chỉ Báo Độ Rộng Cột / Chế Độ Tabbed Của Niri** | Đặc trưng bố cục của Niri + `Low-Spec-Niri-Dotfiles` | **Waybar thuần CSS + script `niri msg`** | **Thấp** |
| **6** | **Khớp Lớp Nền (Layer-Rule) Cho Khung Chữ L Khi Mở Niri Overview** | Noctalia Shell (`layer-rule` integration) | **Cấu hình `config.kdl` của Niri + Waybar hiện có** | **Thấp** |
| **7** | **Góc Bo Lõm Thật (Inverted Corner) Tại Chỗ Nối Chữ L & Hiệu Ứng Bung Hộp Công Cụ (Morphing Popup)** | Caelestia Shell ("Picture Frame") & `iNiR` | **Cần công cụ khác (Eww overlay nhỏ hoặc Quickshell)** | **Cao** |

---

### Mô Tả Chi Tiết Từng Ý Tưởng

#### Ý tưởng 1: Biến Ô Góc `#custom-corner` (Icon Mạng Nhện `󰯊`) Thành Nút Niri Overview Có Phản Hồi Trạng Thái
* **Cảm hứng:** Noctalia Shell và DankMaterialShell (tích hợp chặt với chế độ Overview gốc của Niri).
* **Mô tả:**
  * Trên Hyprland, bạn đang ghi chú trong `style.css` / `config.jsonc` rằng vì Hyprshell không gọi được tổng quan từ ngoài nên `#custom-corner` đành dùng để bật/tắt scratchpad (`magic`).
  * Sang Niri, Niri có sẵn lệnh gốc cực mượt: `niri msg action toggle-overview`. Bạn có thể gán thẳng lệnh này vào `on-click` của `#custom-corner` (và thêm `on-scroll-up` / `on-scroll-down` để chuyển workspace dọc `focus-workspace-up` / `focus-workspace-down`).
  * Hơn nữa, script của `#custom-corner` có thể lắng nghe `niri msg --json event-stream` (sự kiện `OverviewOpenedOrClosed`): khi Overview đang mở, trả về `"class": "active"` để đổi nền ô góc sang vàng đồng `#d4af6a` và icon mạng nhện sang màu tối `#141118` (giống hệt cách bạn đang làm cho `#kafka #custom-layoutmode.desktop`).
* **Công cụ:** **Waybar thuần CSS + script bash/python nhỏ** (tận dụng hoàn toàn cấu trúc `#custom-corner` hiện có).
* **Độ khó:** **Thấp**.

#### Ý tưởng 2: Nâng Cấp `dock-apps.py` Cho Niri — Sắp Xếp Theo Cột & Vẽ Dấu Báo Cửa Sổ Trôi Khuất Màn Hình
* **Cảm hứng:** `LawnGnome/niri-taskbar` và `Qweasd123tg/waybar-niri-windows_x_taskbar`.
* **Mô tả:**
  * Hiện tại trên `dockbar`, thẻ `#windows` của bạn dùng `dock-apps.py` vẽ 10 ảnh `image#w1..w10` (icon + badge `xN` + nền/viền vàng `#d4af6a` khi đang dùng) và một nút `#custom-hidden` ở đầu thẻ.
  * Khi sang Niri:
    1. Đổi nguồn sự kiện của `dock-apps.py` từ socket Hyprland sang `niri msg --json event-stream` (không cần polling, cập nhật tức thì khi mở/đóng/chuyển cửa sổ rồi bắn `pkill -RTMIN+13 waybar`).
    2. Sắp xếp thứ tự các app trên dock theo `(workspace_idx, column_idx)` để thứ tự từ trên xuống dưới trên dock phản ánh đúng thứ tự cột từ trái sang phải trên Niri.
    3. **Điểm đắt giá nhất (vẽ trực tiếp trong ảnh PNG 44x44 của `dock-apps.py` nên không vướng giới hạn CSS của Waybar):** Ngoài viền vàng `#d4af6a` cho app đang focus và badge `xN` màu burgundy `#b8326a`, nếu một cửa sổ của app đó đang bị cuộn khuất khỏi màn hình, `dock-apps.py` có thể vẽ thêm một chấm nhỏ hoặc vạch mảnh màu lilac `#c77dff` ở cạnh trái/phải của icon.
    4. Nút `#custom-hidden` ở đầu thẻ `#windows` có thể chuyển thành bộ đếm **"Số cửa sổ đang nằm ngoài vùng nhìn (off-screen) trong workspace hiện tại"** hoặc **"Số cửa sổ ở workspace scratchpad"**; bấm vào sẽ mở menu nhảy thẳng tới cột đó.
* **Công cụ:** **Waybar hiện có + cập nhật script Python `dock-apps.py`** (dùng Pillow/Cairo như hiện tại).
* **Độ khó:** **Vừa** (do bạn đã có sẵn toàn bộ khung render ảnh 44px và cơ chế `signal: 13`, chỉ cần đổi parser JSON từ `hyprctl clients` sang `niri msg --json windows`).

#### Ý tưởng 3: Module "Dải Băng Cột Cuộn" (Column Ribbon / Minimap) Trên Thanh Trên (`topbar`)
* **Cảm hứng:** `calico32/waybar-niri-windows` và plugin *Niri Workspace Preview* của Noctalia Shell.
* **Mô tả:**
  * Trong Niri, các cửa sổ nằm trên một dải băng ngang. Bạn có thể thêm một module nhỏ gọn ngay cạnh `niri/workspaces` (hoặc tích hợp vào cụm `group/kafka`) hiển thị sơ đồ các cột trong workspace hiện tại bằng ký tự Nerd Font / Unicode kèm màu Pango markup.
  * Ví dụ: Workspace hiện tại có 4 cột, cột 2 đang focus và cột 3 có 2 cửa sổ xếp chồng (stack), script in ra:
    `<span color='#7d6f90'>▭</span> <span color='#d4af6a'><b>▬</b></span> <span color='#c77dff'>▤</span> <span color='#7d6f90'>▭</span>`
  * Bấm chuột trái vào module mở Overview (`niri msg action toggle-overview`); lăn chuột trên module sẽ cuộn dải cột sang trái/phải (`niri msg action focus-column-left` / `focus-column-right`).
  * Vì dùng Pango markup bên trong một viên thuốc nền `#1f1629` có `min-width` cố định hoặc đặt cạnh `network#speed` (cuối cụm trái), thanh bar sẽ **không bị giật bố cục** khi đổi cột, hoàn toàn tuân thủ nguyên tắc hiệu năng trong `style.css` của bạn.
* **Công cụ:** **Waybar thuần CSS + 1 script đọc `niri msg --json event-stream`**.
* **Độ khó:** **Thấp – Vừa**.

#### Ý tưởng 4: Tinh Chỉnh `niri/workspaces` Theo Phong Cách "Focus Hint" & Ẩn Workspace Trống Cuối
* **Cảm hứng:** Chế độ *Focus Hint* của Noctalia Shell và module native `niri/workspaces` của Waybar.
* **Mô tả:**
  * Niri tự động tạo và giữ một workspace trống ở cuối mỗi màn hình. Khi chuyển từ `hyprland/workspaces` sang `niri/workspaces` trong `config.jsonc`:
    * Bạn có thể cấu hình `"format-icons": { "empty": "" }` hoặc dùng CSS `button.empty` làm mờ (`color: #7d6f90; background: transparent;`) để workspace trống dự phòng không gây rối mắt, chỉ sáng lên bằng gradient burgundy–lilac (`linear-gradient(135deg, #b8326a 0%, #9b4dca 100%)` + viền vàng `#d4af6a`) khi bạn thực sự cuộn xuống đó (`button.focused`).
    * Tận dụng trạng thái phân biệt giữa `button.focused` (workspace trên màn hình đang dùng -> nền gradient + viền vàng `#d4af6a`) và `button.active` (workspace đang hiển thị trên màn hình phụ -> nền `#3a1530` + viền `#b8326a`).
    * Giữ nguyên số La Mã (`I, II, III, IV, V...`) hoặc đặt tên workspace trong `config.kdl` của Niri theo chủ đề Kafka/Stellaron Hunters để hiển thị qua `{value}`.
* **Công cụ:** **Waybar thuần CSS (`niri/workspaces`)**.
* **Độ khó:** **Thấp**.

#### Ý tưởng 5: Biến Nút `#custom-layoutmode` (Trong Cụm `#kafka`) Thành Nút Chuyển Chế Độ Cột / Tabbed Của Niri
* **Cảm hứng:** Cơ chế quản lý cột (Column Preset Widths & Tabbed Column Display) đặc trưng của Niri và `Low-Spec-Niri-Dotfiles`.
* **Mô tả:**
  * Hiện tại trên Hyprland, cụm `group/kafka` ở góc trái trên gồm `#custom-launcher` (`󰣇 Kafka`) và `#custom-layoutmode` (chuyển chế độ cuộn ↔ Desktop).
  * Khi sang Niri (vốn đã là trình quản lý cửa sổ cuộn mặc định), nút `#custom-layoutmode` (nằm sát bên phải chữ Kafka, ngăn bằng vạch `rgba(255, 255, 255, 0.28)`) có thể đảm nhận chức năng cực kỳ hữu ích trên Niri:
    * **Bấm chuột trái:** Đổi chế độ hiển thị của cột hiện tại giữa **Xếp dọc bình thường (Normal)** và **Gộp thành thẻ (Tabbed column)** (`niri msg action toggle-column-tabbed-display`), hoặc xoay vòng độ rộng cột (`switch-preset-column-width`: 1/3 -> 1/2 -> 2/3 -> Toàn màn hình `maximize-column`).
    * **Bấm chuột phải:** Bật/tắt chế độ Cửa sổ nổi (Floating) của Niri (`niri msg action toggle-window-floating`).
    * Khi cột đang ở chế độ `tabbed` hoặc `maximized`, trả về `"class": "desktop"` để nút đổi sang nền vàng `#d4af6a` chữ tối `#16101e` như CSS sẵn có.
* **Công cụ:** **Waybar thuần CSS + script `niri msg` nhỏ**.
* **Độ khó:** **Thấp**.

#### Ý tưởng 6: Đồng Bộ Khung Chữ L Waybar Với Chế Độ Overview Và Hệ Thống Của Niri (`layer-rule` & `niri/language`)
* **Cảm hứng:** Noctalia Shell (tích hợp `layer-rule` với Overview) và Waybar Niri Wiki.
* **Mô tả:**
  * Trong Niri, khi bạn mở Overview (zoom-out), các thanh layer-shell ở `layer: "top"` mặc định sẽ đứng yên đè lên trên màn hình Overview. Bạn có thể giữ nguyên cả `topbar` và `dockbar` ở `layer: "top"` để **khung chữ L màu rượu vang đóng vai trò như một khung viền bao quanh màn hình Overview**, giúp không gian zoom-out của Niri nhìn như nằm bên trong buồng lái/khung tranh Kafka.
  * Ngoài ra, đối với nút bộ gõ `#custom-ime` ở đầu `dockbar` (`group/status`), nếu bạn vẫn dùng `fcitx5` cho tiếng Việt (`Unikey`), hãy **giữ nguyên script `ime-status.sh` hiện tại** (vì `niri/language` chỉ đọc XKB layout chứ không đọc trạng thái sub-engine Unikey của Fcitx5). Đây là điểm thực tế quan trọng để tránh mất chữ `VI`/`EN` màu hồng `#ff7aa2` khi chuyển sang Niri.
* **Công cụ:** **Waybar hiện có + cấu hình `config.kdl` của Niri**.
* **Độ khó:** **Thấp**.

#### Ý tưởng 7: Góc Bo Lõm Thật (Inverted Inner Corner) Tại Điểm Giao Chữ L & Popup Trượt Liền Khối
* **Cảm hứng:** Caelestia Shell ("Picture Frame" border) và `iNiR` / `illogical-impulse`.
* **Mô tả:**
  * Hiện tại, chỗ nối chữ L giữa `topbar` (dưới `#custom-corner`) và đỉnh `dockbar` là góc vuông 90 độ ở mép trong (vì mỗi cửa sổ Waybar là một hình chữ nhật GTK3 độc lập, không thể vẽ phần bo cong lõm lấn ra ngoài cửa sổ của nó).
  * Nếu muốn góc trong của chữ L (ngay dưới đáy bên trái của `#custom-corner`, sát mép trái của `dockbar`) có một **đường cong lõm (inverted corner radius ~14px)** có viền hồng `#b8326a` và tô kín phần góc nhọn bằng màu rượu vang `rgba(34, 16, 29, 0.95)` giống Caelestia Shell:
    * **Cách 1 (Giữ nguyên Waybar, thêm 1 widget siêu nhẹ):** Dùng một cửa sổ `eww` (hoặc script Python GTK3 Layer-Shell 16x16px không nhận click `input-region` rỗng) đặt cố định ngay tại góc trong của chữ L để vẽ đúng hình tam giác cong lõm đó.
    * **Cách 2 (Chuyển toàn bộ sang Quickshell):** Nếu về lâu dài bạn muốn cả `topbar`, `dockbar`, `clock-popup.py` và `tools-popup.py` nằm chung một bề mặt vẽ và có hiệu ứng nở khung (morphing) khi rê chuột vào nút công cụ, bạn có thể dựng lại khung chữ L trên **Quickshell** (tham khảo mã nguồn của `caelestia-dots/shell` hoặc `snowarch/inir`).
* **Công cụ:** **Cần công cụ ngoài Waybar** (1 cửa sổ Layer-Shell 16x16px bằng Python/GTK hoặc Eww nếu chỉ vẽ góc lõm; hoặc **Quickshell** nếu muốn hiệu ứng morphing toàn khung).
* **Độ khó:** **Vừa** (nếu dùng script Python GTK Layer-Shell vẽ miếng ghép góc lõm 16x16px tương tự các script `clock-popup.py` / `tools-popup.py` bạn đã có) / **Cao** (nếu viết lại toàn bộ bằng Quickshell).

---

## 4. Lộ Trình Chuyển Đổi Khuyến Nghị Cho Bộ "Kafka" Sang Niri

Để giữ trọn vẹn tâm huyết thiết kế khung chữ L và các script hiện tại mà không phải viết lại từ đầu sang Quickshell:
1. **Bước 1 (Giữ 95% cấu hình Waybar hiện tại):** Đổi `hyprland/workspaces` thành `niri/workspaces` (Ý tưởng 4), giữ nguyên `custom/ime` cho Fcitx5 (Ý tưởng 6).
2. **Bước 2 (Tận dụng sức mạnh Niri ngay trên Khung Chữ L):** Gán `#custom-corner` (icon mạng nhện) cho `niri msg action toggle-overview` (Ý tưởng 1) và đổi `#custom-layoutmode` thành nút chuyển chế độ cột Tabbed / Maximize của Niri (Ý tưởng 5).
3. **Bước 3 (Nâng cấp trải nghiệm cuộn cột):** Sửa phần đọc IPC trong `dock-apps.py` sang `niri msg --json event-stream` kèm chấm báo cửa sổ khuất màn hình (Ý tưởng 2), và tùy chọn thêm viên thuốc Minimap cột cuộn lên `topbar` (Ý tưởng 3).
