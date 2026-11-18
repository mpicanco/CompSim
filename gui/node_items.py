from __future__ import annotations

import math

from PyQt6.QtCore import QRectF, QPointF, Qt
from PyQt6.QtGui import QColor, QPen, QBrush, QPainterPath, QFont, QPainter, QLinearGradient
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QMenu

from .theme import Theme
from core.ports import PortType

PORT_RADIUS = 5
LABEL_H = 20

_PORT_COLOR = {
    PortType.MATERIAL: "port_material",
    PortType.SIGNAL: "port_signal",
    PortType.ENERGY: "port_signal",
    PortType.POWER: "port_power",
}


def port_color(port_type):
    return Theme.color(_PORT_COLOR[port_type])


def _arrow_head(painter, tip, back, size):
    dx = tip.x() - back.x()
    dy = tip.y() - back.y()
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    p1 = QPointF(tip.x() - ux * size + nx * size * 0.5, tip.y() - uy * size + ny * size * 0.5)
    p2 = QPointF(tip.x() - ux * size - nx * size * 0.5, tip.y() - uy * size - ny * size * 0.5)
    painter.drawLine(tip, p1)
    painter.drawLine(tip, p2)


def _layout(block):
    bt = block.block_type
    if bt == "Vessel":
        W, H = 180, 200
        anchors = {
            "in": QPointF(0, 110),
            "vap_out": QPointF(90, 20),
            "liq_out": QPointF(90, 175),
            "level": QPointF(180, 110),
        }
    elif bt == "Valve":
        W, H = 170, 150
        anchors = {"in": QPointF(0, 78), "out": QPointF(170, 78), "opening": QPointF(85, 8)}
    elif bt == "CheckValve":
        W, H = 130, 100
        anchors = {"in": QPointF(0, 40), "out": QPointF(130, 40)}
    elif bt == "Mixer":
        W, H = 160, 110
        anchors = {"in1": QPointF(0, 30), "in2": QPointF(0, 62), "out": QPointF(160, 45)}
    elif bt == "Divider":
        W, H = 160, 110
        anchors = {"in": QPointF(0, 45), "out1": QPointF(160, 28), "out2": QPointF(160, 62)}
    elif bt == "Compressor":
        W, H = 160, 120
        anchors = {"in": QPointF(0, 52), "out": QPointF(160, 52), "speed": QPointF(80, 8)}
    elif bt == "StreamIn":
        W, H = 150, 90
        anchors = {"out": QPointF(150, 35)}
    elif bt == "StreamOut":
        W, H = 150, 90
        anchors = {"in": QPointF(0, 35)}
    elif bt == "AnalogSource":
        W, H = 120, 72
        anchors = {"out": QPointF(120, 30)}
    elif bt == "AnalogSink":
        W, H = 120, 72
        anchors = {"in": QPointF(0, 30)}
    else:
        W, H = 140, 90
        anchors = {}

    i_idx = 0
    for name in block.inputs:
        if name not in anchors:
            anchors[name] = QPointF(0, 30 + i_idx * 24)
            i_idx += 1
    o_idx = 0
    for name in block.outputs:
        if name not in anchors:
            anchors[name] = QPointF(W, 30 + o_idx * 24)
            o_idx += 1
    return W, H, anchors


# -- equipment symbols (P&ID style, ISO 10628 / ISA-5.1 inspired) ------------
def _pens(glyph=False):
    stroke = Theme.color("equip_stroke")
    body = QPen(stroke, 1.4 if glyph else 1.8)
    pipe = QPen(stroke, 1.2 if glyph else 1.5)
    sig = QPen(Theme.color("port_signal"), 1.0 if glyph else 1.2)
    sig.setDashPattern([3, 3])
    for p in (body, pipe, sig):
        p.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if glyph:
            p.setCosmetic(True)
    return body, pipe, sig


