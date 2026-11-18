#!/usr/bin/env bash
# Treo / bỏ treo cửa sổ đang chọn (Super + T).
# Treo = nổi, thu nhỏ về góc phải-dưới, luôn ở trên và theo bạn sang mọi workspace
# (kiểu picture-in-picture: xem docs/thư mục trong khi code).
# Super + T trên cửa sổ đang treo -> bỏ treo. Super + Shift + T (tham số "all")
# -> bỏ treo MỌI cửa sổ, không phụ thuộc chuột đang trỏ vào đâu.

if [[ "$1" == "all" ]]; then
    hyprctl clients -j | python3 -c '
import json, sys, subprocess
for c in json.load(sys.stdin):
    if c["pinned"]:
        a = "address:" + c["address"]
        subprocess.run(["hyprctl", "--batch", f"dispatch hl.dsp.window.pin({{ action = \"disable\", window = \"{a}\" }}); dispatch hl.dsp.window.float({{ action = \"disable\", window = \"{a}\" }})"], capture_output=True)
'
    exit 0
fi

read -r pinned x y w h < <(python3 - <<'EOF'
import json, subprocess
def q(*a):
    try:
        return json.loads(subprocess.run(["hyprctl", *a, "-j"], capture_output=True, text=True).stdout or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
win = q("activewindow")
if not isinstance(win, dict) or not win:
    print("none 0 0 0 0"); raise SystemExit
monitors = q("monitors")
if not isinstance(monitors, list) or not monitors:
    print("none 0 0 0 0"); raise SystemExit
m = next((m for m in monitors if isinstance(m, dict) and m.get("focused")), monitors[0])
mw, mh = int(m["width"] / m["scale"]), int(m["height"] / m["scale"])
w, h = mw * 36 // 100, mh * 42 // 100
print(str(win["pinned"]).lower(), m["x"] + mw - w - 16, m["y"] + mh - h - 16, w, h)
EOF
)

case "$pinned" in
    none) exit 0 ;;
    true) hyprctl --batch 'dispatch hl.dsp.window.pin({ action = "disable" }); dispatch hl.dsp.window.float({ action = "disable" })' >/dev/null ;;
    *)    hyprctl --batch "dispatch hl.dsp.window.float({ action = \"enable\" }); dispatch hl.dsp.window.resize({ x = $w, y = $h, relative = false }); dispatch hl.dsp.window.move({ x = $x, y = $y, relative = false }); dispatch hl.dsp.window.pin({ action = \"enable\" })" >/dev/null ;;
esac
