-- ==============================================================================
--  KAFKA TILE — chia khu làm việc theo tỉ lệ chọn sẵn (1:1, 1:2, 2:1, lưới 2x2...)
--  Nạp từ hyprland.lua bằng dofile(). Chọn kiểu chia qua menu:
--    hypr/scripts/tile-menu.sh  ->  hyprctl eval 'kafka_tile("1:2", "0x<địa chỉ>")'
--  Mỗi workspace nhớ kiểu chia riêng. "auto" = trả về layout mặc định (scrolling — cuộn ngang).
--  Cửa sổ đang chọn lúc bấm menu trở thành cửa sổ CHÍNH (ô to / ô đầu tiên).
-- ==============================================================================

-- Trạng thái theo workspace: KafkaTile[id] = { mode = "1:2", main = "0x...", rule = <WorkspaceRule> }
KafkaTile = KafkaTile or {}

local LAYOUT = "kafka"            -- tên đăng ký
local LAYOUT_ID = "lua:" .. LAYOUT -- tên dùng trong general.layout / workspace_rule

-- Kiểu "cột chính : cột phụ" -> tỉ lệ bề rộng cột chính
local RATIOS = {
    ["1:1"] = 1 / 2, ["1:2"] = 1 / 3, ["2:1"] = 2 / 3,
    ["1:3"] = 1 / 4, ["3:1"] = 3 / 4,
}

local function ws_of(target)
    local w = target and target.window
    local ws = w and w.workspace
    return ws and ws.id or nil
end

local function box(x, y, w, h) return { x = x, y = y, w = w, h = h } end

hl.layout.register(LAYOUT, {
    recalculate = function(ctx)
        local targets = ctx.targets
        local n = #targets
        if n == 0 then return end

        local st = KafkaTile[ws_of(targets[1])] or {}
        local mode = st.mode or "1:1"

        -- Đưa cửa sổ chính lên đầu danh sách
        local order = {}
        for i = 1, n do order[i] = targets[i] end
        if st.main then
            for i = 1, n do
                local w = order[i].window
                if w and w.address == st.main then
                    table.insert(order, 1, table.remove(order, i))
                    break
                end
            end
        end

        local a = ctx.area
        if n == 1 then
            order[1]:place(box(a.x, a.y, a.w, a.h))
            return
        end

        if mode == "grid" then
            -- Lưới: 2 cửa sổ = 2 cột, 3-4 = 2x2, 5-6 = 3x2, ...
            local cols = math.ceil(math.sqrt(n))
            local rows = math.ceil(n / cols)
            local cw, ch = a.w / cols, a.h / rows
            for i = 1, n do
                local c, r = (i - 1) % cols, math.floor((i - 1) / cols)
                -- hàng cuối thiếu ô thì giãn đều cho kín
                local in_row = (r == rows - 1) and (n - r * cols) or cols
                local w = a.w / in_row
                order[i]:place(box(a.x + c * w, a.y + r * ch, w, ch))
            end
        elseif mode == "cols" then
            -- Các cột đều nhau (1:1:1...)
            local w = a.w / n
            for i = 1, n do order[i]:place(box(a.x + (i - 1) * w, a.y, w, a.h)) end
        elseif mode == "rows" then
            -- Các hàng đều nhau (trên/dưới)
            local h = a.h / n
            for i = 1, n do order[i]:place(box(a.x, a.y + (i - 1) * h, a.w, h)) end
        else
            -- Cột chính bên trái theo tỉ lệ, các cửa sổ còn lại xếp chồng bên phải
            local ratio = RATIOS[mode] or 0.5
            local mw = a.w * ratio
            order[1]:place(box(a.x, a.y, mw, a.h))
            local h = a.h / (n - 1)
            for i = 2, n do
                order[i]:place(box(a.x + mw, a.y + (i - 2) * h, a.w - mw, h))
            end
        end
    end,
})

-- Gọi từ menu: kafka_tile(<kiểu>, <địa chỉ cửa sổ chính, có thể bỏ trống>)
function kafka_tile(mode, main)
    local ws = hl.get_active_workspace()
    if not ws or not ws.id then return "no workspace" end
    local id = ws.id
    local st = KafkaTile[id] or {}
    KafkaTile[id] = st

    if mode == "auto" then
        st.mode = nil
        if st.rule then st.rule:set_enabled(false) end
        return "auto"
    end

    st.mode = mode
    if main and main ~= "" then st.main = main end
    if st.rule then
        st.rule:set_enabled(true)
    else
        st.rule = hl.workspace_rule({ workspace = tostring(id), layout = LAYOUT_ID })
    end
    return mode
end

-- Trả về kiểu chia của workspace đang xem (menu dùng để tô ô "đang dùng")
function kafka_tile_current()
    local ws = hl.get_active_workspace()
    local st = ws and KafkaTile[ws.id]
    return (st and st.mode) or "auto"
end
