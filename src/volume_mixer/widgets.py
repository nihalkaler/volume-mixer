"""Reusable pieces of the window: level meters, volume rows, the master card."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme


class ElidedLabel(QLabel):
    """A label that trims long text with "…" instead of widening the window."""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(10)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        if text != self._full:
            self._full = text
            self.setToolTip(text)
            self._elide()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        shown = self.fontMetrics().elidedText(self._full, Qt.ElideRight, max(10, self.width()))
        if shown != self.text():
            super().setText(shown)


class LevelMeter(QWidget):
    """A thin bar showing how loud something is right now."""

    def __init__(self, height: int = 3, parent: QWidget | None = None):
        super().__init__(parent)
        self._level = 0.0
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_level(self, peak: float) -> None:
        peak = max(0.0, min(1.0, peak))
        # Rise instantly, fall gently, like a hardware VU meter.
        new = peak if peak > self._level else self._level * 0.8 + peak * 0.2
        if new < 0.004:
            new = 0.0
        if abs(new - self._level) > 0.002 or (new == 0.0 and self._level != 0.0):
            self._level = new
            self.update()

    def level(self) -> float:
        return self._level

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        radius = r.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.SURFACE_HI))
        p.drawRoundedRect(r, radius, radius)
        if self._level > 0:
            fill = QRectF(r.x(), r.y(), max(r.height(), r.width() * self._level), r.height())
            grad = QLinearGradient(r.topLeft(), r.topRight())
            grad.setColorAt(0.0, QColor(theme.ACCENT))
            grad.setColorAt(0.75, QColor(theme.ACCENT))
            grad.setColorAt(1.0, QColor(theme.METER_HOT))
            p.setBrush(grad)
            p.drawRoundedRect(fill, radius, radius)


class VolumeSlider(QSlider):
    """0-100 slider. Clicking the track jumps straight to that spot."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 100)
        self.setSingleStep(1)
        self.setPageStep(5)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("muted", False)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            handle = 18
            x = event.position().x()
            span = max(1, self.width() - handle)
            value = round((x - handle / 2) / span * 100)
            self.setValue(max(0, min(100, value)))
        super().mousePressEvent(event)

    def set_muted_look(self, muted: bool) -> None:
        if self.property("muted") != muted:
            self.setProperty("muted", muted)
            self.style().unpolish(self)
            self.style().polish(self)

    def set_value_quietly(self, value: int) -> None:
        """Update from the system without echoing the change back to it."""
        if self.isSliderDown() or self.value() == value:
            return
        self.blockSignals(True)
        self.setValue(value)
        self.blockSignals(False)


def icon_button(tooltip: str, size: int = 20) -> QToolButton:
    btn = QToolButton()
    btn.setObjectName("IconButton")
    btn.setToolTip(tooltip)
    btn.setIconSize(QSize(size, size))
    btn.setCursor(Qt.PointingHandCursor)
    btn.setAutoRaise(True)
    return btn


