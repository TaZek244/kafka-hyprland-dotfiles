#!/usr/bin/env python3
"""
Trình tạo bộ biểu tượng (icon theme) "Kafka" dựa trên Papirus-Dark.

Mục đích:
  Tạo một bộ icon theme tên "Kafka" kế thừa từ Papirus-Dark, trong đó toàn bộ
  biểu tượng thư mục (places: folder-*, user-*) được chuyển từ tông violet
  sang bảng màu hồng-tím lấy cảm hứng từ nhân vật Kafka (Honkai: Star Rail),
  kèm hiệu ứng chuyển sắc (gradient) và họa tiết mạng nhện tinh tế ở góc dưới.

Giấy phép (License):
  Các biểu tượng gốc thuộc dự án Papirus Icon Theme (https://github.com/PapirusDevelopmentTeam/papirus-icon-theme),
  được phát hành theo Giấy phép Công cộng GNU phiên bản 3 (GPL-3.0).
  Bản phái sinh "Kafka" được tạo bởi công cụ này giữ nguyên giấy phép GPL-3.0.
"""

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Bảng ánh xạ màu từ tông Violet của Papirus sang tông Hồng-Tím Kafka.
# Các khóa phải viết thường để tra cứu không phân biệt hoa thường.
COLOR_MAP: Dict[str, str] = {
    # Màu chính trên biểu tượng thư mục Papirus
    "#5d399b": "#7a2758",          # Mặt sau / phần tab thư mục
    "#7e57c2": "url(#kafkaFront)", # Mặt trước thư mục (dùng gradient)
    "#e4e4e4": "#f6e3ee",          # Tờ giấy kẹp bên trong thư mục
    "#2c1e44": "#fff2f8",          # Biểu tượng nhỏ (glyph) trên mặt trước (sẽ kèm opacity 0.92)
    # Các sắc độ violet phụ (sáng -> #f7a6cc, tối -> #5a1d45)
    "#9575cd": "#f7a6cc",
    "#b39ddb": "#f7a6cc",
    "#d1c4e9": "#f7a6cc",
    "#673ab7": "#5a1d45",
    "#4527a0": "#5a1d45",
    "#311b92": "#5a1d45",
}

# Màu của glyph cần thêm opacity 0.92
GLYPH_OLD_COLOR = "#2c1e44"
GLYPH_NEW_COLOR = COLOR_MAP[GLYPH_OLD_COLOR]
GLYPH_OPACITY = "0.92"

# Màu mặt trước gốc dùng để nhận diện hình chữ nhật mặt trước
FRONT_OLD_COLOR = "#7e57c2"

# Danh sách các thư mục kích thước chuẩn của Papirus cần quét
PAPIRUS_SIZES: Tuple[str, ...] = (
    "16x16", "16x16@2x",
    "18x18", "18x18@2x",
    "22x22", "22x22@2x",
    "24x24", "24x24@2x",
    "32x32", "32x32@2x",
    "48x48", "48x48@2x",
    "64x64", "64x64@2x",
    "84x84",
    "96x96",
    "128x128",
)

# Biểu thức chính quy khớp tên file violet trong thư mục places/
VIOLET_FILE_RE = re.compile(r"^(folder|user)-violet(-.*)?\.svg$")

# Khối định nghĩa gradient mặt trước thư mục
KAFKA_GRADIENT_DEFS = (
    '<defs>'
    '<linearGradient id="kafkaFront" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#e0559a"/>'
    '<stop offset="0.55" stop-color="#c94785"/>'
    '<stop offset="1" stop-color="#8e4fc4"/>'
    '</linearGradient>'
    '</defs>'
)


def canonical_name(filename: str) -> str:
    """
    Chuyển tên file biến thể '-violet' sang tên chuẩn.
    Ví dụ:
      'folder-violet-music.svg' -> 'folder-music.svg'
      'user-violet-home.svg'    -> 'user-home.svg'
      'folder-violet.svg'       -> 'folder.svg'
    """
    match = VIOLET_FILE_RE.match(filename)
    if not match:
        return filename
    prefix = match.group(1)
    suffix = match.group(2) or ""
    return f"{prefix}{suffix}.svg"


