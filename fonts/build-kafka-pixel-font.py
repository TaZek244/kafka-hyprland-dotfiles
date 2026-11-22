#!/usr/bin/env python3
"""build-kafka-pixel-font.py — Trình dựng font TrueType (.ttf) "Kafka Pixel".

Dựng trực tiếp file .ttf từ bộ chữ bitmap 5×7 có sẵn trong
greetd/kafka-greeter/pixelfont.py chỉ bằng thư viện chuẩn Python (struct, os, sys...).
Không phụ thuộc fontTools hay công cụ bên ngoài.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

# Thêm đường dẫn ../greetd/kafka-greeter (tính từ vị trí script) vào sys.path để import pixelfont
SCRIPT_DIR = Path(__file__).resolve().parent
GREETER_DIR = SCRIPT_DIR.parent / "greetd" / "kafka-greeter"
if str(GREETER_DIR) not in sys.path:
    sys.path.insert(0, str(GREETER_DIR))

import pixelfont  # noqa: E402

# Hằng số thiết kế font (mặc định cho KafkaPixel.ttf — KHÔNG ĐƯỢC THAY ĐỔI)
UNITS_PER_EM = 700   # 7 ô = 1 em → cỡ 14px = mỗi điểm 2px, 21px = 3px, 28px = 4px (chữ sắc, không nhoè)
CELL_SIZE = 100
ADVANCE_WIDTH = 600  # (GW=5 + GAP=1) * 100
ASCENDER = 800
DESCENDER = -100   # dòng = 900/700 em: 14px → 18px, không làm thanh Waybar cao thêm
LINE_GAP = 0
CAP_HEIGHT = 700
X_HEIGHT = 700
EPOCH_1904_OFFSET = 2082844800  # Số giây từ 1904-01-01 00:00:00 đến 1970-01-01 00:00:00 UTC
SFNT_VERSION = 0x00010000
CHECKSUM_MAGIC = 0xB1B0AFBA

# Hằng số metrics cho biến thể tiếng Việt (KafkaPixelVN.ttf)
VN_ASCENDER = 1100
VN_DESCENDER = -300
VN_GRID_COLS = 6       # 5 cột chữ gốc + 1 cột gap (x = 0..600)
VN_ABOVE_ROWS = 3      # 3 hàng dấu phía trên cap height (y = 700..1000)
VN_BASE_ROWS = 7       # 7 hàng thân chữ gốc (y = 0..700)
VN_BELOW_ROWS = 2      # 2 hàng dưới baseline (y = -200..0; dấu nặng ở y = -200..-100)
VN_TOTAL_ROWS = VN_ABOVE_ROWS + VN_BASE_ROWS + VN_BELOW_ROWS  # 12 hàng
VN_Y_BOTTOM = -200     # Đáy của hàng cuối cùng trong lưới 12 hàng

# Các dấu thanh và dấu mũ pixel nhỏ (rộng 5 cột, ghép trên lưới điểm)
VN_TONE_MARKS: dict[str, tuple[str, ...]] = {
    "acute": ("00010", "00100"),           # Dấu sắc
    "grave": ("01000", "00100"),           # Dấu huyền
    "hook": ("01100", "00010", "00100"),   # Dấu hỏi (3 hàng)
    "tilde": ("01010", "10100"),           # Dấu ngã
    "dot": ("00100",),                     # Dấu nặng (1 điểm căn giữa dưới baseline)
}

VN_HAT_MARKS: dict[str, tuple[str, ...]] = {
    "circumflex": ("00100", "01010"),      # Dấu mũ (Â, Ê, Ô)
    "breve": ("10001", "01110"),           # Dấu trăng (Ă)
}

# Bảng tổ hợp nguyên âm tiếng Việt: (chữ gốc 5x7, loại dấu phụ mũ/râu, chuỗi 6 thanh: ngang/huyền/sắc/hỏi/ngã/nặng)
VN_TONE_ORDER: tuple[str, ...] = ("none", "grave", "acute", "hook", "tilde", "dot")
VN_VOWEL_SPECS: tuple[tuple[str, str | None, str], ...] = (
    ("A", None, "AÀÁẢÃẠ"),
    ("A", "breve", "ĂẰẮẲẴẶ"),
    ("A", "circumflex", "ÂẦẤẨẪẬ"),
    ("E", None, "EÈÉẺẼẸ"),
    ("E", "circumflex", "ÊỀẾỂỄỆ"),
    ("I", None, "IÌÍỈĨỊ"),
    ("O", None, "OÒÓỎÕỌ"),
    ("O", "circumflex", "ÔỒỐỔỖỘ"),
    ("O", "horn", "ƠỜỚỞỠỢ"),
    ("U", None, "UÙÚỦŨỤ"),
    ("U", "horn", "ƯỪỨỬỮỰ"),
    ("Y", None, "YỲÝỶỸỴ"),
)


def pad4(data: bytes) -> bytes:
    """Đệm thêm byte 0 để độ dài dữ liệu chia hết cho 4."""
    rem = len(data) % 4
    return data if rem == 0 else data + b"\x00" * (4 - rem)


def calc_checksum(data: bytes) -> int:
    """Tính checksum 32-bit chuẩn OpenType cho khối dữ liệu (đệm 4 byte nếu cần)."""
    padded = pad4(data)
    total = 0
    for (word,) in struct.iter_unpack(">I", padded):
        total = (total + word) & 0xFFFFFFFF
    return total


def rows_to_contours(
    rows: list[str], y_bottom: int = 0
) -> list[list[tuple[int, int]]]:
    """Chuyển ma trận điểm ('0'/'1') thành danh sách các contour hình chữ nhật.

    Gộp các ô '1' liền nhau trên cùng một dòng thành một hình chữ nhật (như hàm _blit).
    Mỗi hình chữ nhật gồm 4 điểm on-curve theo chiều KIM ĐỒNG HỒ:
    (x0, y0) -> (x0, y1) -> (x1, y1) -> (x1, y0).
    Với lưới 5×7 mặc định (y_bottom = 0): dòng r = 0 ở y = 600..700, dòng r = 6 ở y = 0..100.
    Với lưới 6×12 tiếng Việt (y_bottom = -200): dòng r = 0..2 ở y = 700..1000,
    dòng r = 3..9 ở y = 0..700, dòng r = 11 ở y = -200..-100.
    """
    contours: list[list[tuple[int, int]]] = []
    gh = len(rows)
    for r, row in enumerate(rows):
        y0 = (gh - 1 - r) * CELL_SIZE + y_bottom
        y1 = y0 + CELL_SIZE
        c = 0
        gw = len(row)
        while c < gw:
            if row[c] == "1":
                k = c
                while k < gw and row[k] == "1":
                    k += 1
                x0 = c * CELL_SIZE
                x1 = k * CELL_SIZE
                # Hướng kim đồng hồ (CW): dưới-trái -> trên-trái -> trên-phải -> dưới-phải
                contours.append([(x0, y0), (x0, y1), (x1, y1), (x1, y0)])
                c = k
            else:
                c += 1
    return contours


def _blit_grid(
    grid: list[list[str]],
    mark_rows: list[str] | tuple[str, ...],
    top_row: int,
    col_shift: int = 0,
) -> None:
    """Vẽ đè (OR) một ma trận điểm mark_rows lên lưới 2D tại (top_row, col_shift)."""
    for r_off, row_str in enumerate(mark_rows):
        gr = top_row + r_off
        if 0 <= gr < len(grid):
            for c_off, bit in enumerate(row_str):
                if bit == "1":
                    gc = col_shift + c_off
                    if 0 <= gc < len(grid[gr]):
                        grid[gr][gc] = "1"


def compose_vn_vowel_rows(
    base_ch: str, modifier: str | None, tone: str
) -> list[str]:
    """Ghép chữ cái nguyên âm tiếng Việt trên lưới điểm 12 hàng × 6 cột.

    - Hàng 0..2 (y = 700..1000): vùng dấu mũ / dấu thanh phía trên cap height.
    - Hàng 3..9 (y = 0..700): thân chữ gốc 5×7 (cột 0..4) + dấu râu Ơ/Ư ở cột 5.
    - Hàng 10..11 (y = -200..0): vùng dưới baseline (dấu nặng ở hàng 11, y = -200..-100).
    """
    grid = [["0"] * VN_GRID_COLS for _ in range(VN_TOTAL_ROWS)]

    # 1. Đặt chữ gốc 5×7 vào hàng 3..9 (y = 0..700)
    _blit_grid(grid, pixelfont.GLYPHS[base_ch], top_row=VN_ABOVE_ROWS, col_shift=0)

    # 2. Dấu phụ của nguyên âm: mũ (circumflex), trăng (breve), hoặc râu (horn)
    has_hat = modifier in VN_HAT_MARKS
    if has_hat and modifier is not None:
        hat_rows = VN_HAT_MARKS[modifier]  # cao 2 hàng -> đặt ở hàng 1..2 (ngay trên thân chữ, y = 700..900)
        hat_top = VN_ABOVE_ROWS - len(hat_rows)
        _blit_grid(grid, hat_rows, top_row=hat_top, col_shift=0)
    elif modifier == "horn":
        # Râu Ơ, Ư: thêm điểm/nét ở góc trên-phải cột 5 (gap column), hàng 0..1 của thân chữ
        grid[VN_ABOVE_ROWS + 0][5] = "1"
        grid[VN_ABOVE_ROWS + 1][5] = "1"

    # 3. Dấu thanh (huyền, sắc, hỏi, ngã, nặng)
    if tone == "dot":
        # Dấu nặng ở hàng dưới baseline (y = -200..-100)
        _blit_grid(grid, VN_TONE_MARKS["dot"], top_row=VN_TOTAL_ROWS - 1, col_shift=0)
    elif tone in VN_TONE_MARKS:
        tone_rows = VN_TONE_MARKS[tone]
        if has_hat:
            # Có dấu mũ/trăng ở ngay trên chữ: đẩy dấu thanh lên sát đỉnh 3 hàng và dịch sang phải 2 cột (tới cột 5)
            tone_top = 0
            col_shift = 2
        else:
            # Không có dấu mũ: đặt dấu thanh ngay trên thân chữ (chạm hàng 8, tức y = 700..800)
            tone_top = VN_ABOVE_ROWS - len(tone_rows)
            col_shift = 0
        _blit_grid(grid, tone_rows, top_row=tone_top, col_shift=col_shift)

    return ["".join(r) for r in grid]


def compose_vn_d_stroke_rows() -> list[str]:
    """Chữ Đ/đ: thân D hẹp 4 cột (cột 1..4) + thanh ngang cắt qua nét đứng ở hàng giữa, thò ra cột 0.

    (Ghép thanh lên chữ D 5 cột gốc thì trông như chữ B, nên vẽ riêng.)
    """
    rows = ["01110", "01001", "01001", "11101", "01001", "01001", "01110"]
    grid = [["0"] * VN_GRID_COLS for _ in range(VN_TOTAL_ROWS)]
    _blit_grid(grid, rows, top_row=VN_ABOVE_ROWS, col_shift=0)
    return ["".join(r) for r in grid]


def make_notdef_contours() -> list[list[tuple[int, int]]]:
    """Tạo contour cho glyph 0 (.notdef): khung chữ nhật rỗng dày 100 đơn vị.

    Viền ngoài chiều kim đồng hồ (CW), viền trong ngược chiều kim đồng hồ (CCW).
    """
    outer_cw = [(0, 0), (0, 700), (500, 700), (500, 0)]
    inner_ccw = [(100, 100), (400, 100), (400, 600), (100, 600)]
    return [outer_cw, inner_ccw]


def encode_simple_glyph(
    contours: list[list[tuple[int, int]]]
) -> tuple[bytes, tuple[int, int, int, int], int, int]:
    """Đóng gói dữ liệu một simple glyph vào bảng 'glyf'.

    Trả về:
        (raw_bytes_padded_4, (xMin, yMin, xMax, yMax), num_points, num_contours)
    Nếu glyph rỗng (như khoảng trắng), trả về b"" và bbox = (0, 0, 0, 0).
    """
    if not contours:
        return b"", (0, 0, 0, 0), 0, 0

    all_pts = [pt for contour in contours for pt in contour]
    xs = [pt[0] for pt in all_pts]
    ys = [pt[1] for pt in all_pts]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    end_pts: list[int] = []
    idx = -1
    for contour in contours:
        idx += len(contour)
        end_pts.append(idx)

    num_contours = len(contours)
    num_points = len(all_pts)

    # Header của simple glyph: numberOfContours, xMin, yMin, xMax, yMax
    buf = bytearray(struct.pack(">hhhhh", num_contours, x_min, y_min, x_max, y_max))
    # endPtsOfContours (uint16 cho mỗi contour)
    for ep in end_pts:
        buf.extend(struct.pack(">H", ep))
    # instructionLength = 0
    buf.extend(struct.pack(">H", 0))
    # flags: mỗi điểm đều là 0x01 (ON_CURVE_POINT), toạ độ x/y đều ghi dạng int16 (2 byte)
    buf.extend(b"\x01" * num_points)

    # Toạ độ X tương đối (int16 big-endian)
    prev_x = 0
    for x, _ in all_pts:
        dx = x - prev_x
        buf.extend(struct.pack(">h", dx))
        prev_x = x

    # Toạ độ Y tương đối (int16 big-endian)
    prev_y = 0
    for _, y in all_pts:
        dy = y - prev_y
        buf.extend(struct.pack(">h", dy))
        prev_y = y

    # Đệm chẵn 4 byte cho mỗi bản ghi glyph
    return pad4(bytes(buf)), (x_min, y_min, x_max, y_max), num_points, num_contours


def collect_glyphs_and_cmap(
    vietnamese: bool = False,
) -> tuple[list[list[list[tuple[int, int]]]], dict[int, int]]:
    """Tạo danh sách glyph và bảng ánh xạ cmap từ pixelfont.GLYPHS (và bộ chữ tiếng Việt nếu vietnamese=True).

    Quy tắc:
    - Glyph 0: .notdef (hình chữ nhật rỗng).
    - Glyph 1: ' ' (space, không có contour).
    - Các ký tự còn lại trong GLYPHS:
      + '<' ánh xạ vào U+25C0 (◀), KHÔNG ánh xạ vào '<' ASCII.
      + '>' ánh xạ vào U+25B6 (▶), KHÔNG ánh xạ vào '>' ASCII.
      + Chữ HOA 'A'..'Z' ánh xạ vào cả mã ASCII chữ HOA lẫn chữ thường 'a'..'z' (dùng chung glyph).
      + Các ký tự khác ánh xạ theo ord(ch).
    - Khi vietnamese=True: ghép thêm các chữ cái tiếng Việt (A/Ă/Â/E/Ê/I/O/Ô/Ơ/U/Ư/Y với 5 dấu thanh + không dấu, và Đ/đ),
      mỗi chữ thường ánh xạ vào cùng glyph với chữ HOA tương ứng.
    """
    glyph_contours: list[list[list[tuple[int, int]]]] = []
    cmap: dict[int, int] = {}

    # Glyph 0: .notdef
    glyph_contours.append(make_notdef_contours())

    # Glyph 1: space (' ')
    glyph_contours.append([])
    cmap[0x0020] = 1

    for ch, rows in pixelfont.GLYPHS.items():
        if ch == " ":
            continue

        gid = len(glyph_contours)
        glyph_contours.append(rows_to_contours(rows))

        if ch == "<":
            cmap[0x25C0] = gid  # ◀ BLACK LEFT-POINTING TRIANGLE
        elif ch == ">":
            cmap[0x25B6] = gid  # ▶ BLACK RIGHT-POINTING TRIANGLE
        else:
            code = ord(ch)
            cmap[code] = gid
            if "A" <= ch <= "Z":
                cmap[ord(ch.lower())] = gid

    if vietnamese:
        # Các nguyên âm tiếng Việt ghép từ thân 5×7 + dấu mũ/trăng/râu + 5 dấu thanh
        for base_ch, modifier, chars_by_tone in VN_VOWEL_SPECS:
            for tone, ch_upper in zip(VN_TONE_ORDER, chars_by_tone):
                code_upper = ord(ch_upper)
                if code_upper in cmap:
                    # Ký tự ASCII gốc (A, E, I, O, U, Y không dấu) đã có sẵn trong GLYPHS
                    continue
                vn_rows = compose_vn_vowel_rows(base_ch, modifier, tone)
                gid = len(glyph_contours)
                glyph_contours.append(rows_to_contours(vn_rows, y_bottom=VN_Y_BOTTOM))
                cmap[code_upper] = gid
                cmap[ord(ch_upper.lower())] = gid

        # Chữ Đ (U+0110) và đ (U+0111) dùng chung glyph
        d_rows = compose_vn_d_stroke_rows()
        gid_d = len(glyph_contours)
        glyph_contours.append(rows_to_contours(d_rows, y_bottom=VN_Y_BOTTOM))
        cmap[ord("Đ")] = gid_d
        cmap[ord("đ")] = gid_d

    return glyph_contours, cmap


def build_glyf_and_loca(
    glyph_contours: list[list[list[tuple[int, int]]]]
) -> tuple[bytes, bytes, list[tuple[int, int, int, int]], list[bool], int, int]:
    """Dựng bảng 'glyf' và bảng 'loca' (dạng long / uint32, indexToLocFormat = 1)."""
    glyf_parts: list[bytes] = []
    offsets: list[int] = []
    bboxes: list[tuple[int, int, int, int]] = []
    is_empty: list[bool] = []
    max_points = 0
    max_contours = 0
    current_offset = 0

    for contours in glyph_contours:
        offsets.append(current_offset)
        encoded, bbox, n_pts, n_cnts = encode_simple_glyph(contours)
        glyf_parts.append(encoded)
        bboxes.append(bbox)
        is_empty.append(len(encoded) == 0)
        current_offset += len(encoded)
        if n_pts > max_points:
            max_points = n_pts
        if n_cnts > max_contours:
            max_contours = n_cnts

    offsets.append(current_offset)
    glyf_data = b"".join(glyf_parts)
    loca_data = b"".join(struct.pack(">I", off) for off in offsets)
    return glyf_data, loca_data, bboxes, is_empty, max_points, max_contours


def build_hmtx(
    bboxes: list[tuple[int, int, int, int]], is_empty: list[bool]
) -> tuple[bytes, int, int, int]:
    """Dựng bảng 'hmtx' và tính minLSB, minRSB, xMaxExtent cho bảng 'hhea'."""
    records: list[bytes] = []
    min_lsb: int | None = None
    min_rsb: int | None = None
    x_max_extent: int | None = None

    for (x_min, _, x_max, _), empty in zip(bboxes, is_empty):
        lsb = 0 if empty else x_min
        records.append(struct.pack(">Hh", ADVANCE_WIDTH, lsb))
        if not empty:
            rsb = ADVANCE_WIDTH - (lsb + (x_max - x_min))
            extent = lsb + (x_max - x_min)
            min_lsb = lsb if min_lsb is None else min(min_lsb, lsb)
            min_rsb = rsb if min_rsb is None else min(min_rsb, rsb)
            x_max_extent = extent if x_max_extent is None else max(x_max_extent, extent)

    return (
        b"".join(records),
        0 if min_lsb is None else min_lsb,
        0 if min_rsb is None else min_rsb,
        0 if x_max_extent is None else x_max_extent,
    )


def build_head(
    bboxes: list[tuple[int, int, int, int]],
    is_empty: list[bool],
    timestamp_1904: int,
    check_sum_adjustment: int = 0,
) -> bytes:
    """Dựng bảng 'head' đúng chuẩn 54 byte (created/modified là LONGDATETIME 64-bit)."""
    non_empty = [b for b, emp in zip(bboxes, is_empty) if not emp]
    x_min = min(b[0] for b in non_empty) if non_empty else 0
    y_min = min(b[1] for b in non_empty) if non_empty else 0
    x_max = max(b[2] for b in non_empty) if non_empty else 0
    y_max = max(b[3] for b in non_empty) if non_empty else 0

    return struct.pack(
        ">IIIIHHQQhhhhHHhhh",
        0x00010000,            # version 1.0 (Fixed)
        0x00010000,            # fontRevision 1.0 (Fixed)
        check_sum_adjustment & 0xFFFFFFFF,
        0x5F0F3CF5,            # magicNumber
        0x000B,                # flags
        UNITS_PER_EM,          # unitsPerEm (700)
        timestamp_1904,        # created (64-bit)
        timestamp_1904,        # modified (64-bit)
        x_min,
        y_min,
        x_max,
        y_max,
        0,                     # macStyle
        8,                     # lowestRecPPEM
        2,                     # fontDirectionHint
        1,                     # indexToLocFormat = 1 (long)
        0,                     # glyphDataFormat = 0
    )


def build_hhea(
    num_glyphs: int,
    min_lsb: int,
    min_rsb: int,
    x_max_extent: int,
    ascender: int = ASCENDER,
    descender: int = DESCENDER,
) -> bytes:
    """Dựng bảng 'hhea' (36 byte)."""
    return struct.pack(
        ">IhhhHhhhhhhhhhhhH",
        0x00010000,     # version 1.0
        ascender,       # ascender (800 mặc định, 1100 cho VN)
        descender,      # descender (-100 mặc định, -300 cho VN)
        LINE_GAP,       # lineGap = 0
        ADVANCE_WIDTH,  # advanceWidthMax = 600
        min_lsb,        # minLeftSideBearing
        min_rsb,        # minRightSideBearing
        x_max_extent,   # xMaxExtent
        1,              # caretSlopeRise = 1
        0,              # caretSlopeRun = 0
        0,              # caretOffset = 0
        0, 0, 0, 0,     # reserved (4 × int16)
        0,              # metricDataFormat = 0
        num_glyphs,     # numberOfHMetrics
    )


def build_maxp(num_glyphs: int, max_points: int, max_contours: int) -> bytes:
    """Dựng bảng 'maxp' version 1.0 (32 byte)."""
    return struct.pack(
        ">IH" + "H" * 13,
        0x00010000,    # version 1.0
        num_glyphs,    # numGlyphs
        max_points,    # maxPoints
        max_contours,  # maxContours
        0,             # maxCompositePoints
        0,             # maxCompositeContours
        2,             # maxZones = 2
        0,             # maxTwilightPoints
        0,             # maxStorage
        0,             # maxFunctionDefs
        0,             # maxInstructionDefs
        0,             # maxStackElements
        0,             # maxSizeOfInstructions
        0,             # maxComponentElements
        0,             # maxComponentDepth
    )


def build_os2(
    cmap: dict[int, int],
    ascender: int = ASCENDER,
    descender: int = DESCENDER,
) -> bytes:
    """Dựng bảng 'OS/2' version 4 (96 byte)."""
    char_codes = sorted(cmap.keys())
    first_char = min(char_codes) if char_codes else 0
    last_char = min(max(char_codes), 0xFFFF) if char_codes else 0

    # PANOSE 10 byte: bFamilyType=2 (Text and Display), bProportion=9 (Monospaced)
    panose = bytes([2, 0, 5, 9, 0, 0, 0, 0, 0, 0])

    # Unicode ranges: bật bit 0 (Basic Latin) và bit 38 (Geometric Shapes U+25A0..U+25FF, nằm ở ulUnicodeRange2 bit 6)
    ul_unicode_range1 = 1 << 0
    ul_unicode_range2 = 1 << 6
    ul_unicode_range3 = 0
    ul_unicode_range4 = 0

    # CodePageRange1: bit 0 (Latin 1)
    ul_code_page_range1 = 1 << 0
    ul_code_page_range2 = 0

    fs_selection = 0x0040 | 0x0080  # REGULAR | USE_TYPO_METRICS

    return struct.pack(
        ">HhHHHhhhhhhhhhhh10sIIII4sHHHhhhHHIIhhHHH",
        4,                    # version = 4
        ADVANCE_WIDTH,        # xAvgCharWidth = 600
        400,                  # usWeightClass = 400 (Normal)
        5,                    # usWidthClass = 5 (Medium)
        0,                    # fsType = 0 (Installable Embedding)
        600,                  # ySubscriptXSize
        700,                  # ySubscriptYSize
        0,                    # ySubscriptXOffset
        140,                  # ySubscriptYOffset
        600,                  # ySuperscriptXSize
        700,                  # ySuperscriptYSize
        0,                    # ySuperscriptXOffset
        450,                  # ySuperscriptYOffset
        100,                  # yStrikeoutSize
        300,                  # yStrikeoutPosition
        0,                    # sFamilyClass
        panose,               # panose[10]
        ul_unicode_range1,    # ulUnicodeRange1
        ul_unicode_range2,    # ulUnicodeRange2
        ul_unicode_range3,    # ulUnicodeRange3
        ul_unicode_range4,    # ulUnicodeRange4
        b"KAFK",              # achVendID
        fs_selection,         # fsSelection
        first_char,           # usFirstCharIndex
        last_char,            # usLastCharIndex
        ascender,             # sTypoAscender (800 mặc định, 1100 cho VN)
        descender,            # sTypoDescender (-100 mặc định, -300 cho VN)
        LINE_GAP,             # sTypoLineGap = 0
        ascender,             # usWinAscent (800 mặc định, 1100 cho VN)
        abs(descender),       # usWinDescent (100 mặc định, 300 cho VN)
        ul_code_page_range1,  # ulCodePageRange1
        ul_code_page_range2,  # ulCodePageRange2
        X_HEIGHT,             # sxHeight = 700
        CAP_HEIGHT,           # sCapHeight = 700
        0,                    # usDefaultChar = 0
        32,                   # usBreakChar = 32 (' ')
        1,                    # usMaxContext = 1
    )


def build_cmap(cmap: dict[int, int]) -> bytes:
    """Dựng bảng 'cmap' với subtable Format 4 dùng chung cho (0, 3) và (3, 1)."""
    sorted_items = sorted(cmap.items())

    # Gom các mã ký tự liên tiếp thành các segment [startCode..endCode]
    segments: list[tuple[int, int, list[int]]] = []
    for code, gid in sorted_items:
        if not segments or code != segments[-1][1] + 1:
            segments.append((code, code, [gid]))
        else:
            start_c, _, gids = segments[-1]
            gids.append(gid)
            segments[-1] = (start_c, code, gids)

    # Thêm segment kết thúc bắt buộc 0xFFFF..0xFFFF
    segments.append((0xFFFF, 0xFFFF, []))

    seg_count = len(segments)
    seg_count_x2 = seg_count * 2
    entry_selector = 0
    while (1 << (entry_selector + 1)) <= seg_count:
        entry_selector += 1
    search_range = 2 * (1 << entry_selector)
    range_shift = seg_count_x2 - search_range

    end_codes: list[int] = []
    start_codes: list[int] = []
    id_deltas: list[int] = []
    id_range_offsets: list[int] = []
    glyph_id_array: list[int] = []

    for idx, (start_c, end_c, gids) in enumerate(segments):
        end_codes.append(end_c)
        start_codes.append(start_c)

        if start_c == 0xFFFF and end_c == 0xFFFF:
            id_deltas.append(1)
            id_range_offsets.append(0)
            continue

        # Kiểm tra xem gids có tăng đều đúng 1 đơn vị mỗi bước không
        is_linear = all(
            gids[k] - (start_c + k) == gids[0] - start_c for k in range(len(gids))
        )
        if is_linear:
            delta = (gids[0] - start_c) & 0xFFFF
            id_deltas.append(delta)
            id_range_offsets.append(0)
        else:
            id_deltas.append(0)
            # Khoảng cách byte từ vị trí idRangeOffset[idx] tới phần tử đầu của segment trong glyphIdArray
            words_to_end_of_ro = seg_count - idx
            words_in_gia = len(glyph_id_array)
            ro_bytes = (words_to_end_of_ro + words_in_gia) * 2
            id_range_offsets.append(ro_bytes)
            glyph_id_array.extend(gids)

    subtable_len = 16 + 8 * seg_count + 2 * len(glyph_id_array)
    subtable = bytearray(
        struct.pack(
            ">HHHHHHH",
            4,              # format = 4
            subtable_len,   # length
            0,              # language = 0
            seg_count_x2,
            search_range,
            entry_selector,
            range_shift,
        )
    )
    for ec in end_codes:
        subtable.extend(struct.pack(">H", ec))
    subtable.extend(struct.pack(">H", 0))  # reservedPad = 0
    for sc in start_codes:
        subtable.extend(struct.pack(">H", sc))
    for delta in id_deltas:
        subtable.extend(struct.pack(">H", delta))
    for ro in id_range_offsets:
        subtable.extend(struct.pack(">H", ro))
    for gid in glyph_id_array:
        subtable.extend(struct.pack(">H", gid))

    # Header bảng cmap: version = 0, numTables = 2: (0, 3) và (3, 1) cùng trỏ tới offset 20
    subtable_offset = 4 + 2 * 8
    header = struct.pack(
        ">HH" + "HHI" * 2,
        0,                # version
        2,                # numTables
        0, 3, subtable_offset,  # Platform 0 (Unicode), Encoding 3
        3, 1, subtable_offset,  # Platform 3 (Windows), Encoding 1 (Unicode BMP)
    )
    return header + bytes(subtable)


def build_name(vietnamese: bool = False) -> bytes:
    """Dựng bảng 'name' format 0 với bản ghi Macintosh (1, 0, 0) và Windows (3, 1, 0x0409)."""
    if vietnamese:
        names = [
            (1, "Kafka Pixel VN"),
            (2, "Regular"),
            (3, "Kafka Pixel VN Regular 1.0"),
            (4, "Kafka Pixel VN Regular"),
            (5, "Version 1.0"),
            (6, "KafkaPixelVN-Regular"),
        ]
    else:
        names = [
            (1, "Kafka Pixel"),
            (2, "Regular"),
            (3, "Kafka Pixel Regular 1.0"),
            (4, "Kafka Pixel"),
            (5, "Version 1.0"),
            (6, "KafkaPixel-Regular"),
        ]

    # Tạo danh sách (platformID, encodingID, languageID, nameID, encoded_bytes)
    raw_records: list[tuple[int, int, int, int, bytes]] = []
    for name_id, text in names:
        # Platform 1 (Macintosh), Encoding 0 (Roman), Language 0 (English) — ASCII
        raw_records.append((1, 0, 0, name_id, text.encode("ascii")))
        # Platform 3 (Windows), Encoding 1 (Unicode BMP), Language 0x0409 (en-US) — UTF-16BE
        raw_records.append((3, 1, 0x0409, name_id, text.encode("utf-16-be")))

    # Sắp xếp theo thứ tự chuẩn OpenType: (platformID, encodingID, languageID, nameID)
    raw_records.sort(key=lambda r: (r[0], r[1], r[2], r[3]))

    count = len(raw_records)
    string_offset = 6 + count * 12
    header = bytearray(struct.pack(">HHH", 0, count, string_offset))
    storage = bytearray()

    for plat_id, enc_id, lang_id, name_id, data in raw_records:
        offset = len(storage)
        length = len(data)
        header.extend(
            struct.pack(">HHHHHH", plat_id, enc_id, lang_id, name_id, length, offset)
        )
        storage.extend(data)

    return bytes(header + storage)


def build_post() -> bytes:
    """Dựng bảng 'post' version 3.0 (32 byte)."""
    return struct.pack(
        ">IIhhIIIII",
        0x00030000,  # version 3.0 (không lưu tên glyph PostScript)
        0,           # italicAngle = 0.0
        -150,        # underlinePosition = -150
        100,         # underlineThickness = 100
        1,           # isFixedPitch = 1 (monospace)
        0,           # minMemType42
        0,           # maxMemType42
        0,           # minMemType1
        0,           # maxMemType1
    )


def assemble_ttf(vietnamese: bool = False) -> tuple[bytes, int]:
    """Lắp ráp toàn bộ các bảng thành dữ liệu nhị phân TrueType (.ttf) hoàn chỉnh.

    Trả về (ttf_bytes, num_glyphs).
    """
    glyph_contours, cmap = collect_glyphs_and_cmap(vietnamese=vietnamese)
    num_glyphs = len(glyph_contours)
    ascender = VN_ASCENDER if vietnamese else ASCENDER
    descender = VN_DESCENDER if vietnamese else DESCENDER

    glyf_data, loca_data, bboxes, is_empty, max_pts, max_cnts = build_glyf_and_loca(
        glyph_contours
    )
    hmtx_data, min_lsb, min_rsb, x_max_extent = build_hmtx(bboxes, is_empty)

    now_1904 = int(time.time()) + EPOCH_1904_OFFSET

    tables: dict[bytes, bytes] = {
        b"OS/2": build_os2(cmap, ascender=ascender, descender=descender),
        b"cmap": build_cmap(cmap),
        b"glyf": glyf_data,
        b"head": build_head(bboxes, is_empty, now_1904, check_sum_adjustment=0),
        b"hhea": build_hhea(
            num_glyphs,
            min_lsb,
            min_rsb,
            x_max_extent,
            ascender=ascender,
            descender=descender,
        ),
        b"hmtx": hmtx_data,
        b"loca": loca_data,
        b"maxp": build_maxp(num_glyphs, max_pts, max_cnts),
        b"name": build_name(vietnamese=vietnamese),
        b"post": build_post(),
    }

    # Sắp xếp các tag theo thứ tự byte tăng dần
    sorted_tags = sorted(tables.keys())
    num_tables = len(sorted_tags)

    entry_selector = 0
    while (1 << (entry_selector + 1)) <= num_tables:
        entry_selector += 1
    search_range = (1 << entry_selector) * 16
    range_shift = num_tables * 16 - search_range

    sfnt_header = struct.pack(
        ">IHHHH",
        SFNT_VERSION,
        num_tables,
        search_range,
        entry_selector,
        range_shift,
    )

    # Tính offset cho từng bảng (sau Offset Table 12 byte + Table Directory 16 * num_tables byte)
    current_offset = 12 + 16 * num_tables
    table_offsets: dict[bytes, int] = {}
    padded_tables: dict[bytes, bytes] = {}
    table_checksums: dict[bytes, int] = {}

    for tag in sorted_tags:
        raw = tables[tag]
        table_offsets[tag] = current_offset
        padded = pad4(raw)
        padded_tables[tag] = padded
        table_checksums[tag] = calc_checksum(padded)
        current_offset += len(padded)

    # Dựng Table Directory lần 1 (với head.checkSumAdjustment = 0)
    directory = bytearray()
    body = bytearray()
    for tag in sorted_tags:
        raw = tables[tag]
        directory.extend(
            struct.pack(">4sIII", tag, table_checksums[tag], table_offsets[tag], len(raw))
        )
        body.extend(padded_tables[tag])

    preliminary_font = sfnt_header + bytes(directory) + bytes(body)
    total_checksum = calc_checksum(preliminary_font)
    check_sum_adjustment = (CHECKSUM_MAGIC - total_checksum) & 0xFFFFFFFF

    # Cập nhật head.checkSumAdjustment (chú ý: checksum trong Table Directory của 'head' được tính khi checkSumAdjustment = 0)
    tables[b"head"] = build_head(
        bboxes, is_empty, now_1904, check_sum_adjustment=check_sum_adjustment
    )
    padded_tables[b"head"] = pad4(tables[b"head"])

    # Dựng Table Directory và thân file lần cuối
    final_directory = bytearray()
    final_body = bytearray()
    for tag in sorted_tags:
        raw = tables[tag]
        final_directory.extend(
            struct.pack(">4sIII", tag, table_checksums[tag], table_offsets[tag], len(raw))
        )
        final_body.extend(padded_tables[tag])

    return sfnt_header + bytes(final_directory) + bytes(final_body), num_glyphs


def lookup_cmap_format4(cmap_bytes: bytes, codepoint: int) -> int:
    """Giải mã bảng 'cmap' Format 4 bằng struct để tra glyph ID từ mã Unicode."""
    _, num_tables = struct.unpack_from(">HH", cmap_bytes, 0)
    sub_offset = None
    for i in range(num_tables):
        plat_id, enc_id, off = struct.unpack_from(">HHI", cmap_bytes, 4 + i * 8)
        if (plat_id, enc_id) == (3, 1):
            sub_offset = off
            break
    if sub_offset is None:
        return 0

    fmt, length, _, seg_count_x2 = struct.unpack_from(">HHHH", cmap_bytes, sub_offset)
    if fmt != 4:
        return 0

    seg_count = seg_count_x2 // 2
    pos = sub_offset + 14
    end_codes = struct.unpack_from(f">{seg_count}H", cmap_bytes, pos)
    pos += 2 * seg_count + 2  # +2 cho reservedPad
    start_codes = struct.unpack_from(f">{seg_count}H", cmap_bytes, pos)
    pos += 2 * seg_count
    id_deltas = struct.unpack_from(f">{seg_count}H", cmap_bytes, pos)
    pos += 2 * seg_count
    id_range_offsets_pos = pos
    id_range_offsets = struct.unpack_from(f">{seg_count}H", cmap_bytes, pos)

    for i in range(seg_count):
        if start_codes[i] <= codepoint <= end_codes[i]:
            if id_range_offsets[i] == 0:
                return (codepoint + id_deltas[i]) & 0xFFFF
            ro_pos = id_range_offsets_pos + i * 2
            gid_pos = ro_pos + id_range_offsets[i] + 2 * (codepoint - start_codes[i])
            if gid_pos + 2 > sub_offset + length:
                return 0
            (gid,) = struct.unpack_from(">H", cmap_bytes, gid_pos)
            if gid == 0:
                return 0
            return (gid + id_deltas[i]) & 0xFFFF
    return 0


def run_selftest() -> int:
    """Dựng font vào thư mục tạm rồi đọc lại bằng struct để kiểm tra toàn diện."""
    all_passed = True

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal all_passed
        status = "PASS" if condition else "FAIL"
        if not condition:
            all_passed = False
        suffix = f" ({detail})" if detail else ""
        print(f"[{status}] {name}{suffix}")

    with tempfile.TemporaryDirectory() as tmpdir:
        ttf_path = Path(tmpdir) / "KafkaPixel.ttf"
        ttf_bytes, built_num_glyphs = assemble_ttf()
        ttf_path.write_bytes(ttf_bytes)
        data = ttf_path.read_bytes()

    # 1. Kiểm tra chữ ký sfnt 0x00010000
    sfnt_ver, num_tables, search_range, entry_selector, range_shift = struct.unpack_from(
        ">IHHHH", data, 0
    )
    check("Chữ ký sfnt == 0x00010000", sfnt_ver == 0x00010000, f"0x{sfnt_ver:08X}")

    # 2. Đọc danh mục bảng và kiểm tra thứ tự tag + checksum từng bảng
    records: dict[bytes, tuple[int, int, int]] = {}
    tags_order: list[bytes] = []
    checksums_ok = True
    bad_tags: list[str] = []

    for i in range(num_tables):
        tag, csum, off, length = struct.unpack_from(">4sIII", data, 12 + i * 16)
        tags_order.append(tag)
        records[tag] = (csum, off, length)
        tbl_slice = data[off : off + length]
        if tag == b"head":
            # Khi tính checksum bảng head, trường checkSumAdjustment (byte 8..12) phải coi bằng 0
            tbl_zeroed = tbl_slice[:8] + b"\x00\x00\x00\x00" + tbl_slice[12:]
            actual_csum = calc_checksum(tbl_zeroed)
        else:
            actual_csum = calc_checksum(tbl_slice)
        if actual_csum != csum:
            checksums_ok = False
            bad_tags.append(tag.decode("ascii", errors="replace"))

    check("Thứ tự bảng sắp theo tag tăng dần", tags_order == sorted(tags_order))
    check(
        "Mọi checksum bảng đều đúng",
        checksums_ok,
        "OK" if checksums_ok else f"Sai ở: {', '.join(bad_tags)}",
    )

    # 3. Kiểm tra checksum toàn file == 0xB1B0AFBA
    file_checksum = calc_checksum(data)
    check(
        "Checksum toàn file == 0xB1B0AFBA",
        file_checksum == CHECKSUM_MAGIC,
        f"0x{file_checksum:08X}",
    )

    # 4. Kiểm tra bảng cmap tra được 'A', 'a' (cùng glyph với 'A'), '0', ':', '%', U+25B6
    _, cmap_off, cmap_len = records[b"cmap"]
    cmap_bytes = data[cmap_off : cmap_off + cmap_len]
    gid_A = lookup_cmap_format4(cmap_bytes, ord("A"))
    gid_a = lookup_cmap_format4(cmap_bytes, ord("a"))
    gid_0 = lookup_cmap_format4(cmap_bytes, ord("0"))
    gid_colon = lookup_cmap_format4(cmap_bytes, ord(":"))
    gid_percent = lookup_cmap_format4(cmap_bytes, ord("%"))
    gid_play = lookup_cmap_format4(cmap_bytes, 0x25B6)
    gid_lt_ascii = lookup_cmap_format4(cmap_bytes, ord("<"))
    gid_gt_ascii = lookup_cmap_format4(cmap_bytes, ord(">"))

    cmap_ok = (
        gid_A > 0
        and gid_a == gid_A
        and gid_0 > 0
        and gid_colon > 0
        and gid_percent > 0
        and gid_play > 0
        and gid_lt_ascii == 0
        and gid_gt_ascii == 0
    )
    check(
        "cmap tra được 'A', 'a' (== 'A'), '0', ':', '%', U+25B6 (và không ánh xạ '<', '>')",
        cmap_ok,
        f"A={gid_A}, a={gid_a}, 0={gid_0}, :={gid_colon}, %={gid_percent}, U+25B6={gid_play}",
    )

    # 5. Kiểm tra numGlyphs khớp giữa maxp, hhea và hmtx
    _, maxp_off, _ = records[b"maxp"]
    _, num_glyphs_maxp = struct.unpack_from(">IH", data, maxp_off)
    _, hhea_off, _ = records[b"hhea"]
    (num_hmetrics,) = struct.unpack_from(">H", data, hhea_off + 34)
    _, hmtx_off, hmtx_len = records[b"hmtx"]

    metrics_match = (
        num_glyphs_maxp == built_num_glyphs
        and num_hmetrics == num_glyphs_maxp
        and hmtx_len == num_glyphs_maxp * 4
    )
    check(
        "numGlyphs khớp giữa maxp, hhea và hmtx",
        metrics_match,
        f"numGlyphs={num_glyphs_maxp}, hmtx_len={hmtx_len}",
    )

    # 6. Kiểm tra bảng loca tăng dần (không giảm)
    _, loca_off, loca_len = records[b"loca"]
    loca_count = loca_len // 4
    loca_offsets = list(struct.unpack_from(f">{loca_count}I", data, loca_off))
    loca_monotonic = loca_count == num_glyphs_maxp + 1 and all(
        loca_offsets[i] <= loca_offsets[i + 1] for i in range(len(loca_offsets) - 1)
    )
    check(
        "Bảng loca có số mục = numGlyphs + 1 và tăng dần",
        loca_monotonic,
        f"entries={loca_count}, last_offset={loca_offsets[-1]}",
    )

    # 7. Kiểm tra glyph 'I' có số contour > 0
    gid_I = lookup_cmap_format4(cmap_bytes, ord("I"))
    _, glyf_off, _ = records[b"glyf"]
    i_glyf_start = loca_offsets[gid_I]
    i_glyf_end = loca_offsets[gid_I + 1]
    i_contours = 0
    if i_glyf_end > i_glyf_start:
        (i_contours,) = struct.unpack_from(">h", data, glyf_off + i_glyf_start)
    check(
        "Glyph 'I' có số contour > 0",
        gid_I > 0 and i_contours > 0,
        f"gid={gid_I}, numberOfContours={i_contours}",
    )

    # 8. Kiểm tra metrics mặc định của KafkaPixel.ttf không hề thay đổi
    _, head_off, _ = records[b"head"]
    (upm_def,) = struct.unpack_from(">H", data, head_off + 18)
    dx_min, dy_min, dx_max, dy_max = struct.unpack_from(">hhhh", data, head_off + 36)
    h_asc_def, h_desc_def = struct.unpack_from(">hh", data, hhea_off + 4)
    _, os2_off, _ = records[b"OS/2"]
    o_tasc_def, o_tdesc_def, _, o_wasc_def, o_wdesc_def = struct.unpack_from(
        ">hhhHH", data, os2_off + 68
    )
    default_unchanged = (
        ASCENDER == 800
        and DESCENDER == -100
        and UNITS_PER_EM == 700
        and built_num_glyphs == 59
        and upm_def == 700
        and (dx_min, dy_min, dx_max, dy_max) == (0, 0, 500, 700)
        and (h_asc_def, h_desc_def) == (800, -100)
        and (o_tasc_def, o_tdesc_def, o_wasc_def, o_wdesc_def) == (800, -100, 800, 100)
    )
    check(
        "Font mặc định giữ nguyên metrics (ASCENDER=800, DESCENDER=-100, UPM=700, 59 glyphs)",
        default_unchanged,
        f"head=({dx_min},{dy_min},{dx_max},{dy_max}), hhea=({h_asc_def},{h_desc_def}), OS/2=({o_tasc_def},{o_tdesc_def},{o_wasc_def},{o_wdesc_def})",
    )

    # 9. Dựng biến thể tiếng Việt KafkaPixelVN.ttf vào file tạm và kiểm tra toàn diện
    with tempfile.TemporaryDirectory() as tmpdir_vn:
        vn_path = Path(tmpdir_vn) / "KafkaPixelVN.ttf"
        vn_bytes, vn_num_glyphs = assemble_ttf(vietnamese=True)
        vn_path.write_bytes(vn_bytes)
        vn_data = vn_path.read_bytes()

    _, vn_num_tables, _, _, _ = struct.unpack_from(">IHHHH", vn_data, 0)
    vn_records: dict[bytes, tuple[int, int, int]] = {}
    vn_csum_ok = True
    for i in range(vn_num_tables):
        tag, csum, off, length = struct.unpack_from(">4sIII", vn_data, 12 + i * 16)
        vn_records[tag] = (csum, off, length)
        tbl_slice = vn_data[off : off + length]
        if tag == b"head":
            tbl_slice = tbl_slice[:8] + b"\x00\x00\x00\x00" + tbl_slice[12:]
        if calc_checksum(tbl_slice) != csum:
            vn_csum_ok = False

    vn_file_csum = calc_checksum(vn_data)
    check(
        "VN: Checksum các bảng và toàn file == 0xB1B0AFBA",
        vn_csum_ok and vn_file_csum == CHECKSUM_MAGIC,
        f"0x{vn_file_csum:08X}, numGlyphs={vn_num_glyphs}",
    )

    # 10. Kiểm tra bảng name của VN
    _, vn_name_off, vn_name_len = vn_records[b"name"]
    vn_name_bytes = vn_data[vn_name_off : vn_name_off + vn_name_len]
    name_ok = (
        b"Kafka Pixel VN" in vn_name_bytes
        and b"Kafka Pixel VN Regular" in vn_name_bytes
        and b"KafkaPixelVN-Regular" in vn_name_bytes
        and "Kafka Pixel VN".encode("utf-16-be") in vn_name_bytes
        and "Kafka Pixel VN Regular".encode("utf-16-be") in vn_name_bytes
        and "KafkaPixelVN-Regular".encode("utf-16-be") in vn_name_bytes
    )
    check("VN: Bảng name chứa 'Kafka Pixel VN', 'Kafka Pixel VN Regular', 'KafkaPixelVN-Regular'", name_ok)

    # 11. Kiểm tra metrics bảng head, hhea, OS/2 của VN
    _, vn_head_off, _ = vn_records[b"head"]
    (vn_upm,) = struct.unpack_from(">H", vn_data, vn_head_off + 18)
    vx_min, vy_min, vx_max, vy_max = struct.unpack_from(">hhhh", vn_data, vn_head_off + 36)
    _, vn_hhea_off, _ = vn_records[b"hhea"]
    vh_asc, vh_desc = struct.unpack_from(">hh", vn_data, vn_hhea_off + 4)
    _, vn_os2_off, _ = vn_records[b"OS/2"]
    vo_tasc, vo_tdesc, _, vo_wasc, vo_wdesc = struct.unpack_from(
        ">hhhHH", vn_data, vn_os2_off + 68
    )
    vn_metrics_ok = (
        vn_upm == 700
        and (vh_asc, vh_desc) == (1100, -300)
        and (vo_tasc, vo_tdesc, vo_wasc, vo_wdesc) == (1100, -300, 1100, 300)
        and 0 <= vx_min <= vx_max <= ADVANCE_WIDTH
        and VN_DESCENDER <= vy_min < 0 < 700 < vy_max <= VN_ASCENDER
    )
    check(
        "VN: Metrics đúng (UPM=700, ascender=1100, descender=-300, winDescent=300)",
        vn_metrics_ok,
        f"head=({vx_min},{vy_min},{vx_max},{vy_max}), hhea=({vh_asc},{vh_desc}), OS/2=({vo_tasc},{vo_tdesc},{vo_wasc},{vo_wdesc})",
    )

    # 12. Kiểm tra cmap VN chứa đủ các chuỗi tiếng Việt yêu cầu và toàn bộ bảng nguyên âm + Đ/đ
    _, vn_cmap_off, vn_cmap_len = vn_records[b"cmap"]
    vn_cmap_bytes = vn_data[vn_cmap_off : vn_cmap_off + vn_cmap_len]
    sample_letters = "ĂÂĐÊÔƠƯăâđêôơư"
    sample_sentence = "Khởi động lại Tắt máy Chọn hệ điều hành Tự khởi động sau giây"

    missing_letters = [
        ch for ch in sample_letters if lookup_cmap_format4(vn_cmap_bytes, ord(ch)) == 0
    ]
    missing_sentence = [
        ch
        for ch in sample_sentence
        if ch != " " and lookup_cmap_format4(vn_cmap_bytes, ord(ch)) == 0
    ]

    all_vn_pairs_ok = True
    for _, _, chars_by_tone in VN_VOWEL_SPECS:
        for ch_u in chars_by_tone:
            gid_u = lookup_cmap_format4(vn_cmap_bytes, ord(ch_u))
            gid_l = lookup_cmap_format4(vn_cmap_bytes, ord(ch_u.lower()))
            if gid_u <= 0 or gid_u != gid_l:
                all_vn_pairs_ok = False
    gid_D_stroke = lookup_cmap_format4(vn_cmap_bytes, ord("Đ"))
    gid_d_stroke = lookup_cmap_format4(vn_cmap_bytes, ord("đ"))
    if gid_D_stroke <= 0 or gid_D_stroke != gid_d_stroke:
        all_vn_pairs_ok = False

    check(
        "VN: cmap chứa mọi ký tự trong 'ĂÂĐÊÔƠƯăâđêôơư' và câu mẫu tiếng Việt (HOA == thường)",
        not missing_letters and not missing_sentence and all_vn_pairs_ok,
        "OK"
        if (not missing_letters and not missing_sentence and all_vn_pairs_ok)
        else f"Thiếu: {missing_letters + missing_sentence}",
    )

    # 13. Kiểm tra bbox của mọi glyph trong VN nằm trong [0..ADVANCE_WIDTH] và [VN_DESCENDER..VN_ASCENDER]
    _, vn_loca_off, vn_loca_len = vn_records[b"loca"]
    vn_loca_offsets = list(
        struct.unpack_from(f">{vn_loca_len // 4}I", vn_data, vn_loca_off)
    )
    _, vn_glyf_off, _ = vn_records[b"glyf"]
    bbox_out_of_bounds: list[str] = []
    for gid in range(vn_num_glyphs):
        g_start = vn_loca_offsets[gid]
        g_end = vn_loca_offsets[gid + 1]
        if g_end > g_start:
            n_cnt, gx_min, gy_min, gx_max, gy_max = struct.unpack_from(
                ">hhhhh", vn_data, vn_glyf_off + g_start
            )
            if not (
                n_cnt > 0
                and 0 <= gx_min <= gx_max <= ADVANCE_WIDTH
                and VN_DESCENDER <= gy_min <= gy_max <= VN_ASCENDER
            ):
                bbox_out_of_bounds.append(
                    f"gid={gid}:({gx_min},{gy_min},{gx_max},{gy_max})"
                )
    check(
        "VN: Mọi glyph bbox nằm gọn trong advance (0..600) và descender..ascender (-300..1100)",
        not bbox_out_of_bounds,
        "OK" if not bbox_out_of_bounds else ", ".join(bbox_out_of_bounds[:5]),
    )

    return 0 if all_passed else 1


def main() -> int:
    """Điểm vào CLI của trình dựng font Kafka Pixel."""
    parser = argparse.ArgumentParser(
        description="Dựng font TrueType (.ttf) 'Kafka Pixel' (hoặc biến thể tiếng Việt --vietnamese) từ pixelfont.py 5x7."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Đường dẫn file .ttf đầu ra (mặc định: fonts/KafkaPixel.ttf, hoặc fonts/KafkaPixelVN.ttf khi có --vietnamese).",
    )
    parser.add_argument(
        "--vietnamese",
        action="store_true",
        help="Dựng biến thể tiếng Việt 'Kafka Pixel VN' (fonts/KafkaPixelVN.ttf).",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Chạy tự kiểm tra cấu trúc nhị phân của font (cả bản mặc định và bản tiếng Việt) trong thư mục tạm.",
    )
    args = parser.parse_args()

    if args.selftest:
        return run_selftest()

    default_name = "KafkaPixelVN.ttf" if args.vietnamese else "KafkaPixel.ttf"
    out_path: Path = args.out if args.out is not None else (SCRIPT_DIR / default_name)
    os.makedirs(out_path.parent, exist_ok=True)
    ttf_bytes, num_glyphs = assemble_ttf(vietnamese=args.vietnamese)
    out_path.write_bytes(ttf_bytes)
    family_label = "Kafka Pixel VN" if args.vietnamese else "Kafka Pixel"
    print(f"Đã dựng {family_label}: {num_glyphs} glyphs -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