class VolumeRow(QFrame):
    """One line in a list: icon, name, slider, %, mute and optional extras."""

    volumeChanged = Signal(str, int)
    muteToggled = Signal(str, bool)
    makeDefault = Signal(str)

    def __init__(self, key: str, icon: QIcon, is_input: bool = False, can_default: bool = False):
        super().__init__()
        self.key = key
        self.is_input = is_input
        self._muted = False
        self.setObjectName("Row")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(32, 32)
        self.set_icon(icon)

        self.title = ElidedLabel()
        self.title.setObjectName("RowTitle")
        self.subtitle = ElidedLabel()
        self.subtitle.setObjectName("RowSubtitle")
        self.subtitle.hide()

        self.badge = QLabel("DEFAULT")
        self.badge.setObjectName("Badge")
        self.badge.hide()
        self.default_btn = QPushButton("Set default")
        self.default_btn.setObjectName("Ghost")
        self.default_btn.setCursor(Qt.PointingHandCursor)
        self.default_btn.setToolTip("Make this the Windows default device")
        self.default_btn.clicked.connect(lambda: self.makeDefault.emit(self.key))
        self.default_btn.hide()
        self._can_default = can_default

        self.mute_btn = icon_button("Mute", 18)
        self.mute_btn.clicked.connect(self._on_mute_clicked)

        self.slider = VolumeSlider()
        self.slider.valueChanged.connect(self._on_slider)
        self.percent = QLabel("0")
        self.percent.setObjectName("Percent")
        self.percent.setFixedWidth(30)
        self.percent.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.meter = LevelMeter(3)

        # layout -----------------------------------------------------------
        head = QHBoxLayout()
        head.setSpacing(8)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(self.title)
        names.addWidget(self.subtitle)
        head.addLayout(names, 1)
        head.addWidget(self.badge, 0, Qt.AlignVCenter)
        head.addWidget(self.default_btn, 0, Qt.AlignVCenter)

        slider_col = QVBoxLayout()
        slider_col.setSpacing(5)
        slider_col.setContentsMargins(0, 6, 0, 0)
        slider_col.addWidget(self.slider)
        slider_col.addWidget(self.meter)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self.mute_btn, 0, Qt.AlignTop)
        controls.addLayout(slider_col, 1)
        controls.addWidget(self.percent, 0, Qt.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(2)
        right.addLayout(head)
        right.addLayout(controls)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 8)
        outer.setSpacing(12)
        outer.addWidget(self.icon_label, 0, Qt.AlignTop)
        outer.addLayout(right, 1)

    # ------------------------------------------------------------------
    def set_icon(self, icon: QIcon) -> None:
        self.icon_label.setPixmap(icon.pixmap(QSize(32, 32)))

    def set_state(
        self,
        title: str,
        volume: int,
        muted: bool,
        subtitle: str = "",
        is_default: bool = False,
    ) -> None:
        self.title.set_full_text(title)
        if subtitle:
            self.subtitle.set_full_text(subtitle)
            self.subtitle.show()
        else:
            self.subtitle.hide()

        self.badge.setVisible(is_default)
        self.default_btn.setVisible(self._can_default and not is_default)

        self.slider.set_value_quietly(volume)
        self._show_volume(self.slider.value(), muted)

    def _show_volume(self, volume: int, muted: bool) -> None:
        self._muted = muted
        self.percent.setText(str(volume))
        self.slider.set_muted_look(muted)
        if self.is_input:
            self.mute_btn.setIcon(icons.microphone(18, muted))
        else:
            self.mute_btn.setIcon(icons.speaker_for(volume, muted, 18))
        self.mute_btn.setToolTip("Unmute" if muted else "Mute")

    def _on_slider(self, value: int) -> None:
        self._show_volume(value, self._muted)
        self.volumeChanged.emit(self.key, value)

    def _on_mute_clicked(self) -> None:
        self._show_volume(self.slider.value(), not self._muted)
        self.muteToggled.emit(self.key, self._muted)


