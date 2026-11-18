# Kiểm toán tập lệnh: từ Hyprland sang niri

Tài liệu này chỉ phân tích mã nguồn trong ``. Các tên action bên dưới đều lấy từ `Action` trong `niri-ipc-lib.rs`; các tên trường JSON lấy từ `Window`, `Workspace`, `Output`, `KeyboardLayouts` trong cùng tệp. Không đặt ra action nào khác.

## 1. Bảng ánh xạ từng lần gọi `hyprctl`

| file:line | Lệnh hyprctl | Mục đích | Tương đương trong niri |
|---|---|---|---|
| `powermenu.sh:46` | `hyprctl dispatch "hl.dsp.exit()"` | Đăng xuất khỏi phiên sau khi đã xác nhận | `niri msg action quit` (đã có bước xác nhận riêng trong script; có thể dùng `niri msg action quit --skip-confirmation`) |
| `actionsmenu.sh:15` | `hyprctl activewindow -j` (đọc `address`) | Lưu cửa sổ đang focus trước khi rofi chiếm focus | `niri msg --json focused-window` → lấy `id` (niri không có `address`) |
| `actionsmenu.sh:44` | `hyprctl dispatch "hl.dsp.window.float({ action = \"toggle\", window = \"address:$addr\" })"` | Bật/tắt chế độ nổi của cửa sổ đã lưu | `niri msg action toggle-window-floating --id <id>` |
| `actionsmenu.sh:46` | `hyprctl dispatch 'hl.dsp.window.float({ action = "toggle" })'` | Bật/tắt chế độ nổi của cửa sổ đang focus | `niri msg action toggle-window-floating` (mặc định tác động lên cửa sổ focus) |
| `hide-windows.py:31` → `:48` | `hyprctl clients -j` | Liệt kê client cho menu ẩn/hiện | `niri msg --json windows` → dùng `app_id` (thay `class`), `id` (thay `address`), `title`, `workspace_id`, `is_focused`, `is_floating`, `is_urgent`; niri có thêm `pid`, dùng `focus_timestamp` thay `focusHistoryID`, không có `mapped` |
| `hide-windows.py:31` → `:119` | `hyprctl activeworkspace -j` | Lấy workspace đang hoạt động để đưa cửa sổ về khi hiện lại | `niri msg --json workspaces` → chọn phần tử có `is_focused: true`, lấy `id` / `idx` / `name` (niri không có yêu cầu `activeworkspace` riêng) |
| `hide-windows.py:31` → `:177` | `hyprctl activewindow -j` | Lấy cửa sổ focus cho lệnh "ẩn cửa sổ hiện tại" | `niri msg --json focused-window` → `id`, `app_id`, `workspace_id`, `is_focused` |
| `hide-windows.py:106` | `hyprctl dispatch hl.dsp.window.move({ workspace = "special:hidden", window = "address:…", follow = false })` | Đẩy cửa sổ vào workspace đặc biệt để ẩn | `niri msg action move-window-to-workspace --window-id <id> hidden --focus false`; niri không có khái niệm workspace `special:` nên phải dùng workspace thường |
| `hide-windows.py:205` | `hyprctl --batch "dispatch hl.dsp.window.move({…}); …"` | Hiện lại mọi cửa sổ ẩn trong một lô lệnh | `niri msg action move-window-to-workspace --window-id <id> <tên-workspace> --focus false` (lặp cho từng `id`); niri không có `--batch`, nhưng có thể gửi nhiều yêu cầu qua `$NIRI_SOCKET` hoặc `niri msg raw-request` |
| `tile-menu.sh:14` | `hyprctl activewindow -j` | Lưu cửa sổ chính trước khi mở rofi | `niri msg --json focused-window` → `id` |
| `tile-menu.sh:19` | `hyprctl repl 'return kafka_tile_current()'` | Hỏi chế độ chia khu Lua đang dùng để đánh dấu trong menu | không có tương đương (niri không có cấu hình Lua cũng như cổng `repl`) |
| `tile-menu.sh:53` | `hyprctl eval "kafka_tile('…', '$addr')"` | Áp tỉ lệ/lưới chia khu tùy biến qua hàm Lua | không có tương đương (không có `eval` Lua; niri dùng mô hình cột với `niri msg action set-column-width …`, `switch-preset-column-width`, `toggle-column-tabbed-display`, nhưng không có grid/dwindle theo tỉ lệ) |
| `toggle-app.sh:5` | `hyprctl clients -j` (lọc `"class"`) | Kiểm tra app đã mở hay chưa | `niri msg --json windows` → so khớp `app_id` (niri không có `class`) |
| `toggle-app.sh:6` | `hyprctl dispatch "hl.dsp.window.close({ window = \"class:^($class)$\" })"` | Đóng app theo class | `niri msg action close-window --id <id>` (phải lấy `id` từ `niri msg --json windows` lọc theo `app_id`; niri không có selector `class:`) |
| `dock-apps.py:109` → `:114` | `hyprctl clients -j` | Gom nhóm icon dock theo class, giữ thứ tự và địa chỉ | `niri msg --json windows` → gom theo `app_id`, định danh bằng `id`, xếp theo `focus_timestamp`; không có `address`, `class`, `mapped`, `focusHistoryID` |
| `dock-apps.py:109` → `:114` | `hyprctl activewindow -j` | Tô nền nhóm chứa cửa sổ đang focus | `niri msg --json focused-window` → `id`, `app_id`, `is_focused` |
| `dock-apps.py:332` | `hyprctl dispatch hl.dsp.{window.close\|focus}({ window = "address:…" })` | Nhấn icon dock: chuyển focus hoặc đóng cửa sổ | `niri msg action focus-window --id <id>` / `niri msg action close-window --id <id>` |
| `clock-popup.py:206` | `hyprctl cursorpos -j` | Lấy tọa độ x của con trỏ để đặt popup dưới đồng hồ | không có tương đương (`Request` trong niri-ipc-lib.rs không có `cursorpos`; chỉ có `PickColor`, `PickWindow`) |
| `dock-density.sh:22` | `hyprctl monitors -j` | Lấy chiều cao màn hình theo pixel logic để tính mật độ dock | `niri msg --json focused-output` (hoặc `niri msg --json outputs`) → `logical.height`, `logical.scale`; niri đã cho kích thước logic nên không cần chia cho `scale` |
| `dock-density.sh:33` | `hyprctl clients -j` | Đếm số app khác nhau để co giãn ô dock | `niri msg --json windows` → đếm các `app_id` khác nhau, loại `kafka-cava` và cửa sổ thuộc workspace ẩn (`workspace_id`) |
| `capture.sh:176` | `hyprctl monitors -j` (chọn mục `focused`) | Lấy tên monitor đang focus cho `wf-recorder -o` | `niri msg --json focused-output` → `name` (các output cũng có `logical` trong `niri msg --json outputs`) |
| `keybinds-editor.py:227` | `hyprctl binds -j` | Liệt kê phím tắt đang hoạt động | không có tương đương (niri IPC không có yêu cầu `Binds`; phím tắt chỉ nằm trong file cấu hình) |
| `keybinds-editor.py:426` | `hyprctl reload` | Nạp lại cấu hình sau khi ghi file | `niri msg action load-config-file` (`path = None` → nạp lại config hiện tại) |
| `pin-toggle.sh:9` | `hyprctl clients -j` | Tìm các client có `pinned: true` để bỏ treo tất cả | `niri msg --json windows`, nhưng niri không có trường `pinned` → không thể nhận diện cửa sổ đã "treo" |
| `pin-toggle.sh:14` | `hyprctl --batch 'dispatch hl.dsp.window.pin({ action = "disable", window = "address:…" }); dispatch hl.dsp.window.float({ action = "disable", window = "address:…" })'` | Bỏ treo rồi đưa về xếp cho từng cửa sổ | `niri msg action move-window-to-tiling --id <id>` cho phần float; không có tương đương cho `pin` (niri không có tính năng pin) |
| `pin-toggle.sh:23` → `:26` | `hyprctl activewindow -j` | Lấy cửa sổ focus để quyết định treo hay bỏ treo | `niri msg --json focused-window` → `id`, `is_focused`, `is_floating` |
| `pin-toggle.sh:23` → `:29` | `hyprctl monitors -j` | Lấy kích thước/vị trí monitor để tính khung PiP 36% × 42% | `niri msg --json focused-output` → `logical.x`, `logical.y`, `logical.width`, `logical.height`, `scale`; niri không có trường `focused` trong `outputs` |
| `pin-toggle.sh:41` | `hyprctl --batch 'dispatch hl.dsp.window.pin({ action = "disable" }); dispatch hl.dsp.window.float({ action = "disable" })'` | Bỏ treo cửa sổ đang focus | `niri msg action move-window-to-tiling`; không có tương đương cho `pin` |
| `pin-toggle.sh:42` | `hyprctl --batch "dispatch hl.dsp.window.float({ action = \"enable\" }); dispatch hl.dsp.window.resize({ x = $w, y = $h, relative = false }); dispatch hl.dsp.window.move({ x = $x, y = $y, relative = false }); dispatch hl.dsp.window.pin({ action = \"enable\" })"` | Treo cửa sổ: cho nổi, đổi kích thước, dời góc phải-dưới, rồi pin | `niri msg action move-window-to-floating --id <id>` + `niri msg action set-window-width --id <id> <w>` + `niri msg action set-window-height --id <id> <h>` + `niri msg action move-floating-window --id <id> --x <x> --y <y>`; không có tương đương cho `pin` |
| `closemenu.sh:10` | `hyprctl clients -j` | Liệt kê cửa sổ cho menu đóng | `niri msg --json windows` → `id`, `app_id`, `title`, `workspace_id` (không có `address`) |
| `closemenu.sh:47` | `hyprctl dispatch "hl.dsp.window.close({ window = \"address:$addr\" })"` | Đóng cửa sổ được chọn | `niri msg action close-window --id <id>` |

