# PyInstaller recipe for VolumeMixer.exe:  pyinstaller VolumeMixer.spec --noconfirm
#
# A one-file .exe unpacks everything inside it to a temporary folder every
# time it starts, so leaving out what the widget never uses makes it start
# faster (it runs at every sign-in) as well as making the download smaller.
from PyInstaller.utils.hooks import collect_submodules

# Parts of Qt and Python the widget doesn't use. Matched against file names.
UNUSED = (
    "opengl32sw.dll",      # 20 MB software OpenGL; the widget draws without OpenGL
    "libcrypto", "libssl",  # SSL: the widget never goes online
    "qopensslbackend", "qschannelbackend", "qcertonlybackend",  # Qt TLS plugins
    "qnetworklistmanager",  # Qt network-status plugin
    "qdirect2d",            # alternative Windows renderer; the standard one is used
    "qtiff", "qwebp", "qjpeg", "qgif", "qicns", "qtga", "qwbmp", "qpdf", "qsvg",  # image formats (only PNG is used)
    "Qt6Svg", "Qt6Pdf", "Qt6Qml", "Qt6Quick", "Qt6OpenGL", "Qt6VirtualKeyboard",
)


def needed(entry) -> bool:
    name = entry[0].replace("\\", "/")
    if "/translations/" in name:  # Qt's own dialog translations
        return False
    return not any(part.lower() in name.lower() for part in UNUSED)


a = Analysis(
    ["run.py"],
    pathex=["src"],
    datas=[("assets", "assets")],
    hiddenimports=collect_submodules("pycaw"),
    excludes=["tkinter", "_tkinter", "ssl", "_ssl", "_hashlib"],
    noarchive=False,
)
a.binaries = [b for b in a.binaries if needed(b)]
a.datas = [d for d in a.datas if needed(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VolumeMixer",
    console=False,  # no black console window
    icon=["assets/icon.ico"],
    upx=False,
    debug=False,
    strip=False,
)
