"""The Extra small view: two dials side by side.

The left dial controls a device picked from its dropdown ("Default" follows
whichever output Windows is using, so out of the box it's the master
volume). The right dial controls an app picked from its dropdown.

Turn a dial by dragging up/down (or left/right) or with the scroll wheel.
"""

from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme
from .models import INPUT, OUTPUT, AppInfo, DeviceInfo
from .theme import px
from .widgets import LevelMeter, caps_label, icon_button, meter_height

DEFAULT_DEVICE = "default"  # the dial follows the Windows default output
SWEEP = 270.0  # degrees from 0% to 100%
START = 225.0  # angle of 0% (bottom-left), counter-clockwise from 3 o'clock
DRAG_PER_PIXEL = 0.5  # volume points per pixel of mouse movement


class Knob(QWidget):
    """A rotary volume knob drawn in the current theme."""

    valueChanged = Signal(int)

    def __init__(self, diameter: int):
        super().__init__()
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Drag up or down, or scroll, to change the volume")
        self._value = 0
        self._muted = False
        self._drag: tuple[QPointF, int] | None = None

    # ---- value -----------------------------------------------------------
    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:  # noqa: N802 (Qt naming)
        value = int(max(0, min(100, round(value))))
        if value != self._value:
            self._value = value
            self.update()
            self.valueChanged.emit(value)

    def set_value_quietly(self, value: int) -> None:
        """Update from the system without echoing it back, and never while
        the user is turning the knob."""
        if self._drag is None and value != self._value:
            self._value = int(max(0, min(100, value)))
            self.update()

    def set_muted(self, muted: bool) -> None:
        if muted != self._muted:
            self._muted = muted
            self.update()

    def is_dragging(self) -> bool:
        return self._drag is not None

    # ---- mouse -----------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._drag = (event.globalPosition(), self._value)
            event.accept()
            return
        event.ignore()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is None:
            event.ignore()
            return
        start, start_value = self._drag
        delta = event.globalPosition() - start
        # Up or right turns it up; down or left turns it down.
        self.setValue(start_value + (delta.x() - delta.y()) * DRAG_PER_PIXEL)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None and event.button() == Qt.LeftButton:
            self._drag = None
            event.accept()
            return
        event.ignore()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self.isEnabled():
            event.ignore()
            return
        delta = event.angleDelta()
        steps = (delta.y() or delta.x()) / 120
        if steps:
            self.setValue(self._value + round(steps * 2) or (1 if steps > 0 else -1))
        event.accept()

    # ---- drawing -----------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = theme.P
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)

        side = min(self.width(), self.height())
        c = QPointF(self.width() / 2, self.height() / 2)
        arc_w = side * 0.065
        radius = side / 2 - arc_w * (1.6 if p.glow else 0.8)
        arc_rect = QRectF(c.x() - radius, c.y() - radius, 2 * radius, 2 * radius)
        body_r = radius * 0.64
        fraction = self._value / 100

        # Scale: empty track, then the filled part up to the current value.
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(p.track, arc_w, Qt.SolidLine, Qt.FlatCap if p.hud else Qt.RoundCap))
        painter.drawArc(arc_rect, round(START * 16), round(-SWEEP * 16))
        fill = QColor(p.muted if self._muted else p.accent)
        if fraction > 0:
            if p.glow and not self._muted:
                for spread, alpha in ((3.0, 0.10), (2.0, 0.18)):
                    halo = QColor(fill)
                    halo.setAlphaF(alpha)
                    painter.setPen(QPen(halo, arc_w * spread, Qt.SolidLine, Qt.RoundCap))
                    painter.drawArc(arc_rect, round(START * 16), round(-SWEEP * fraction * 16))
            painter.setPen(QPen(fill, arc_w, Qt.SolidLine, Qt.FlatCap if p.hud else Qt.RoundCap))
            painter.drawArc(arc_rect, round(START * 16), round(-SWEEP * fraction * 16))

        if p.console:  # printed scale marks, 0 to 10
            painter.setPen(QPen(QColor(p.muted), max(1.0, side * 0.012)))
            for i in range(11):
                a = math.radians(START - SWEEP * i / 10)
                inner, outer = radius * (0.74 if i % 5 else 0.70), radius * 0.82
                painter.drawLine(
                    QPointF(c.x() + math.cos(a) * inner, c.y() - math.sin(a) * inner),
                    QPointF(c.x() + math.cos(a) * outer, c.y() - math.sin(a) * outer),
                )

        self._draw_body(painter, c, body_r)

        # Pointer
        a = math.radians(START - SWEEP * fraction)
        tip = QPointF(c.x() + math.cos(a) * body_r * 0.86, c.y() - math.sin(a) * body_r * 0.86)
        tail = QPointF(c.x() + math.cos(a) * body_r * 0.30, c.y() - math.sin(a) * body_r * 0.30)
        pointer = QColor(p.strong if (p.console or not p.hud) else p.accent)
        if self._muted:
            pointer = QColor(p.muted)
        painter.setPen(QPen(pointer, max(1.5, side * 0.045), Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(tail, tip)

        # The number sits in the open gap at the bottom of the scale.
        font = QFont()
        font.setFamilies(theme.HUD_FONTS if (p.hud or p.console) else theme.UI_FONTS)
        font.setPixelSize(max(7, round(side * (0.12 if self._muted else 0.15))))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(p.danger if self._muted else p.strong)
        text = "MUTED" if self._muted else str(self._value)
        box = QRectF(c.x() - radius, c.y() + body_r * 0.98, 2 * radius, side / 2 - body_r * 0.98)
        painter.drawText(box, Qt.AlignHCenter | Qt.AlignVCenter, text)

    def _draw_body(self, painter: QPainter, c: QPointF, r: float) -> None:
        p = theme.P
        # Drop shadow under the knob
        shadow = QRadialGradient(c + QPointF(0, r * 0.12), r * 1.18)
        shadow.setColorAt(0.80, QColor(0, 0, 0, 70 if p.name != "light" else 30))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(shadow)
        painter.drawEllipse(c + QPointF(0, r * 0.12), r * 1.18, r * 1.18)

        if p.console:
            # Knurled black knob with a flat cap, like a desk's gain knob.
            body = QRadialGradient(c - QPointF(r * 0.3, r * 0.4), r * 1.5)
            body.setColorAt(0, QColor(70, 74, 79))
            body.setColorAt(1, QColor(14, 15, 16))
            painter.setBrush(body)
            painter.setPen(QPen(QColor(0, 0, 0, 160), 1))
            painter.drawEllipse(c, r, r)
            painter.setPen(QPen(QColor(255, 255, 255, 26), max(1.0, r * 0.05)))
            for i in range(36):
                a = math.radians(i * 10)
                painter.drawLine(
                    QPointF(c.x() + math.cos(a) * r * 0.86, c.y() + math.sin(a) * r * 0.86),
                    QPointF(c.x() + math.cos(a) * r * 0.98, c.y() + math.sin(a) * r * 0.98),
                )
            cap = QRadialGradient(c - QPointF(r * 0.2, r * 0.25), r)
            cap.setColorAt(0, QColor(58, 61, 66))
            cap.setColorAt(1, QColor(28, 30, 32))
            painter.setPen(QPen(QColor(0, 0, 0, 120), 1))
            painter.setBrush(cap)
            painter.drawEllipse(c, r * 0.76, r * 0.76)
            return

        if p.hud:
            # Faceted (octagonal) knob for the HUD themes
            path = QPainterPath()
            for i in range(8):
                a = math.radians(22.5 + i * 45)
                pt = QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r)
                path.moveTo(pt) if i == 0 else path.lineTo(pt)
            path.closeSubpath()
            base = QColor(p.panel2 or p.panel)
            painter.setBrush(base.lighter(170))
            painter.setPen(QPen(p.border, max(1.0, r * 0.05)))
            painter.drawPath(path)
            return

        light = p.name == "light"
        body = QRadialGradient(c - QPointF(r * 0.35, r * 0.45), r * 1.6)
        top = QColor(p.panel).lighter(108 if light else 190)
        bottom = QColor(p.panel).darker(112 if light else 110)
        body.setColorAt(0, top)
        body.setColorAt(1, bottom)
        painter.setBrush(body)
        painter.setPen(QPen(p.border, 1))
        painter.drawEllipse(c, r, r)


class ThemedCombo(QComboBox):
    """A dropdown that trims long names with "…" and draws its own arrow."""

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(px(40))
        self.setIconSize(QSize(px(13), px(13)))
        self._items: list[tuple[str, str]] = []
        self.display_text: dict[str, str] = {}  # what the closed box shows for an entry

    def set_items(self, items: list[tuple[str, str, QIcon | None]], current: str) -> None:
        """Replace the entries (data, text, icon) only when they've changed, so
        the once-a-second refresh never closes an open dropdown."""
        key = [(data, text) for data, text, _ in items]
        if self.view().isVisible():
            return
        if key != self._items:
            self.blockSignals(True)
            self.clear()
            for data, text, icon in items:
                if data == "--":
                    self.insertSeparator(self.count())
                elif icon is not None:
                    self.addItem(icon, text, data)
                else:
                    self.addItem(text, data)
            self.blockSignals(False)
            self._items = key
            widest = max((self.fontMetrics().horizontalAdvance(t) for _, t, _ in items), default=0)
            self.view().setMinimumWidth(min(px(340), widest + px(48)))
        index = self.findData(current)
        if index >= 0 and index != self.currentIndex():
            self.blockSignals(True)
            self.setCurrentIndex(index)
            self.blockSignals(False)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        field = self.style().subControlRect(QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxEditField, self)
        room = field.width() - (self.iconSize().width() + px(4) if not opt.currentIcon.isNull() else 0)
        full = self.display_text.get(self.currentData(), opt.currentText)
        self.setToolTip(full)
        opt.currentText = self.fontMetrics().elidedText(full, Qt.ElideRight, max(10, room))
        painter.drawComplexControl(QStyle.CC_ComboBox, opt)
        painter.drawControl(QStyle.CE_ComboBoxLabel, opt)
        # Arrow
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(theme.P.muted, max(1.2, 1.5 * theme.S), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        cx, cy, w = self.width() - px(10), self.height() / 2, px(3.5)
        painter.drawPolyline([QPointF(cx - w, cy - w / 2), QPointF(cx, cy + w / 2), QPointF(cx + w, cy - w / 2)])


class DialColumn(QWidget):
    """Label, dropdown, knob, and a mute button with a level meter."""

    volumeChanged = Signal(int)
    muteClicked = Signal()

    def __init__(self, title: str):
        super().__init__()
        self.header = QHBoxLayout()
        self.header.setContentsMargins(0, 0, 0, 0)
        self.header.setSpacing(px(2))
        self.label = caps_label(title, "Eyebrow")
        self.header.addWidget(self.label, 1)

        self.combo = ThemedCombo()
        self.knob = Knob(px(92))
        self.knob.valueChanged.connect(self.volumeChanged)
        self.mute_btn = icon_button("Mute", px(15))
        self.mute_btn.clicked.connect(self.muteClicked)
        self.meter = LevelMeter(meter_height(2.5))

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(px(4))
        bottom.addWidget(self.mute_btn)
        bottom.addWidget(self.meter, 1, Qt.AlignVCenter)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(px(5))
        lay.addLayout(self.header)
        lay.addWidget(self.combo)
        lay.addSpacing(px(2))
        lay.addWidget(self.knob, 0, Qt.AlignHCenter)
        lay.addLayout(bottom)

    def show_state(self, volume: int, muted: bool, is_input: bool, enabled: bool = True) -> None:
        self.knob.setEnabled(enabled)
        self.mute_btn.setEnabled(enabled)
        self.knob.set_value_quietly(volume)
        self.knob.set_muted(muted)
        size = px(15)
        shown = self.knob.value()
        self.mute_btn.setIcon(icons.microphone(size, muted) if is_input else icons.speaker_for(shown, muted, size))
        self.mute_btn.setToolTip("Unmute" if muted else "Mute")
        if not enabled:
            self.meter.set_level(0)


class DialsView(QWidget):
    """Device dial on the left, app dial on the right."""

    deviceVolume = Signal(str, int)
    deviceMute = Signal(str, bool)
    appVolume = Signal(str, int)
    appMute = Signal(str, bool)
    deviceChosen = Signal(str)  # DEFAULT_DEVICE or a device id
    appChosen = Signal(str)  # an app key
    expandRequested = Signal()

    def __init__(self, device_choice: str | None, app_choice: str | None):
        super().__init__()
        self.device_choice = device_choice or DEFAULT_DEVICE
        self.app_choice = app_choice
        self.devices: dict[str, DeviceInfo] = {}
        self.apps: dict[str, AppInfo] = {}
        self.default_output: str | None = None
        self.shown_app: str | None = None

        self.device_col = DialColumn("Device")
        self.app_col = DialColumn("App")
        self.expand_btn = icon_button("Switch to the full mixer", px(14))
        self.expand_btn.setIcon(icons.faders(px(14)))
        self.expand_btn.clicked.connect(self.expandRequested)
        self.app_col.header.addWidget(self.expand_btn, 0, Qt.AlignVCenter)
        self.expand_btn.setFixedSize(px(18), px(16))

        rule = QFrame()
        rule.setObjectName("Rule")
        rule.setFixedWidth(1)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(px(12))
        lay.addWidget(self.device_col, 1)
        lay.addWidget(rule)
        lay.addWidget(self.app_col, 1)

        self.device_col.combo.activated.connect(self._on_device_picked)
        self.app_col.combo.activated.connect(self._on_app_picked)
        self.device_col.volumeChanged.connect(self._on_device_volume)
        self.app_col.volumeChanged.connect(self._on_app_volume)
        self.device_col.muteClicked.connect(self._on_device_mute)
        self.app_col.muteClicked.connect(self._on_app_mute)

    # ---- what each dial points at -------------------------------------------
    def target_device(self) -> DeviceInfo | None:
        if self.device_choice != DEFAULT_DEVICE and self.device_choice in self.devices:
            return self.devices[self.device_choice]
        return self.devices.get(self.default_output) if self.default_output else None

    def target_app(self) -> AppInfo | None:
        return self.apps.get(self.shown_app) if self.shown_app else None

    def set_choices(self, device_choice: str | None, app_choice: str | None) -> None:
        self.device_choice = device_choice or DEFAULT_DEVICE
        self.app_choice = app_choice

    # ---- keeping up with the system ------------------------------------------
    def update_state(
        self, devices: list[DeviceInfo], apps: list[AppInfo], icon_for: Callable[[AppInfo], QIcon]
    ) -> None:
        self.devices = {d.id: d for d in devices}
        self.default_output = next((d.id for d in devices if d.flow == OUTPUT and d.is_default), None)
        self.apps = {a.key: a for a in apps}

        # Device dropdown: Default first, then outputs, then microphones.
        size = px(13)
        items: list[tuple[str, str, QIcon | None]] = []
        default_name = self.devices[self.default_output].name if self.default_output else "no output"
        items.append((DEFAULT_DEVICE, f"Default output (now {default_name})", icons.speaker(size, 2, False)))
        # Closed, it just shows the device the dial is turning.
        self.device_col.combo.display_text = {DEFAULT_DEVICE: default_name}
        outputs = sorted((d for d in devices if d.flow == OUTPUT), key=lambda d: d.name.lower())
        inputs = sorted((d for d in devices if d.flow == INPUT), key=lambda d: d.name.lower())
        for d in outputs:
            items.append((d.id, d.name, icons.speaker(size, 2, False)))
        if inputs:
            items.append(("--", "", None))
        for d in inputs:
            items.append((d.id, d.name, icons.microphone(size, False)))
        shown_device = self.device_choice if self.device_choice in self.devices else DEFAULT_DEVICE
        self.device_col.combo.set_items(items, shown_device)

        target = self.target_device()
        if target is None:
            self.device_col.show_state(0, False, False, enabled=False)
        else:
            self.device_col.show_state(target.volume, target.muted, target.flow == INPUT)

        # App dropdown. If the chosen app isn't playing, show another one but
        # keep the choice, so it comes back when the app starts again.
        if apps:
            self.shown_app = self.app_choice if self.app_choice in self.apps else apps[0].key
            app_items = [(a.key, a.name, icon_for(a)) for a in apps]
            self.app_col.combo.setEnabled(True)
            self.app_col.combo.set_items(app_items, self.shown_app)
            app = self.apps[self.shown_app]
            self.app_col.show_state(app.volume, app.muted, False)
        else:
            self.shown_app = None
            self.app_col.combo.set_items([("", "No apps playing", None)], "")
            self.app_col.combo.setEnabled(False)
            self.app_col.show_state(0, False, False, enabled=False)

    def update_meters(self, device_peak: Callable[[str], float], app_peak: Callable[[str], float]) -> None:
        target = self.target_device()
        self.device_col.meter.set_level(device_peak(target.id) if target else 0.0)
        self.app_col.meter.set_level(app_peak(self.shown_app) if self.shown_app else 0.0)

    # ---- user actions -----------------------------------------------------------
    def _on_device_picked(self, index: int) -> None:
        choice = self.device_col.combo.itemData(index)
        if not choice:
            return
        self.device_choice = choice
        self.deviceChosen.emit(choice)
        target = self.target_device()
        if target:
            self.device_col.knob.set_value_quietly(target.volume)
            self.device_col.show_state(target.volume, target.muted, target.flow == INPUT)

    def _on_app_picked(self, index: int) -> None:
        choice = self.app_col.combo.itemData(index)
        if not choice:
            return
        self.app_choice = self.shown_app = choice
        self.appChosen.emit(choice)
        app = self.apps.get(choice)
        if app:
            self.app_col.show_state(app.volume, app.muted, False)

    def _on_device_volume(self, value: int) -> None:
        target = self.target_device()
        if target:
            target.volume = value
            self.deviceVolume.emit(target.id, value)
            self.device_col.show_state(value, target.muted, target.flow == INPUT)

    def _on_device_mute(self) -> None:
        target = self.target_device()
        if target:
            target.muted = not target.muted
            self.deviceMute.emit(target.id, target.muted)
            self.device_col.show_state(target.volume, target.muted, target.flow == INPUT)

    def _on_app_volume(self, value: int) -> None:
        app = self.target_app()
        if app:
            app.volume = value
            self.appVolume.emit(app.key, value)
            self.app_col.show_state(value, app.muted, False)

    def _on_app_mute(self) -> None:
        app = self.target_app()
        if app:
            app.muted = not app.muted
            self.appMute.emit(app.key, app.muted)
            self.app_col.show_state(app.volume, app.muted, False)
