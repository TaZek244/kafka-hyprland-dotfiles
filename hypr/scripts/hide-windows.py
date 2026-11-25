#!/usr/bin/env python3
"""Ẩn/hiện cửa sổ Hyprland bằng workspace đặc biệt."""

import html
import json
import os
import subprocess
import sys


HIDDEN_WS = "special:hidden"
ROFI_GLYPH = "\U000f0613"
VISIBLE_GLYPH = "\U000f0208"
HIDDEN_GLYPH = "\U000f0209"


def run(args, stdin=None, timeout=3):
    """Chạy lệnh an toàn, trả về CompletedProcess hoặc None.
    timeout=None cho lệnh chờ người dùng (rofi), không thì menu tự đóng sau 3s."""
    try:
        return subprocess.run(
            args,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"hide-windows: {exc}", file=sys.stderr)
        return None


def hypr_json(*args):
    result = run(["hyprctl", *args])
    if result is None or result.returncode != 0:
        if result and result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        return None
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"hide-windows: JSON không hợp lệ: {exc}", file=sys.stderr)
        return None


def is_special(ws_name):
    return isinstance(ws_name, str) and ws_name.startswith("special:")


def filtered_clients():
    clients = hypr_json("clients", "-j")
    if not isinstance(clients, list):
        return None
    result = []
    for client in clients:
        if not isinstance(client, dict) or client.get("mapped", True) is False:
            continue
        cls = client.get("class") or ""
        if not cls or cls == "kafka-cava":
            continue
        workspace = client.get("workspace")
        ws_name = workspace.get("name") if isinstance(workspace, dict) else ""
        if is_special(ws_name) and ws_name != HIDDEN_WS:
            continue
        if not client.get("address"):
            continue
        result.append(client)
    return result


def sort_clients(clients):
    return sorted(
        clients,
        key=lambda c: (
            c.get("workspace", {}).get("name") == HIDDEN_WS if isinstance(c.get("workspace"), dict) else False,
            c.get("focusHistoryID", 0),
        ),
    )


def is_hidden(client):
    ws = client.get("workspace")
    return isinstance(ws, dict) and ws.get("name") == HIDDEN_WS


def safe_text(value):
    return html.escape(str(value or ""), quote=False)


def limited_text(value, limit):
    return safe_text(str(value or "")[:limit])


def row_for(client):
    cls = safe_text(client.get("class"))
    title = limited_text(client.get("title") or client.get("class"), 60)
    if is_hidden(client):
        return f"<span foreground='#7d6f90'>{HIDDEN_GLYPH}  <b>{cls}</b>  · ẩn · {title}</span>"
    ws = client.get("workspace", {})
    ws_name = ws.get("name", "") if isinstance(ws, dict) else ""
    return (
        f"<span foreground='#a8e6cf'>{VISIBLE_GLYPH}</span>  <b>{cls}</b>  "
        f"<span foreground='#a99bbd'>· {safe_text(ws_name)} · {title}</span>"
    )


def dispatch_move(address, workspace):
    expr = (
        f"hl.dsp.window.move({{ workspace = {json.dumps(workspace, ensure_ascii=False)}, "
        f"window = {json.dumps('address:' + address, ensure_ascii=False)}, follow = false }})"
    )
    result = run(["hyprctl", "dispatch", expr])
    if result is None or result.returncode != 0:
        if result and result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        return False
    return True


def notify_waybar():
    run(["pkill", "-RTMIN+11", "-x", "waybar"])


def active_workspace():
    data = hypr_json("activeworkspace", "-j")
    return data.get("name") if isinstance(data, dict) else None


def show_client(client, workspace):
    return dispatch_move(str(client.get("address")), workspace)


