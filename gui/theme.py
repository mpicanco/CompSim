from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QColor

_STYLES_DIR = Path(__file__).resolve().parent.parent / "styles"

PALETTES = {
    "dark": {
        "canvas_bg": "#1b1e24",
        "grid": "#2a2f3a",
        "grid_major": "#333a47",
        "node_bg": "#242a35",
        "node_border": "#3d4554",
        "node_header": "#2f3644",
        "text": "#e6e6e6",
        "subtext": "#9aa4b5",
        "port_material": "#4aa3ff",
        "port_signal": "#ffb84d",
        "port_power": "#4dff88",
        "edge": "#8f9bb3",
        "edge_active": "#4aa3ff",
        "selection": "#2f81f7",
        "equip_stroke": "#c9d1dc",
        "equip_fill": "#2b3442",
        "equip_shade": "#3a4558",
        "liquid": "#2f7fd6",
        "feed": "#2e7d4f",
        "product": "#8a5a1f",
    },
    "light": {
        "canvas_bg": "#f7f8fa",
        "grid": "#e3e6ec",
        "grid_major": "#d4d9e1",
        "node_bg": "#ffffff",
        "node_border": "#b9c0cc",
        "node_header": "#eef1f6",
        "text": "#1f2430",
        "subtext": "#5b6472",
        "port_material": "#1a73e8",
        "port_signal": "#c77800",
        "port_power": "#1e9e5a",
        "edge": "#5b6472",
        "edge_active": "#1a73e8",
        "selection": "#1a73e8",
        "equip_stroke": "#2b3340",
        "equip_fill": "#f1f5fb",
        "equip_shade": "#dbe3ef",
        "liquid": "#7fb6f2",
        "feed": "#cdebd8",
        "product": "#f6dfc0",
    },
}


class Theme:
    dark = True

    @classmethod
    def colors(cls):
        return PALETTES["dark" if cls.dark else "light"]

    @classmethod
    def color(cls, key):
        return QColor(cls.colors()[key])

    @classmethod
    def apply(cls, app):
        qss = (_STYLES_DIR / ("dark.qss" if cls.dark else "light.qss")).read_text()
        app.setStyleSheet(qss)

    @classmethod
    def toggle(cls, app):
        cls.dark = not cls.dark
        cls.apply(app)
