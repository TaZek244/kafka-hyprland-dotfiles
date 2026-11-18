#!/usr/bin/env python3
"""Trình xem và chỉnh sửa phím tắt Hyprland (GTK4, không dùng libadwaita)."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATA_PATH = Path(os.path.expanduser("~/.config/hypr/keybinds.lua"))
DEFAULT_PATH = Path(os.path.expanduser("~/.config/hypr/hyprland.lua"))
MOD_ORDER = ("SUPER", "CTRL", "ALT", "SHIFT")
MOD_BITS = {"SHIFT": 1, "CTRL": 4, "ALT": 8, "SUPER": 64}


@dataclass
class Keybind:
    keys: str
    action: str = ""
    command: str = ""
    description: str = ""
    source: str = "Mặc định"
    dispatcher: str = ""
    disabled: bool = False
    system: bool = False


def folded(value: str) -> str:
    """Bỏ dấu tiếng Việt để tìm kiếm dễ hơn."""
    return "".join(c for c in unicodedata.normalize("NFD", value.lower())
                   if unicodedata.category(c) != "Mn")


def normalize_keys(value: str) -> str:
    value = value.strip()
    if value.lower().startswith("mouse:"):
        return "mouse:" + value.split(":", 1)[1].strip()
    parts = [p.strip() for p in value.split("+") if p.strip()]
    if not parts:
        return value
    mods = {p.upper() for p in parts[:-1]}
    key = parts[-1]
    return " + ".join([m for m in MOD_ORDER if m in mods] + [key])


def keys_from_modmask(mask: int, key: str, mouse: bool = False) -> str:
    key = f"mouse:{key}" if mouse and not key.lower().startswith("mouse:") else key
    return " + ".join([m for m in MOD_ORDER if mask & MOD_BITS[m]] + [key])


def lua_unescape(value: str) -> str:
    return re.sub(r"\\([\\\"nrt])", lambda m: {"n": "\n", "r": "\r", "t": "\t"}.get(m.group(1), m.group(1)), value)


def lua_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")


def read_lua_string(text: str, start: int) -> tuple[str, int]:
    if start >= len(text) or text[start] != '"':
        raise ValueError("cần chuỗi Lua bắt đầu bằng dấu ngoặc kép")
    i, out = start + 1, []
    while i < len(text):
        if text[i] == '"':
            return "".join(out), i + 1
        if text[i] == "\\" and i + 1 < len(text):
            out.append(lua_unescape(text[i:i + 2])); i += 2
        else:
            out.append(text[i]); i += 1
    raise ValueError("chuỗi Lua chưa đóng")


def parse_keybinds_lua(path: Path = DATA_PATH) -> list[dict[str, str]]:
    """Parser nhỏ, chỉ nhận đúng định dạng mà ứng dụng này ghi."""
    text = path.read_text(encoding="utf-8")
    body_match = re.search(r"\breturn\s*\{(.*)\}\s*\Z", text, re.S)
    if not body_match:
        raise ValueError("keybinds.lua không có bảng return hợp lệ")
    body = body_match.group(1)
    result: list[dict[str, str]] = []
    pos = 0
    field_re = re.compile(r"\s*([A-Za-z_]\w*)\s*=\s*")
    while True:
        # Bỏ khoảng trắng, dấu phẩy và comment giữa các mục
        m = re.compile(r"(?:\s|,|--[^\n]*)*").match(body, pos)
        pos = m.end()
        if pos >= len(body):
            break
        if body[pos] != "{":
            raise ValueError(f"ký tự lạ trong keybinds.lua: {body[pos:pos + 20]!r}")
        pos += 1
        # Đọc lần lượt key = "chuỗi" cho tới dấu } đóng mục (dấu } nằm trong chuỗi không tính)
        fields: dict[str, str] = {}
        while True:
            pos = re.compile(r"(?:\s|,)*").match(body, pos).end()
            if pos >= len(body):
                raise ValueError("bảng phím tắt chưa đóng")
            if body[pos] == "}":
                pos += 1
                break
            fm = field_re.match(body, pos)
            if not fm:
                raise ValueError(f"không đọc được trường: {body[pos:pos + 20]!r}")
            fields[fm.group(1)], pos = read_lua_string(body, fm.end())
        if "keys" not in fields:
            raise ValueError("mục thiếu keys")
        fields.setdefault("action", "")
        fields.setdefault("command", "")
        fields.setdefault("description", "")
        if fields["action"] not in ("exec", "lua", "unbind"):
            raise ValueError(f"action không hợp lệ: {fields['action']}")
        result.append({k: fields[k] for k in ("keys", "action", "command", "description")})
    return result


def split_lua_args(text: str) -> list[str]:
    """Tách đối số ở dấu phẩy cấp ngoài cùng (bỏ qua chuỗi '..'/".." và ngoặc (), {}, [])."""
    result, start, depth, quote, escaped = [], 0, 0, None, False
    for i, char in enumerate(text):
        if quote:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == quote: quote = None
            continue
        if char in "'\"": quote = char
        elif char in "({[": depth += 1
        elif char in ")}]": depth -= 1
        elif char == "," and depth == 0:
            result.append(text[start:i].strip()); start = i + 1
    result.append(text[start:].strip())
    return result


def balanced_call(line: str, opening: int) -> tuple[str, int] | None:
    """Trả về (nội dung trong ngoặc, vị trí ngay sau dấu ')' đóng) hoặc None."""
    depth, quote, escaped = 0, None, False
    for i in range(opening, len(line)):
        c = line[i]
        if quote:
            if escaped: escaped = False
            elif c == "\\": escaped = True
            elif c == quote: quote = None
        elif c in "'\"": quote = c
        elif c == "(": depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0: return line[opening + 1:i], i + 1
    return None


def eval_lua_string(expr: str, env: dict[str, str]) -> str | None:
    """Tính biểu thức chuỗi Lua đơn giản: "a" .. biến .. 'b'. Không tính được thì None."""
    parts, buf, quote, escaped, i = [], [], None, False, 0
    expr = expr.strip()
    while i < len(expr):
        c = expr[i]
        if quote:
            buf.append(c)
            if escaped: escaped = False
            elif c == "\\": escaped = True
            elif c == quote: quote = None
        elif c in "'\"": quote = c; buf.append(c)
        elif expr.startswith("..", i): parts.append("".join(buf).strip()); buf = []; i += 1
        else: buf.append(c)
        i += 1
    parts.append("".join(buf).strip())
    out = []
    for part in parts:
        if len(part) >= 2 and part[0] == part[-1] and part[0] in "'\"":
            out.append(lua_unescape(part[1:-1]) if part[0] == '"' else part[1:-1].replace("\\'", "'").replace("\\\\", "\\"))
        elif re.fullmatch(r"[A-Za-z_]\w*", part) and part in env:
            out.append(env[part])
        else:
            return None
    return "".join(out)


def static_defaults(path: Path = DEFAULT_PATH) -> list[Keybind]:
    result: list[Keybind] = []
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.lstrip() or raw.lstrip().startswith("--"): continue
        # Biến chuỗi cấp ngoài (local terminal = "kitty", local scripts = "~/..."), dùng để hiện lệnh thật.
        lm = re.match(r"^local\s+([A-Za-z_]\w*)\s*=\s*(.+?)\s*(--.*)?$", raw)
        if lm:
            value = eval_lua_string(lm.group(2), env)
            if value is not None: env[lm.group(1)] = value
            continue
        match = re.search(r"hl\.bind\s*\(", raw)
        if not match: continue
        found = balanced_call(raw, match.end() - 1)
        if found is None: continue
        call, call_end = found
        args = split_lua_args(call)
        if len(args) < 2: continue
        key_expr, action = args[0], args[1]
        km = re.fullmatch(r'key\(\s*"([^"]+)"\s*\)', key_expr)
        if km:
            keys = normalize_keys("SUPER + " + km.group(1))
        elif re.fullmatch(r'"[^"\n]*"', key_expr):
            keys = normalize_keys(key_expr[1:-1])
        else:
            continue
        exec_match = re.match(r"hl\.dsp\.exec_cmd\((.*)\)$", action, re.S)
        resolved = eval_lua_string(exec_match.group(1), env) if exec_match else None
        if resolved is not None:
            shown, kind = resolved, "exec"          # lệnh shell thật, sửa được như "Chạy lệnh"
        else:
            shown, kind = action, "lua"             # biểu thức Lua nguyên văn
        tail = raw[call_end:]
        comment = tail.split("--", 1)[1].strip() if "--" in tail else ""
        result.append(Keybind(keys, kind, shown, comment, "Mặc định"))
    return result


def hyprctl_binds() -> list[Keybind]:
    try:
        proc = subprocess.run(["hyprctl", "binds", "-j"], capture_output=True, text=True, timeout=3, check=True)
        data = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return []
    result = []
    for item in data if isinstance(data, list) else []:
        keys = keys_from_modmask(int(item.get("modmask", 0)), str(item.get("key", "")), bool(item.get("mouse", False)))
        dispatcher = str(item.get("dispatcher", ""))
        name = re.search(r"Dispatcher\(([^)]+)", dispatcher)
        result.append(Keybind(keys, "", name.group(1) if name else dispatcher, str(item.get("description", "")), "Hệ thống", dispatcher, system=True))
    return result


def load_bindings() -> tuple[list[Keybind], str | None]:
    defaults = static_defaults(DEFAULT_PATH) if DEFAULT_PATH.exists() else []
    active = hyprctl_binds()
    try: custom_raw = parse_keybinds_lua(DATA_PATH) if DATA_PATH.exists() else []
    except (OSError, ValueError) as exc: return [], str(exc)
    default_map = {b.keys: b for b in defaults}
    active_map = {b.keys: b for b in active}
    # Khi hyprctl không chạy được (ngoài phiên Hyprland hoặc lệnh lỗi),
    # dùng parse tĩnh làm dữ liệu hoạt động dự phòng để ứng dụng vẫn hữu ích.
    if not active_map:
        active_map = {b.keys: b for b in defaults}
    customs = []
    for item in custom_raw:
        key = normalize_keys(item["keys"])
        if item["action"] == "unbind":
            customs.append(Keybind(key, "unbind", "", item.get("description", ""), "Đã tắt", disabled=True))
        else:
            source = "Đã sửa" if key in default_map else "Tùy chỉnh"
            customs.append(Keybind(key, item["action"], item.get("command", ""), item.get("description", ""), source))
    custom_map = {b.keys: b for b in customs}
    merged: list[Keybind] = []
    for key, active_item in active_map.items():
        if key in custom_map: continue
        if key in default_map:
            item = default_map[key]
            item = Keybind(item.keys, item.action, item.command, active_item.description or item.description, "Mặc định", active_item.dispatcher)
        elif active_item.description:
            # Phím có mô tả nhưng không khai báo trong hyprland.lua: do chương trình khác
            # đăng ký lúc chạy (vd hyprshell). Chỉ xem.
            item = active_item
        else:
            # Phím sinh trong vòng lặp của hyprland.lua (Super + số, Super + hướng...):
            # không parse tĩnh được biểu thức, nhưng vẫn là phím mặc định nên tắt/ghi đè được.
            item = Keybind(key, "lua", "", "", "Mặc định", active_item.dispatcher)
            item.command = ""
            item.description = f"(trong vòng lặp của hyprland.lua: {active_item.command})"
        merged.append(item)
    base_keys = {b.keys for b in merged if b.source == "Mặc định"}
    for item in customs:
        if item.source == "Tùy chỉnh" and item.keys in base_keys | set(default_map):
            item.source = "Đã sửa"
    merged.extend(customs)
    return merged, None


def serialize_bindings(items: list[dict[str, str]]) -> str:
    lines = ["-- Phím tắt tùy chỉnh — FILE DO keybinds-editor.py GHI, sửa bằng app.", "-- Được nạp sau các phím mặc định trong hyprland.lua.", "return {"]
    for item in items:
        parts = [f'keys = "{lua_escape(item["keys"])}"', f'action = "{lua_escape(item["action"])}"']
        if item["action"] != "unbind": parts.append(f'command = "{lua_escape(item.get("command", ""))}"')
        if item.get("description", ""): parts.append(f'description = "{lua_escape(item["description"])}"')
        lines.append("    { " + ", ".join(parts) + " },")
    lines.append("}\n")
    return "\n".join(lines)


def write_bindings(items: list[dict[str, str]], backup_done: list[bool]) -> None:
    target = Path(os.path.realpath(DATA_PATH))
    target.parent.mkdir(parents=True, exist_ok=True)
    if not backup_done[0] and target.exists():
        shutil.copy2(target, target.with_name(target.name + ".bak")); backup_done[0] = True
    fd, temp = tempfile.mkstemp(prefix=".keybinds-", suffix=".lua", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream: stream.write(serialize_bindings(items))
        os.chmod(temp, 0o644)  # mkstemp tạo file 600; dotfile cần 644 như các file khác
        os.replace(temp, target)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def selftest() -> bool:
    try:
        defaults = static_defaults(DEFAULT_PATH)
        assert defaults and any("SUPER + SHIFT + X" == b.keys for b in defaults)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "keybinds.lua"
            original = [{"keys": "SUPER + V", "action": "exec", "command": 'printf "Xin chào, \\\"Kafka\\\"\\n"', "description": "Mô tả có dấu, \\"}, {"keys": "SUPER + P", "action": "lua", "command": 'hl.dsp.window.pin({ action = "toggle" })', "description": "có } và {"}, {"keys": "SUPER + J", "action": "unbind", "command": "", "description": ""}]
            path.write_text(serialize_bindings(original), encoding="utf-8")
            assert parse_keybinds_lua(path) == original
        print("PASS: parser hyprland.lua và round-trip keybinds.lua")
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False


def cli_list() -> None:
    rows, error = load_bindings()
    if error: print(f"Lỗi: {error}", file=sys.stderr)
    print(f"{'Phím':30} {'Làm gì':40} {'Mô tả':30} Nguồn")
    for row in rows: print(f"{row.keys:30} {row.command[:40]:40} {row.description[:30]:30} {row.source}")


def gui_main() -> int:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gio, GLib, GObject, Gtk

    class Editor(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="kafka.keybinds", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
            self.backup_done = [False]; self.rows: list[Keybind] = []; self.error = None; self.selected: Keybind | None = None
            self.connect("activate", self.activate)

        def activate(self, _app):
            if hasattr(self, "window"): self.window.present(); return
            self.window = Gtk.ApplicationWindow(application=self, title="Phím tắt", default_width=1000, default_height=640)
            self.window.connect("close-request", lambda *_: False)
            self.window.add_css_class("kafka-window")
            self.build_ui(); self.reload()
            controller = Gtk.EventControllerKey(); controller.connect("key-pressed", self.global_key); self.window.add_controller(controller)
            self.window.present()

        def build_ui(self):
            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); root.set_margin_top(16); root.set_margin_bottom(14); root.set_margin_start(18); root.set_margin_end(18); self.window.set_child(root)
            top = Gtk.Box(spacing=8); root.append(top)
            self.search = Gtk.SearchEntry(placeholder_text="Tìm phím, hành động hoặc mô tả…"); self.search.set_hexpand(True); self.search.connect("search-changed", lambda *_: self.refresh_list()); top.append(self.search)
            self.filter = Gtk.DropDown.new_from_strings(["Tất cả", "Mặc định", "Tùy chỉnh", "Đã sửa", "Đã tắt"]); self.filter.connect("notify::selected", lambda *_: self.refresh_list()); top.append(self.filter)
            self.stats = Gtk.Label(xalign=0); root.append(self.stats)
            self.listbox = Gtk.ListBox(); self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE); self.listbox.add_css_class("bind-list"); self.listbox.connect("row-selected", self.select_row); self.listbox.connect("row-activated", lambda *_: self.edit_selected()); scroll = Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_child(self.listbox); root.append(scroll)
            buttons = Gtk.Box(spacing=8); root.append(buttons)
            self.add_btn = Gtk.Button(label="Thêm"); self.add_btn.add_css_class("suggested-action"); self.add_btn.connect("clicked", lambda *_: self.edit_dialog(None)); buttons.append(self.add_btn)
            self.edit_btn = Gtk.Button(label="Sửa"); self.edit_btn.connect("clicked", lambda *_: self.edit_selected()); buttons.append(self.edit_btn)
            self.delete_btn = Gtk.Button(label="Xóa"); self.delete_btn.connect("clicked", lambda *_: self.delete_selected()); buttons.append(self.delete_btn)
            reload_btn = Gtk.Button(label="Nạp lại"); reload_btn.connect("clicked", lambda *_: self.reload()); buttons.append(reload_btn)
            self.status = Gtk.Label(xalign=0); self.status.set_hexpand(True); buttons.append(self.status)
            css = Gtk.CssProvider(); css.load_from_data(b'''* { font-family: "FiraCode Nerd Font"; } window { background: #16101e; color: #ece3ea; } entry, dropdown, button { border-radius: 10px; } button { background: #2b1828; color: #ece3ea; } button.suggested-action { background: #b8326a; color: white; } .bind-list { background: transparent; } .bind-list > row { border-radius: 8px; } .bind-list > row:hover { background: #3a1530; } .bind-list > row:selected { background: #5c1d40; } .bind-row { padding: 8px 10px; } dropdown > button { background: #2b1828; } entry { background: #22101d; color: #ece3ea; border: 1px solid #3b1a33; } entry:focus-within { border-color: #b8326a; } .keycap { background: #22101d; border: 1px solid #b8326a; border-radius: 6px; padding: 1px 7px; } .muted { color: #a99aa6; } .disabled { color: #6e5a6b; text-decoration: line-through; } .custom { color: #d4af6a; } .edited { color: #e05a8c; } .system { color: #a99aa6; }''', -1); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)

        def reload(self):
            self.rows, self.error = load_bindings(); self.refresh_list(); self.status.set_text(f"Lỗi: {self.error}" if self.error else "Đã nạp dữ liệu")

        def refresh_list(self):
            while (child := self.listbox.get_first_child()) is not None: self.listbox.remove(child)
            query = folded(self.search.get_text()) if hasattr(self, "search") else ""; source = self.filter.get_selected_item().get_string() if hasattr(self, "filter") and self.filter.get_selected_item() else "Tất cả"
            visible = [r for r in self.rows if (source == "Tất cả" or r.source == source) and (not query or query in folded(" ".join((r.keys, r.command, r.description))))]
            for row in sorted(visible, key=lambda x: folded(x.keys)):
                box = Gtk.Box(spacing=10); box.add_css_class("bind-row"); box.set_tooltip_text(row.keys)
                keybox = Gtk.Box(spacing=3); keybox.set_size_request(230, -1)
                for part in row.keys.split(" + "): keybox.append(Gtk.Label(label=part, css_classes=["keycap"]))
                box.append(keybox)
                # Cột cố định + cắt chữ dài bằng "…" để cột Nguồn luôn nằm trong khung (xem đủ ở tooltip)
                cmd = Gtk.Label(label=row.command or "—", xalign=0, hexpand=True, ellipsize=3, width_chars=30, max_width_chars=30); cmd.set_tooltip_text(row.command or None); box.append(cmd)
                desc = Gtk.Label(label=row.description or "—", xalign=0, hexpand=True, ellipsize=3, width_chars=28, max_width_chars=28, css_classes=["muted"]); desc.set_tooltip_text(row.description or None); box.append(desc)
                box.append(Gtk.Label(label=row.source, xalign=0, width_chars=10, css_classes=[{"Đã tắt":"disabled", "Tùy chỉnh":"custom", "Đã sửa":"edited", "Hệ thống":"system"}.get(row.source, "")]))
                listrow = Gtk.ListBoxRow(); listrow.set_child(box); listrow._keybind = row; self.listbox.append(listrow)
            counts = {s: sum(r.source == s for r in self.rows) for s in ("Tùy chỉnh", "Đã sửa", "Đã tắt")}; self.stats.set_text(f"{len(visible)} phím · {counts['Tùy chỉnh']} tùy chỉnh · {counts['Đã sửa']} đã sửa · {counts['Đã tắt']} đã tắt")

        def select_row(self, _box, row):
            self.selected = getattr(row, "_keybind", None) if row else None; self.edit_btn.set_sensitive(bool(self.selected and not self.selected.system)); self.delete_btn.set_label("Khôi phục" if self.selected and self.selected.disabled else "Xóa"); self.delete_btn.set_sensitive(bool(self.selected and not self.selected.system))

        def edit_selected(self):
            if self.selected and not self.selected.system: self.edit_dialog(self.selected)

        def global_key(self, _controller, keyval, _keycode, state):
            name = Gdk.keyval_name(keyval) or ""
            if state & Gdk.ModifierType.CONTROL_MASK and name.lower() == "f": self.search.grab_focus(); return True
            if state & Gdk.ModifierType.CONTROL_MASK and name.lower() == "n": self.edit_dialog(None); return True
            if name == "Delete": self.delete_selected(); return True
            if name == "Escape": self.window.close(); return True
            return False

        def alert(self, title, message, callback=None):
            dialog = Gtk.AlertDialog(); dialog.set_message(title); dialog.set_detail(message); dialog.set_buttons(["Đóng"]); dialog.choose(self.window, None, lambda *_: callback() if callback else None)

        def delete_selected(self):
            row = self.selected
            if not row: return
            if row.disabled: self.confirm("Khôi phục phím tắt?", "Bỏ mục unbind để phím mặc định hoạt động lại.", lambda: self.mutate(row, "restore")); return
            text = "Xóa mục tùy chỉnh?" if row.source == "Tùy chỉnh" else "Xóa bản sửa? Phím mặc định sẽ trở lại." if row.source == "Đã sửa" else "Tắt phím mặc định?"
            self.confirm(text, "Thao tác này sẽ ghi keybinds.lua.", lambda: self.mutate(row, "delete"))

        def confirm(self, title, detail, callback):
            dialog = Gtk.AlertDialog(); dialog.set_message(title); dialog.set_detail(detail); dialog.set_buttons(["Hủy", "Đồng ý"]); dialog.set_cancel_button(0); dialog.set_default_button(1); dialog.choose(self.window, None, lambda d, res: callback() if d.choose_finish(res) == 1 else None)

        def mutate(self, row, operation):
            try: items = parse_keybinds_lua(DATA_PATH) if DATA_PATH.exists() else []
            except ValueError as exc: self.alert("Không thể đọc file", str(exc)); return
            key = normalize_keys(row.keys); items = [x for x in items if not (normalize_keys(x["keys"]) == key and (operation != "delete" or row.source != "Đã sửa" or x["action"] != "unbind"))]
            if operation == "delete" and row.source == "Mặc định": items.append({"keys": key, "action": "unbind", "command": "", "description": ""})
            gone = operation == "delete" and row.source in ("Mặc định", "Tùy chỉnh")
            self.save_items(items, (key, not gone))

        def save_items(self, items, check=None):
            self.pending_check = check
            try: write_bindings(items, self.backup_done); subprocess.run(["hyprctl", "reload"], timeout=3); GLib.timeout_add(500, self.after_save)
            except (OSError, subprocess.SubprocessError, ValueError) as exc: self.alert("Không thể lưu", str(exc))

        def after_save(self):
            self.reload()
            check, self.pending_check = getattr(self, "pending_check", None), None
            if check:
                keys, should_exist = check
                active = {b.keys for b in hyprctl_binds()}
                if (keys in active) != should_exist:
                    msg = (f"{keys} chưa hoạt động sau khi nạp lại. Lệnh Lua có thể sai cú pháp hoặc tên phím không đúng."
                           if should_exist else f"{keys} vẫn còn hoạt động sau khi nạp lại.")
                    self.status.set_text("Cảnh báo: " + msg); self.alert("Kiểm tra sau khi lưu", msg); return False
            self.status.set_text("Đã lưu và nạp lại Hyprland"); return False

        def edit_dialog(self, existing):
            win = Gtk.Window(title="Sửa phím tắt" if existing else "Thêm phím tắt", transient_for=self.window, modal=True, default_width=560, default_height=430); box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); box.set_margin_top(18); box.set_margin_bottom(18); box.set_margin_start(18); box.set_margin_end(18); win.set_child(box)
            mods = Gtk.Box(spacing=8); checks = {m: Gtk.CheckButton(label=m) for m in MOD_ORDER}; [mods.append(c) for c in checks.values()]; box.append(mods)
            key_entry = Gtk.Entry(placeholder_text="Phím (B, Return, F5, mouse_down)"); record = Gtk.Button(label="Ghi phím"); row = Gtk.Box(spacing=8); row.append(key_entry); row.append(record); box.append(row)
            action = Gtk.DropDown.new_from_strings(["Chạy lệnh", "Lệnh Hyprland"]); box.append(action); samples = Gtk.DropDown.new_from_strings(["Đóng cửa sổ|hl.dsp.window.close()", "Buộc đóng|hl.dsp.window.kill()", "Toàn màn hình|hl.dsp.window.fullscreen({ mode = 0 })", "Nổi/xếp|hl.dsp.window.float({ action = \"toggle\" })", "Treo pin|hl.dsp.window.pin({ action = \"toggle\" })", "Sang workspace 1|hl.dsp.focus({ workspace = 1 })", "Chuyển cửa sổ sang workspace 1|hl.dsp.window.move({ workspace = 1 })"]); samples.set_visible(False); box.append(samples); command = Gtk.Entry(placeholder_text="Lệnh shell hoặc biểu thức Lua"); description = Gtk.Entry(placeholder_text="Mô tả"); box.append(command); box.append(description)
            def on_action(*_):
                samples.set_visible(action.get_selected() == 1)
                if action.get_selected() == 1 and not command.get_text().strip(): command.set_text(samples.get_selected_item().get_string().split("|", 1)[1])
            action.connect("notify::selected", on_action); samples.connect("notify::selected", lambda *_: command.set_text(samples.get_selected_item().get_string().split("|", 1)[1]));
            if existing:
                parts = existing.keys.split(" + "); key_entry.set_text(parts[-1]); [checks[m].set_active(m in parts[:-1]) for m in MOD_ORDER]; command.set_text(existing.command); description.set_text(existing.description); action.set_selected(0 if existing.action == "exec" else 1)
            def record_key(_button):
                ctl = Gtk.EventControllerKey();
                def pressed(_c, keyval, _code, state):
                    name = Gdk.keyval_name(keyval) or ""
                    masks = {"SUPER": Gdk.ModifierType.MOD4_MASK, "CTRL": Gdk.ModifierType.CONTROL_MASK, "ALT": Gdk.ModifierType.ALT_MASK, "SHIFT": Gdk.ModifierType.SHIFT_MASK}
                    mods_state = [(m, bool(state & masks[m])) for m in MOD_ORDER]
                    if name.upper() in MOD_ORDER or not name: return True
                    key_entry.set_text(name); [checks[m].set_active(on) for m, on in mods_state]; return True
                if getattr(key_entry, "_recording", False): key_entry.grab_focus(); return
                key_entry._recording = True; ctl.connect("key-pressed", pressed); key_entry.add_controller(ctl); key_entry.grab_focus()
            record.connect("clicked", record_key)
            footer = Gtk.Box(halign=Gtk.Align.END, spacing=8); cancel = Gtk.Button(label="Hủy"); save = Gtk.Button(label="Lưu"); save.add_css_class("suggested-action"); footer.append(cancel); footer.append(save); box.append(footer); cancel.connect("clicked", lambda *_: win.close())
            def do_save(_):
                key = key_entry.get_text().strip(); keys = " + ".join([m for m in MOD_ORDER if checks[m].get_active()] + [key]) if key else ""
                act = "exec" if action.get_selected() == 0 else "lua"; cmd = command.get_text()
                if not key or (act == "exec" and not cmd): self.alert("Thiếu dữ liệu", "Cần có phím và lệnh hợp lệ."); return
                try: items = parse_keybinds_lua(DATA_PATH) if DATA_PATH.exists() else []
                except ValueError as exc: self.alert("Không thể đọc file", str(exc)); return
                oldkey = existing.keys if existing else None
                clash = next((r for r in self.rows if r.keys == normalize_keys(keys) and r.keys != normalize_keys(oldkey or "\0") and not r.disabled), None)
                duplicate = clash is not None
                def commit():
                    new_items = [x for x in items if normalize_keys(x["keys"]) != normalize_keys(oldkey or "\0") and normalize_keys(x["keys"]) != normalize_keys(keys)]
                    if existing and existing.source == "Mặc định" and normalize_keys(oldkey) != normalize_keys(keys): new_items.append({"keys": oldkey, "action": "unbind", "command": "", "description": ""})
                    new_items.append({"keys": normalize_keys(keys), "action": act, "command": cmd, "description": description.get_text()}); self.save_items(new_items, (normalize_keys(keys), True)); win.close()
                if duplicate: self.confirm("Ghi đè phím tắt?", f"{normalize_keys(keys)} đang dùng cho: {clash.command or clash.description or clash.dispatcher} ({clash.source}).", commit)
                else: commit()
            save.connect("clicked", do_save); win.present()

    return 0 if Editor().run(sys.argv) == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Xem và chỉnh sửa phím tắt Hyprland")
    parser.add_argument("--list", action="store_true", help="in danh sách, không mở GUI")
    parser.add_argument("--selftest", action="store_true", help="kiểm tra parser")
    args = parser.parse_args()
    if args.selftest: return 0 if selftest() else 1
    if args.list: cli_list(); return 0
    return gui_main()


if __name__ == "__main__": sys.exit(main())