**Lưu ý chung về dữ liệu cửa sổ:** JSON của niri dùng `app_id` (không phải `class`), `id` (không phải `address`), có thêm `pid`, và **không có tọa độ `x`/`y` cho cửa sổ xếp (tiled)** — chỉ có các thông tin trong `layout` như `tile_pos_in_workspace_view` (`Option`), `tile_size`, `window_offset_in_tile`. Vì vậy mọi mã dùng `address`, tọa độ tuyệt đối hay `focusHistoryID` đều phải viết lại. `hyprctl layers` ở `dock-density.sh:19` chỉ nằm trong comment hướng dẫn đo kích thước, không phải lời gọi thực thi.

### Công cụ riêng của Hyprland (ngoài `hyprctl`)

| file:line | Công cụ | Tương đương trong niri |
|---|---|---|
| `capture.sh:125` | `hyprshot -m output -m active` (chụp output đang focus) | `niri msg action screenshot-screen --path <đường-dẫn-tuyệt-đối>` |
| `capture.sh:127` | `hyprshot -m window` / `-m region` | `niri msg action screenshot-window --id <id> --path <...>` / `niri msg action screenshot --path <...>` (giao diện chọn vùng) |
| `capture.sh:137` | `hyprshot -m region --raw` (ảnh ra stdout) | `niri msg action screenshot --path <...>` rồi đọc tệp; không có chế độ `--raw` tương đương |
| `powermenu.sh:44`, `actionsmenu.sh:50` | `hyprlock` | dùng tiếp được: hyprlock chạy trên giao thức chuẩn `ext-session-lock-v1` mà niri hỗ trợ (ghi chú của người review; opencode ghi nhầm là cần swaylock) |

