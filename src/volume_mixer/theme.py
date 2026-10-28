"""Themes, sizes and the Qt stylesheet.

The four themes use the same colours as the World Clock Widget, so the two
widgets look like a set on the desktop.

``P`` (the palette) and ``S`` (the size scale) describe the look currently in
use. The window sets them with :func:`use` before it builds its contents, and
the icons, meters and stylesheet read them.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor

UI_FONTS = ["Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "sans-serif"]
HUD_FONTS = ["Bahnschrift", "Segoe UI", "DejaVu Sans Condensed", "sans-serif"]

THEMES = ("dark", "light", "cyberpunk", "tactical")
THEME_NAMES = {"dark": "Dark", "light": "Light", "cyberpunk": "Cyberpunk", "tactical": "Tactical"}

# Size presets, on the clock's 1-100 scale where 50 is normal.
SIZES = ((40, "Small"), (50, "Normal"), (65, "Large"), (80, "Extra large"))
MIN_SIZE, MAX_SIZE = 30, 100


def scale_for(size: int) -> float:
    """50 is normal size; 100 is twice as big."""
    return max(MIN_SIZE, min(MAX_SIZE, size)) / 50.0


def rgba(r: int, g: int, b: int, a: float = 1.0) -> QColor:
    return QColor(r, g, b, round(max(0.0, min(1.0, a)) * 255))


@dataclass(frozen=True)
class Palette:
    name: str
    panel: QColor  # background (alpha replaced by the opacity setting)
    panel2: QColor | None  # bottom of a vertical background gradient
    border: QColor
    border2: QColor | None  # right-hand end of a border gradient
    separator: QColor
    text: QColor  # names and labels
    strong: QColor  # big numbers, slider handles
    muted: QColor  # secondary text
    accent: QColor  # sliders, badges, meters
    hot: QColor  # top of the level meters
    danger: QColor  # mute cross
    track: QColor  # empty slider / meter track
    hover: QColor  # row hover, selected tab
    tile: QColor  # icon tiles
    glow: bool = False  # neon halo round the panel
    hud: bool = False  # cut-corner panel, scanlines, HUD font
    tactical: bool = False  # even cut corners, hatching, corner brackets

    def with_accent(self, color: QColor) -> "Palette":
        from dataclasses import replace

        return replace(self, accent=color)


PALETTES: dict[str, Palette] = {
    "dark": Palette(
        name="dark",
        panel=rgba(17, 19, 25),
        panel2=None,
        border=rgba(255, 255, 255, 0.10),
        border2=None,
        separator=rgba(255, 255, 255, 0.07),
        text=rgba(236, 239, 244),
        strong=rgba(255, 255, 255),
        muted=rgba(164, 171, 184),
        accent=rgba(255, 138, 91),
        hot=rgba(255, 209, 102),
        danger=rgba(255, 107, 107),
        track=rgba(255, 255, 255, 0.13),
        hover=rgba(255, 255, 255, 0.055),
        tile=rgba(255, 255, 255, 0.07),
    ),
    "light": Palette(
        name="light",
        panel=rgba(250, 250, 252),
        panel2=None,
        border=rgba(0, 0, 0, 0.08),
        border2=None,
        separator=rgba(0, 0, 0, 0.07),
        text=rgba(30, 34, 42),
        strong=rgba(17, 19, 25),
        muted=rgba(95, 102, 116),
        accent=rgba(226, 96, 52),
        hot=rgba(214, 151, 0),
        danger=rgba(208, 52, 52),
        track=rgba(0, 0, 0, 0.11),
        hover=rgba(0, 0, 0, 0.045),
        tile=rgba(0, 0, 0, 0.055),
    ),
    "cyberpunk": Palette(
        name="cyberpunk",
        panel=rgba(10, 6, 20),
        panel2=rgba(24, 10, 44),
        border=rgba(255, 42, 109, 0.95),
        border2=rgba(5, 217, 232, 0.95),
        separator=rgba(5, 217, 232, 0.16),
        text=rgba(5, 217, 232),
        strong=rgba(242, 245, 255),
        muted=rgba(150, 150, 214),
        accent=rgba(255, 42, 109),
        hot=rgba(249, 240, 2),
        danger=rgba(255, 80, 80),
        track=rgba(5, 217, 232, 0.20),
        hover=rgba(5, 217, 232, 0.07),
        tile=rgba(5, 217, 232, 0.10),
        glow=True,
        hud=True,
    ),
    "tactical": Palette(
        name="tactical",
        panel=rgba(28, 32, 21),
        panel2=rgba(17, 20, 13),
        border=rgba(181, 161, 107, 0.9),
        border2=None,
        separator=rgba(181, 161, 107, 0.16),
        text=rgba(216, 198, 154),
        strong=rgba(236, 226, 200),
        muted=rgba(160, 150, 118),
        accent=rgba(242, 160, 61),
        hot=rgba(230, 90, 70),
        danger=rgba(230, 90, 70),
        track=rgba(181, 161, 107, 0.24),
        hover=rgba(242, 160, 61, 0.07),
        tile=rgba(181, 161, 107, 0.12),
        hud=True,
        tactical=True,
    ),
}

# The look in use right now (set by the window before building widgets).
P: Palette = PALETTES["dark"]
S: float = 1.0


def use(palette: Palette, scale: float) -> None:
    global P, S
    P, S = palette, scale


def px(n: float) -> int:
    """A size in pixels at the current scale."""
    return max(1, round(n * S))


def css(c: QColor) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha()})"


def stylesheet() -> str:
    p = P
    hud_font = ", ".join(f'"{f}"' for f in HUD_FONTS)
    number_font = f"font-family: {hud_font};" if p.hud else ""
    caps_weight = 700 if p.hud else 600
    return f"""
