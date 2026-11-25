#!/usr/bin/env python3
"""Hiển thị pin thiết bị ngoại vi đang kết nối cho module ``custom/devbat``.

Script dò động qua UPower, BlueZ và USB HID; không cần ghi cứng danh sách thiết
bị. Khi chạy liên tục, mỗi dòng stdout là một JSON mới khi nội dung thay đổi.
Mọi lỗi D-Bus, sysfs hoặc dịch vụ tùy chọn đều được coi như không có thiết bị
và sẽ được thử lại ở lần làm mới kế tiếp. ``BrokenPipeError`` có nghĩa Waybar
đã đóng pipe nên tiến trình thoát ngay. Pin Logitech được cập nhật theo thông
báo HID++ từ hidraw; cắm/rút USB được nhận từ udev. Solaar và quét thiết bị USB
vẫn có chu kỳ dự phòng để hoạt động cả khi thiếu quyền hoặc thiếu dịch vụ.
"""

import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib


GLYPHS = {
    "mouse": "\U000f037d",
    "keyboard": "\U000f030c",
    "headset": "\U000f02ce",
    "headphones": "\U000f02cb",
    "gaming": "\U000f02b4",
    "phone": "\U000f03f2",
    "tablet": "\U000f04f6",
    "pen": "\U000f03ea",
    "speakers": "\U000f04c3",
    "other": "\U000f00af",
    "usb": "\U000f0553",
}
CHARGING = "\U000f140b"
BATTERY_LEVELS = {3: 20, 4: 5, 6: 55, 7: 80, 8: 100}
KIND_BY_TYPE = {
    5: "mouse",
    6: "keyboard",
    12: "gaming",
    8: "phone",
    10: "tablet",
    13: "pen",
    17: "headset",
    18: "speakers",
    19: "headphones",
}
KIND_BY_ICON = {
    "input-mouse": "mouse",
    "input-keyboard": "keyboard",
    "audio-headset": "headset",
    "audio-headphones": "headphones",
    "input-gaming": "gaming",
    "phone": "phone",
    "input-tablet": "tablet",
}
GROUPS = {"headset": 0, "headphones": 0, "speakers": 0, "keyboard": 1, "mouse": 2}


def _die_with_parent():
    """preexec_fn: tiến trình con nhận SIGTERM khi script chết (Waybar khởi động lại),
    không thì `nmcli monitor`/`pactl subscribe`/`udevadm monitor` sống mồ côi mãi."""
    try:
        import ctypes
        import signal

        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # 1 = PR_SET_PDEATHSIG
    except Exception:
        pass


def is_hidpp_event(data: bytes) -> bool:
    """Nhận diện thông báo HID++ tự phát, không nhận phản hồi của Solaar."""
    return len(data) >= 4 and data[0] in (0x10, 0x11) and (data[3] & 0x0F) == 0


def _plain(value):
    """Lấy giá trị Python từ Variant hoặc giá trị đã unpack."""
    try:
        return value.unpack()
    except AttributeError:
        return value


def _getall(bus, path, interface, dest="org.freedesktop.UPower"):
    try:
        result = bus.call_sync(
            dest,
            path,
            "org.freedesktop.DBus.Properties",
            "GetAll",
            GLib.Variant("(s)", (interface,)),
            GLib.VariantType("(a{sv})"),
            Gio.DBusCallFlags.NONE,
            3000,
            None,
        )
        return {k: _plain(v) for k, v in _plain(result)[0].items()}
    except Exception:
        return {}


def _kind(value):
    return KIND_BY_TYPE.get(int(value or 0), "other")


def _device(name, kind, percent, charging, source):
    return {
        "name": str(name or "Thiết bị"),
        "kind": kind if kind in GLYPHS else "other",
        "percent": max(0, min(100, int(round(float(percent))))),
        "charging": bool(charging),
        "source": source,
    }


def discover_upower(bus):
    devices = []
    try:
        result = bus.call_sync(
            "org.freedesktop.UPower",
            "/org/freedesktop/UPower",
            "org.freedesktop.UPower",
            "EnumerateDevices",
            None,
            GLib.VariantType("(ao)"),
            Gio.DBusCallFlags.NONE,
            3000,
            None,
        )
        paths = _plain(result)[0]
    except Exception:
        return devices
    for path in paths:
        if path.endswith("DisplayDevice") or "/devices/" not in path:
            continue
        props = _getall(bus, path, "org.freedesktop.UPower.Device")
        if not props:  # không đọc được thuộc tính → bỏ, đừng đoán
            continue
        try:
            if props.get("PowerSupply", False) or int(props.get("Type", 0)) == 1:
                continue
            if "IsPresent" in props and not props["IsPresent"]:
                continue
            name = props.get("Model") or props.get("Vendor") or path.rsplit("/", 1)[-1]
            percent = float(props.get("Percentage", 0.0))
            if percent == 0 and int(props.get("BatteryLevel", 0)) in BATTERY_LEVELS:
                percent = BATTERY_LEVELS[int(props["BatteryLevel"])]
            devices.append(
                _device(name, _kind(props.get("Type")), percent, int(props.get("State", 0)) in (1, 4), "upower")
            )
            devices[-1]["native_path"] = str(props.get("NativePath", ""))
        except (TypeError, ValueError):
            continue
    return devices


