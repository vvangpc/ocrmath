"""Full-screen translucent overlay for selecting a screen region.

Emits `captured(bytes)` with PNG bytes of the cropped region, or
`cancelled()` if the user pressed Esc / the selection was too small.
"""
from __future__ import annotations

from PyQt6.QtCore import (
    Qt, QPoint, QRect, QBuffer, QIODevice, QByteArray,
    pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import (
    QGuiApplication, QPainter, QColor, QPen, QPixmap, QKeyEvent,
    QMouseEvent, QPaintEvent,
)
from PyQt6.QtWidgets import QWidget

MIN_REGION_SIDE = 5  # px — anything smaller is treated as misclick
DIM_COLOR = QColor(0, 0, 0, 110)


class Snipper(QWidget):
    captured = pyqtSignal(bytes)
    cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._screenshot: QPixmap | None = None
        self._dimmed: QPixmap | None = None  # screenshot + dim, pre-rendered
        self._virtual_origin = QPoint(0, 0)

    # ---- public API --------------------------------------------------------

    @pyqtSlot()
    def start(self) -> None:
        """Take a fresh screenshot and show the overlay full-screen."""
        screens = QGuiApplication.screens()
        if not screens:
            self.cancelled.emit()
            return

        # Compute virtual desktop bounding rect (multi-monitor aware)
        full = QRect()
        for s in screens:
            full = full.united(s.geometry())
        self._virtual_origin = full.topLeft()

        # Grab each screen's pixmap and stitch into one big QPixmap.
        # grabWindow() returns physical pixels (devicePixelRatio set), so the
        # canvas gets the max DPR too — otherwise the capture is downscaled to
        # logical resolution on scaled displays, hurting OCR accuracy.
        dpr = max(s.devicePixelRatio() for s in screens)
        canvas = QPixmap(int(full.width() * dpr), int(full.height() * dpr))
        canvas.setDevicePixelRatio(dpr)
        canvas.fill(QColor(0, 0, 0))
        painter = QPainter(canvas)
        for s in screens:
            geom = s.geometry()
            shot = s.grabWindow(0)  # full screen, physical pixels
            painter.drawPixmap(geom.topLeft() - full.topLeft(), shot)
        painter.end()
        self._screenshot = canvas
        # Dim once here rather than blending a full-desktop fill on every
        # mouse move.
        dimmed = QPixmap(canvas)
        painter = QPainter(dimmed)
        painter.fillRect(QRect(QPoint(0, 0), full.size()), DIM_COLOR)
        painter.end()
        self._dimmed = dimmed

        self._origin = None
        self._current = None
        # Plain show() on the virtual-desktop rect: showFullScreen() would
        # snap the overlay to a single monitor, leaving the others
        # unselectable on multi-screen setups.
        self.setGeometry(full)
        self.show()
        self.raise_()
        self.activateWindow()

    # ---- events ------------------------------------------------------------

    def paintEvent(self, evt: QPaintEvent) -> None:
        if self._screenshot is None or self._dimmed is None:
            return
        p = QPainter(self)
        # Only the damaged region: mouse moves update() just the selection's
        # old + new bounds. Source rects are in device pixels (DPR-scaled).
        area = evt.rect()
        p.drawPixmap(area, self._dimmed, _to_device_rect(area, self._dimmed))
        sel = self._selection()
        if sel is None:
            return
        # Re-draw original pixels inside the selection to undo the dim.
        inner = sel.intersected(area)
        if not inner.isEmpty():
            p.drawPixmap(inner, self._screenshot,
                         _to_device_rect(inner, self._screenshot))
        p.setPen(QPen(QColor(255, 90, 0), 2))
        p.drawRect(sel)
        # Size label
        label = f"{sel.width()} x {sel.height()}"
        p.setPen(QColor(255, 255, 255))
        p.drawText(sel.x() + 4, max(0, sel.y() - 6), label)

    def _selection(self) -> QRect | None:
        if self._origin is None or self._current is None:
            return None
        return QRect(self._origin, self._current).normalized()

    def _selection_bounds(self) -> QRect:
        """Everything paintEvent draws for the selection: the rect, its 2px
        pen, and the size label above it."""
        sel = self._selection()
        if sel is None:
            return QRect()
        bounds = sel.adjusted(-3, -3, 3, 3)
        label = QRect(sel.x(), max(0, sel.y() - 6) - 24, 180, 30)
        return bounds.united(label)

    def _move_selection_end(self, pos: QPoint) -> None:
        old = self._selection_bounds()
        self._current = pos
        self.update(old.united(self._selection_bounds()))

    def _finish(self) -> None:
        """Hide and drop the full-desktop pixmaps (tens of MB on 4K)."""
        self.hide()
        self._screenshot = None
        self._dimmed = None
        self._origin = None
        self._current = None

    def mousePressEvent(self, evt: QMouseEvent) -> None:
        if evt.button() == Qt.MouseButton.LeftButton:
            old = self._selection_bounds()
            self._origin = evt.pos()
            self._current = evt.pos()
            self.update(old.united(self._selection_bounds()))

    def mouseMoveEvent(self, evt: QMouseEvent) -> None:
        if self._origin is not None:
            self._move_selection_end(evt.pos())

    def mouseReleaseEvent(self, evt: QMouseEvent) -> None:
        if evt.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        if self._screenshot is None:
            return
        self._current = evt.pos()
        sel = self._selection()
        cropped = None
        if sel.width() >= MIN_REGION_SIDE and sel.height() >= MIN_REGION_SIDE:
            # copy() takes device-pixel coordinates — crop at full resolution.
            cropped = self._screenshot.copy(
                _to_device_rect(sel, self._screenshot))
        self._finish()
        if cropped is None:
            self.cancelled.emit()
            return
        self.captured.emit(_pixmap_to_png_bytes(cropped))

    def keyPressEvent(self, evt: QKeyEvent) -> None:
        if evt.key() == Qt.Key.Key_Escape:
            self._finish()
            self.cancelled.emit()


def _to_device_rect(logical: QRect, pix: QPixmap) -> QRect:
    """Map a logical-coordinate rect onto `pix`'s device-pixel grid."""
    dpr = pix.devicePixelRatio()
    return QRect(
        round(logical.x() * dpr),
        round(logical.y() * dpr),
        round(logical.width() * dpr),
        round(logical.height() * dpr),
    )


def _pixmap_to_png_bytes(pix: QPixmap) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pix.save(buf, "PNG")
    return bytes(buf.data())


# Standalone smoke test: python snipper.py -> press mouse -> writes test.png
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    sn = Snipper()

    def on_cap(data: bytes) -> None:
        from pathlib import Path
        Path("test_capture.png").write_bytes(data)
        print(f"saved test_capture.png ({len(data)} bytes)")
        app.quit()

    def on_cancel() -> None:
        print("cancelled")
        app.quit()

    sn.captured.connect(on_cap)
    sn.cancelled.connect(on_cancel)
    sn.start()
    sys.exit(app.exec())
