# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller-спека для GUI ("Редактор Ramus RSF"), общая для Windows,
macOS и Linux -- один и тот же файл, платформа определяется через
sys.platform при запуске самого PyInstaller на соответствующей ОС
(см. .github/workflows/release.yml).

Сборка:
    pyinstaller packaging/pyinstaller/ramus-rsf-gui.spec --noconfirm

Результат:
    dist/RamusRSFEditor/            (Windows/Linux, --onedir)
    dist/RamusRSFEditor.app/        (macOS, .app-бандл)
"""
import sys
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH).resolve().parent.parent  # packaging/pyinstaller/ -> корень репозитория
sys.path.insert(0, str(ROOT))
from ramus_rsf_tool import __version__  # noqa: E402

APP_NAME = "RamusRSFEditor"
APP_DISPLAY_NAME = "Редактор Ramus RSF"
BUNDLE_ID = "tools.ramus-rsf.editor"

ICONS_DIR = ROOT / "packaging" / "icons"
ICON_WIN = str(ICONS_DIR / "ramus-rsf-tool.ico")
ICON_MAC = str(ICONS_DIR / "ramus-rsf-tool.icns")

a = Analysis(
    [str(ROOT / "packaging" / "pyinstaller" / "entrypoint.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "ramus_rsf_tool" / "gui" / "resources"),
         "ramus_rsf_tool/gui/resources"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # PyQt6 тянет много неиспользуемых нами модулей; явно исключаем
        # самые тяжёлые, чтобы установщик оставался компактным.
        "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuick3D",
        "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtNetwork", "PyQt6.QtBluetooth", "PyQt6.QtNfc",
        "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtPositioning", "PyQt6.QtSensors", "PyQt6.QtSerialPort",
        "PyQt6.QtTest", "PyQt6.QtDesigner", "PyQt6.QtHelp",
        "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon = None
if sys.platform.startswith("win"):
    icon = ICON_WIN
elif sys.platform == "darwin":
    icon = ICON_MAC

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=ICON_MAC,
        bundle_identifier=BUNDLE_ID,
        version=__version__,
        info_plist={
            "CFBundleName": APP_DISPLAY_NAME,
            "CFBundleDisplayName": APP_DISPLAY_NAME,
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "MIT",
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "Ramus RSF Model",
                    "CFBundleTypeExtensions": ["rsf"],
                    "CFBundleTypeRole": "Editor",
                    "LSHandlerRank": "Owner",
                }
            ],
        },
    )
