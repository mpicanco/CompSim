from __future__ import annotations

from PyQt6.QtCore import Qt, QMimeData, QRect, pyqtSignal
from PyQt6.QtGui import QDrag, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget, QScrollArea

from .theme import Theme
from .node_items import draw_glyph
from .canvas import BLOCK_MIME
from models import BLOCK_REGISTRY

DRAG_THRESHOLD = 8


class BlockButton(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, block_type, cls, parent=None):
        super().__init__(parent)
        self.block_type = block_type
        self.cls = cls
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag onto the canvas, or click to add")
        self._press_pos = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(Theme.color("node_bg")))
        painter.setPen(QPen(Theme.color("node_border"), 1))
        painter.drawRoundedRect(QRect(0, 0, self.width() - 1, self.height() - 1), 4, 4)
        draw_glyph(painter, QRect(6, (self.height() - 16) // 2, 16, 16), self.block_type, Theme.color("text"))
        painter.setPen(QPen(Theme.color("text"), 1))
        painter.drawText(QRect(28, 0, self.width() - 32, self.height()), Qt.AlignmentFlag.AlignVCenter, self.cls.block_type)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.position().toPoint() - self._press_pos).manhattanLength() < DRAG_THRESHOLD:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(BLOCK_MIME, self.block_type.encode())
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def mouseReleaseEvent(self, event):
        if self._press_pos is not None and (event.position().toPoint() - self._press_pos).manhattanLength() < DRAG_THRESHOLD:
            self.clicked.emit(self.block_type)
        self._press_pos = None
        super().mouseReleaseEvent(event)


class Sidebar(QWidget):
    add_block = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Equipment Palette")
        f = title.font()
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 4, 0)
        inner_layout.setSpacing(4)

        by_category = {}
        for block_type, cls in BLOCK_REGISTRY.items():
            by_category.setdefault(cls.category, []).append((block_type, cls))

        for category in ("Sources", "Equipment"):
            items = by_category.pop(category, [])
            if not items:
                continue
            cat_label = QLabel(category)
            cat_label.setStyleSheet("color: #9aa4b5;")
            inner_layout.addWidget(cat_label)
            for block_type, cls in items:
                btn = BlockButton(block_type, cls)
                btn.clicked.connect(self.add_block)
                inner_layout.addWidget(btn)
        for category, items in by_category.items():
            inner_layout.addWidget(QLabel(category))
            for block_type, cls in items:
                btn = BlockButton(block_type, cls)
                btn.clicked.connect(self.add_block)
                inner_layout.addWidget(btn)

        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll)
