from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt, QLineF, pyqtSignal
from PyQt6.QtGui import QPen, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QGraphicsPathItem,
)

from .node_items import NodeItem, PortItem
from .edge_items import EdgeItem
from .theme import Theme
from core.ports import PortDirection
from models import create_block

BLOCK_MIME = "application/x-comp-sim-block"


class CanvasScene(QGraphicsScene):
    # emitted whenever blocks or streams are added/removed
    blocks_changed = pyqtSignal()
    # emitted with the block whose configuration panel should open
    node_config_requested = pyqtSignal(object)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._node_items = {}
        self._edge_items = {}
        self._temp_line = None
        self._drag_port = None
        self.setSceneRect(-20000, -20000, 40000, 40000)

    # -- blocks -------------------------------------------------------------
    def create_block(self, block_type, scene_pos):
        block = create_block(block_type)
        block.name = self._unique_name(block_type)
        self.controller.add_block(block)
        item = NodeItem(block)
        self.addItem(item)
        item.setPos(scene_pos - QPointF(item.boundingRect().width() / 2, item.boundingRect().height() / 2))
        self._node_items[block.instance_id] = item
        self.blocks_changed.emit()
        return item

    def _unique_name(self, block_type):
        taken = {n.name for n in self.controller.graph.nodes}
        i = 1
        while f"{block_type}{i}" in taken:
            i += 1
        return f"{block_type}{i}"

    def remove_node(self, instance_id):
        self.controller.remove_block(instance_id)
        item = self._node_items.pop(instance_id, None)
        if item is None:
            return
        for eid in list(self._edge_items):
            if self._edge_items[eid].edge.source.owner.instance_id == instance_id or \
               self._edge_items[eid].edge.target.owner.instance_id == instance_id:
                self._remove_edge_item(eid)
        self.removeItem(item)
        self.blocks_changed.emit()

    # -- connections --------------------------------------------------------
    def begin_connection(self, port_item):
        if port_item.port.direction != PortDirection.OUTPUT:
            return
        self._drag_port = port_item
        self._temp_line = QGraphicsPathItem()
        self._temp_line.setZValue(0)
        self._temp_line.setPen(QPen(Theme.color("edge_active"), 2.0, Qt.PenStyle.DashLine))
        self.addItem(self._temp_line)
        self._update_temp_line(port_item.scenePos())

    def _update_temp_line(self, end):
        if self._temp_line is None or self._drag_port is None:
            return
        s = self._drag_port.scenePos()
        dx = max(30.0, abs(end.x() - s.x()) * 0.5)
        path = QPainterPath(s)
        path.cubicTo(QPointF(s.x() + dx, s.y()), QPointF(end.x() - dx, end.y()), end)
        self._temp_line.setPath(path)

    def mouseMoveEvent(self, event):
        if self._temp_line is not None:
            self._update_temp_line(event.scenePos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._temp_line is not None and self._drag_port is not None:
            target = self._port_at(event.scenePos())
            if target is not None:
                self.create_edge(self._drag_port, target)
            self._finish_connection()
        super().mouseReleaseEvent(event)

    def _finish_connection(self):
        if self._temp_line is not None:
            self.removeItem(self._temp_line)
        self._temp_line = None
        self._drag_port = None

    def _port_at(self, pos):
        for item in self.items(pos):
            if isinstance(item, PortItem):
                return item
        return None

    def create_edge(self, source_item, target_item):
        src = source_item.port
        tgt = target_item.port
        if src is tgt or src.owner is tgt.owner:
            return None
        if src.direction != PortDirection.OUTPUT or tgt.direction != PortDirection.INPUT:
            return None
        if src.port_type != tgt.port_type:
            return None

        # a port holds a single stream: replace any existing one, removing it
        # from the simulation graph as well as from the canvas
        for port in (tgt, src):
            if not port.is_connected:
                continue
            if port is tgt:
                old = self.controller.graph.find_edge(tgt.connection, tgt)
            else:
                old = self.controller.graph.find_edge(src, src.connection)
            if old is not None:
                self.controller.remove_edge(old.id)
                self._remove_edge_item(old.id)
            else:
                port.disconnect()

        edge = self.controller.add_edge(src, tgt)
        item = EdgeItem(edge, source_item, target_item)
        self.addItem(item)
        self._edge_items[edge.id] = item
        source_item.add_edge_item(item)
        target_item.add_edge_item(item)
        item.update_path()
        self.blocks_changed.emit()
        return item

    def _remove_edge_item(self, edge_id):
        item = self._edge_items.pop(edge_id, None)
        if item is None:
            return
        item.source_item.remove_edge_item(item)
        item.target_item.remove_edge_item(item)
        self.removeItem(item)

    def remove_selected(self):
        for item in list(self.selectedItems()):
            if isinstance(item, EdgeItem):
                if item.edge.id in self._edge_items:
                    self.controller.remove_edge(item.edge.id)
                    self._remove_edge_item(item.edge.id)
                    self.blocks_changed.emit()
            elif isinstance(item, NodeItem):
                self.remove_node(item.block.instance_id)

    def restyle(self):
        for item in self._node_items.values():
            item.restyle()
        for item in self._edge_items.values():
            item.restyle()

    def clear_flowsheet(self):
        """Remove every block and stream from the canvas and the graph."""
        for instance_id in list(self._node_items):
            self.remove_node(instance_id)

    def node_item(self, instance_id):
        return self._node_items.get(instance_id)

    def refresh_values(self):
        """Repaint nodes whose displayed value changes every solver step."""
        for item in self._node_items.values():
            item.update()


class CanvasView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self._zoom = 1.0

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, Theme.color("canvas_bg"))
        minor = 20
        major = 100
        left = int(rect.left()) - (int(rect.left()) % minor)
        top = int(rect.top()) - (int(rect.top()) % minor)

        lines = []
        x = left
        while x < rect.right():
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
            x += minor
        y = top
        while y < rect.bottom():
            lines.append(QLineF(rect.left(), y, rect.right(), y))
            y += minor

        painter.setPen(QPen(Theme.color("grid"), 1))
        painter.drawLines(lines)

        major_lines = []
        mx = int(rect.left()) - (int(rect.left()) % major)
        while mx < rect.right():
            major_lines.append(QLineF(mx, rect.top(), mx, rect.bottom()))
            mx += major
        my = int(rect.top()) - (int(rect.top()) % major)
        while my < rect.bottom():
            major_lines.append(QLineF(rect.left(), my, rect.right(), my))
            my += major
        painter.setPen(QPen(Theme.color("grid_major"), 1))
        painter.drawLines(major_lines)

    # -- drag-drop of blocks from the sidebar -------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(BLOCK_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(BLOCK_MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(BLOCK_MIME):
            block_type = bytes(event.mimeData().data(BLOCK_MIME)).decode()
            pos = self.mapToScene(event.position().toPoint())
            self.scene().create_block(block_type, pos)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom *= factor
        self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event):
        # Normal delivery: the NodeItem under the cursor handles it. Fallback
        # for clicks that land on the node's area but no child item took them.
        super().mouseDoubleClickEvent(event)
        if event.isAccepted():
            return
        pos = self.mapToScene(event.position().toPoint())
        for item in self.scene().items(pos):
            if isinstance(item, NodeItem):
                item.request_config()
                event.accept()
                return
