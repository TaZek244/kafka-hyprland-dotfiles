#!/usr/bin/env python3
"""kafka-greeter — trình đăng nhập pixel cho greetd (thay ReGreet), vẽ toàn bộ bằng cairo trên lưới điểm.

  kafka-greeter.py                    chạy thật (cage + greetd, cần $GREETD_SOCK), toàn màn hình
  kafka-greeter.py --demo [--window 1600x900]   thử với greetd giả (mật khẩu: pass), không đăng nhập thật
  kafka-greeter.py --shot out.png [--window WxH] vẽ một khung hình ra PNG rồi thoát (xem trước, không cần màn hình)

Giao diện "KAFKA.SYS": nền = ảnh Kafka pixel hoá (bg-pixel.png 240x135, phóng nearest) + mưa pixel,
đồng hồ font pixel 5x7 tự vẽ (pixelfont.py), hộp đăng nhập kiểu cửa sổ game (thanh tiêu đề hồng, ảnh
đại diện avatar.png (ảnh thật, không pixel hoá), ô mật khẩu chấm vuông + con trỏ khối, chọn phiên ◀ ▶, nút ENTER).
Phím: gõ mật khẩu · Enter đăng nhập · Esc xoá · Tab đổi phiên · ↑/↓ đổi người dùng.
Nút khởi động lại/tắt máy góc phải dưới phải bấm 2 lần trong 3s.
Cài vào /usr/local/share/kafka-greeter bằng greetd/install-greetd.sh --greeter kafka (user greeter không đọc được ~).
"""

import math
import os
import random
import sys
import threading
import time
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pixelfont as pf  # noqa: E402

STATE_FILE = os.environ.get("KAFKA_GREETER_STATE", "/var/cache/kafka-greeter/state.json")
QUOTE = "LISTEN TO THE SOUND OF THE RAIN..."
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
FPS = 15


def hexc(h, a=1.0):
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)


C = {
    "edge": hexc("#140e1a"),
    "panel": hexc("#261e30", 0.94),
    "card": hexc("#30263c"),
    "hover": hexc("#4a3c59"),
    "hi": hexc("#56466a"),
    "sh": hexc("#1d1626"),
    "text": hexc("#fbf7fd"),
    "dim": hexc("#d4cade"),
    "faint": hexc("#9a8bab"),
    "pink": hexc("#c94785"),
    "pink_hi": hexc("#f08cbb"),
    "pink_sh": hexc("#962f62"),
    "pink_fg": hexc("#f08cbb"),
    "crit": hexc("#e0506e"),
    "crit_fg": hexc("#ff9aae"),
    "ok": hexc("#7fd6a8"),
    "shadow": hexc("#0b0710", 0.85),
}


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(d):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(d, f)
    except OSError:
        pass


# ---------------------------------------------------------------- mô hình (không phụ thuộc GTK)
class Model:
    def __init__(self, users, sessions, state=None):
        state = state or {}
        self.users = users or [{"name": "user", "gecos": ""}]
        self.sessions = sessions or [{"name": "Hyprland", "exec": ["start-hyprland"]}]
        names = [u["name"] for u in self.users]
        self.ui = names.index(state["user"]) if state.get("user") in names else 0
        snames = [s["name"] for s in self.sessions]
        self.si = snames.index(state["session"]) if state.get("session") in snames else 0
        self.password = ""
        self.status, self.status_kind = "ENTER PASSWORD", "info"
        self.busy = False
        self.shake_t0 = -10.0
        self.confirm = None  # ("reboot"|"poweroff", hạn)

    @property
    def user(self):
        return self.users[self.ui]

    @property
    def session(self):
        return self.sessions[self.si]

    def key_char(self, ch):
        if self.busy or not ch or not ch.isprintable() or len(self.password) >= 256:
            return
        self.password += ch

    def backspace(self):
        if not self.busy:
            self.password = self.password[:-1]

    def clear(self):
        if not self.busy:
            self.password = ""

    def cycle_session(self, d=1):
        if not self.busy:
            self.si = (self.si + d) % len(self.sessions)

    def cycle_user(self, d=1):
        if not self.busy:
            self.ui = (self.ui + d) % len(self.users)
            self.password = ""

    def power_press(self, what, now):
        """Lần 1: xin xác nhận; lần 2 trong 3s: trả về True (chạy)."""
        if self.confirm and self.confirm[0] == what and now < self.confirm[1]:
            self.confirm = None
            return True
        self.confirm = (what, now + 3.0)
        return False


