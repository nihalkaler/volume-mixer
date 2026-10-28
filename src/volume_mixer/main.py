"""Entry point: settings, single instance, audio backend, then the widget."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QFont, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, __version__, desktop, icons, theme
from .config import ConfigStore

INSTANCE_KEY = "volume-mixer-widget-single-instance"


def resource_path(relative: str) -> Path:
    """Find bundled files both when run from source and from the .exe."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="volume-mixer", description=APP_NAME)
    parser.add_argument("--demo", action="store_true", help="use pretend devices and apps (works on any OS)")
    parser.add_argument("--settings", type=Path, help="use this settings file instead of the usual one")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def make_backend(demo: bool):
    if demo or os.name != "nt":
        from .demo_audio import DemoAudioBackend

        return DemoAudioBackend(), True
    from .windows_audio import WindowsAudioBackend

    return WindowsAudioBackend(), False


def _already_running() -> bool:
    """If another copy is open, ask it to come forward and return True."""
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    if os.name == "nt":
        try:  # its own taskbar/tray identity instead of "python.exe"
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VolumeMixer.Widget")
        except (AttributeError, OSError):
            pass

    QCoreApplication.setOrganizationName("VolumeMixerWidget")
    QCoreApplication.setApplicationName(APP_NAME)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)  # a widget only closes from its menu

    if _already_running():
        return 0
    QLocalServer.removeServer(INSTANCE_KEY)  # tidy up after a crash
    server = QLocalServer()
    server.listen(INSTANCE_KEY)

    icon_file = resource_path("assets/icon.png")
    app.setWindowIcon(QIcon(str(icon_file)) if icon_file.exists() else icons.app_icon())
    font = QFont()
    font.setFamilies(theme.UI_FONTS)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    if os.name != "nt":
        app.setStyle("Fusion")  # Windows keeps its own menus; the widget is styled either way

    store = ConfigStore(args.settings)
    error = store.load()
    if error:
        QMessageBox.warning(None, APP_NAME, error)
    if store.first_run and desktop.autostart_supported():
        # Like the World Clock Widget: on first launch, start with Windows.
        try:
            desktop.set_autostart(True)
        except OSError:
            pass

    try:
        backend, demo = make_backend(args.demo)
    except Exception as exc:  # e.g. the Windows audio service isn't running
        QMessageBox.critical(None, APP_NAME, f"Couldn't connect to Windows audio:\n\n{exc}")
        return 1

    from .window import MixerWindow

    widget = MixerWindow(backend, store, demo=demo)

    def on_new_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.disconnectFromServer()
        widget.show_and_raise()

    server.newConnection.connect(on_new_connection)
    widget.show_widget()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
