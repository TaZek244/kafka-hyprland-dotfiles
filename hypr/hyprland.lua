-- ==============================================================================
--  HYPRLAND CONFIGURATION - KAFKA (HONKAI: STAR RAIL) EDITION  (Hyprland >= 0.57, Lua)
--  Chuyển từ hyprland.conf (0.56). hyprland.conf giữ lại làm bản tham khảo, 0.57 KHÔNG đọc nó.
--  Theme Palette:
--    Obsidian Base   : #141118 | #1e1826
--    Kafka Burgundy  : #b8326a | #8f2456
--    Lightning Lilac : #c77dff | #9b4dca
--    Coat Brass Gold : #d4af6a
--    Ivory Text      : #f4eef8
--  Kiểm tra: Hyprland --verify-config   (KHÔNG dùng -c hypr/hyprland.conf nữa)
--  hyprctl dispatch giờ nhận biểu thức Lua: hyprctl dispatch 'hl.dsp.window.close()'
-- ==============================================================================

-- ----------------
-- 1. MONITORS
-- ----------------
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })

-- ----------------
-- 2. PROGRAMS & PATHS
-- ----------------
local terminal    = "kitty"
local fileManager = "thunar"
local menu        = "walker"   -- trình mở app (walker + elephant, theme walker/themes/kafka); bấm lần nữa = đóng
local wallScript  = "~/.config/hypr/scripts/wallpaper-cycle.sh"
-- Hình nền cố định: mặc định kafka_landscape_3.jpg; Kafka Studio (scripts/studio.py, tab Hình nền → "Đặt làm mặc định")
-- ghi đường dẫn ảnh khác vào ~/.local/state/kafka/wallpaper → đăng nhập lần sau dùng ảnh đó (file mất thì về mặc định)
local wallpaper   = "~/.config/hypr/wallpapers/kafka_landscape_3.jpg"
do
    local state = (os.getenv("XDG_STATE_HOME") or (os.getenv("HOME") .. "/.local/state")) .. "/kafka/wallpaper"
    local f = io.open(state, "r")
    if f then
        local path = (f:read("*l") or ""):gsub("^%s+", ""):gsub("%s+$", "")
        f:close()
        local g = path ~= "" and io.open(path, "r")
        if g then g:close(); wallpaper = "'" .. path:gsub("'", "") .. "'" end
    end
end
local powerMenu   = "~/.config/hypr/scripts/powermenu.sh"
local clipMenu    = 'cliphist list | rofi -dmenu -p "Clipboard" -theme ~/.config/rofi/kafka.rasi | cliphist decode | wl-copy'
local scripts     = "~/.config/hypr/scripts/"

-- ----------------
-- 3. AUTOSTART (tương đương exec-once: chỉ chạy khi Hyprland khởi động, không chạy lại khi reload)
-- ----------------
hl.on("hyprland.start", function()
    -- Phiên Hyprland lồng để thử cấu hình: đặt KAFKA_NESTED_TEST=1 để không chạy lại các daemon.
    if os.getenv("KAFKA_NESTED_TEST") then return end

    -- Bộ gõ chạy ĐẦU TIÊN, trước Waybar: ô VI/EN gọi fcitx5-remote, nếu fcitx5 chưa có thì D-Bus tự bật
    -- một bản thiếu môi trường Wayland → gõ không dấu. ime-guard xuất môi trường cho D-Bus, bật fcitx5
    -- và giám sát (chết/mất Wayland thì tự bật lại). Xem hypr/scripts/ime-guard.sh.
    hl.exec_cmd(scripts .. "ime-guard.sh daemon")
    -- theme.css + symlink bố cục thanh trên (topbar-current.jsonc) phải có trước, thiếu thì Waybar mất hết CSS.
    -- hud.py (thẻ nhân vật/chỉ số của theme pixel) vẽ 1 lần trước Waybar rồi chạy nền; ở bản phẳng nó tự thoát.
    -- khay hệ thống tự viết (ngăn BG trên dock, tối đa 3 ô): nhận tên org.kde.StatusNotifierWatcher TRƯỚC khi app chạy ngầm khởi động
    hl.exec_cmd(scripts .. "sni-tray.py daemon")
    hl.exec_cmd(scripts .. "ui-theme.sh ensure; " .. scripts .. "hud.py once; waybar")
    hl.exec_cmd(scripts .. "hud.py daemon")
    hl.exec_cmd("dunst")
    hl.exec_cmd("/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1")
    hl.exec_cmd("nm-applet --indicator")
    -- awww-daemon chạy mãi không thoát, nên không nối bằng && (vế sau sẽ không bao giờ chạy)
    hl.exec_cmd("awww-daemon")
    hl.exec_cmd("sleep 1 && " .. wallScript .. " set " .. wallpaper)
    -- Muốn tự đổi hình nền theo vòng thì thay dòng trên bằng:
    --   hl.exec_cmd("sleep 1 && " .. wallScript .. " init")
    --   hl.exec_cmd("sleep 2 && " .. wallScript .. " auto 600")
    -- Phase 2: Idle daemon (giảm sáng -> khóa -> tắt màn hình -> ngủ khi dùng pin)
    hl.exec_cmd("hypridle")
    -- Tổng quan kiểu GNOME: nhấn-thả Super; Alt+Tab chuyển cửa sổ (hyprshell/config.toml)
    hl.exec_cmd("hyprshell run")
    -- Walker chạy nền để mở tức thì; elephant (nguồn dữ liệu app) là systemd user service
    hl.exec_cmd("systemctl --user start elephant.service; walker --gapplication-service")
    -- Popup ngang cho nút công cụ trên đầu dock (rê chuột vào là hiện)
    hl.exec_cmd(scripts .. "tools-popup.py")
    hl.exec_cmd(scripts .. "ws-popup.py")                  -- rê chuột lên ô workspace (Waybar chỉ hiện khu đang dùng) = popup chọn khu
    -- Viền xoay màu tự tắt khi dùng pin / power-saver, bật lại khi cắm sạc (power-watch.sh set on|off|auto để ghi đè)
    hl.exec_cmd(scripts .. "power-watch.sh daemon")
    hl.exec_cmd(scripts .. "media-pill.py")      -- ô "Đang phát" (rê chuột = sóng nhạc, bấm = popup lời bài hát)
    hl.exec_cmd("[ \"$(" .. scripts .. "ui-theme.sh status)\" = flat ] && " .. scripts .. "corner-fillet.py")   -- góc lõm (chỉ bản phẳng) chỗ nối thanh trên + dock (overlay, tự ẩn khi toàn màn hình)
    -- Phase 3: Lưu lịch sử clipboard (văn bản + hình ảnh)
    hl.exec_cmd("wl-paste --type text --watch cliphist store")
    hl.exec_cmd("wl-paste --type image --watch cliphist store")
end)

