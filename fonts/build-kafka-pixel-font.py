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

# Hằng số thiết kế font
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


def rows_to_contours(rows: list[str]) -> list[list[tuple[int, int]]]:
    """Chuyển ma trận 7 dòng × 5 cột ('0'/'1') thành danh sách các contour hình chữ nhật.

    Gộp các ô '1' liền nhau trên cùng một dòng thành một hình chữ nhật (như hàm _blit).
    Mỗi hình chữ nhật gồm 4 điểm on-curve theo chiều KIM ĐỒNG HỒ:
    (x0, y0) -> (x0, y1) -> (x1, y1) -> (x1, y0).
    Dòng r = 0 ở trên cùng (y = 600..700), dòng r = 6 ở dưới cùng (y = 0..100).
    """
    contours: list[list[tuple[int, int]]] = []
    gh = len(rows)  # 7
    for r, row in enumerate(rows):
        y0 = (gh - 1 - r) * CELL_SIZE
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


def collect_glyphs_and_cmap() -> tuple[list[list[list[tuple[int, int]]]], dict[int, int]]:
    """Tạo danh sách glyph và bảng ánh xạ cmap từ pixelfont.GLYPHS.

    Quy tắc:
    - Glyph 0: .notdef (hình chữ nhật rỗng).
    - Glyph 1: ' ' (space, không có contour).
    - Các ký tự còn lại trong GLYPHS:
      + '<' ánh xạ vào U+25C0 (◀), KHÔNG ánh xạ vào '<' ASCII.
      + '>' ánh xạ vào U+25B6 (▶), KHÔNG ánh xạ vào '>' ASCII.
      + Chữ HOA 'A'..'Z' ánh xạ vào cả mã ASCII chữ HOA lẫn chữ thường 'a'..'z' (dùng chung glyph).
      + Các ký tự khác ánh xạ theo ord(ch).
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
    num_glyphs: int, min_lsb: int, min_rsb: int, x_max_extent: int
) -> bytes:
    """Dựng bảng 'hhea' (36 byte)."""
    return struct.pack(
        ">IhhhHhhhhhhhhhhhH",
        0x00010000,     # version 1.0
        ASCENDER,       # ascender = 900
        DESCENDER,      # descender = -200
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


def build_os2(cmap: dict[int, int]) -> bytes:
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
        ASCENDER,             # sTypoAscender = 900
        DESCENDER,            # sTypoDescender = -200
        LINE_GAP,             # sTypoLineGap = 0
        ASCENDER,             # usWinAscent = 900
        abs(DESCENDER),       # usWinDescent = 200
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


def build_name() -> bytes:
    """Dựng bảng 'name' format 0 với bản ghi Macintosh (1, 0, 0) và Windows (3, 1, 0x0409)."""
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


def assemble_ttf() -> tuple[bytes, int]:
    """Lắp ráp toàn bộ các bảng thành dữ liệu nhị phân TrueType (.ttf) hoàn chỉnh.

    Trả về (ttf_bytes, num_glyphs).
    """
    glyph_contours, cmap = collect_glyphs_and_cmap()
    num_glyphs = len(glyph_contours)

    glyf_data, loca_data, bboxes, is_empty, max_pts, max_cnts = build_glyf_and_loca(
        glyph_contours
    )
    hmtx_data, min_lsb, min_rsb, x_max_extent = build_hmtx(bboxes, is_empty)

    now_1904 = int(time.time()) + EPOCH_1904_OFFSET

    tables: dict[bytes, bytes] = {
        b"OS/2": build_os2(cmap),
        b"cmap": build_cmap(cmap),
        b"glyf": glyf_data,
        b"head": build_head(bboxes, is_empty, now_1904, check_sum_adjustment=0),
        b"hhea": build_hhea(num_glyphs, min_lsb, min_rsb, x_max_extent),
        b"hmtx": hmtx_data,
        b"loca": loca_data,
        b"maxp": build_maxp(num_glyphs, max_pts, max_cnts),
        b"name": build_name(),
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

    return 0 if all_passed else 1


def main() -> int:
    """Điểm vào CLI của trình dựng font Kafka Pixel."""
    default_out = SCRIPT_DIR / "KafkaPixel.ttf"
    parser = argparse.ArgumentParser(
        description="Dựng font TrueType (.ttf) 'Kafka Pixel' từ pixelfont.py 5x7."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=default_out,
        help="Đường dẫn file .ttf đầu ra (mặc định: fonts/KafkaPixel.ttf cạnh script).",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Chạy tự kiểm tra cấu trúc nhị phân của font trong thư mục tạm.",
    )
    args = parser.parse_args()

    if args.selftest:
        return run_selftest()

    out_path: Path = args.out
    os.makedirs(out_path.parent, exist_ok=True)
    ttf_bytes, num_glyphs = assemble_ttf()
    out_path.write_bytes(ttf_bytes)
    print(f"Đã dựng Kafka Pixel: {num_glyphs} glyphs -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
