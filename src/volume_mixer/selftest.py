"""``--self-test LOG``: exercise the real Windows code for a few seconds and
report anything that goes wrong.

The release build runs the finished ``VolumeMixer.exe`` with this on a
Windows machine before publishing it, so problems that only show up on
Windows (the audio APIs, window placement, Start with Windows, a file missing
from the .exe) are caught there instead of on your PC. You can also run it
yourself: ``VolumeMixer.exe --self-test result.txt``.

It doesn't change anything that matters: volumes are written back with the
values they already have, the default device is "set" to the one already in
use, Start with Windows is put back as it was, and it uses its own throwaway
settings file.
"""

from __future__ import annotations

import logging
import sys
import tempfile
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QPoint, QtMsgType, QTimer, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import APP_NAME, __version__, desktop, theme
from .config import MODES, ConfigStore

TIME_LIMIT_S = 90


class Report:
    def __init__(self, path: Path):
        self.path = path
        self.lines: list[str] = []
        self.errors = 0
        self.started = time.monotonic()
        self._warned: set[str] = set()

    # One line per entry (tracebacks folded onto it), so the build can show
    # each problem as a single message.
    @staticmethod
    def _one_line(text: str) -> str:
        return " ⏎ ".join(part.rstrip() for part in text.strip().splitlines())

    def info(self, text: str) -> None:
        self.lines.append(f"INFO: {self._one_line(text)}")

    def warn(self, text: str) -> None:
        if text not in self._warned:  # the same Qt warning can come up dozens of times
            self._warned.add(text)
            self.lines.append(f"WARNING: {self._one_line(text)}")

    def error(self, text: str) -> None:
        self.errors += 1
        self.lines.append(f"ERROR: {self._one_line(text)}")

    def check(self, ok: bool, what: str) -> None:
        if ok:
            self.info(f"ok: {what}")
        else:
            self.error(f"failed: {what}")

    def write(self) -> None:
        verdict = "PASSED" if self.errors == 0 else f"FAILED ({self.errors} problem(s))"
        took = time.monotonic() - self.started
        text = "\n".join([f"{APP_NAME} {__version__} self-test {verdict} in {took:.1f}s", *self.lines]) + "\n"
        try:
            self.path.write_text(text, encoding="utf-8")
        except OSError:
            pass
        if sys.stdout is not None:  # None in the windowed .exe
            try:
                sys.stdout.write(text)
            except OSError:
                pass


class _ErrorLog(logging.Handler):
    """Anything the app logs as an error counts as a problem."""

    def __init__(self, report: Report):
        super().__init__(logging.ERROR)
        self.report = report

    def emit(self, record: logging.LogRecord) -> None:
        text = record.getMessage()
        if record.exc_info:
            text += "\n" + "".join(traceback.format_exception(*record.exc_info)).rstrip()
        self.report.error(f"logged: {text}")


def run(app: QApplication, log_path: Path, demo: bool) -> int:
    report = Report(log_path)
    error_log = _ErrorLog(report)
    logging.getLogger().addHandler(error_log)
    old_excepthook = sys.excepthook

    def excepthook(kind, value, tb):  # exceptions inside Qt callbacks land here
        report.error("exception:\n" + "".join(traceback.format_exception(kind, value, tb)).rstrip())

    sys.excepthook = excepthook

    def qt_messages(kind, _context, message):
        if kind in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            report.error(f"Qt: {message}")
        elif kind == QtMsgType.QtWarningMsg:
            report.warn(f"Qt: {message}")

    old_handler = qInstallMessageHandler(qt_messages)
    try:
        return _run(app, report, demo)
    finally:
        logging.getLogger().removeHandler(error_log)
        sys.excepthook = old_excepthook
        qInstallMessageHandler(old_handler)