def mac_matches(bluez_path, native_path):
    """So khớp MAC trong đường dẫn BlueZ ``dev_AA_BB`` với NativePath UPower."""

    def mac(text):
        found = re.search(r"(?:dev[_/])([0-9A-Fa-f]{2}(?:[_:][0-9A-Fa-f]{2}){5})", text or "")
        return found.group(1).replace("_", ":").lower() if found else ""

    a, b = mac(bluez_path), mac(native_path)
    return bool(a and b and a == b)


def discover_bluez(bus, upower):
    result = []
    try:
        reply = bus.call_sync(
            "org.bluez",
            "/",
            "org.freedesktop.DBus.ObjectManager",
            "GetManagedObjects",
            None,
            None,
            Gio.DBusCallFlags.NONE,
            3000,
            None,
        )
        objects = _plain(reply)[0]
    except Exception:
        return result
    names = {d["name"].casefold() for d in upower}
    for path, interfaces in objects.items():
        props = interfaces.get("org.bluez.Device1")
        if not props or not bool(_plain(props.get("Connected", False))):
            continue
        props = {k: _plain(v) for k, v in props.items()}
        name = str(props.get("Alias") or props.get("Name") or path.rsplit("/", 1)[-1])
        if "org.bluez.Battery1" in interfaces:
            continue
        if name.casefold() in names or any(mac_matches(path, d.get("native_path", "")) for d in upower):
            continue
        result.append({"name": name, "kind": KIND_BY_ICON.get(str(props.get("Icon", "")), "other")})
    return result


def discover_usb(upower):
    result, names = [], {d["name"].casefold() for d in upower}
    for path in glob.glob("/sys/bus/usb/devices/*"):
        product = _read(os.path.join(path, "product"))
        if not product or not glob.glob(path + "/*:*/bInterfaceClass"):
            continue
        if not any(_read(p) == "03" for p in glob.glob(path + "/*:*/bInterfaceClass")):
            continue
        name = product
        if "receiver" in name.casefold():
            manufacturer = _read(os.path.join(path, "manufacturer"))
            if manufacturer:
                name = f"{manufacturer} {name}"
        low = name.casefold()
        kind = "mouse" if "mouse" in low else "keyboard" if "keyboard" in low else "usb"
        if low not in names:
            result.append({"name": name, "kind": kind})
            names.add(name.casefold())
    return result


def parse_solaar(text):
    """Phân tích các khối thiết bị trong đầu ra ``solaar show``."""
    found = []
    current = None
    for line in text.splitlines():
        match = re.match(r"^\s{0,4}(\d+):\s+(.+?)\s*$", line)
        if match:
            if current and current.get("percent") is not None:
                found.append(current)
            current = {"name": match.group(2), "kind": "other", "percent": None, "charging": False}
            continue
        if current is None:
            continue
        kind = re.search(r"Kind\s*:\s*(\w+)", line, re.I)
        battery = re.search(r"Battery\s*:\s*(\d+)%(?:,\s*([\w .]+))?", line, re.I)  # 1.1.x: "BatteryStatus.RECHARGING."
        if kind:
            current["kind"] = kind.group(1).lower() if kind.group(1).lower() in GLYPHS else "other"
        if battery:
            current["percent"] = int(battery.group(1))
            state = (battery.group(2) or "").lower()
            current["charging"] = "charg" in state and "discharg" not in state
    if current and current.get("percent") is not None:
        found.append(current)
    return [_device(d["name"], d["kind"], d["percent"], d["charging"], "solaar") for d in found]


