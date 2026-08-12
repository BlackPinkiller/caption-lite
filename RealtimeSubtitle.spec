from importlib.util import find_spec

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

sherpa_binaries = collect_dynamic_libs("sherpa_onnx")
hidden = collect_submodules("sherpa_onnx")
if not sherpa_binaries:
    raise RuntimeError("No sherpa-onnx dynamic libraries were collected")
for package in ("sherpa_onnx_core", "sherpa_onnx_bin"):
    if find_spec(package) is not None:
        sherpa_binaries += collect_dynamic_libs(package)
        hidden += collect_submodules(package)

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=sherpa_binaries,
    datas=[("resources/silero_vad.int8.onnx", "resources")],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtMultimedia",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RealtimeSubtitle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="resources/app-icon-cc.ico",
)