def _parse_float(val: Optional[str]) -> Optional[float]:
    """Đọc số thực từ chuỗi thuộc tính SVG (bỏ đơn vị px nếu có)."""
    if val is None:
        return None
    cleaned = val.strip()
    if cleaned.endswith("px"):
        cleaned = cleaned[:-2].strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_attr(tag_text: str, attr_name: str) -> Optional[str]:
    """Trích xuất giá trị thuộc tính từ một thẻ mở/tự đóng SVG."""
    pattern = rf'\b{ re.escape(attr_name) }\s*=\s*(["\'])(.*?)\1'
    m = re.search(pattern, tag_text, flags=re.IGNORECASE | re.DOTALL)
    return m.group(2) if m else None


def _get_svg_width(svg_text: str) -> Optional[float]:
    """Lấy giá trị thuộc tính width trên thẻ mở <svg ...>."""
    m = re.search(r"<svg\b[^>]*>", svg_text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return _parse_float(_extract_attr(m.group(0), "width"))


def _has_fill_color(tag_text: str, hex_color: str) -> bool:
    """Kiểm tra xem một thẻ SVG có chứa fill=<hex_color> hoặc style='...fill:<hex_color>...' không."""
    esc = re.escape(hex_color)
    # Kiểm tra trong style="...fill:#xxxxxx..."
    if re.search(rf"fill\s*:\s*{esc}\b", tag_text, flags=re.IGNORECASE):
        return True
    # Kiểm tra thuộc tính rời fill="#xxxxxx"
    if re.search(rf'\bfill\s*=\s*["\']\s*{esc}\s*["\']', tag_text, flags=re.IGNORECASE):
        return True
    return False


def _find_front_rect(svg_text: str) -> Optional[Dict[str, Optional[float]]]:
    """
    Tìm phần tử <rect> mặt trước có màu fill #7e57c2.
    Trả về dict chứa x, y, width, height, rx, ry (nếu có).
    """
    for m in re.finditer(r"<rect\b[^>]*>", svg_text, flags=re.IGNORECASE | re.DOTALL):
        tag = m.group(0)
        if _has_fill_color(tag, FRONT_OLD_COLOR):
            w = _parse_float(_extract_attr(tag, "width"))
            h = _parse_float(_extract_attr(tag, "height"))
            x = _parse_float(_extract_attr(tag, "x"))
            y = _parse_float(_extract_attr(tag, "y"))
            if w is None or h is None:
                continue
            rx = _parse_float(_extract_attr(tag, "rx"))
            ry = _parse_float(_extract_attr(tag, "ry"))
            return {
                "x": x if x is not None else 0.0,
                "y": y if y is not None else 0.0,
                "width": w,
                "height": h,
                "rx": rx,
                "ry": ry,
            }
    return None


def _fmt_num(val: float) -> str:
    """Định dạng số thực gọn gàng cho tọa độ SVG."""
    rounded = round(val, 3)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.3f}".rstrip("0").rstrip(".")


