"""Generate the RealGoodSplits app icon (PNG + multi-size Windows ICO).

Run with:  python tools/make_icon.py   (requires Pillow)
Outputs into realgoodsplits/assets/.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "realgoodsplits" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

S = 1024  # render large, then downscale for crisp edges
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Rounded dark background (matches the app theme).
pad = int(S * 0.05)
d.rounded_rectangle(
    [pad, pad, S - pad, S - pad], radius=int(S * 0.23), fill=(19, 26, 43, 255)
)

# Four "stem" equalizer bars, one per source colour.
colors = [(244, 114, 182), (245, 158, 11), (52, 211, 153), (96, 165, 250)]
heights = [0.40, 0.66, 0.50, 0.74]  # fraction of inner height

inner = S - 2 * pad
bar_w = inner * 0.13
gap = (inner - len(colors) * bar_w) / (len(colors) + 1)
base = S - pad - inner * 0.18  # bottom baseline of the bars

for i, (c, h) in enumerate(zip(colors, heights)):
    x0 = pad + gap * (i + 1) + bar_w * i
    x1 = x0 + bar_w
    y0 = base - inner * h
    d.rounded_rectangle([x0, y0, x1, base], radius=int(bar_w / 2), fill=c + (255,))

master = img.resize((256, 256), Image.LANCZOS)
master.save(OUT / "icon.png")
master.save(
    OUT / "icon.ico",
    sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
)
print("wrote", OUT / "icon.png", "and", OUT / "icon.ico")
