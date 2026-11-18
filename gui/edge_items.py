from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPen, QPainterPath
from PyQt6.QtWidgets import QGraphicsPathItem

from .theme import Theme


class EdgeItem(QGraphicsPathItem):
    def __init__(self, edge, source_item, target_item):
        super().__init__()
        self.edge = edge
        self.source_item = source_item
        self.target_item = target_item
        self.setZValue(0)
        self.setFlags(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)
        self.restyle()
        self.update_path()

    def restyle(self):
        self.setPen(QPen(Theme.color("edge"), 2.0))

    def update_path(self):
        if self.source_item is None or self.target_item is None:
            return
        s = self.source_item.scenePos()
        t = self.target_item.scenePos()
        dx = max(30.0, abs(t.x() - s.x()) * 0.5)
        path = QPainterPath(s)
        path.cubicTo(QPointF(s.x() + dx, s.y()), QPointF(t.x() - dx, t.y()), t)
        self.setPath(path)
