"""
Phase 2: split the painting into layers with the hidden parts painted in.

    python3 tools/build_layers.py

Needs art/landscape.png, art/landscape_depth.png and tools/lama_fp32.onnx
(see README). Writes public/layers/*.webp, src/layers.json (positions, depth
planes, draw order), art/_layers_preview.png (contact sheet) and
public/scene/scene.webp + public/og.jpg (the still image and social preview,
as the scene is now; run this after build_phase1.py, which writes plain ones).

Layers, back to front:
  sky · city (distant city + river) · balloon-1..4 · bird-1..n · trees (trees
  + hedge) · path (pavement, railing, flower bed) · lamps (lamps + benches) ·
  cat-orange/tabby/white · girl (+ the little thought puffs)
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent / "layers"))
from inpaint import inpaint  # noqa: E402
import masks as M  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "art"
OUT = ROOT / "public" / "layers"
OUT.mkdir(parents=True, exist_ok=True)
for old in list(OUT.glob("*.webp")):
    old.unlink()

img = np.asarray(Image.open(ART / "landscape.png").convert("RGB")).astype(np.float32) / 255.0
D = np.asarray(Image.open(ART / "landscape_depth.png").convert("L")).astype(np.float32) / 255.0
H, W, _ = img.shape
print("masks…")
m = M.build_masks(img, D)
b = lambda a, t=0.5: a > t  # noqa: E731
grow = lambda a, n: ndi.binary_dilation(a, iterations=n)  # noqa: E731

cats = b(m["cat-orange"], 0.05) | b(m["cat-tabby"], 0.05) | b(m["cat-white"], 0.05)
girl = b(m["girl"], 0.05) | b(m["bubble"])
lampbench = b(m["lamps"], 0.05) | b(m["benches"], 0.05)
balloons = np.any([bm > 0.05 for bm in m["balloons"]], axis=0)
trees, path = b(m["trees"]), b(m["path"])
yy, xx = np.mgrid[0:H, 0:W]

# ── plates: remove things front to back, painting in what was behind ──────────
CACHE = ART / "_plates.npz"  # delete (or pass --fresh) to re-run the inpainting
if CACHE.exists() and "--fresh" not in sys.argv:
    print("plates: using cache", CACHE.name)
    c = np.load(CACHE)
    P1, P2, P3, P4 = (c[k].astype(np.float32) / 255.0 for k in ("P1", "P2", "P3", "P4"))
    v = int(c["v"]) if "v" in c else 1
    # later fixes to the cat cut-outs: paint what they gained out of the path
    patches = []
    if v < 2:  # the white cat's tail
        patches.append(grow(b(m["cat-white"], 0.05), 4) & (xx > 1350) & (yy > 922))
    if v < 3:  # the tabby's ears, muzzle, chest and paws
        patches.append(grow(b(m["cat-tabby"], 0.05), 4))
    for hole in patches:
        print("plates: painting out a cat's newly cut-out parts…")
        P1 = inpaint(P1, hole)
        P2 = inpaint(P2, hole)
    if patches:
        q = lambda a: (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)  # noqa: E731
        np.savez_compressed(CACHE, P1=q(P1), P2=q(P2), P3=q(P3), P4=q(P4), v=3)
else:
    print("plate 1: girl + cats…")
    P1 = inpaint(img, grow(girl | cats, 4))
    print("plate 2: lamps + benches…")
    P2 = inpaint(P1, grow(lampbench, 4))
    print("plate 3: behind trees and railing (rims only)…")
    back = ~(trees | path)
    P3 = inpaint(P2, (trees | path) & grow(back, 48) & ~balloons)
    print("plate 4: sky without balloons, birds, leaves…")
    P4 = inpaint(P3, grow(balloons | m["birds_raw"] | m["leaves"], 3))
    q = lambda a: (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)  # noqa: E731
    np.savez_compressed(CACHE, P1=q(P1), P2=q(P2), P3=q(P3), P4=q(P4), v=3)

# the river behind the railing: LaMa tends to redraw the posts it was asked to
# remove, and the river is just horizontal bands of reflection, so fill each
# row from the clean river on either side instead
curb_x, curb_y = np.array(M.CURB, np.float32).T
behind_rail = (yy < np.interp(xx, curb_x, curb_y)) & (yy > 740) & (xx < 860)
river_ok = behind_rail & ~grow(path | (m["path"] > 0.02) | girl | cats, 3)
# only repaint what the opaque railing covers at rest; where the path layer is
# see-through (its soft edges, the far end of the railing) the plate must stay
# as it was, or the fill would show even when nothing moves
# the railing's soft 1-2 px rim (round the post knobs and top rail) goes with
# the railing: made solid in the path layer, so it can be filled here too
# without showing at rest, and no outline of the posts is left in the water
rail_rim = behind_rail & (m["path"] > 0.02) & grow(m["path"] > 0.5, 2) & ~grow(girl | cats, 3)
to_fill = (behind_rail & (m["path"] > 0.5) & ~grow(girl | cats, 3)) | rail_rim
last = None
for y in range(741, int(curb_y.max()) + 1):
    xs = np.nonzero(river_ok[y])[0]
    if len(xs) > 40:
        last = np.stack([np.interp(np.arange(W), xs, P4[y, xs, c]) for c in range(3)], axis=1)
    if last is not None:
        P4[y, to_fill[y]] = last[to_fill[y]]
soft_fill = (ndi.gaussian_filter(to_fill.astype(np.float32), 2) * ((m["path"] > 0.5) | rail_rim))[..., None]
P4 = P4 * (1 - soft_fill) + np.dstack([ndi.gaussian_filter(P4[..., c], (0.8, 5)) for c in range(3)]) * soft_fill

# plate 1 may only differ from the painting near the girl and cats, and plate
# 2 also near the lamps and benches. Cached plates can predate tighter
# cut-outs (the background by her scarf, the tabby's tail tip against a bench
# leg), so everything else comes back from the painting itself
keep1 = ~grow(girl | cats, 4)
P1[keep1] = img[keep1]
keep2 = keep1 & ~grow(lampbench, 4)
P2[keep2] = img[keep2]

# where the tabby was (it's gone from the scene), the painted-in pavement kept
# a dark smudge from its paws and shadow: even out anything much darker than
# the pavement around it
# (including the pavement between its legs, where its shadow was)
tabby_area = (grow(b(m["cat-tabby"], 0.05), 6) | ((xx > 1015) & (xx < 1090) & (yy > 858) & (yy < 890)))
tabby_area &= ~b(m["benches"], 0.3) & ~b(m["lamps"], 0.3)
for P in (P1, P2):
    med = np.dstack([ndi.median_filter(P[..., c], 15) for c in range(3)])
    stain = tabby_area & (P.mean(axis=2) < med.mean(axis=2) - 0.06)
    a = np.clip(ndi.gaussian_filter(grow(stain, 1).astype(np.float32), 1.0), 0, 1)[..., None] * tabby_area[..., None]
    P[:] = P * (1 - a) + med * a

# above y 830 by the bench leg was never tabby (its tail ends there; above is
# the bench's leg, the hedge and the lamp base), so keep the painting there
not_tabby = tabby_area & (xx > 1066) & (yy < 830)
# ...except the bench's thin front leg itself, which is part of the bench
# sprite: behind it, close the dark line up with the colours on either side
leg_line = grow((img.mean(axis=2) < 0.46) & (xx >= 1079) & (xx <= 1084) & (yy >= 806) & (yy < 830), 1)
no_leg = np.dstack([ndi.grey_closing(img[..., c], size=(1, 9)) for c in range(3)])
for P in (P1, P2):
    P[not_tabby] = img[not_tabby]
    P[not_tabby & leg_line] = no_leg[not_tabby & leg_line]

# the far end of the railing and its flower bed (by the girl) are too thin
# and far for the automatic path mask, so they'd sit in the river layer and
# drift apart from the rest of the railing. Pick them out by colour (iron,
# leaves and flowers against the pale water), move them to the path layer,
# and fill the river behind them from the clean water on either side
lum0 = img.mean(axis=2)
sat0 = (img.max(axis=2) - img.min(axis=2)) / np.maximum(img.max(axis=2), 1e-3)
far_rail = ((lum0 < 0.62) | (img[..., 1] > img[..., 0]) | (sat0 > 0.33))
far_rail &= (xx > 600) & (xx < 860) & (yy > 762) & (yy < np.interp(xx, curb_x, curb_y) + 6)
far_rail &= ~b(m["path"]) & ~grow(girl, 2)
far_rail = ndi.binary_closing(far_rail, iterations=2)
lab_f, n_f = ndi.label(far_rail)
far_rail = np.isin(lab_f, 1 + np.nonzero(ndi.sum(far_rail, lab_f, range(1, n_f + 1)) > 60)[0])
far_rail = grow(ndi.binary_fill_holes(far_rail), 1)
water_ok = (xx < 860) & (yy > 741) & ~far_rail & ~b(m["path"], 0.3) & ~grow(girl, 3)
last = None
for y in range(762, 880):
    xs = np.nonzero(water_ok[y])[0]
    if len(xs) > 40:
        last = np.stack([np.interp(np.arange(W), xs, P4[y, xs, c]) for c in range(3)], axis=1)
    if last is not None:
        P4[y, far_rail[y]] = last[far_rail[y]]

# the background between her scarf and dress was never hidden, in any plate
gap = m["girl_gap"]
for P in (P3, P4):
    P[gap] = img[gap]

# background depth: the depth map with every standalone object removed, so the
# path and trees move by their own depth, and objects stand on it
objects = grow(girl | cats | lampbench | balloons | m["birds_raw"], 6)
known = (~objects).astype(np.float32)
Dbg, todo = D.copy(), objects.copy()
for sig in (4, 10, 25, 60):  # fill from the smallest neighbourhood with enough support
    den = ndi.gaussian_filter(known, sig)
    est = ndi.gaussian_filter(D * known, sig) / np.maximum(den, 1e-4)
    take = todo & ((den > 0.2) | (sig == 60))
    Dbg[take] = est[take]
    todo &= ~take
Dbg = ndi.gaussian_filter(Dbg, 3)
# the railing and flower bed on the left stand upright on the curb: give each
# column the depth of the pavement at the curb, so the posts don't lean (the
# raw depth map mixes in the far river between the bars)
for x in range(int(curb_x[-1]) + 1):
    cy = int(np.interp(x, curb_x, curb_y))
    Dbg[700:cy, x] = Dbg[min(H - 1, cy + 4), x]
Image.fromarray((np.clip(Dbg, 0, 1) * 255).astype(np.uint8)).resize((W // 2, H // 2), Image.LANCZOS).save(
    OUT / "depth.webp", lossless=True, method=6)


def ground_at(x0, x1, y):
    """Depth of the pavement just below an object's base (x0..x1 at row y)."""
    y = int(y)
    win = Dbg[min(H - 2, y + 2):min(H, y + 8), int(x0):int(x1)]
    return round(float(np.median(win)), 4)