class MasterCard(QFrame):
    """The always-visible master volume at the top of the window."""

    volumeChanged = Signal(int)
    muteToggled = Signal(bool)
    pinToggled = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("MasterCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._muted = False
        self._has_device = True

        eyebrow = QLabel("MASTER VOLUME")
        eyebrow.setObjectName("Eyebrow")
        self.device = ElidedLabel("Default output")
        self.device.setObjectName("MasterDevice")

        self.percent = QLabel("0")
        self.percent.setObjectName("MasterPercent")
        self.percent.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.pin_btn = icon_button("Keep on top of other windows", 18)
        self.pin_btn.setCheckable(True)
        self.pin_btn.setIcon(icons.pin(18, False))
        self.pin_btn.toggled.connect(self._on_pin)

        self.mute_btn = icon_button("Mute", 24)
        self.mute_btn.setFixedSize(40, 40)
        self.mute_btn.clicked.connect(self._on_mute_clicked)

        self.slider = VolumeSlider()
        self.slider.setObjectName("MasterSlider")
        self.slider.valueChanged.connect(self._on_slider)
        self.meter = LevelMeter(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(eyebrow, 1, Qt.AlignVCenter)
        top.addWidget(self.pin_btn, 0, Qt.AlignVCenter)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(self.device, 1, Qt.AlignBottom)
        name_row.addWidget(self.percent, 0, Qt.AlignBottom)

        slider_col = QVBoxLayout()
        slider_col.setSpacing(8)
        slider_col.setContentsMargins(0, 8, 0, 0)
        slider_col.addWidget(self.slider)
        slider_col.addWidget(self.meter)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(self.mute_btn, 0, Qt.AlignTop)
        controls.addLayout(slider_col, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(4)
        lay.addLayout(top)
        lay.addLayout(name_row)
        lay.addSpacing(6)
        lay.addLayout(controls)

    # ------------------------------------------------------------------
    def set_device(self, name: str | None, volume: int = 0, muted: bool = False) -> None:
        self._has_device = name is not None
        self.slider.setEnabled(self._has_device)
        self.mute_btn.setEnabled(self._has_device)
        if name is None:
            self.device.set_full_text("No output device")
            self.percent.setText("–")
            self.meter.set_level(0)
            return
        self.device.set_full_text(name)
        self.slider.set_value_quietly(volume)
        self._show_volume(self.slider.value(), muted)

    def set_pinned(self, pinned: bool) -> None:
        self.pin_btn.blockSignals(True)
        self.pin_btn.setChecked(pinned)
        self.pin_btn.blockSignals(False)
        self.pin_btn.setIcon(icons.pin(18, pinned))

    def _show_volume(self, volume: int, muted: bool) -> None:
        self._muted = muted
        self.percent.setText(str(volume))
        self.slider.set_muted_look(muted)
        self.mute_btn.setIcon(icons.speaker_for(volume, muted, 24))
        self.mute_btn.setToolTip("Unmute" if muted else "Mute")

    def _on_slider(self, value: int) -> None:
        self._show_volume(value, self._muted)
        self.volumeChanged.emit(value)

    def _on_mute_clicked(self) -> None:
        self._show_volume(self.slider.value(), not self._muted)
        self.muteToggled.emit(self._muted)

    def _on_pin(self, on: bool) -> None:
        self.pin_btn.setIcon(icons.pin(18, on))
        self.pinToggled.emit(on)


class ListPanel(QWidget):
    """A vertical list of rows that is kept in sync with the system.

    Rows are reused between refreshes (so a slider being dragged is never
    destroyed), new ones are added and vanished ones removed.
    """

    def __init__(self, empty_text: str):
        super().__init__()
        self.rows: dict[str, VolumeRow] = {}
        self._order: list[object] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 4, 0, 8)
        self._layout.setSpacing(2)
        self._empty = QLabel(empty_text)
        self._empty.setObjectName("Empty")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True)
        self._layout.addWidget(self._empty)
        self._layout.addStretch(1)
        self._sections: dict[str, QLabel] = {}

    def section(self, title: str) -> QLabel:
        label = self._sections.get(title)
        if label is None:
            label = QLabel(title.upper())
            label.setObjectName("Section")
            self._sections[title] = label
        return label

    def arrange(self, items: list[object]) -> None:
        """Lay out ``items`` (rows and section labels) in this exact order."""
        live_rows = {w for w in items if isinstance(w, VolumeRow)}
        for key, row in list(self.rows.items()):
            if row not in live_rows:
                self._layout.removeWidget(row)
                row.deleteLater()
                del self.rows[key]
        for title, label in list(self._sections.items()):
            if label not in items:
                self._layout.removeWidget(label)
                label.hide()

        self._empty.setVisible(not live_rows)
        if items == self._order:
            return
        for w in self._order:
            if w in items:
                self._layout.removeWidget(w)
        for i, w in enumerate(items):
            self._layout.insertWidget(1 + i, w)  # index 0 is the empty label
            w.show()
        self._order = list(items)
