"""Icons drawn with QPainter, so the app needs no icon font or image files
(apart from the app icon) and looks the same on every Windows version."""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

from . import theme


def _canvas(size: int) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size * 2, size * 2)  # draw at 2x for crisp high-DPI icons
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


def speaker(size: int, level: int, muted: bool, color: str = theme.TEXT) -> QIcon:
    """Speaker with 0-3 sound waves, or a cross when muted."""
    pm, p = _canvas(size)
    s = size / 24.0
    c = QColor(color)
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
        p.setPen(_pen(QColor(theme.DANGER), 1.8 * s))
        p.drawLine(QPointF(15.5 * s, 9 * s), QPointF(21.5 * s, 15 * s))
        p.drawLine(QPointF(21.5 * s, 9 * s), QPointF(15.5 * s, 15 * s))
    else:
        for i in range(level):
            r = (3.2 + i * 3.2) * s
            rect = QRectF(12 * s - r, 12 * s - r, 2 * r, 2 * r)
            p.drawArc(rect, -45 * 16, 90 * 16)
    p.end()
    return QIcon(pm)


def speaker_for(volume: int, muted: bool, size: int = 20, color: str = theme.TEXT) -> QIcon:
    if muted or volume == 0:
        return speaker(size, 0, True, color)
    level = 1 if volume < 34 else 2 if volume < 67 else 3
    return speaker(size, level, False, color)


def microphone(size: int, muted: bool, color: str = theme.TEXT) -> QIcon:
    pm, p = _canvas(size)
    s = size / 24.0
    c = QColor(color)
    p.setPen(_pen(c, 1.7 * s))
    p.drawRoundedRect(QRectF(9 * s, 3 * s, 6 * s, 11 * s), 3 * s, 3 * s)
    p.drawArc(QRectF(5.5 * s, 6 * s, 13 * s, 12 * s), 180 * 16, 180 * 16)
    p.drawLine(QPointF(12 * s, 18 * s), QPointF(12 * s, 21 * s))
    p.drawLine(QPointF(9 * s, 21 * s), QPointF(15 * s, 21 * s))
    if muted:
        p.setPen(_pen(QColor(theme.DANGER), 1.9 * s))
        p.drawLine(QPointF(4 * s, 4 * s), QPointF(20 * s, 20 * s))
    p.end()
    return QIcon(pm)


def pin(size: int, active: bool) -> QIcon:
    pm, p = _canvas(size)
    s = size / 24.0
    c = QColor(theme.ACCENT if active else theme.TEXT_DIM)
    p.setPen(_pen(c, 1.7 * s))
    p.setBrush(c if active else Qt.NoBrush)
    head = QPainterPath()
    head.moveTo(9 * s, 3.5 * s)
    head.lineTo(15 * s, 3.5 * s)
    head.lineTo(14 * s, 10 * s)
    head.lineTo(17.5 * s, 14 * s)
    head.lineTo(6.5 * s, 14 * s)
    head.lineTo(10 * s, 10 * s)
    head.closeSubpath()
    p.drawPath(head)
    p.drawLine(QPointF(12 * s, 14 * s), QPointF(12 * s, 21 * s))
    p.end()
    return QIcon(pm)


def bell(size: int) -> QIcon:
    pm, p = _canvas(size)
    s = size / 24.0
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.SURFACE_HI))
    p.drawRoundedRect(QRectF(0, 0, 24 * s, 24 * s), 7 * s, 7 * s)
    c = QColor(theme.TEXT)
    p.setPen(_pen(c, 1.6 * s))
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
    """Rounded tile with a speaker or microphone, used in the device list."""
    pm, p = _canvas(size)
    s = size / 24.0
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.SURFACE_HI))
    p.drawRoundedRect(QRectF(0, 0, 24 * s, 24 * s), 7 * s, 7 * s)
    p.end()
    glyph = microphone(int(size * 0.62), False) if is_input else speaker(int(size * 0.62), 2, False)
    p = QPainter(pm)
    off = size * 0.19
    glyph.paint(p, int(off), int(off), int(size * 0.62), int(size * 0.62))
    p.end()
    return QIcon(pm)


def letter_tile(size: int, name: str) -> QIcon:
    """Coloured tile with the app's first letter, used when an app has no icon."""
    pm, p = _canvas(size)
    digest = hashlib.md5(name.encode("utf-8")).digest()
    hue = digest[0] * 360 // 256
    p.setPen(Qt.NoPen)
    p.setBrush(QColor.fromHsl(hue, 110, 70))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.29, size * 0.29)
    font = QFont(theme.FONT_FAMILY)
    font.setPixelSize(int(size * 0.5))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#F4F6FA"))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, (name.strip()[:1] or "?").upper())
    p.end()
    return QIcon(pm)


def app_icon(size: int = 256) -> QIcon:
    """The Volume Mixer app icon: three mixer faders on a dark tile."""
    pm, p = _canvas(size)
    s = size / 64.0
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.SURFACE))
    p.drawRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s), 15 * s, 15 * s)
    track = QColor(theme.TRACK)
    accent = QColor(theme.ACCENT)
    for i, knob_y in enumerate((38, 22, 31)):
        x = (18 + i * 14) * s
        p.setPen(_pen(track, 5 * s))
        p.drawLine(QPointF(x, 14 * s), QPointF(x, 50 * s))
        p.setPen(_pen(accent, 5 * s))
        p.drawLine(QPointF(x, knob_y * s), QPointF(x, 50 * s))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.TEXT))
        p.drawEllipse(QPointF(x, knob_y * s), 5.5 * s, 5.5 * s)
    p.end()
    return QIcon(pm)