# ── helpers ──────────────────────────────────────────────────────────────────
layers = []


def save(name, rgb, alpha, depth, kind="static", quality=90, extra=None):
    alpha = np.clip(alpha, 0, 1)
    ys, xs = np.nonzero(alpha > 0.004)
    if len(xs) == 0:
        return
    pad = 2
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(W, xs.max() + 1 + pad), min(H, ys.max() + 1 + pad)
    rgba = np.dstack([rgb[y0:y1, x0:x1], alpha[y0:y1, x0:x1]])
    im = Image.fromarray((rgba * 255 + 0.5).astype(np.uint8))
    # exact=True keeps colour under transparent pixels (no dark fringes)
    im.save(OUT / f"{name}.webp", quality=quality, method=6, exact=True, alpha_quality=100)
    entry = {"name": name, "file": f"layers/{name}.webp", "rect": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)],
             "depth": depth, "kind": kind}
    if extra:
        entry.update(extra)
    layers.append(entry)
    print(f"  {name:12s} {x1 - x0:4d}x{y1 - y0:<4d} {(OUT / f'{name}.webp').stat().st_size // 1024:4d} KB  depth={depth}")


def soft(a, s=1.0):
    return np.clip(ndi.gaussian_filter(a.astype(np.float32), s), 0, 1)


