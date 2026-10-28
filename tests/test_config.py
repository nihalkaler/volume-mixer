"""Settings file: defaults, round trips, validation and range limits."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volume_mixer.config import Config, ConfigError, ConfigStore  # noqa: E402


def test_first_run_writes_defaults(tmp_path):
    store = ConfigStore(tmp_path / "sub" / "config.toml")
    assert store.load() is None
    assert store.first_run
    assert store.path.exists()
    assert Config.from_toml(store.path.read_text()) == Config()


def test_round_trip_keeps_everything(tmp_path):
    cfg = Config(theme="soundboard", size=65, layer="top", locked=True, opacity=0.6,
                 tab="apps", compact=True, accent="#2EC4B6", x=-1200, y=40,
                 view="dials", dial_device="{0.0.0.00000000}.{ab-12}", dial_app="spotify.exe")
    cfg.extra["future_setting"] = [1, 2]
    again = Config.from_toml(cfg.to_toml())
    assert again == cfg


def test_values_are_kept_in_range():
    cfg = Config.from_toml("size = 500\nopacity = 0.01\n")
    assert cfg.size == 100 and cfg.opacity == 0.3


@pytest.mark.parametrize(
    "text, word",
    [
        ('theme = "neon"', "theme"),
        ('layer = "floor"', "layer"),
        ("locked = 1", "locked"),
        ('accent = "teal"', "accent"),
        ('view = "tiny"', "view"),
        ("size = true", "size"),
        ("theme = ", "TOML"),
    ],
)
def test_mistakes_are_explained(text, word):
    with pytest.raises(ConfigError, match=word):
        Config.from_toml(text)


def test_store_keeps_last_good_settings(tmp_path):
    store = ConfigStore(tmp_path / "config.toml")
    store.load()
    store.config.theme = "light"
    store.save()
    store.path.write_text('theme = "plaid"\n')
    error = store.load()
    assert error and "theme" in error
    assert store.config.theme == "light"


def test_hand_edits_load(tmp_path):
    store = ConfigStore(tmp_path / "config.toml")
    store.load()
    store.path.write_text('theme = "tactical"\nlayer = "normal"\n')
    assert store.load() is None
    assert (store.config.theme, store.config.layer) == ("tactical", "normal")
