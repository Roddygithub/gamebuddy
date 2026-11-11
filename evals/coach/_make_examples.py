"""Regenerate the synthetic example frames committed next to this script.

The examples exercise the eval harness end to end without real captures; they
are deliberately simple. Real annotated captures (coach.save_frames, then a
screenshot of the decision window) are what the measurement is actually for.

    .venv/bin/python evals/coach/_make_examples.py
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, fill) -> None:
    draw.text(xy, text, font=_font(size), fill=fill)


def shop_frame() -> bytes:
    img = Image.new("RGB", (960, 540), (18, 24, 34))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 959, 64], fill=(26, 34, 48))
    _text(draw, (24, 12), "GOLD 52", 34, (255, 204, 68))
    _text(draw, (780, 18), "LEVEL 7", 26, (150, 160, 175))
    for x, name, cost in ((60, "Slark", "3"), (380, "Tidehunter", "5")):
        draw.rectangle([x, 100, x + 280, 440], fill=(34, 48, 71), outline=(90, 110, 140), width=3)
        draw.ellipse([x + 200, 360, x + 264, 424], fill=(255, 204, 68))
        _text(draw, (x + 218, 378), cost, 30, (20, 24, 34))
        _text(draw, (x + 24, 130), name, 30, (235, 240, 248))
        draw.rectangle([x + 24, 200, x + 256, 320], fill=(52, 70, 99))
    for x, label in ((60, "Reroll (2)"), (520, "Buy XP (5)")):
        draw.rectangle([x, 470, x + 380, 525], fill=(47, 61, 82), outline=(90, 110, 140), width=2)
        _text(draw, (x + 110, 483), label, 26, (235, 240, 248))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def ambiguous_frame() -> bytes:
    import random

    rng = random.Random(7)
    img = Image.new("RGB", (960, 540), (24, 26, 30))
    draw = ImageDraw.Draw(img)
    for _ in range(14):
        x, y = rng.randint(0, 900), rng.randint(0, 480)
        r = rng.randint(20, 90)
        grey = rng.randint(45, 75)
        draw.ellipse([x, y, x + r, y + r], fill=(grey, grey, grey + 6))
    draw.rectangle([380, 200, 620, 360], fill=(38, 40, 46))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


if __name__ == "__main__":
    for name, payload in (
        ("example-shop", shop_frame()),
        ("example-ambiguous", ambiguous_frame()),
    ):
        path = HERE / name / "frame.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        print(f"wrote {path} ({len(payload)} bytes)")