print("export…")

# depth: a number = the layer moves rigidly at that depth; "map" = each pixel
# moves by the background depth map (public/layers/depth.webp)

# loose leaves: the painted ones are replaced by the drifting sprites from
# tools/build_leaves.py, so they are painted out of the sky (and of the still
# image below). The tiny specks the leaf mask also caught go back in.
leaf_lab, _ = ndi.label(m["leaves"])
leaf_orange = (img[..., 0] - img[..., 2]) > 0.35  # real leaves have ~100+ such px, cloud bits none
leaf_ids, specks = [], np.zeros((H, W), bool)
for i, sl in enumerate(ndi.find_objects(leaf_lab), 1):
    if (leaf_orange[sl] & (leaf_lab[sl] == i)).sum() >= 40:
        leaf_ids.append(i)
    else:
        specks |= leaf_lab == i
# where LaMa's fill of a leaf hole strays from a plain smooth fill of the sky
# around it (it once left a grey smear), use that
known = (~grow(m["leaves"], 2)).astype(np.float32)
smooth_sky = np.dstack([ndi.gaussian_filter(img[..., c] * known, 7) for c in range(3)]) / np.maximum(
    ndi.gaussian_filter(known, 7), 1e-4)[..., None]
leaf_holes = np.zeros((H, W), bool)
for i in leaf_ids:
    hole = grow(leaf_lab == i, 2)
    leaf_holes |= hole
    if np.abs(P4[hole] - smooth_sky[hole]).mean() > 0.035:
        a = soft(hole, 1.5)[..., None]
        P4 = P4 * (1 - a) + smooth_sky * a
        print(f"  leaf hole {i}: smooth fill instead of LaMa")
