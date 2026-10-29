"""Icons drawn with QPainter in the current theme's colours, so the app needs
no icon font or image files (apart from the app icon)."""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

from . import theme


def _canvas(size: int) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size * 2, size * 2)  # drawn at 2x so icons stay crisp on high-DPI screens
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    return pm, p


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _tile(p: QPainter, size: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(theme.P.tile)
    if theme.P.hud:
        cut = size * 0.22
        path = QPainterPath()
        path.moveTo(cut, 0)
        path.lineTo(size, 0)
        path.lineTo(size, size - cut)
        path.lineTo(size - cut, size)
        path.lineTo(0, size)
        path.lineTo(0, cut)
        path.closeSubpath()
        p.drawPath(path)
    else:
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)


def speaker(size: int, level: int, muted: bool, color: QColor | None = None) -> QIcon:
    """Speaker with 0-3 sound waves, or a cross when muted."""
    pm, p = _canvas(size)
    s = size / 24.0
    c = color or theme.P.text
    p.setPen(_pen(c, 1.7 * s))
    p.setBrush(Qt.NoBrush)

    body = QPainterPath()
    body.moveTo(3 * s, 9.5 * s)
    body.lineTo(7 * s, 9.5 * s)
    body.lineTo(12 * s, 5 * s)
    body.lineTo(12 * s, 19 * s)
    body.lineTo(7 * s, 14.5 * s)
    body.lineTo(3 * s, 14.5 * s)
    body.closeSubpath()
    p.drawPath(body)

    if muted:
        p.setPen(_pen(theme.P.danger, 1.8 * s))
        p.drawLine(QPointF(15.5 * s, 9 * s), QPointF(21.5 * s, 15 * s))
        p.drawLine(QPointF(21.5 * s, 9 * s), QPointF(15.5 * s, 15 * s))
    else:
        for i in range(level):
            r = (3.2 + i * 3.2) * s
            p.drawArc(QRectF(12 * s - r, 12 * s - r, 2 * r, 2 * r), -45 * 16, 90 * 16)
    p.end()
    return QIcon(pm)


def speaker_for(volume: int, muted: bool, size: int) -> QIcon:
    if muted or volume == 0:
        return speaker(size, 0, True)
    return speaker(size, 1 if volume < 34 else 2 if volume < 67 else 3, False)


def microphone(size: int, muted: bool, color: QColor | None = None) -> QIcon:
    pm, p = _canvas(size)
    s = size / 24.0
    p.setPen(_pen(color or theme.P.text, 1.7 * s))
    p.drawRoundedRect(QRectF(9 * s, 3 * s, 6 * s, 11 * s), 3 * s, 3 * s)
    p.drawArc(QRectF(5.5 * s, 6 * s, 13 * s, 12 * s), 180 * 16, 180 * 16)
    p.drawLine(QPointF(12 * s, 18 * s), QPointF(12 * s, 21 * s))
    p.drawLine(QPointF(9 * s, 21 * s), QPointF(15 * s, 21 * s))
    if muted:
        p.setPen(_pen(theme.P.danger, 1.9 * s))
        p.drawLine(QPointF(4 * s, 4 * s), QPointF(20 * s, 20 * s))
    p.end()
    return QIcon(pm)


def chevron(size: int, up: bool) -> QIcon:
    """Collapse / expand arrow for the master card."""
    pm, p = _canvas(size)
    s = size / 24.0
    p.setPen(_pen(theme.P.muted, 1.9 * s))
    if up:
        p.drawPolyline([QPointF(7 * s, 14.5 * s), QPointF(12 * s, 9.5 * s), QPointF(17 * s, 14.5 * s)])
    else:
        p.drawPolyline([QPointF(7 * s, 9.5 * s), QPointF(12 * s, 14.5 * s), QPointF(17 * s, 9.5 * s)])
    p.end()
    return QIcon(pm)


def step_arrow(size: int, up: bool) -> QIcon:
    """A solid up or down arrow on a small tile: the dials' step buttons."""
    pm, p = _canvas(size)
    s = size / 24.0
    _tile(p, 24 * s)
    path = QPainterPath()
    if up:
        path.moveTo(12 * s, 7 * s)
        path.lineTo(18 * s, 15.5 * s)
        path.lineTo(6 * s, 15.5 * s)
    else:
        path.moveTo(12 * s, 17 * s)
        path.lineTo(18 * s, 8.5 * s)
        path.lineTo(6 * s, 8.5 * s)
    path.closeSubpath()
    p.setPen(_pen(theme.P.text, 1.2 * s))
    p.setBrush(theme.P.text)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


