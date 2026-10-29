"""Windows Core Audio backend, built on pycaw + comtypes.

Every COM call here runs on the Qt main thread (Qt and comtypes both set the
main thread up as a single-threaded COM apartment). The UI polls this backend
on timers, so there are no COM callbacks or extra threads to manage.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

import comtypes
import psutil
from _ctypes import COMError
from pycaw.api.audiopolicy import IAudioSessionControl2
from pycaw.api.endpointvolume import IAudioMeterInformation
from pycaw.api.policyconfig import IPolicyConfig
from pycaw.constants import (
    DEVICE_STATE,
    AudioSessionState,
    CLSID_CPolicyConfigClient,
    EDataFlow,
    ERole,
)
from pycaw.utils import AudioDevice, AudioSession, AudioUtilities

from .models import (
    INPUT,
    OUTPUT,
    AppInfo,
    DeviceInfo,
    clamp_percent,
    pretty_exe_name,
)

SYSTEM_SOUNDS_KEY = "__system_sounds__"
_FLOWS = ((EDataFlow.eRender.value, OUTPUT), (EDataFlow.eCapture.value, INPUT))

# Errors a device or session can throw when it disappears mid-call.
_GONE = (COMError, OSError, ValueError, psutil.Error)


def _file_description(path: str) -> str | None:
    """Read the "File description" from an .exe's version info.

    That's the friendly name Windows shows ("Google Chrome" rather than
    "chrome.exe").
    """
    version = ctypes.windll.version
    version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, wintypes.LPDWORD]
    version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    version.GetFileVersionInfoW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    version.GetFileVersionInfoW.restype = wintypes.BOOL
    version.VerQueryValueW.argtypes = [
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.UINT),
    ]
    version.VerQueryValueW.restype = wintypes.BOOL

    size = version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(path, 0, size, buf):
        return None

    ptr = ctypes.c_void_p()
    length = wintypes.UINT()
    translations: list[tuple[int, int]] = []
    if version.VerQueryValueW(
        buf, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(length)
    ) and length.value:
        pairs = ctypes.cast(ptr, ctypes.POINTER(wintypes.WORD * 2))
        for i in range(length.value // 4):
            translations.append((pairs[i][0], pairs[i][1]))
    # Common fallbacks: US English with Unicode / Western code pages.
    translations += [(0x0409, 0x04B0), (0x0409, 0x04E4)]

    for lang, codepage in translations:
        key = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileDescription"
        if version.VerQueryValueW(buf, key, ctypes.byref(ptr), ctypes.byref(length)):
            if length.value > 1:
                text = ctypes.wstring_at(ptr.value, length.value - 1).strip()
                if text:
                    return text
    return None


class _ProcessInfo:
    __slots__ = ("key", "name", "exe_path")

    def __init__(self, key: str, name: str, exe_path: str | None):
        self.key = key
        self.name = name
        self.exe_path = exe_path


class WindowsAudioBackend:
    """Talks to Windows through the Core Audio COM APIs."""

    def __init__(self) -> None:
        self._enumerator = AudioUtilities.GetDeviceEnumerator()
        self._devices: dict[str, AudioDevice] = {}  # id -> pycaw device
        self._meters: dict[str, object] = {}  # id -> IAudioMeterInformation
        self._names: dict[str, str] = {}  # device id -> friendly name
        self._flows: dict[str, str] = {}  # device id -> OUTPUT / INPUT
        self._sessions: dict[str, list[AudioSession]] = {}  # app key -> sessions
        self._session_meters: dict[str, list[object]] = {}
        self._procs: dict[int, _ProcessInfo] = {}  # pid -> cached info
        self._exe_names: dict[str, str] = {}  # exe name -> friendly name
        self._exe_paths: dict[str, str] = {}  # exe name -> full path (for icons)

    # ------------------------------------------------------------------
    # devices
    # ------------------------------------------------------------------
    def _device(self, device_id: str) -> AudioDevice:
        dev = self._devices.get(device_id)
        if dev is None:
            raw = self._enumerator.GetDevice(device_id)
            dev = AudioUtilities.CreateDevice(raw)
            self._devices[device_id] = dev
            self._names[device_id] = dev.FriendlyName or "Audio device"
        return dev

    def _default_id(self, flow: int) -> str | None:
        try:
            return self._enumerator.GetDefaultAudioEndpoint(
                flow, ERole.eMultimedia.value
            ).GetId()
        except _GONE:
            return None  # no device of this kind is connected

    def _snapshot(self, device_id: str, flow: str, default_id: str | None) -> DeviceInfo:
        vol = self._device(device_id).EndpointVolume
        return DeviceInfo(
            id=device_id,
            name=self._names[device_id],
            flow=flow,
            volume=clamp_percent(vol.GetMasterVolumeLevelScalar() * 100),
            muted=bool(vol.GetMute()),
            is_default=device_id == default_id,
        )

    def default_output(self) -> DeviceInfo | None:
        default_id = self._default_id(EDataFlow.eRender.value)
        if default_id is None:
            return None
        try:
            return self._snapshot(default_id, OUTPUT, default_id)
        except _GONE:
            self._forget_device(default_id)
            return None

    def list_devices(self) -> list[DeviceInfo]:
        result: list[DeviceInfo] = []
        seen: set[str] = set()
        for flow_value, flow in _FLOWS:
            default_id = self._default_id(flow_value)
            try:
                collection = self._enumerator.EnumAudioEndpoints(
                    flow_value, DEVICE_STATE.ACTIVE.value
                )
                count = collection.GetCount()
            except _GONE:
                continue
            for i in range(count):
                try:
                    device_id = collection.Item(i).GetId()
                    self._flows[device_id] = flow
                    result.append(self._snapshot(device_id, flow, default_id))
                    seen.add(device_id)
                except _GONE:
                    continue
        # Drop cached COM objects for devices that were unplugged.
        for gone in set(self._devices) - seen:
            self._forget_device(gone)
        return result

    def _forget_device(self, device_id: str) -> None:
        self._devices.pop(device_id, None)
        self._meters.pop(device_id, None)
        self._names.pop(device_id, None)
        self._flows.pop(device_id, None)

    def set_device_volume(self, device_id: str, percent: int) -> None:
        try:
            self._device(device_id).EndpointVolume.SetMasterVolumeLevelScalar(
                clamp_percent(percent) / 100.0, None
            )
        except _GONE:
            self._forget_device(device_id)

    def set_device_mute(self, device_id: str, muted: bool) -> None:
        try:
            self._device(device_id).EndpointVolume.SetMute(int(bool(muted)), None)
        except _GONE:
            self._forget_device(device_id)

    def set_default_device(self, device_id: str) -> None:
        """Make a device the Windows default for every role.

        Uses the undocumented IPolicyConfig interface, which is what the
        Windows sound settings use too. Setting all three roles matches what
        the "Set Default" button in the classic Sound control panel does.
        """
        policy = comtypes.CoCreateInstance(
            CLSID_CPolicyConfigClient, IPolicyConfig, comtypes.CLSCTX_ALL
        )
        for role in (ERole.eConsole, ERole.eMultimedia, ERole.eCommunications):
            # comtypes raises COMError on a failing HRESULT, so no return
            # value check is needed here.
            policy.SetDefaultEndpoint(device_id, role.value)

    def device_state(self, device_id: str) -> tuple[int, bool] | None:
        """Volume and mute of one device, for the quick 5-times-a-second
        check that keeps the master volume in step with the keyboard's
        volume keys and the Windows volume flyout."""
        try:
            vol = self._device(device_id).EndpointVolume
            return clamp_percent(vol.GetMasterVolumeLevelScalar() * 100), bool(vol.GetMute())
        except _GONE:
            self._forget_device(device_id)
            return None

    def device_peak(self, device_id: str) -> float:
        try:
            meter = self._meters.get(device_id)
            if meter is None:
                raw = self._device(device_id)._dev  # the underlying IMMDevice
                meter = raw.Activate(
                    IAudioMeterInformation._iid_, comtypes.CLSCTX_ALL, None
                ).QueryInterface(IAudioMeterInformation)
                self._meters[device_id] = meter
            return float(meter.GetPeakValue())
        except _GONE:
            self._meters.pop(device_id, None)
            return 0.0

    # ------------------------------------------------------------------
    # applications (audio sessions)
    # ------------------------------------------------------------------
    def _process_info(self, pid: int) -> _ProcessInfo | None:
        if pid == 0:
            return _ProcessInfo(SYSTEM_SOUNDS_KEY, "System sounds", None)
        cached = self._procs.get(pid)
        if cached is not None:
            return cached
        try:
            proc = psutil.Process(pid)
            exe_name = proc.name()
        except psutil.Error:
            return None  # process already exited
        try:
            exe_path = proc.exe() or None
        except psutil.Error:
            exe_path = None  # e.g. elevated process we can't inspect

        # Group by program file name, so every chrome.exe process lands in one
        # row even when Windows hides the full path of some of them.
        key = exe_name.lower()
        cached_name = self._exe_names.get(key)
        if cached_name is None and exe_path:
            try:
                cached_name = _file_description(exe_path) or ""
            except OSError:
                cached_name = ""
            self._exe_names[key] = cached_name
            self._exe_paths[key] = exe_path
        name = cached_name or pretty_exe_name(exe_name)

        info = _ProcessInfo(key, name, exe_path or self._exe_paths.get(key))
        self._procs[pid] = info
        return info

    def list_apps(self) -> list[AppInfo]:
        groups: dict[str, AppInfo] = {}
        sessions: dict[str, list[AudioSession]] = {}
        if not self._flows:
            self.list_devices()  # learn which output devices exist

        for device_id, flow in list(self._flows.items()):
            if flow != OUTPUT:
                continue
            try:
                manager = self._device(device_id).AudioSessionManager
                enum = manager.GetSessionEnumerator()
                count = enum.GetCount()
            except _GONE:
                continue
            for i in range(count):
                try:
                    ctl = enum.GetSession(i)
                    if ctl is None:
                        continue
                    session = AudioSession(ctl.QueryInterface(IAudioSessionControl2))
                    if session.State == AudioSessionState.Expired:
                        continue
                    info = self._process_info(session.ProcessId)
                    if info is None:
                        continue
                    vol = session.SimpleAudioVolume
                    volume = clamp_percent(vol.GetMasterVolume() * 100)
                    muted = bool(vol.GetMute())
                except _GONE:
                    continue

                device_name = self._names.get(device_id, "")
                app = groups.get(info.key)
                if app is None:
                    app = AppInfo(
                        key=info.key,
                        name=info.name,
                        volume=volume,
                        muted=muted,
                        exe_path=info.exe_path,
                        is_system=info.key == SYSTEM_SOUNDS_KEY,
                    )
                    groups[info.key] = app
                else:
                    # One slider for the whole app: show the loudest session,
                    # and only call it muted if every session is muted.
                    app.volume = max(app.volume, volume)
                    app.muted = app.muted and muted
                    if app.exe_path is None and info.exe_path:
                        app.exe_path = info.exe_path
                    if app.name != info.name and info.exe_path:
                        app.name = info.name  # prefer the friendly name
                if device_name and device_name not in app.devices:
                    app.devices.append(device_name)
                sessions.setdefault(info.key, []).append(session)

        self._sessions = sessions
        self._session_meters = {}
        # Forget cached process info for processes that have exited.
        alive = {s.ProcessId for group in sessions.values() for s in group}
        for pid in set(self._procs) - alive:
            self._procs.pop(pid, None)

        apps = sorted(groups.values(), key=lambda a: (not a.is_system, a.name.lower()))
        return apps

    def set_app_volume(self, key: str, percent: int) -> None:
        level = clamp_percent(percent) / 100.0
        for session in self._sessions.get(key, []):
            try:
                session.SimpleAudioVolume.SetMasterVolume(level, None)
            except _GONE:
                continue

    def set_app_mute(self, key: str, muted: bool) -> None:
        for session in self._sessions.get(key, []):
            try:
                session.SimpleAudioVolume.SetMute(int(bool(muted)), None)
            except _GONE:
                continue

    def app_state(self, key: str) -> tuple[int, bool] | None:
        """Volume and mute of one app (loudest session; muted only if every
        session is), matching what list_apps reports."""
        volume, muted, found = 0, True, False
        for session in self._sessions.get(key, []):
            try:
                vol = session.SimpleAudioVolume
                volume = max(volume, clamp_percent(vol.GetMasterVolume() * 100))
                muted = muted and bool(vol.GetMute())
                found = True
            except _GONE:
                continue
        return (volume, muted) if found else None

    def app_peak(self, key: str) -> float:
        meters = self._session_meters.get(key)
        if meters is None:
            meters = []
            for session in self._sessions.get(key, []):
                try:
                    meters.append(session._ctl.QueryInterface(IAudioMeterInformation))
                except _GONE:
                    continue
            self._session_meters[key] = meters
        peak = 0.0
        for meter in meters:
            try:
                peak = max(peak, float(meter.GetPeakValue()))
            except _GONE:
                continue
        return peak


def is_supported() -> bool:
    return os.name == "nt"