sky_rgb = P4.copy()
sky_rgb[specks] = img[specks]

# sky: opaque, everything else painted out
save("sky", sky_rgb, np.ones((H, W)), 0.0, kind="sky", quality=88)

# distant city + river: soft top edge just above the tallest spire
city_alpha = np.clip((yy - 588) / 34.0, 0, 1)
# where the river ripples: the water only. The far end of the railing and its
# flower bed are too thin and distant to have a layer of their own, so they
# sit in this one and must stay still
RIVER = (0, 742, 860, 90)
rv = P4[RIVER[1]:RIVER[1] + RIVER[3], RIVER[0]:RIVER[0] + RIVER[2]]
ry, rx = np.mgrid[RIVER[1]:RIVER[1] + RIVER[3], RIVER[0]:RIVER[0] + RIVER[2]]
rlum = rv.mean(axis=2)
rsat = (rv.max(axis=2) - rv.min(axis=2)) / np.maximum(rv.max(axis=2), 1e-3)
rail = ((rlum < 0.62) | (rv[..., 1] > rv[..., 0]) | (rsat > 0.33)) & (rx > 600) & (ry > 762)
rail = ndi.binary_closing(rail, iterations=3)
lab_r, n_r = ndi.label(rail)
rail = np.isin(lab_r, 1 + np.nonzero(ndi.sum(rail, lab_r, range(1, n_r + 1)) > 150)[0])
rail = ndi.binary_dilation(ndi.binary_fill_holes(rail), iterations=3)
water = 1 - soft(rail, 1.5)
Image.fromarray((water * 255 + 0.5).astype(np.uint8)).save(OUT / "water.webp", lossless=True, method=6)
save("city", P4, city_alpha, 0.03, kind="city", quality=88,
     extra={"river": list(RIVER), "waterMask": "layers/water.webp"})

