"""RealGoodSplits — a high-quality AI stem splitter powered by Demucs.

Public API:
    from realgoodsplits import StemSeparator, MODELS, collect_audio_files
"""

from .separator import (
    StemSeparator,
    MODELS,
    FOUR_STEMS,
    SIX_STEMS,
    AUDIO_EXTS,
    auto_device,
    collect_audio_files,
)

__all__ = [
    "StemSeparator",
    "MODELS",
    "FOUR_STEMS",
    "SIX_STEMS",
    "AUDIO_EXTS",
    "auto_device",
    "collect_audio_files",
    "__version__",
]

__version__ = "1.0.0"
