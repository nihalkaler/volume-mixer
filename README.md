# Volume Mixer

An on-screen volume control panel for Windows 10 and 11. The master volume
is always at the top, and two tabs underneath let you control every audio
device and every app separately.

| Devices | Apps |
| --- | --- |
| ![Devices tab](docs/devices.png) | ![Apps tab](docs/apps.png) |

## Features

- **Master volume, always visible** — slider, mute button and live level
  meter for your default output device. It follows Windows if you switch
  output devices.
- **Devices tab** — every connected output (speakers, headphones, HDMI) and
  input (microphones) with its own volume, mute and level meter. Click
  **Set default** to make any device the Windows default.
- **Apps tab** — every app currently using audio, with its own volume and
  mute, just like the Windows volume mixer. Apps appear and disappear as they
  start and stop using sound. If an app uses more than one output device,
  one slider controls all of them.
- **Always on top** — click the pin to keep the window above everything else.
- **System tray** — closing the window keeps it in the tray; click the tray
  icon to bring it back. Right-click the tray icon to quit.
- Remembers its size, position, tab and pin setting between launches.
- Only one copy runs at a time; launching it again just brings the window
  forward.

## Download

1. Go to the [Releases](../../releases) page.
2. Download `VolumeMixer.exe` from the latest release.
3. Double-click it. No installation needed.

Windows SmartScreen may warn that the app is from an unknown publisher,
because the .exe isn't code-signed. Click **More info → Run anyway**.

## Run from source

Needs Python 3.10 or newer.

```bash
git clone https://github.com/<your-username>/volume-mixer.git
cd volume-mixer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python run.py
```

Options:

| Flag | What it does |
| --- | --- |
| `--demo` | Uses pretend devices and apps. Works on macOS/Linux too, handy for UI work. |
| `--hidden` | Starts in the system tray without opening the window. |

## Build the .exe yourself

```bash
pyinstaller run.py --name VolumeMixer --onefile --windowed --noconfirm ^
  --icon assets/icon.ico --add-data "assets;assets" --paths src ^
  --collect-submodules pycaw
```

The file appears in `dist\VolumeMixer.exe`.

## Publishing a release

GitHub Actions (`.github/workflows/build.yml`) runs the tests and builds the
.exe on every push. To publish a downloadable release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow creates a release for that tag with `VolumeMixer.exe` attached.

## Tests

```bash
python -m pytest -q tests
```

The tests drive the real window against the demo audio backend, so they run
on any OS without a sound card.

## How it works

```
src/volume_mixer/
├── main.py           start-up, single-instance check, picks the backend
├── window.py         the main window, tabs, tray icon and refresh timers
├── widgets.py        master card, volume rows, level meters, sliders
├── windows_audio.py  Windows Core Audio via pycaw (devices, apps, meters)
├── demo_audio.py     pretend audio system for --demo and tests
├── models.py         plain data classes shared by the UI and backends
├── icons.py          icons drawn in code (speaker, mic, pin, app icon)
└── theme.py          colours and the Qt stylesheet
```

- Windows audio is read through the Core Audio COM APIs using
  [pycaw](https://github.com/AndreMiras/pycaw): `IMMDeviceEnumerator` for
  devices, `IAudioEndpointVolume` for device volume, `IAudioSessionManager2`
  and `ISimpleAudioVolume` for per-app volume, and `IAudioMeterInformation`
  for the level meters.
- Setting the default device uses `IPolicyConfig`, the same undocumented
  interface the Windows Sound settings use.
- The window polls the system once a second for device/app changes and 20
  times a second for the level meters. Everything runs on the UI thread, so
  there are no COM threading issues.

## Licence

MIT — see [LICENSE](LICENSE).