def knob(size: int) -> QIcon:
    """A small dial: a ring with a pointer (the "switch to dials" button)."""
    pm, p = _canvas(size)
    s = size / 24.0
    p.setPen(_pen(theme.P.muted, 1.8 * s))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(4 * s, 4 * s, 16 * s, 16 * s), 225 * 16, -270 * 16)
    p.drawLine(QPointF(12 * s, 12 * s), QPointF(15.8 * s, 8.2 * s))
    p.end()
    return QIcon(pm)


def faders(size: int) -> QIcon:
    """Three mixer faders (the "switch to the full mixer" button)."""
    pm, p = _canvas(size)
    s = size / 24.0
    pen = _pen(theme.P.muted, 1.8 * s)
    for x, knob_y in ((6.5, 14.5), (12, 8.5), (17.5, 12)):
        p.setPen(pen)
        p.drawLine(QPointF(x * s, 4.5 * s), QPointF(x * s, 19.5 * s))
        p.setPen(Qt.NoPen)
        p.setBrush(theme.P.muted)
        p.drawRoundedRect(QRectF((x - 2.4) * s, (knob_y - 1.6) * s, 4.8 * s, 3.2 * s), 1.2 * s, 1.2 * s)
    p.end()
    return QIcon(pm)


def bell(size: int) -> QIcon:
    pm, p = _canvas(size)
    s = size / 24.0
    _tile(p, 24 * s)
    p.setPen(_pen(theme.P.text, 1.6 * s))
    p.setBrush(Qt.NoBrush)
    body = QPainterPath()
    body.moveTo(6.5 * s, 16 * s)
    body.cubicTo(8 * s, 14 * s, 7.5 * s, 12 * s, 7.5 * s, 10.5 * s)
    body.cubicTo(7.5 * s, 7.5 * s, 9.5 * s, 5.5 * s, 12 * s, 5.5 * s)
    body.cubicTo(14.5 * s, 5.5 * s, 16.5 * s, 7.5 * s, 16.5 * s, 10.5 * s)
    body.cubicTo(16.5 * s, 12 * s, 16 * s, 14 * s, 17.5 * s, 16 * s)
    body.closeSubpath()
    p.drawPath(body)
    p.drawLine(QPointF(10.5 * s, 18.5 * s), QPointF(13.5 * s, 18.5 * s))
    p.end()
    return QIcon(pm)


def device_badge(size: int, is_input: bool) -> QIcon:
    """Tile with a speaker or microphone, used in the device list."""
    pm, p = _canvas(size)
    _tile(p, size)
    inner = int(size * 0.62)
    glyph = microphone(inner, False) if is_input else speaker(inner, 2, False)
    off = (size - inner) / 2
    glyph.paint(p, round(off), round(off), inner, inner)
    p.end()
    return QIcon(pm)


def letter_tile(size: int, name: str) -> QIcon:
    """Coloured tile with the app's first letter, for apps without an icon."""
    pm, p = _canvas(size)
    hue = hashlib.md5(name.encode("utf-8")).digest()[0] * 360 // 256
    p.setPen(Qt.NoPen)
    p.setBrush(QColor.fromHsl(hue, 110, 70))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
    font = QFont()
    font.setFamilies(theme.UI_FONTS)
    font.setPixelSize(max(6, int(size * 0.5)))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#F4F6FA"))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, (name.strip()[:1] or "?").upper())
    p.end()
    return QIcon(pm)


def app_icon(size: int = 256) -> QIcon:
    """The app icon: three mixer faders on a dark tile (same in every theme)."""
    pm, p = _canvas(size)
    s = size / 64.0
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#181B21"))
    p.drawRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s), 15 * s, 15 * s)
    track, accent = QColor("#2E3440"), QColor("#5EE6C4")
    for i, knob_y in enumerate((38, 22, 31)):
        x = (18 + i * 14) * s
        p.setPen(_pen(track, 5 * s))
        p.drawLine(QPointF(x, 14 * s), QPointF(x, 50 * s))
        p.setPen(_pen(accent, 5 * s))
        p.drawLine(QPointF(x, knob_y * s), QPointF(x, 50 * s))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#E9ECF1"))
        p.drawEllipse(QPointF(x, knob_y * s), 5.5 * s, 5.5 * s)
    p.end()
    return QIcon(pm)