for i, bm in enumerate(m["balloons"], 1):
    save(f"balloon-{i}", img, bm, round(0.08 - 0.01 * i, 3), kind="balloon")

# birds: one sprite each; alpha from how much darker than the sky they are
lum = img.mean(axis=2)
sky_lum = ndi.median_filter(lum, 25)
lab, n = ndi.label(grow(m["birds_raw"], 3))
bird_i = 0
for sl in ndi.find_objects(lab):
    if (sl[0].stop - sl[0].start) * (sl[1].stop - sl[1].start) < 60:
        continue
    bird_i += 1
    region = np.zeros((H, W), bool)
    region[sl] = True
    a = np.clip((sky_lum - lum - 0.02) / 0.10, 0, 1) * region * grow(m["birds_raw"], 2)
    save(f"bird-{bird_i}", img, soft(a, 0.5), 0.09, kind="bird")

# the still image shown before WebGL starts: the painting without its loose
# leaves (and without the tabby, below), so the canvas fading in over it matches
plate = sky_rgb * (1 - city_alpha[..., None]) + P4 * city_alpha[..., None]
a = soft(leaf_holes, 1.5)[..., None]
still = img * (1 - a) + plate * a

# trees + hedge: lamps/benches/girl/cats painted out, and the layer extended a
# little under everything in front of it so no gap opens when things move.
# Not under the girl above the horizon: there she stands against sky, and the
# painted-in patch would slide out from behind her.
front_of_trees = (girl & (yy > 700)) | cats | lampbench | path
t_alpha = np.maximum(m["trees"], soft(grow(trees, 40) & front_of_trees & (xx > 845), 2))
# how much each part of the trees sways: more the higher above the ground
# (where the trunks meet the hedge), nothing on the traced trunks and
# branches, the distant lavender buildings or the hedge
sway = np.clip((760 - yy) / 450.0, 0, 1) ** 2
unswayed = np.zeros((H, W), np.uint8)
for line in M.TRUNKS:
    for (xa, ya, wa), (xb, yb, wb) in zip(line, line[1:]):
        for t in np.linspace(0, 1, 12):
            cv2.circle(unswayed, (round(xa + (xb - xa) * t), round(ya + (yb - ya) * t)), round(wa + (wb - wa) * t) + 1, 1, -1)
unswayed = unswayed.astype(bool) | ((P2[..., 2] > P2[..., 0]) & (yy > 600))
sway *= 1 - soft(unswayed, 1.5)
save("trees", P2, t_alpha, "map", kind="trees", quality=88)
tx, ty, tw, th = layers[-1]["rect"]
Image.fromarray((np.clip(sway[ty:ty + th, tx:tx + tw], 0, 1) * 255 + 0.5).astype(np.uint8)).save(
    OUT / "sway.webp", lossless=True, method=6)
layers[-1]["swayMap"] = "layers/sway.webp"

# path, railing and flower bed
front_of_path = girl | cats | lampbench
p_alpha = np.maximum(m["path"], soft(grow(path, 40) & front_of_path, 2))
p_alpha = np.maximum(p_alpha, soft(grow(gap, 2), 1))  # the gap by her scarf, solid
p_alpha = np.maximum(p_alpha, np.clip(ndi.gaussian_filter(far_rail.astype(np.float32), 0.7), 0, 1))  # far railing
p_alpha = np.maximum(p_alpha, rail_rim)
save("path", P2, p_alpha, "map", kind="path", quality=88)

# lamps and benches: one sprite each, standing where they touch the ground.
# Taken from plate 1, so a bench leg continues behind the cat sitting by it.
lamp_px, bench_px = m["lamps"], m["benches"]
for i, (x0, y0, x1, y1) in enumerate(M.LAMPS, 1):
    a = np.zeros((H, W), np.float32)
    a[y0 - 2:y1 + 2, x0 - 2:x1 + 2] = lamp_px[y0 - 2:y1 + 2, x0 - 2:x1 + 2]
    save(f"lamp-{i}", P1, a, ground_at(x0, x1, y1), kind="lamp", extra={"head": list(M.LAMP_HEADS[i - 1])})