-- Dock: co giãn thẻ app theo số cửa sổ để dock không dài quá màn hình (dock-density.sh).
-- Trễ 0.4s để danh sách cửa sổ kịp cập nhật sau khi mở/đóng.
if not os.getenv("KAFKA_NESTED_TEST") then
    local function dockDensity() hl.exec_cmd("sleep 0.4; " .. scripts .. "dock-density.sh") end
    hl.on("window.open", dockDensity)
    hl.on("window.close", dockDensity)
    hl.on("window.move_to_workspace", dockDensity)   -- ẩn/hiện cửa sổ đổi số app trên dock
    -- Dock: vẽ lại các app gộp theo class (icon + "xN" + ô đang dùng), xem scripts/dock-apps.py
    local function dockApps() hl.exec_cmd(scripts .. "dock-apps.py render") end
    local function dockAppsLate() hl.exec_cmd("sleep 0.3; " .. scripts .. "dock-apps.py render") end
    for _, ev in ipairs({ "window.active", "window.class", "window.move_to_workspace" }) do
        hl.on(ev, dockApps)
    end
    hl.on("window.open", dockAppsLate)    -- trễ: danh sách cửa sổ chưa kịp cập nhật
    hl.on("window.close", dockAppsLate)
    hl.on("hyprland.start", dockApps)
    hl.on("hyprland.start", dockDensity)
    -- Thanh trên: bản đồ cột (custom/columns, signal 15, scripts/column-map.sh)
    local function columnMap() hl.exec_cmd("sleep 0.25; pkill -RTMIN+15 waybar") end   -- trễ: chờ animation cuộn đặt xong vị trí
    for _, ev in ipairs({ "window.active", "window.open", "window.close", "window.move_to_workspace", "workspace.active" }) do
        hl.on(ev, columnMap)
    end
end

-- ----------------
-- 4. ENVIRONMENT VARIABLES
-- ----------------
-- Con trỏ Kafka (thiết kế riêng, dựng bằng cursors/build-kafka-cursor.py: hyprcursor + Xcursor)
-- Kafka-BEN = bộ con trỏ người dùng tự tải (example/Kafka.zip, chuyển bằng cursors/ani2theme.py, chỉ có trên máy này);
-- thiếu thì đổi lại "Kafka-Cursor" (theme tự vẽ, install.sh luôn dựng)
hl.env("XCURSOR_THEME", "Kafka-BEN")
hl.env("HYPRCURSOR_THEME", "Kafka-BEN")
hl.env("XCURSOR_SIZE", "32")
hl.env("HYPRCURSOR_SIZE", "32")
hl.env("QT_QPA_PLATFORM", "wayland;xcb")
-- Chỉ đặt khi đã cài qt6ct (install.sh có cài); thiếu gói thì app Qt báo lỗi plugin theme
do
    local f = io.open("/usr/bin/qt6ct", "r")
    if f then f:close(); hl.env("QT_QPA_PLATFORMTHEME", "qt6ct") end
end
hl.env("GDK_BACKEND", "wayland,x11,*")
hl.env("SDL_VIDEODRIVER", "wayland")
hl.env("CLUTTER_BACKEND", "wayland")
-- Input Method (Fcitx5 Vietnamese Unikey support) — giữ nguyên để gõ tiếng Việt ổn định
hl.env("GTK_IM_MODULE", "fcitx")
hl.env("QT_IM_MODULE", "fcitx")
hl.env("XMODIFIERS", "@im=fcitx")

