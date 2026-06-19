"""Core stem-separation engine.

This wraps Demucs behind a small, well-typed API used by both the GUI and the
CLI. It uses Demucs' stable low-level building blocks (``pretrained.get_model``
+ ``apply.apply_model`` + ``audio.save_audio``) — the same path ``python -m
demucs`` takes internally — so results match the reference implementation.

Heavy imports (``torch`` / ``demucs``) happen lazily inside methods so that
importing this module — and launching the GUI — stays instant.
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
        self._model = None  # demucs model (BagOfModels), loaded lazily
        self._loaded_name: Optional[str] = None

    # -- model lifecycle ----------------------------------------------------

    def _ensure_loaded(self):
        if self._model is not None and self._loaded_name == self.model_name:
            return self._model
        from demucs.pretrained import get_model  # heavy import, kept local

        self._model = get_model(self.model_name)
        self._loaded_name = self.model_name
        return self._model

    @property
    def samplerate(self) -> int:
        return int(self._ensure_loaded().samplerate)

    @property
    def sources(self) -> List[str]:
        return list(self._ensure_loaded().sources)

    def preload(self) -> None:
        """Eagerly download/load the model (e.g. to warm a cache)."""
        self._ensure_loaded()

    # -- audio loading ------------------------------------------------------

    @staticmethod
    def _load_track(path: Path, samplerate: int, channels: int):
        """Read an audio file to a ``[channels, time]`` tensor at ``samplerate``.

        Tries, in order: Demucs' ffmpeg-backed reader (handles mp3/m4a/…),
        torchaudio, then soundfile. The soundfile fallback covers WAV/FLAC/OGG
        without any ffmpeg/torchcodec dependency, which keeps things working on
        a bare Windows install.
        """
        import torch
        from demucs.audio import AudioFile, convert_audio

        # 1) ffmpeg-backed — the broadest format support.
        try:
            return AudioFile(str(path)).read(
                streams=0, samplerate=samplerate, channels=channels
            )
        except Exception:
            pass

        # 2) torchaudio.
        try:
            import torchaudio

            wav, sr = torchaudio.load(str(path))
            return convert_audio(wav, sr, samplerate, channels)
        except Exception:
            pass

        # 3) soundfile (libsndfile) — no ffmpeg/torchcodec required.
        import soundfile as sf

        data, sr = sf.read(str(path), dtype="float32", always_2d=True)  # [frames, ch]
        wav = torch.from_numpy(data.T).contiguous()  # -> [ch, frames]
        return convert_audio(wav, sr, samplerate, channels)

    @staticmethod
    def _save(source, out_path: Path, *, ext: str, samplerate: int,
              mp3_bitrate: int, bit_depth: int, float32: bool) -> None:
        """Write one stem. WAV/FLAC go through soundfile; MP3 through lameenc.

        This deliberately avoids torchaudio's writer, which in recent versions
        delegates to TorchCodec/FFmpeg and is therefore not always available.
        """
        if ext == "mp3":
            # Demucs' MP3 encoder uses lameenc and is independent of torchaudio.
            from demucs.audio import save_audio

            save_audio(source, str(out_path), samplerate=samplerate, bitrate=mp3_bitrate)
            return

        import numpy as np
        import soundfile as sf

        data = source.detach().transpose(0, 1).contiguous().cpu().numpy().astype("float32")
        peak = float(np.max(np.abs(data))) if data.size else 0.0
        if peak > 1.0:  # rescale rather than hard-clip, matching Demucs' default
            data = data / peak
        if float32:
            subtype = "FLOAT"
        else:
            subtype = "PCM_24" if bit_depth == 24 else "PCM_16"
        sf.write(str(out_path), data, samplerate, subtype=subtype)

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
        progress: bool = False,
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
            progress: Show Demucs' built-in tqdm progress bar (handy for the CLI).

        Returns:
            The list of paths that were written.
        """
        import torch
        from demucs.apply import apply_model

        input_path = Path(input_path)
        output_dir = Path(output_dir)
        model = self._ensure_loaded()

        if log_cb:
            log_cb(f"Loading: {input_path.name}")

        wav = self._load_track(input_path, model.samplerate, model.audio_channels)

        # Standard Demucs normalisation: zero-mean / unit-std before the model,
        # reversed afterwards so output levels match the input.
        ref = wav.mean(0)
        mean = ref.mean()
        std = ref.std()
        if float(std) < 1e-8:
            std = torch.tensor(1.0)
        wav = (wav - mean) / std

        with torch.no_grad():
            estimates = apply_model(
                model,
                wav[None],
                shifts=self.shifts,
                split=True,
                overlap=self.overlap,
                progress=progress,
                device=self.device,
                num_workers=self.jobs,
                segment=self.segment,
            )[0]
        estimates = estimates * std + mean

        separated = {name: estimates[i] for i, name in enumerate(model.sources)}
        out_map = self._select_outputs(separated, stems=stems, two_stems=two_stems)

        written: List[Path] = []
        ext = output_format.lower().lstrip(".")
        track = input_path.stem
        for stem_name, source in out_map.items():
            rel = filename_template.format(track=track, stem=stem_name, ext=ext)
            out_path = output_dir / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)

            self._save(
                source, out_path, ext=ext, samplerate=model.samplerate,
                mp3_bitrate=mp3_bitrate, bit_depth=bit_depth, float32=float32,
            )
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