def _filled_arrow(painter, tip, back, size, color):
    dx, dy = tip.x() - back.x(), tip.y() - back.y()
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    path = QPainterPath(tip)
    path.lineTo(tip.x() - ux * size + nx * size * 0.45, tip.y() - uy * size + ny * size * 0.45)
    path.lineTo(tip.x() - ux * size - nx * size * 0.45, tip.y() - uy * size - ny * size * 0.45)
    path.closeSubpath()
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawPath(path)
    painter.restore()


def _poly(*pts):
    path = QPainterPath(QPointF(*pts[0]))
    for p in pts[1:]:
        path.lineTo(QPointF(*p))
    path.closeSubpath()
    return path


def _body_gradient(rect):
    g = QLinearGradient(rect.left(), 0, rect.right(), 0)
    base = Theme.color("equip_fill")
    shade = Theme.color("equip_shade")
    g.setColorAt(0.0, shade)
    g.setColorAt(0.45, base)
    g.setColorAt(1.0, shade)
    return QBrush(g)


def _instrument_bubble(painter, center, r, tag, glyph=False):
    painter.save()
    painter.setPen(QPen(Theme.color("equip_stroke"), 1.2))
    painter.setBrush(QBrush(Theme.color("node_bg")))
    painter.drawEllipse(center, r, r)
    if not glyph:
        f = QFont()
        f.setPixelSize(int(r * 0.9))
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r),
                         Qt.AlignmentFlag.AlignCenter, tag)
    painter.restore()


def _sym_vessel(painter, block, glyph):
    body, pipe, sig = _pens(glyph=glyph)
    L, R, T, B = 50.0, 130.0, 38.0, 158.0
    head = 20.0  # 2:1 elliptical heads
    path = QPainterPath(QPointF(L, T + head))
    path.arcTo(QRectF(L, T, R - L, 2 * head), 180, -180)
    path.lineTo(R, B - head)
    path.arcTo(QRectF(L, B - 2 * head, R - L, 2 * head), 0, -180)
    path.closeSubpath()

    if not glyph:
        # nozzles / process lines
        painter.setPen(pipe)
        painter.drawLine(QPointF(0, 110), QPointF(L, 110))
        _filled_arrow(painter, QPointF(L, 110), QPointF(0, 110), 8, Theme.color("equip_stroke"))
        painter.drawLine(QPointF(90, 20), QPointF(90, T))
        painter.drawLine(QPointF(90, B), QPointF(90, 175))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_body_gradient(QRectF(L, T, R - L, B - T)))
    painter.drawPath(path)

    level = 0.45 if glyph else max(0.0, min(1.0, float(block.states.get("level", 0.0) or 0.0)))
    if level > 0.005:
        h = level * (B - T)
        liq = QColor(Theme.color("liquid"))
        liq.setAlpha(170 if Theme.dark else 200)
        painter.save()
        painter.setClipPath(path)
        painter.setBrush(QBrush(liq))
        painter.drawRect(QRectF(L, B - h, R - L, h))
        surf = QPen(Theme.color("liquid").lighter(140), 1.2)
        surf.setCosmetic(glyph)
        painter.setPen(surf)
        painter.drawLine(QPointF(L, B - h), QPointF(R, B - h))
        painter.restore()

    # tangent (seam) lines
    seam = QPen(Theme.color("equip_stroke"), 0.8, Qt.PenStyle.DashLine)
    seam.setCosmetic(glyph)
    painter.setPen(seam)
    painter.drawLine(QPointF(L, T + head), QPointF(R, T + head))
    painter.drawLine(QPointF(L, B - head), QPointF(R, B - head))

    painter.setPen(body)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)

    if not glyph:
        # inlet diverter + demister pad
        painter.setPen(pipe)
        painter.drawLine(QPointF(L + 10, 100), QPointF(L + 10, 120))
        mesh = QPen(Theme.color("equip_stroke"), 0.8)
        painter.setPen(mesh)
        y0, y1 = T + head + 6, T + head + 16
        painter.drawRect(QRectF(L + 8, y0, R - L - 16, y1 - y0))
        x = L + 8
        while x < R - 10:
            painter.drawLine(QPointF(x, y1), QPointF(x + 8, y0))
            x += 8
        # level transmitter
        painter.setPen(sig)
        painter.drawLine(QPointF(R, 110), QPointF(180, 110))
        _instrument_bubble(painter, QPointF(155, 128), 10, "LT")
        painter.setPen(sig)
        painter.drawLine(QPointF(155, 110), QPointF(155, 118))