def _read(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return stream.read().strip()
    except OSError:
        return ""


def merge_solaar(upower, solaar):
    """Thêm thiết bị Solaar không trùng tên với danh sách UPower."""
    names = {d["name"].casefold() for d in upower}
    return list(upower) + [d for d in solaar if d["name"].casefold() not in names]


def hide_receivers(nobat, solaar):
    """Solaar đã đọc được thiết bị sau đầu thu Logitech → bỏ dòng "đầu thu: không báo pin"."""
    if not solaar:
        return nobat
    return [d for d in nobat if not ("logitech" in d["name"].casefold() and "receiver" in d["name"].casefold())]


def build(devices, nobat):
    """Tạo JSON Waybar, giữ markup Pango trong text và tooltip."""
    ordered = sorted(devices, key=lambda d: (GROUPS.get(d["kind"], 3), d["name"].casefold()))
    classes = []
    if any(not d["charging"] and d["percent"] <= 20 for d in ordered):
        classes.append("low")
    if any(not d["charging"] and d["percent"] <= 10 for d in ordered):
        classes.append("critical")
    shown = []
    for d in ordered[:3]:
        glyph = GLYPHS.get(d["kind"], GLYPHS["other"])
        number = f"{d['percent']}%"
        if not d["charging"] and d["percent"] <= 10:
            number = f"<span color='#ff6b82'>{number}</span>"
        elif not d["charging"] and d["percent"] <= 20:
            number = f"<span color='#ffe08a'>{number}</span>"
        shown.append(f"{glyph} {number}" + (f" {CHARGING}" if d["charging"] else ""))
    if len(ordered) > 3:
        shown.append(f"+{len(ordered) - 3}")
    text = "  ".join(shown)
    lines = []
    for d in ordered:
        label = html.escape(d["name"], quote=False)
        line = f"{GLYPHS.get(d['kind'], GLYPHS['other'])} {label}: {d['percent']}%"
        lines.append(line + (" (đang sạc)" if d["charging"] else ""))
    for d in nobat:
        lines.append(
            f"{GLYPHS.get(d.get('kind', 'other'), GLYPHS['other'])} {html.escape(d['name'], quote=False)}: không báo pin"
        )
    lines.append("Bấm: bảng Bluetooth · Phải: làm mới")
    return json.dumps(
        {"text": text, "tooltip": "\n".join(lines), "class": classes or (["normal"] if ordered else ["empty"])},
        ensure_ascii=False,
    )


def discover(include_solaar=True):
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    except Exception:
        return [], []
    upower = discover_upower(bus)
    nobat = discover_bluez(bus, upower)
    nobat.extend(discover_usb(upower))
    if include_solaar and shutil.which("solaar"):
        try:
            out = subprocess.run(["solaar", "show"], capture_output=True, text=True, timeout=15).stdout
            solaar = parse_solaar(out)
            upower = merge_solaar(upower, solaar)
            nobat = hide_receivers(nobat, solaar)
        except (OSError, subprocess.SubprocessError):
            pass
    return upower, nobat


class Runner:
    def __init__(self):
        self.loop = GLib.MainLoop()
        self.last = None
        self.refresh_source = 0
        self.lock = threading.Lock()
        self.solaar_devices = []
        self.solaar_lock = threading.Lock()
        self.solaar_running = False
        self.solaar_quiet_until = 0.0
        self.solaar_source = 0
        self.hidraw_sources = {}

    def emit(self):
        devices, nobat = discover(False)
        devices = merge_solaar(devices, self.solaar_devices)
        nobat = hide_receivers(nobat, self.solaar_devices)
        line = build(devices, nobat)
        with self.lock:
            if line == self.last:
                return False
            self.last = line
        try:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except BrokenPipeError:
            os._exit(0)
        return False

    def refresh_solaar(self):
        """Chạy một lần ``solaar show`` ngoài main loop."""
        with self.solaar_lock:
            if self.solaar_running:
                return
            self.solaar_running = True
        try:
            if not shutil.which("solaar"):
                return
            try:
                output = subprocess.run(["solaar", "show"], capture_output=True, text=True, timeout=15).stdout
                GLib.idle_add(self.set_solaar, parse_solaar(output))
            except (OSError, subprocess.SubprocessError):
                pass
        finally:
            with self.solaar_lock:
                self.solaar_running = False
                self.solaar_quiet_until = time.monotonic() + 3.0

    def request_solaar(self, delay=0):
        """Hẹn một lần đọc Solaar, gộp các thông báo HID++ liên tiếp."""
        if self.solaar_source:
            GLib.source_remove(self.solaar_source)
        self.solaar_source = GLib.timeout_add(delay, self._start_solaar)

    def _start_solaar(self):
        self.solaar_source = 0
        threading.Thread(target=self.refresh_solaar, daemon=True).start()
        return False

    def _solaar_fallback(self):
        """Đọc Solaar dự phòng mỗi 300 giây, kể cả khi nó được cài sau đó."""
        while True:
            # Đưa thao tác tạo timeout về main context của GLib.
            GLib.idle_add(self._start_solaar)
            time.sleep(300)

    def set_solaar(self, devices):
        self.solaar_devices = devices
        self.emit()
        return False

    def schedule(self, delay=300):
        """Gộp loạt sự kiện: chỉ giữ một lần làm mới sau `delay` ms."""
        if self.refresh_source:
            GLib.source_remove(self.refresh_source)
        self.refresh_source = GLib.timeout_add(delay, self._scheduled)

    def _scheduled(self):
        self.refresh_source = 0
        self.emit()
        return False

    def _tick(self):
        """Quét dự phòng; sự kiện udev mới là nguồn chính cho USB."""
        self.emit()
        return True

    def signal(self, *_args):
        self.schedule()
        self.request_solaar()
        return True

    def _hidraw_paths(self):
        """Tìm các hidraw Logitech có tên Receiver mà không cần pyudev."""
        paths = []
        for uevent in glob.glob("/sys/class/hidraw/hidraw*/device/uevent"):
            values = {}
            for line in _read(uevent).splitlines():
                key, sep, value = line.partition("=")
                if sep:
                    values[key] = value
            desc = b""
            try:
                with open(os.path.join(os.path.dirname(uevent), "report_descriptor"), "rb") as f:
                    desc = f.read()
            except OSError:
                pass
            # chỉ kênh HID++ (có report id 0x10/0x11); kênh chuột/bàn phím thường thì bỏ, khỏi bị đánh thức mỗi lần rê chuột
            if (
                values.get("HID_ID", "").upper().startswith("0003:0000046D:")
                and "receiver" in values.get("HID_NAME", "").casefold()
                and (b"\x85\x10" in desc or b"\x85\x11" in desc)
            ):
                node = os.path.basename(os.path.dirname(os.path.dirname(uevent)))
                paths.append(os.path.join("/dev", node))
        return paths

    def close_hidraw(self):
        for fd, source in list(self.hidraw_sources.items()):
            GLib.source_remove(source)
            try:
                os.close(fd)
            except OSError:
                pass
        self.hidraw_sources.clear()

    def open_hidraw(self):
        """Mở lại watch khi đầu thu được cắm lại hoặc đổi số hidraw."""
        self.close_hidraw()
        for path in self._hidraw_paths():
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            try:
                source = GLib.unix_fd_add_full(
                    GLib.PRIORITY_DEFAULT,
                    fd,
                    GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR,
                    self._hidraw_io,
                    None,
                )
            except (AttributeError, TypeError, ValueError):
                os.close(fd)
                continue
            self.hidraw_sources[fd] = source

    def _hidraw_io(self, fd, condition, _data):
        if condition & (GLib.IOCondition.HUP | GLib.IOCondition.ERR):
            self._remove_hidraw(fd)
            return False
        while True:
            try:
                data = os.read(fd, 64)
            except BlockingIOError:
                break
            except OSError:
                self._remove_hidraw(fd)
                return False
            if not data:
                self._remove_hidraw(fd)
                return False
            if is_hidpp_event(data):
                with self.solaar_lock:
                    quiet = self.solaar_running or time.monotonic() < self.solaar_quiet_until
                if not quiet:
                    self.request_solaar(1500)
        return True

    def _remove_hidraw(self, fd):
        source = self.hidraw_sources.pop(fd, 0)
        if source:
            GLib.source_remove(source)
        try:
            os.close(fd)
        except OSError:
            pass

    def _udev_event(self):
        """Xử lý sự kiện udev trong main loop, nơi được phép sửa các watch."""
        self.schedule(800)
        self.open_hidraw()
        self.request_solaar(2000)
        return False

    def monitor_udev(self):
        """Theo dõi add/remove/bind; nếu udev chết thì tự khởi động lại."""
        while True:
            process = None
            try:
                process = subprocess.Popen(
                    ["udevadm", "monitor", "--udev", "--subsystem-match=usb", "--subsystem-match=hidraw"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                    preexec_fn=_die_with_parent,
                )
                for line in process.stdout:
                    if any(f" {word} " in line for word in ("add", "remove", "bind")):
                        GLib.idle_add(self._udev_event)
            except (OSError, subprocess.SubprocessError):
                pass
            finally:
                if process is not None:
                    try:
                        process.kill()
                    except OSError:
                        pass
            time.sleep(5)

    def setup_signals(self):
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            flags = Gio.DBusSignalFlags.MATCH_ARG0_NAMESPACE | Gio.DBusSignalFlags.MATCH_PATH_NAMESPACE
            bus.signal_subscribe(
                "org.freedesktop.UPower",
                "org.freedesktop.UPower",
                "DeviceAdded",
                None,
                None,
                Gio.DBusSignalFlags.NONE,
                self.signal,
                None,
            )
            bus.signal_subscribe(
                "org.freedesktop.UPower",
                "org.freedesktop.UPower",
                "DeviceRemoved",
                None,
                None,
                Gio.DBusSignalFlags.NONE,
                self.signal,
                None,
            )
            bus.signal_subscribe(
                None,
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                "/org/freedesktop/UPower/devices",
                "org.freedesktop.UPower.Device",
                flags,
                self.signal,
                None,
            )
            for member in ("InterfacesAdded", "InterfacesRemoved"):
                bus.signal_subscribe(
                    "org.bluez",
                    "org.freedesktop.DBus.ObjectManager",
                    member,
                    "/",
                    None,
                    Gio.DBusSignalFlags.MATCH_PATH_NAMESPACE,
                    self.signal,
                    None,
                )
            bus.signal_subscribe(
                "org.bluez",
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                "/",
                "org.bluez.Device1",
                flags,
                self.signal,
                None,
            )
        except Exception:
            pass

    def run(self):
        self.emit()
        self.setup_signals()
        self.open_hidraw()
        self.request_solaar()
        threading.Thread(target=self._solaar_fallback, daemon=True).start()
        threading.Thread(target=self.monitor_udev, daemon=True).start()
        GLib.timeout_add_seconds(120, self._tick)
        try:  # SIGUSR1 = làm mới ngay (nút chuột phải trên Waybar)
            gi.require_version("GLibUnix", "2.0")
            from gi.repository import GLibUnix

            GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, 10, self.signal)
        except (ImportError, ValueError, AttributeError, TypeError):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 10, self.signal)
        self.loop.run()