# ---------------------------------------------------------------- vẽ
class Painter:
    def __init__(self, model):
        import cairo

        self.cairo = cairo
        self.m = model
        self.bg = self._load("bg-pixel.png")
        self.avatar = self._load("avatar.png")  # ảnh mặt GIỮ NÉT (người dùng: không pixel hoá), khung vẫn pixel
        self.static = None
        self.static_size = None
        self.drops = []
        self.hits = []  # [(x, y, w, h, action)]
        self.hover = None
        self.t0 = time.monotonic()

    def _load(self, name):
        try:
            return self.cairo.ImageSurface.create_from_png(os.path.join(HERE, name))
        except Exception:
            return None

    # --- lưới
    def unit(self, w, h):
        return max(2, min(w // 480, h // 270))

    def rect(self, ctx, x, y, w, h, col):
        ctx.set_source_rgba(*col)
        ctx.rectangle(x, y, w, h)
        ctx.fill()

    def frame(self, ctx, x, y, w, h, P, fill, hi, sh, edge, r=3):
        """Khung pixel: góc bậc thang r ô, viền ngoài 1 ô, mép sáng trên-trái / bóng dưới-phải 1 ô."""

        def body(inset, col):
            ctx.set_source_rgba(*col)
            i = inset
            ri = max(0, r - i)
            for k in range(ri):  # các bậc góc (hàng trên + dưới)
                cut = ri - k
                cut = int(round(ri - math.sqrt(max(0, ri * ri - (ri - k - 0.5) ** 2)))) if ri > 1 else cut
                ctx.rectangle(x + (i + cut) * P, y + (i + k) * P, w - 2 * (i + cut) * P, P)
                ctx.rectangle(x + (i + cut) * P, y + h - (i + k + 1) * P, w - 2 * (i + cut) * P, P)
            ctx.rectangle(x + i * P, y + (i + ri) * P, w - 2 * i * P, h - 2 * (i + ri) * P)
            ctx.fill()

        body(0, edge)
        body(1, sh)
        # mép sáng: phủ nửa trên-trái của lớp 1 bằng hi (vẽ khối lệch lên-trái rồi lớp fill đè)
        ctx.save()
        ctx.rectangle(x, y, w - 2 * P, h - 2 * P)
        ctx.clip()
        body(1, hi)
        ctx.restore()
        ctx.save()
        ctx.rectangle(x + 2 * P, y + 2 * P, w - 2 * P, h - 2 * P)
        ctx.clip()
        body(1, sh)
        ctx.restore()
        body(2, fill)

    # --- lớp tĩnh: nền pixel + làm tối viền
    def _static(self, w, h):
        cairo = self.cairo
        surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
        ctx = cairo.Context(surf)
        if self.bg:
            bw, bh = self.bg.get_width(), self.bg.get_height()
            s = max(w / bw, h / bh)
            ctx.save()
            ctx.translate((w - bw * s) / 2, (h - bh * s) / 2)
            ctx.scale(s, s)
            ctx.set_source_surface(self.bg, 0, 0)
            ctx.get_source().set_filter(cairo.FILTER_NEAREST)
            ctx.paint()
            ctx.restore()
        else:  # không có ảnh: chạng vạng tím, dải màu bậc thang
            steps = 18
            for i in range(steps):
                k = i / (steps - 1)
                ctx.set_source_rgb(0.08 + 0.18 * k, 0.05 + 0.04 * k, 0.11 + 0.10 * k)
                ctx.rectangle(0, h * i / steps, w, h / steps + 1)
                ctx.fill()
        P = self.unit(w, h)
        # tối dần về mép theo vòng bậc thang (vignette pixel)
        rings = 10
        for i in range(rings):
            a = 0.05 * (rings - i) / rings
            ctx.set_source_rgba(0.04, 0.02, 0.06, a)
            ins = i * 6 * P
            ctx.rectangle(0, 0, w, h)
            ctx.rectangle(ins, ins, w - 2 * ins, h - 2 * ins)
            ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            ctx.fill()
        ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
        ctx.set_source_rgba(0.06, 0.03, 0.08, 0.40)
        ctx.paint()
        # đường quét ngang mờ (scanline) mỗi 2 ô
        ctx.set_source_rgba(0, 0, 0, 0.10)
        for y in range(0, h, 2 * P):
            ctx.rectangle(0, y, w, max(2, P * 3 // 5))
        ctx.fill()
        return surf

    def _rain(self, ctx, w, h, P, dt):
        target = w // (P * 6)
        while len(self.drops) < target:
            self.drops.append(
                [
                    random.randrange(0, w // P) * P,
                    random.uniform(-h, 0),
                    random.uniform(0.6, 1.4),
                    random.choice((3, 4, 5, 6)),
                ]
            )
        for d in self.drops:
            d[1] += d[2] * 70 * P * dt
            if d[1] > h:
                d[0] = random.randrange(0, w // P) * P
                d[1] = random.uniform(-h * 0.3, 0)
        for d in self.drops:
            y = int(d[1] // P) * P
            a = 0.18 + 0.22 * (d[2] - 0.6) / 0.8
            ctx.set_source_rgba(0.94, 0.55, 0.73, a)
            ctx.rectangle(d[0], y, P, d[3] * P)
            ctx.fill()
            ctx.set_source_rgba(1, 0.85, 0.93, a + 0.15)
            ctx.rectangle(d[0], y + d[3] * P, P, P)
            ctx.fill()

    def hit(self, x, y, w, h, action):
        self.hits.append((x, y, w, h, action))

    def text_center(self, ctx, s, cx, y, cell, col, shadow=True):
        pf.draw_text(ctx, s, cx - pf.text_width(s, cell) // 2, y, cell, col, C["shadow"] if shadow else None)

    def draw(self, ctx, w, h, dt=1 / FPS):
        P = self.unit(w, h)
        now = time.monotonic()
        t = now - self.t0
        if self.static is None or self.static_size != (w, h):
            self.static = self._static(w, h)
            self.static_size = (w, h)
        ctx.set_source_surface(self.static, 0, 0)
        ctx.paint()
        self._rain(ctx, w, h, P, dt)
        self.hits = []
        m = self.m

        # ---- đồng hồ
        lt = time.localtime()
        clock = time.strftime("%H:%M", lt)
        cy = int(h * 0.10) // P * P
        self.text_center(ctx, clock, w // 2, cy, 3 * P, C["text"])
        date = f"{DAYS[lt.tm_wday]}  {lt.tm_mday:02d}.{lt.tm_mon:02d}.{lt.tm_year}"
        self.text_center(ctx, date, w // 2, cy + 7 * 3 * P + 4 * P, P, C["dim"])

        # ---- hộp đăng nhập: lưới riêng to hơn nền một bậc (P0 = lưới nền, P = lưới hộp)
        P0 = P
        P = P0 + max(1, P0 // 4)
        DW, DH = 140 * P, 86 * P
        shake = 0
        st = now - m.shake_t0
        if st < 0.45:
            shake = int(math.sin(st * 45) * (1 - st / 0.45) * 3) * P
        dx = (w - DW) // 2 // P * P + shake
        dy = (h - DH) // 2 // P * P + 12 * P
        # bóng đổ cứng
        self.rect(ctx, dx + 2 * P, dy + 2 * P, DW, DH, (0.04, 0.02, 0.06, 0.55))
        self.frame(ctx, dx, dy, DW, DH, P, C["panel"], C["hi"], C["sh"], C["edge"], r=4)
        # thanh tiêu đề
        tb = (dx + 2 * P, dy + 2 * P, DW - 4 * P, 11 * P)
        self.frame(ctx, *tb, P, C["pink"], C["pink_hi"], C["pink_sh"], hexc("#3d1028"), r=2)
        ic = max(2, P * 3 // 5)
        pf.draw_icon(ctx, "spider", tb[0] + 4 * P, tb[1] + (11 * P - 9 * ic) // 2, ic, C["text"])
        title_cell = max(2, P * 3 // 5)
        pf.draw_text(
            ctx,
            "KAFKA.SYS // LOGIN",
            tb[0] + 6 * P + 9 * ic,
            tb[1] + (11 * P - 7 * title_cell) // 2,
            title_cell,
            C["text"],
            hexc("#3d1028"),
        )
        for i, col in enumerate((C["text"], C["text"], C["text"])):
            bx = tb[0] + tb[2] - (5 + i * 5) * P
            self.rect(ctx, bx, tb[1] + 4 * P, 3 * P, 3 * P, hexc("#3d1028"))
            self.rect(ctx, bx, tb[1] + 4 * P, 2 * P, 2 * P, (1, 1, 1, 0.85 - i * 0.25))

        # ảnh đại diện
        ax, ay, AS = dx + 8 * P, dy + 20 * P, 40 * P
        self.rect(ctx, ax - 2 * P, ay - 2 * P, AS + 4 * P, AS + 4 * P, C["edge"])
        self.rect(ctx, ax - P, ay - P, AS + 2 * P, AS + 2 * P, C["pink"])
        if self.avatar:
            ctx.save()
            ctx.translate(ax, ay)
            ctx.scale(AS / self.avatar.get_width(), AS / self.avatar.get_height())
            ctx.set_source_surface(self.avatar, 0, 0)
            ctx.get_source().set_filter(self.cairo.FILTER_BEST)
            ctx.paint()
            ctx.restore()
        else:
            self.rect(ctx, ax, ay, AS, AS, C["card"])
            pf.draw_icon(ctx, "spider", ax + (AS - 9 * 3 * P) // 2, ay + (AS - 9 * 3 * P) // 2, 3 * P, C["pink_fg"])
        # nhãn "trực tuyến" nhấp nháy dưới ảnh
        on = int(t * 2) % 2 == 0
        self.rect(ctx, ax, ay + AS + 4 * P, 2 * P, 2 * P, C["ok"] if on else hexc("#3f7a5c"))
        pf.draw_text(ctx, "ONLINE", ax + 4 * P, ay + AS + 4 * P - P // 2, max(2, P * 3 // 5), C["faint"])

        # cột phải
        rx = dx + 56 * P
        rw = DW - 56 * P - 8 * P
        name = m.user["name"]
        multi = len(m.users) > 1
        ny = dy + 20 * P
        nx = rx + (5 * P if multi else 0)
        pf.draw_text(ctx, name, nx, ny, P, C["text"], C["shadow"])
        if multi:
            self._arrow(ctx, "<", rx, ny + P, P, "user-", now)
            self._arrow(ctx, ">", nx + pf.text_width(name, P) + 2 * P, ny + P, P, "user+", now)
        sub = (m.user.get("gecos") or "STELLARON HUNTER").split(",")[0][:24]
        pf.draw_text(ctx, sub, rx, ny + 10 * P, max(2, P * 3 // 5), C["faint"])

        # ô mật khẩu
        py_ = dy + 37 * P
        ph = 12 * P
        self.rect(ctx, rx, py_, rw, ph, C["edge"])
        self.rect(ctx, rx + P, py_ + P, rw - 2 * P, ph - 2 * P, C["card"])
        self.rect(ctx, rx + P, py_ + P, rw - 2 * P, P, C["sh"])
        focus_col = C["crit"] if m.status_kind == "error" and st < 2 else C["pink"]
        self.rect(ctx, rx, py_ + ph, rw, P // 2 or 1, focus_col)
        cx0 = rx + 4 * P
        n = len(m.password)
        maxdots = (rw - 10 * P) // (4 * P)
        for i in range(min(n, maxdots)):
            self.rect(ctx, cx0 + i * 4 * P, py_ + 5 * P, 2 * P, 2 * P, C["text"])
        if n == 0 and not m.busy:
            pf.draw_text(ctx, "PASSWORD", cx0, py_ + (ph - 7 * max(2, P * 3 // 5)) // 2, max(2, P * 3 // 5), C["faint"])
        if not m.busy and int(t * 2.2) % 2 == 0:
            curx = cx0 + min(n, maxdots) * 4 * P + (0 if n else pf.text_width("PASSWORD", max(2, P * 3 // 5)) + 2 * P)
            self.rect(ctx, curx, py_ + 3 * P, P, 6 * P, C["pink_fg"])
        if m.busy:  # thanh chờ chạy ngang
            k = (t * 1.4) % 1.0
            bw_ = rw // 4
            bx = rx + P + int((rw - 2 * P - bw_) * k) // P * P
            self.rect(ctx, bx, py_ + ph - 3 * P, bw_, P, C["pink_fg"])

        # chọn phiên
        sy = dy + 53 * P
        sc = max(2, P * 3 // 5)
        pf.draw_text(ctx, "SESSION", rx, sy, sc, C["faint"])
        sname = m.session["name"][:22]
        vy = sy + 6 * P
        self._arrow(ctx, "<", rx, vy, P, "sess-", now, cell=sc)
        pf.draw_text(ctx, sname, rx + 5 * P, vy, sc, C["dim"], C["shadow"])
        self._arrow(ctx, ">", rx + 5 * P + pf.text_width(sname, sc) + 2 * P, vy, P, "sess+", now, cell=sc)

        # nút ENTER
        bw, bh = 32 * P, 11 * P
        bx, by = rx + rw - bw, dy + 55 * P
        hov = self.hover == "login"
        self.frame(
            ctx,
            bx,
            by,
            bw,
            bh,
            P,
            hexc("#d9568f") if hov else C["pink"],
            C["pink_hi"],
            C["pink_sh"],
            hexc("#3d1028"),
            r=2,
        )
        self.text_center(ctx, "> ENTER", bx + bw // 2, by + (bh - 7 * sc) // 2, sc, C["text"], False)
        self.hit(bx, by, bw, bh, "login")

        # dòng trạng thái
        col = {"error": C["crit_fg"], "ok": C["ok"], "busy": C["pink_fg"]}.get(m.status_kind, C["faint"])
        msg = m.status
        if m.busy:
            msg += "." * (int(t * 3) % 4)
        pf.draw_text(ctx, msg[:40], rx, dy + 70 * P, sc, col)
        pf.draw_text(ctx, "TAB: SESSION  ESC: CLEAR", dx + 8 * P, dy + DH - 7 * P, sc, hexc("#6f6283"))

        P = P0
        sc = max(2, P * 3 // 5)
        # ---- câu thoại gõ dần, góc trái dưới
        k = min(len(QUOTE), int(t * 14))
        q = QUOTE[:k] + ("_" if int(t * 2) % 2 == 0 else " ")
        pf.draw_text(ctx, q, 8 * P, h - 14 * P, max(2, P * 3 // 4), C["dim"], C["shadow"])

        # ---- nút nguồn, góc phải dưới
        S = 14 * P
        for i, what in enumerate(("poweroff", "reboot")):
            x = w - (8 + 16 * (i + 1)) * P + 2 * P
            y = h - 8 * P - S
            hov = self.hover == what
            armed = m.confirm and m.confirm[0] == what and now < m.confirm[1]
            fill = C["crit"] if armed else (C["hover"] if hov else C["card"])
            self.frame(ctx, x, y, S, S, P, fill, C["crit_fg"] if armed else C["hi"], C["sh"], C["edge"], r=2)
            ic = max(1, P)
            pf.draw_icon(
                ctx,
                "power" if what == "poweroff" else "reboot",
                x + (S - 9 * ic) // 2,
                y + (S - 9 * ic) // 2,
                ic,
                C["text"],
            )
            self.hit(x, y, S, S, what)
        if m.confirm and now < m.confirm[1]:
            lab = "CLICK AGAIN TO " + ("SHUT DOWN" if m.confirm[0] == "poweroff" else "REBOOT")
            pf.draw_text(
                ctx, lab, w - 8 * P - pf.text_width(lab, sc), h - 8 * P - S - 8 * P, sc, C["crit_fg"], C["shadow"]
            )

    def _arrow(self, ctx, ch, x, y, P, action, now, cell=None):
        cell = cell or P
        hov = self.hover == action
        pf.draw_text(ctx, ch, x, y, cell, C["pink_fg"] if hov else C["faint"])
        self.hit(x - P, y - P, pf.text_width(ch, cell) + 2 * P, 7 * cell + 2 * P, action)

    def at(self, x, y):
        for hx, hy, hw, hh, a in reversed(self.hits):
            if hx <= x < hx + hw and hy <= y < hy + hh:
                return a
        return None


# ---------------------------------------------------------------- ứng dụng GTK
def run(args):
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib, Gtk
    import greetd_ipc as ipc

    demo = "--demo" in args
    size = None
    if "--window" in args:
        ww, hh = args[args.index("--window") + 1].split("x")
        size = (int(ww), int(hh))

    mock = None
    if demo:
        me = os.environ.get("USER", "kafka")
        users = [
            {"name": me, "uid": 1000, "gecos": "Stellaron Hunter", "home": ""},
            {"name": "kafka", "uid": 1001, "gecos": "", "home": ""},
        ]
        sessions = ipc.list_sessions() or [{"name": "Hyprland", "exec": ["start-hyprland"]}]
        mock = ipc.MockGreetd(users={me: "pass", "kafka": "pass"})
        sock = mock.start()
        state = {}
    else:
        users, sessions, sock, state = ipc.list_users(), ipc.list_sessions(), None, load_state()

    model = Model(users, sessions, state)
    painter = Painter(model)

    win = Gtk.Window(title="kafka-greeter")
    win.set_app_paintable(True)
    area = Gtk.DrawingArea()
    area.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
    win.add(area)
    last = [time.monotonic()]

    def on_draw(_w, ctx):
        now = time.monotonic()
        painter.draw(ctx, area.get_allocated_width(), area.get_allocated_height(), min(0.2, now - last[0]))
        last[0] = now
        return False

    def tick():
        area.queue_draw()
        return True

    def finish_ok():
        if not demo:
            save_state({"user": model.user["name"], "session": model.session["name"]})
        if demo:
            print("DEMO: đăng nhập OK →", getattr(mock, "started", None))
        GLib.timeout_add(700, lambda: Gtk.main_quit() or False)

    def do_login():
        if model.busy:
            return
        if not model.password:
            model.status, model.status_kind = "PASSWORD IS EMPTY", "error"
            model.shake_t0 = time.monotonic()
            return
        model.busy = True
        model.status, model.status_kind = "AUTHENTICATING", "busy"
        user, pw, cmd = model.user["name"], model.password, model.session["exec"]
        model.password = ""

        def worker():
            try:
                cli = ipc.GreetdClient(sock)
                try:
                    cli.login(user, pw, cmd, [])
                finally:
                    cli.close()
                GLib.idle_add(done, None)
            except ipc.GreetdError as e:
                GLib.idle_add(done, e)
            except Exception as e:  # noqa: BLE001 — không để greeter chết vì lỗi lạ
                GLib.idle_add(done, ipc.GreetdError("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def done(err):
        model.busy = False
        if err is None:
            model.status, model.status_kind = f"WELCOME BACK, {model.user['name']}", "ok"
            finish_ok()
        else:
            auth = getattr(err, "error_type", "") == "auth_error"
            model.status = "ACCESS DENIED" if auth else ("ERROR: " + str(getattr(err, "description", err)))[:40]
            model.status_kind = "error"
            model.shake_t0 = time.monotonic()
        return False

    def power(what):
        if demo:
            model.status, model.status_kind = f"DEMO: {what.upper()}", "info"
            return
        GLib.spawn_async(["systemctl", what], flags=GLib.SpawnFlags.SEARCH_PATH)

    def act(a):
        if a == "login":
            do_login()
        elif a in ("sess-", "sess+"):
            model.cycle_session(-1 if a.endswith("-") else 1)
        elif a in ("user-", "user+"):
            model.cycle_user(-1 if a.endswith("-") else 1)
        elif a in ("poweroff", "reboot"):
            if model.power_press(a, time.monotonic()):
                power(a)
        area.queue_draw()

    def on_key(_w, ev):
        k = ev.keyval
        name = Gdk.keyval_name(k) or ""
        ctrl = ev.state & Gdk.ModifierType.CONTROL_MASK
        if name in ("Return", "KP_Enter"):
            do_login()
        elif name == "BackSpace":
            model.backspace()
        elif name == "Escape" or (ctrl and name.lower() == "u"):
            model.clear()
        elif name in ("Tab", "ISO_Left_Tab"):
            model.cycle_session(-1 if name == "ISO_Left_Tab" else 1)
        elif name in ("Up", "Down"):
            model.cycle_user(-1 if name == "Up" else 1)
        elif not ctrl:
            u = Gdk.keyval_to_unicode(k)
            if u:
                model.key_char(chr(u))
        if model.status_kind == "error" and not model.busy and name not in ("Return", "KP_Enter"):
            model.status, model.status_kind = "ENTER PASSWORD", "info"
        area.queue_draw()
        return True

    def on_motion(_w, ev):
        a = painter.at(ev.x, ev.y)
        if a != painter.hover:
            painter.hover = a
            win.get_window().set_cursor(Gdk.Cursor.new_from_name(win.get_display(), "pointer" if a else "default"))
        return False

    def on_press(_w, ev):
        if ev.button == 1:
            a = painter.at(ev.x, ev.y)
            if a:
                act(a)
        return True

    area.connect("draw", on_draw)
    area.connect("motion-notify-event", on_motion)
    area.connect("button-press-event", on_press)
    win.connect("key-press-event", on_key)
    win.connect("destroy", Gtk.main_quit)
    if size:
        win.set_default_size(*size)
    else:
        win.fullscreen()
    win.show_all()
    GLib.timeout_add(1000 // FPS, tick)
    if demo and "--autotype" in args:  # thử luồng đăng nhập không cần bàn phím: --autotype "sai,pass"
        tries = args[args.index("--autotype") + 1].split(",")

        def auto(i=0):
            if i < len(tries):
                model.password = tries[i]
                do_login()
                GLib.timeout_add(2500, lambda: auto(i + 1) or False)

        GLib.timeout_add(1500, lambda: auto() or False)
    try:
        Gtk.main()
    finally:
        if mock:
            mock.stop()


def shot(args):
    """Vẽ 1 khung ra PNG (không cần màn hình) để xem trước."""
    import cairo

    out = args[args.index("--shot") + 1]
    w, h = 1920, 1080
    if "--window" in args:
        w, h = (int(v) for v in args[args.index("--window") + 1].split("x"))
    sys.path.insert(0, HERE)
    try:
        import greetd_ipc as ipc

        sessions = ipc.list_sessions()
    except Exception:
        sessions = []
    m = Model([{"name": os.environ.get("USER", "kafka"), "gecos": ""}], sessions)
    m.password = "secret" if "--typed" in args else ""
    if "--error" in args:
        m.status, m.status_kind = "ACCESS DENIED", "error"
    p = Painter(m)
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
    ctx = cairo.Context(surf)
    for _ in range(40):  # cho mưa rơi vào khung hình
        p.draw(ctx, w, h, 1 / FPS)
    p.t0 -= 10  # câu thoại đã gõ xong
    p.draw(ctx, w, h, 1 / FPS)
    surf.write_to_png(out)
    print(out)


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS: " if cond else "FAIL: ") + name)
        ok = ok and cond

    m = Model(
        [{"name": "a"}, {"name": "b"}],
        [{"name": "S1", "exec": ["x"]}, {"name": "S2", "exec": ["y"]}],
        {"user": "b", "session": "S2"},
    )
    check("nhớ người dùng/phiên cũ", m.user["name"] == "b" and m.session["name"] == "S2")
    m.key_char("p")
    m.key_char("w")
    m.key_char("\x07")
    check("gõ ký tự in được, bỏ ký tự điều khiển", m.password == "pw")
    m.backspace()
    check("backspace", m.password == "p")
    m.cycle_user(1)
    check("đổi người dùng xoá mật khẩu", m.user["name"] == "a" and m.password == "")
    m.cycle_session(1)
    check("xoay vòng phiên", m.session["name"] == "S1")
    check("nút nguồn bấm 1 lần chỉ xin xác nhận", m.power_press("reboot", 100.0) is False)
    check("bấm lần 2 trong 3s thì chạy", m.power_press("reboot", 101.0) is True)
    m.power_press("poweroff", 200.0)
    check("quá 3s phải xác nhận lại", m.power_press("poweroff", 204.0) is False)
    m2 = Model([], [], {"user": "zzz"})
    check("danh sách rỗng vẫn có mặc định", m2.user["name"] and m2.session["exec"])
    check(
        "font có đủ chữ cho giao diện", all(ch in pf.GLYPHS for ch in "KAFKA.SYS // LOGIN ENTER PASSWORD:0123456789<>")
    )
    print("selftest", "ok" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--selftest" in a:
        sys.exit(selftest())
    if "--shot" in a:
        shot(a)
        sys.exit(0)
    run(a)
