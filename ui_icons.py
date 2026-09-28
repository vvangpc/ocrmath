"""Small vector icons drawn with Qt, avoiding external image assets."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient,
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
# Dark squircle tile carrying an orange radical over a white x (√x). Detail is
# size-adaptive: below 32px the gloss, glow and shadow go, strokes get
# heavier and the vinculum is snapped to the pixel grid so the tray icon stays
# crisp at 16px. tools/make_icon.py renders icon.ico from this same code.

LOGO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

# Unit-space geometry: radical (tick, valley, apex, vinculum end) and the
# two strokes of the x, with a slight italic lean.
_RADICAL = ((0.185, 0.555), (0.28, 0.505), (0.405, 0.755), (0.545, 0.265),
            (0.815, 0.265))
_X_STROKES = (((0.612, 0.43), (0.752, 0.635)),
              ((0.768, 0.43), (0.596, 0.635)))


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


def _stroke(painter: QPainter, pts, width: float, brush: QBrush) -> None:
    painter.setPen(QPen(brush, width, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(*pts[0]))
    for pt in pts[1:]:
        path.lineTo(QPointF(*pt))
    painter.drawPath(path)


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
    shape = _squircle(rect, n)
    bg = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    bg.setColorAt(0, QColor("#3b4354"))
    bg.setColorAt(1, QColor("#161a23"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawPath(shape)
    if not small:
        p.save()
        p.setClipPath(shape)
        glow = QRadialGradient(QPointF(0.5 * s, 0.56 * s), 0.46 * s)
        glow.setColorAt(0, QColor(255, 122, 26, 46))
        glow.setColorAt(1, QColor(255, 122, 26, 0))
        p.setBrush(glow)
        p.drawRect(rect)
        sheen = QLinearGradient(0, rect.top(), 0, rect.top() + rect.height() / 2)
        sheen.setColorAt(0, QColor(255, 255, 255, 34))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(sheen)
        p.drawRect(rect)
        p.restore()
    # Light rim keeps the dark tile's edge readable on dark taskbars.
    rw = 1.0 if small else max(1.0, s / 128)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 52 if small else 44), rw))
    p.drawPath(_squircle(rect.adjusted(rw / 2, rw / 2, -rw / 2, -rw / 2), n))

    orange = QLinearGradient(0.18 * s, 0, 0.82 * s, 0)
    orange.setColorAt(0, QColor("#ffc766"))
    orange.setColorAt(1, QColor("#ff6a00"))
    white = QBrush(QColor("white"))

    if small:
        w = 2.0 if size <= 20 else 2.5
        vin_y = round(s * 0.27 - w / 2) + w / 2  # top edge on a pixel row
        radical = [(0.2 * s, 0.575 * s), (0.28 * s, 0.53 * s),
                   (0.4 * s, 0.8 * s), (0.53 * s, vin_y), (0.86 * s, vin_y)]
        _stroke(p, radical, w, QBrush(orange))
        xw = max(1.5, w * 0.8)
        top, bottom = vin_y + w / 2 + xw * 0.9, 0.8 * s
        left, right = 0.6 * s, 0.83 * s
        _stroke(p, [(left, top), (right, bottom)], xw, white)
        _stroke(p, [(right, top), (left, bottom)], xw, white)
    else:
        def scaled(pts):
            return [(x * s, y * s) for x, y in pts]
        # A touch heavier at mid sizes so strokes keep >= 2.5px at 32.
        w = 0.072 * s + (0.9 if s <= 48 else 0.0)
        xw = 0.066 * s + (0.8 if s <= 48 else 0.0)
        p.save()
        p.translate(0, 0.016 * s)
        _stroke(p, scaled(_RADICAL), w, QBrush(QColor(0, 0, 0, 80)))
        p.restore()
        _stroke(p, scaled(_RADICAL), w, QBrush(orange))
        for stroke in _X_STROKES:
            _stroke(p, scaled(stroke), xw, white)
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


def icon(name: str, color: str = INK, size: int = 24) -> QIcon:
    """Return a named line icon."""
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
