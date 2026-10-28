"""Entry point: picks the audio backend, enforces a single instance, starts Qt."""

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

from . import APP_NAME, __version__, icons, theme

INSTANCE_KEY = "volume-mixer-single-instance"


def resource_path(relative: str) -> Path:
    """Find bundled files both when run from source and from the .exe."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="volume-mixer", description=APP_NAME)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use pretend devices and apps (works on any OS)",
    )
    parser.add_argument("--hidden", action="store_true", help="start in the tray")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def make_backend(demo: bool):
    if demo or os.name != "nt":
        from .demo_audio import DemoAudioBackend

        return DemoAudioBackend(), True
    from .windows_audio import WindowsAudioBackend

    return WindowsAudioBackend(), False


def _already_running() -> bool:
    """If another copy is open, ask it to show itself and return True."""
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
        # Give the app its own taskbar identity (instead of "python.exe").
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VolumeMixer.App")
        except (AttributeError, OSError):
            pass

    QCoreApplication.setOrganizationName("VolumeMixer")
    QCoreApplication.setApplicationName(APP_NAME)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)  # the tray icon keeps us alive

    if _already_running():
        return 0
    QLocalServer.removeServer(INSTANCE_KEY)  # clean up after a crash
    server = QLocalServer()
    server.listen(INSTANCE_KEY)

    icon_file = resource_path("assets/icon.png")
    app.setWindowIcon(QIcon(str(icon_file)) if icon_file.exists() else icons.app_icon())
    font = QFont()
    font.setFamilies(theme.FONT_FALLBACKS)
    font.setPixelSize(13)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    app.setStyle("Fusion")  # consistent look; the stylesheet does the rest
    app.setStyleSheet(theme.STYLESHEET)

    try:
        backend, demo = make_backend(args.demo)
    except Exception as exc:  # e.g. Windows audio service not running
        QMessageBox.critical(None, APP_NAME, f"Couldn't connect to Windows audio:\n\n{exc}")
        return 1

    from .window import MixerWindow

    window = MixerWindow(backend, demo=demo)

    def on_new_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.disconnectFromServer()
        window.show_and_raise()

    server.newConnection.connect(on_new_connection)

    if not (args.hidden and window.tray is not None):
        window.show()
    if not window.tray:
        app.setQuitOnLastWindowClosed(True)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
