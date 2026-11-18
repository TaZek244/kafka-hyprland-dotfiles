"""Backend giả tối giản, cùng API với control_backends.py để thử popup."""
wifi = {"enabled": True, "ssid": "KafkaNet", "strength": 82}
bt = {"available": True, "powered": True, "discovering": False, "devices": [{"path": "/fake/headset", "address": "00:11", "name": "Kafka Headset", "icon": "audio-headset", "paired": True, "connected": True, "trusted": True, "battery": 76}, {"path": "/fake/phone", "address": "00:22", "name": "Điện thoại", "icon": "phone", "paired": False, "connected": False, "trusted": False, "battery": None}]}
_dnd = False; _idle = False; _ime = "vi"; _power = "balanced"; _brightness = 78; _muted = False; _vol = 42
def wifi_state(): return dict(wifi)
def wifi_set_enabled(on): wifi["enabled"] = on; return True, ""
def wifi_list(rescan=False): return [{"ssid": "KafkaNet", "strength": 82, "secure": True, "active": wifi["enabled"], "known": True}, {"ssid": "Cafe", "strength": 47, "secure": False, "active": False, "known": False}]
def wifi_connect(ssid, password=None): wifi.update(enabled=True, ssid=ssid, strength=70); return True, ""
def wifi_disconnect(): wifi["ssid"] = None; return True, ""
def wifi_forget(ssid): return True, ""
def bt_state(): return dict(bt)
def bt_set_powered(on): bt["powered"] = on; return True, ""
def bt_set_discovering(on): bt["discovering"] = on; return True, ""
def bt_connect(path): return True, ""
def bt_disconnect(path): return True, ""
def bt_pair(path): return True, ""
def bt_remove(path): return True, ""
def audio_outputs(): return [{"name": "fake-sink", "description": "Loa Kafka", "default": True, "volume": _vol, "muted": _muted}]
def audio_inputs(): return [{"name": "fake-source", "description": "Micro Kafka", "default": True, "volume": 55, "muted": False}]
def audio_set_default(kind, name): return True, ""
def audio_volume(kind="output"): return {"volume": _vol, "muted": _muted}
def audio_set_volume(kind, percent, name=None):
    global _vol
    _vol = percent; return True, ""
def audio_toggle_mute(kind, name=None):
    global _muted
    _muted = not _muted; return True, ""
def audio_streams(): return [{"index": 1, "app": "Trình phát thử", "icon": None, "volume": 35, "muted": False}]
def audio_set_stream_volume(index, percent): return True, ""
def brightness_get(): return _brightness
def brightness_set(percent):
    global _brightness
    _brightness = percent; return True, ""
def power_profile_get(): return _power
def power_profiles(): return ["power-saver", "balanced", "performance"]
def power_profile_set(name):
    global _power
    _power = name; return True, ""
def battery(): return {"present": True, "percent": 88, "state": "charging", "time": "1,5 giờ"}
def dnd_get(): return _dnd
def dnd_set(on):
    global _dnd
    _dnd = on; return True, ""
def idle_inhibit_get(): return _idle
def idle_inhibit_set(on):
    global _idle
    _idle = on; return True, ""
def ime_get(): return _ime
def ime_toggle():
    global _ime
    _ime = "en" if _ime == "vi" else "vi"; return True, ""