def _build_spiderweb_group(rect: Dict[str, Optional[float]], svg_width: float) -> str:
    """
    Tạo khối <defs><clipPath.../></defs> và nhóm <g> vẽ góc mạng nhện ở góc dưới-phải
    của hình chữ nhật mặt trước thư mục.
    """
    x = rect["x"] or 0.0
    y = rect["y"] or 0.0
    w = rect["width"] or 0.0
    h = rect["height"] or 0.0
    rx = rect["rx"]
    ry = rect["ry"]

    # Tâm mạng nhện tại góc dưới-phải của mặt trước, bán kính R = 0.42 * height
    cx = x + w
    cy = y + h
    radius = 0.42 * h

    # 5 tia hướng sang phần tư trên-trái: 180°, 202.5°, 225°, 247.5°, 270°
    angles_deg = (180.0, 202.5, 225.0, 247.5, 270.0)
    angles_rad = [math.radians(a) for a in angles_deg]

    # Độ dày nét vẽ theo kích thước logic của SVG
    stroke_w = max(0.5, (svg_width / 48.0) * 0.8)

    # Thuộc tính bo góc của clipPath rect (chịu được trường hợp thiếu rx/ry)
    rx_attr = f' rx="{_fmt_num(rx)}"' if rx is not None else ""
    ry_attr = f' ry="{_fmt_num(ry)}"' if ry is not None else ""

    clip_rect = (
        f'<rect x="{_fmt_num(x)}" y="{_fmt_num(y)}" '
        f'width="{_fmt_num(w)}" height="{_fmt_num(h)}"{rx_attr}{ry_attr}/>'
    )
    clip_defs = f'<defs><clipPath id="kafkaWebClip">{clip_rect}</clipPath></defs>'

    # Vẽ các tia từ tâm ra ngoài
    spoke_Commands: List[str] = []
    for rad in angles_rad:
        px = cx + radius * math.cos(rad)
        py = cy + radius * math.sin(rad)
        spoke_Commands.append(
            f"M {_fmt_num(cx)},{_fmt_num(cy)} L {_fmt_num(px)},{_fmt_num(py)}"
        )

    # Vẽ 3 vòng tơ nối các tia liền kề ở bán kính 0.35R, 0.65R, 0.95R
    # Sử dụng đường cong bậc hai (Q) với điểm điều khiển kéo về tâm 12%
    ring_scales = (0.35, 0.65, 0.95)
    ring_commands: List[str] = []
    for scale in ring_scales:
        r_ring = radius * scale
        pts = [
            (cx + r_ring * math.cos(rad), cy + r_ring * math.sin(rad))
            for rad in angles_rad
        ]
        if not pts:
            continue
        seg = [f"M {_fmt_num(pts[0][0])},{_fmt_num(pts[0][1])}"]
        for i in range(len(pts) - 1):
            p1 = pts[i]
            p2 = pts[i + 1]
            mid_x = 0.5 * (p1[0] + p2[0])
            mid_y = 0.5 * (p1[1] + p2[1])
            # Kéo điểm trung điểm về phía tâm (cx, cy) 12%
            ctrl_x = mid_x + 0.12 * (cx - mid_x)
            ctrl_y = mid_y + 0.12 * (cy - mid_y)
            seg.append(
                f"Q {_fmt_num(ctrl_x)},{_fmt_num(ctrl_y)} "
                f"{_fmt_num(p2[0])},{_fmt_num(p2[1])}"
            )
        ring_commands.append(" ".join(seg))

    all_d = " ".join(spoke_Commands + ring_commands)
    web_group = (
        f'{clip_defs}'
        f'<g id="kafkaSpiderWeb" clip-path="url(#kafkaWebClip)" '
        f'stroke="#ffffff" stroke-opacity="0.22" fill="none" '
        f'stroke-width="{_fmt_num(stroke_w)}" stroke-linecap="round">'
        f'<path d="{all_d}"/>'
        f'</g>'
    )
    return web_group