-- ----------------
-- 5. LOOK AND FEEL (KAFKA THEME)
-- ----------------
hl.config({
    general = {
        gaps_in     = 6,
        gaps_out    = 12,
        border_size = 2,
        col = {
            -- Kafka Burgundy -> Electric Spider Lilac -> Brass Gold gradient
            active_border   = { colors = { "rgba(b8326aff)", "rgba(c77dffff)", "rgba(d4af6aff)" }, angle = 45 },
            inactive_border = "rgba(382b47aa)",
        },
        resize_on_border = true,
        allow_tearing    = false,
        -- Layout cuộn ngang kiểu niri: mỗi cửa sổ là một cột, mở thêm không làm co cửa sổ cũ.
        -- Muốn quay lại chia đôi kiểu cũ: đổi thành "dwindle" (phím Super + J/P chỉ chạy với dwindle).
        layout           = "scrolling",
    },

    scrolling = {
        column_width             = 0.5,                      -- cột mới rộng 1/2 màn hình
        explicit_column_widths   = "0.333, 0.5, 0.667, 1.0", -- các mức Super + G / Super + -/= xoay vòng
        fullscreen_on_one_column = false,                    -- chỉ 1 cửa sổ thì vẫn giữ 1/2, không tự giãn hết
        focus_fit_method         = 1,                        -- chuyển tiêu điểm thì cuộn vừa đủ cho cột hiện ra
        follow_focus             = 1,                        -- dải cột tự cuộn theo cửa sổ được chọn (0 = không cuộn theo)
    },

    decoration = {
        rounding         = 14,
        active_opacity   = 0.96,
        inactive_opacity = 0.90,
        shadow = {
            enabled      = true,
            range        = 20,
            render_power = 3,
            color        = "rgba(140d1cee)",
        },
        blur = {
            enabled           = true,
            size              = 7,
            passes            = 3,
            new_optimizations = true,
            ignore_opacity    = true,
            xray              = false,
            vibrancy          = 0.22,
        },
    },

    animations = { enabled = true },

    dwindle = { preserve_split = true },

    misc = {
        force_default_wallpaper = 0,
        disable_hyprland_logo   = true,
        -- Cửa sổ nổi phải nằm TRỌN trong vùng nội dung (trừ chỗ Waybar), kể cả sau khi kéo.
        -- 0 = tắt, 1 = chỉ cần lộ một phần, 2 = trọn vẹn. Cửa sổ quá to được kafka_fit_float() thu lại trước.
        float_force_onscreen    = 2,
    },

    -- ----------------
    -- 6. INPUT & TOUCHPAD
    -- ----------------
    input = {
        kb_layout    = "us",
        follow_mouse = 1,
        sensitivity  = 0,
        touchpad = {
            natural_scroll       = true,
            tap_to_click         = true,
            disable_while_typing = true,
        },
    },
})

-- Viền/góc/bóng cửa sổ theo giao diện (hypr/scripts/ui-theme.sh, Super + Alt + U):
--   flat  = như khối decoration trên (bo 14, viền 2 gradient đỏ-tím-vàng, bóng mờ lan 20)
--   pixel = "pixel mềm": bo 6, viền 3 gradient hồng → tím, bóng CỨNG lệch xuống-phải (shadow.sharp)
-- ui-theme.sh gọi `hyprctl eval 'kafka_ui_theme("pixel")'`; lúc nạp file đọc trạng thái để reload/đăng nhập vẫn giữ.
-- Đổi giá trị bản flat ở khối hl.config trên thì sửa cả ở đây.
function kafka_ui_theme(mode)
    if mode == "pixel" then
        hl.config({
            general = {
                border_size = 3,
                col = {
                    active_border   = { colors = { "rgba(f08cbbff)", "rgba(c94785ff)", "rgba(a37de0ff)" }, angle = 45 },
                    inactive_border = "rgba(3a2f46ff)",
                },
            },
            decoration = {
                rounding       = 6,
                rounding_power = 2.0,
                shadow = { enabled = true, sharp = true, range = 1, offset = "6 6", color = "rgba(0b0710cc)" },
            },
        })
    else
        hl.config({
            general = {
                border_size = 2,
                col = {
                    active_border   = { colors = { "rgba(b8326aff)", "rgba(c77dffff)", "rgba(d4af6aff)" }, angle = 45 },
                    inactive_border = "rgba(382b47aa)",
                },
            },
            decoration = {
                rounding       = 14,
                rounding_power = 2.0,
                shadow = { enabled = true, sharp = false, range = 20, offset = "0 0", color = "rgba(140d1cee)" },
            },
        })
    end
    return mode
end
do
    local f = io.open((os.getenv("XDG_STATE_HOME") or (os.getenv("HOME") .. "/.local/state")) .. "/kafka/ui-theme", "r")
    local mode = f and f:read("*l") or "flat"
    if f then f:close() end
    if mode == "pixel" then kafka_ui_theme("pixel") end
end

-- Custom smooth "Spider Thread" bezier curves
hl.curve("kafkaSnap",   { type = "bezier", points = { {0.05, 0.9}, {0.1, 1.05} } })
hl.curve("kafkaSmooth", { type = "bezier", points = { {0.25, 1},   {0.5, 1}    } })
hl.curve("linear",      { type = "bezier", points = { {0, 0},      {1, 1}      } })

