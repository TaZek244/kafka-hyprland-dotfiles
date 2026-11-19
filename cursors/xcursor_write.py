#!/usr/bin/env python3
"""xcursor_write.py — ghi file con trỏ Xcursor từ PNG (thay cho xcursorgen, máy không có). Chỉ thư viện chuẩn.

API:  read_png(path) -> (w, h, rgba_bytes)
      write_xcursor(out, [{"size", "png", "xhot", "yhot", "delay"}, ...])   (nhiều cỡ + nhiều khung động)
      parse_xcursor(path) -> list dict (để kiểm tra)
CLI:  xcursor_write.py <out> <size>:<png>:<xhot>:<yhot>[:<delay>] ...   ·   --selftest
"""

import os
import struct
import sys
import tempfile
import zlib

IMAGE_TYPE = 0xFFFD0002


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def read_png(path):
    """Đọc PNG 8-bit RGBA (color type 6) hoặc RGB (2), không xen kẽ → (w, h, bytes RGBA)."""
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: không phải PNG")
    pos, idat, w = 8, b"", None
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ctype, _c, _f, inter = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or inter:
                raise ValueError(f"{path}: chỉ hỗ trợ PNG 8-bit RGB/RGBA không xen kẽ")
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    bpp = 4 if ctype == 6 else 3
    raw = zlib.decompress(idat)
    stride = w * bpp
    out = bytearray()
    prev = bytearray(stride)
    i = 0
    for _ in range(h):
        ft = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if ft == 1:
                line[x] = (line[x] + a) & 0xFF
            elif ft == 2:
                line[x] = (line[x] + b) & 0xFF
            elif ft == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 0xFF
            elif ft == 4:
                line[x] = (line[x] + _paeth(a, b, c)) & 0xFF
        prev = line
        if bpp == 4:
            out += line
        else:
            for x in range(w):
                out += line[x * 3:x * 3 + 3] + b"\xff"
    return w, h, bytes(out)


def _argb_premul(rgba):
    px = []
    for k in range(0, len(rgba), 4):
        r, g, b, a = rgba[k:k + 4]
        px.append((a << 24) | (((r * a + 127) // 255) << 16) | (((g * a + 127) // 255) << 8) | ((b * a + 127) // 255))
    return struct.pack(f"<{len(px)}I", *px)


def write_xcursor(out_path, frames):
    imgs = []
    for f in sorted(frames, key=lambda f: f["size"]):        # sort ổn định: giữ thứ tự khung trong cùng cỡ
        w, h, rgba = read_png(f["png"])
        xh = max(0, min(int(f["xhot"]), w - 1))
        yh = max(0, min(int(f["yhot"]), h - 1))
        chunk = struct.pack("<9I", 36, IMAGE_TYPE, int(f["size"]), 1, w, h, xh, yh, int(f.get("delay", 0))) + _argb_premul(rgba)
        imgs.append((int(f["size"]), chunk))
    n = len(imgs)
    pos = 16 + 12 * n
    head = struct.pack("<4sIII", b"Xcur", 16, 0x10000, n)
    toc, body = b"", b""
    for size, chunk in imgs:
        toc += struct.pack("<III", IMAGE_TYPE, size, pos)
        body += chunk
        pos += len(chunk)
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(head + toc + body)
    os.replace(tmp, out_path)


def parse_xcursor(path):
    d = open(path, "rb").read()
    magic, hs, ver, n = struct.unpack("<4sIII", d[:16])
    if magic != b"Xcur":
        raise ValueError("sai magic")
    res = []
    for k in range(n):
        typ, sub, pos = struct.unpack("<III", d[16 + 12 * k:28 + 12 * k])
        _hl, _t, size, _v, w, h, xh, yh, delay = struct.unpack("<9I", d[pos:pos + 36])
        pix = struct.unpack(f"<{w * h}I", d[pos + 36:pos + 36 + 4 * w * h])
        res.append({"toc_size": sub, "size": size, "w": w, "h": h, "xhot": xh, "yhot": yh, "delay": delay, "pixels": pix})
    return res


# ---------- kiểm thử ----------
def _write_png(path, w, h, rgba, filt=0):
    """PNG RGBA tối giản, mã hoá mọi hàng bằng bộ lọc filt (0 None, 1 Sub, 4 Paeth)."""
    stride, raw, prev = w * 4, b"", bytes(w * 4)
    for y in range(h):
        line = rgba[y * stride:(y + 1) * stride]
        enc = bytearray()
        for x in range(stride):
            a = line[x - 4] if x >= 4 else 0
            b, c = prev[x], (prev[x - 4] if x >= 4 else 0)
            pred = {0: 0, 1: a, 4: _paeth(a, b, c)}[filt]
            enc.append((line[x] - pred) & 0xFF)
        raw += bytes([filt]) + bytes(enc)
        prev = line

    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name)
        ok = ok and bool(cond)
    with tempfile.TemporaryDirectory() as t:
        px = bytes([255, 0, 0, 128, 0, 255, 0, 255, 10, 20, 30, 0, 200, 100, 50, 64])
        for f in (0, 1, 4):
            p = os.path.join(t, f"a{f}.png")
            _write_png(p, 2, 2, px, f)
            check(f"read_png bộ lọc {f}", read_png(p) == (2, 2, px))
        big = bytes((x * 7 + y * 13 + c * 29) & 0xFF for y in range(5) for x in range(4) for c in range(4))
        p4 = os.path.join(t, "b.png")
        _write_png(p4, 4, 5, big, 4)
        check("read_png Paeth 4x5", read_png(p4) == (4, 5, big))
        out = os.path.join(t, "cur")
        write_xcursor(out, [{"size": 32, "png": p4, "xhot": 9, "yhot": 1, "delay": 50},
                            {"size": 24, "png": os.path.join(t, "a0.png"), "xhot": 1, "yhot": 1, "delay": 70},
                            {"size": 24, "png": os.path.join(t, "a1.png"), "xhot": 0, "yhot": 0, "delay": 70}])
        r = parse_xcursor(out)
        check("magic + ntoc", len(r) == 3)
        check("sắp theo cỡ, giữ thứ tự khung", [x["size"] for x in r] == [24, 24, 32] and r[0]["xhot"] == 1 and r[1]["xhot"] == 0)
        check("toc subtype = size", all(x["toc_size"] == x["size"] for x in r))
        check("kẹp hotspot", r[2]["xhot"] == 3 and r[2]["yhot"] == 1)
        check("delay", r[0]["delay"] == 70 and r[2]["delay"] == 50)
        check("premultiplied (255,0,0,128) → 0x80800000", r[0]["pixels"][0] == 0x80800000)
        check("alpha 0 → 0", r[0]["pixels"][2] == 0)
    return 0 if ok else 1


def main(argv):
    if argv[:1] == ["--selftest"]:
        return selftest()
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    frames = []
    for spec in argv[1:]:
        parts = spec.split(":")
        if len(parts) not in (4, 5):
            print(f"sai cú pháp: {spec} (cần size:png:xhot:yhot[:delay])", file=sys.stderr)
            return 2
        frames.append({"size": int(parts[0]), "png": parts[1], "xhot": int(parts[2]), "yhot": int(parts[3]),
                       "delay": int(parts[4]) if len(parts) == 5 else 0})
    write_xcursor(argv[0], frames)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