def _replace_glyph_element(tag_text: str) -> str:
    """
    Đổi màu glyph #2c1e44 -> #fff2f8 và bổ sung opacity 0.92 trên phần tử chứa nó.
    Xử lý cả dạng style="...fill:#2c1e44..." lẫn thuộc tính rời fill="#2c1e44".
    """
    esc_old = re.escape(GLYPH_OLD_COLOR)

    # Trường hợp 1: Màu nằm trong thuộc tính style="..."
    def _update_style(match: re.Match) -> str:
        quote = match.group(1)
        style_val = match.group(2)
        if not re.search(rf"fill\s*:\s*{esc_old}\b", style_val, flags=re.IGNORECASE):
            return match.group(0)
        new_style = re.sub(
            rf"(fill\s*:\s*){esc_old}\b",
            rf"\1{GLYPH_NEW_COLOR}",
            style_val,
            flags=re.IGNORECASE,
        )
        # Nếu chưa có thuộc tính opacity rời trong style thì nối thêm opacity:0.92
        if not re.search(r"(?<![-\w])opacity\s*:", new_style, flags=re.IGNORECASE):
            new_style = new_style.rstrip().rstrip(";") + f";opacity:{GLYPH_OPACITY}"
        return f"style={quote}{new_style}{quote}"

    updated = re.sub(
        r'\bstyle\s*=\s*(["\'])(.*?)\1',
        _update_style,
        tag_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Trường hợp 2: Màu nằm trong thuộc tính rời fill="#2c1e44"
    if re.search(rf'\bfill\s*=\s*["\']\s*{esc_old}\s*["\']', updated, flags=re.IGNORECASE):
        updated = re.sub(
            rf'(\bfill\s*=\s*["\'])\s*{esc_old}\s*(["\'])',
            rf"\1{GLYPH_NEW_COLOR}\2",
            updated,
            flags=re.IGNORECASE,
        )
        # Nếu thẻ chưa có opacity="..." và cũng chưa có opacity trong style
        has_opacity_attr = re.search(r'\bopacity\s*=\s*["\']', updated, flags=re.IGNORECASE)
        has_opacity_style = re.search(r"(?<![-\w])opacity\s*:", updated, flags=re.IGNORECASE)
        if not has_opacity_attr and not has_opacity_style:
            if updated.endswith("/>"):
                updated = updated[:-2] + f' opacity="{GLYPH_OPACITY}"/>'
            elif updated.endswith(">"):
                updated = updated[:-1] + f' opacity="{GLYPH_OPACITY}">'

    return updated


def transform_svg(svg_text: str) -> str:
    """
    Biến đổi nội dung SVG từ tông màu violet của Papirus sang phong cách Kafka:
      1. Chèn <defs> chứa linearGradient #kafkaFront ngay sau thẻ mở <svg ...>.
      2. Nếu kích thước gốc của SVG (width) >= 32 và tìm thấy <rect> mặt trước (#7e57c2),
         chèn nhóm họa tiết mạng nhện trước phần tử glyph đầu tiên (#2c1e44) hoặc trước </svg>.
      3. Thay thế bảng màu theo COLOR_MAP (bao gồm bổ sung opacity 0.92 cho glyph #2c1e44).
    """
    result = svg_text

    # 0. Icon không phải hình thư mục (vd user-desktop: màn hình) không có mặt sau #5d399b; ở đó
    #    #2c1e44 là thanh/đế màn hình tối chứ không phải glyph → giữ tối (đổi sang tím than).
    if not re.search(r"#5d399b", result, flags=re.IGNORECASE):
        result = re.sub(r"#2c1e44", "#4a1a3c", result, flags=re.IGNORECASE)

    # 1. Tìm hình chữ nhật mặt trước và kích thước SVG trước khi đổi màu
    svg_width = _get_svg_width(result)
    front_rect = _find_front_rect(result)

    # 2. Chèn họa tiết mạng nhện nếu width >= 32 và có rect mặt trước
    if svg_width is not None and svg_width >= 32.0 and front_rect is not None:
        web_svg = _build_spiderweb_group(front_rect, svg_width)
        # Kiểm tra xem có phần tử nào chứa màu glyph (#2c1e44) không
        glyph_tag_match = None
        for m in re.finditer(r"<[a-zA-Z0-9:_-]+\b[^>]*>", result, flags=re.DOTALL):
            if _has_fill_color(m.group(0), GLYPH_OLD_COLOR):
                glyph_tag_match = m
                break

        if glyph_tag_match is not None:
            idx = glyph_tag_match.start()
            result = result[:idx] + web_svg + "\n " + result[idx:]
        else:
            close_match = re.search(r"</svg\s*>", result, flags=re.IGNORECASE)
            if close_match:
                idx = close_match.start()
                result = result[:idx] + " " + web_svg + "\n" + result[idx:]

    # 3. Chèn khối <defs><linearGradient id="kafkaFront".../></defs> ngay sau thẻ mở <svg ...>
    svg_open_match = re.search(r"<svg\b[^>]*>", result, flags=re.IGNORECASE | re.DOTALL)
    if svg_open_match:
        insert_pos = svg_open_match.end()
        result = result[:insert_pos] + "\n " + KAFKA_GRADIENT_DEFS + result[insert_pos:]

    # 4. Đổi màu glyph #2c1e44 kèm opacity 0.92 trên từng thẻ chứa nó
    def _process_tag(match: re.Match) -> str:
        tag = match.group(0)
        if _has_fill_color(tag, GLYPH_OLD_COLOR):
            return _replace_glyph_element(tag)
        return tag

    result = re.sub(r"<[a-zA-Z0-9:_-]+\b[^>]*>", _process_tag, result, flags=re.DOTALL)

    # 5. Thay thế các màu còn lại trong COLOR_MAP (cả dạng fill:#hex và fill="#hex")
    for old_hex, new_val in COLOR_MAP.items():
        if old_hex.lower() == GLYPH_OLD_COLOR:
            continue
        esc = re.escape(old_hex)
        # Thay trong thuộc tính style="...fill:#xxxxxx..."
        result = re.sub(
            rf"(fill\s*:\s*){esc}\b",
            rf"\1{new_val}",
            result,
            flags=re.IGNORECASE,
        )
        # Thay trong thuộc tính rời fill="#xxxxxx"
        result = re.sub(
            rf'(\bfill\s*=\s*["\'])\s*{esc}\s*(["\'])',
            rf"\1{new_val}\2",
            result,
            flags=re.IGNORECASE,
        )

    return result


def build_index_theme(src_dir: Path, out_dir: Path) -> bool:
    """
    Tạo file index.theme cho theme Kafka từ <src-dark>/index.theme (ưu tiên Papirus-Dark cùng cấp)
    hoặc <src>/index.theme. Đổi Name, Comment, Inherits và giữ nguyên Directories.
    """
    parent_dir = src_dir.parent
    src_dark_index = parent_dir / "Papirus-Dark" / "index.theme"
    src_index = src_dark_index if src_dark_index.is_file() else (src_dir / "index.theme")

    if not src_index.is_file():
        return False

    content = src_index.read_text(encoding="utf-8")
    lines = content.splitlines()
    out_lines: List[str] = []
    in_icon_theme_section = False
    has_inherits = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            # Nếu rời khỏi [Icon Theme] mà chưa gặp dòng Inherits= thì chèn vào
            if in_icon_theme_section and not has_inherits:
                out_lines.append("Inherits=Papirus-Dark,Papirus,breeze-dark,hicolor")
                has_inherits = True
            in_icon_theme_section = (stripped == "[Icon Theme]")
            out_lines.append(line)
            continue

        if in_icon_theme_section:
            if re.match(r"^Name\s*=", stripped):
                out_lines.append("Name=Kafka")
                continue
            if re.match(r"^Comment\s*=", stripped):
                out_lines.append("Comment=Papirus-Dark với thư mục hồng tím Kafka")
                continue
            if re.match(r"^Inherits\s*=", stripped):
                out_lines.append("Inherits=Papirus-Dark,Papirus,breeze-dark,hicolor")
                has_inherits = True
                continue

        out_lines.append(line)

    if in_icon_theme_section and not has_inherits:
        out_lines.append("Inherits=Papirus-Dark,Papirus,breeze-dark,hicolor")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.theme").write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return True


def safe_clean_output(out_dir: Path) -> None:
    """
    Xóa sạch thư mục <out> cũ trước khi dựng.
    Để đảm bảo an toàn, chỉ gọi shutil.rmtree khi đường dẫn chuẩn hóa kết thúc bằng '/Kafka'.
    """
    normalized = os.path.normpath(str(out_dir))
    if not normalized.endswith("/Kafka"):
        raise ValueError(
            f"Từ chối xóa thư mục đích vì đường dẫn không kết thúc bằng '/Kafka': {normalized}"
        )
    if out_dir.exists():
        shutil.rmtree(out_dir)


def build_theme(src_dir: Path, out_dir: Path) -> int:
    """
    Dựng toàn bộ icon theme Kafka từ thư mục nguồn Papirus (src_dir) sang (out_dir).
    Trả về tổng số file đã tạo (gồm các file SVG và index.theme).
    """
    if not src_dir.is_dir():
        raise FileNotFoundError(f"Không tìm thấy thư mục nguồn Papirus: {src_dir}")

    safe_clean_output(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    created_count = 0

    if build_index_theme(src_dir, out_dir):
        created_count += 1

    for size_name in PAPIRUS_SIZES:
        places_src = src_dir / size_name / "places"
        if not places_src.is_dir():
            continue

        places_out = out_dir / size_name / "places"
        entries = sorted(os.listdir(places_src))

        for entry in entries:
            if not VIOLET_FILE_RE.match(entry):
                continue

            src_file = places_src / entry
            if not src_file.is_file():
                continue

            # Đọc nội dung thật của file (tự động đi qua symlink nếu là symlink)
            with open(src_file, "r", encoding="utf-8") as f:
                raw_svg = f.read()

            transformed = transform_svg(raw_svg)
            target_name = canonical_name(entry)

            places_out.mkdir(parents=True, exist_ok=True)
            target_path = places_out / target_name
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(transformed)

            created_count += 1

        # Tên phụ: Papirus có tên trỏ vòng qua tên khác rồi mới tới bản màu xanh mặc định
        # (vd folder-publicshare → folder-image-people → folder-blue-image-people). Tên nào cuối cùng
        # trỏ tới (folder|user)-blue[-x].svg thì tạo symlink sang bản Kafka (folder|user)[-x].svg đã dựng.
        if places_out.is_dir():
            for entry in entries:
                src_file = places_src / entry
                if not src_file.is_symlink() or (places_out / entry).exists():
                    continue
                real = os.path.basename(os.path.realpath(src_file))
                m = re.match(r"^(folder|user)-blue(-.*)?\.svg$", real)
                if not m:
                    continue
                canon = f"{m.group(1)}{m.group(2) or ''}.svg"
                if canon != entry and (places_out / canon).is_file():
                    os.symlink(canon, places_out / entry)
                    created_count += 1

    # Cập nhật icon cache của GTK nếu có công cụ gtk-update-icon-cache
    if shutil.which("gtk-update-icon-cache"):
        try:
            subprocess.run(
                ["gtk-update-icon-cache", "-f", "-t", str(out_dir)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    return created_count


# ---------------------------------------------------------------------------
# Dữ liệu mẫu và bộ tự kiểm tra (--selftest)
# ---------------------------------------------------------------------------

SAMPLE_SVG_48 = """<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" version="1">
 <rect style="opacity:0.2" width="40" height="26" x="4" y="17" rx="2" ry="2"/>
 <path style="fill:#5d399b" d="M 4,34 C 4,35.108 4.892,36 6,36 H 42 C 43.108,36 44,35.108 44,34 V 12 C 44,10.892 43.108,10 42,10 H 24 C 21,10 20,6 17,6 H 6 C 4.892,6 4,6.892 4,8"/>
 <rect style="opacity:0.2" width="40" height="26" x="4" y="15" rx="2" ry="2"/>
 <rect style="fill:#e4e4e4" width="36" height="16" x="6" y="13" rx="2" ry="2"/>
 <rect style="fill:#7e57c2" width="40" height="26" x="4" y="16" rx="2" ry="2"/>
 <path style="opacity:0.1;fill:#ffffff" d="M 6,6 C 4.892,6 4,6.892 4,8 V 9 C 4,7.892 4.892,7 6,7 H 17 C 20,7 21,11 24,11 H 42 C 43.108,11 44,11.892 44,13 V 12 C 44,10.892 43.108,10 42,10 H 24 C 21,10 20,6 17,6 Z"/>
</svg>"""

SAMPLE_GLYPH_PATH = (
    ' <path style="fill:#2c1e44" d="M 21,30.176 C 20.679,30.061 20.341,30.001 20,30 '
    "18.343,30 17,31.343 17,33 17,34.657 18.343,36 20,36 21.657,36 23,34.657 23,33 V 26 "
    "H 29 V 30.176 C 28.679,30.061 28.341,30.001 28,30 26.343,30 25,31.343 25,33 "
    "25,34.657 26.343,36 28,36 29.657,36 31,34.657 31,33 V 23 C 31,22.446 30.331,22 "
    '29.5,22 H 22.5 C 21.669,22 21,22.446 21,23"/>\n'
)

SAMPLE_SVG_48_MUSIC = SAMPLE_SVG_48.replace("</svg>", SAMPLE_GLYPH_PATH + "</svg>")

# Bản 16x16 dùng thuộc tính fill="..." trực tiếp và rect không có rx/ry
SAMPLE_SVG_16 = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" version="1">
 <path fill="#5d399b" d="M 1,12 V 3 H 7 L 9,5 H 15 V 12 Z"/>
 <rect fill="#e4e4e4" width="12" height="6" x="2" y="4"/>
 <rect fill="#7e57c2" width="14" height="9" x="1" y="6"/>
 <path fill="#2c1e44" d="M 6,8 H 10 V 12 H 6 Z"/>
</svg>"""


def run_selftest() -> int:
    """
    Chạy bộ kiểm tra tự động (--selftest) trên chuỗi SVG mẫu và cây thư mục tạm.
    In PASS/FAIL cho từng mục và trả về 0 nếu đạt toàn bộ, 1 nếu có lỗi.
    """
    all_passed = True

    def report(name: str, ok: bool, detail: str = "") -> None:
        nonlocal all_passed
        status = "PASS" if ok else "FAIL"
        suffix = f" ({detail})" if detail else ""
        print(f"[{status}] {name}{suffix}")
        if not ok:
            all_passed = False

    out_48 = transform_svg(SAMPLE_SVG_48)
    out_48_music = transform_svg(SAMPLE_SVG_48_MUSIC)
    out_16 = transform_svg(SAMPLE_SVG_16)

    # (1) Không còn các mã màu violet gốc (#7e57c2, #5d399b, #2c1e44)
    forbidden = ("#7e57c2", "#5d399b", "#2c1e44")
    no_old_colors = all(
        c not in out_48.lower()
        and c not in out_48_music.lower()
        and c not in out_16.lower()
        for c in forbidden
    )
    has_new_colors = (
        "#7a2758" in out_48_music.lower()
        and "#f6e3ee" in out_48_music.lower()
        and "#fff2f8" in out_48_music.lower()
        and "opacity:0.92" in out_48_music.lower()
        and "#fff2f8" in out_16.lower()
        and 'opacity="0.92"' in out_16.lower()
    )
    report(
        "1. Đổi màu (#7e57c2, #5d399b, #2c1e44) và thêm opacity 0.92 cho glyph",
        no_old_colors and has_new_colors,
    )

    # (2) Có url(#kafkaFront) và <linearGradient id="kafkaFront"
    has_grad = all(
        "url(#kafkaFront)" in s and '<linearGradient id="kafkaFront"' in s
        for s in (out_48, out_48_music, out_16)
    )
    report(
        "2. Chèn gradient url(#kafkaFront) và <linearGradient id=\"kafkaFront\"",
        has_grad,
    )

    # (3) Với width=48 có clipPath kafkaWebClip và nhóm mạng nhện nằm trước glyph;
    #     với width=16 thì không có
    web_in_48 = 'id="kafkaWebClip"' in out_48 and 'clip-path="url(#kafkaWebClip)"' in out_48
    web_pos = out_48_music.find('clip-path="url(#kafkaWebClip)"')
    glyph_pos = out_48_music.find("#fff2f8")
    web_before_glyph = (web_pos != -1 and glyph_pos != -1 and web_pos < glyph_pos)
    no_web_in_16 = "kafkaWebClip" not in out_16
    report(
        "3. Mạng nhện: có ở width=48 (nằm trước glyph) và không có ở width=16",
        web_in_48 and web_before_glyph and no_web_in_16,
    )

    # (4) Kết quả parse được bằng xml.etree.ElementTree.fromstring
    xml_ok = True
    xml_err = ""
    try:
        for s in (out_48, out_48_music, out_16):
            ET.fromstring(s)
    except ET.ParseError as exc:
        xml_ok = False
        xml_err = str(exc)
    report("4. Kết quả SVG hợp lệ với xml.etree.ElementTree.fromstring", xml_ok, xml_err)

    # (5) Hàm canonical_name
    c1 = canonical_name("folder-violet-music.svg") == "folder-music.svg"
    c2 = canonical_name("user-violet-home.svg") == "user-home.svg"
    c3 = canonical_name("folder-violet.svg") == "folder.svg"
    report(
        "5. Kiểm tra hàm canonical_name()",
        c1 and c2 and c3,
    )

    # (6) Chạy build end-to-end trong thư mục tạm
    e2e_ok = True
    e2e_detail = ""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            fake_papirus = tmp_root / "Papirus"
            fake_papirus_dark = tmp_root / "Papirus-Dark"
            fake_out = tmp_root / "Kafka"

            fake_papirus_dark.mkdir(parents=True)
            (fake_papirus_dark / "index.theme").write_text(
                "[Icon Theme]\n"
                "Name=Papirus-Dark\n"
                "Comment=Papirus Dark Icon Theme\n"
                "Inherits=Papirus,breeze-dark,hicolor\n"
                "Directories=16x16/places,48x48/places\n\n"
                "[16x16/places]\nSize=16\nContext=Places\nType=Fixed\n\n"
                "[48x48/places]\nSize=48\nContext=Places\nType=Fixed\n",
                encoding="utf-8",
            )

            places_16 = fake_papirus / "16x16" / "places"
            places_48 = fake_papirus / "48x48" / "places"
            places_16.mkdir(parents=True)
            places_48.mkdir(parents=True)

            (places_16 / "folder-violet.svg").write_text(SAMPLE_SVG_16, encoding="utf-8")
            (places_16 / "user-violet-home.svg").write_text(SAMPLE_SVG_16, encoding="utf-8")
            (places_48 / "folder-violet.svg").write_text(SAMPLE_SVG_48, encoding="utf-8")
            (places_48 / "folder-violet-music.svg").write_text(SAMPLE_SVG_48_MUSIC, encoding="utf-8")
            # Tạo một symlink giả lập cấu trúc Papirus
            os.symlink("folder-violet-music.svg", places_48 / "user-violet-desktop.svg")
            # File màu khác không được chạm tới
            (places_48 / "folder-blue.svg").write_text(SAMPLE_SVG_48, encoding="utf-8")

            total = build_theme(fake_papirus, fake_out)

            expected_files = [
                fake_out / "index.theme",
                fake_out / "16x16" / "places" / "folder.svg",
                fake_out / "16x16" / "places" / "user-home.svg",
                fake_out / "48x48" / "places" / "folder.svg",
                fake_out / "48x48" / "places" / "folder-music.svg",
                fake_out / "48x48" / "places" / "user-desktop.svg",
            ]
            for ef in expected_files:
                if not ef.is_file() or ef.is_symlink():
                    e2e_ok = False
                    e2e_detail = f"Thiếu hoặc là symlink: {ef}"
                    break

            # Đảm bảo không tạo file có chữ -violet hay -blue
            if (fake_out / "48x48" / "places" / "folder-violet.svg").exists():
                e2e_ok = False
                e2e_detail = "File folder-violet.svg không nên tồn tại ở đầu ra"
            if (fake_out / "48x48" / "places" / "folder-blue.svg").exists():
                e2e_ok = False
                e2e_detail = "File folder-blue.svg không nên tồn tại ở đầu ra"

            # Kiểm tra nội dung index.theme
            idx_text = (fake_out / "index.theme").read_text(encoding="utf-8")
            if (
                "Name=Kafka" not in idx_text
                or "Comment=Papirus-Dark với thư mục hồng tím Kafka" not in idx_text
                or "Inherits=Papirus-Dark,Papirus,breeze-dark,hicolor" not in idx_text
                or "Directories=16x16/places,48x48/places" not in idx_text
            ):
                e2e_ok = False
                e2e_detail = "Nội dung index.theme không khớp yêu cầu"

            if total != len(expected_files):
                e2e_ok = False
                e2e_detail = f"Số lượng file tạo ra ({total}) khác kỳ vọng ({len(expected_files)})"
    except Exception as exc:  # pragma: no cover
        e2e_ok = False
        e2e_detail = str(exc)

    report("6. Kiểm tra dựng end-to-end trên cây thư mục tạm", e2e_ok, e2e_detail)

    return 0 if all_passed else 1


def resolve_default_src() -> Path:
    """Tìm đường dẫn mặc định của Papirus: /usr/share/icons/Papirus hoặc ~/.local/share/icons/Papirus."""
    sys_path = Path("/usr/share/icons/Papirus")
    if sys_path.is_dir():
        return sys_path
    user_path = Path(os.path.expanduser("~/.local/share/icons/Papirus"))
    if user_path.is_dir():
        return user_path
    return sys_path


def main(argv: Optional[List[str]] = None) -> int:
    """Điểm vào chính của chương trình."""
    parser = argparse.ArgumentParser(
        description="Dựng bộ icon theme Kafka (Papirus-Dark với thư mục hồng-tím Kafka)."
    )
    parser.add_argument(
        "--src",
        type=str,
        default=None,
        help="Thư mục nguồn Papirus (mặc định: /usr/share/icons/Papirus, fallback ~/.local/share/icons/Papirus)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="~/.local/share/icons/Kafka",
        help="Thư mục đích chứa theme Kafka (mặc định: ~/.local/share/icons/Kafka)",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Chạy bộ kiểm tra tự động với dữ liệu mẫu và thư mục tạm, không chạm hệ thống thật",
    )

    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    src_dir = (
        Path(os.path.expanduser(args.src))
        if args.src is not None
        else resolve_default_src()
    )
    out_dir = Path(os.path.expanduser(args.out))

    try:
        total_created = build_theme(src_dir, out_dir)
    except Exception as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1

    print(f"Đã tạo thành công {total_created} file cho icon theme Kafka tại: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