hl.animation({ leaf = "windows",     enabled = true, speed = 5,  bezier = "kafkaSnap",   style = "popin 80%" })
hl.animation({ leaf = "windowsOut",  enabled = true, speed = 5,  bezier = "kafkaSmooth", style = "popin 80%" })
hl.animation({ leaf = "border",      enabled = true, speed = 10, bezier = "kafkaSmooth" })
-- Viền xoay màu liên tục: đẹp nhưng bắt Hyprland vẽ lại mọi khung hình (~3-4% CPU lúc rảnh).
-- Muốn tiết kiệm pin thì đổi thành: hl.animation({ leaf = "borderangle", enabled = false })
hl.animation({ leaf = "borderangle", enabled = true, speed = 60, bezier = "linear",      style = "loop" })
hl.animation({ leaf = "fade",        enabled = true, speed = 5,  bezier = "kafkaSmooth" })
hl.animation({ leaf = "workspaces",  enabled = true, speed = 5,  bezier = "kafkaSnap",   style = "slidefade 20%" })

-- Kính mờ cho popup nhạc: Hyprland làm nhòe phía sau khung; ignore_alpha để lớp phủ trong suốt
-- (alpha ~0) quanh khung không bị nhòe cả màn hình.
hl.layer_rule({ name = "kafka-glass-media", match = { namespace = "^kafka-media-popup$" }, blur = true, ignore_alpha = 0.05 })

-- Cử chỉ kiểu niri: vuốt 3 ngón ngang = cuộn dải cột, 3 ngón dọc = đổi workspace
hl.gesture({ fingers = 3, direction = "horizontal", action = "scroll_move" })
hl.gesture({ fingers = 3, direction = "vertical",   action = "workspace" })
-- 4 ngón: lên = tổng quan hyprshell (như nhấn-thả Super), xuống = chế độ Desktop ⇄ cuộn (như Super + D).
-- action nhận hàm Lua (chuỗi "dispatcher" không hợp lệ ở 0.57).
hl.gesture({ fingers = 4, direction = "up",   action = function() hl.exec_cmd("hyprshell socat '\"OpenOverview\"'") end })
hl.gesture({ fingers = 4, direction = "down", action = function() hl.exec_cmd(os.getenv("HOME") .. "/.config/hypr/scripts/desktop-mode.sh toggle") end })
-- Chụm 3 ngón = kính lúp (phóng to quanh con trỏ), xem thêm kafka_zoom() ở phần phím tắt
hl.gesture({ fingers = 3, direction = "pinch", action = "cursorZoom" })

-- ----------------
-- 7. KEYBINDINGS
-- ----------------
local mainMod = "SUPER"
local function key(k) return mainMod .. " + " .. k end

-- Core Applications
hl.bind(key("Q"),              hl.dsp.exec_cmd(terminal))
hl.bind(key("Return"),         hl.dsp.exec_cmd(terminal))
hl.bind(key("C"),              hl.dsp.window.close())
hl.bind(key("SHIFT + X"),      hl.dsp.window.kill())                                   -- buộc đóng app treo (KHÔNG dùng Shift+C: dễ nhầm với copy)
hl.bind(key("SHIFT + Q"),      hl.dsp.exec_cmd(scripts .. "closemenu.sh"))             -- menu chọn chương trình để đóng
hl.bind(key("T"),              hl.dsp.exec_cmd(scripts .. "pin-toggle.sh"))            -- treo cửa sổ nổi ở góc, theo mọi workspace
hl.bind(key("SHIFT + T"),      hl.dsp.exec_cmd(scripts .. "pin-toggle.sh all"))        -- bỏ treo tất cả
hl.bind(key("O"),              hl.dsp.exec_cmd(scripts .. "hide-windows.py menu"))     -- menu chọn cửa sổ ẩn/hiện
hl.bind(key("I"),              hl.dsp.exec_cmd(scripts .. "hide-windows.py hide-active")) -- ẩn cửa sổ đang chọn (vào special:hidden)
hl.bind(key("SHIFT + I"),      hl.dsp.exec_cmd(scripts .. "hide-windows.py show-all"))  -- hiện lại mọi cửa sổ đã ẩn
hl.bind(key("M"),              hl.dsp.exec_cmd(powerMenu))
hl.bind(key("Escape"),         hl.dsp.exec_cmd(scripts .. "lock.sh"))   -- hyprlock theo giao diện (pixel/phẳng)
hl.bind(key("E"),              hl.dsp.exec_cmd(fileManager))
hl.bind(key("Space"),          hl.dsp.exec_cmd(menu))
hl.bind(key("R"),              hl.dsp.exec_cmd(menu))
-- Nhấn-thả riêng Super: do hyprshell tự đăng ký (chế độ tổng quan), không bind ở đây.
-- Super + W (đổi hình nền) đã tắt vì dùng một hình nền cố định
-- hl.bind(key("W"), hl.dsp.exec_cmd(wallScript .. " next"))
hl.bind(key("SHIFT + B"),      hl.dsp.exec_cmd("killall -SIGUSR2 waybar || waybar &"))
hl.bind(key("V"),              hl.dsp.exec_cmd(clipMenu))
hl.bind(key("A"),              hl.dsp.exec_cmd(scripts .. "toggle-app.sh kafka-cava kitty --class kafka-cava -e cava")) -- bấm lần nữa để tắt
hl.bind(key("SHIFT + A"),      hl.dsp.exec_cmd(scripts .. "cava-wallpaper.py --toggle"))  -- sóng nhạc ở đáy màn hình (bấm xuyên), chỉ hiện khi có tiếng
hl.bind(key("ALT + U"),        hl.dsp.exec_cmd(scripts .. "ui-theme.sh toggle"))         -- giao diện Waybar: phẳng ⇄ pixel
hl.bind(key("ALT + A"),        hl.dsp.exec_cmd(scripts .. "cava-wallpaper.py --cycle-mode"))  -- sóng nhạc: nổi trên cửa sổ ⇄ làm hình nền

