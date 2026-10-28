"""Widget tests against the demo backend. They run on any OS (no sound card needed)."""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from volume_mixer import theme  # noqa: E402
from volume_mixer.config import ConfigStore  # noqa: E402
from volume_mixer.demo_audio import SYSTEM_SOUNDS_KEY, DemoAudioBackend  # noqa: E402
from volume_mixer.models import AppInfo, clamp_percent, pretty_exe_name  # noqa: E402
from volume_mixer.window import TAB_APPS, TAB_DEVICES, MixerWindow  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def store(tmp_path):
    s = ConfigStore(tmp_path / "config.toml")
    s.load()
    return s


@pytest.fixture
def window(qapp, store):
    backend = DemoAudioBackend()
    w = MixerWindow(backend, store, demo=True)
    w.refresh_timer.stop()
    w.meter_timer.stop()
    yield w, backend
    w._quitting = True
    w.layer.close()
    w.close()


def _mouse(w, kind, pos: QPoint, button=Qt.LeftButton):
    local = QPointF(w.mapFromGlobal(pos))
    event = QMouseEvent(kind, local, QPointF(pos), button, button, Qt.NoModifier)
    QApplication.sendEvent(w, event)


# ---- master volume -------------------------------------------------------
def test_master_shows_default_output(window):
    w, backend = window
    assert w.master.device.full_text() == "Speakers (Realtek(R) Audio)"
    assert w.master.slider.value() == backend.devices["spk"].volume


def test_master_slider_changes_system_volume(window):
    w, backend = window
    w.master.slider.setValue(25)
    assert backend.devices["spk"].volume == 25
    assert w.devices_panel.rows["spk"].slider.value() == 25


def test_master_mute(window):
    w, backend = window
    w.master.mute_btn.click()
    assert backend.devices["spk"].muted is True
    w.master.mute_btn.click()
    assert backend.devices["spk"].muted is False


def test_master_stays_visible_in_compact_mode(window, store):
    w, _ = window
    full_height = w.height()
    w.master.collapse_btn.click()
    assert store.config.compact is True
    assert w.lists.isHidden() and not w.master.isHidden()
    assert w.height() < full_height
    w.master.collapse_btn.click()
    assert not w.lists.isHidden()


# ---- devices tab -------------------------------------------------------------
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
    assert backend.devices["hp"].is_default and not backend.devices["spk"].is_default
    assert w.master.device.full_text() == "Headphones (WH-1000XM5)"
    w.master.slider.setValue(9)
    assert backend.devices["hp"].volume == 9


def test_default_badge_and_button(window):
    w, _ = window
    spk, hp = w.devices_panel.rows["spk"], w.devices_panel.rows["hp"]
    assert not spk.badge.isHidden() and spk.default_btn.isHidden()
    assert hp.badge.isHidden() and not hp.default_btn.isHidden()


# ---- apps tab --------------------------------------------------------------------
def test_apps_tab_controls_each_app_separately(window, store):
    w, backend = window
    w.show_tab(TAB_APPS)
    assert store.config.tab == "apps"
    w.apps_panel.rows["spotify"].slider.setValue(33)
    w.apps_panel.rows["chrome"].mute_btn.click()
    assert backend.apps["spotify"].volume == 33
    assert backend.apps["chrome"].muted is True
    assert backend.apps["discord"].volume == 70


def test_new_and_closed_apps_appear_and_disappear(window):
    w, backend = window
    backend.apps["zoom"] = AppInfo("zoom", "Zoom", 50, False)
    del backend.apps["vlc"]
    w.refresh()
    assert "zoom" in w.apps_panel.rows and "vlc" not in w.apps_panel.rows
    assert w.apps_tab_btn.text().endswith(str(len(backend.apps)))


def test_system_sounds_listed_first(window):
    _, backend = window
    assert backend.list_apps()[0].key == SYSTEM_SOUNDS_KEY


def test_refresh_does_not_fight_a_dragged_slider(window):
    w, backend = window
    slider = w.master.slider
    slider.setSliderDown(True)
    backend.devices["spk"].volume = 5
    w.refresh()
    assert slider.value() != 5
    slider.setSliderDown(False)
    w.refresh()
    assert slider.value() == 5


