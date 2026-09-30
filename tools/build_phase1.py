"""
Phase 1 asset build: the painting + its refined depth map.

    python3 tools/build_phase1.py              # art/landscape.png (default)
    python3 tools/build_phase1.py floor2       # the portrait version

Inputs : art/<name>.png, art/<name>_depth.png (from tools/estimate_depth.py)
Outputs: public/scene/scene.webp   the painting, near-lossless WebP
         public/scene/depth.webp   refined depth (bright = near), same size
         public/og.jpg             1200x630 social preview
         src/scene-meta.json       focus point, bubble position, girl depth
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "art"
OUT = ROOT / "public" / "scene"
OUT.mkdir(parents=True, exist_ok=True)

# Where things are in each painting (pixel coordinates in the source PNG).
PAINTINGS = {
    "landscape": {
        "balloons": [(333, 131, 434, 258), (1011, 168, 1053, 223), (1103, 274, 1147, 334), (1102, 478, 1143, 535)],
        "girl_box": (795, 592, 1000, 930),
        # painted thought bubble + its two small trailing puffs (cx, cy, rx, ry)
        "bubble": [(934, 510, 76, 49), (899, 567, 12, 10), (885, 587, 8, 7)],
        "focus": (900, 690),  # kept near screen centre
        "og_center": (880, 640),
    },
    "floor2": {
        "balloons": [(100, 125, 240, 295), (690, 165, 750, 245), (748, 338, 796, 400), (778, 718, 836, 792)],
        "girl_box": (452, 1022, 640, 1334),
        "bubble": [(580, 937, 82, 52), (545, 992, 16, 11), (531, 1013, 9, 7)],
        "focus": (548, 1090),
        "og_center": (527, 1060),
    },
}

NAME = sys.argv[1] if len(sys.argv) > 1 else "landscape"
P = PAINTINGS[NAME]

src = Image.open(ART / f"{NAME}.png").convert("RGB")
W, H = src.size
d = np.asarray(Image.open(ART / f"{NAME}_depth.png").convert("L").resize((W, H), Image.BICUBIC)).astype(np.float32) / 255.0

# ---------------------------------------------------------------- depth refine
# 1) Balloons belong to the sky, not the foreground: flatten them just in
#    front of the sky so they drift a touch but don't swim.
for x0, y0, x1, y1 in P["balloons"]:
    region = d[y0:y1, x0:x1]
    d[y0:y1, x0:x1] = np.minimum(region, 0.06 + region * 0.08)

# 2) The girl is a rigid card at a single depth, so her silhouette never warps.
x0, y0, x1, y1 = P["girl_box"]
box = d[y0:y1, x0:x1]
girl = ndi.binary_fill_holes(ndi.binary_closing(box > 0.28, iterations=3))
lab, n = ndi.label(girl)
if n:
    girl = lab == (1 + int(np.argmax(ndi.sum(girl, lab, range(1, n + 1)))))
GIRL_DEPTH = float(np.median(d[y1 - 22:y1 - 8, x0 + 30:x1 - 90]))  # the path under her feet
box[girl] = GIRL_DEPTH
d[y0:y1, x0:x1] = box

# 3) The painted thought bubble sits at the girl's depth (the HTML bubble is
#    drawn on top of it).
yy, xx = np.mgrid[0:H, 0:W]
for cx, cy, rx, ry in P["bubble"]:
    d[((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 < 1.0] = GIRL_DEPTH

# 4) Grow near objects a few pixels outward, then soften. This pushes the
#    depth edge into the background so stretching happens on soft sky/path
#    pixels instead of on the girl's outline.
d = ndi.grey_dilation(d, size=(7, 7))
d = ndi.gaussian_filter(d, 2.2)

# ------------------------------------------------------------------ export
src.save(OUT / "scene.webp", quality=95, method=6)
Image.fromarray((np.clip(d, 0, 1) * 255).astype(np.uint8)).save(OUT / "depth.webp", lossless=True, method=6)

# Social preview: 1200x630 around the girl and bubble
ox, oy = P["og_center"]
cw = min(W, int(H * 1200 / 630))
ch = int(cw * 630 / 1200)
left = min(max(0, ox - cw // 2), W - cw)
top = min(max(0, oy - ch // 2), H - ch)
src.crop((left, top, left + cw, top + ch)).resize((1200, 630), Image.LANCZOS).save(
    ROOT / "public" / "og.jpg", quality=88, optimize=True, progressive=True
)

bx, by, brx, bry = P["bubble"][0]
meta = {
    "size": [W, H],
    "focus": list(P["focus"]),
    "bubble": [bx, by, brx * 2, bry * 2],  # centre x, centre y, w, h of the painted bubble
    "girlDepth": round(GIRL_DEPTH, 4),
}
(ROOT / "src" / "scene-meta.json").write_text(json.dumps(meta, indent=2))
print(json.dumps(meta))
