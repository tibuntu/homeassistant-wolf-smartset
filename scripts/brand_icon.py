"""Generate the neutral brand icon (no Wolf trademark) under custom_components/wolf_smartset/brand/.

Home Assistant serves custom_components/<domain>/brand/icon.png (256 px) and icon@2x.png (512 px)
when they exist. Run once: uv run python scripts/brand_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

BRAND = Path(__file__).resolve().parents[1] / "custom_components" / "wolf_smartset" / "brand"
BACKGROUND = (31, 58, 95, 255)  # dark blue
FOREGROUND = (255, 255, 255, 255)


def draw(size: int) -> Image.Image:
    """A rounded square with a white drop: heat and water, nothing branded."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas = ImageDraw.Draw(image)
    canvas.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 6, fill=BACKGROUND)
    cx, cy, r = size / 2, size * 0.6, size * 0.22
    canvas.ellipse((cx - r, cy - r, cx + r, cy + r), fill=FOREGROUND)
    canvas.polygon(
        [(cx, size * 0.14), (cx - r * 0.95, cy - r * 0.35), (cx + r * 0.95, cy - r * 0.35)],
        fill=FOREGROUND,
    )
    return image


if __name__ == "__main__":
    BRAND.mkdir(exist_ok=True)
    draw(256).save(BRAND / "icon.png")
    draw(512).save(BRAND / "icon@2x.png")
    print(f"written to {BRAND}")