def menu():
    probe = run(["pidof", "rofi"])
    if probe and probe.returncode == 0:
        run(["pkill", "-x", "rofi"])
        return

    selected_address = None
    selected_row = 0
    while True:
        clients = filtered_clients()
        if clients is None:
            return
        clients = sort_clients(clients)
        if not clients:
            run(["notify-send", "Kafka", "Không có cửa sổ nào đang mở."])
            return
        rows = [row_for(client) for client in clients]
        if selected_address:
            selected_row = next((i for i, c in enumerate(clients) if str(c.get("address")) == selected_address), 0)
        hidden_count = sum(is_hidden(client) for client in clients)
        message = f"Bấm để ẩn ⇄ hiện · Esc để xong · đang ẩn: {hidden_count}"
        rofi = run(
            [
                "rofi",
                "-dmenu",
                "-i",
                "-markup-rows",
                "-format",
                "i",
                "-no-custom",
                "-selected-row",
                str(selected_row),
                "-p",
                f"{ROFI_GLYPH}  Ẩn/hiện",
                "-mesg",
                message,
                "-theme",
                os.path.expanduser("~/.config/rofi/kafka.rasi"),
                "-theme-str",
                'entry { placeholder: "  Lọc cửa sổ..."; }',
            ],
            "\n".join(rows) + "\n",
            timeout=None,
        )
        if rofi is None or rofi.returncode != 0 or not rofi.stdout.strip():
            return
        try:
            index = int(rofi.stdout.strip().splitlines()[0])
            client = clients[index]
        except (ValueError, IndexError):
            return
        selected_address = str(client.get("address"))
        if is_hidden(client):
            workspace = active_workspace()
            changed = workspace is not None and show_client(client, workspace)
        else:
            changed = dispatch_move(selected_address, HIDDEN_WS)
        if changed:
            notify_waybar()


def hide_active():
    client = hypr_json("activewindow", "-j")
    if not isinstance(client, dict) or not client:
        return
    clients = filtered_clients()
    if clients is None:
        return
    address = str(client.get("address", ""))
    target = next((c for c in clients if str(c.get("address")) == address), None)
    if target and not is_hidden(target) and dispatch_move(address, HIDDEN_WS):
        notify_waybar()


def show_all():
    clients = filtered_clients()
    workspace = active_workspace() if clients is not None else None
    if not clients or workspace is None:
        return
    hidden = [c for c in clients if is_hidden(c)]
    if not hidden:
        return
    expressions = []
    for client in hidden:
        address = json.dumps("address:" + str(client.get("address")), ensure_ascii=False)
        target = json.dumps(workspace, ensure_ascii=False)
        expressions.append(
            f"dispatch hl.dsp.window.move({{ workspace = {target}, window = {address}, follow = false }})"
        )
    result = run(["hyprctl", "--batch", "; ".join(expressions)])
    if result is None or result.returncode != 0:
        if result and result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        return
    notify_waybar()


def status():
    clients = filtered_clients()
    hidden = [c for c in clients or [] if is_hidden(c)]
    lines = [f"Đang ẩn {len(hidden)} cửa sổ:"]
    for client in hidden:
        cls = safe_text(client.get("class"))
        title = limited_text(client.get("title") or client.get("class"), 40)
        lines.append(f"• {cls} — {title}")
    lines.append("Trái: chọn ẩn/hiện (Super + O) · Phải: hiện lại tất cả")
    count = len(hidden)
    payload = {
        "text": HIDDEN_GLYPH + (f" {count}" if count else ""),  # mắt gạch chéo: dễ hiểu là "ẩn"
        "class": "has" if count else "none",
        "tooltip": "\n".join(lines),
    }
    print(json.dumps(payload, ensure_ascii=False))


def main():
    commands = {"menu": menu, "hide-active": hide_active, "show-all": show_all, "status": status}
    command = sys.argv[1] if len(sys.argv) > 1 else "menu"
    commands.get(command, lambda: print(f"Lệnh không hợp lệ: {command}", file=sys.stderr))()


if __name__ == "__main__":
    main()
