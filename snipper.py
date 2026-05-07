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

        # Grab each screen's pixmap and stitch into one big QPixmap
        canvas = QPixmap(full.size())
        canvas.fill(QColor(0, 0, 0))
        painter = QPainter(canvas)
        for s in screens:
            geom = s.geometry()
            shot = s.grabWindow(0)  # full screen
            painter.drawPixmap(geom.topLeft() - full.topLeft(), shot)
        painter.end()
        self._screenshot = canvas

        self.setGeometry(full)
        self._origin = None
        self._current = None
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    # ---- events ------------------------------------------------------------

    def paintEvent(self, _evt: QPaintEvent) -> None:
        if self._screenshot is None:
            return
        p = QPainter(self)
        p.drawPixmap(0, 0, self._screenshot)
        # Dim overlay
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        # Highlight selection rect
        if self._origin and self._current:
            sel = QRect(self._origin, self._current).normalized()
            # Re-draw original pixels inside selection to undo the dim
            p.drawPixmap(sel, self._screenshot, sel)
            pen = QPen(QColor(255, 90, 0), 2)
            p.setPen(pen)
            p.drawRect(sel)
            # Size label
            label = f"{sel.width()} x {sel.height()}"
            p.setPen(QColor(255, 255, 255))
            p.drawText(sel.x() + 4, max(0, sel.y() - 6), label)

    def mousePressEvent(self, evt: QMouseEvent) -> None:
        if evt.button() == Qt.MouseButton.LeftButton:
            self._origin = evt.pos()
            self._current = evt.pos()
            self.update()

    def mouseMoveEvent(self, evt: QMouseEvent) -> None:
        if self._origin:
            self._current = evt.pos()
            self.update()

    def mouseReleaseEvent(self, evt: QMouseEvent) -> None:
        if evt.button() != Qt.MouseButton.LeftButton or not self._origin:
            return
        self._current = evt.pos()
        sel = QRect(self._origin, self._current).normalized()
        self.hide()
        if sel.width() < MIN_REGION_SIDE or sel.height() < MIN_REGION_SIDE:
            self.cancelled.emit()
            return
        cropped = self._screenshot.copy(sel)
        self.captured.emit(_pixmap_to_png_bytes(cropped))

    def keyPressEvent(self, evt: QKeyEvent) -> None:
        if evt.key() == Qt.Key.Key_Escape:
            self.hide()
            self.cancelled.emit()


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