# the small bench's front-left leg: a thin iron line coming down from the seat
# to where the tabby's tail tip was. The bench cut-out missed it (it merged
# with the tail), so take its dark pixels from the painting itself
leg_box = (slice(806, 825), slice(1079, 1084))  # the iron only, not the old tail tip
bench_leg = np.zeros((H, W), np.float32)
bench_leg[leg_box] = np.clip((0.5 - img[leg_box].mean(axis=2)) / 0.1, 0, 1)
bench_leg *= ~(m["cat-tabby"] > 0.5)
bench_rgb = P1.copy()
bench_rgb[bench_leg > 0] = img[bench_leg > 0]

for i, (x0, y0, x1, y1) in enumerate(M.BENCHES, 1):
    a = np.zeros((H, W), np.float32)
    a[y0 - 2:y1 + 2, x0 - 2:x1 + 2] = bench_px[y0 - 2:y1 + 2, x0 - 2:x1 + 2]
    if i == 2:
        a = np.maximum(a, bench_leg)
    save(f"bench-{i}", bench_rgb, a, ground_at(x0, x1, y1), kind="bench")

# the tabby (the grey cat by the small bench) is painted out of the plates and
# replaced by a new grey cat, cut from art/cat_grey.png (a watercolour on
# white), standing where the tabby stood and looking up towards the girl
def new_grey_cat():
    src = np.asarray(Image.open(ART / "cat_grey.png").convert("RGB")).astype(np.float32) / 255
    # background: near white and connected to the border. The palest fur is
    # much warmer (blue <= ~0.8), so the blue channel sets the soft edge
    a = np.clip((0.975 - src[..., 2]) / 0.1, 0, 1)
    lab, _ = ndi.label(a < 0.5)
    border = np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    bg = np.isin(lab, border[border > 0])
    a = np.where(bg, a, 1.0)
    # only the cat itself: drop stray marks on the paper around it
    fg, n = ndi.label(a > 0.5)
    if n > 1:
        keep = 1 + int(np.argmax(ndi.sum(np.ones_like(a), fg, range(1, n + 1))))
        a *= ndi.binary_dilation(fg == keep, iterations=3)
    a = ndi.gaussian_filter(a, 1.0)
    # un-mix the white from the soft edge
    a3 = np.maximum(a, 0.35)[..., None]
    rgb = np.clip((src - (1 - a3)) / a3, 0, 1)
    ys, xs = np.nonzero(a > 0.05)
    crop = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
    return rgb[crop], a[crop], (xs.min(), ys.min())


GREY_H = 66  # px in the painting, ears/tail top to paws (the tabby was ~60 incl. tail)
GREY_FEET = (1010, 892)  # left end and bottom of its paws (tail tip then clears the bench leg and lamp base)
GREY_HR = 3  # its texture is drawn at 3x the painting's resolution, so it stays crisp on sharp screens
g_rgb, g_a, g_off = new_grey_cat()
k = GREY_H / g_a.shape[0]
gw, gh = max(1, round(g_a.shape[1] * k)), GREY_H
gx0, gy0 = GREY_FEET[0], GREY_FEET[1] - gh
# the sprite's rect in the painting: the cat plus room for its shadow
G_PAD = 10
grect = [gx0 - G_PAD, gy0 - 2, gw + 2 * G_PAD, gh + 8]
R = GREY_HR
rgba = np.dstack([g_rgb, g_a])
hi = np.asarray(Image.fromarray((rgba * 255 + 0.5).astype(np.uint8)).resize((gw * R, gh * R), Image.LANCZOS)).astype(
    np.float32) / 255
