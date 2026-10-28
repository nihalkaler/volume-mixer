"""The main window: master volume on top, Devices / Apps tabs below."""

from __future__ import annotations

import logging

from PySide6.QtCore import QFileInfo, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, icons
from .models import INPUT, OUTPUT, AppInfo, AudioBackend, DeviceInfo
from .widgets import ListPanel, MasterCard, VolumeRow

log = logging.getLogger(__name__)

REFRESH_MS = 1000  # how often the device / app lists are re-read
METER_MS = 50  # how often the level meters move (~20 fps)

TAB_DEVICES = 0
TAB_APPS = 1


class MixerWindow(QWidget):
    def __init__(self, backend: AudioBackend, demo: bool = False):
        super().__init__()
        self.backend = backend
        self.settings = QSettings("VolumeMixer", "VolumeMixer")
        self._quitting = False
        self._master_id: str | None = None
        self._icon_provider = QFileIconProvider()
        self._app_icons: dict[str, QIcon] = {}

        self.setObjectName("Root")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle(APP_NAME + (" (demo)" if demo else ""))
        self.setWindowIcon(QApplication.windowIcon())
        self.setMinimumSize(360, 460)
        self.resize(420, 640)

        # ---- master ---------------------------------------------------
        self.master = MasterCard()
        self.master.volumeChanged.connect(self._set_master_volume)
        self.master.muteToggled.connect(self._set_master_mute)
        self.master.pinToggled.connect(self.set_pinned)

        # ---- tab switcher -----------------------------------------------
        seg = QFrame()
        seg.setObjectName("Segmented")
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(3, 3, 3, 3)
        seg_lay.setSpacing(3)
        self.tab_buttons = QButtonGroup(self)
        self.tab_buttons.setExclusive(True)
        self.devices_tab_btn = self._segment("Devices")
        self.apps_tab_btn = self._segment("Apps")
        for i, btn in enumerate((self.devices_tab_btn, self.apps_tab_btn)):
            self.tab_buttons.addButton(btn, i)
            seg_lay.addWidget(btn, 1)
        self.tab_buttons.idClicked.connect(self.show_tab)

        # ---- pages -------------------------------------------------------
        self.devices_panel = ListPanel("No audio devices are connected.")
        self.apps_panel = ListPanel(
            "No apps are using audio right now.\nStart playing something and it will appear here."
        )
        self.pages = QStackedWidget()
        for panel in (self.devices_panel, self.apps_panel):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setWidget(panel)
            self.pages.addWidget(scroll)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 10)
        root.setSpacing(12)
        root.addWidget(self.master)
        root.addWidget(seg)
        root.addWidget(self.pages, 1)

        # ---- timers ------------------------------------------------------
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.meter_timer = QTimer(self)
        self.meter_timer.timeout.connect(self.update_meters)

        self._restore_settings()
        self._setup_tray()
        self.refresh()
        self.refresh_timer.start(REFRESH_MS)
        self.meter_timer.start(METER_MS)

    # ------------------------------------------------------------------
    # setup helpers
    # ------------------------------------------------------------------
    def _segment(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("Segment")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    def _restore_settings(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        tab = int(self.settings.value("tab", TAB_DEVICES))
        self.show_tab(tab if tab in (TAB_DEVICES, TAB_APPS) else TAB_DEVICES)
        pinned = self.settings.value("pinned", False)
        pinned = pinned in (True, "true", "1", 1)
        self.master.set_pinned(pinned)
        if pinned:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    def _setup_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction("Open " + APP_NAME, self.show_and_raise)
        self.tray_pin_action = QAction("Always on top", menu, checkable=True)
        self.tray_pin_action.setChecked(self.master.pin_btn.isChecked())
        self.tray_pin_action.toggled.connect(self.set_pinned)
        menu.addAction(self.tray_pin_action)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self._tray_menu = menu  # keep a reference so it isn't garbage collected
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # ------------------------------------------------------------------
    # window behaviour
    # ------------------------------------------------------------------
    def show_tab(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        btn = self.tab_buttons.button(index)
        if btn is not None:
            btn.setChecked(True)
        self.settings.setValue("tab", index)

    def set_pinned(self, pinned: bool) -> None:
        self.master.set_pinned(pinned)
        if getattr(self, "tray", None) is not None:
            self.tray_pin_action.blockSignals(True)
            self.tray_pin_action.setChecked(pinned)
            self.tray_pin_action.blockSignals(False)
        self.settings.setValue("pinned", pinned)
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, pinned)
        if visible:
            self.show()  # changing window flags hides the window

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_and_raise()

    def quit(self) -> None:
        self._quitting = True
        self.close()
        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.settings.setValue("geometry", self.saveGeometry())
        if self.tray is not None and not self._quitting:
            # Keep running in the tray so the controls are one click away.
            event.ignore()
            self.hide()
            if not self.settings.value("tray_hint_shown", False) in (True, "true"):
                self.tray.showMessage(
                    APP_NAME,
                    "Still running in the system tray. Right-click the icon to quit.",
                    QSystemTrayIcon.Information,
                    4000,
                )
                self.settings.setValue("tray_hint_shown", True)
            return
        if self.tray is not None:
            self.tray.hide()
        event.accept()

    # ------------------------------------------------------------------
    # pulling state from the system
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        try:
            devices = self.backend.list_devices()
        except Exception:  # never let one bad poll crash the app
            log.exception("Could not list devices")
            devices = []
        master = next((d for d in devices if d.flow == OUTPUT and d.is_default), None)
        if master is None:
            try:
                master = self.backend.default_output()
            except Exception:
                log.exception("Could not read the default output")
        self._master_id = master.id if master else None
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
                    row = VolumeRow(
                        d.id,
                        icons.device_badge(32, d.flow == INPUT),
                        is_input=d.flow == INPUT,
                        can_default=True,
                    )
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
        for a in apps:
            row = panel.rows.get(a.key)
            if row is None:
                row = VolumeRow(a.key, self._icon_for(a))
                row.volumeChanged.connect(self._set_app_volume)
                row.muteToggled.connect(self._set_app_mute)
                panel.rows[a.key] = row
            subtitle = "  ·  ".join(a.devices) if len(a.devices) > 1 or self._many_outputs() else ""
            row.set_state(a.name, a.volume, a.muted, subtitle=subtitle)
            items.append(row)
        panel.arrange(items)

    def _many_outputs(self) -> bool:
        """Only show which device an app plays on when there's a choice."""
        return sum(1 for r in self.devices_panel.rows.values() if not r.is_input) > 1

    def _icon_for(self, app: AppInfo) -> QIcon:
        if app.is_system:
            return icons.bell(32)
        cached = self._app_icons.get(app.key)
        if cached is not None:
            return cached
        icon = QIcon()
        if app.exe_path:
            icon = self._icon_provider.icon(QFileInfo(app.exe_path))
        if icon.isNull() or icon.pixmap(QSize(32, 32)).isNull():
            icon = icons.letter_tile(32, app.name)
        self._app_icons[app.key] = icon
        return icon

    def update_meters(self) -> None:
        if not self.isVisible() or self.isMinimized():
            return
        try:
            if self._master_id:
                self.master.meter.set_level(self.backend.device_peak(self._master_id))
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
        if self._master_id:
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
        if device_id == self._master_id:
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
