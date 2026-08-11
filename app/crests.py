"""Crest pipeline (plan §6):

fetch PNG → RGBA → composite onto white → L → resize (LANCZOS) → UnsharpMask
→ 1-bit (threshold by default; per-crest dither override) → disk cache.

Predominantly-white crests are inverted after compositing (mean-luminance
sample) or they vanish on white paper.
"""
import io
import logging
import os

import requests
from PIL import Image, ImageFilter, ImageOps

from . import config

log = logging.getLogger(__name__)

CREST_DIR = os.path.join(config.CACHE_DIR, "crests")
# Fixed threshold override (env CREST_THRESHOLD, 1–254). 0 = Otsu adaptive,
# which separates low-contrast (e.g. near-white) crests a fixed cut can't.
FIXED_THRESHOLD = int(os.environ.get("CREST_THRESHOLD", "0"))


def _otsu(hist: list[int]) -> int:
    total = sum(hist)
    if not total:
        return 128
    sum_all = sum(i * n for i, n in enumerate(hist))
    sum_b = 0.0
    w_b = 0
    best, thresh = 0.0, 128
    for i, n in enumerate(hist):
        w_b += n
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * n
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > best:
            best, thresh = var, i
    return thresh


def crest_path(team_id: int) -> str:
    return os.path.join(CREST_DIR, f"{team_id}.png")


def get_crest(team_id: int) -> str | None:
    """Return cached file path, processing on first request. None on failure."""
    path = crest_path(team_id)
    if os.path.exists(path):
        return path
    os.makedirs(CREST_DIR, exist_ok=True)
    try:
        r = requests.get(config.CREST_URL_TMPL.format(id=team_id), timeout=15,
                         headers={"User-Agent": config.USER_AGENT})
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception as exc:  # noqa: BLE001 — fail soft, template falls back to initials
        log.warning("crest %s fetch failed: %s", team_id, exc)
        return None

    white = Image.new("RGBA", img.size, (255, 255, 255, 255))
    grey = Image.alpha_composite(white, img).convert("L")

    size = (config.CREST_SIZE, config.CREST_SIZE)
    grey = ImageOps.contain(grey, size, Image.LANCZOS)
    canvas = Image.new("L", size, 255)
    canvas.paste(grey, ((size[0] - grey.width) // 2, (size[1] - grey.height) // 2))
    canvas = canvas.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=2))

    if team_id in config.CREST_DITHER_IDS:
        mono = canvas.convert("1")                       # Floyd–Steinberg
    else:
        # Otsu on the crest area only (exclude the padding we pasted), so a
        # small crest on a big white canvas doesn't skew the split.
        thresh = FIXED_THRESHOLD or _otsu(grey.histogram())
        mono = canvas.point(lambda p: 255 if p > thresh else 0).convert("1")
        # Polarity: e-ink wants dark marks on white paper. If the crest area
        # binarised mostly black (a light-on-dark or near-white source), flip it.
        area = mono.crop(((size[0] - grey.width) // 2, (size[1] - grey.height) // 2,
                          (size[0] + grey.width) // 2, (size[1] + grey.height) // 2))
        black_frac = 1 - (sum(area.histogram()[128:]) / max(1, area.width * area.height))
        if black_frac > 0.62:
            mono = ImageOps.invert(mono.convert("L")).convert("1")

    mono.save(path)
    return path
