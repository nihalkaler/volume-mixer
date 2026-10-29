"""A pretend audio system.

Used when the app runs with ``--demo`` or on a non-Windows machine, so the
interface can be developed, screenshotted and tested anywhere.
"""

from __future__ import annotations

import math
import time

from .models import INPUT, OUTPUT, AppInfo, DeviceInfo, clamp_percent

SYSTEM_SOUNDS_KEY = "__system_sounds__"


class DemoAudioBackend:
    def __init__(self) -> None:
        self._start = time.monotonic()
        self.devices: dict[str, DeviceInfo] = {
            d.id: d
            for d in (
                DeviceInfo("spk", "Speakers (Realtek(R) Audio)", OUTPUT, 64, False, True),
                DeviceInfo("hp", "Headphones (WH-1000XM5)", OUTPUT, 40, False),
                DeviceInfo("hdmi", "LG ULTRAGEAR (NVIDIA High Definition Audio)", OUTPUT, 100, True),
                DeviceInfo("mic", "Microphone Array (Realtek(R) Audio)", INPUT, 80, False, True),
                DeviceInfo("usbmic", "Microphone (Blue Yeti)", INPUT, 72, False),
            )
        }
        self.apps: dict[str, AppInfo] = {
            a.key: a
            for a in (
                AppInfo(SYSTEM_SOUNDS_KEY, "System sounds", 100, False, is_system=True),
                AppInfo("spotify", "Spotify", 85, False),
                AppInfo("chrome", "Google Chrome", 60, False),
                AppInfo("discord", "Discord", 70, False),
                AppInfo("vlc", "VLC media player", 100, True),
            )
        }
        default_out = self._default_id(OUTPUT)
        for app in self.apps.values():
            app.devices = [self.devices[default_out].name] if default_out else []

    # ---- devices -------------------------------------------------------
    def _default_id(self, flow: str) -> str | None:
        for d in self.devices.values():
            if d.flow == flow and d.is_default:
                return d.id
        return None

    def default_output(self) -> DeviceInfo | None:
        did = self._default_id(OUTPUT)
        return _copy(self.devices[did]) if did else None

    def list_devices(self) -> list[DeviceInfo]:
        return [_copy(d) for d in self.devices.values()]

    def set_device_volume(self, device_id: str, percent: int) -> None:
        if device_id in self.devices:
            self.devices[device_id].volume = clamp_percent(percent)

    def set_device_mute(self, device_id: str, muted: bool) -> None:
        if device_id in self.devices:
            self.devices[device_id].muted = bool(muted)

    def set_default_device(self, device_id: str) -> None:
        target = self.devices[device_id]
        for d in self.devices.values():
            if d.flow == target.flow:
                d.is_default = d.id == device_id
        if target.flow == OUTPUT:
            for app in self.apps.values():
                app.devices = [target.name]

    def device_state(self, device_id: str) -> tuple[int, bool] | None:
        d = self.devices.get(device_id)
        return (d.volume, d.muted) if d else None

    def device_peak(self, device_id: str) -> float:
        d = self.devices.get(device_id)
        if d is None or d.muted:
            return 0.0
        if d.flow == OUTPUT and not d.is_default:
            return 0.0
        return self._wave(hash(device_id) % 7) * d.volume / 100

    # ---- apps ----------------------------------------------------------
    def list_apps(self) -> list[AppInfo]:
        return [_copy(a) for a in self.apps.values()]

    def set_app_volume(self, key: str, percent: int) -> None:
        if key in self.apps:
            self.apps[key].volume = clamp_percent(percent)

    def set_app_mute(self, key: str, muted: bool) -> None:
        if key in self.apps:
            self.apps[key].muted = bool(muted)

    def app_state(self, key: str) -> tuple[int, bool] | None:
        a = self.apps.get(key)
        return (a.volume, a.muted) if a else None

    def app_peak(self, key: str) -> float:
        a = self.apps.get(key)
        if a is None or a.muted or key in (SYSTEM_SOUNDS_KEY, "discord"):
            return 0.0
        return self._wave(len(key)) * a.volume / 100

    def _wave(self, seed: int) -> float:
        t = time.monotonic() - self._start
        v = 0.55 + 0.3 * math.sin(t * 2.1 + seed) + 0.15 * math.sin(t * 7.3 + seed * 3)
        return max(0.0, min(1.0, v))


def _copy(obj):
    from dataclasses import replace

    if isinstance(obj, AppInfo):
        return replace(obj, devices=list(obj.devices))
    return replace(obj)
