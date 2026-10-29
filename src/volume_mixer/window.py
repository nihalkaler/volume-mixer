"""The desktop widget: a borderless, see-through panel with the master volume
on top and Devices / Apps tabs below. Behaves like the World Clock Widget:
drag it anywhere, lock it, keep it on the desktop / normal / always on top,
no taskbar button, tray icon, and one right-click menu for everything."""

from __future__ import annotations

import logging
import math
import random

from PySide6.QtCore import QFileInfo, QFileSystemWatcher, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QActionGroup,
    QColor,
    QCursor,
    QGuiApplication,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, desktop, icons, theme
from .config import LAYER_NAMES, LAYERS, MODE_NAMES, MODES, Config, ConfigStore
from .dials import DialsView
from .models import INPUT, OUTPUT, AppInfo, AudioBackend, DeviceInfo
from .theme import px
from .widgets import ListPanel, MasterCard, VolumeRow

log = logging.getLogger(__name__)

REFRESH_MS = 1000  # how often devices and apps are re-read
METER_MS = 50  # level meters, about 20 frames a second
SAVE_POSITION_MS = 600

TAB_DEVICES = 0
TAB_APPS = 1
TAB_KEYS = ("devices", "apps")

PANEL_WIDTH = 330  # at normal size
DIALS_WIDTH = 340  # the Extra small (dials) view, at its own scale
MAX_LIST_HEIGHT = 300  # rows beyond this scroll
SCREEN_GAP = 24  # gap from the screen edge on first launch