-- Window States
hl.bind(key("SHIFT + V"),      function()                           -- nổi/xếp; vừa nổi thì thu cho vừa vùng nội dung
    hl.dispatch(hl.dsp.window.float({ action = "toggle" }))
    if kafka_fit_float then kafka_fit_float(hl.get_active_window()) end
end)
hl.bind(key("F"),              hl.dsp.window.fullscreen({ mode = 0 }))   -- toàn màn hình (che cả Waybar)
hl.bind(key("SHIFT + F"),      hl.dsp.window.fullscreen({ mode = 1 }))   -- phóng to trong vùng nội dung (chừa Waybar); bấm lại = thu
-- Đổi nghĩa phím do pseudo/togglesplit chỉ chạy với dwindle: Super + P = promote (bên dưới), Super + J = focus xuống.

-- Layout cuộn (scrolling): đổi độ rộng, dời, gộp/tách cột
hl.bind(key("G"),              hl.dsp.layout("colresize +conf"))      -- xoay vòng độ rộng cột: 1/3 → 1/2 → 2/3 → toàn màn
hl.bind(key("SHIFT + G"),      hl.dsp.exec_cmd(scripts .. "tile-menu.sh")) -- bảng chia ô cố định cho workspace này (Auto = về cuộn)
hl.bind(key("D"),              hl.dsp.exec_cmd(scripts .. "desktop-mode.sh toggle")) -- chuyển chế độ cuộn ↔ Desktop (cửa sổ tự do), mọi workspace
-- Super + Tab = chuyển cửa sổ bằng bộ chuyển của hyprshell (giữ Super, Tab để sang tiếp, thả Super = nhảy tới).
-- hyprshell chỉ tự gán Alt + Tab; đặt nó sang "super" thì mất phím tổng quan. Xem scripts/window-switch.sh.
hl.bind(key("Tab"),            hl.dsp.exec_cmd(scripts .. "window-switch.sh open"),     { repeating = true })
hl.bind(key("SHIFT + Tab"),    hl.dsp.exec_cmd(scripts .. "window-switch.sh open-rev"), { repeating = true })
hl.bind(key("code:133"),       hl.dsp.exec_cmd(scripts .. "window-switch.sh release"),  { release = true, transparent = true })   -- Super_L theo mã phím: hyprshell gỡ mọi bind tên "super_l" khi gán phím tổng quan
hl.bind(key("Super_R"),        hl.dsp.exec_cmd(scripts .. "window-switch.sh release"),  { release = true, transparent = true })
hl.bind(key("minus"),          hl.dsp.layout("colresize -0.1"),  { repeating = true })  -- thu hẹp cột
hl.bind(key("equal"),          hl.dsp.layout("colresize +0.1"),  { repeating = true })  -- nới rộng cột
hl.bind(key("CTRL + left"),    hl.dsp.layout("swapcol l"))            -- dời cột sang trái
hl.bind(key("CTRL + right"),   hl.dsp.layout("swapcol r"))            -- dời cột sang phải
hl.bind(key("comma"),          hl.dsp.layout("consume_or_expel prev")) -- gộp cửa sổ vào cột trái (xếp chồng); bấm lại = tách ra
hl.bind(key("period"),         hl.dsp.layout("consume_or_expel next")) -- gộp cửa sổ vào cột phải; bấm lại = tách ra
hl.bind(key("P"),              hl.dsp.layout("promote"))               -- tách cửa sổ khỏi cột chồng thành cột riêng
-- Đã thử trong phiên lồng (0.57.2): "l/r" không hợp lệ cho consume_or_expel (phải prev/next);
-- "move tobeg/toend" lỗi, "focus tobeg" không làm gì, "fit active" = giãn cột hết màn (đã có Super + G).