def selftest():
    assert is_hidpp_event(bytes([0x11, 0x02, 0x07, 0x00] + [0] * 16))
    assert not is_hidpp_event(bytes([0x11, 0x02, 0x07, 0x1A] + [0] * 16))
    assert is_hidpp_event(bytes([0x10, 0x02, 0x41, 0x00, 0, 0, 0]))
    assert not is_hidpp_event(bytes([0x02, 0, 0, 0]))
    assert not is_hidpp_event(bytes([0, 0, 0]))
    sample = """Bolt Receiver
  Device path  : /dev/hidraw3
  1: MX Keys S
     Kind         : keyboard
     Battery: 70%, discharging.
  2: MX Master 3S
     Kind         : mouse
     Battery: 15%, recharging.
"""
    parsed = parse_solaar(sample)
    assert len(parsed) == 2 and parsed[0]["percent"] == 70 and not parsed[0]["charging"]
    assert parsed[0]["kind"] == "keyboard" and parsed[1]["charging"]
    assert json.loads(build([], []))["text"] == ""
    four = [
        _device("A&B", "mouse", 10, False, "x"),
        _device("B", "keyboard", 20, False, "x"),
        _device("C", "headset", 50, False, "x"),
        _device("D", "other", 90, False, "x"),
    ]
    built = json.loads(build(four, []))
    assert (
        "+1" in built["text"]
        and "#ff6b82" in built["text"]
        and "#ffe08a" in built["text"]
        and "A&amp;B" in built["tooltip"]
    )
    real = parse_solaar(
        "  2: Signature M650 L\n     Kind         : mouse\n"
        "            Battery: 100%, BatteryStatus.DISCHARGING.\n"
        "                 1: BL1 38.10.B0014\n        10: XY STATS   {2250} V1\n"
        "  3: K380\n     Battery: 40%, BatteryStatus.RECHARGING.\n"
    )
    assert [(d["name"], d["percent"], d["charging"]) for d in real] == [
        ("Signature M650 L", 100, False),
        ("K380", 40, True),
    ], real
    assert hide_receivers([{"name": "Logitech USB Receiver"}, {"name": "X"}], real) == [{"name": "X"}]
    up = [_device("MX Master 3S", "mouse", 50, False, "upower")]
    assert len(merge_solaar(up, parse_solaar("1: MX Master 3S\n Battery: 50%"))) == 1
    assert mac_matches("/org/bluez/hci0/dev_41_A3_4C_1A_94_BA", "/org/bluez/hci0/dev_41:A3:4C:1A:94:BA")
    print("device-battery.py selftest OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--json" in sys.argv:
        print(json.dumps(discover()[0], ensure_ascii=False, indent=2))
        sys.exit(0)
    if "--once" in sys.argv:
        print(build(*discover()))
        sys.exit(0)
    Runner().run()