def _run(app: QApplication, report: Report, demo: bool) -> int:
    report.info(f"Python {sys.version.split()[0]}, Windows: {desktop.IS_WINDOWS}, frozen: {getattr(sys, 'frozen', False)}")
    report.info(f"system tray available: {QSystemTrayIcon.isSystemTrayAvailable()}")

    from .main import make_backend

    try:
        backend, demo = make_backend(demo)
    except Exception:
        report.error("audio backend failed to start:\n" + traceback.format_exc().rstrip())
        report.write()
        return 1
    report.info(f"audio backend: {type(backend).__name__}")

    store = ConfigStore(Path(tempfile.mkdtemp(prefix="volmix-selftest-")) / "config.toml")
    store.load()

    from .window import MixerWindow

    widget = MixerWindow(backend, store, demo=demo)
    steps = _steps(widget, backend, store, report)
    result = {"code": 1}

    def next_step() -> None:
        try:
            delay = next(steps)
        except StopIteration:
            finish()
            return
        except Exception:
            report.error("self-test step crashed:\n" + traceback.format_exc().rstrip())
            finish()
            return
        QTimer.singleShot(delay, next_step)

    def finish() -> None:
        result["code"] = 0 if report.errors == 0 else 1
        report.write()
        widget.quit()

    def too_slow() -> None:
        report.error(f"did not finish within {TIME_LIMIT_S}s")
        finish()

    QTimer.singleShot(0, next_step)
    QTimer.singleShot(TIME_LIMIT_S * 1000, too_slow)
    app.exec()
    return result["code"]


def _steps(widget, backend, store, report: Report):
    """The test, one step at a time; each ``yield`` lets Qt run for a while."""
    from .models import INPUT, OUTPUT

    # ---- the audio system ------------------------------------------------------
    devices = backend.list_devices()
    outputs = [d for d in devices if d.flow == OUTPUT]
    inputs = [d for d in devices if d.flow == INPUT]
    default = backend.default_output()
    report.info(f"{len(outputs)} output(s), {len(inputs)} input(s); default output: "
                f"{default.name if default else 'none'}")
    for d in devices:
        state = backend.device_state(d.id)
        report.check(state is not None and state[0] == d.volume, f"read volume of {d.name!r}")
        backend.device_peak(d.id)
        backend.set_device_volume(d.id, d.volume)  # same value: changes nothing
        backend.set_device_mute(d.id, d.muted)
    if default is not None:
        backend.set_default_device(default.id)  # already the default: changes nothing
        again = backend.default_output()
        report.check(again is not None and again.id == default.id, "set the default device")
    apps = backend.list_apps()
    report.info(f"{len(apps)} app(s) using sound: {', '.join(a.name for a in apps) or 'none'}")
    for a in apps:
        state = backend.app_state(a.key)
        report.check(state is not None, f"read volume of app {a.name!r}")
        backend.app_peak(a.key)
        backend.set_app_volume(a.key, a.volume)
        backend.set_app_mute(a.key, a.muted)
    if not devices:
        report.warn("no audio devices on this machine, so the device and app code ran on empty lists")
    yield 0

    # ---- the widget on screen --------------------------------------------------------
    widget.show_widget()
    yield 400
    report.check(widget.isVisible() and widget.width() > 100, "widget shows")
    if desktop.IS_WINDOWS and QGuiApplication.platformName() == "windows":
        yield from _window_checks(widget, report)
    elif desktop.IS_WINDOWS:
        # e.g. the test suite's invisible screen: no real windows to check
        report.info(f"window placement not checked on the {QGuiApplication.platformName()!r} screen")

    # ---- every mode, theme and size -------------------------------------------------------
    for mode in MODES:
        widget.set_mode(mode)
        for name in theme.THEMES:
            widget.set_theme(name)
            widget.refresh()
            widget.quick_sync()
            widget.update_meters()
            report.check(not widget.grab().isNull() and theme.P.name == name, f"{mode} mode in the {name} theme")
            yield 30
        for size, label in (theme.DIAL_SIZES if mode == "dials" else theme.SIZES):
            widget.set_size(size)
            yield 30
        report.check(store.config.mode == mode, f"{mode} mode with every size")
    widget.set_mode("default")
    widget.set_theme("dark")
    widget.set_size(50)

    # ---- menu, snapping, settings file -----------------------------------------------------
    widget._fill_menu()
    report.check(len(widget.menu.actions()) > 8, "right-click menu")
    widget._snapped(widget.pos(), widget.pos() + QPoint(20, 20))
    text = store.path.read_text(encoding="utf-8").replace('theme = "dark"', 'theme = "soundboard"')
    store.path.write_text(text, encoding="utf-8")
    yield 600  # the file watcher picks the change up
    widget._reload_settings()
    report.check(store.config.theme == "soundboard", "editing the settings file")
    widget.set_meters(False)
    widget.set_meters(True)

    # ---- Start with Windows -------------------------------------------------------------
    if desktop.autostart_supported():
        before = desktop.autostart_command()
        try:
            desktop.set_autostart(True)
            report.check(desktop.autostart_command() == desktop.launch_command(), "turn on Start with Windows")
            desktop.set_autostart(False)
            report.check(not desktop.autostart_enabled(), "turn off Start with Windows")
        finally:
            _restore_autostart(before)
        report.check(desktop.autostart_command() == before, "Start with Windows put back as it was")
    yield 100