def _draw_screw(painter: QPainter, centre: QPointF, radius: float, angle: float) -> None:
    """A small countersunk slotted screw head."""
    head = QRadialGradient(centre - QPointF(radius * 0.35, radius * 0.35), radius * 1.4)
    head.setColorAt(0, QColor(214, 218, 222))
    head.setColorAt(1, QColor(92, 97, 102))
    painter.setPen(QPen(QColor(0, 0, 0, 120), max(0.8, radius * 0.18)))
    painter.setBrush(head)
    painter.drawEllipse(centre, radius, radius)
    rad = math.radians(angle)
    dx, dy = math.cos(rad) * radius * 0.72, math.sin(rad) * radius * 0.72
    painter.setPen(QPen(QColor(40, 42, 45), max(0.8, radius * 0.32), Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(centre - QPointF(dx, dy), centre + QPointF(dx, dy))


def _chamfered(r: QRectF, big: float, small: float) -> QPainterPath:
    """The clock's cut-corner panel: big cuts top-left and bottom-right."""
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    path = QPainterPath()
    path.moveTo(x + big, y)
    path.lineTo(x + w - small, y)
    path.lineTo(x + w, y + small)
    path.lineTo(x + w, y + h - big)
    path.lineTo(x + w - big, y + h)
    path.lineTo(x + small, y + h)
    path.lineTo(x, y + h - small)
    path.lineTo(x, y + big)
    path.closeSubpath()
    return path


class MixerWindow(QWidget):
    def __init__(self, backend: AudioBackend, store: ConfigStore | None = None, demo: bool = False):
        super().__init__()
        self.backend = backend
        self.store = store or ConfigStore()
        if store is None:
            self.store.load()
        self.demo = demo
        self._quitting = False
        self._master_id: str | None = None
        self._master_volume: int | None = None
        self._icon_provider = QFileIconProvider()
        self._app_icons: dict[str, QIcon] = {}
        self._drag_offset: QPoint | None = None
        self._last_error: str | None = None
        self._content: QWidget | None = None
        self._panel_cache: tuple | None = None
        self.dials: DialsView | None = None
        self.margin = 0

        self.setWindowTitle(APP_NAME + (" (demo)" if demo else ""))
        self.setWindowIcon(QApplication.windowIcon())
        # Borderless, no taskbar button, see-through around the panel.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_AlwaysShowToolTips)
        self.layer = desktop.DesktopLayer(self)

        self._root = QVBoxLayout(self)
        self._root.setSpacing(0)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.meter_timer = QTimer(self)
        self.meter_timer.timeout.connect(self.update_meters)
        self._save_pos_timer = QTimer(self, singleShot=True, interval=SAVE_POSITION_MS)
        self._save_pos_timer.timeout.connect(self._save_position)

        self._build()
        self._place_initially()
        self._setup_tray()
        self._watch_settings()
        self.refresh_timer.start(REFRESH_MS)
        self.meter_timer.start(METER_MS)

    # ------------------------------------------------------------------
    # building (and rebuilding when the theme or size changes)
    # ------------------------------------------------------------------
    @property
    def cfg(self) -> Config:
        return self.store.config

    def _palette(self) -> theme.Palette:
        pal = theme.PALETTES[self.cfg.theme]
        if self.cfg.accent:
            pal = pal.with_accent(QColor(self.cfg.accent))
        return pal

    def _build(self) -> None:
        use_dials = self.cfg.mode == "dials"
        theme.use(self._palette(), theme.scale_for(self.cfg.dial_size if use_dials else self.cfg.size))
        self.margin = px(14)  # room for the soft shadow round the panel
        pad = px(14)
        bottom = px(13) if theme.P.console else px(10)  # clear of the screws
        self._root.setContentsMargins(self.margin + pad, self.margin + px(12), self.margin + pad, self.margin + bottom)

        if self._content is not None:
            self._root.removeWidget(self._content)
            self._content.deleteLater()
        self._app_icons.clear()

        content = QWidget(self)
        content.setStyleSheet(theme.stylesheet())
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        if use_dials:
            self.dials = DialsView(self.cfg.dial_device, self.cfg.dial_app)
            self.dials.deviceVolume.connect(self._set_device_volume)
            self.dials.deviceMute.connect(self._set_device_mute)
            self.dials.appVolume.connect(self._set_app_volume)
            self.dials.appMute.connect(self._set_app_mute)
            self.dials.deviceChosen.connect(self._remember_dial_device)
            self.dials.appChosen.connect(self._remember_dial_app)
            self.dials.expandRequested.connect(lambda: self.set_mode("default"))
            lay.addWidget(self.dials)
            self._root.addWidget(content)
            self._content = content
            self.refresh()
            self.update()
            return
        self.dials = None

        self.master = MasterCard()
        self.master.volumeChanged.connect(self._set_master_volume)
        self.master.muteToggled.connect(self._set_master_mute)
        self.master.collapseToggled.connect(self.set_compact)
        self.master.dialsRequested.connect(lambda: self.set_mode("dials"))

        self.lists = QWidget()
        lists_lay = QVBoxLayout(self.lists)
        lists_lay.setContentsMargins(0, px(12), 0, 0)
        lists_lay.setSpacing(px(6))

        seg = QFrame()
        seg.setObjectName("Segmented")
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(px(2), px(2), px(2), px(2))
        seg_lay.setSpacing(px(2))
        self.tab_buttons = QButtonGroup(content)
        self.devices_tab_btn = self._segment("Devices")
        self.apps_tab_btn = self._segment("Apps")
        for i, btn in enumerate((self.devices_tab_btn, self.apps_tab_btn)):
            self.tab_buttons.addButton(btn, i)
            seg_lay.addWidget(btn, 1)
        self.tab_buttons.idClicked.connect(self.show_tab)

        self.devices_panel = ListPanel("No audio devices are connected.")
        self.apps_panel = ListPanel("No apps are using sound right now.")
        self.pages = QStackedWidget()
        self._scrolls: list[QScrollArea] = []
        for panel in (self.devices_panel, self.apps_panel):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.viewport().setAutoFillBackground(False)
            scroll.setWidget(panel)
            self.pages.addWidget(scroll)
            self._scrolls.append(scroll)

        lists_lay.addWidget(seg)
        lists_lay.addWidget(self.pages)

        lay.addWidget(self.master)
        lay.addWidget(self.lists)
        self._root.addWidget(content)
        self._content = content

        self.master.set_collapsed(self.cfg.compact)
        self.lists.setVisible(not self.cfg.compact)
        index = TAB_KEYS.index(self.cfg.tab)
        self.pages.setCurrentIndex(index)
        self.tab_buttons.button(index).setChecked(True)

        self.refresh()
        self.update()

    def _segment(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("Segment")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        return btn

    # ------------------------------------------------------------------
    # size and position
    # ------------------------------------------------------------------
    def _fit(self) -> None:
        """Size the widget to its contents (lists scroll past a maximum)."""
        if self.dials is None and not self.cfg.compact:
            panel = (self.devices_panel, self.apps_panel)[self.pages.currentIndex()]
            want = min(panel.content_height(), px(MAX_LIST_HEIGHT))
            if self.pages.height() != want or self.pages.minimumHeight() != want:
                self.pages.setFixedHeight(want)
        # Recalculate now rather than on the next event-loop pass, so showing
        # or hiding the lists resizes the widget straight away.
        layouts = [self._content.layout(), self._root]
        if self.dials is None:
            layouts.insert(0, self.lists.layout())
        for layout in layouts:
            layout.invalidate()
            layout.activate()
        width = px(DIALS_WIDTH if self.dials is not None else PANEL_WIDTH) + 2 * self.margin
        height = self._root.sizeHint().height()
        size = QSize(width, height)
        if size == self.size() and self.minimumSize() == size:
            return
        old = self.frameGeometry()
        self.setFixedSize(size)
        if self.isVisible() and self._anchored_bottom(old):
            # In the lower half of the screen the bottom edge stays put, so the
            # widget grows upwards instead of off the screen.
            self.move(old.x(), old.bottom() + 1 - height)
        self._keep_on_screen()

    def _anchored_bottom(self, geo: QRect) -> bool:
        screen = QGuiApplication.screenAt(geo.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return False
        return geo.center().y() > screen.availableGeometry().center().y()

    def _place_initially(self) -> None:
        self._fit()
        if self.cfg.x is not None and self.cfg.y is not None:
            self.move(self.cfg.x, self.cfg.y)
            if self._keep_on_screen(reset_if_lost=True):
                return
        self.move(self._default_position())

    def _default_position(self) -> QPoint:
        """Bottom-right of the main screen, near the Windows volume icon."""
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)
        gap = SCREEN_GAP - self.margin
        return QPoint(area.right() + 1 - self.width() - gap, area.bottom() + 1 - self.height() - gap)

    def _keep_on_screen(self, reset_if_lost: bool = False) -> bool:
        """Pull the widget back onto a screen. Returns False if it was lost."""
        geo = self.frameGeometry()
        screens = QGuiApplication.screens()
        if not screens:
            return True
        best = max(screens, key=lambda s: s.availableGeometry().intersected(geo).width()
                   * s.availableGeometry().intersected(geo).height())
        area = best.availableGeometry()
        visible = area.intersected(geo)
        if visible.width() < px(60) or visible.height() < px(40):
            if reset_if_lost:
                return False
        m = self.margin
        x = min(max(geo.x(), area.left() - m), area.right() + 1 - geo.width() + m)
        y = min(max(geo.y(), area.top() - m), area.bottom() + 1 - geo.height() + m)
        if (x, y) != (geo.x(), geo.y()):
            self.move(x, y)
        return True

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self._save_pos_timer.start()

    def _save_position(self) -> None:
        pos = self.pos()
        if (self.cfg.x, self.cfg.y) != (pos.x(), pos.y()):
            self.cfg.x, self.cfg.y = pos.x(), pos.y()
            self.store.save()

    # ------------------------------------------------------------------
    # drawing the panel
    # ------------------------------------------------------------------
    def _panel_path(self, r: QRectF) -> QPainterPath:
        p = theme.P
        if p.tactical:
            return _chamfered(r, px(10), px(10))
        if p.hud:
            return _chamfered(r, px(16), px(5))
        path = QPainterPath()
        radius = px(6) if p.console else px(16)
        path.addRoundedRect(r, radius, radius)
        return path

    def paintEvent(self, _event) -> None:  # noqa: N802
        # The panel only changes with the theme, size or opacity, so it's drawn
        # once into an image. The level meters repaint 20 times a second, and
        # each repaint only copies the image instead of redrawing the panel.
        dpr = self.devicePixelRatioF()
        key = (self.size().width(), self.size().height(), dpr, theme.P, theme.S, self.cfg.opacity, self.margin)
        if self._panel_cache is None or self._panel_cache[0] != key:
            image = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
            image.setDevicePixelRatio(dpr)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            self._draw_panel(painter)
            painter.end()
            self._panel_cache = (key, image)
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._panel_cache[1])

    def _draw_panel(self, painter: QPainter) -> None:
        p = theme.P
        s = theme.S
        painter.setRenderHint(QPainter.Antialiasing)
        m = self.margin
        r = QRectF(self.rect()).adjusted(m + 0.5, m + 0.5, -m - 0.5, -m - 0.5)

        # Soft shadow so the panel lifts off any wallpaper.
        painter.setPen(Qt.NoPen)
        steps = max(4, m - 2)
        strength = 0.022 if p.name == "light" else 0.04
        for i in range(steps, 0, -1):
            alpha = strength * (1 - i / (steps + 1))
            painter.setBrush(QColor(0, 0, 0, round(alpha * 255)))
            grow = i * 0.9
            painter.drawPath(self._panel_path(r.adjusted(-grow, -grow + 2 * s, grow, grow + 2 * s)))

        path = self._panel_path(r)
        top = QColor(p.panel)
        top.setAlphaF(self.cfg.opacity)
        if p.panel2 is not None:
            bottom = QColor(p.panel2)
            bottom.setAlphaF(self.cfg.opacity)
            grad = QLinearGradient(r.topLeft(), r.bottomLeft())
            grad.setColorAt(0, top)
            grad.setColorAt(1, bottom)
            painter.setBrush(grad)
        else:
            painter.setBrush(top)
        painter.drawPath(path)

        painter.save()
        painter.setClipPath(path)
        if p.tactical:  # faint diagonal hatching
            painter.setPen(QPen(QColor(216, 198, 154, 9), max(1.0, s)))
            step = 7 * max(0.6, s)
            x = r.left() - r.height()
            while x < r.right():
                painter.drawLine(QPointF(x, r.bottom()), QPointF(x + r.height(), r.top()))
                x += step
        elif p.hud:  # faint scanlines
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 7))
            y = r.top() + 2 * s
            while y < r.bottom():
                painter.drawRect(QRectF(r.left(), y, r.width(), max(1.0, s)))
                y += 3 * max(1.0, s)
        elif p.console:  # brushed metal: fine horizontal streaks
            rng = random.Random(7)  # same streaks every time
            y = r.top()
            while y < r.bottom():
                light = rng.random() < 0.5
                alpha = rng.randint(3, 9)
                painter.setPen(QPen(QColor(255, 255, 255, alpha) if light else QColor(0, 0, 0, alpha + 4), 1))
                x0 = r.left() + rng.random() * r.width() * 0.3
                x1 = r.right() - rng.random() * r.width() * 0.3
                painter.drawLine(QPointF(x0, y), QPointF(x1, y))
                y += 1.0 + rng.random() * 1.6
            # a light catch along the top edge
            shine = QLinearGradient(r.topLeft(), r.topLeft() + QPointF(0, 26 * s))
            shine.setColorAt(0, QColor(255, 255, 255, 16))
            shine.setColorAt(1, QColor(255, 255, 255, 0))
            painter.fillRect(r, shine)
        painter.restore()

        border = p.border
        brush = QLinearGradient(r.topLeft(), r.topRight())
        brush.setColorAt(0, border)
        brush.setColorAt(1, p.border2 or border)
        painter.setBrush(Qt.NoBrush)
        if p.glow:
            for spread, alpha in ((4.0, 0.08), (2.2, 0.16)):
                glow = QLinearGradient(r.topLeft(), r.topRight())
                c1, c2 = QColor(border), QColor(p.border2 or border)
                c1.setAlphaF(alpha)
                c2.setAlphaF(alpha)
                glow.setColorAt(0, c1)
                glow.setColorAt(1, c2)
                painter.setPen(QPen(glow, 1.2 * s * spread))
                painter.drawPath(path)
        painter.setPen(QPen(brush, 1.4 * s if p.hud else max(1.0, s)))
        painter.drawPath(path)

        if p.tactical:  # corner brackets, like the marks on a rangefinder
            inset, arm = 6 * s, 11 * s
            pen = QPen(p.accent, 1.8 * s)
            pen.setCapStyle(Qt.FlatCap)
            painter.setPen(pen)
            for cx, cy, dx, dy in (
                (r.left() + inset, r.top() + inset, 1, 1),
                (r.right() - inset, r.top() + inset, -1, 1),
                (r.left() + inset, r.bottom() - inset, 1, -1),
                (r.right() - inset, r.bottom() - inset, -1, -1),
            ):
                painter.drawPolyline([QPointF(cx, cy + arm * dy), QPointF(cx, cy), QPointF(cx + arm * dx, cy)])
        elif p.hud:  # thick tabs on the top-left and bottom-right edges
            for x0, y, x1, color in (
                (r.left() + 20 * s, r.top() + 1.1 * s, r.left() + 62 * s, p.border),
                (r.right() - 62 * s, r.bottom() - 1.1 * s, r.right() - 20 * s, p.border2 or p.border),
            ):
                for width, alpha in ((7.0, 0.12), (3.0, 1.0)):
                    c = QColor(color)
                    c.setAlphaF(alpha * color.alphaF())
                    painter.setPen(QPen(c, width * s, Qt.SolidLine, Qt.RoundCap))
                    painter.drawLine(QPointF(x0, y), QPointF(x1, y))
        elif p.console:  # a screw in each corner, slots turned every which way
            inset, radius = 7 * s, 3.0 * s
            for i, (cx, cy) in enumerate((
                (r.left() + inset, r.top() + inset),
                (r.right() - inset, r.top() + inset),
                (r.left() + inset, r.bottom() - inset),
                (r.right() - inset, r.bottom() - inset),
            )):
                _draw_screw(painter, QPointF(cx, cy), radius, angle=(25, 110, 160, 65)[i])

    # ------------------------------------------------------------------
    # mouse: drag to move, right-click for the menu
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and not self.cfg.locked:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self.setCursor(Qt.SizeAllCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.button() == Qt.LeftButton:
            self._drag_offset = None
            self.unsetCursor()
            self._keep_on_screen()
            self._save_position()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self.menu.popup(event.globalPos())

    def nativeEvent(self, event_type, message):  # noqa: N802
        handled = self.layer.native_event(message)
        if handled is not None:
            return handled
        return False, 0

    def closeEvent(self, event) -> None:  # noqa: N802
        # Alt+F4 and the like don't close a widget; use Exit in the menu.
        if self._quitting:
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------------------
    # menu and tray
    # ------------------------------------------------------------------
    def _setup_tray(self) -> None:
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._fill_menu)
        self._fill_menu()
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(APP_NAME)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            # Like the clock: clicking the tray icon opens the menu, which
            # also works when the widget is hidden behind other windows.
            self.menu.popup(QCursor.pos())

    def _fill_menu(self) -> None:
        m = self.menu
        m.clear()
        cfg = self.cfg

        m.addAction("Bring the widget forward", self.bring_forward)
        m.addSeparator()

        def choices(title, options, current, setter):
            sub = m.addMenu(title)
            group = QActionGroup(sub)
            for value, label in options:
                act = sub.addAction(label)
                act.setCheckable(True)
                act.setChecked(value == current)
                group.addAction(act)
                act.triggered.connect(lambda _=False, v=value: setter(v))

        dials = cfg.mode == "dials"
        choices("Mode", [(mode, MODE_NAMES[mode]) for mode in MODES], cfg.mode, self.set_mode)
        # Each mode has its own sizes, and remembers its own choice.
        choices("Size", theme.DIAL_SIZES if dials else theme.SIZES, cfg.dial_size if dials else cfg.size, self.set_size)
        compact = m.addAction("Master volume only")
        compact.setCheckable(True)
        compact.setChecked(cfg.compact)
        compact.setEnabled(not dials)
        compact.toggled.connect(self.set_compact)
        m.addSeparator()
        choices("Theme", [(t, theme.THEME_NAMES[t]) for t in theme.THEMES], cfg.theme, self.set_theme)
        choices("Placement", [(layer, LAYER_NAMES[layer]) for layer in LAYERS], cfg.layer, self.set_layer)

        lock = m.addAction("Lock position")
        lock.setCheckable(True)
        lock.setChecked(cfg.locked)
        lock.toggled.connect(self.set_locked)

        auto = m.addAction("Start with Windows")
        auto.setCheckable(True)
        auto.setEnabled(desktop.autostart_supported())
        auto.setChecked(desktop.autostart_enabled())
        auto.toggled.connect(self.set_autostart)

        m.addSeparator()
        sound = m.addAction("Windows sound settings…", desktop.open_sound_settings)
        sound.setEnabled(desktop.IS_WINDOWS)
        m.addAction("Edit settings file…", lambda: desktop.open_in_editor(self.store.path))
        m.addSeparator()
        m.addAction("Exit", self.quit)

    # ------------------------------------------------------------------
    # settings (menu actions, and changes made in the settings file)
    # ------------------------------------------------------------------
    def _change(self, **values) -> None:
        old = Config(**{k: getattr(self.cfg, k) for k in Config.__dataclass_fields__})
        for key, value in values.items():
            setattr(self.cfg, key, value)
        self.store.save()
        self.apply_config(old)

    def set_mode(self, mode: str) -> None:
        """"default" (the full mixer) or "dials"."""
        self._change(mode=mode)

    def set_size(self, size: int) -> None:
        """Size for whichever mode is showing; the other mode keeps its own."""
        if self.cfg.mode == "dials":
            self._change(dial_size=int(size))
        else:
            self._change(size=int(size))

    def _remember_dial_device(self, choice: str) -> None:
        self.cfg.dial_device = choice
        self.store.save()

    def _remember_dial_app(self, choice: str) -> None:
        self.cfg.dial_app = choice
        self.store.save()

    def set_theme(self, name: str) -> None:
        self._change(theme=name)

    def set_layer(self, layer: str) -> None:
        self._change(layer=layer)

    def set_locked(self, locked: bool) -> None:
        self._change(locked=locked)

    def set_compact(self, compact: bool) -> None:
        self._change(compact=compact)

    def set_autostart(self, enabled: bool) -> None:
        try:
            desktop.set_autostart(enabled)
        except OSError as exc:
            QMessageBox.warning(None, APP_NAME, f"Couldn't change Start with Windows:\n{exc}")

    def show_tab(self, index: int) -> None:
        if TAB_KEYS[index] != self.cfg.tab:
            self._change(tab=TAB_KEYS[index])
        elif self.dials is None:
            self.pages.setCurrentIndex(index)
            self.tab_buttons.button(index).setChecked(True)

    def apply_config(self, old: Config) -> None:
        new = self.cfg
        looks = ("theme", "size", "dial_size", "accent", "mode")
        if any(getattr(new, k) != getattr(old, k) for k in looks):
            self._build()
        if new.opacity != old.opacity:
            self.update()
        if self.dials is None:
            if new.compact != old.compact:
                self.master.set_collapsed(new.compact)
                self.lists.setVisible(not new.compact)
            if new.tab != old.tab:
                index = TAB_KEYS.index(new.tab)
                self.pages.setCurrentIndex(index)
                self.tab_buttons.button(index).setChecked(True)
        elif (new.dial_device, new.dial_app) != (old.dial_device, old.dial_app):
            self.dials.set_choices(new.dial_device, new.dial_app)
            self.refresh()
        if new.layer != old.layer and self.isVisible():
            self.layer.apply(new.layer)
        self._fit()
        if (new.x, new.y) != (old.x, old.y) and new.x is not None and new.y is not None:
            if (new.x, new.y) != (self.x(), self.y()):
                self.move(new.x, new.y)
                self._keep_on_screen()

    def _watch_settings(self) -> None:
        self._watcher = QFileSystemWatcher(self)
        self._reload_timer = QTimer(self, singleShot=True, interval=300)
        self._reload_timer.timeout.connect(self._reload_settings)
        self._watcher.fileChanged.connect(lambda _path: self._reload_timer.start())
        self._watcher.directoryChanged.connect(lambda _path: self._reload_timer.start())
        if self.store.path.parent.exists():
            self._watcher.addPath(str(self.store.path.parent))
        if self.store.path.exists():
            self._watcher.addPath(str(self.store.path))

    def _reload_settings(self) -> None:
        # Editors often replace the file when saving, so watch it again.
        if self.store.path.exists() and str(self.store.path) not in self._watcher.files():
            self._watcher.addPath(str(self.store.path))
        old = Config(**{k: getattr(self.cfg, k) for k in Config.__dataclass_fields__})
        error = self.store.load()
        if error:
            if error != self._last_error:
                self._last_error = error
                box = QMessageBox(QMessageBox.Warning, APP_NAME, error)
                box.setAttribute(Qt.WA_DeleteOnClose)
                box.show()
            return
        self._last_error = None
        self.apply_config(old)

    # ------------------------------------------------------------------
    # showing and quitting
    # ------------------------------------------------------------------
    def show_widget(self) -> None:
        self.show()
        self.layer.apply(self.cfg.layer)

    def show_and_raise(self) -> None:
        """Called when the app is launched a second time."""
        self.show_widget()
        self.bring_forward()

    def bring_forward(self) -> None:
        if not self.isVisible():
            self.show_widget()
        self.layer.bring_forward()

    def quit(self) -> None:
        self._quitting = True
        self._save_position()
        self.refresh_timer.stop()
        self.meter_timer.stop()
        self.layer.close()
        if self.tray is not None:
            self.tray.hide()
        self.close()
        QApplication.quit()

    # ------------------------------------------------------------------
    # pulling state from the system
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        try:
            devices = self.backend.list_devices()
        except Exception:  # never let one bad poll crash the widget
            log.exception("Could not list devices")
            devices = []
        master = next((d for d in devices if d.flow == OUTPUT and d.is_default), None)
        if master is None:
            try:
                master = self.backend.default_output()
            except Exception:
                log.exception("Could not read the default output")
        self._master_id = master.id if master else None
        if self.dials is not None:
            try:
                apps = self.backend.list_apps()
            except Exception:
                log.exception("Could not list apps")
                apps = []
            self.dials.update_state(devices, apps, self._icon_for)
            self._update_tray_tooltip(master)
            self._fit()
            return
        if master:
            self.master.set_device(master.name, master.volume, master.muted)
        else:
            self.master.set_device(None)
        self._sync_devices(devices)

        try:
            apps = self.backend.list_apps()
        except Exception:
            log.exception("Could not list apps")
            apps = []
        self._sync_apps(apps)

        self.devices_tab_btn.setText(f"Devices  ·  {len(devices)}")
        self.apps_tab_btn.setText(f"Apps  ·  {len(apps)}")
        self._update_tray_tooltip(master)
        self._fit()

    def _update_tray_tooltip(self, master: DeviceInfo | None) -> None:
        tray = getattr(self, "tray", None)
        if tray is None:
            return
        if master is None:
            tip = f"{APP_NAME}: no output device"
        else:
            tip = f"{APP_NAME}: {'muted' if master.muted else f'{master.volume}%'} on {master.name}"
        if tray.toolTip() != tip:
            tray.setToolTip(tip[:127])

    def _sync_devices(self, devices: list[DeviceInfo]) -> None:
        panel = self.devices_panel
        items: list[object] = []
        for flow, title in ((OUTPUT, "Output"), (INPUT, "Input")):
            group = [d for d in devices if d.flow == flow]
            if not group:
                continue
            items.append(panel.section(title))
            group.sort(key=lambda d: (not d.is_default, d.name.lower()))
            for d in group:
                row = panel.rows.get(d.id)
                if row is None:
                    row = VolumeRow(d.id, icons.device_badge(px(28), d.flow == INPUT), d.flow == INPUT, True)
                    row.volumeChanged.connect(self._set_device_volume)
                    row.muteToggled.connect(self._set_device_mute)
                    row.makeDefault.connect(self._make_default)
                    panel.rows[d.id] = row
                row.set_state(d.name, d.volume, d.muted, is_default=d.is_default)
                items.append(row)
        panel.arrange(items)

    def _sync_apps(self, apps: list[AppInfo]) -> None:
        panel = self.apps_panel
        items: list[object] = []
        many_outputs = sum(1 for r in self.devices_panel.rows.values() if not r.is_input) > 1
        for a in apps:
            row = panel.rows.get(a.key)
            if row is None:
                row = VolumeRow(a.key, self._icon_for(a))
                row.volumeChanged.connect(self._set_app_volume)
                row.muteToggled.connect(self._set_app_mute)
                panel.rows[a.key] = row
            # Only say which device an app plays on when there's a choice.
            subtitle = "  ·  ".join(a.devices) if len(a.devices) > 1 or many_outputs else ""
            row.set_state(a.name, a.volume, a.muted, subtitle=subtitle)
            items.append(row)
        panel.arrange(items)

    def _icon_for(self, app: AppInfo) -> QIcon:
        size = px(28)
        if app.is_system:
            return icons.bell(size)
        cached = self._app_icons.get(app.key)
        if cached is not None:
            return cached
        icon = QIcon()
        if app.exe_path:
            icon = self._icon_provider.icon(QFileInfo(app.exe_path))
        if icon.isNull() or icon.pixmap(QSize(size, size)).isNull():
            icon = icons.letter_tile(size, app.name)
        self._app_icons[app.key] = icon
        return icon

    def update_meters(self) -> None:
        if not self.isVisible():
            return
        try:
            if self.dials is not None:
                self.dials.update_meters(self.backend.device_peak, self.backend.app_peak)
                return
            if self._master_id:
                self.master.meter.set_level(self.backend.device_peak(self._master_id))
            if self.cfg.compact:
                return
            if self.pages.currentIndex() == TAB_DEVICES:
                for key, row in self.devices_panel.rows.items():
                    row.meter.set_level(self.backend.device_peak(key))
            else:
                for key, row in self.apps_panel.rows.items():
                    row.meter.set_level(self.backend.app_peak(key))
        except Exception:
            log.exception("Could not read levels")

    # ------------------------------------------------------------------
    # pushing changes to the system
    # ------------------------------------------------------------------
    def _guard(self, what: str, fn, *args) -> None:
        try:
            fn(*args)
        except Exception:
            log.exception("Could not %s", what)

    def _set_master_volume(self, value: int) -> None:
        if self._master_id and self.dials is None:
            self._guard("set master volume", self.backend.set_device_volume, self._master_id, value)
            row = self.devices_panel.rows.get(self._master_id)
            if row:
                row.set_state(row.title.full_text(), value, row._muted, is_default=True)

    def _set_master_mute(self, muted: bool) -> None:
        if self._master_id:
            self._guard("mute master", self.backend.set_device_mute, self._master_id, muted)
            self.refresh()

    def _set_device_volume(self, device_id: str, value: int) -> None:
        self._guard("set device volume", self.backend.set_device_volume, device_id, value)
        if device_id == self._master_id and self.dials is None:
            self.master.set_device(self.master.device.full_text(), value, self.master._muted)

    def _set_device_mute(self, device_id: str, muted: bool) -> None:
        self._guard("mute device", self.backend.set_device_mute, device_id, muted)
        if device_id == self._master_id:
            self.refresh()

    def _make_default(self, device_id: str) -> None:
        self._guard("set the default device", self.backend.set_default_device, device_id)
        self.refresh()

    def _set_app_volume(self, key: str, value: int) -> None:
        self._guard("set app volume", self.backend.set_app_volume, key, value)

    def _set_app_mute(self, key: str, muted: bool) -> None:
        self._guard("mute app", self.backend.set_app_mute, key, muted)
