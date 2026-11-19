#!/usr/bin/env python3
"""ani2theme.py — chuyển bộ con trỏ Windows (.ani/.cur) thành theme Linux (hyprcursor + Xcursor).

Dùng cho bộ con trỏ người dùng tự tải về (vd file zip của họa sĩ). Hình của tác giả KHÔNG đưa vào repo:
script đọc từ thư mục giải nén và cài thẳng vào ~/.local/share/icons/<tên>.

  ani2theme.py <thư mục chứa .ani/.cur> [--name Kafka-BEN] [--preview ảnh.png]

Ánh xạ tên file → con trỏ theo quy ước Windows (pointer, help, work, busy, cross, text, hand(=bút),
unavailable, vert, horz, dgn1, dgn2, move, alternate, link). Ảnh phóng "nearest" lên 32/48/64/96 để giữ nét
pixel. Hỗ trợ khung BMP 1/4/8/24/32-bit (có mặt nạ AND) và PNG nhúng.
"""

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xcursor_write as xw  # noqa: E402

SIZES = (32, 48, 64, 96)

# tên file Windows (không phân biệt hoa thường, bỏ đuôi) → (tên chuẩn, tên phụ)
MAP = {
    "pointer": ("default", ["left_ptr", "arrow", "top_left_arrow", "left-arrow", "x-cursor", "X_cursor", "context-menu"]),
    "help": ("help", ["question_arrow", "whats_this", "left_ptr_help"]),
    "work": ("progress", ["left_ptr_watch", "half-busy"]),
    "busy": ("wait", ["watch", "clock"]),
    "cross": ("crosshair", ["cross", "tcross", "cell", "plus", "zoom-in", "zoom-out"]),
    "text": ("text", ["xterm", "ibeam", "vertical-text"]),
    "hand": ("pencil", ["draft", "color-picker"]),
    "unavailable": ("not-allowed", ["forbidden", "circle", "crossed_circle", "no-drop", "dnd-no-drop"]),
    "unavailiable": ("not-allowed", ["forbidden", "circle", "crossed_circle", "no-drop", "dnd-no-drop"]),
    "vert": ("ns-resize", ["sb_v_double_arrow", "v_double_arrow", "size_ver", "n-resize", "s-resize", "row-resize", "split_v", "top_side", "bottom_side"]),
    "horz": ("ew-resize", ["sb_h_double_arrow", "h_double_arrow", "size_hor", "e-resize", "w-resize", "col-resize", "split_h", "left_side", "right_side"]),
    "dgn1": ("nwse-resize", ["size_fdiag", "nw-resize", "se-resize", "top_left_corner", "bottom_right_corner", "bd_double_arrow"]),
    "dgn2": ("nesw-resize", ["size_bdiag", "ne-resize", "sw-resize", "top_right_corner", "bottom_left_corner", "fd_double_arrow"]),
    "move": ("move", ["fleur", "size_all", "all-scroll", "dnd-move", "grabbing", "closedhand"]),
    "alternate": ("up-arrow", ["center_ptr", "copy", "dnd-copy", "alias", "dnd-link"]),
    "link": ("pointer", ["hand1", "hand2", "hand", "pointing_hand", "grab", "openhand"]),
}


# ---------- đọc khung ảnh ----------
def decode_ico_entry(data):
    """Một file .cur/.ico (trong chunk icon của .ani) → (w, h, rgba, xhot, yhot) của ảnh lớn nhất."""
    _r, _t, cnt = struct.unpack("<HHH", data[:6])
    best = None
    for k in range(cnt):
        w, h, _c, _r2, hx, hy, size, off = struct.unpack("<BBBBHHII", data[6 + 16 * k:22 + 16 * k])
        w, h = w or 256, h or 256
        if best is None or w > best[0]:
            best = (w, h, hx, hy, data[off:off + size])
    w, h, hx, hy, img = best
    if img[:8] == b"\x89PNG\r\n\x1a\n":
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(img)
        tmp.close()
        try:
            w, h, rgba = xw.read_png(tmp.name)
        finally:
            os.unlink(tmp.name)
        return w, h, rgba, hx, hy
    return (*decode_bmp(img, w, h), hx, hy)