def _bowtie(cx, cy, hw, hh):
    left = _poly((cx - hw, cy - hh), (cx - hw, cy + hh), (cx, cy))
    right = _poly((cx + hw, cy - hh), (cx + hw, cy + hh), (cx, cy))
    return left, right


def _sym_valve(painter, block, glyph):
    body, pipe, sig = _pens(glyph=glyph)
    cx, cy = 85.0, 78.0
    hw, hh = 24.0, 15.0
    if not glyph:
        painter.setPen(pipe)
        painter.drawLine(QPointF(0, cy), QPointF(cx - hw, cy))
        painter.drawLine(QPointF(cx + hw, cy), QPointF(170, cy))
    left, right = _bowtie(cx, cy, hw, hh)
    painter.setPen(body)
    painter.setBrush(QBrush(Theme.color("equip_fill")))
    painter.drawPath(left)
    painter.drawPath(right)
    # stem + diaphragm actuator
    dome_top, dome_base = 34.0, 52.0
    painter.drawLine(QPointF(cx, cy), QPointF(cx, dome_base))
    dome = QPainterPath(QPointF(cx - 20, dome_base))
    dome.arcTo(QRectF(cx - 20, dome_top, 40, 2 * (dome_base - dome_top)), 180, -180)
    dome.closeSubpath()
    painter.setBrush(_body_gradient(QRectF(cx - 20, dome_top, 40, 20)))
    painter.drawPath(dome)
    if not glyph:
        painter.setPen(sig)
        painter.drawLine(QPointF(cx, 8), QPointF(cx, dome_top))
        # opening indicator bar under the body
        try:
            op = float(block.inputs["opening"].value)
        except Exception:
            op = None
        if op is not None and 0.0 <= op <= 1.0:
            bar = QRectF(cx - 22, cy + hh + 8, 44, 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(Theme.color("equip_shade")))
            painter.drawRoundedRect(bar, 2, 2)
            painter.setBrush(QBrush(Theme.color("port_signal")))
            painter.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * op, bar.height()), 2, 2)


def _sym_check_valve(painter, block, glyph):
    body, pipe, sig = _pens(glyph=glyph)
    cx, cy = 65.0, 40.0
    hw, hh = 22.0, 14.0
    if not glyph:
        painter.setPen(pipe)
        painter.drawLine(QPointF(0, cy), QPointF(cx - hw, cy))
        painter.drawLine(QPointF(cx + hw, cy), QPointF(130, cy))
    left, right = _bowtie(cx, cy, hw, hh)
    painter.setPen(body)
    painter.setBrush(QBrush(Theme.color("equip_fill")))
    painter.drawPath(left)
    painter.setBrush(QBrush(Theme.color("equip_stroke")))  # filled = blocked direction
    painter.drawPath(right)
    painter.drawLine(QPointF(cx, cy - hh - 2), QPointF(cx, cy + hh + 2))
    if not glyph:
        # flow-direction arrow
        painter.setPen(pipe)
        ay = cy - hh - 10
        painter.drawLine(QPointF(cx - 14, ay), QPointF(cx + 10, ay))
        _filled_arrow(painter, QPointF(cx + 16, ay), QPointF(cx - 14, ay), 7, Theme.color("equip_stroke"))