-- Screenshot (Grim + Slurp -> Clipboard & ~/Pictures/Screenshots)
-- Chụp / quay màn hình: scripts/capture.sh (hyprshot + satty + wf-recorder), cũng là nút chụp trên dock
hl.bind(key("SHIFT + S"), hl.dsp.exec_cmd(scripts .. "capture.sh region"))   -- chụp vùng
hl.bind("Print",          hl.dsp.exec_cmd(scripts .. "capture.sh menu"))     -- menu chọn kiểu chụp/quay (6 ô)
hl.bind("SHIFT + Print",  hl.dsp.exec_cmd(scripts .. "capture.sh full"))     -- chụp ngay màn hình đang dùng
hl.bind(key("SHIFT + R"), hl.dsp.exec_cmd(scripts .. "capture.sh rec full")) -- quay màn hình; đang quay thì dừng

-- Focus Navigation (Arrow keys + Vim HJKL; J = xuống, trước đây là togglesplit)
for k, dir in pairs({ left = "left", right = "right", up = "up", down = "down", h = "left", l = "right", k = "up", j = "down" }) do
    hl.bind(key(k), hl.dsp.focus({ direction = dir }))
end

-- Workspaces (1-10) + Move Active Window to Workspace
for i = 1, 10 do
    local k = i % 10 -- 10 -> phím 0
    hl.bind(key(k),             hl.dsp.focus({ workspace = i }))
    hl.bind(key("SHIFT + " .. k), hl.dsp.window.move({ workspace = i }))
end

-- Scratchpad (Special Workspace)
hl.bind(key("S"),         hl.dsp.workspace.toggle_special("magic"))
hl.bind(key("SHIFT + Z"), hl.dsp.window.move({ workspace = "special:magic" }))

-- Mouse Bindings (Move/Resize/Scroll Workspaces)
hl.bind(key("mouse_down"), hl.dsp.focus({ workspace = "e+1" }))
hl.bind(key("mouse_up"),   hl.dsp.focus({ workspace = "e-1" }))
-- Kính lúp (zoom quanh con trỏ, tính năng có sẵn của Hyprland, thay plugin macos-zoom):
-- Super + Ctrl + cuộn / = / - phóng to/thu nhỏ, Super + Ctrl + 0 về 1x. Mức 1..6, bước 0.25.
function kafka_zoom(step)
    local cur = tonumber(hl.get_config("cursor.zoom_factor")) or 1
    local z = (step == 0) and 1 or math.max(1, math.min(6, cur + step))
    hl.config({ cursor = { zoom_factor = z } })
    return z
end
hl.bind(key("CTRL + mouse_down"), function() kafka_zoom(0.25) end)
hl.bind(key("CTRL + mouse_up"),   function() kafka_zoom(-0.25) end)
hl.bind(key("CTRL + equal"),      function() kafka_zoom(0.25) end,  { repeating = true })
hl.bind(key("CTRL + minus"),      function() kafka_zoom(-0.25) end, { repeating = true })
hl.bind(key("CTRL + 0"),          function() kafka_zoom(0) end)
hl.bind(key("mouse:272"),  hl.dsp.window.drag(),   { mouse = true })
hl.bind(key("mouse:273"),  hl.dsp.window.resize(), { mouse = true })

-- Laptop Function Keys (Audio & Brightness) — chạy cả khi khóa màn hình, giữ phím để lặp
local fn = { locked = true, repeating = true }
hl.bind("XF86AudioRaiseVolume",  hl.dsp.exec_cmd("wpctl set-volume -l 1.5 @DEFAULT_AUDIO_SINK@ 5%+"), fn)
hl.bind("XF86AudioLowerVolume",  hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),        fn)
hl.bind("XF86AudioMute",         hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),       fn)
hl.bind("XF86AudioMicMute",      hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"),     fn)
hl.bind("XF86MonBrightnessUp",   hl.dsp.exec_cmd("brightnessctl s 5%+"),                              fn)
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("brightnessctl s 5%-"),                              fn)

-- Phím tắt tùy chỉnh: hypr/keybinds.lua (do scripts/keybinds-editor.py ghi, nút 󰌌 trên dock).
-- Nạp SAU các phím mặc định ở trên nên ghi đè được chúng. Mỗi mục:
--   { keys = "SUPER + B", action = "exec",   command = "<lệnh shell>", description = "..." }
--   { keys = "SUPER + B", action = "lua",    command = "hl.dsp.window.close()", description = "..." }
--   { keys = "SUPER + B", action = "unbind" }            -- tắt phím mặc định
-- Mục lỗi bị bỏ qua (pcall) để một dòng sai không làm hỏng cả cấu hình.
do
    local ok, list = pcall(dofile, os.getenv("HOME") .. "/.config/hypr/keybinds.lua")
    if ok and type(list) == "table" then
        for _, b in ipairs(list) do
            if type(b) == "table" and type(b.keys) == "string" then
                pcall(hl.unbind, b.keys)
                local opts = { description = b.description }
                if b.action == "exec" and type(b.command) == "string" then
                    pcall(hl.bind, b.keys, hl.dsp.exec_cmd(b.command), opts)
                elseif b.action == "lua" and type(b.command) == "string" then
                    local f = load("return " .. b.command)
                    local okd, d = false, nil
                    if f then okd, d = pcall(f) end
                    if okd and d then pcall(hl.bind, b.keys, d, opts) end
                end
            end
        end
    end
end

