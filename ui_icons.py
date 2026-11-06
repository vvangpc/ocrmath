"""Small vector icons drawn with Qt, avoiding external image assets."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap,
    QGuiApplication, QPalette,
)

INK = "#263238"

# Icons are immutable once drawn; cache them so repeated icon() calls during
# window construction don't re-render the same pixmap.
_ICON_CACHE: dict[tuple, QIcon] = {}


def _pixmap(size: int) -> tuple[QPixmap, QPainter]:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pix, painter


# ---- app logo --------------------------------------------------------------
#
# Near-black squircle tile carrying a white integral sign. Below 32px the tile
# goes full-bleed and the stroke gets relatively heavier so the tray icon stays
# readable at 16px. web/common.js draws the same glyph, and tools/make_icon.py
# renders icon.ico from this code.

LOGO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _squircle(rect: QRectF, n: float) -> QPainterPath:
    """Superellipse |x|^n + |y|^n = 1 fitted to `rect`."""
    cx, cy = rect.center().x(), rect.center().y()
    a, b = rect.width() / 2, rect.height() / 2
    path = QPainterPath()
    steps = 160
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        pt = QPointF(cx + a * math.copysign(abs(c) ** (2 / n), c),
                     cy + b * math.copysign(abs(s) ** (2 / n), s))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    return path


def render_logo(size: int, *, opacity: float = 1.0) -> QImage:
    """Draw the app logo at `size` x `size` px."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setOpacity(opacity)
    s = float(size)
    small = size < 32

    # Tile: full-bleed at tray sizes, where every pixel counts.
    pad = 0.0 if small else s * 0.035
    n = 4.2 if small else 5.0
    rect = QRectF(pad, pad, s - 2 * pad, s - 2 * pad)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#17181a"))
    p.drawPath(_squircle(rect, n))
    # Light rim keeps the dark tile's edge readable on dark taskbars.
    rw = 1.0 if small else max(1.0, s / 128)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 52 if small else 44), rw))
    p.drawPath(_squircle(rect.adjusted(rw / 2, rw / 2, -rw / 2, -rw / 2), n))

    # The glyph lives in a 24-unit box: two curls joined by a slanted stem.
    scale = (0.92 if small else 0.78) * s / 24
    offset = (s - 24 * scale) / 2

    def pt(x: float, y: float) -> QPointF:
        return QPointF(offset + x * scale, offset + y * scale)

    glyph = QPainterPath(pt(16.6, 4.3))
    glyph.cubicTo(pt(14.7, 3.3), pt(12.9, 4.1), pt(12.5, 6.5))
    glyph.lineTo(pt(10.7, 17.5))
    glyph.cubicTo(pt(10.3, 19.9), pt(8.5, 20.7), pt(6.6, 19.7))
    width = max(1.6, s * (0.115 if small else 0.075))
    p.setPen(QPen(QColor("white"), width, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPath(glyph)
    p.end()
    return img


def app_icon(*, busy: bool = False) -> QIcon:
    """The app/tray icon, holding every LOGO_SIZES rendition so Qt picks the
    hand-tuned one for whatever pixel size the tray asks for. `busy` is the
    faded frame the tray blinks to while a recognition runs."""
    key = ("app", busy)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    result = QIcon()
    for size in LOGO_SIZES:
        result.addPixmap(QPixmap.fromImage(
            render_logo(size, opacity=0.5 if busy else 1.0)))
    _ICON_CACHE[key] = result
    return result


def icon(name: str, color: str | None = None, size: int = 24) -> QIcon:
    """Return a named line icon."""
    if color is None:
        app = QGuiApplication.instance()
        color = app.palette().color(QPalette.ColorRole.Text).name() if app else INK
    key = (name, color, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    pix, painter = _pixmap(size)
    c = QColor(color)
    pen = QPen(c, max(1.6, size * 0.085), Qt.PenStyle.SolidLine,
               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)

    if name == "snip":
        for x1, y1, x2, y2 in (
            (.18, .36, .18, .18), (.18, .18, .36, .18),
            (.64, .18, .82, .18), (.82, .18, .82, .36),
            (.82, .64, .82, .82), (.82, .82, .64, .82),
            (.36, .82, .18, .82), (.18, .82, .18, .64),
        ):
            painter.drawLine(QPointF(s * x1, s * y1), QPointF(s * x2, s * y2))
        painter.drawLine(QPointF(s * .42, s * .50), QPointF(s * .58, s * .50))
        painter.drawLine(QPointF(s * .50, s * .42), QPointF(s * .50, s * .58))
    elif name == "pdf":
        painter.drawRoundedRect(QRectF(s * .25, s * .14, s * .50, s * .72), 3, 3)
        painter.drawLine(QPointF(s * .37, s * .44), QPointF(s * .63, s * .44))
        painter.drawLine(QPointF(s * .37, s * .57), QPointF(s * .63, s * .57))
        painter.drawLine(QPointF(s * .37, s * .70), QPointF(s * .54, s * .70))
    elif name == "history":
        painter.drawEllipse(QRectF(s * .18, s * .18, s * .64, s * .64))
        painter.drawLine(QPointF(s * .50, s * .31), QPointF(s * .50, s * .53))
        painter.drawLine(QPointF(s * .50, s * .53), QPointF(s * .64, s * .61))
    elif name == "settings":
        painter.drawEllipse(QRectF(s * .36, s * .36, s * .28, s * .28))
        for x1, y1, x2, y2 in (
            (.50, .15, .50, .27), (.50, .73, .50, .85),
            (.15, .50, .27, .50), (.73, .50, .85, .50),
            (.25, .25, .33, .33), (.67, .67, .75, .75),
            (.75, .25, .67, .33), (.33, .67, .25, .75),
        ):
            painter.drawLine(QPointF(s * x1, s * y1), QPointF(s * x2, s * y2))
    elif name == "copy":
        painter.drawRoundedRect(QRectF(s * .34, s * .24, s * .42, s * .52), 3, 3)
        painter.drawRoundedRect(QRectF(s * .22, s * .36, s * .42, s * .52), 3, 3)
    elif name == "refresh":
        painter.drawArc(QRectF(s * .20, s * .20, s * .60, s * .60), 30 * 16, 270 * 16)
        painter.drawLine(QPointF(s * .72, s * .22), QPointF(s * .80, s * .41))
        painter.drawLine(QPointF(s * .72, s * .22), QPointF(s * .54, s * .26))
    elif name == "sync":
        painter.drawArc(QRectF(s * .18, s * .22, s * .60, s * .48), 35 * 16, 185 * 16)
        painter.drawArc(QRectF(s * .22, s * .30, s * .60, s * .48), 215 * 16, 185 * 16)
        painter.drawLine(QPointF(s * .25, s * .70), QPointF(s * .17, s * .54))
        painter.drawLine(QPointF(s * .25, s * .70), QPointF(s * .42, s * .68))
    elif name == "folder":
        painter.drawRoundedRect(QRectF(s * .15, s * .31, s * .70, s * .48), 3, 3)
        painter.drawLine(QPointF(s * .18, s * .34), QPointF(s * .40, s * .34))
        painter.drawLine(QPointF(s * .40, s * .34), QPointF(s * .47, s * .42))
    elif name == "play":
        painter.setBrush(c)
        path = QPainterPath()
        path.moveTo(s * .34, s * .23)
        path.lineTo(s * .76, s * .50)
        path.lineTo(s * .34, s * .77)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "close":
        painter.drawLine(QPointF(s * .30, s * .30), QPointF(s * .70, s * .70))
        painter.drawLine(QPointF(s * .70, s * .30), QPointF(s * .30, s * .70))
    elif name == "trash":
        painter.drawLine(QPointF(s * .30, s * .34), QPointF(s * .70, s * .34))
        painter.drawLine(QPointF(s * .42, s * .24), QPointF(s * .58, s * .24))
        painter.drawRoundedRect(QRectF(s * .33, s * .38, s * .34, s * .42), 3, 3)
    elif name == "open":
        painter.drawRoundedRect(QRectF(s * .22, s * .26, s * .48, s * .48), 3, 3)
        painter.drawLine(QPointF(s * .49, s * .25), QPointF(s * .78, s * .25))
        painter.drawLine(QPointF(s * .78, s * .25), QPointF(s * .78, s * .54))
        painter.drawLine(QPointF(s * .78, s * .25), QPointF(s * .45, s * .58))
    else:
        painter.drawEllipse(QRectF(s * .28, s * .28, s * .44, s * .44))

    painter.end()
    result = QIcon(pix)
    _ICON_CACHE[key] = result
    return result
