"""Volume Mixer — an on-screen volume control widget for Windows."""

try:
    # The release build writes this file from the release's tag (v2.0.3 -> 2.0.3),
    # so the version inside the app always matches the release it came from.
    from ._version import __version__
except ImportError:  # running from source
    __version__ = "dev"

APP_NAME = "Volume Mixer"