# the scene's evening light: a little less contrast, warmer, a touch of haze
c = hi[..., :3]
c = (c - 0.5) * 0.95 + 0.5 + np.array([0.02, 0.0, -0.03])
c = np.clip(c * 0.94 + np.array([0.99, 0.84, 0.76]) * 0.06, 0, 1)
# a soft brown outline (about one painting pixel), like the painted cats have
sa = hi[..., 3]
edge = np.clip(sa - ndi.grey_erosion(sa, size=(R + 1, R + 1)), 0, 1) * (sa > 0.4)
c = c * (1 - 0.5 * edge[..., None]) + np.array([0.42, 0.3, 0.27]) * 0.5 * edge[..., None]
# a soft lavender shadow on the pavement under its paws, like the other cats
hy, hx = np.mgrid[0:grect[3] * R, 0:grect[2] * R]
px_, py_ = grect[0] + (hx + 0.5) / R, grect[1] + (hy + 0.5) / R
sh = np.exp(-(((px_ - (gx0 + gw * 0.48)) / (gw * 0.47)) ** 2 + ((py_ - (GREY_FEET[1] - 1.5)) / 3.2) ** 2))
sh = np.clip(sh * 1.3, 0, 1) * 0.42
g_hi_rgb = np.zeros((grect[3] * R, grect[2] * R, 3), np.float32) + np.array([0.62, 0.55, 0.62])
g_hi_a = sh.astype(np.float32)
oy, ox = 2 * R, G_PAD * R
ca = sa[..., None]
g_hi_rgb[oy:oy + gh * R, ox:ox + gw * R] = c * ca + g_hi_rgb[oy:oy + gh * R, ox:ox + gw * R] * (1 - ca)
g_hi_a[oy:oy + gh * R, ox:ox + gw * R] = 1 - (1 - sa) * (1 - sh[oy:oy + gh * R, ox:ox + gw * R])
g_hi = Image.fromarray((np.dstack([g_hi_rgb, g_hi_a]) * 255 + 0.5).astype(np.uint8))
# painting-resolution copy, for the still image
lo = np.asarray(g_hi.resize((grect[2], grect[3]), Image.LANCZOS)).astype(np.float32) / 255
grey_rgb, grey_a = np.zeros((H, W, 3), np.float32), np.zeros((H, W), np.float32)
grey_rgb[grect[1]:grect[1] + grect[3], grect[0]:grect[0] + grect[2]] = lo[..., :3]
grey_a[grect[1]:grect[1] + grect[3], grect[0]:grect[0] + grect[2]] = lo[..., 3]


def to_painting(x, y):
    """cat_grey.png px -> painting px"""
    return [round(gx0 + (x - g_off[0]) * k, 1), round(gy0 + (y - g_off[1]) * k, 1)]


# tail: leaves the body at ~(1180, 430) in the source image, tip at ~(1235, 95)
grey_tail = to_painting(1180, 430) + to_painting(1235, 95)

for name in ("cat-orange", "cat-grey", "cat-white"):
    if name == "cat-grey":
        g_hi.save(OUT / "cat-grey.webp", quality=92, method=6, exact=True, alpha_quality=100)
        layers.append({"name": name, "file": "layers/cat-grey.webp", "rect": grect,
                       "depth": ground_at(gx0, gx0 + gw, GREY_FEET[1] - 4), "kind": "cat", "tail": grey_tail})
        print(f"  {name:12s} {grect[2]}x{grect[3]} (texture {g_hi.width}x{g_hi.height})")
        continue
    x0, y0, x1, y1 = M.CATS[name]
    save(name, img, m[name], ground_at(x0, x1, y1), kind="cat", extra={"tail": list(M.TAILS[name])})

girl_depth = ground_at(830, 900, M.GIRL[3] - 4)  # the pavement under her feet
save("girl", img, m["girl"], girl_depth, kind="girl", quality=92)

