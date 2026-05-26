"""Small vector icons drawn with Qt, avoiding external image assets."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QConicalGradient, QIcon, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap,
)

PRIMARY = "#ff6a00"
INK = "#263238"


def _pixmap(size: int) -> tuple[QPixmap, QPainter]:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pix, painter


def app_icon(size: int = 64, *, busy: bool = False) -> QIcon:
    """Return the app/tray icon."""
    pix, painter = _pixmap(size)
    pad = max(2, int(size * 0.05))
    rect = QRectF(pad, pad, size - pad * 2, size - pad * 2)

    bg = QLinearGradient(rect.topLeft(), rect.bottomRight())
    bg.setColorAt(0, QColor("#ff8a2a"))
    bg.setColorAt(1, QColor("#f04438"))
    if busy:
        painter.setOpacity(0.55)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(bg)
    painter.drawRoundedRect(rect, size * 0.22, size * 0.22)

    shine = QConicalGradient(QPointF(size * 0.52, size * 0.48), -35)
    shine.setColorAt(0.0, QColor(255, 255, 255, 76))
    shine.setColorAt(0.35, QColor(255, 255, 255, 0))
    shine.setColorAt(1.0, QColor(255, 255, 255, 76))
    painter.setBrush(shine)
    painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), size * 0.18, size * 0.18)

    pen = QPen(QColor("white"), max(3, size * 0.08), Qt.PenStyle.SolidLine,
               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    path = QPainterPath()
    path.moveTo(size * 0.66, size * 0.25)
    path.lineTo(size * 0.35, size * 0.25)
    path.lineTo(size * 0.53, size * 0.50)
    path.lineTo(size * 0.35, size * 0.75)
    path.lineTo(size * 0.68, size * 0.75)
    painter.drawPath(path)
    painter.end()
    return QIcon(pix)


def icon(name: str, color: str = INK, size: int = 24) -> QIcon:
    """Return a named line icon."""
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
    return QIcon(pix)
