"""Image preparation (Spec 3A cost rule 2): downscale to max ~1024 px JPEG before any model call.

Full resolution phone photos are never sent. Pillow is required; without it the engine
refuses to send images rather than sending originals.
"""
from __future__ import annotations

import base64
import hashlib
import io
from typing import List, Tuple

from . import config


def _decode(img) -> bytes:
    if isinstance(img, bytes):
        return img
    s = str(img)
    if s.startswith("data:"):
        s = s.split(",", 1)[1]
    try:
        return base64.b64decode(s, validate=True)
    except Exception:
        with open(s, "rb") as f:          # a file path
            return f.read()


def photo_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def prepare(images: List) -> Tuple[List[str], List[str]]:
    """Returns (data URLs of downscaled JPEGs, sha256 hashes of the originals)."""
    try:
        from PIL import Image
    except ImportError as e:  # fail loudly, never send full resolution
        raise RuntimeError("Pillow is required to downscale photos before sending: pip install Pillow") from e
    urls, hashes = [], []
    for img in images or []:
        raw = _decode(img)
        hashes.append(photo_hash(raw))
        im = Image.open(io.BytesIO(raw))
        im = im.convert("RGB")
        im.thumbnail((config.IMAGE_MAX_DIM, config.IMAGE_MAX_DIM))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=config.IMAGE_JPEG_QUALITY, optimize=True)
        urls.append("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
    return urls, hashes
