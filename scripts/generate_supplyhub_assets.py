"""Genera gli asset SupplyHub dalle risoluzioni richieste a partire da image/s.png.

Uso una volta sola: ridimensiona l'asset ufficiale senza ridisegnarlo.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "image" / "s.png"
OUT = ROOT / "frontend" / "public"
OUT.mkdir(parents=True, exist_ok=True)

src = Image.open(SRC).convert("RGBA")


def square(image: Image.Image, size: int) -> Image.Image:
    return image.resize((size, size), Image.LANCZOS)


targets = {
    "favicon-16x16.png": 16,
    "favicon-32x32.png": 32,
    "apple-touch-icon.png": 180,
    "android-chrome-192x192.png": 192,
    "android-chrome-512x512.png": 512,
    "supplyhub-logo.png": 512,
}
for name, size in targets.items():
    square(src, size).save(OUT / name, "PNG")

sizes = [(16, 16), (32, 32), (48, 48), (64, 64)]
src.resize((256, 256), Image.LANCZOS).save(
    OUT / "favicon.ico", format="ICO", sizes=sizes
)

print("Asset generati in", OUT)
for name in [*targets, "favicon.ico"]:
    print(" -", name)