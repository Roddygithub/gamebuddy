import io

from PIL import Image, ImageDraw

from gamebro.capture import Rect, WindowInfo, to_jpeg
from gamebro.capture.base import overlay_mask
from gamebro.coach.observer import dhash, hash_distance


def _png(color, w=200, h=120, box=None):
    img = Image.new("RGB", (w, h), color)
    if box:
        ImageDraw.Draw(img).rectangle(box, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_dhash_detects_change():
    a = _png((10, 10, 10))
    b = _png((10, 10, 10), box=(20, 20, 120, 100))
    assert hash_distance(dhash(a), dhash(a)) == 0.0
    assert hash_distance(dhash(a), dhash(b)) > 0.1


def test_to_jpeg_resizes_and_masks():
    png = _png((200, 30, 30), w=2000, h=1000)
    jpg = to_jpeg(png, max_width=640, quality=60, mask=Rect(0, 0, 320, 500))
    img = Image.open(io.BytesIO(jpg))
    assert img.width == 640 and img.format == "JPEG"
    # masked region is dark, the rest is red
    assert img.getpixel((10, 10))[0] < 60
    assert img.getpixel((600, 10))[0] > 150


def test_overlay_mask_relative_coords():
    win = WindowInfo(id="1", title="Game", app_id="game", rect=Rect(100, 100, 800, 600))
    assert overlay_mask(win, None) is None
    assert overlay_mask(win, Rect(2000, 0, 100, 100)) is None
    m = overlay_mask(win, Rect(850, 50, 200, 200))
    assert m == Rect(750, 0, 50, 150)
