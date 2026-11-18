# Ghi chú chuyển đổi

## Không thể ánh xạ

- `hyprshell run` bị loại bỏ: đây là thành phần riêng của Hyprland; niri có Overview tích hợp và bộ chuyển cửa sổ Alt+Tab (`recent-windows`).
- Các hook sự kiện `window.open`, `window.close`, `window.active`, `window.class` và `window.move_to_workspace` cho `dock-density.sh`/`dock-apps.py` không có dạng khai báo trong config niri. Đã để TODO trong `config.kdl`; cần một tiến trình riêng đọc `niri msg --json event-stream`.
- `pin-toggle`/pin cửa sổ sang mọi workspace không có tương đương niri.
- `hide-windows.py` dùng special workspace ẩn, nhưng niri không có special workspace kiểu Hyprland.
- Scratchpad `special:magic` không có tương đương niri.
- `togglesplit` không có thao tác tương đương trực tiếp; `Mod+J` được dùng cho focus xuống như yêu cầu, còn tabbed display là cách thay thế gần nhất.
- `pseudotile` không có tương đương trực tiếp; `Mod+P` dùng `center-column` theo yêu cầu.
- Hyprland `borderangle` (gradient xoay liên tục) không có animation tương đương trong niri.
- Blur của Hyprland có `size`/`vibrancy`/`ignore_opacity`/`new_optimizations`/`xray`; niri 26.04 chỉ tài liệu hóa các hiệu ứng `background-effect` và block toàn cục `blur` với `passes`, `offset`, `noise`, `saturation`. Vì vậy chỉ bật blur cho kitty, walker/rofi và đặt `passes 3`; không bịa thuộc tính radius 7 hay các tùy chọn còn lại.
- Hyprland `resize_on_border`, `allow_tearing`, `dwindle`, `preserve_split`, `force_default_wallpaper` và `disable_hyprland_logo` không có ánh xạ cần thiết trong yêu cầu niri.
- `KAFKA_NESTED_TEST` và logic kiểm tra `/usr/bin/qt6ct` không được chuyển: niri KDL không có điều kiện Lua; `QT_QPA_PLATFORMTHEME` được đặt bắt buộc theo mapping spec.

## Phán đoán và lựa chọn

- Không tạo `output` block vì mapping spec yêu cầu output tự động; niri tự chọn mode, scale và vị trí.
- `XCURSOR_SIZE` được đặt trong `environment` và `cursor { xcursor-size 24; }` được dùng vì mapping yêu cầu kích thước con trỏ; biến `HYPRCURSOR_SIZE` bị bỏ vì đây là biến riêng Hyprland.
- `focus-follows-mouse max-scroll-amount="0%"`, `dwt`, gradient `in="oklch longer hue"`, `background-effect`, `shadow off`, các action phím tắt và `default-floating-position` đều dùng đúng cú pháp được tài liệu niri 26.04 cung cấp.
- Niri mặc định căn giữa cửa sổ nổi mới; vì vậy không thêm thuộc tính `center` không tồn tại. Các cửa sổ nổi chỉ đặt kích thước bằng `default-column-width` và `default-window-height`.
- Vị trí `kafka-cava` dùng `x=12 y=12 relative-to="bottom-right"`, tương đương lề 12 px ở góc dưới phải theo hệ tọa độ của niri.
- `Mod+Shift+S` dùng UI `screenshot` tích hợp theo mapping spec; `Print`, `Shift+Print` và `Alt+Print` lần lượt dùng `screenshot`, `screenshot-screen`, `screenshot-window`.
- Niri tài liệu hóa `spawn` cho đường dẫn/chương trình và `spawn-sh` cho shell string; các pipeline, `&&`, `||` và lệnh nhiều bước dùng `spawn-sh-at-startup`/`spawn-sh`.
- Include là bắt buộc và nằm cuối file. Theo `Configuration:-Include.md`, include tương đối được giải theo vị trí file config và các thiết lập được merge theo vị trí; `keybinds-user.kdl` tồn tại nên không cần `optional=true`.
- `Mod+Tab` chỉ mở Overview theo yêu cầu; không thêm cấu hình `recent-windows`, nhờ đó Alt+Tab mặc định của niri vẫn được giữ nguyên.
