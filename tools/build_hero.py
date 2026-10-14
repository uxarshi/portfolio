"""Cut the living hero out of the video's first frame.

Reads assets/hero.jpg (frame 0 of "final intro video.mp4") and writes
assets/hero/plate.jpg (the frame with balloons, cats and girl painted out),
one webp sprite per moving thing, and assets/hero/scene.json (sprite rects,
anchors and lamp-glow spots, all in frame pixels).

Run: python3 tools/build_hero.py [--preview]
Needs opencv-python-headless, onnxruntime, numpy, and the LaMa model from
../my website/tools/lama_fp32.onnx.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parent.parent
FRAME = ROOT / "assets/hero.jpg"
OUT = ROOT / "assets/hero"
GIRL_CUTOUT = ROOT / "new images/Wind-Swept Hijabi Girl Illustration.png"
LAMA = ROOT.parent / "my website/tools/lama_fp32.onnx"
PREVIEW = "--preview" in sys.argv

# The girl cutout is the same drawing as the girl in the frame; this maps it
# onto the frame (found with SIFT + RANSAC).
GIRL_M = np.array([[0.36916, 0.0002, 977.30], [-0.0002, 0.36916, 459.62]], np.float32)

# Boxes (x0, y0, x1, y1) around things cut straight from the frame.
BALLOONS = [
    (0, 12, 70, 170),
    (152, 56, 248, 182),
    (355, 130, 455, 258),
    (632, 242, 713, 346),
    (1385, 297, 1459, 396),
    (1488, 22, 1606, 176),
]
CATS = {
    "cat-orange": (628, 878, 786, 1062),
    "cat-tabby": (1340, 852, 1470, 990),
    "cat-white": (1838, 902, 1920, 1052),
}
# Cat tails: the box that holds the tail, and where it leaves the body.
TAILS = {
    "cat-orange": {"box": (636, 882, 686, 958), "base": (660, 958)},
    "cat-tabby": {"box": (1428, 855, 1464, 922), "base": (1445, 922)},
}
# Lamp glass centres and rough glass size, nearest lamp first.
LAMPS = [
    (1860, 345, 70), (1528, 532, 40), (1466, 615, 26), (1403, 640, 24),
    (1365, 668, 20), (1327, 695, 17), (1298, 710, 15), (1270, 722, 13),
    (1243, 736, 11), (1220, 746, 10),
]


def grabcut_rect(img, box, iters=8):
    x0, y0, x1, y1 = box
    pad = 12
    X0, Y0 = max(0, x0 - pad), max(0, y0 - pad)
    X1, Y1 = min(img.shape[1], x1 + pad), min(img.shape[0], y1 + pad)
    crop = img[Y0:Y1, X0:X1]
    mask = np.zeros(crop.shape[:2], np.uint8)
    rect = (x0 - X0, y0 - Y0, min(x1, X1 - 1) - x0, min(y1, Y1 - 1) - y0)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(crop, mask, rect, bgd, fgd, iters, cv2.GC_INIT_WITH_RECT)
    fg = np.isin(mask, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    full = np.zeros(img.shape[:2], np.uint8)
    full[Y0:Y1, X0:X1] = largest(fg)
    return full


def grabcut_prior(img, prior, band=7, iters=6):
    """Refine a rough mask: its eroded core is certain, a band around its edge is a guess."""
    k = np.ones((3, 3), np.uint8)
    core = cv2.erode(prior, k, iterations=band)
    outer = cv2.dilate(prior, k, iterations=band)
    mask = np.full(prior.shape, cv2.GC_BGD, np.uint8)
    mask[outer > 0] = cv2.GC_PR_BGD
    mask[prior > 0] = cv2.GC_PR_FGD
    mask[core > 0] = cv2.GC_FGD
    ys, xs = np.nonzero(outer)
    y0, y1, x0, x1 = ys.min() - 4, ys.max() + 5, xs.min() - 4, xs.max() + 5
    sub = mask[y0:y1, x0:x1].copy()
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img[y0:y1, x0:x1], sub, None, bgd, fgd, iters, cv2.GC_INIT_WITH_MASK)
    out = np.zeros_like(prior)
    out[y0:y1, x0:x1] = np.isin(sub, (cv2.GC_FGD, cv2.GC_PR_FGD))
    return largest(out)


def largest(m):
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    if n <= 1:
        return m.astype(np.uint8)
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    keep = (lab == i).astype(np.uint8)
    # fill pinholes
    inv = 1 - keep
    n2, lab2, st2, _ = cv2.connectedComponentsWithStats(inv)
    for j in range(1, n2):
        x, y, w, h, a = st2[j]
        if a < 400 and x > 0 and y > 0 and x + w < m.shape[1] and y + h < m.shape[0]:
            keep[lab2 == j] = 1
    return keep


def restore_hood(img, m):
    """The registered cutout sits a few px low on the head, so the mask lost
    the hood's top outline and the little peak over her forehead (~1111, 486).
    Around the head, take back every non-sky pixel (hood and its outline) that lie
    within a few px of the mask."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(int)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    yy, xx = np.mgrid[0:m.shape[0], 0:m.shape[1]]
    head = (xx > 1070) & (xx < 1200) & (yy > 465) & (yy < 620)
    sky = (h >= 4) & (h <= 36) & (s > 55) & (v > 170)   # warm sunset sky (and skin, already inside)
    hood = ~sky
    near = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=7) > 0
    grown = m.astype(bool) | (head & near & hood)
    grown = cv2.morphologyEx(grown.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return largest(grown)


def trim_scarf(img, m):
    """The cutout's scarf hangs a little lower than the frame's, so the mask
    picks up a strip of foliage under it (which then waved in the wind).
    Drop green/yellow/teal pixels there and anything below the scarf's lower
    edge, which runs from (1217, 700) to (1330, 678)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(int)
    h, s = hsv[..., 0], hsv[..., 1]
    yy, xx = np.mgrid[0:m.shape[0], 0:m.shape[1]]
    zone = (xx > 1180) & (xx < 1350) & (yy > 640) & (yy < 740)
    foliage = (h >= 12) & (h <= 100) & (s > 45)
    edge_y = 700 - (xx - 1217) * (22 / 113) + 2
    below = (xx > 1200) & (yy > edge_y)
    keep = m.astype(bool) & ~(zone & (foliage | below))
    keep = cv2.morphologyEx(keep.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return largest(keep)


def balloon_shape(m):
    """GrabCut drops pale stripes that look like cloud. Balloons are symmetric
    about their basket, so mirror the mask there and take the convex hull."""
    ys, xs = np.nonzero(m)
    bottom = ys > ys.max() - (ys.max() - ys.min()) * 0.12
    axis = xs[bottom].mean()
    mirrored = np.zeros_like(m)
    mx = np.round(2 * axis - xs).astype(int)
    ok = (mx >= 0) & (mx < m.shape[1])
    mirrored[ys[ok], mx[ok]] = 1
    both = m | mirrored
    hull = cv2.convexHull(np.column_stack(np.nonzero(both)[::-1]).astype(np.int32))
    out = np.zeros_like(m)
    cv2.fillConvexPoly(out, hull, 1)
    return out


def soft_alpha(m, feather=1.2):
    a = cv2.GaussianBlur(m.astype(np.float32), (0, 0), feather)
    return np.clip((a - 0.5) * 1.6 + 0.5, 0, 1) * (cv2.dilate(m, np.ones((3, 3), np.uint8)) > 0)


_lama = None


def lama_fill(img, hole):
    """Inpaint `hole` (uint8 0/1) one 512-ish window at a time."""
    global _lama
    if _lama is None:
        _lama = ort.InferenceSession(str(LAMA), providers=["CPUExecutionProvider"])
    out = img.copy()
    n, lab, st, _ = cv2.connectedComponentsWithStats(hole)
    for i in range(1, n):
        x, y, w, h, _a = st[i]
        size = int(max(w, h) * 2.2)
        size = max(size, 256)
        cx, cy = x + w // 2, y + h // 2
        X0 = int(np.clip(cx - size // 2, 0, max(0, img.shape[1] - size)))
        Y0 = int(np.clip(cy - size // 2, 0, max(0, img.shape[0] - size)))
        X1, Y1 = min(img.shape[1], X0 + size), min(img.shape[0], Y0 + size)
        crop = out[Y0:Y1, X0:X1]
        m = (lab[Y0:Y1, X0:X1] == i).astype(np.uint8)
        ci = cv2.resize(crop, (512, 512), interpolation=cv2.INTER_AREA)
        cm = cv2.resize(m, (512, 512), interpolation=cv2.INTER_NEAREST)
        x_img = ci[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255
        x_m = (cm > 0)[None, None].astype(np.float32)
        r = _lama.run(None, {"image": x_img, "mask": x_m})[0][0].transpose(1, 2, 0)[:, :, ::-1]
        if r.max() <= 1.5:
            r = r * 255
        r = cv2.resize(np.clip(r, 0, 255).astype(np.uint8), (X1 - X0, Y1 - Y0), interpolation=cv2.INTER_CUBIC)
        crop[m > 0] = r[m > 0]
    return out


def save_sprite(name, img, alpha, extra=None):
    ys, xs = np.nonzero(alpha > 0.01)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgba = np.dstack([img[y0:y1, x0:x1], (alpha[y0:y1, x0:x1] * 255).astype(np.uint8)])
    cv2.imwrite(str(OUT / f"{name}.webp"), rgba, [cv2.IMWRITE_WEBP_QUALITY, 95])
    entry = {"src": f"assets/hero/{name}.webp", "rect": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]}
    if extra:
        entry.update(extra)
    return entry, (x0, y0, x1, y1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    img = cv2.imread(str(FRAME))
    H, W = img.shape[:2]
    masks = {}

    for i, box in enumerate(BALLOONS):
        masks[f"balloon-{i + 1}"] = balloon_shape(grabcut_rect(img, box))
    for name, box in CATS.items():
        masks[name] = grabcut_rect(img, box)

    cut = cv2.imread(str(GIRL_CUTOUT), cv2.IMREAD_UNCHANGED)
    prior = (cv2.warpAffine(cut[:, :, 3], GIRL_M, (W, H), flags=cv2.INTER_LINEAR) > 128).astype(np.uint8)
    masks["girl"] = trim_scarf(img, restore_hood(img, grabcut_prior(img, prior)))

    if PREVIEW:
        ov = img.copy()
        for name, m in masks.items():
            cnt, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            cv2.drawContours(ov, cnt, -1, (0, 0, 255), 1)
        for x, y, s in LAMPS:
            cv2.circle(ov, (x, y), s // 2, (0, 255, 0), 1)
        cv2.imwrite(str(OUT / "_preview_masks.png"), ov)

    # Plate: everything that moves is painted out, with a margin so a sprite
    # that drifts a few pixels never uncovers its own ghost.
    hole = np.zeros((H, W), np.uint8)
    for name, m in masks.items():
        grow = 10 if name.startswith("balloon") else 7
        hole |= cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=grow)
    plate = lama_fill(img, hole)
    cv2.imwrite(str(OUT / "plate.jpg"), plate, [cv2.IMWRITE_JPEG_QUALITY, 90])

    scene = {"size": [W, H], "sprites": [], "lamps": [{"x": x, "y": y, "r": s} for x, y, s in LAMPS],
             "water": save_water(img)}
    for name, m in masks.items():
        a = soft_alpha(m)
        kind = name.split("-")[0]
        entry, (x0, y0, x1, y1) = save_sprite(name, img, a, {"name": name, "kind": kind})
        if kind == "cat":
            ys = np.nonzero(m)[0]
            entry["anchor"] = [int((x0 + x1) / 2), int(ys.max())]  # feet: breathing scales from here
            if name in TAILS:
                entry["tail"] = save_tail(name, (x0, y0, x1, y1))
        if kind == "girl":
            entry["wind"] = {"map": save_wind(name, m, (x0, y0, x1, y1))}
        scene["sprites"].append(entry)

    # Draw order: far balloons first, then cats behind/in front by feet y, girl.
    order = {"balloon": 0, "cat": 1, "girl": 2}
    scene["sprites"].sort(key=lambda e: (order[e["kind"]], e["rect"][1] + e["rect"][3]))
    (OUT / "scene.json").write_text(json.dumps(scene, indent=1))
    print("wrote", OUT, [e["name"] for e in scene["sprites"]])


WATER_RECT = (0, 686, 1050, 150)


def save_water(img):
    """Where the river ripples: from the embankment (y 694, or the bridge
    base at y 724 under the bridge) down to just above the top rail, minus
    anything dark (posts, the lamp pole) so they never wobble."""
    x0, y0, w, h = WATER_RECT
    yy, xx = np.mgrid[y0:y0 + h, x0:x0 + w].astype(np.float32)
    top = np.where(xx < 420, 696, 726)
    rail = 835 - 0.0575 * xx - 6
    water = ((yy > top) & (yy < rail) & (xx < 1040)).astype(np.uint8)
    v = cv2.cvtColor(img[y0:y0 + h, x0:x0 + w], cv2.COLOR_BGR2HSV)[..., 2]
    dark = cv2.dilate((v < 80).astype(np.uint8), np.ones((3, 3), np.uint8), iterations=3)
    water &= 1 - dark
    water = cv2.erode(water, np.ones((3, 3), np.uint8), iterations=1)
    soft = cv2.GaussianBlur(water.astype(np.float32), (0, 0), 2.5) * water
    cv2.imwrite(str(OUT / "water.png"), (soft * 255).astype(np.uint8))
    return {"map": "assets/hero/water.png", "rect": list(WATER_RECT)}


def save_tail(name, rect):
    """Bend weight for a tail: 0 where it leaves the body, 1 at the tip."""
    x0, y0, x1, y1 = rect
    t = TAILS[name]
    bx0, by0, bx1, by1 = t["box"]
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    inside = ((xx >= bx0) & (xx <= bx1) & (yy >= by0) & (yy <= by1)).astype(np.float32)
    inside = cv2.GaussianBlur(inside, (0, 0), 2)
    along = np.clip((t["base"][1] - yy) / (t["base"][1] - by0), 0, 1) ** 1.2
    w = inside * along
    cv2.imwrite(str(OUT / f"{name}-tail.png"), (w * 255).astype(np.uint8))
    return {"map": f"assets/hero/{name}-tail.png", "base": list(t["base"])}


def save_wind(name, m, rect):
    """How strongly the wind moves each pixel of the girl: 0 on the face, hands,
    bag and body; rising along the scarf tail and towards the dress hem."""
    x0, y0, x1, y1 = rect
    h, w = y1 - y0, x1 - x0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # In frame pixels: the scarf tail streams right from past the bag
    # (x > 1190) to its tip near 1345, between y 600 and 760; the dress
    # flares from ~y 780 down, most on its trailing (right) side.
    fx, fy = xx + x0, yy + y0
    scarf = np.clip((fx - 1190) / 150, 0, 1) * ((fy > 590) & (fy < 770))
    # Only the trailing hem (behind her, x > ~1170) moves; the front of the
    # dress, her ankles and shoes stay put.
    hem = np.clip((fy - 800) / 180, 0, 1) ** 1.3 * np.clip((fx - 1170) / 110, 0, 1)
    wind = np.clip(np.maximum(scarf, hem), 0, 1)
    wind = cv2.GaussianBlur(wind, (0, 0), 6)
    legs = cv2.GaussianBlur(((fx < 1175) & (fy > 930)).astype(np.float32), (0, 0), 6)
    wind *= 1 - np.clip(legs * 2, 0, 1)
    wind[(fy > 985) & (fx < 1180)] = 0
    cv2.imwrite(str(OUT / f"{name}-wind.png"), (wind * 255).astype(np.uint8))
    return f"assets/hero/{name}-wind.png"


if __name__ == "__main__":
    main()
