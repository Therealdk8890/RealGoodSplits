"""Core stem-separation engine.

This module wraps `demucs` behind a small, well-typed API that both the GUI and
the CLI use. Heavy imports (``torch`` / ``demucs``) happen lazily inside methods
so that importing this module — and launching the GUI — stays instant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

# --- Model catalogue -------------------------------------------------------

#: Human-readable description for each supported Demucs model.
MODELS = {
    "htdemucs": "Default hybrid-transformer model. 4 stems. Best speed/quality balance.",
    "htdemucs_ft": "Fine-tuned variant. 4 stems. Highest quality, ~4x slower.",
    "htdemucs_6s": "6 stems — adds separate guitar & piano (experimental).",
    "mdx_extra": "MDX-Extra. 4 stems. Strong non-transformer alternative.",
    "mdx_extra_q": "Quantised MDX-Extra. 4 stems. Smaller download, a touch lower quality.",
}

FOUR_STEMS = ["drums", "bass", "other", "vocals"]
SIX_STEMS = ["drums", "bass", "other", "vocals", "guitar", "piano"]

#: Stems produced by each model, used by the UI to show the right checkboxes.
MODEL_STEMS = {
    "htdemucs": FOUR_STEMS,
    "htdemucs_ft": FOUR_STEMS,
    "htdemucs_6s": SIX_STEMS,
    "mdx_extra": FOUR_STEMS,
    "mdx_extra_q": FOUR_STEMS,
}

#: Audio file extensions we consider when scanning folders.
AUDIO_EXTS = {
    ".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg",
    ".opus", ".wma", ".aif", ".aiff", ".alac",
}

# A progress callback receives a fraction in [0, 1] and a short status message.
ProgressCB = Callable[[float, str], None]
# A log callback receives a single line of human-readable text.
LogCB = Callable[[str], None]


def auto_device() -> str:
    """Pick the best available compute device (CUDA → Apple MPS → CPU)."""
    try:
        import torch
    except Exception:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


def collect_audio_files(paths: Iterable[str | Path]) -> List[Path]:
    """Expand a mix of files and folders into a de-duplicated list of audio files.

    Folders are scanned recursively. Order is preserved.
    """
    found: List[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in AUDIO_EXTS:
                    found.append(f)
        elif p.is_file():
            found.append(p)
    seen: set[Path] = set()
    unique: List[Path] = []
    for f in found:
        rp = f.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(f)
    return unique


class StemSeparator:
    """A reusable wrapper around a Demucs model.

    The underlying model is loaded lazily on first use and cached, so a single
    instance can process many files efficiently (great for batch jobs).
    """

    def __init__(
        self,
        model_name: str = "htdemucs",
        device: Optional[str] = None,
        *,
        overlap: float = 0.25,
        shifts: int = 0,
        segment: Optional[float] = None,
        jobs: int = 0,
    ) -> None:
        self.model_name = model_name
        self.device = device or auto_device()
        self.overlap = overlap
        self.shifts = shifts
        self.segment = segment
        self.jobs = jobs
        self._sep = None  # demucs.api.Separator, created lazily
        self._loaded_key = None
        self._current_cb: Optional[ProgressCB] = None

    # -- model lifecycle ----------------------------------------------------

    def _config_key(self):
        return (
            self.model_name, self.device, self.overlap,
            self.shifts, self.segment, self.jobs,
        )

    def _ensure_loaded(self) -> None:
        key = self._config_key()
        if self._sep is not None and self._loaded_key == key:
            return
        from demucs.api import Separator  # heavy import, kept local

        kwargs = dict(
            model=self.model_name,
            device=self.device,
            overlap=self.overlap,
            shifts=self.shifts,
            jobs=self.jobs,
            progress=False,
            callback=self._demucs_callback,
        )
        if self.segment:
            kwargs["segment"] = self.segment
        self._sep = Separator(**kwargs)
        self._loaded_key = key

    @property
    def samplerate(self) -> int:
        self._ensure_loaded()
        return int(self._sep.samplerate)

    def preload(self) -> None:
        """Eagerly download/load the model (e.g. to warm a cache)."""
        self._ensure_loaded()

    # -- progress bridge ----------------------------------------------------

    def _demucs_callback(self, data: dict) -> None:
        """Translate Demucs' internal callback dict into a 0..1 fraction."""
        cb = self._current_cb
        if cb is None:
            return
        try:
            models = max(1, int(data.get("models", 1)))
            model_idx = int(data.get("model_idx_in_bag", 0))
            length = max(1, int(data.get("audio_length", 1)))
            offset = int(data.get("segment_offset", 0))
            frac = (model_idx + offset / length) / models
            cb(min(max(frac, 0.0), 1.0), "Separating…")
        except Exception:
            # Progress is best-effort; never let it break a separation.
            pass

    # -- the main event -----------------------------------------------------

    def separate_file(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        *,
        stems: Optional[Sequence[str]] = None,
        two_stems: bool = False,
        output_format: str = "wav",
        mp3_bitrate: int = 320,
        bit_depth: int = 16,
        float32: bool = False,
        filename_template: str = "{track}/{stem}.{ext}",
        progress_cb: Optional[ProgressCB] = None,
        log_cb: Optional[LogCB] = None,
    ) -> List[Path]:
        """Separate a single audio file and write the requested stems to disk.

        Args:
            stems: Subset of stems to keep (defaults to all the model produces).
            two_stems: If True, output only ``vocals`` + ``no_vocals`` (the sum
                of every non-vocal source — i.e. an instrumental / karaoke pair).
            output_format: ``wav`` | ``mp3`` | ``flac``.
            bit_depth: 16 or 24 (WAV/FLAC only).
            float32: Write 32-bit float WAV/FLAC (overrides ``bit_depth``).
            filename_template: Uses ``{track}``, ``{stem}`` and ``{ext}``.

        Returns:
            The list of paths that were written.
        """
        from demucs.api import save_audio  # local heavy import

        input_path = Path(input_path)
        output_dir = Path(output_dir)
        self._ensure_loaded()

        if log_cb:
            log_cb(f"Loading: {input_path.name}")

        self._current_cb = progress_cb
        try:
            _origin, separated = self._sep.separate_audio_file(str(input_path))
        finally:
            self._current_cb = None

        out_map = self._select_outputs(separated, stems=stems, two_stems=two_stems)

        written: List[Path] = []
        ext = output_format.lower().lstrip(".")
        track = input_path.stem
        for stem_name, source in out_map.items():
            rel = filename_template.format(track=track, stem=stem_name, ext=ext)
            out_path = output_dir / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)

            save_kwargs = dict(samplerate=self.samplerate)
            if ext == "mp3":
                save_kwargs["bitrate"] = mp3_bitrate
            else:  # wav / flac
                if float32:
                    save_kwargs["as_float"] = True
                else:
                    save_kwargs["bits_per_sample"] = bit_depth

            save_audio(source, str(out_path), **save_kwargs)
            written.append(out_path)
            if log_cb:
                log_cb(f"  ✓ {rel}")
        return written

    @staticmethod
    def _select_outputs(separated: dict, *, stems, two_stems) -> dict:
        """Resolve the raw model output into the stems the user asked for."""
        if two_stems:
            out: dict = {}
            if "vocals" in separated:
                out["vocals"] = separated["vocals"]
            instrumental = None
            for name, src in separated.items():
                if name == "vocals":
                    continue
                instrumental = src if instrumental is None else instrumental + src
            if instrumental is not None:
                out["no_vocals"] = instrumental
            return out

        if stems:
            wanted = {s.lower() for s in stems}
            return {k: v for k, v in separated.items() if k.lower() in wanted}

        return dict(separated)