QWidget {{ color: {css(p.text)}; font-size: {px(13)}px; background: transparent; }}
QToolTip {{
    background: {css(p.panel)}; color: {css(p.strong)}; border: 1px solid {css(p.border)};
    padding: {px(4)}px {px(6)}px;
}}

QLabel#Eyebrow, QLabel#Section {{
    color: {css(p.muted)}; font-size: {px(10.5)}px; font-weight: {caps_weight};
}}
QLabel#Section {{ padding: {px(8)}px {px(10)}px {px(1)}px {px(10)}px; }}
QLabel#MasterDevice {{ color: {css(p.strong)}; font-size: {px(14)}px; font-weight: 600; }}
QLabel#MasterPercent {{
    color: {css(p.strong)}; font-size: {px(28)}px; font-weight: {500 if p.hud else 300}; {number_font}
}}
QLabel#RowTitle {{ color: {css(p.strong if not p.hud else p.text)}; font-size: {px(12.5)}px; font-weight: 600; }}
QLabel#RowSubtitle {{ color: {css(p.muted)}; font-size: {px(10.5)}px; }}
QLabel#Percent {{ color: {css(p.muted)}; font-size: {px(11.5)}px; {number_font} }}
QLabel#Empty {{ color: {css(p.muted)}; font-size: {px(12)}px; padding: {px(18)}px {px(10)}px; }}
QLabel#Badge {{
    color: {css(QColor(p.panel.red(), p.panel.green(), p.panel.blue()))}; background: {css(p.accent)};
    border-radius: {px(3) if p.hud else px(7)}px; font-size: {px(9)}px; font-weight: 700;
    padding: {px(1)}px {px(6)}px;
}}

QFrame#Row {{ border-radius: {px(3) if p.hud else px(10)}px; }}
QFrame#Row:hover {{ background: {css(p.hover)}; }}
QFrame#Rule {{ background: {css(p.separator)}; border: none; }}

QToolButton#IconButton {{ border: none; border-radius: {px(3) if p.hud else px(7)}px; padding: {px(3)}px; }}
QToolButton#IconButton:hover {{ background: {css(p.hover)}; }}

QPushButton#Ghost {{
    color: {css(p.muted)}; border: 1px solid {css(p.separator)};
    border-radius: {px(3) if p.hud else px(7)}px; padding: {px(1)}px {px(7)}px; font-size: {px(10)}px;
}}
QPushButton#Ghost:hover {{ color: {css(p.strong)}; border-color: {css(p.muted)}; }}

QPushButton#Segment {{
    color: {css(p.muted)}; border: none; border-radius: {px(3) if p.hud else px(7)}px;
    padding: {px(5)}px 0; font-weight: 600; font-size: {px(12)}px;
}}
QPushButton#Segment:hover {{ color: {css(p.strong)}; }}
QPushButton#Segment:checked {{ background: {css(p.hover)}; color: {css(p.strong)}; }}
QFrame#Segmented {{
    border: 1px solid {css(p.separator)}; border-radius: {px(4) if p.hud else px(9)}px;
}}

QSlider {{ min-height: {px(16)}px; }}
QSlider::groove:horizontal {{ height: {px(4)}px; background: {css(p.track)}; border-radius: {px(2)}px; }}
QSlider::sub-page:horizontal {{ background: {css(p.accent)}; border-radius: {px(2)}px; }}
QSlider::handle:horizontal {{
    background: {css(p.strong)}; width: {px(12)}px; height: {px(12)}px;
    margin: -{px(4)}px 0; border-radius: {px(2) if p.hud else px(6)}px;
}}
QSlider[muted="true"]::sub-page:horizontal {{ background: {css(p.muted)}; }}
QSlider[muted="true"]::handle:horizontal {{ background: {css(p.muted)}; }}
QSlider#MasterSlider {{ min-height: {px(20)}px; }}
QSlider#MasterSlider::groove:horizontal {{ height: {px(6)}px; border-radius: {px(3)}px; }}
QSlider#MasterSlider::sub-page:horizontal {{ border-radius: {px(3)}px; }}
QSlider#MasterSlider::handle:horizontal {{
    width: {px(16)}px; height: {px(16)}px; margin: -{px(5)}px 0; border-radius: {px(2) if p.hud else px(8)}px;
}}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: {px(6)}px; margin: {px(2)}px 0; }}
QScrollBar::handle:vertical {{ background: {css(p.track)}; border-radius: {px(3)}px; min-height: {px(24)}px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""