def test_meters_follow_audio(window):
    w, _ = window
    w.show_widget()
    w.show_tab(TAB_DEVICES)
    w.update_meters()
    assert w.master.meter.level() > 0
    assert w.devices_panel.rows["hdmi"].meter.level() == 0  # muted device


def test_long_names_are_trimmed_not_widened(window):
    w, _ = window
    w.show_widget()
    QApplication.processEvents()
    row = w.devices_panel.rows["hdmi"]
    assert row.title.full_text().startswith("LG ULTRAGEAR")
    assert row.title.text().endswith("…")


# ---- widget behaviour --------------------------------------------------------------
def test_widget_has_no_frame_or_taskbar_button(window):
    w, _ = window
    flags = w.windowFlags()
    assert flags & Qt.FramelessWindowHint
    assert flags & Qt.Tool  # tool windows get no taskbar button
    assert w.testAttribute(Qt.WA_TranslucentBackground)


def test_drag_moves_widget_and_saves_position(window, store):
    w, _ = window
    w.show_widget()
    w.move(200, 200)
    start = w.mapToGlobal(QPoint(40, 40))
    _mouse(w, QMouseEvent.MouseButtonPress, start)
    _mouse(w, QMouseEvent.MouseMove, start + QPoint(30, 20))
    _mouse(w, QMouseEvent.MouseButtonRelease, start + QPoint(30, 20))
    assert (w.x(), w.y()) == (230, 220)
    assert (store.config.x, store.config.y) == (230, 220)


def test_lock_position_stops_dragging(window, store):
    w, _ = window
    w.show_widget()
    w.set_locked(True)
    assert store.config.locked
    w.move(200, 200)
    start = w.mapToGlobal(QPoint(40, 40))
    _mouse(w, QMouseEvent.MouseButtonPress, start)
    _mouse(w, QMouseEvent.MouseMove, start + QPoint(30, 20))
    _mouse(w, QMouseEvent.MouseButtonRelease, start + QPoint(30, 20))
    assert (w.x(), w.y()) == (200, 200)


@pytest.mark.parametrize("name", theme.THEMES)
def test_every_theme_builds(window, store, name):
    w, backend = window
    w.set_theme(name)
    assert store.config.theme == name and theme.P.name == name
    w.master.slider.setValue(41)  # the rebuilt widget still drives the system
    assert backend.devices["spk"].volume == 41
    assert not w.grab().isNull()


def test_size_changes_widget_size(window, store):
    w, _ = window
    normal = w.width()
    w.set_size(80)
    assert store.config.size == 80
    assert w.width() > normal * 1.4


def test_placement_setting_saved(window, store):
    w, _ = window
    for layer in ("top", "normal", "desktop"):
        w.set_layer(layer)
        assert store.config.layer == layer


def test_menu_has_the_clock_style_options(window):
    w, _ = window
    w._fill_menu()
    labels = [a.text() for a in w.menu.actions() if a.text()]
    for expected in ("Master volume only", "Size", "Theme", "Placement", "Lock position",
                     "Start with Windows", "Edit settings file…", "Exit"):
        assert expected in labels


def test_settings_file_edits_are_applied(window, store):
    w, _ = window
    text = store.path.read_text().replace('theme = "dark"', 'theme = "tactical"')
    store.path.write_text(text)
    w._reload_settings()
    assert store.config.theme == "tactical" and theme.P.name == "tactical"


def test_broken_settings_file_keeps_last_good(window, store, monkeypatch):
    w, _ = window
    shown = []
    monkeypatch.setattr("volume_mixer.window.QMessageBox.show", lambda self: shown.append(self.text()))
    store.path.write_text('theme = "neon"\n')
    w._reload_settings()
    assert store.config.theme == "dark"
    assert shown and "theme" in shown[0]


def test_close_does_not_quit_widget(window):
    w, _ = window
    w.show_widget()
    w.close()
    assert w.isVisible()


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
