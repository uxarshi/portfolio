"""Cut the hero's hot-air balloons out cleanly for the footer sky.

The hero sprites in assets/hero/ are hull-shaped (they carry sky between the
envelope and the basket), which shows on the cream footer. Here each balloon
is pulled from assets/hero.jpg by difference against the balloon-free LaMa
plate (assets/hero/plate.jpg), so the sky drops out and the ropes stay.
Colours are un-mixed from the sky at the soft edges.

Writes assets/balloons/h2.webp ... h6.webp (balloon-1 is cut off by the frame
edge, so it is skipped).

    python3 tools/build_footer_balloons.py
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
PAD = 6
LO, HI = 14, 46   # colour distance (0-255 RGB) mapped to alpha 0..1

hero = np.asarray(Image.open(ROOT / 'assets/hero.jpg').convert('RGB'), np.float32)
plate = np.asarray(Image.open(ROOT / 'assets/hero/plate.jpg').convert('RGB'), np.float32)
scene = json.loads((ROOT / 'assets/hero/scene.json').read_text())

for sp in scene['sprites']:
    if sp['kind'] != 'balloon' or sp['name'] == 'balloon-1':
        continue
    x, y, w, h = sp['rect']
    x0, y0 = max(0, x - PAD), max(0, y - PAD)
    x1, y1 = min(hero.shape[1], x + w + PAD), min(hero.shape[0], y + h + PAD)
    I, P = hero[y0:y1, x0:x1], plate[y0:y1, x0:x1]

    d = np.sqrt(((I - P) ** 2).sum(-1))
    d = ndimage.median_filter(d, 3)
    a = np.clip((d - LO) / (HI - LO), 0, 1)

    # keep only the balloon itself: the largest blob (envelope + ropes + basket)
    lab, n = ndimage.label(ndimage.binary_dilation(a > 0.3, iterations=2))
    if n > 1:
        sizes = ndimage.sum(np.ones_like(a), lab, range(1, n + 1))
        a *= lab == (1 + int(np.argmax(sizes)))
    # drop faint specks where the plate's inpainting differs from the sky:
    # support = solid parts of the balloon, grown by a couple of pixels
    solid = a > 0.55
    lab, n = ndimage.label(solid)
    if n > 1:
        sizes = ndimage.sum(np.ones_like(a), lab, range(1, n + 1))
        solid = np.isin(lab, 1 + np.nonzero(sizes >= 12)[0])
    a *= ndimage.binary_dilation(solid, iterations=2)
    # below the envelope only the ropes and basket belong to the balloon, and
    # both are darker than the sky behind them: clear the pale sky smudges hanging around the basket
    rows = np.nonzero((a > 0.55).sum(1) > 0)[0]
    widths = (a > 0.55).sum(1)
    env_bottom = rows[0] + int(np.argmax(widths[rows[0]:]))
    env_bottom += int(np.argmax(widths[env_bottom:] < 0.2 * widths.max()))
    dark = ndimage.binary_dilation(I.mean(-1) < P.mean(-1) - 40, iterations=1)
    a[env_bottom:] *= dark[env_bottom:]
    # the envelope is near-symmetric: trim anything sticking out further on
    # one side than the other (sky smudges stuck to the outline)
    axis = np.nonzero(a[:env_bottom] > 0.55)[1].mean()
    for r in range(env_bottom):
        cols = np.nonzero(a[r] > 0.55)[0]
        if len(cols) < 4:
            continue
        reach = min(axis - cols[0], cols[-1] - axis) + 3
        lo, hi = int(np.floor(axis - reach)), int(np.ceil(axis + reach))
        a[r, :max(lo, 0)] = 0
        a[r, hi + 1:] = 0
    a = ndimage.gaussian_filter(a, 0.5)

    # un-mix the sky from the edge pixels: I = a*F + (1-a)*P
    am = np.maximum(a, 0.05)[..., None]
    F = np.clip((I - (1 - am) * P) / am, 0, 255)

    rgba = np.dstack([F, a * 255]).astype(np.uint8)
    ys, xs = np.nonzero(a > 0.02)
    rgba = rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    name = 'h' + sp['name'].split('-')[1]
    Image.fromarray(rgba).save(ROOT / f'assets/balloons/{name}.webp', quality=90, method=6)
    print(name, rgba.shape[1], 'x', rgba.shape[0])
