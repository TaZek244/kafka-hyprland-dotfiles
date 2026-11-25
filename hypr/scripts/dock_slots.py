"""dock_slots.py — ô dùng chung của dock 4 ngăn (dock-apps.py, dock-pins.py): ô TRỐNG và ô "+N".

Các ngăn có số ô CỐ ĐỊNH (FAV 6, RUN 4, BG 3) để ngăn bên dưới không bao giờ xê dịch: ô chưa dùng vẫn vẽ
(bản pixel = ô kho đồ chìm, bản phẳng = ảnh trong suốt), ngăn quá đầy thì ô cuối thành "+N" (bấm = dock-more.py).
"""

import os
import tempfile
from pathlib import Path

OUT_PX = 40
DARK = (20 / 255, 14 / 255, 26 / 255)


def pixel_theme_enabled():
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "kafka" / "ui-theme"
    try:
        return state.read_text(encoding="utf-8").strip() == "pixel"
    except OSError:
        return False


def _frame(ctx, inner):
    """Khung ô kho đồ 40x40 bậc thang (giống _pixel_surface của dock-apps.py)."""
    ctx.set_source_rgb(*DARK)
    ctx.move_to(2, 0)
    ctx.line_to(38, 0)
    ctx.line_to(40, 2)
    ctx.line_to(40, 38)
    ctx.line_to(38, 40)
    ctx.line_to(2, 40)
    ctx.line_to(0, 38)
    ctx.line_to(0, 2)
    ctx.close_path()
    ctx.fill()
    for (x, y, w, h), col in (
        ((2, 2, 36, 36), inner),
        ((2, 2, 36, 2), (15 / 255, 10 / 255, 20 / 255)),
        ((2, 2, 2, 36), (15 / 255, 10 / 255, 20 / 255)),
        ((2, 38, 36, 2), (74 / 255, 60 / 255, 89 / 255)),
        ((38, 2, 2, 36), (74 / 255, 60 / 255, 89 / 255)),
    ):
        ctx.set_source_rgb(*col)
        ctx.rectangle(x, y, w, h)
        ctx.fill()


def empty_surface(pixel=None):
    import cairo

    pixel = pixel_theme_enabled() if pixel is None else pixel
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, OUT_PX, OUT_PX)
    if pixel:
        ctx = cairo.Context(s)
        ctx.set_antialias(cairo.ANTIALIAS_NONE)
        _frame(ctx, (24 / 255, 18 / 255, 31 / 255))  # chìm hơn ô có app
    else:
        ctx = cairo.Context(s)  # phẳng: chấm mờ giữa ô để biết còn chỗ
        ctx.set_source_rgba(1, 1, 1, 0.10)
        ctx.arc(20, 20, 2, 0, 6.2832)
        ctx.fill()
    return s


def more_surface(n, pixel=None):
    """Ô "+N": còn N mục không vừa ngăn."""
    import cairo
    import gi

    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    pixel = pixel_theme_enabled() if pixel is None else pixel
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, OUT_PX, OUT_PX)
    ctx = cairo.Context(s)
    if pixel:
        ctx.set_antialias(cairo.ANTIALIAS_NONE)
        _frame(ctx, (44 / 255, 34 / 255, 56 / 255))
        col = (1.0, 224 / 255, 138 / 255)
    else:
        ctx.set_source_rgba(1, 1, 1, 0.08)
        ctx.rectangle(2, 2, 36, 36)
        ctx.fill()
        col = (251 / 255, 247 / 255, 253 / 255)
    ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)
    lay = PangoCairo.create_layout(ctx)
    fd = Pango.FontDescription("FiraCode Nerd Font Bold")
    fd.set_absolute_size((13 if n < 10 else 11) * Pango.SCALE)
    lay.set_font_description(fd)
    lay.set_text(f"+{n}", -1)
    _ink, log = lay.get_pixel_extents()
    x, y = (OUT_PX - log.width) / 2, (OUT_PX - log.height) / 2
    if pixel:
        ctx.set_source_rgb(*DARK)
        ctx.move_to(x + 1, y + 1)
        PangoCairo.show_layout(ctx, lay)
    ctx.set_source_rgb(*col)
    ctx.move_to(x, y)
    PangoCairo.show_layout(ctx, lay)
    return s


def write_png(surface, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    try:
        surface.write_to_png(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