`hyprpicker` không được dùng trong `hypr/scripts/`.

## 2. Kết luận từng tập lệnh

| Tập lệnh | Kết luận | Lý do (một dòng) |
|---|---|---|
| `powermenu.sh` | sửa nhỏ | Đổi `hl.dsp.exit()` thành `niri msg action quit` (hyprlock giữ nguyên); rofi và `systemctl` giữ nguyên. |
| `actionsmenu.sh` | sửa nhỏ | Thay `activewindow -j` bằng `niri msg --json focused-window` (`id` thay `address`), float bằng `toggle-window-floating`. |
| `hide-windows.py` | viết lại | Cơ chế ẩn dùng workspace `special:` không có trong niri; phải dùng workspace thường với `move-window-to-workspace --focus false` và đổi `class`/`address`/`focusHistoryID` sang `app_id`/`id`/`focus_timestamp`. |
| `tile-menu.sh` | viết lại | `repl`/`eval` gọi Lua chia khu của Hyprland không tồn tại trong niri; chỉ giữ được phần chọn rofi, phần áp dụng phải dùng action cột của niri và bỏ chế độ grid/dwindle. |
| `lunar_vn.py` | chạy được ngay | Thuần Python, không gọi `hyprctl` và cũng không dùng `hyprshot`, `hyprlock` hay `hyprpicker`. |
| `power-profile.sh` | chạy được ngay | Chỉ dùng `powerprofilesctl` và `notify-send`, không phụ thuộc compositor. |
| `wallpaper-cycle.sh` | chạy được ngay | Dùng `awww` (trình đặt hình nền Wayland, không phải công cụ Hyprland); chỉ cần chuyển thư mục `~/.config/hypr/wallpapers` nếu muốn. |
| `toggle-app.sh` | sửa nhỏ | Đổi `class` thành `app_id` và đóng bằng `niri msg action close-window --id <id>` sau khi tra cứu trong `niri msg --json windows`. |
| `closemenu.sh` | sửa nhỏ | Đọc `niri msg --json windows` (`id`, `app_id`, `title`) rồi đóng bằng `close-window --id <id>` thay vì selector `address:`. |
| `pin-toggle.sh` | bỏ | Tính năng cốt lõi là pin (cửa sổ luôn hiện trên mọi workspace) không có tương đương trong niri; giữ lại được nhiều nhất là cửa sổ nổi, không giữ được ngữ nghĩa pin. |
| `capture.sh` | viết lại | `hyprshot` là công cụ Hyprland-only; chuyển sang `screenshot-screen`/`screenshot-window`/`screenshot` của niri và lấy monitor qua `focused-output` (`wf-recorder`, `slurp`, `satty` vẫn dùng được). |
| `tools-popup.py` | sửa nhỏ | Không dùng `hyprctl` hay công cụ Hyprland-only, nhưng hiện được `hyprland.lua` tự chạy lúc khởi động nên phải chuyển sang autostart của niri và đo lại tọa độ vùng hotspot. |
| `ime-status.sh` | chạy được ngay | Chỉ hỏi `fcitx5-remote` qua D-Bus, độc lập compositor. |
| `dock-density.sh` | sửa nhỏ | Thay hai lệnh `hyprctl` bằng `focused-output`/`windows` và chuyển trigger từ hook `hl.on` sang `niri msg event-stream`. |
| `keybinds-editor.py` | bỏ | Đọc/ghi `hyprland.lua` + `keybinds.lua` và lấy danh sách qua `hyprctl binds -j` (niri không có); phải quản lý file cấu hình của niri bằng tay. |
| `dock-apps.py` | viết lại | Mọi khóa dữ liệu đều là của Hyprland (`class`, `address`, `focusHistoryID`, hook `hl.on`) → `app_id`, `id`, `focus_timestamp`, `event-stream`. |
| `tools-status.sh` | chạy được ngay | Chỉ gọi `capture.sh status` và `dunstctl`, không dùng `hyprctl` hay công cụ Hyprland-only (sau khi `capture.sh` được chuyển đổi). |
| `clock-popup.py` | sửa nhỏ | Chỉ có một lần gọi `hyprctl cursorpos -j` để canh popup; niri IPC không có `cursorpos` nên bỏ bước này, căn giữa, hoặc lấy con trỏ qua GDK. |

## 3. Waybar (`config.jsonc`)

| Module đặc thù Hyprland | Vị trí | Thay thế trong Waybar 0.16 |
|---|---|---|
| `hyprland/workspaces` | `modules-left` dòng 14; khai báo dòng 36–61 | `niri/workspaces` — đây là module `hyprland/*` duy nhất trong file; dùng các trường từ `niri-ipc-lib.rs` là `idx`, `name`, `is_active`, `is_focused`, `is_urgent`, `active_window_id`. |

Waybar 0.16 cũng có `niri/window` (có thể thay cho phần tiêu đề cửa sổ hiện tại mà config đang bỏ qua, xem comment dòng 63) và `niri/language` (thay cho `custom/ime` nếu chỉ cần tên bàn phím, lấy qua `niri msg --json keyboard-layouts` với `names` và `current_idx`); hiện hai module này không xuất hiện trong `config.jsonc`.

Ngoài module `hyprland/*`, cần đổi đường dẫn `~/.config/hypr/scripts/...` trong các mục `exec` và `on-click` sang thư mục script mới. Riêng cờ `--class kafka-...` của kitty vẫn hữu ích vì niri gán giá trị đó vào `app_id`, đúng với cách các script lọc cửa sổ sau khi sửa.
