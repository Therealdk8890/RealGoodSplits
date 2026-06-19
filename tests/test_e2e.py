"""End-to-end separation test.

Generates a short synthetic stereo tone, runs a real Demucs separation on CPU,
and asserts that the expected stem files are produced. Skipped automatically if
torch / demucs are not installed.
"""

from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("demucs")
np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from realgoodsplits.separator import StemSeparator


def _make_tone(path: Path, seconds: float = 3.0, sr: int = 44100) -> None:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    left = 0.2 * np.sin(2 * np.pi * 110 * t) + 0.2 * np.sin(2 * np.pi * 440 * t)
    right = 0.2 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)
    sf.write(str(path), np.stack([left, right], axis=1), sr)


def test_four_stem_separation(tmp_path):
    src = tmp_path / "tone.wav"
    _make_tone(src)

    sep = StemSeparator(model_name="htdemucs", device="cpu")
    written = sep.separate_file(src, tmp_path / "out", output_format="wav")

    assert len(written) == 4
    for p in written:
        assert p.exists() and p.stat().st_size > 0


def test_two_stem_mp3(tmp_path):
    src = tmp_path / "tone.wav"
    _make_tone(src)

    sep = StemSeparator(model_name="htdemucs", device="cpu")
    written = sep.separate_file(
        src, tmp_path / "out", two_stems=True, output_format="mp3"
    )

    names = sorted(p.stem for p in written)
    assert names == ["no_vocals", "vocals"]
    for p in written:
        assert p.exists() and p.stat().st_size > 0
