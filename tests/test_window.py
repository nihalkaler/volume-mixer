"""UI tests against the demo backend. They run on any OS (no sound card needed)."""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QCoreApplication, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from volume_mixer.demo_audio import SYSTEM_SOUNDS_KEY, DemoAudioBackend  # noqa: E402
from volume_mixer.models import AppInfo, clamp_percent, pretty_exe_name  # noqa: E402
from volume_mixer.window import TAB_APPS, TAB_DEVICES, MixerWindow  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    QCoreApplication.setOrganizationName("VolumeMixerTests")
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp):
    QSettings("VolumeMixer", "VolumeMixer").clear()
    backend = DemoAudioBackend()
    w = MixerWindow(backend, demo=True)
    w.refresh_timer.stop()
    w.meter_timer.stop()
    yield w, backend
    w._quitting = True
    w.close()


def test_master_shows_default_output(window):
    w, backend = window
    assert w.master.device.full_text() == "Speakers (Realtek(R) Audio)"
    assert w.master.slider.value() == backend.devices["spk"].volume


def test_master_slider_changes_system_volume(window):
    w, backend = window
    w.master.slider.setValue(25)
    assert backend.devices["spk"].volume == 25
    # the default device's row in the Devices tab follows along
    assert w.devices_panel.rows["spk"].slider.value() == 25


def test_master_mute(window):
    w, backend = window
    w.master.mute_btn.click()
    assert backend.devices["spk"].muted is True
    w.master.mute_btn.click()
    assert backend.devices["spk"].muted is False


def test_devices_tab_lists_every_device(window):
    w, backend = window
    assert set(w.devices_panel.rows) == set(backend.devices)


def test_device_volume_and_mute(window):
    w, backend = window
    row = w.devices_panel.rows["hp"]
    row.slider.setValue(12)
    assert backend.devices["hp"].volume == 12
    row.mute_btn.click()
    assert backend.devices["hp"].muted is True


def test_set_default_device_moves_master(window):
    w, backend = window
    w.devices_panel.rows["hp"].default_btn.click()
    assert backend.devices["hp"].is_default
    assert not backend.devices["spk"].is_default
    assert w.master.device.full_text() == "Headphones (WH-1000XM5)"
    w.master.slider.setValue(9)
    assert backend.devices["hp"].volume == 9


def test_default_badge_and_button(window):
    w, _ = window
    spk, hp = w.devices_panel.rows["spk"], w.devices_panel.rows["hp"]
    assert not spk.badge.isHidden() and spk.default_btn.isHidden()
    assert hp.badge.isHidden() and not hp.default_btn.isHidden()


def test_apps_tab_controls_each_app_separately(window):
    w, backend = window
    w.show_tab(TAB_APPS)
    w.apps_panel.rows["spotify"].slider.setValue(33)
    w.apps_panel.rows["chrome"].mute_btn.click()
    assert backend.apps["spotify"].volume == 33
    assert backend.apps["chrome"].muted is True
    assert backend.apps["discord"].volume == 70  # untouched


def test_new_and_closed_apps_appear_and_disappear(window):
    w, backend = window
    backend.apps["zoom"] = AppInfo("zoom", "Zoom", 50, False)
    del backend.apps["vlc"]
    w.refresh()
    assert "zoom" in w.apps_panel.rows
    assert "vlc" not in w.apps_panel.rows
    assert w.apps_tab_btn.text().endswith(str(len(backend.apps)))


def test_system_sounds_listed_first(window):
    w, backend = window
    names = [a.key for a in backend.list_apps()]
    assert names[0] == SYSTEM_SOUNDS_KEY


def test_refresh_does_not_fight_a_dragged_slider(window):
    w, backend = window
    slider = w.master.slider
    slider.setSliderDown(True)
    backend.devices["spk"].volume = 5  # something else changes the volume
    w.refresh()
    assert slider.value() != 5
    slider.setSliderDown(False)
    w.refresh()
    assert slider.value() == 5


def test_meters_follow_audio(window):
    w, backend = window
    w.show()
    w.show_tab(TAB_DEVICES)
    w.update_meters()
    assert w.master.meter.level() > 0
    assert w.devices_panel.rows["hdmi"].meter.level() == 0  # muted device


def test_long_names_are_trimmed_not_widened(window):
    w, _ = window
    w.resize(380, 600)
    w.show()
    QApplication.processEvents()
    row = w.devices_panel.rows["hdmi"]
    assert row.title.full_text().startswith("LG ULTRAGEAR")
    assert row.title.text().endswith("…")
    assert w.width() <= 400


def test_pin_keeps_window_on_top(window):
    w, _ = window
    from PySide6.QtCore import Qt

    w.master.pin_btn.click()
    assert w.windowFlags() & Qt.WindowStaysOnTopHint
    w.master.pin_btn.click()
    assert not (w.windowFlags() & Qt.WindowStaysOnTopHint)


@pytest.mark.parametrize(
    "exe, expected",
    [("spotify.exe", "Spotify"), ("obs64.exe", "Obs64"), ("WhatsApp.exe", "WhatsApp"), ("", "Unknown app")],
)
def test_pretty_exe_name(exe, expected):
    assert pretty_exe_name(exe) == expected


def test_clamp_percent():
    assert clamp_percent(-4) == 0
    assert clamp_percent(49.6) == 50
    assert clamp_percent(130) == 100
