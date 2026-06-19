# Changelog

## 1.0.0 — 2026-06-19

First release.

- Desktop **GUI** (CustomTkinter) and a full **CLI** (`realgoodsplits-cli`).
- Stem separation powered by **Demucs v4** — models: `htdemucs`, `htdemucs_ft`,
  `htdemucs_6s` (6 stems), `mdx_extra`, `mdx_extra_q`.
- **Karaoke mode** (vocals + instrumental), per-stem selection, and batch / folder processing.
- Optional **drag-and-drop** (`tkinterdnd2`).
- Output to **WAV / MP3 / FLAC** with selectable bitrate and bit depth.
- **GPU auto-detect** — CUDA (NVIDIA), MPS (Apple Silicon), or CPU.
- Robust audio I/O: WAV/FLAC read+write via `soundfile`, MP3 via `lameenc`
  (no FFmpeg required for those formats).
- Windows one-click installer (`install_windows.bat`), PyInstaller build
  (`build_windows.bat` / spec), and an embedded app icon.
- GitHub Actions: unit tests (Windows + Linux), a real end-to-end separation
  test on Windows, and a Windows `.exe` build/release workflow.
