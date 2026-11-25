#!/usr/bin/env python3
"""Daemon cảnh báo pin, sóng Wi-Fi và kết nối Internet cho Kafka's Web."""

import ctypes
import errno
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time


DEFAULTS = {
    "battery": {"enabled": True, "levels": [80, 50, 30, 15], "critical": 15},
    "devices": {"enabled": True, "levels": [30, 15], "critical": 10},
    "wifi_signal": {"enabled": True, "levels": [40, 20]},
    "internet": {"enabled": True, "grace_seconds": 20},
    # bảng cảnh báo giữa màn hình kiểu game (alert-popup.py) + âm thanh; tắt = chỉ thông báo dunst
    "popup": {"enabled": True, "sound": True, "volume": 80, "seconds": 10},
}
POPUP = os.path.join(os.path.dirname(os.path.realpath(__file__)), "alert-popup.py")
POPUP_KIND = {"battery": "battery", "devices": "device", "wifi": "wifi", "internet": "internet"}
RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
PID_FILE = os.path.join(RUNTIME, "kafka-alert-watch.pid")
LOCK_FILE = os.path.join(RUNTIME, "kafka-alert-watch.lock")
SELF_DIR = os.path.dirname(os.path.realpath(__file__))
CONFIG_FILE = os.environ.get("KAFKA_ALERTS_CONFIG", os.path.join(SELF_DIR, "..", "alerts.json"))


def _log(message):
    try:
        print("alert-watch.py: " + message, file=sys.stderr)
    except Exception:
        pass


def _read(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return stream.read().strip()
    except OSError:
        return ""


def _run(command, timeout=5):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _die_with_parent():
    """Cho tiến trình con nhận SIGTERM khi daemon cha kết thúc."""
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)
    except Exception:
        pass


def _copy_defaults():
    return json.loads(json.dumps(DEFAULTS))


def load_config(path=CONFIG_FILE):
    config = _copy_defaults()
    try:
        with open(path, encoding="utf-8") as stream:
            raw = json.load(stream)
    except (OSError, ValueError, TypeError):
        return config
    if not isinstance(raw, dict):
        return config
    for name, default in DEFAULTS.items():
        value = raw.get(name)
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("enabled"), bool):
            config[name]["enabled"] = value["enabled"]
        if "levels" in default:
            levels = value.get("levels")
            if (
                isinstance(levels, list)
                and levels
                and all(isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 99 for x in levels)
            ):
                config[name]["levels"] = sorted(set(levels), reverse=True)
            if (
                "critical" in default
                and isinstance(value.get("critical"), int)
                and not isinstance(value.get("critical"), bool)
                and 0 <= value["critical"] <= 99
            ):  # 0 = không bao giờ khẩn cấp
                config[name]["critical"] = value["critical"]
        elif name == "popup":
            for key in ("enabled", "sound"):
                if isinstance(value.get(key), bool):
                    config[name][key] = value[key]
            for key, lo, hi in (("volume", 0, 100), ("seconds", 3, 120)):
                v = value.get(key)
                if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi:
                    config[name][key] = v
        elif name == "internet":
            grace = value.get("grace_seconds")
            if isinstance(grace, (int, float)) and not isinstance(grace, bool) and grace >= 0:
                config[name]["grace_seconds"] = grace
    return config


class LevelTracker:
    """Theo dõi các mốc giảm dần và tự tái vũ trang bằng hysteresis."""

    def __init__(self, levels, hysteresis):
        self.levels = sorted(set(int(x) for x in levels), reverse=True)
        self.hysteresis = hysteresis
        self.armed = set(self.levels)
        self.previous = None

    def update(self, value, active=True):
        if not active:
            self.armed = set(self.levels)
            self.previous = None
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        for level in self.levels:
            if value > level + self.hysteresis:
                self.armed.add(level)
        old = self.previous
        self.previous = value
        crossed = [
            level for level in self.levels if level in self.armed and value <= level and (old is None or old > level)
        ]
        if not crossed:
            return None
        lowest = min(crossed)
        for level in crossed:
            self.armed.discard(level)
        return lowest


def parse_wireless(text):
    for line in text.splitlines()[2:]:
        fields = line.split()
        if len(fields) >= 3:
            try:
                quality = float(fields[2].rstrip("."))
                return max(0, min(100, int(quality * 100 / 70)))
            except ValueError:
                pass
    return None


