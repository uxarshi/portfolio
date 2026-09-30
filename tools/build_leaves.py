"""
Cut the flying-leaf sprites out of the reference sheet.

    python3 tools/build_leaves.py

Reads art/leaves_sheet.png (leaves on an off-white background, with soft
shadows and text labels) and writes public/leaves/*.webp + src/leaves.json.
The background, shadows and labels are dropped by colour: the leaves are
saturated and warm, the rest is not. Colours are nudged towards the leaves
painted in the scene, so the new ones sit in the same sunset light.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "leaves"
OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*.webp"):
    old.unlink()

MAX_SIDE = 128  # px, longest side of each sprite (near leaves are drawn up to ~110 px)

sheet = np.asarray(Image.open(ROOT / "art" / "leaves_sheet.png").convert("RGB")).astype(np.float32) / 255
H, W, _ = sheet.shape
bg = np.median(sheet[5:40, 5:40].reshape(-1, 3), axis=0)

# leaf = saturated and warm. Measured on this sheet: leaf bodies have
# saturation 0.45+ (even the pale withered one), the warm-grey drop shadows
# ~0.19, the paper and the grey labels less. Warmth (red minus blue) keeps
# anything grey out
mx = sheet.max(axis=2)
sat = (mx - sheet.min(axis=2)) / np.maximum(mx, 1e-3)
warm = sheet[..., 0] - sheet[..., 2]
alpha = np.clip((sat - 0.26) / 0.16, 0, 1) * np.clip((warm - 0.12) / 0.1, 0, 1)
# small pale highlights inside a leaf stay solid. Only small holes: a shadow's
# darker watercolour rim can enclose the whole shadow, which must stay out
solid = alpha > 0.5
holes, _ = ndi.label(ndi.binary_fill_holes(solid) & ~solid)
sizes = np.bincount(holes.ravel())
small = (sizes < 120)[holes] & (holes > 0)
alpha = np.maximum(ndi.gaussian_filter(alpha, 0.6), small)
# un-mix the background from the soft edge pixels, so no pale fringe remains
a3 = np.maximum(alpha, 0.35)[..., None]  # faint edge pixels: don't over-correct into specks
rgb = np.clip((sheet - (1 - a3) * bg) / a3, 0, 1)

# the leaves painted in the scene, as the colour target
painted = np.asarray(Image.open(ROOT / "art" / "landscape.png").convert("RGB")).astype(np.float32) / 255
spots = [(148, 375, 38, 36), (319, 461, 36, 35), (1204, 290, 34, 31), (1008, 349, 30, 25)]
px = np.concatenate([painted[y:y + h, x:x + w].reshape(-1, 3) for x, y, w, h in spots])
px = px[(px[:, 0] - px[:, 2]) > 0.35]  # just the orange of the leaves
target = px.mean(axis=0)
source = rgb[alpha > 0.9].mean(axis=0)
haze = np.array([0.99, 0.84, 0.76])  # the peachy air of the scene


def grade(c):
    # halfway to the painted leaves' colour, then a touch of the evening haze
    c = c * (1 + 0.55 * (target / source - 1))
    return np.clip(c * 0.88 + haze * 0.12, 0, 1)


# rows of the sheet (y ranges) and which ones fly: the scale comparison and
# the scattered-on-ground groups are left out
lab, n = ndi.label(ndi.binary_dilation(alpha > 0.45, iterations=2))
leaves = []
for i, sl in enumerate(ndi.find_objects(lab), 1):
    ys, xs = sl
    h, w = ys.stop - ys.start, xs.stop - xs.start
    area = (lab[sl] == i).sum()
    if area < 1500 or h < 40:
        continue  # debris, bits of text
    cy, cx = (ys.start + ys.stop) / 2, (xs.start + xs.stop) / 2
    if cy > 700 and cx > 570:
        continue  # scale comparison / scattered on ground
    leaves.append((cy, cx, i, sl))

# reading order: by row, then left to right
leaves.sort(key=lambda l: (int(l[0] // 330), l[1]))
names = ["front", "back", "edge", "angled-left", "angled-right", "top",
         "curled-slightly", "curled", "wrinkled", "torn", "spotted", "crushed", "withered",
         "turning-1", "turning-2", "turning-3", "turning-4"]
manifest = []
for k, (cy, cx, i, sl) in enumerate(leaves):
    ys, xs = sl
    pad = 6
    y0, y1 = max(0, ys.start - pad), min(H, ys.stop + pad)
    x0, x1 = max(0, xs.start - pad), min(W, xs.stop + pad)
    own = ndi.binary_dilation(lab[y0:y1, x0:x1] == i, iterations=3)
    a = alpha[y0:y1, x0:x1] * own
    c = grade(rgb[y0:y1, x0:x1])
    im = Image.fromarray((np.dstack([c, a]) * 255 + 0.5).astype(np.uint8))
    s = MAX_SIDE / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    name = names[k] if k < len(names) else f"leaf-{k + 1}"
    im.save(OUT / f"{name}.webp", quality=90, method=6, exact=True, alpha_quality=100)
    manifest.append({"name": name, "file": f"leaves/{name}.webp", "size": [im.width, im.height],
                     # edge-on and curled leaves hardly flip; flat ones turn over
                     "flat": name not in ("edge", "curled", "wrinkled", "withered")})
    print(f"  {name:16s} {im.width}x{im.height}")

(ROOT / "src" / "leaves.json").write_text(json.dumps(manifest, indent=1))
print(len(manifest), "leaves")

# contact sheet for checking
sheet_out = Image.new("RGBA", (len(manifest) * 140, 150), (238, 205, 190, 255))
for k, m in enumerate(manifest):
    im = Image.open(OUT / f"{m['name']}.webp")
    sheet_out.alpha_composite(im, (k * 140 + (140 - im.width) // 2, (150 - im.height) // 2))
sheet_out.save(ROOT / "art" / "_leaves_preview.png")