def _sym_mixer(painter, block, glyph):
    body, pipe, sig = _pens(glyph=glyph)
    tri = _poly((60, 14), (60, 76), (110, 45))
    if not glyph:
        painter.setPen(pipe)
        painter.drawLine(QPointF(0, 30), QPointF(60, 30))
        painter.drawLine(QPointF(0, 62), QPointF(60, 62))
        painter.drawLine(QPointF(110, 45), QPointF(160, 45))
    painter.setPen(body)
    painter.setBrush(_body_gradient(QRectF(60, 14, 50, 62)))
    painter.drawPath(tri)
    # converging streams inside
    inner = QPen(Theme.color("equip_stroke"), 1.0)
    inner.setCosmetic(glyph)
    painter.setPen(inner)
    painter.drawLine(QPointF(64, 30), QPointF(88, 45))
    painter.drawLine(QPointF(64, 60), QPointF(88, 45))
    painter.drawLine(QPointF(88, 45), QPointF(100, 45))


def _sym_divider(painter, block, glyph):
    body, pipe, sig = _pens(glyph=glyph)
    tri = _poly((100, 14), (100, 76), (50, 45))
    if not glyph:
        painter.setPen(pipe)
        painter.drawLine(QPointF(0, 45), QPointF(50, 45))
        painter.drawLine(QPointF(100, 28), QPointF(160, 28))
        painter.drawLine(QPointF(100, 62), QPointF(160, 62))
    painter.setPen(body)
    painter.setBrush(_body_gradient(QRectF(50, 14, 50, 62)))
    painter.drawPath(tri)
    inner = QPen(Theme.color("equip_stroke"), 1.0)
    inner.setCosmetic(glyph)
    painter.setPen(inner)
    painter.drawLine(QPointF(60, 45), QPointF(72, 45))
    painter.drawLine(QPointF(72, 45), QPointF(96, 30))
    painter.drawLine(QPointF(72, 45), QPointF(96, 60))


def _sym_compressor(painter, block, glyph):
    body, pipe, sig = _pens(glyph=glyph)
    cx, cy, r = 80.0, 52.0, 28.0
    if not glyph:
        painter.setPen(pipe)
        painter.drawLine(QPointF(0, cy), QPointF(cx - r, cy))
        painter.drawLine(QPointF(cx + r, cy), QPointF(160, cy))
    painter.setPen(body)
    painter.setBrush(_body_gradient(QRectF(cx - r, cy - r, 2 * r, 2 * r)))
    painter.drawEllipse(QPointF(cx, cy), r, r)
    # ISO 10628 compressor: lines converging from suction (wide) to discharge (narrow)
    def on(a):
        return QPointF(cx + r * math.cos(math.radians(a)), cy - r * math.sin(math.radians(a)))
    painter.drawLine(on(118), on(28))
    painter.drawLine(on(242), on(332))
    if not glyph:
        # drive shaft to speed controller
        painter.setPen(sig)
        painter.drawLine(QPointF(cx, 8), QPointF(cx, cy - r))


def _sym_stream(painter, block, glyph, inlet):
    body, pipe, sig = _pens(glyph=glyph)
    cy = 35.0
    if inlet:
        # feed: flat-backed tag pointing right
        tag = _poly((36, cy - 13), (88, cy - 13), (102, cy), (88, cy + 13), (36, cy + 13))
        fill = Theme.color("feed")
        if not glyph:
            painter.setPen(pipe)
            painter.drawLine(QPointF(102, cy), QPointF(144, cy))
            _filled_arrow(painter, QPointF(150, cy), QPointF(102, cy), 9, Theme.color("equip_stroke"))
    else:
        # product: chevron tag
        tag = _poly((48, cy - 13), (100, cy - 13), (114, cy), (100, cy + 13), (48, cy + 13), (60, cy))
        fill = Theme.color("product")
        if not glyph:
            painter.setPen(pipe)
            painter.drawLine(QPointF(0, cy), QPointF(48, cy))
            _filled_arrow(painter, QPointF(54, cy), QPointF(0, cy), 9, Theme.color("equip_stroke"))
    painter.setPen(body)
    painter.setBrush(QBrush(fill))
    painter.drawPath(tag)


