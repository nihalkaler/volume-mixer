"""Plain data types shared by the audio backends and the UI.

The UI never touches Windows audio objects directly. It only sees these
snapshots, which keeps the window code testable on any OS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

OUTPUT = "output"
INPUT = "input"


@dataclass
class DeviceInfo:
    """One audio endpoint (speakers, headphones, microphone, ...)."""

    id: str
    name: str
    flow: str  # OUTPUT or INPUT
    volume: int  # 0-100
    muted: bool
    is_default: bool = False


@dataclass
class AppInfo:
    """One application playing audio.

    Windows can give a single app several audio sessions (a browser often has
    one per tab or per device). They are grouped under one ``key`` so the user
    sees one slider per app, like the Windows volume mixer does.
    """

    key: str
    name: str
    volume: int  # 0-100
    muted: bool
    exe_path: str | None = None
    devices: list[str] = field(default_factory=list)  # output device names
    is_system: bool = False


class AudioBackend(Protocol):
    """What the UI needs from an audio system."""

    # ---- master (default output device) -------------------------------
    def default_output(self) -> DeviceInfo | None: ...

    # ---- devices -------------------------------------------------------
    def list_devices(self) -> list[DeviceInfo]: ...

    def set_device_volume(self, device_id: str, percent: int) -> None: ...

    def set_device_mute(self, device_id: str, muted: bool) -> None: ...

    def set_default_device(self, device_id: str) -> None: ...

    def device_peak(self, device_id: str) -> float: ...

    # ---- applications ----------------------------------------------------
    def list_apps(self) -> list[AppInfo]: ...

    def set_app_volume(self, key: str, percent: int) -> None: ...

    def set_app_mute(self, key: str, muted: bool) -> None: ...

    def app_peak(self, key: str) -> float: ...


def clamp_percent(value: float) -> int:
    """Round and clamp a volume to a whole 0-100 percentage."""
    return int(max(0, min(100, round(value))))


def pretty_exe_name(exe_name: str) -> str:
    """Turn ``"spotify.exe"`` into ``"Spotify"`` as a last-resort app name."""
    stem = exe_name
    if stem.lower().endswith(".exe"):
        stem = stem[:-4]
    stem = stem.replace("_", " ").replace("-", " ").strip()
    if not stem:
        return exe_name or "Unknown app"
    # Keep names that already have capitals (e.g. "obs64", "WhatsApp").
    if stem.islower():
        stem = stem[:1].upper() + stem[1:]
    return stem