def _window_checks(widget, report: Report):
    """Placement on Windows: always on top, normal, and on the desktop."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetShellWindow.restype = wintypes.HWND
    GWL_EXSTYLE, WS_EX_TOPMOST, WS_EX_TOOLWINDOW, GW_HWNDNEXT = -20, 0x8, 0x80, 2
    hwnd = widget.layer.hwnd

    def ex_style() -> int:
        return user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)

    report.check(bool(ex_style() & WS_EX_TOOLWINDOW), "no taskbar button (tool window)")
    widget.set_layer("top")
    yield 150
    report.check(bool(ex_style() & WS_EX_TOPMOST), "Always on top")
    widget.set_layer("normal")
    yield 150
    report.check(not ex_style() & WS_EX_TOPMOST, "Like a normal window")
    widget.set_layer("desktop")
    yield 150
    report.check(not ex_style() & WS_EX_TOPMOST, "On the desktop: not on top")

    # Something tries to bring it to the front: on the desktop it must stay at
    # the back (this goes through the WM_WINDOWPOSCHANGING handling).
    from .desktop import HWND_TOP, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE

    user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    yield 150
    # Only the desktop itself (Explorer's wallpaper / icons window) may be below it.
    below = user32.GetWindow(hwnd, GW_HWNDNEXT)
    below_class = desktop._class_name(below) if below else ""
    report.check(not below or below_class in ("Progman", "WorkerW"),
                 f"On the desktop: stays behind other windows (next window down: {below_class or 'none'})")

    # Win+D / clicking the wallpaper brings it forward, and using any other
    # window drops it back (the foreground-window hook).
    shell = user32.GetShellWindow()
    if shell:
        widget.layer._on_foreground(None, 3, shell, 0, 0, 0, 0)
        report.check(widget.layer.raised, "comes forward when the desktop is shown")
        user32.GetDesktopWindow.restype = wintypes.HWND
        widget.layer._on_foreground(None, 3, user32.GetDesktopWindow(), 0, 0, 0, 0)
        report.check(not widget.layer.raised, "drops back when another window is used")
    else:
        report.warn("no desktop shell (Explorer) here, so the Win+D behaviour wasn't checked")
    widget.set_layer("desktop")
    yield 50


def _restore_autostart(before: str | None) -> None:
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, desktop.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if before is None:
            try:
                winreg.DeleteValue(key, desktop.RUN_VALUE)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(key, desktop.RUN_VALUE, 0, winreg.REG_SZ, before)