def decode_bmp(b, w, h):
    hsz, bw, bh2, _pl, bpp, comp = struct.unpack("<IiiHHI", b[:20])
    if comp not in (0, 3):
        raise ValueError(f"BMP nén kiểu {comp} chưa hỗ trợ")
    ncol = struct.unpack("<I", b[32:36])[0] or (1 << bpp if bpp <= 8 else 0)
    pal_off = hsz
    pal = [tuple(b[pal_off + 4 * i:pal_off + 4 * i + 4]) for i in range(ncol)] if bpp <= 8 else []
    px_off = pal_off + 4 * len(pal)
    stride = ((w * bpp + 31) // 32) * 4
    mstride = ((w + 31) // 32) * 4
    mask_off = px_off + stride * h
    rgba = bytearray(w * h * 4)
    has_alpha = False
    for y in range(h):
        row = b[px_off + (h - 1 - y) * stride:]
        for x in range(w):
            if bpp == 32:
                bl, g, r, a = row[4 * x:4 * x + 4]
                has_alpha = has_alpha or a
            elif bpp == 24:
                bl, g, r = row[3 * x:3 * x + 3]
                a = 255
            else:
                bit = x * bpp
                v = (row[bit // 8] >> (8 - bpp - bit % 8)) & ((1 << bpp) - 1)
                bl, g, r, _ = pal[v]
                a = 255
            i = (y * w + x) * 4
            rgba[i:i + 4] = bytes((r, g, bl, a))
    if not (bpp == 32 and has_alpha):            # dùng mặt nạ AND: bit 1 = trong suốt
        for y in range(h):
            mrow = b[mask_off + (h - 1 - y) * mstride:]
            for x in range(w):
                if (mrow[x // 8] >> (7 - x % 8)) & 1:
                    rgba[(y * w + x) * 4 + 3] = 0
    return w, h, bytes(rgba)


def read_ani(path):
    """→ list (w, h, rgba, xhot, yhot, delay_ms) theo thứ tự phát."""
    d = open(path, "rb").read()
    if d[:4] != b"RIFF" or d[8:12] != b"ACON":
        if d[2:4] == b"\x02\x00":                # .cur tĩnh
            w, h, rgba, hx, hy = decode_ico_entry(d)
            return [(w, h, rgba, hx, hy, 0)]
        raise ValueError(f"{path}: không phải .ani/.cur")
    frames, rate, seq, jif = [], None, None, 6
    pos = 12

    def walk(pos, end):
        nonlocal rate, seq, jif
        while pos + 8 <= end:
            cid = d[pos:pos + 4]
            ln = struct.unpack("<I", d[pos + 4:pos + 8])[0]
            body = d[pos + 8:pos + 8 + ln]
            if cid == b"LIST":
                walk(pos + 12, pos + 8 + ln)
            elif cid == b"anih":
                jif = struct.unpack("<9I", body[:36])[7] or 6
            elif cid == b"rate":
                rate = list(struct.unpack(f"<{ln // 4}I", body))
            elif cid == b"seq ":
                seq = list(struct.unpack(f"<{ln // 4}I", body))
            elif cid == b"icon":
                frames.append(decode_ico_entry(body))
            pos += 8 + ln + (ln & 1)
    walk(pos, len(d))
    order = seq or list(range(len(frames)))
    out = []
    for k, idx in enumerate(order):
        w, h, rgba, hx, hy = frames[idx]
        j = (rate[k] if rate and k < len(rate) else jif)
        out.append((w, h, rgba, hx, hy, round(j * 1000 / 60)))
    # gộp khung trùng liên tiếp (bộ tĩnh vẫn đóng gói 8 khung giống nhau)
    merged = []
    for f in out:
        if merged and merged[-1][2] == f[2]:
            m = merged[-1]
            merged[-1] = (*m[:5], m[5] + f[5])
        else:
            merged.append(f)
    if len(merged) == 1:
        merged = [(*merged[0][:5], 0)]
    return merged


def scale_nearest(rgba, w, h, n):
    out = bytearray(n * n * 4)
    for y in range(n):
        sy = y * h // n
        for x in range(n):
            sx = x * w // n
            out[(y * n + x) * 4:(y * n + x) * 4 + 4] = rgba[(sy * w + sx) * 4:(sy * w + sx) * 4 + 4]
    return bytes(out)


def build(src_dir, name, preview=None):
    files = {os.path.splitext(f)[0].lower(): os.path.join(src_dir, f) for f in os.listdir(src_dir)
             if f.lower().endswith((".ani", ".cur"))}
    work = tempfile.mkdtemp(prefix="ani2theme-")
    try:
        src = os.path.join(work, "src")
        os.makedirs(os.path.join(src, "hyprcursors"))
        with open(os.path.join(src, "manifest.hl"), "w") as f:
            f.write(f"name = {name}\ndescription = Chuyển từ bộ con trỏ Windows\nversion = 1.0\ncursors_directory = hyprcursors\n")
        xc = os.path.join(work, "cursors")
        os.makedirs(xc)
        prev, done, used = [], [], set()
        for key, path in sorted(files.items()):
            if key not in MAP:
                print(f"  bỏ qua {os.path.basename(path)} (không biết gán cho con trỏ nào)")
                continue
            shape, aliases = MAP[key]
            if shape in used:
                continue
            used.add(shape)
            frames = read_ani(path)
            w0, h0, _r, hx0, hy0, _d = frames[0]
            d = os.path.join(src, "hyprcursors", shape)
            os.makedirs(d)
            meta = ["resize_algorithm = nearest", f"hotspot_x = {hx0 / w0:.4f}", f"hotspot_y = {hy0 / h0:.4f}",
                    "nominal_size = 1.0"]
            xf = []
            for size in SIZES:
                for i, (w, h, rgba, hx, hy, delay) in enumerate(frames):
                    fn = f"{shape}-{size}-{i:02d}.png"
                    p = os.path.join(d, fn)
                    xw._write_png(p, size, size, scale_nearest(rgba, w, h, size))
                    meta.append(f"define_size = {size}, {fn}" + (f", {delay}" if len(frames) > 1 else ""))
                    xf.append({"size": size, "png": p, "xhot": hx * size // w, "yhot": hy * size // h, "delay": delay})
                    if size == 96 and i == 0:
                        prev.append(p)
            meta.append("define_override = " + ";".join(a for a in aliases if a != shape))
            with open(os.path.join(d, "meta.hl"), "w") as f:
                f.write("\n".join(meta) + "\n")
            xw.write_xcursor(os.path.join(xc, shape), xf)
            for a in aliases:
                if not os.path.lexists(os.path.join(xc, a)):
                    os.symlink(shape, os.path.join(xc, a))
            done.append(f"{key}→{shape} ({len(frames)} khung, điểm nóng {hx0},{hy0})")
        hout = os.path.join(work, "hout")
        os.makedirs(hout)
        p = subprocess.run(["hyprcursor-util", "--create", src, "--output", hout], capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError("hyprcursor-util lỗi:\n" + p.stdout[-800:] + p.stderr[-800:])
        out = os.path.expanduser(f"~/.local/share/icons/{name}")
        shutil.rmtree(out, ignore_errors=True)
        shutil.copytree(os.path.join(hout, os.listdir(hout)[0]), out, symlinks=True)
        shutil.copytree(xc, os.path.join(out, "cursors"), symlinks=True)
        with open(os.path.join(out, "index.theme"), "w") as f:
            f.write(f"[Icon Theme]\nName={name}\nInherits=Kafka-Cursor,Adwaita\n")
        if preview:
            subprocess.run(["magick", "montage", *prev, "-tile", "8x", "-geometry", "96x96+10+10",
                            "-background", "#6b5a7e", preview], check=True)
        print("\n".join("  " + x for x in done))
        print(f"Đã cài {name}: {len(done)} con trỏ → {out}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    src, name, preview = argv[0], "Kafka-BEN", None
    it = iter(argv[1:])
    for a in it:
        if a == "--name":
            name = next(it)
        elif a == "--preview":
            preview = next(it)
    build(src, name, preview)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