-- ----------------
-- 7b. CHIA KHU LÀM VIỆC THEO TỈ LỆ (1:1, 2:1, lưới...) — xem hypr/kafka-tile.lua
--     Chọn qua ô "Chia khu" trong hộp chức năng trên dock (scripts/tile-menu.sh).
-- ----------------
do
    local ok, err = pcall(dofile, os.getenv("HOME") .. "/.config/hypr/kafka-tile.lua")
    if not ok then print("kafka-tile: " .. tostring(err)) end
end

-- ----------------
-- 8. WINDOW RULES
-- ----------------
-- Chặn app tự phóng to khi xếp cột. Ở chế độ Desktop, kafka_desktop() TẮT luật này để nút phóng to của app chạy
-- bằng phóng to của Hyprland (chừa Waybar); để chặn thì app như Chromium tự giãn bằng cả màn hình, đè lên Waybar.
KafkaSuppressMax = hl.window_rule({ name = "suppress-maximize", match = { class = ".*" }, suppress_event = "maximize" })

local pavu = "^(org\\.pulseaudio\\.pavucontrol|pavucontrol)$"
hl.window_rule({ name = "pavucontrol", match = { class = pavu }, float = true, size = "760 520", center = true })

hl.window_rule({ name = "nm-editor",   match = { class = "^(nm-connection-editor)$" }, float = true })
hl.window_rule({ name = "blueman",     match = { class = "^(blueman-manager)$" },      float = true, size = "720 480", center = true })
-- btop (bấm CPU/RAM/nhiệt độ trên Waybar), thay gnome-system-monitor
-- App quản lý phím tắt (nút 󰌌 trên dock, scripts/keybinds-editor.py)
hl.window_rule({ name = "kafka-keybinds", match = { class = "^(kafka\\.keybinds)$" }, float = true, size = "1000 640", center = true })
hl.window_rule({ name = "kafka-studio", match = { class = "^(kafka\\.studio)$" }, float = true, size = "1440 760", center = true })   -- Kafka Studio (scripts/studio.py)
hl.window_rule({ name = "kafka-btop",  match = { class = "^(kafka-btop)$" },           float = true, size = "1100 680", center = true })
hl.window_rule({ name = "satty",       match = { class = "^(com\\.gabm\\.satty)$" },     float = true, size = "1500 900", center = true })   -- vẽ lên ảnh chụp (capture.sh edit)
hl.window_rule({ name = "file-dialog", match = { title = "^(Open File|Save File|Confirm)$" }, float = true })

-- ----------------
-- 8b. CHẾ ĐỘ DESKTOP (cửa sổ tự do) ↔ CUỘN — scripts/desktop-mode.sh, Super + D, nút  /  trên thanh trên
--     kafka_desktop(true) bật luật "mọi cửa sổ MỚI đều nổi"; script lo phần cho cửa sổ đang mở nổi lên / xếp lại.
--     Trạng thái lưu ở ~/.local/state/kafka/layout-mode nên reload / đăng nhập lại vẫn giữ chế độ.
-- ----------------
-- Giới hạn một cửa sổ nổi trong vùng nội dung: to hơn thì thu lại, lệch ra ngoài thì đẩy vào (lề FLOAT_MARGIN).
local FLOAT_MARGIN = 12   -- = gaps_out, cách thanh trên / dock như cửa sổ xếp cột
function kafka_fit_float(w)
    if not w or not w.floating or w.pinned or (w.fullscreen or 0) ~= 0 then return "skip" end
    if w.workspace and w.workspace.id and w.workspace.id < 0 then return "skip" end   -- special: (ẩn, scratchpad)
    local m = w.monitor
    if not m or not w.at or not w.size then return "skip" end
    local r, sc = m.reserved or {}, (m.scale and m.scale > 0) and m.scale or 1
    local ax = m.x + (r.left or 0) + FLOAT_MARGIN
    local ay = m.y + (r.top or 0) + FLOAT_MARGIN
    local aw = math.floor(m.width / sc - (r.left or 0) - (r.right or 0) - 2 * FLOAT_MARGIN)
    local ah = math.floor(m.height / sc - (r.top or 0) - (r.bottom or 0) - 2 * FLOAT_MARGIN)
    local x, y, ww, wh = w.at.x, w.at.y, w.size.x, w.size.y
    local nw, nh = math.min(ww, aw), math.min(wh, ah)
    local nx = math.floor(math.max(ax, math.min(x, ax + aw - nw)))
    local ny = math.floor(math.max(ay, math.min(y, ay + ah - nh)))
    local target = "address:" .. w.address
    if nw ~= ww or nh ~= wh then
        hl.dispatch(hl.dsp.window.resize({ x = nw, y = nh, relative = false, window = target }))
    end
    if nx ~= x or ny ~= y then
        hl.dispatch(hl.dsp.window.move({ x = nx, y = ny, relative = false, window = target }))
    end
    return "ok"