def wifi_connected():
    for line in _run(["nmcli", "-t", "-f", "TYPE,STATE", "device"]).splitlines():
        kind, sep, state = line.partition(":")
        if sep and kind == "wifi" and state == "connected":
            return True
    return False


def read_wifi():
    if not wifi_connected():
        return None, False
    return parse_wireless(_read("/proc/net/wireless")), True


def read_battery(sys_root="/sys/class/power_supply"):
    batteries = []
    try:
        names = sorted(os.listdir(sys_root))
    except OSError:
        return None, "Unknown"
    for name in names:
        base = os.path.join(sys_root, name)
        if _read(os.path.join(base, "type")) != "Battery":
            continue
        try:
            percent = float(_read(os.path.join(base, "capacity")))
        except ValueError:
            continue
        status = _read(os.path.join(base, "status")) or "Unknown"
        weight = None
        for filename in ("energy_full", "charge_full"):
            try:
                weight = float(_read(os.path.join(base, filename)))
                if weight > 0:
                    break
            except ValueError:
                weight = None
        batteries.append((max(0, min(100, percent)), status, weight))
    if not batteries:
        return None, "Unknown"
    weighted = [(p, w) for p, _, w in batteries if w]
    if weighted:
        percent = sum(p * w for p, w in weighted) / sum(w for _, w in weighted)
    else:
        percent = sum(p for p, _, _ in batteries) / len(batteries)
    statuses = [status for _, status, _ in batteries]
    status = "Discharging" if "Discharging" in statuses else statuses[0]
    return int(round(percent)), status


