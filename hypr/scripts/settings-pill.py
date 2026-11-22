#!/usr/bin/env python3
"""settings-pill.py — nút "Cài đặt chung" trên thanh trên ở theme pixel (`custom/settings` trong waybar/topbar-pixel.jsonc).

Gộp Wi-Fi + âm lượng + pin thành MỘT nút (người dùng 2026-11-22): bấm = popup Cài đặt nhanh
(`control-popup.py main`), phải = bảng Wi-Fi, giữa = tắt/mở tiếng, lăn = âm lượng (trong config Waybar).

Module custom chạy LIÊN TỤC (không `interval`): mỗi dòng in ra = một lần cập nhật JSON {text, tooltip, class}.
Cập nhật ngay khi có sự kiện, không hỏi định kỳ dày:
  * âm lượng  : `pactl subscribe` (sự kiện sink/server)
  * mạng      : `nmcli monitor`
  * pin + sóng: hẹn giờ 15s (sysfs + /proc/net/wireless, rất rẻ)

  settings-pill.py            chạy cho Waybar
  settings-pill.py --once     in một dòng rồi thoát
  settings-pill.py --selftest
"""

import json
import os
import subprocess
import sys
import threading
import time

VOL_ICONS = ["\U000f057f", "\U000f0580", "\U000f057e"]          # 󰕿 󰖀 󰕾
VOL_MUTE = "\U000f075f"                                          # 󰝟
WIFI_ICONS = ["\U000f092f", "\U000f091f", "\U000f0922", "\U000f0925", "\U000f0928"]   # 󰤯 󰤟 󰤢 󰤥 󰤨
WIFI_OFF, ETH = "\U000f092e", "\U000f0200"                       # 󰤮 󰈀
BAT_ICONS = ["\U000f007a", "\U000f007c", "\U000f007e", "\U000f0080", "\U000f0079"]    # 󰁺 󰁼 󰁾 󰂀 󰁹
BAT_CHG, AC = "\U000f0084", "\U000f06a5"                         # 󰂄 󰚥
SEP = "<span color='#5a4a6b'>│</span>"


def run(cmd, timeout=2):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def volume():
    """(phần trăm, tắt tiếng) hoặc (None, False)."""
    out = run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    return parse_volume(out)


def parse_volume(out):
    parts = out.split()
    if len(parts) < 2 or parts[0] != "Volume:":
        return None, False
    try:
        return int(round(float(parts[1]) * 100)), "[MUTED]" in out
    except ValueError:
        return None, False


def network():
    """(kiểu 'wifi'|'ethernet'|None, tên kết nối, sóng 0..100 hoặc None)."""
    kind = name = None
    for line in run(["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device"]).splitlines():
        t, _, rest = line.partition(":")
        st, _, conn = rest.partition(":")
        if st == "connected" and t in ("wifi", "ethernet"):
            if kind != "ethernet":                 # có dây thì ưu tiên hiện dây
                kind, name = t, conn.replace("\\:", ":")
    sig = parse_wireless(read("/proc/net/wireless")) if kind == "wifi" else None
    return kind, name, sig


def parse_wireless(txt):
    """Chất lượng sóng (thang 70) → phần trăm, từ /proc/net/wireless."""
    for line in txt.splitlines()[2:]:
        f = line.split()
        if len(f) >= 3:
            try:
                return max(0, min(100, int(float(f[2].rstrip(".")) * 100 / 70)))
            except ValueError:
                pass
    return None


def battery():
    base = "/sys/class/power_supply"
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return None, False
    for n in names:
        if read(f"{base}/{n}/type") == "Battery":
            cap = read(f"{base}/{n}/capacity")
            if cap.isdigit():
                return int(cap), read(f"{base}/{n}/status") in ("Charging", "Full")
    return None, False