end
-- Kéo bằng chuột trái (Super + kéo, kéo mép, kéo thanh tiêu đề của app): Hyprland không báo "kéo xong", nên
-- chụp hình học các cửa sổ nổi lúc NHẤN chuột trái và so lúc THẢ (bind non_consuming: không chặn cú bấm nào).
--   kích thước đổi (kéo mép)                     → thu lại cho vừa vùng nội dung ngay
--   chỉ vị trí đổi + thả chuột NGOÀI vùng nội dung → phóng to trong vùng nội dung (chừa Waybar)
--   (ngoài = lên thanh trên, vào dock, hoặc chạm mép màn hình)
local DRAG_EDGE = 2
local function kafka_cursor_outside(cx, cy)
    local m = hl.get_monitor_at(cx, cy)
    if not m then return false end
    local r, sc = m.reserved or {}, (m.scale and m.scale > 0) and m.scale or 1
    local x0, y0 = m.x + (r.left or 0), m.y + (r.top or 0)
    local x1 = m.x + m.width / sc - (r.right or 0)
    local y1 = m.y + m.height / sc - (r.bottom or 0)
    return cx < x0 + DRAG_EDGE or cx > x1 - DRAG_EDGE or cy < y0 + DRAG_EDGE or cy > y1 - DRAG_EDGE
end
KafkaDragSnap = {}
function kafka_drag_begin()
    KafkaDragSnap = {}
    for _, w in ipairs(hl.get_windows()) do
        if w.floating and (w.fullscreen or 0) == 0 and w.at and w.size then
            KafkaDragSnap[w.address] = { w.at.x, w.at.y, w.size.x, w.size.y }
        end
    end
    return "ok"
end
function kafka_drag_end(cx, cy)   -- cx, cy: toạ độ con trỏ lúc thả (bỏ trống = lấy hiện tại)
    local snap = KafkaDragSnap
    KafkaDragSnap = {}
    if next(snap) == nil then return "none" end
    if not cx then
        local c = hl.get_cursor_pos()
        if not c then return "none" end
        cx, cy = c.x, c.y
    end
    local result = "none"
    for _, w in ipairs(hl.get_windows()) do
        local s = snap[w.address]
        if s and w.floating and (w.fullscreen or 0) == 0 and w.at and w.size then
            local moved   = w.at.x ~= s[1] or w.at.y ~= s[2]
            local resized = w.size.x ~= s[3] or w.size.y ~= s[4]
            if resized then
                kafka_fit_float(w); result = "fit"
            elseif moved and kafka_cursor_outside(cx, cy) then
                hl.dispatch(hl.dsp.window.fullscreen({ mode = 1, window = "address:" .. w.address })); result = "max"
            elseif moved then
                kafka_fit_float(w); result = "moved"
            end
        end
    end
    return result
end
hl.bind("mouse:272", function() kafka_drag_begin() end,
    { non_consuming = true, ignore_mods = true, description = "chụp hình học cửa sổ nổi trước khi kéo" })
hl.bind("mouse:272", function()
    local c = hl.get_cursor_pos()
    local cx, cy = c and c.x, c and c.y
    -- đợi một nhịp cho Hyprland chốt kích thước/vị trí sau khi thả
    hl.timer(function() kafka_drag_end(cx, cy) end, { timeout = 60, type = "oneshot" })
end, { release = true, non_consuming = true, ignore_mods = true, description = "kéo xong: thu cho vừa / phóng to" })

-- Góc lõm (scripts/corner-fillet.py) dùng lớp overlay vì layer rule `order` không đưa nó lên trên Waybar trong cùng lớp top.
-- KHÔNG đặt order cho Waybar (topbar/dockbar): order đổi cả thứ tự xếp vùng dành riêng -> dock chiếm hết cạnh phải, đẩy thanh trên.

-- Cửa sổ mới mở: đợi luật nổi/kích thước áp xong rồi mới giới hạn
hl.on("window.open", function(w)
    if not w then return end
    local addr = w.address
    hl.timer(function()
        for _, x in ipairs(hl.get_windows()) do
            if x.address == addr then kafka_fit_float(x) break end
        end
    end, { timeout = 150, type = "oneshot" })
end)
-- desktop-mode.sh gọi sau khi cho các cột nổi lên
function kafka_fit_all_floats()
    for _, w in ipairs(hl.get_windows()) do kafka_fit_float(w) end
    return "ok"
end

function kafka_desktop(on)
    if KafkaSuppressMax then KafkaSuppressMax:set_enabled(not on) end   -- Desktop: cho phép phóng to (chừa Waybar)
    if on then
        if KafkaDesktopRule then
            KafkaDesktopRule:set_enabled(true)
        else
            KafkaDesktopRule = hl.window_rule({ name = "kafka-desktop", match = { class = ".*" }, float = true })
        end
        return "desktop"
    end
    if KafkaDesktopRule then KafkaDesktopRule:set_enabled(false) end
    return "scroll"
end
do
    local state = (os.getenv("XDG_STATE_HOME") or (os.getenv("HOME") .. "/.local/state")) .. "/kafka/layout-mode"
    local f = io.open(state, "r")
    if f then
        local mode = f:read("*l"); f:close()
        if mode == "desktop" then kafka_desktop(true) end
    end
end

-- Cửa sổ sóng nhạc cava (Super + A)
hl.window_rule({
    name  = "kafka-cava",
    match = { class = "^(kafka-cava)$" },
    float = true,
    size  = "720 260",
    move  = "(monitor_w-732) (monitor_h-272)",
})