def read_devices():
    script = os.path.join(SELF_DIR, "device-battery.py")
    try:
        result = subprocess.run([sys.executable, script, "--json"], capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else []
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def connectivity():
    value = _run(["nmcli", "-t", "networking", "connectivity"], timeout=4).strip().splitlines()
    return value[0] if value else "unknown"


def intentionally_offline():
    radio = _run(["nmcli", "radio", "wifi"], timeout=4).strip().lower()
    if radio != "disabled":
        return False
    for line in _run(["nmcli", "-t", "-f", "TYPE,STATE", "device"], timeout=4).splitlines():
        kind, sep, state = line.partition(":")
        if sep and kind in ("wifi", "ethernet", "gsm") and state == "connected":
            return False
    return True


def battery_time():
    for line in _run(["upower", "-e"], timeout=4).splitlines():
        if "battery" not in line.lower() and "bat" not in line.lower():
            continue
        info = _run(["upower", "-i", line.strip()], timeout=4)
        match = re.search(r"time to empty:\s*([0-9.]+)\s*(hours?|minutes?)", info, re.I)
        if match:
            minutes = float(match.group(1)) * (60 if match.group(2).lower().startswith("hour") else 1)
            return f"{int(minutes // 60)} giờ {int(minutes % 60)} phút"
    return ""


POPUP_CONFIG = dict(DEFAULTS["popup"])  # daemon cập nhật khi nạp cấu hình (set_popup_config)


def set_popup_config(config):
    POPUP_CONFIG.clear()
    POPUP_CONFIG.update(config.get("popup", DEFAULTS["popup"]))


def popup_args(category, title, body, urgency, popup, value=None, device_kind=""):
    level = {"critical": "critical", "low": "ok"}.get(urgency, "warn")
    args = [
        sys.executable,
        POPUP,
        "--title",
        title,
        "--body",
        body,
        "--level",
        level,
        "--kind",
        POPUP_KIND.get(category, "test"),
        "--seconds",
        str(popup["seconds"]),
        "--volume",
        str(popup["volume"]),
    ]
    if value is not None:
        args += ["--value", str(int(round(value)))]
    if device_kind:
        args += ["--device-kind", device_kind]
    return args + (["--sound"] if popup["sound"] else [])


def notify(
    category, title, body, urgency="normal", icon="dialog-warning", device=None, sender=None, value=None, device_kind=""
):
    if sender is not None:
        sender(category, title, body, urgency, icon, device)
        return
    tag = "kafka-alert-" + category + ("-" + device.replace(" ", "-") if device else "")
    popup = POPUP_CONFIG.get("enabled") and os.path.exists(POPUP)
    if popup:
        try:  # bảng giữa màn hình + âm thanh; không chờ (bảng tự đóng/xếp hàng)
            subprocess.Popen(
                popup_args(category, title, body, urgency, POPUP_CONFIG, value, device_kind),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            popup = False
    # vẫn gửi dunst để có trong lịch sử; khi đã hiện bảng thì rule `kafka.alert.popup` trong dunstrc giấu hộp dunst
    extra = ["-c", "kafka.alert.popup"] if popup else []
    try:
        subprocess.run(
            ["notify-send", "-a", "Kafka Alerts", "-u", urgency, "-i", icon, "-h", "string:x-dunst-stack-tag:" + tag]
            + extra
            + [title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def icon_for(percent):
    return "battery-empty" if percent <= 15 else "battery-low" if percent <= 30 else "battery-caution"


def wifi_pending_update(pending, level, percent):
    """Đếm hai mẫu Wi-Fi liên tiếp dưới cùng một mốc."""
    if level is not None:
        pending[level] = 1
    fired = []
    for pending_level in list(pending):
        if percent > pending_level:  # sóng hồi lại -> mẫu yếu trước đó không còn "liên tiếp"
            del pending[pending_level]
            continue
        if pending_level != level:
            pending[pending_level] += 1
        if pending[pending_level] >= 2:
            fired.append(pending_level)
            del pending[pending_level]
    return fired


class AlertDaemon:
    def __init__(self, config):
        self.config = config
        self.wake = threading.Event()
        self.stop = False
        self.battery_tracker = LevelTracker(config["battery"]["levels"], 3)
        self.wifi_tracker = LevelTracker(config["wifi_signal"]["levels"], 5)
        self.devices = {}
        self.last_battery = 0
        self.last_devices = 0
        self.last_wifi = 0
        self.last_internet = 0
        self.bad_since = None
        self.internet_alerted = False
        self.wifi_pending = {}

    def reload(self):
        old, self.config = self.config, load_config()
        set_popup_config(self.config)
        # chỉ dựng lại bộ đếm khi mốc đổi: lưu cấu hình (Studio) không làm báo lại mốc đã báo
        if self.config["battery"]["levels"] != old["battery"]["levels"]:
            self.battery_tracker = LevelTracker(self.config["battery"]["levels"], 3)
        if self.config["wifi_signal"]["levels"] != old["wifi_signal"]["levels"]:
            self.wifi_tracker = LevelTracker(self.config["wifi_signal"]["levels"], 5)
            self.wifi_pending.clear()
        if self.config["devices"]["levels"] != old["devices"]["levels"]:
            self.devices.clear()
        self.wake.set()

    def battery_check(self):
        percent, status = read_battery()
        if percent is None:
            return
        level = self.battery_tracker.update(percent, status == "Discharging")
        if level is not None and self.config["battery"]["enabled"]:
            remaining = battery_time()
            body = f"Đang dùng pin — còn khoảng {remaining}" if remaining else "Đang dùng pin"
            urgency = "critical" if level <= self.config["battery"]["critical"] else "normal"
            notify("battery", f"Pin còn {level}%", body, urgency, icon_for(level), value=percent)

    def device_check(self):
        found = read_devices()
        current = set()
        for item in found:
            try:
                name, percent = str(item["name"]), float(item["percent"])
            except (KeyError, TypeError, ValueError):
                continue
            current.add(name)
            tracker = self.devices.setdefault(name, LevelTracker(self.config["devices"]["levels"], 3))
            level = tracker.update(percent, not bool(item.get("charging", False)))
            if level is not None and self.config["devices"]["enabled"]:
                urgency = "critical" if level <= self.config["devices"]["critical"] else "normal"
                notify(
                    "devices",
                    f"Pin {name} còn {level}%",
                    "Thiết bị ngoại vi đang sắp hết pin — nhớ sạc",
                    urgency,
                    icon_for(level),
                    name,
                    value=percent,
                    device_kind=str(item.get("kind") or ""),
                )
        for name in set(self.devices) - current:
            del self.devices[name]

    def wifi_check(self):
        percent, connected = read_wifi()
        level = self.wifi_tracker.update(percent, connected and percent is not None)
        if not connected or percent is None:
            self.wifi_pending.clear()
        if connected and percent is not None and self.config["wifi_signal"]["enabled"]:
            for _ in wifi_pending_update(self.wifi_pending, level, percent):
                notify(
                    "wifi",
                    f"Sóng Wi-Fi yếu ({int(percent)}%)",
                    "Kết nối có thể chậm hoặc chập chờn — lại gần router",
                    "normal",
                    "network-wireless-offline",
                    value=percent,
                )

    def internet_check(self):
        state = connectivity()
        now = time.monotonic()
        if state == "full":
            if self.internet_alerted and self.config["internet"]["enabled"]:
                notify(
                    "internet",
                    "Đã có Internet trở lại",
                    "Kết nối Internet đã được khôi phục",
                    "low",
                    "network-transmit-receive",
                )
            self.bad_since, self.internet_alerted = None, False
            return
        if intentionally_offline():
            self.bad_since, self.internet_alerted = None, False
            return
        if self.bad_since is None:
            self.bad_since = now
        if (
            not self.internet_alerted
            and now - self.bad_since >= self.config["internet"]["grace_seconds"]
            and self.config["internet"]["enabled"]
        ):
            detail = state if state in ("limited", "portal", "none") else "không rõ trạng thái"
            notify("internet", "Mất kết nối Internet", f"Trạng thái kết nối: {detail}", "normal", "network-offline")
            self.internet_alerted = True

    def run(self):
        def udev():
            while not self.stop:
                try:
                    process = subprocess.Popen(
                        ["udevadm", "monitor", "--udev", "--subsystem-match=power_supply"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        preexec_fn=_die_with_parent,
                    )
                    for _ in process.stdout:
                        self.wake.set()
                        if self.stop:
                            break
                except (OSError, AttributeError):
                    pass
                if not self.stop:
                    time.sleep(5)

        threading.Thread(target=udev, daemon=True).start()
        mtime = None
        while not self.stop:
            try:
                current_mtime = os.stat(CONFIG_FILE).st_mtime_ns
                if mtime is not None and current_mtime != mtime:
                    self.reload()
                mtime = current_mtime
            except OSError:
                pass
            now = time.monotonic()
            if now - self.last_battery >= 30:
                self.battery_check()
                self.last_battery = now
            if now - self.last_devices >= 300:
                self.device_check()
                self.last_devices = now
            if now - self.last_wifi >= 30:
                self.wifi_check()
                self.last_wifi = now
            if now - self.last_internet >= 15:
                self.internet_check()
                self.last_internet = now
            self.wake.wait(5)
            self.wake.clear()


def snapshot(config):
    battery, status = read_battery()
    wifi, connected = read_wifi()
    return {
        "battery": {"percent": battery, "status": status},
        "devices": read_devices(),
        "wifi": {"percent": wifi, "connected": connected},
        "connectivity": connectivity(),
        "config": config,
    }


def test_notifications(config):
    samples = [
        (
            "battery",
            "Pin còn 50%",
            "[Thử] Đang dùng pin — còn khoảng 2 giờ 10 phút",
            "normal",
            "battery-caution",
            None,
            48,
            "",
        ),
        (
            "devices",
            "Pin Signature M650 còn 30%",
            "[Thử] Thiết bị ngoại vi đang sắp hết pin — nhớ sạc",
            "normal",
            "battery-low",
            "Thu",
            27,
            "mouse",
        ),
        (
            "wifi",
            "Sóng Wi-Fi yếu (35%)",
            "[Thử] Kết nối có thể chậm hoặc chập chờn — lại gần router",
            "normal",
            "network-wireless-offline",
            None,
            35,
            "",
        ),
        (
            "internet",
            "Mất kết nối Internet",
            "[Thử] Trạng thái kết nối: none",
            "normal",
            "network-offline",
            None,
            None,
            "",
        ),
    ]
    for name, title, body, urgency, icon, device, value, dkind in samples:
        if config[name if name != "wifi" else "wifi_signal"]["enabled"]:
            notify(name, title, body, urgency, icon, device, value=value, device_kind=dkind)


def selftest():
    tracker = LevelTracker([80, 50, 30, 15], 3)
    assert [tracker.update(x) for x in (85, 79, 49, 29)] == [None, 80, 50, 30]
    assert [LevelTracker([80, 50, 30, 15], 3).update(25)] == [30]
    tracker = LevelTracker([30], 3)
    assert (
        tracker.update(29) == 30
        and tracker.update(28) is None
        and tracker.update(34) is None
        and tracker.update(29) == 30
    )
    assert tracker.update(20, False) is None and tracker.update(19) == 30
    wifi = LevelTracker([40], 5)
    assert wifi.update(45) is None and wifi.update(40) == 40
    pending = {}
    assert wifi_pending_update(pending, 40, 40) == []
    assert wifi_pending_update(pending, None, 39) == [40]
    pending = {}
    assert wifi_pending_update(pending, 40, 38) == [] and wifi_pending_update(pending, None, 42) == [] and pending == {}
    d = AlertDaemon(load_config(os.devnull))
    d.battery_tracker.update(45)
    t = d.battery_tracker
    import unittest.mock as _m

    with _m.patch(__name__ + ".load_config", return_value=_copy_defaults()):
        d.reload()
    assert d.battery_tracker is t and t.update(44) is None
    sample = "Inter-| sta-|   Quality        |\n face | tus | link level noise |\nwlp0s20f3: 0000   52.  -58.  -256 ..."
    assert parse_wireless(sample) == 74
    with tempfile.TemporaryDirectory() as root:
        os.mkdir(os.path.join(root, "BAT0"))
        for filename, value in (
            ("type", "Battery"),
            ("capacity", "80"),
            ("status", "Discharging"),
            ("energy_full", "100"),
        ):
            with open(os.path.join(root, "BAT0", filename), "w", encoding="utf-8") as f:
                f.write(value)
        os.mkdir(os.path.join(root, "BAT1"))
        for filename, value in (
            ("type", "Battery"),
            ("capacity", "40"),
            ("status", "Discharging"),
            ("energy_full", "300"),
        ):
            with open(os.path.join(root, "BAT1", filename), "w", encoding="utf-8") as f:
                f.write(value)
        assert read_battery(root) == (50, "Discharging")
        broken = os.path.join(root, "broken.json")
        with open(broken, "w", encoding="utf-8") as f:
            f.write('{"battery":{"levels":[15, 80, 15, 50]}}')
        cfg = load_config(broken)
        assert cfg["battery"]["levels"] == [80, 50, 15] and cfg["devices"] == DEFAULTS["devices"]
    a = popup_args("devices", "T", "B", "normal", {"seconds": 9, "volume": 50, "sound": False}, 27.4, "mouse")
    assert a[a.index("--value") + 1] == "27" and a[a.index("--device-kind") + 1] == "mouse"
    a = popup_args("battery", "T", "B", "critical", {"seconds": 9, "volume": 50, "sound": True})
    assert a[a.index("--level") + 1] == "critical" and a[a.index("--kind") + 1] == "battery" and a[-1] == "--sound"
    assert popup_args("internet", "T", "B", "low", {"seconds": 9, "volume": 50, "sound": False})[-1] == "50"
    with tempfile.TemporaryDirectory() as root:
        f = os.path.join(root, "a.json")
        with open(f, "w", encoding="utf-8") as h:
            h.write('{"popup": {"enabled": false, "volume": 300, "seconds": 5}}')
        c = load_config(f)["popup"]
        assert c == {"enabled": False, "sound": True, "volume": 80, "seconds": 5}, c
    print("alert-watch.py selftest OK")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    config = load_config()
    set_popup_config(config)
    if "--status" in argv:
        print(json.dumps(snapshot(config), ensure_ascii=False))
        return 0
    if "--test" in argv:
        test_notifications(config)
        return 0
    if "--reload" in argv:
        try:
            os.kill(int(_read(PID_FILE)), signal.SIGUSR1)
            return 0
        except (OSError, ValueError):
            print("Không tìm thấy daemon đang chạy", file=sys.stderr)
            return 1
    if not argv or argv[0] != "daemon":
        print("Cách dùng: daemon | --status | --test | --reload | --selftest", file=sys.stderr)
        return 1
    os.makedirs(RUNTIME, exist_ok=True)
    lock = open(LOCK_FILE, "w", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in (errno.EACCES, errno.EAGAIN):
            print("Daemon đã đang chạy")
            return 0
        raise
    with open(PID_FILE, "w", encoding="utf-8") as pid:
        pid.write(str(os.getpid()))
    daemon = AlertDaemon(config)

    def stop(_signum, _frame):
        daemon.stop = True
        daemon.wake.set()

    def reload_config(_signum, _frame):
        daemon.reload()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGUSR1, reload_config)
    try:
        daemon.run()
    except Exception as error:
        _log(f"lỗi vòng lặp: {error}")
    finally:
        try:
            os.unlink(PID_FILE)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