def _sym_analog(painter, block, glyph, is_source):
    body, pipe, sig = _pens(glyph=glyph)
    box = QRectF(12, 12, 96, 36)
    if is_source:
        val = block.config.get("value", 0.0) if hasattr(block, "config") else 0.0
        painter.setPen(pipe)
        painter.drawLine(QPointF(108, 30), QPointF(118, 30))
        _filled_arrow(painter, QPointF(120, 30), QPointF(108, 30), 7, Theme.color("equip_stroke"))
    else:
        val = block.states.get("value") if hasattr(block, "states") else None
        painter.setPen(pipe)
        painter.drawLine(QPointF(2, 30), QPointF(12, 30))
        _filled_arrow(painter, QPointF(12, 30), QPointF(2, 30), 7, Theme.color("equip_stroke"))
    painter.setPen(body)
    painter.setBrush(_body_gradient(box))
    painter.drawRoundedRect(box, 6, 6)
    if not glyph:
        text = "----" if val is None else f"{val:.3g}"
        painter.setPen(QPen(Theme.color("text")))
        f = QFont()
        f.setBold(True)
        f.setPixelSize(13)
        painter.setFont(f)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)


_SYMBOLS = {
    "Vessel": _sym_vessel,
    "Valve": _sym_valve,
    "CheckValve": _sym_check_valve,
    "Mixer": _sym_mixer,
    "Divider": _sym_divider,
    "Compressor": _sym_compressor,
    "StreamIn": lambda p, b, g: _sym_stream(p, b, g, inlet=True),
    "StreamOut": lambda p, b, g: _sym_stream(p, b, g, inlet=False),
    "AnalogSource": lambda p, b, g: _sym_analog(p, b, g, True),
    "AnalogSink": lambda p, b, g: _sym_analog(p, b, g, False),
}

# region (node coordinates) that the sidebar glyph is cropped to
_GLYPH_CROP = {
    "Vessel": QRectF(10, 34, 160, 128),
    "Valve": QRectF(55, 30, 60, 66),
    "CheckValve": QRectF(37, 8, 56, 56),
    "Mixer": QRectF(55, 10, 60, 70),
    "Divider": QRectF(45, 10, 60, 70),
    "Compressor": QRectF(48, 20, 64, 64),
    "StreamIn": QRectF(32, 3, 74, 64),
    "StreamOut": QRectF(44, 3, 74, 64),
    "AnalogSource": QRectF(0, 8, 120, 44),
    "AnalogSink": QRectF(0, 8, 120, 44),
}


def _draw_symbol(painter, block):
    fn = _SYMBOLS.get(block.block_type)
    painter.save()
    if fn is not None:
        fn(painter, block, False)
    painter.restore()


