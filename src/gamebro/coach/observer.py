"""Cheap observation: perceptual hash to detect that the screen actually changed."""

from __future__ import annotations

import io


def dhash(image_bytes: bytes, size: int = 16) -> int:
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(img.tobytes())
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hash_distance(a: int, b: int, size: int = 16) -> float:
    """Normalized Hamming distance in [0, 1]."""
    return bin(a ^ b).count("1") / float(size * size)
