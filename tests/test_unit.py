"""Fast unit tests — no PyTorch/Demucs required."""

from realgoodsplits.separator import (
    MODELS,
    MODEL_STEMS,
    StemSeparator,
    collect_audio_files,
)


def test_collect_audio_files_filters_and_recurses(tmp_path):
    (tmp_path / "a.wav").write_bytes(b"x")
    (tmp_path / "b.mp3").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.flac").write_bytes(b"x")

    found = sorted(p.name for p in collect_audio_files([tmp_path]))
    assert found == ["a.wav", "b.mp3", "c.flac"]


def test_collect_audio_files_dedupes(tmp_path):
    f = tmp_path / "song.wav"
    f.write_bytes(b"x")
    found = collect_audio_files([f, f, tmp_path])
    assert len(found) == 1


def test_two_stems_groups_instrumental():
    raw = {"drums": 1, "bass": 2, "other": 3, "vocals": 10}
    out = StemSeparator._select_outputs(raw, stems=None, two_stems=True)
    assert set(out) == {"vocals", "no_vocals"}
    assert out["vocals"] == 10
    assert out["no_vocals"] == 1 + 2 + 3  # drums + bass + other


def test_stem_subset_selection():
    raw = {"drums": 1, "bass": 2, "other": 3, "vocals": 10}
    out = StemSeparator._select_outputs(raw, stems=["Vocals", "drums"], two_stems=False)
    assert set(out) == {"vocals", "drums"}


def test_default_keeps_all_stems():
    raw = {"drums": 1, "bass": 2, "other": 3, "vocals": 10}
    out = StemSeparator._select_outputs(raw, stems=None, two_stems=False)
    assert out == raw


def test_every_model_declares_stems():
    for name in MODELS:
        assert MODEL_STEMS.get(name), f"{name} has no declared stems"