def _draw_port_label(painter, name, pos, W, H):
    cx, cy = W / 2.0, H / 2.0
    dx = pos.x() - cx
    dy = pos.y() - cy
    x, y = pos.x(), pos.y()
    if abs(dx) >= abs(dy):
        # horizontal ports: label sits just above the process line
        if dx > 0:
            painter.drawText(QRectF(x - 70, y - 20, 66, 16),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, name)
        else:
            painter.drawText(QRectF(x + 4, y - 20, 66, 16),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, name)
    else:
        if dy > 0:
            painter.drawText(QRectF(x + 8, y - 8, 62, 16),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        else:
            painter.drawText(QRectF(x + 8, y - 8, 62, 16),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)


class PortItem(QGraphicsEllipseItem):
    def __init__(self, port, parent=None):
        super().__init__(-PORT_RADIUS, -PORT_RADIUS, 2 * PORT_RADIUS, 2 * PORT_RADIUS, parent)
        self.port = port
        self._edge_items = set()
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setZValue(2)
        self.restyle()

    def restyle(self):
        self.setBrush(QBrush(port_color(self.port.port_type)))
        self.setPen(QPen(QColor("#000000") if not Theme.dark else QColor("#ffffff"), 1.0))

    def add_edge_item(self, item):
        self._edge_items.add(item)

    def remove_edge_item(self, item):
        self._edge_items.discard(item)

    def refresh_edges(self):
        for e in self._edge_items:
            e.update_path()

    def hoverEnterEvent(self, event):
        self.setScale(1.35)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setScale(1.0)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.scene().begin_connection(self)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        # a double-click on a port belongs to its block: open the block panel
        node = self.parentItem()
        if node is not None and hasattr(node, "request_config"):
            node.request_config()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class NodeItem(QGraphicsItem):
    def __init__(self, block):
        super().__init__()
        self.block = block
        self.port_items = {}
        self.W, self.H, self.anchors = _layout(block)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(1)
        self._build_ports()

    def _build_ports(self):
        for name, port in self.block.inputs.items():
            item = PortItem(port, parent=self)
            item.setPos(self.anchors[name])
            self.port_items[name] = item
        for name, port in self.block.outputs.items():
            item = PortItem(port, parent=self)
            item.setPos(self.anchors[name])
            self.port_items[name] = item

    def boundingRect(self):
        return QRectF(-8, -8, self.W + 16, self.H + 16)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        _draw_symbol(painter, self.block)

        painter.setPen(QPen(Theme.color("text"), 1.0))
        f = QFont()
        f.setBold(True)
        f.setPointSize(8)
        painter.setFont(f)
        painter.drawText(QRectF(0, self.H - LABEL_H, self.W, LABEL_H),
                         Qt.AlignmentFlag.AlignCenter, self.block.name)

        painter.setFont(QFont())
        painter.setPen(QPen(Theme.color("subtext"), 1.0))
        for name, pos in self.anchors.items():
            _draw_port_label(painter, name, pos, self.W, self.H)

        if self.isSelected():
            painter.setPen(QPen(Theme.color("selection"), 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(0, 0, self.W, self.H).adjusted(-3, -3, 3, 3), 6, 6)

    # -- configuration panel -------------------------------------------------
    def request_config(self):
        scene = self.scene()
        if scene is not None and hasattr(scene, "node_config_requested"):
            scene.node_config_requested.emit(self.block)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.request_config()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        scene = self.scene()
        if scene is None:
            return
        menu = QMenu()
        configure = menu.addAction("Configure…")
        delete = menu.addAction("Delete")
        chosen = menu.exec(event.screenPos())
        if chosen is configure:
            self.request_config()
        elif chosen is delete:
            scene.remove_node(self.block.instance_id)
        event.accept()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.block.position = (value.x(), value.y())
            for p in self.port_items.values():
                p.refresh_edges()
        return super().itemChange(change, value)

    def refresh_edges(self):
        for p in self.port_items.values():
            p.refresh_edges()

    def restyle(self):
        for p in self.port_items.values():
            p.restyle()
        self.update()


# -- small palette icons (sidebar) ------------------------------------------
def draw_glyph(painter, rect, block_type, color):
    """Draw the canvas symbol of ``block_type`` scaled into ``rect``."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(rect)
    fn = _SYMBOLS.get(block_type)
    crop = _GLYPH_CROP.get(block_type)
    if fn is None or crop is None:
        painter.setPen(QPen(color, 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 3, 3)
        painter.restore()
        return
    s = min(rect.width() / crop.width(), rect.height() / crop.height())
    painter.translate(rect.center())
    painter.scale(s, s)
    painter.translate(-crop.center())

    class _Stub:
        states = {"level": 0.45}
        inputs = {}
    fn(painter, _Stub(), True)
    painter.restore()
