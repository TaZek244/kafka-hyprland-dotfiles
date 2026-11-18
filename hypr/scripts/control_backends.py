#!/usr/bin/env python3
"""Backend đồng bộ cho popup Trung tâm điều khiển."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
import sys
from pathlib import Path
from typing import Any

_TIMEOUT = 8
_ERR = "Không thực hiện được"


def _run(args: list[str], timeout: int = _TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _ok(proc: subprocess.CompletedProcess[str]) -> tuple[bool, str]:
    if proc.returncode == 0:
        return True, "OK"
    return False, (proc.stderr or proc.stdout or _ERR).strip()[:160]


def _nm_unescape(value: str) -> str:
    out, i = [], 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            out.append(value[i + 1]); i += 2
        else:
            out.append(value[i]); i += 1
    return "".join(out)


def _nm_fields(line: str, count: int = 4) -> list[str]:
    fields, current, escaped = [], [], False
    for ch in line.rstrip("\n"):
        if escaped:
            current.extend(("\\", ch)); escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":" and len(fields) < count - 1:
            fields.append("".join(current)); current = []
        else:
            current.append(ch)
    if escaped: current.append("\\")
    fields.append("".join(current))
    return fields


def parse_nmcli_wifi(text: str, known_names: set[str] | list[str] | None = None) -> list[dict[str, Any]]:
    """Parse nmcli terse wifi output and merge duplicate SSIDs."""
    try:
        known = set(known_names or ())
        merged: dict[str, dict[str, Any]] = {}
        for raw in text.splitlines():
            if not raw.strip(): continue
            f = _nm_fields(raw, 4)
            if len(f) < 4: continue
            active, ssid, strength, security = f
            ssid, security = _nm_unescape(ssid), _nm_unescape(security)
            if not ssid: continue
            try: power = max(0, min(100, int(strength)))
            except ValueError: continue
            item = {"ssid": ssid, "strength": power, "secure": bool(security and security != "--"),
                    "active": active.strip() == "*", "known": ssid in known}
            old = merged.get(ssid)
            if old is None or (item["active"], item["strength"]) > (old["active"], old["strength"]):
                item["active"] = item["active"] or bool(old and old["active"])
                item["known"] = item["known"] or bool(old and old["known"])
                merged[ssid] = item
            else:
                old["active"] |= item["active"]; old["known"] |= item["known"]
                old["secure"] |= item["secure"]
        return sorted(merged.values(), key=lambda x: (not x["active"], -x["strength"], x["ssid"]))
    except Exception:
        return []


def _unwrap_busctl(value: Any) -> Any:
    if isinstance(value, dict) and "data" in value and "type" in value:
        return _unwrap_busctl(value["data"])
    if isinstance(value, dict): return {k: _unwrap_busctl(v) for k, v in value.items()}
    if isinstance(value, list): return [_unwrap_busctl(v) for v in value]
    return value


def parse_bluez_busctl(sample: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """Đổi wrapper JSON của busctl thành cấu trúc GetManagedObjects."""
    try:
        data = sample.get("data", sample)
        if isinstance(data, list) and len(data) == 1: data = data[0]
        return {str(path): {str(iface): _unwrap_busctl(props) for iface, props in ifaces.items()}
                for path, ifaces in data.items()}
    except Exception:
        return {}


def parse_bluez_objects(objects: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    try:
        adapters = [(p, i) for p, x in objects.items() if (i := x.get("org.bluez.Adapter1")) is not None]
        devices = []
        for path, ifaces in objects.items():
            d = ifaces.get("org.bluez.Device1")
            if not d or (not d.get("Name") and not d.get("Alias")) or not d.get("Paired", False): continue
            battery = ifaces.get("org.bluez.Battery1", {}).get("Percentage")
            devices.append({"path": path, "address": d.get("Address", ""), "name": d.get("Name") or d.get("Alias", ""),
                            "icon": d.get("Icon", "bluetooth"), "paired": bool(d.get("Paired")),
                            "connected": bool(d.get("Connected")), "trusted": bool(d.get("Trusted")),
                            "battery": int(battery) if battery is not None else None})
        devices.sort(key=lambda d: (not d["connected"], not d["paired"], d["name"].casefold()))
        adapter = adapters[0][1] if adapters else {}
        return {"available": bool(adapters), "powered": bool(adapter.get("Powered", False)),
                "discovering": bool(adapter.get("Discovering", False)), "devices": devices}
    except Exception:
        return {"available": False, "powered": False, "discovering": False, "devices": []}


def parse_pactl_devices(json_text: str, default_name: str | None = None, kind: str = "output") -> list[dict[str, Any]]:
    try:
        raw = json.loads(json_text)
        result = []
        for item in raw if isinstance(raw, list) else []:
            name = str(item.get("name", ""))
            # Monitor không phải thiết bị để hiển thị trong popup.
            if ".monitor" in name: continue
            vol = item.get("volume") or {}
            vals = [v.get("value_percent", "0%").rstrip("%") for v in vol.values() if isinstance(v, dict)]
            try: percent = round(sum(int(float(v)) for v in vals) / len(vals)) if vals else 0
            except (ValueError, TypeError): percent = 0
            props = item.get("properties") or {}
            result.append({"name": name, "description": item.get("description", name), "default": name == default_name,
                           "volume": max(0, min(150, percent)), "muted": bool(item.get("mute", False))})
        return result
    except Exception: return []


def parse_pactl_streams(json_text: str) -> list[dict[str, Any]]:
    try:
        out = []
        for x in json.loads(json_text):
            vals = [v.get("value_percent", "0%").rstrip("%") for v in (x.get("volume") or {}).values()]
            out.append({"index": int(x.get("index", 0)), "app": (x.get("properties") or {}).get("application.name", ""),
                        "icon": (x.get("properties") or {}).get("application.icon_name"),
                        "volume": int(float(vals[0])) if vals else 0, "muted": bool(x.get("mute", False))})
        return out
    except Exception: return []


def parse_brightness(text: str) -> int:
    try:
        m = re.search(r"(?:^|,)\s*(\d{1,3})%", text)
        return max(0, min(100, int(m.group(1)))) if m else 0
    except Exception: return 0


def parse_upower(text: str) -> dict[str, Any]:
    result = {"present": False, "percent": None, "state": "unknown", "time": None}
    try:
        result["present"] = bool(re.search(r"^\s*present:\s*yes", text, re.M | re.I))
        m = re.search(r"^\s*percentage:\s*(\d+)%", text, re.M | re.I)
        if m: result["percent"] = max(0, min(100, int(m.group(1))))
        state = re.search(r"^\s*state:\s*(\S+)", text, re.M | re.I)
        if state:
            result["state"] = {"fully-charged": "full", "charging": "charging", "discharging": "discharging"}.get(state.group(1).lower(), "unknown")
        for pat in (r"time to full:\s*(.+)", r"time to empty:\s*(.+)"):
            m = re.search(pat, text, re.I)
            if m: result["time"] = m.group(1).strip(); break
    except Exception: pass
    return result


def wifi_state() -> dict[str, Any]:
    try:
        p = _run(["nmcli", "-t", "-e", "yes", "-f", "GENERAL.STATE,GENERAL.CONNECTION", "dev", "show"])
        if p.returncode != 0: return {"enabled": False, "ssid": None, "strength": None}
        ssid = None
        for line in p.stdout.splitlines():
            if line.startswith("GENERAL.CONNECTION:"): ssid = _nm_unescape(line.split(":", 1)[1])
        w = wifi_list(False)
        active = next((x for x in w if x["active"]), None)
        return {"enabled": True, "ssid": ssid if ssid and ssid != "--" else (active["ssid"] if active else None), "strength": active["strength"] if active else None}
    except Exception: return {"enabled": False, "ssid": None, "strength": None}


def wifi_set_enabled(on: bool) -> tuple[bool, str]:
    try: return _ok(_run(["nmcli", "radio", "wifi", "on" if on else "off"]))
    except Exception: return False, _ERR


def wifi_list(rescan: bool = False) -> list[dict[str, Any]]:
    try:
        known_p = _run(["nmcli", "-t", "-f", "NAME,TYPE", "con", "show"])
        known = {_nm_fields(x, 2)[0] for x in known_p.stdout.splitlines() if len(_nm_fields(x, 2)) > 1 and _nm_fields(x, 2)[1] == "802-11-wireless"}
        p = _run(["nmcli", "-t", "-e", "yes", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes" if rescan else "no"])
        return parse_nmcli_wifi(p.stdout, known) if p.returncode == 0 else []
    except Exception: return []


def wifi_connect(ssid: str, password: str | None = None) -> tuple[bool, str]:
    try:
        known = any(x["ssid"] == ssid and x["known"] for x in wifi_list())
        args = ["nmcli", "con", "up", "id", ssid] if known else ["nmcli", "dev", "wifi", "connect", ssid] + (["password", password] if password is not None else [])
        p = _run(args)
        if p.returncode == 0: return True, "Đã kết nối"
        if not known: _run(["nmcli", "con", "delete", "id", ssid])
        return False, "Sai mật khẩu hoặc không kết nối được"
    except Exception: return False, "Sai mật khẩu hoặc không kết nối được"


def wifi_disconnect() -> tuple[bool, str]:
    try:
        s = wifi_state().get("ssid")
        return _ok(_run(["nmcli", "con", "down", "id", s])) if s else (False, "Không có mạng đang nối")
    except Exception: return False, _ERR


def wifi_forget(ssid: str) -> tuple[bool, str]:
    try: return _ok(_run(["nmcli", "con", "delete", "id", ssid]))
    except Exception: return False, _ERR


def _bluez_call(path: str, method: str, args: tuple[Any, ...] = (), timeout: int = _TIMEOUT) -> tuple[bool, str]:
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    proxy = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.NONE, None, "org.bluez", path, "org.bluez." + method.split(".")[0], None)
    proxy.call_sync(method.split(".")[-1], GLib.Variant("()", args) if args else None, Gio.DBusCallFlags.NONE, timeout * 1000, None)
    return True, "OK"


def bt_state() -> dict[str, Any]:
    default = {"available": False, "powered": False, "discovering": False, "devices": []}
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        p = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.NONE, None, "org.bluez", "/", "org.freedesktop.DBus.ObjectManager", None)
        value = p.call_sync("GetManagedObjects", None, Gio.DBusCallFlags.NONE, _TIMEOUT * 1000, None).unpack()[0]
        return parse_bluez_objects(value)
    except Exception: return default


def _bt_method(path: str, method: str) -> tuple[bool, str]:
    try: return _bluez_call(path, method, timeout=20 if method == "Device1.Connect" else _TIMEOUT)
    except Exception: return False, _ERR


def bt_set_powered(on: bool) -> tuple[bool, str]:
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None); path = next((p for p, x in _managed(bus).items() if "org.bluez.Adapter1" in x), None)
        if not path: return False, "Không tìm thấy Bluetooth"
        pr = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.NONE, None, "org.bluez", path, "org.freedesktop.DBus.Properties", None)
        try: pr.call_sync("Set", GLib.Variant("(ssv)", ("org.bluez.Adapter1", "Powered", GLib.Variant("b", on))), Gio.DBusCallFlags.NONE, _TIMEOUT * 1000, None)
        except Exception:
            if on: _run(["rfkill", "unblock", "bluetooth"]); pr.call_sync("Set", GLib.Variant("(ssv)", ("org.bluez.Adapter1", "Powered", GLib.Variant("b", on))), Gio.DBusCallFlags.NONE, _TIMEOUT * 1000, None)
        return True, "OK"
    except Exception: return False, _ERR


def _managed(bus: Any) -> dict[str, Any]:
    from gi.repository import Gio
    p = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.NONE, None, "org.bluez", "/", "org.freedesktop.DBus.ObjectManager", None)
    return p.call_sync("GetManagedObjects", None, Gio.DBusCallFlags.NONE, _TIMEOUT * 1000, None).unpack()[0]


def bt_set_discovering(on: bool) -> tuple[bool, str]:
    try:
        from gi.repository import Gio
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None); path = next((p for p, x in _managed(bus).items() if "org.bluez.Adapter1" in x), None)
        return _bt_method(path, "Adapter1." + ("StartDiscovery" if on else "StopDiscovery")) if path else (False, "Không tìm thấy Bluetooth")
    except Exception: return False, _ERR


def bt_connect(path: str) -> tuple[bool, str]: return _bt_method(path, "Device1.Connect")
def bt_disconnect(path: str) -> tuple[bool, str]: return _bt_method(path, "Device1.Disconnect")
def bt_pair(path: str) -> tuple[bool, str]:
    try:
        ok, msg = _bt_method(path, "Device1.Pair")
        if not ok: return ok, msg
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        props = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.NONE, None, "org.bluez", path, "org.freedesktop.DBus.Properties", None)
        props.call_sync("Set", GLib.Variant("(ssv)", ("org.bluez.Device1", "Trusted", GLib.Variant("v", GLib.Variant("b", True)))), Gio.DBusCallFlags.NONE, _TIMEOUT * 1000, None)
        return _bt_method(path, "Device1.Connect")
    except Exception: return False, _ERR
def bt_remove(path: str) -> tuple[bool, str]:
    try:
        from gi.repository import Gio
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None); adapter = "/".join(path.split("/")[:4])
        return _bluez_call(adapter, "Adapter1.RemoveDevice", (path,))
    except Exception: return False, _ERR


def _pactl(kind: str) -> tuple[list[dict[str, Any]], str]:
    try:
        p = _run(["pactl", "-f", "json", "list", "sinks" if kind == "output" else "sources"])
        d = _run(["pactl", "get-default-sink" if kind == "output" else "get-default-source"])
        return parse_pactl_devices(p.stdout, d.stdout.strip(), kind), d.stdout.strip()
    except Exception: return [], ""


def audio_outputs() -> list[dict[str, Any]]: return _pactl("output")[0]
def audio_inputs() -> list[dict[str, Any]]: return _pactl("input")[0]
def audio_set_default(kind: str, name: str) -> tuple[bool, str]:
    try: return _ok(_run(["pactl", "set-default-sink" if kind == "output" else "set-default-source", name]))
    except Exception: return False, _ERR


def audio_volume(kind: str = "output") -> dict[str, Any]:
    items, _ = _pactl(kind); x = next((v for v in items if v["default"]), None)
    return {"volume": x["volume"], "muted": x["muted"]} if x else {"volume": 0, "muted": False}


def audio_set_volume(kind: str, percent: int, name: str | None = None) -> tuple[bool, str]:
    try: return _ok(_run(["pactl", "set-sink-volume" if kind == "output" else "set-source-volume", name or ("@DEFAULT_SINK@" if kind == "output" else "@DEFAULT_SOURCE@"), f"{max(0, min(150, int(percent)))}%"]))
    except Exception: return False, _ERR


def audio_toggle_mute(kind: str, name: str | None = None) -> tuple[bool, str]:
    try: return _ok(_run(["pactl", "set-sink-mute" if kind == "output" else "set-source-mute", name or ("@DEFAULT_SINK@" if kind == "output" else "@DEFAULT_SOURCE@"), "toggle"]))
    except Exception: return False, _ERR


def audio_streams() -> list[dict[str, Any]]:
    try: return parse_pactl_streams(_run(["pactl", "-f", "json", "list", "sink-inputs"]).stdout)
    except Exception: return []


def audio_set_stream_volume(index: int, percent: int) -> tuple[bool, str]:
    try: return _ok(_run(["pactl", "set-sink-input-volume", str(index), f"{max(0, min(150, int(percent)))}%"]))
    except Exception: return False, _ERR


def brightness_get() -> int:
    try: return parse_brightness(_run(["brightnessctl", "-m"]).stdout)
    except Exception: return 0
def brightness_set(percent: int) -> tuple[bool, str]:
    try: return _ok(_run(["brightnessctl", "set", f"{max(1, min(100, int(percent)))}%"]))
    except Exception: return False, _ERR
def power_profile_get() -> str:
    try: return _run(["powerprofilesctl", "get"]).stdout.strip() or ""
    except Exception: return ""
def power_profiles() -> list[str]:
    try:
        text = _run(["powerprofilesctl", "list"]).stdout
        return [x for x in ("power-saver", "balanced", "performance") if re.search(rf"^\s*\*?\s*{re.escape(x)}:", text, re.M)]
    except Exception: return []
def power_profile_set(name: str) -> tuple[bool, str]:
    try: return _ok(_run(["powerprofilesctl", "set", name]))
    except Exception: return False, _ERR


def battery() -> dict[str, Any]:
    try:
        bats = list(Path("/sys/class/power_supply").glob("BAT*/capacity"))
        if not bats: return {"present": False, "percent": None, "state": "unknown", "time": None}
        root = bats[0].parent; pct = int(bats[0].read_text().strip()); status = (root / "status").read_text().strip().lower()
        up = _run(["upower", "-i", f"/org/freedesktop/UPower/devices/battery_{root.name}"])
        val = parse_upower(up.stdout) if up.returncode == 0 else {}
        return {"present": True, "percent": pct, "state": {"charging": "charging", "discharging": "discharging", "full": "full", "fully-charged": "full"}.get(status, "unknown"), "time": val.get("time")}
    except Exception: return {"present": False, "percent": None, "state": "unknown", "time": None}


def dnd_get() -> bool:
    try: return _run(["dunstctl", "is-paused"]).stdout.strip().lower() == "true"
    except Exception: return False
def dnd_set(on: bool) -> tuple[bool, str]:
    try:
        p = _run(["dunstctl", "set-paused", "true" if on else "false"]); _run(["pkill", "-RTMIN+10", "waybar"]); _run(["pkill", "-RTMIN+12", "waybar"]); return _ok(p)
    except Exception: return False, _ERR


def _pidfile() -> Path: return Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "kafka-idle-inhibit.pid"
def idle_inhibit_get() -> bool:
    try:
        pid = _pidfile().read_text().strip(); return bool(pid and "kafka-idle" in Path(f"/proc/{int(pid)}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore"))
    except Exception: return False
def idle_inhibit_set(on: bool) -> tuple[bool, str]:
    try:
        pf = _pidfile()
        if on:
            p = subprocess.Popen(["systemd-inhibit", "--what=idle:sleep", "--who=kafka-idle", "--why=Giữ màn hình sáng", "--mode=block", "sleep", "infinity"], start_new_session=True)
            pf.write_text(str(p.pid))
            time.sleep(0.25)   # chờ exec xong, idle_inhibit_get() gọi ngay sau mới thấy "kafka-idle" trong cmdline
            return True, "OK"
        pid = int(pf.read_text()); os.kill(pid, signal.SIGTERM); pf.unlink(missing_ok=True); return True, "OK"
    except Exception: return False, _ERR


def ime_get() -> str:
    try: return {"1": "en", "2": "vi"}.get(_run(["fcitx5-remote"]).stdout.strip(), "off")
    except Exception: return "off"
def ime_toggle() -> tuple[bool, str]:
    try: return _ok(_run(["fcitx5-remote", "-t"]))
    except Exception: return False, _ERR


def _dump() -> dict[str, Any]:
    return {"wifi_state": wifi_state(), "wifi_list": wifi_list(), "bt_state": bt_state(), "audio_outputs": audio_outputs(), "audio_inputs": audio_inputs(), "audio_streams": audio_streams(), "brightness_get": brightness_get(), "power_profile_get": power_profile_get(), "battery": battery(), "dnd_get": dnd_get(), "idle_inhibit_get": idle_inhibit_get(), "ime_get": ime_get()}


def _selftest() -> None:
    base = Path(__file__).resolve().parent / "tests" / "control-samples"   # mẫu đầu ra thật đã ẩn danh
    wifi = parse_nmcli_wifi("*:Cafe\\:Net:80:WPA2\n:Cafe\\:Net:40:--\n:Other:90:WPA2", {"Other"})
    assert wifi[0]["ssid"] == "Cafe:Net" and wifi[0]["strength"] == 80 and wifi[1]["known"]
    assert parse_brightness((base / "brightnessctl.txt").read_text()) == 95
    assert parse_upower((base / "upower-bat.txt").read_text())["state"] == "full"
    objs = parse_bluez_busctl(json.loads((base / "bluez-objects.json").read_text()))
    bt = parse_bluez_objects(objs); assert bt["powered"] and bt["devices"][0]["connected"] and len(bt["devices"]) == 2
    assert len(parse_pactl_devices((base / "pactl-sources.json").read_text(), kind="input")) == 2
    assert parse_pactl_streams((base / "pactl-sink-inputs.json").read_text())[0]["app"] == "Chromium"
    assert power_profiles_from_text((base / "powerprofilesctl-list.txt").read_text()) == ["power-saver", "balanced", "performance"]
    print("selftest ok")


def power_profiles_from_text(text: str) -> list[str]:
    try: return [x for x in ("power-saver", "balanced", "performance") if re.search(rf"^\s*\*?\s*{re.escape(x)}:", text, re.M)]
    except Exception: return []


if __name__ == "__main__":
    if "--selftest" in sys.argv: _selftest()
    elif "--dump" in sys.argv: print(json.dumps(_dump(), ensure_ascii=False, indent=2))