# the still image, where the tabby was: what the layers beneath it show
gone = grow(b(m["cat-tabby"], 0.05), 5)
ys, xs = np.nonzero(gone)
by0, by1, bx0, bx1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
rest = np.zeros((by1 - by0, bx1 - bx0, 3), np.float32)
for L in layers:
    lx, ly, lw, lh = L["rect"]
    ox0, oy0, ox1, oy1 = max(lx, bx0), max(ly, by0), min(lx + lw, bx1), min(ly + lh, by1)
    if ox0 >= ox1 or oy0 >= oy1:
        continue
    im = np.asarray(Image.open(ROOT / "public" / L["file"]).convert("RGBA")).astype(np.float32) / 255
    part = im[oy0 - ly:oy1 - ly, ox0 - lx:ox1 - lx]
    dst = rest[oy0 - by0:oy1 - by0, ox0 - bx0:ox1 - bx0]
    dst[:] = dst * (1 - part[..., 3:]) + part[..., :3] * part[..., 3:]
a = soft(gone, 1.5)[by0:by1, bx0:bx1, None]
still[by0:by1, bx0:bx1] = still[by0:by1, bx0:bx1] * (1 - a) + rest * a
# and the new grey cat standing there
ga = grey_a[..., None]
still = still * (1 - ga) + grey_rgb * ga
still_im = Image.fromarray((np.clip(still, 0, 1) * 255 + 0.5).astype(np.uint8))
still_im.save(ROOT / "public" / "scene" / "scene.webp", quality=95, method=6)
# the social preview (1200x630 around the girl and bubble), from the same
# picture, so a shared link shows the scene as it is now
ox, oy = 880, 640
cw = min(W, int(H * 1200 / 630))
ch = int(cw * 630 / 1200)
left, top = min(max(0, ox - cw // 2), W - cw), min(max(0, oy - ch // 2), H - ch)
still_im.crop((left, top, left + cw, top + ch)).resize((1200, 630), Image.LANCZOS).save(
    ROOT / "public" / "og.jpg", quality=88, optimize=True, progressive=True)

# painted-in lamp heads that stayed in the hedge (far lamps), for glow/click
far_heads = [list(h) for h in M.LAMP_HEADS[len(M.LAMPS):]]

cx, cy, rx, ry = M.BUBBLE
manifest = {
    "size": [W, H],
    "focus": [900, 690],
    "bubble": [cx, cy, rx * 2, ry * 2],
    "girlDepth": girl_depth,
    "depthMap": "layers/depth.webp",
    "farLampHeads": far_heads,
    "layers": layers,
}
(ROOT / "src" / "layers.json").write_text(json.dumps(manifest, indent=1))

# ── contact sheet ─────────────────────────────────────────────────────────────
tile_w = 360
sheet_items = []
for L in layers:
    im = Image.open(ROOT / "public" / L["file"]).convert("RGBA")
    k = min(tile_w / im.width, 220 / im.height, 1.0)
    im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    sheet_items.append((L["name"], im))
cols = 4
rows = (len(sheet_items) + cols - 1) // cols
sheet = Image.new("RGB", (cols * (tile_w + 16) + 16, rows * 262 + 16), (250, 246, 242))
dr = ImageDraw.Draw(sheet)
for i, (name, im) in enumerate(sheet_items):
    cx0, cy0 = 16 + (i % cols) * (tile_w + 16), 16 + (i // cols) * 262
    checker = Image.new("RGB", (tile_w, 222), (255, 255, 255))
    cd = ImageDraw.Draw(checker)
    for yy_ in range(0, 222, 12):
        for xx_ in range(0, tile_w, 12):
            if (xx_ // 12 + yy_ // 12) % 2:
                cd.rectangle([xx_, yy_, xx_ + 11, yy_ + 11], fill=(226, 226, 230))
    checker.paste(im, ((tile_w - im.width) // 2, (222 - im.height) // 2), im)
    sheet.paste(checker, (cx0, cy0))
    dr.text((cx0, cy0 + 226), name, fill=(90, 70, 60))
sheet.save(ART / "_layers_preview.png")
total = sum((ROOT / "public" / L["file"]).stat().st_size for L in layers)
print(f"{len(layers)} layers, {total // 1024} KB total")