def build(vol, muted, kind, name, sig, bat, charging):
    """JSON cho Waybar (tách riêng để selftest)."""
    cls = []
    if kind == "wifi":
        net_icon = WIFI_ICONS[min(4, (sig or 0) * 5 // 101)] + (f" {sig}%" if sig is not None else "")   # có số → 3 ô cân nhau
        net_tip = f"Wi-Fi: {name}" + (f" ({sig}%)" if sig is not None else "")
    elif kind == "ethernet":
        net_icon, net_tip = ETH, f"Dây mạng: {name}"
    else:
        net_icon, net_tip = WIFI_OFF, "Chưa kết nối mạng"
        cls.append("offline")
    if vol is None:
        vol_txt, vol_tip = f"{VOL_MUTE}", "Không có loa"
    elif muted:
        vol_txt, vol_tip = f"{VOL_MUTE} <span color='#9a8bab'>{vol}%</span>", f"Âm lượng {vol}% (đang tắt tiếng)"
        cls.append("muted")
    else:
        vol_txt, vol_tip = f"{VOL_ICONS[min(2, vol * 3 // 101)]} {vol}%", f"Âm lượng {vol}%"
    if bat is None:
        bat_txt, bat_tip = AC, "Cắm điện (không có pin)"
    else:
        icon = BAT_CHG if charging else BAT_ICONS[min(4, bat * 5 // 101)]
        col = ""
        if not charging and bat <= 15:
            col, _ = "#ff6b82", cls.append("critical")
        elif not charging and bat <= 30:
            col, _ = "#ffe08a", cls.append("warning")
        num = f"<span color='{col}'>{bat}%</span>" if col else f"{bat}%"
        bat_txt, bat_tip = f"{icon} {num}", f"Pin {bat}%" + (" (đang sạc)" if charging else "")
    text = f"{net_icon}  {SEP}  {vol_txt}  {SEP}  {bat_txt}"
    tip = (f"{net_tip} · {vol_tip} · {bat_tip}\n"
           "Bấm: cài đặt nhanh · Phải: bảng Wi-Fi · Giữa: tắt/mở tiếng · Lăn: âm lượng")
    return json.dumps({"text": text, "tooltip": tip, "class": cls or ["normal"]}, ensure_ascii=False)


def snapshot():
    v, m = volume()
    k, n, s = network()
    b, c = battery()
    return build(v, m, k, n, s, b, c)


class Pill:
    def __init__(self):
        self.lock = threading.Lock()
        self.last = None
        self.wake = threading.Event()

    def emit(self):
        with self.lock:
            line = snapshot()
            if line != self.last:
                self.last = line
                try:
                    sys.stdout.write(line + "\n")
                    sys.stdout.flush()
                except BrokenPipeError:
                    os._exit(0)                     # Waybar đã tắt

    def watch(self, cmd, keep):
        """Chạy lệnh theo dõi; dòng nào khớp `keep` thì đánh thức vòng in (gộp sự kiện dồn dập)."""
        while True:
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                for line in p.stdout:
                    if keep(line):
                        self.wake.set()
            except OSError:
                pass
            time.sleep(5)                            # lệnh chết (vd pipewire khởi động lại) → chạy lại

    def loop(self):
        threading.Thread(target=self.watch, daemon=True,
                         args=(["pactl", "subscribe"], lambda l: " on sink" in l or " on server" in l)).start()
        threading.Thread(target=self.watch, daemon=True, args=(["nmcli", "monitor"], lambda l: True)).start()
        self.emit()
        while True:
            fired = self.wake.wait(15)
            if fired:
                time.sleep(0.12)                     # gộp loạt sự kiện khi lăn chuột
                self.wake.clear()
            self.emit()


def selftest():
    assert parse_volume("Volume: 0.45\n") == (45, False)
    assert parse_volume("Volume: 0.30 [MUTED]\n") == (30, True)
    assert parse_volume("") == (None, False)
    w = ("Inter-| sta-|   Quality        |   Discarded packets\n"
         " face | tus | link level noise |  nwid  crypt\n"
         " wlan0: 0000   56.  -54.  -256        0      0\n")
    assert parse_wireless(w) == 80
    j = json.loads(build(45, False, "wifi", "Nha", 80, 93, False))
    assert "93%" in j["text"] and "45%" in j["text"] and j["class"] == ["normal"] and "Nha" in j["tooltip"]
    j = json.loads(build(30, True, None, None, None, 12, False))
    assert set(j["class"]) == {"offline", "muted", "critical"}
    j = json.loads(build(None, False, "ethernet", "eth", None, None, False))
    assert AC in j["text"] and ETH in j["text"]
    json.loads(snapshot())
    print("settings-pill.py selftest OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--once" in sys.argv:
        print(snapshot())
        sys.exit(0)
    Pill().loop()
