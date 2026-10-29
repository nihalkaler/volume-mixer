"""Windows desktop integration for the widget, the same way the World Clock
Widget does it:

- **Placement**: on the desktop (kept underneath every other window), like a
  normal window, or always on top.
- **Show desktop**: with "on the desktop" placement, pressing Win+D or
  clicking the wallpaper brings the widget forward so you can see it; it drops
  back down as soon as another window is used.
- **Start with Windows**: the registry ``Run`` key.

On other systems these quietly do nothing (or use plain Qt window flags), so
the app still runs there in demo mode.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = os.name == "nt"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "VolumeMixerWidget"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    HWND_TOP = wintypes.HWND(0)
    HWND_BOTTOM = wintypes.HWND(1)
    HWND_TOPMOST = wintypes.HWND(-1)
    HWND_NOTOPMOST = wintypes.HWND(-2)
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x2, 0x4, 0x10
    WM_WINDOWPOSCHANGING = 0x0046
    WM_MOUSEACTIVATE = 0x0021
    MA_NOACTIVATE = 3
    EVENT_SYSTEM_FOREGROUND = 0x0003
    WINEVENT_OUTOFCONTEXT = 0x0000
    GWL_EXSTYLE = -20
    WS_EX_NOACTIVATE = 0x08000000

    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int

    WinEventProc = ctypes.WINFUNCTYPE(
        None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
        wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
    )
    user32.SetWinEventHook.argtypes = [
        wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WinEventProc,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    ]
    user32.SetWinEventHook.restype = wintypes.HANDLE
    user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]

    class WINDOWPOS(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("hwndInsertAfter", wintypes.HWND),
            ("x", ctypes.c_int),
            ("y", ctypes.c_int),
            ("cx", ctypes.c_int),
            ("cy", ctypes.c_int),
            ("flags", wintypes.UINT),
        ]


# HWND_NOTOPMOST (-2) as ctypes may report it: signed, or unsigned 32/64-bit.
_NOTOPMOST_VALUES = {-2, 2**32 - 2, 2**64 - 2}


def _class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(64)
    n = user32.GetClassNameW(hwnd, buf, 64)
    return buf.value[: max(0, n)]


class DesktopLayer:
    """Keeps one window at the chosen placement (see the module docstring)."""

    def __init__(self, widget):
        self.widget = widget
        self.layer = "normal"
        self.raised = False  # brought forward because the desktop was shown
        self._hook = None
        self._proc = None

    @property
    def hwnd(self):
        return wintypes.HWND(int(self.widget.winId())) if IS_WINDOWS else None

    def apply(self, layer: str) -> None:
        self.layer = layer
        self.raised = False
        if not IS_WINDOWS:
            from PySide6.QtCore import Qt

            w = self.widget
            visible = w.isVisible()
            w.setWindowFlag(Qt.WindowStaysOnTopHint, layer == "top")
            w.setWindowFlag(Qt.WindowStaysOnBottomHint, layer == "desktop")
            if visible:
                w.show()
            return
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        hwnd = self.hwnd
        if layer == "top":
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        else:
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
            if layer == "desktop":
                user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, flags)
        self._ensure_hook()

    def bring_forward(self) -> None:
        """Show the widget above other windows until another window is used."""
        if not IS_WINDOWS:
            self.widget.raise_()
            return
        if self.layer == "desktop":
            self.raised = True
        if self.layer != "top":
            user32.SetWindowPos(self.hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _ensure_hook(self) -> None:
        if self._hook is not None:
            return
        self._proc = WinEventProc(self._on_foreground)  # keep a reference alive
        self._hook = user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, self._proc, 0, 0, WINEVENT_OUTOFCONTEXT
        )

    def _on_foreground(self, _hook, _event, hwnd, _obj, _child, _thread, _time) -> None:
        try:
            if self.layer != "desktop" or not hwnd:
                return
            mine = self.hwnd
            if hwnd == mine.value:
                return
            # "Show desktop" (Win+D) or clicking the wallpaper focuses the
            # desktop window, which would otherwise cover the widget.
            desktop = _class_name(hwnd) in ("WorkerW", "Progman")
            flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            if desktop and not self.raised:
                self.raised = True
                user32.SetWindowPos(mine, HWND_TOP, 0, 0, 0, 0, flags)
            elif not desktop and self.raised:
                self.raised = False
                user32.SetWindowPos(mine, HWND_BOTTOM, 0, 0, 0, 0, flags)
        except Exception:  # never let a hook callback take the app down
            pass

    def native_event(self, message) -> tuple[bool, int] | None:
        """Handle the window messages that keep the widget in its layer.

        Returns ``(True, result)`` when the message is fully handled.
        """
        if not IS_WINDOWS:
            return None
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_MOUSEACTIVATE:
            # Clicking the widget shouldn't steal focus from what you're doing.
            return True, MA_NOACTIVATE
        if msg.message == WM_WINDOWPOSCHANGING and self.layer == "desktop" and not self.raised:
            pos = WINDOWPOS.from_address(msg.lParam)
            # HWND_NOTOPMOST is let through: it's how an "always on top" widget
            # drops back down before being sent to the bottom.
            after = pos.hwndInsertAfter or 0
            if after not in _NOTOPMOST_VALUES:
                pos.hwndInsertAfter = 1  # HWND_BOTTOM
                pos.flags &= ~SWP_NOZORDER
        return None

    def close(self) -> None:
        if IS_WINDOWS and self._hook:
            user32.UnhookWinEvent(self._hook)
        self._hook = None


# ----------------------------------------------------------------------
# Start with Windows
# ----------------------------------------------------------------------
def launch_command() -> str:
    """The command Windows should run at sign-in."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    run_py = Path(__file__).resolve().parents[2] / "run.py"
    return f'"{exe}" "{run_py}"'


def autostart_supported() -> bool:
    return IS_WINDOWS


def autostart_command() -> str | None:
    """What Windows currently runs at sign-in for this widget, if anything."""
    if not IS_WINDOWS:
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, RUN_VALUE)
            return str(value)
    except OSError:
        return None


def autostart_enabled() -> bool:
    return autostart_command() is not None


def refresh_autostart() -> None:
    """If the exe has been moved since Start with Windows was turned on,
    point Windows at where it is now (otherwise it silently stops starting)."""
    command = autostart_command()
    if command is not None and command != launch_command():
        set_autostart(True)


def set_autostart(enabled: bool) -> None:
    if not IS_WINDOWS:
        return
    import winreg

    # CreateKeyEx opens the Run key, or creates it on profiles that don't
    # have one yet (OpenKey would fail there and Start with Windows would
    # silently never turn on).
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


# ----------------------------------------------------------------------
# Opening things
# ----------------------------------------------------------------------
def open_in_editor(path: Path) -> None:
    if IS_WINDOWS:
        subprocess.Popen(["notepad.exe", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-t", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def open_sound_settings() -> None:
    if IS_WINDOWS:
        os.startfile("ms-settings:sound")  # type: ignore[attr-defined]
