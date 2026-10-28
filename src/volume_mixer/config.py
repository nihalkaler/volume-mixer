"""Settings, saved to a TOML file you can also edit by hand.

Windows: ``%APPDATA%\\VolumeMixerWidget\\config.toml`` (same idea as the
World Clock Widget). Elsewhere: ``~/.config/VolumeMixerWidget/config.toml``.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from .theme import MAX_SIZE, MIN_SIZE, THEMES

LAYERS = ("desktop", "normal", "top")
LAYER_NAMES = {
    "desktop": "On the desktop (behind windows)",
    "normal": "Like a normal window",
    "top": "Always on top",
}
TABS = ("devices", "apps")
VIEWS = ("panel", "dials")  # dials = the Extra small size
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class ConfigError(ValueError):
    """The settings file has a mistake; the message says what and where."""


@dataclass
class Config:
    theme: str = "dark"
    size: int = 50
    layer: str = "desktop"
    locked: bool = False
    opacity: float = 0.85
    tab: str = "devices"
    compact: bool = False
    accent: str | None = None  # e.g. "#2EC4B6"; None uses the theme's accent
    view: str = "panel"  # "dials" is the Extra small size
    dial_device: str = "default"  # what the device dial controls
    dial_app: str | None = None  # what the app dial controls
    x: int | None = None  # widget position; None = not placed yet
    y: int | None = None
    extra: dict = field(default_factory=dict, repr=False)  # unknown keys, kept as-is

    # ------------------------------------------------------------------
    @classmethod
    def from_toml(cls, text: str) -> "Config":
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"The settings file isn't valid TOML: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        cfg = cls()
        known = {f.name for f in fields(cls)} - {"extra"}

        def need(key, kinds, what):
            value = data[key]
            if isinstance(value, bool) and bool not in kinds:
                raise ConfigError(f"`{key}` should be {what}, not {value!r}.")
            if not isinstance(value, kinds):
                raise ConfigError(f"`{key}` should be {what}, not {value!r}.")
            return value

        for key in data:
            if key not in known:
                cfg.extra[key] = data[key]
        if "theme" in data:
            v = str(need("theme", (str,), "a theme name")).lower()
            if v not in THEMES:
                raise ConfigError(f"`theme` should be one of {', '.join(THEMES)}, not {v!r}.")
            cfg.theme = v
        if "size" in data:
            cfg.size = int(max(MIN_SIZE, min(MAX_SIZE, need("size", (int, float), "a number"))))
        if "layer" in data:
            v = str(need("layer", (str,), "a placement")).lower()
            if v not in LAYERS:
                raise ConfigError(f"`layer` should be one of {', '.join(LAYERS)}, not {v!r}.")
            cfg.layer = v
        if "locked" in data:
            cfg.locked = need("locked", (bool,), "true or false")
        if "opacity" in data:
            cfg.opacity = float(max(0.3, min(1.0, need("opacity", (int, float), "a number from 0.3 to 1.0"))))
        if "tab" in data:
            v = str(need("tab", (str,), "devices or apps")).lower()
            if v not in TABS:
                raise ConfigError(f"`tab` should be devices or apps, not {v!r}.")
            cfg.tab = v
        if "compact" in data:
            cfg.compact = need("compact", (bool,), "true or false")
        if "accent" in data:
            v = need("accent", (str,), 'a colour like "#2EC4B6"')
            if v and not _HEX.match(v):
                raise ConfigError(f'`accent` should be a colour like "#2EC4B6", not {v!r}.')
            cfg.accent = v or None
        if "view" in data:
            v = str(need("view", (str,), "panel or dials")).lower()
            if v not in VIEWS:
                raise ConfigError(f"`view` should be panel or dials, not {v!r}.")
            cfg.view = v
        if "dial_device" in data:
            cfg.dial_device = need("dial_device", (str,), "a device") or "default"
        if "dial_app" in data:
            cfg.dial_app = need("dial_app", (str,), "an app") or None
        if "x" in data and "y" in data:
            cfg.x = int(need("x", (int,), "a whole number"))
            cfg.y = int(need("y", (int,), "a whole number"))
        return cfg

    def to_toml(self) -> str:
        def q(s: str) -> str:
            return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

        lines = [
            "# Volume Mixer widget settings. Changes appear within a second of saving.",
            "",
            f"theme = {q(self.theme):<15}# dark | light | cyberpunk | tactical | soundboard",
            f"size = {self.size:<16}# {MIN_SIZE} to {MAX_SIZE}: 50 is normal, 100 is twice as big",
            f"layer = {q(self.layer):<15}# desktop | normal | top",
            f"locked = {str(self.locked).lower():<14}# true stops the widget being dragged",
            f"opacity = {self.opacity:<13g}# background, 0.3 to 1.0",
            f"tab = {q(self.tab):<17}# devices | apps",
            f"compact = {str(self.compact).lower():<13}# true shows the master volume only",
        ]
        if self.accent:
            lines.append(f"accent = {q(self.accent):<14}# your own accent colour")
        else:
            lines.append('# accent = "#2EC4B6"   # uncomment for your own accent colour')
        lines += [
            "",
            "# Extra small size: two dials instead of the full mixer.",
            f"view = {q(self.view):<16}# panel | dials",
            f"dial_device = {q(self.dial_device)}   # \"default\" follows the Windows default output",
        ]
        if self.dial_app:
            lines.append(f"dial_app = {q(self.dial_app)}")
        if self.x is not None and self.y is not None:
            lines += ["", "# Where the widget sits (saved when you drag it).", f"x = {self.x}", f"y = {self.y}"]
        for key, value in self.extra.items():
            lines.append(f"{key} = {_toml_value(value)}")
        return "\n".join(lines) + "\n"


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return '"' + str(value) + '"'


def default_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "VolumeMixerWidget" / "config.toml"


class ConfigStore:
    """Loads and saves the settings file, remembering the last good settings."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_path()
        self.config = Config()
        self.first_run = False
        self._last_written: str | None = None

    def load(self) -> str | None:
        """Read the file. Returns an error message, or None if all is well."""
        if not self.path.exists():
            self.first_run = True
            self.config = Config()
            self.save()
            return None
        try:
            text = self.path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            return f"Couldn't read {self.path}:\n{exc}"
        if text == self._last_written:
            return None  # our own save, nothing new
        try:
            self.config = Config.from_toml(text)
        except ConfigError as exc:
            return f"{exc}\n\nKeeping the last good settings until it's fixed.\n({self.path})"
        return None

    def save(self) -> None:
        text = self.config.to_toml()
        if text == self._last_written:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.path)
            self._last_written = text
        except OSError:
            pass  # e.g. read-only folder: keep working with settings in memory
