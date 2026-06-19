"""Command-line interface for RealGoodSplits.

Examples
--------
    realgoodsplits-cli song.mp3
    realgoodsplits-cli song.mp3 --two-stems -f mp3
    realgoodsplits-cli ./album_folder -o ./out -m htdemucs_ft --stems vocals drums
    realgoodsplits-cli --list-models
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__
from .separator import MODELS, MODEL_STEMS, StemSeparator, auto_device, collect_audio_files


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="realgoodsplits-cli",
        description="Split songs into stems (vocals, drums, bass, …) with Demucs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("inputs", nargs="*", help="Audio files and/or folders to process.")
    p.add_argument("-o", "--output", default="separated",
                   help="Output directory.")
    p.add_argument("-m", "--model", default="htdemucs", choices=list(MODELS),
                   help="Demucs model to use.")
    p.add_argument("--two-stems", action="store_true",
                   help="Output only vocals + instrumental (karaoke pair).")
    p.add_argument("--stems", nargs="+", metavar="STEM",
                   help="Subset of stems to keep, e.g. --stems vocals drums.")
    p.add_argument("-f", "--format", default="wav",
                   choices=["wav", "mp3", "flac"], help="Output audio format.")
    p.add_argument("--mp3-bitrate", type=int, default=320,
                   help="MP3 bitrate (kbps) when --format mp3.")
    p.add_argument("--bit-depth", type=int, default=16, choices=[16, 24],
                   help="Bit depth for WAV/FLAC.")
    p.add_argument("--float32", action="store_true",
                   help="Write 32-bit float WAV/FLAC (overrides --bit-depth).")
    p.add_argument("--device", default="auto",
                   choices=["auto", "cpu", "cuda", "mps"],
                   help="Compute device.")
    p.add_argument("--shifts", type=int, default=0,
                   help="Random shifts for higher quality (slower).")
    p.add_argument("--overlap", type=float, default=0.25,
                   help="Segment overlap (0–1).")
    p.add_argument("--segment", type=float, default=None,
                   help="Segment length in seconds (lower = less memory).")
    p.add_argument("-j", "--jobs", type=int, default=0,
                   help="Parallel worker processes (CPU).")
    p.add_argument("--list-models", action="store_true",
                   help="List available models and exit.")
    p.add_argument("-V", "--version", action="version",
                   version=f"RealGoodSplits {__version__}")
    return p


def _print_models() -> None:
    print("Available models:\n")
    for name, desc in MODELS.items():
        stems = ", ".join(MODEL_STEMS.get(name, []))
        print(f"  {name:<14} {desc}")
        print(f"  {'':<14} stems: {stems}\n")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.list_models:
        _print_models()
        return 0

    if not args.inputs:
        print("error: no input files or folders given. "
              "Pass some audio, or use --list-models.", file=sys.stderr)
        return 2

    files = collect_audio_files(args.inputs)
    if not files:
        print("error: no audio files found in the given paths.", file=sys.stderr)
        return 1

    device = auto_device() if args.device == "auto" else args.device
    print(f"RealGoodSplits {__version__}")
    print(f"  model : {args.model}")
    print(f"  device: {device}")
    print(f"  files : {len(files)}")
    print(f"  output: {Path(args.output).resolve()}\n")

    separator = StemSeparator(
        model_name=args.model,
        device=device,
        overlap=args.overlap,
        shifts=args.shifts,
        segment=args.segment,
        jobs=args.jobs,
    )

    failures = 0
    started = time.time()
    for idx, audio in enumerate(files, 1):
        print(f"[{idx}/{len(files)}] {audio.name}")

        last = {"pct": -5}

        def progress(frac: float, _msg: str) -> None:
            pct = int(frac * 100)
            if pct >= last["pct"] + 5:  # throttle to every ~5%
                last["pct"] = pct
                bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
                print(f"\r    [{bar}] {pct:3d}%", end="", flush=True)

        try:
            written = separator.separate_file(
                audio,
                args.output,
                stems=args.stems,
                two_stems=args.two_stems,
                output_format=args.format,
                mp3_bitrate=args.mp3_bitrate,
                bit_depth=args.bit_depth,
                float32=args.float32,
                progress_cb=progress,
            )
            print(f"\r    [####################] 100%")
            for w in written:
                print(f"      -> {w}")
        except Exception as exc:  # keep going through a batch
            failures += 1
            print(f"\r    ! failed: {exc}", file=sys.stderr)

    elapsed = time.time() - started
    ok = len(files) - failures
    print(f"\nDone: {ok}/{len(files)} succeeded in {elapsed:.1f}s.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
