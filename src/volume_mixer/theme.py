"""Colours, fonts and the Qt stylesheet in one place."""

FONT_FAMILY = "Segoe UI Variable Text"
FONT_FALLBACKS = ["Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "sans-serif"]

BG = "#101216"
SURFACE = "#181B21"
SURFACE_HI = "#232831"
BORDER = "#262B34"
TRACK = "#2E3440"
TEXT = "#E9ECF1"
TEXT_DIM = "#8C94A3"
TEXT_FAINT = "#5D6573"
ACCENT = "#5EE6C4"  # mint
ACCENT_PRESSED = "#3FCFAB"
METER_HOT = "#F5B54A"  # amber near the top of the meter
DANGER = "#FF6B6B"

STYLESHEET = f"""
QWidget#Root {{ background: {BG}; }}
QWidget {{ color: {TEXT}; font-size: 13px; }}
QToolTip {{
    background: {SURFACE_HI}; color: {TEXT}; border: 1px solid {BORDER};
    padding: 4px 6px; border-radius: 6px;
}}

/* ---- cards ------------------------------------------------------ */
QFrame#MasterCard {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 16px;
}}
QFrame#Row {{ background: transparent; border-radius: 12px; }}
QFrame#Row:hover {{ background: {SURFACE}; }}

QLabel#Eyebrow {{
    color: {TEXT_DIM}; font-size: 11px; font-weight: 600; letter-spacing: 1.2px;
}}
QLabel#MasterDevice {{ color: {TEXT}; font-size: 15px; font-weight: 600; }}
QLabel#MasterPercent {{ color: {TEXT}; font-size: 30px; font-weight: 300; }}
QLabel#RowTitle {{ color: {TEXT}; font-size: 13px; font-weight: 600; }}
QLabel#RowSubtitle {{ color: {TEXT_DIM}; font-size: 11px; }}
QLabel#Percent {{ color: {TEXT_DIM}; font-size: 12px; }}
QLabel#Section {{
    color: {TEXT_FAINT}; font-size: 11px; font-weight: 600; letter-spacing: 1.2px;
    padding: 10px 12px 2px 12px;
}}
QLabel#Empty {{ color: {TEXT_FAINT}; font-size: 13px; padding: 32px 12px; }}
QLabel#Badge {{
    color: {BG}; background: {ACCENT}; border-radius: 8px;
    font-size: 10px; font-weight: 700; padding: 1px 7px;
}}

/* ---- buttons ---------------------------------------------------- */
QToolButton#IconButton {{
    background: transparent; border: none; border-radius: 8px; padding: 4px;
}}
QToolButton#IconButton:hover {{ background: {SURFACE_HI}; }}
QToolButton#IconButton:pressed {{ background: {TRACK}; }}

QPushButton#Ghost {{
    background: transparent; color: {TEXT_DIM}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 2px 9px; font-size: 11px;
}}
QPushButton#Ghost:hover {{ color: {TEXT}; border-color: {TEXT_FAINT}; }}

/* segmented tab switcher */
QFrame#Segmented {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 11px;
}}
QPushButton#Segment {{
    background: transparent; color: {TEXT_DIM}; border: none; border-radius: 8px;
    padding: 7px 0; font-weight: 600;
}}
QPushButton#Segment:hover {{ color: {TEXT}; }}
QPushButton#Segment:checked {{ background: {SURFACE_HI}; color: {TEXT}; }}

/* ---- sliders ---------------------------------------------------- */
QSlider::groove:horizontal {{ height: 4px; background: {TRACK}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {TEXT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: #FFFFFF; }}
QSlider[muted="true"]::sub-page:horizontal {{ background: {TEXT_FAINT}; }}
QSlider[muted="true"]::handle:horizontal {{ background: {TEXT_DIM}; }}

QSlider#MasterSlider::groove:horizontal {{ height: 6px; border-radius: 3px; }}
QSlider#MasterSlider::sub-page:horizontal {{ border-radius: 3px; }}
QSlider#MasterSlider::handle:horizontal {{
    width: 18px; height: 18px; margin: -6px 0; border-radius: 9px;
}}

/* ---- scroll area ------------------------------------------------ */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {TRACK}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {TEXT_FAINT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QMenu {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {SURFACE_HI}; }}
"""
