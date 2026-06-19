# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for RealGoodSplits.
#
# Builds a one-folder Windows app (more reliable than one-file for PyTorch).
# Build with:  pyinstaller realgoodsplits.spec
#
# Note: this bundles PyTorch, so the output folder is large (1.5-2.5 GB).
# Model weights are still downloaded on first run.

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []

# Packages that ship data files / dynamic submodules PyInstaller can't see.
for pkg in (
    "torch", "torchaudio", "demucs", "julius", "dora",
    "openunmix", "lameenc", "soundfile", "customtkinter", "einops",
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # package optional / not installed
        print(f"[spec] skipping {pkg}: {exc}")

hiddenimports += collect_submodules("torchaudio")

# tkinterdnd2 is optional; include it if present.
try:
    d, b, h = collect_all("tkinterdnd2")
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass


a = Analysis(
    ["run_gui.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test", "test"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RealGoodSplits",
    console=False,
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="RealGoodSplits",
)
