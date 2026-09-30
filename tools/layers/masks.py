"""Cut-out masks for every layer of art/landscape.png.

Masks are float32 alpha maps (0..1) at full painting size. They come from the
depth map (art/landscape_depth.png) plus GrabCut colour refinement, guided by
the hand-measured boxes below. Change the boxes if you swap the painting.
"""
import cv2
import numpy as np
from scipy import ndimage as ndi

# ───────────────────────────── where things are (x0, y0, x1, y1) ──────────
GIRL = (795, 592, 1000, 932)
BUBBLE = (934, 510, 78, 51)  # painted thought bubble ellipse (cx, cy, rx, ry)
PUFFS = [(899, 567, 13, 11), (885, 587, 9, 8)]  # its small trailing puffs
# the background seen between her scarf, bag and dress (far lamps, trees,
# path). The automatic cut-out swallowed it, so the scarf flutter bent the
# lamps; traced by hand along the scarf's lower edge and the dress's edge
GIRL_GAPS = [
    # below the scarf, between bag and dress
    [(889, 716), (900, 729), (910, 734), (920, 733), (930, 729), (940, 726), (950, 725), (960, 729),
     (970, 730), (980, 729), (990, 733), (997, 738), (1006, 742), (1006, 850), (990, 845), (983, 836),
     (975, 827), (960, 815), (935, 799), (910, 781), (890, 762), (885, 750), (888, 748)],
    # above the scarf's tip
    [(925, 640), (1006, 640), (1006, 722), (996, 722), (988, 716), (975, 707), (966, 700), (958, 692),
     (950, 689), (940, 689), (925, 688)],
]
CATS = {
    "cat-orange": (528, 848, 630, 958),
    "cat-tabby": (1014, 812, 1092, 886),
    "cat-white": (1292, 860, 1398, 944),
}
# the white cat's tail lies on the pale pavement, which colour and depth can't
# tell apart, so it is traced by hand
WHITE_TAIL = [(1352, 926), (1366, 927), (1378, 929), (1388, 932), (1392, 935), (1389, 939), (1378, 938),
              (1366, 936), (1354, 934)]
# the tabby's white muzzle, chest and paws and its ears are as pale as the
# pavement, so the automatic cut-out lost them; its outline, traced by hand
# (the tail stops at y 830; above it is the small bench's front leg)
TABBY = [(1022, 830), (1027, 834), (1031, 834), (1036, 830), (1040, 838), (1044, 841), (1055, 839), (1066, 839),
         (1074, 843), (1079, 838), (1082, 830), (1081, 822), (1079, 816), (1081, 814), (1085, 814), (1088, 822),
         (1087, 832), (1084, 841), (1081, 847), (1081, 858), (1081, 868), (1080, 882), (1074, 883), (1074, 875),
         (1072, 868), (1071, 882), (1064, 883), (1065, 872), (1062, 864), (1052, 863), (1048, 870), (1048, 883),
         (1041, 883), (1041, 872), (1038, 866), (1035, 872), (1034, 883), (1029, 883), (1031, 870), (1032, 858),
         (1030, 852), (1022, 848), (1019, 845), (1020, 839), (1021, 834)]
# the trunks and main branches of the trees on the right, which stay still
# while the foliage sways: polylines of (x, y, half width)
TRUNKS = [
    [(1468, 772, 10), (1467, 700, 10), (1464, 600, 9), (1462, 545, 8)],  # big tree, right
    [(1460, 548, 6), (1445, 515, 5), (1428, 485, 5), (1410, 455, 4), (1395, 428, 3)],
    [(1466, 540, 6), (1476, 490, 6), (1486, 445, 5), (1492, 425, 5)],
    [(1472, 660, 4), (1492, 610, 4)],
    [(1455, 640, 3), (1430, 605, 3), (1405, 575, 2)],
    [(1343, 772, 8), (1342, 700, 8), (1340, 650, 7), (1332, 615, 5), (1324, 585, 4)],  # behind the big lamp
    [(1345, 645, 4), (1360, 610, 3), (1372, 585, 3)],
    [(1302, 772, 6), (1301, 690, 6)],
    [(1300, 690, 4), (1285, 655, 3), (1270, 625, 3)],
    [(1304, 688, 4), (1318, 650, 3), (1330, 615, 3)],
    [(1258, 772, 4), (1257, 715, 4), (1265, 690, 2)],
    [(1229, 772, 5), (1228, 700, 5)],
    [(1227, 700, 3), (1212, 670, 3), (1200, 650, 2)],
    [(1230, 700, 3), (1245, 670, 3), (1252, 655, 2)],
    [(1174, 772, 5), (1173, 700, 4), (1160, 675, 2)],
]
# each cat's tail: base (where it leaves the body) and tip, for the wiggle
TAILS = {"cat-orange": (551, 903, 543, 855), "cat-tabby": (1075, 845, 1083, 830),
         "cat-white": (1358, 931, 1391, 936)}
# the three nearest lamps and two nearest benches get their own layer; the
# small far ones are only a few pixels wide and stay painted into the hedge
LAMPS = [(1342, 452, 1426, 926), (1143, 576, 1202, 862), (1048, 658, 1084, 824)]
BENCHES = [(1196, 780, 1366, 912), (1076, 772, 1166, 850)]
# lantern outlines (cap tip → roof → glass → bottom ring), one per lamp above
LANTERNS = [
    [(1380, 456), (1387, 469), (1396, 477), (1413, 493), (1406, 501), (1401, 540), (1393, 553), (1367, 553),
     (1359, 540), (1354, 501), (1347, 493), (1364, 477), (1373, 469)],
    [(1170, 578), (1177, 591), (1191, 604), (1187, 611), (1183, 630), (1179, 637), (1162, 637), (1158, 630),
     (1154, 611), (1150, 604), (1163, 591)],
    [(1065, 661), (1070, 668), (1078, 676), (1075, 681), (1073, 695), (1057, 695), (1055, 681), (1052, 676),
     (1060, 668)],
]
# lamp heads (x, y) for glow / click-to-light, nearest first, including the far ones
LAMP_HEADS = [(1380, 505), (1172, 610), (1066, 680), (1008, 712), (980, 733), (966, 741)]
BALLOONS = [(328, 126, 440, 262), (1006, 163, 1058, 228), (1098, 269, 1152, 339), (1097, 473, 1148, 540)]
SKY_BOTTOM = 735  # nothing below this is sky
BIRD_ZONE = (440, 260, 900, 440)
# where the right-hand hedge meets the pavement (x, y), left → right
HEDGE_EDGE = [(840, 742), (900, 752), (1000, 770), (1100, 792), (1200, 826), (1300, 862), (1400, 890), (1492, 905)]
# where the left flower bed's curb meets the pavement
CURB = [(0, 1012), (100, 1002), (200, 988), (300, 965), (400, 943), (500, 916), (600, 890), (700, 864),
        (800, 838), (840, 828)]
# the far end of the promenade, where the path meets the trees
PATH_FAR_Y = 742


def _smooth(mask, sigma=0.8):
    return np.clip(ndi.gaussian_filter(mask.astype(np.float32), sigma), 0, 1)


def _largest(mask):
    lab, n = ndi.label(mask)
    if n == 0:
        return mask
    sizes = ndi.sum(mask, lab, range(1, n + 1))
    return lab == (1 + int(np.argmax(sizes)))


def _grabcut(img8, box, hint_fg, hint_bg=None, pad=14, iters=6, depth=None):
    """GrabCut inside `box`, seeded with depth hints. Returns a full-size bool mask.
    With `depth`, GrabCut sees (depth, depth, brightness) instead of colour, which
    separates objects whose colours match what's behind them."""
    H, W = hint_fg.shape
    x0, y0, x1, y1 = box
    X0, Y0, X1, Y1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
    crop = np.ascontiguousarray(img8[Y0:Y1, X0:X1])
    if depth is not None:
        dc = depth[Y0:Y1, X0:X1]
        lo, hi = np.percentile(dc, 2), np.percentile(dc, 98)
        dn = np.clip((dc - lo) / max(hi - lo, 1e-3) * 255, 0, 255).astype(np.uint8)
        crop = np.ascontiguousarray(np.dstack([dn, dn, crop.mean(axis=2).astype(np.uint8)]))
    gc = np.full(crop.shape[:2], cv2.GC_BGD, np.uint8)
    inner = np.zeros(crop.shape[:2], bool)
    inner[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = True
    gc[inner] = cv2.GC_PR_BGD
    fg = hint_fg[Y0:Y1, X0:X1] & inner
    gc[fg] = cv2.GC_PR_FGD
    gc[ndi.binary_erosion(fg, iterations=3)] = cv2.GC_FGD
    if hint_bg is not None:
        gc[hint_bg[Y0:Y1, X0:X1] & inner & ~fg] = cv2.GC_BGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(crop, gc, None, bgd, fgd, iters, cv2.GC_INIT_WITH_MASK)
    out = np.zeros((H, W), bool)
    out[Y0:Y1, X0:X1] = (gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)
    return out


def _otsu(v):
    hist, edges = np.histogram(v, bins=64, range=(0, 1))
    w = np.cumsum(hist); mu = np.cumsum(hist * edges[:-1])
    wt, mt = w[-1], mu[-1]
    between = (mt * w - mu * wt) ** 2 / np.maximum(w * (wt - w), 1e-9)
    return edges[int(np.argmax(between))]


def ground_profile(D):
    """Depth of the pavement per row (for 'what's in front of the ground')."""
    H, W = D.shape
    cols = np.r_[640:780, 1000:1010]
    g = np.median(D[:, cols], axis=1)
    return ndi.gaussian_filter1d(g, 3)


def build_masks(img, D):
    """img: float RGB 0..1, D: raw depth 0..1 (bright = near). Returns dict of alpha maps."""
    H, W, _ = img.shape
    img8 = (img * 255).astype(np.uint8)[..., ::-1]  # BGR for OpenCV
    yy, xx = np.mgrid[0:H, 0:W]
    G = ground_profile(D)[:, None]
    in_front = D > G + 0.025  # nearer than the pavement at that row
    m = {}

    # girl: depth separates her from sky/city/trees; near the feet, GrabCut
    # separates the cream dress from the pink pavement by colour
    x0, y0, x1, y1 = GIRL
    box = np.zeros((H, W), bool)
    box[y0:y1, x0:x1] = True
    upper = yy < 660  # head and shoulders: sky/city behind
    hint = box & (((D > 0.3) & upper) | ((D > 0.41) & ~upper & (yy < 800)) | (in_front & (xx < 960)))
    bg = box & (((D < 0.22) & upper) | ((D < 0.36) & ~upper & (yy < 800)))
    girl = _grabcut(img8, GIRL, hint, bg)
    girl = _largest(ndi.binary_fill_holes(ndi.binary_closing(girl, iterations=2)))
    puffs = np.zeros((H, W), bool)
    for cx, cy, rx, ry in PUFFS:
        puffs |= ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 < 1
    gap = np.zeros((H, W), np.uint8)
    cv2.fillPoly(gap, [np.array(g, np.int32) for g in GIRL_GAPS], 1)
    # shrunk a pixel so the scarf's and dress's outlines stay with her
    m["girl_gap"] = ndi.binary_erosion(gap > 0, iterations=1)
    girl &= ~m["girl_gap"]  # (the trees below may now claim what's in the gap)
    m["girl"] = _smooth(girl | puffs)
    cx, cy, rx, ry = BUBBLE
    m["bubble"] = (((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 < 1).astype(np.float32)

    hsv = cv2.cvtColor(img8, cv2.COLOR_BGR2HSV).astype(np.float32)
    hue = hsv[..., 0] * 2  # degrees
    lum = img.mean(axis=2)
    sat = img.max(axis=2) - img.min(axis=2)
    iron = (lum < 0.5) & (sat < 0.12)
    dark = (lum < 0.46) & (sat < 0.16)  # bench frames are dark, slightly green
    greenish = (img[..., 1] > img[..., 0] - 0.03) & (lum > 0.46)

    def boxmask(b):
        x0, y0, x1, y1 = b
        bm = np.zeros((H, W), bool)
        bm[y0:y1, x0:x1] = True
        return bm

    def left_ground(b):
        """Pavement depth per row, just left of the box."""
        x0, y0, x1, y1 = b
        g = np.median(D[:, max(0, x0 - 34):x0 - 4], axis=1)
        return ndi.gaussian_filter1d(g, 2)[:, None]

    # lamps: dark iron posts + the glowing glass at the top
    lamps = np.zeros((H, W), bool)
    for b in LAMPS:
        x0, y0, x1, y1 = b
        bm = boxmask(b)
        top = bm & (yy < y0 + (y1 - y0) * 0.22)
        fg = bm & (iron | (top & (lum > 0.78)))
        bg = bm & ~top & (sat > 0.15) & (lum > 0.4)
        one = _grabcut(img8, b, fg, bg, pad=6) & ~top  # the post
        lantern = np.zeros((H, W), np.uint8)
        cv2.fillPoly(lantern, [np.array(LANTERNS[LAMPS.index(b)], np.int32)], 1)
        post = _largest(ndi.binary_opening(one, iterations=1))
        # bridge the neck between lantern and post
        neck = ndi.binary_dilation(lantern > 0, iterations=4) & ndi.binary_dilation(post, iterations=4)
        lamps |= post | (lantern > 0) | ndi.binary_closing(neck, iterations=2)

    # cats: nearer than the pavement behind them (depth), refined by colour
    for name, b in CATS.items():
        x0, y0, x1, y1 = b
        bm = boxmask(b)
        Gl = left_ground(b)
        fg = bm & (D > Gl + 0.03)
        bg = bm & ((np.abs(D - Gl) < 0.008) & (yy < y1 - 12) | lamps)
        if name == "cat-white":  # a white cat: anything darker is bench/hedge
            bg |= bm & (lum < 0.6)
        c = _grabcut(img8, b, fg & ~bg, bg, pad=10)
        c = _largest(ndi.binary_fill_holes(ndi.binary_closing(c, iterations=2)))
        traced = {"cat-white": WHITE_TAIL, "cat-tabby": TABBY}.get(name)
        if traced:
            extra = np.zeros((H, W), np.uint8)
            cv2.fillPoly(extra, [np.array(traced, np.int32)], 1)
            c |= extra > 0
        if name == "cat-tabby":
            c &= ~((yy < 829) & (xx > 1070))  # above its tail tip: the bench's leg
        m[name] = _smooth(c)

    # benches: iron frame + brown slats, against a green/pink hedge
    benches = np.zeros((H, W), bool)
    for i, b in enumerate(BENCHES):
        bm = boxmask(b)
        wood = (hue > 10) & (hue < 34) & (sat > 0.16) & (sat < 0.33) & (lum > 0.38) & (lum < 0.64)
        fg = bm & (dark | (wood & ~greenish))
        if i > 0:  # smaller benches: also "nearer than the hedge behind"
            fg |= bm & ~greenish & (D > left_ground(b) + 0.015) & (lum < 0.75)
        bg = bm & ((greenish & ~dark) | (lum > 0.8) | lamps)
        benches |= _grabcut(img8, b, fg, bg, pad=6)
    for c in CATS:  # cats in front of benches are not bench
        benches &= m[c] < 0.5
    benches &= ~lamps
    m["lamps"] = _smooth(lamps)
    m["benches"] = _smooth(ndi.binary_opening(benches, iterations=1))

    balloons = []
    for b in BALLOONS:
        x0, y0, x1, y1 = b
        bm = np.zeros((H, W), bool)
        bm[y0:y1, x0:x1] = D[y0:y1, x0:x1] > 0.07
        balloons.append(_smooth(_largest(ndi.binary_fill_holes(bm)), 0.6))
    m["balloons"] = balloons

    # sky objects: birds are darker than the sky around them, loose leaves
    # are saturated orange
    sky_zone = (D < 0.09) & (yy < SKY_BOTTOM)
    bx0, by0, bx1, by1 = BIRD_ZONE
    bird_zone = sky_zone & (xx >= bx0) & (xx < bx1) & (yy >= by0) & (yy < by1)
    birds = bird_zone & (lum < ndi.median_filter(lum, 25) - 0.07)
    birds = ndi.binary_opening(birds, iterations=1)
    birds = ndi.binary_dilation(birds, iterations=1)
    leaf_zone = sky_zone & ((yy < 605) | ((xx > 560) & (xx < 900) & (yy < 690)))
    leaves = leaf_zone & (img[..., 0] - img[..., 2] > 0.30) & (img[..., 0] - img[..., 1] > 0.18)
    leaves = ndi.binary_dilation(ndi.binary_opening(leaves), iterations=3)
    for bm in balloons:
        birds &= bm < 0.1
        leaves &= bm < 0.1
    m["birds_raw"] = birds
    m["leaves"] = leaves

    # hedge edge as a y-per-column curve
    ex, ey = zip(*HEDGE_EDGE)
    edge = np.interp(np.arange(W), ex, ey)
    edge[: ex[0]] = H  # the hedge edge only exists on the right
    edge = edge[None, :]

    # trees & hedge: everything on the right that isn't sky, above the pavement
    trees = (D > 0.075) & (xx > 845) & (yy < edge) & (yy > 120)
    for bm in balloons:
        trees &= ~ndi.binary_dilation(bm > 0.05, iterations=3)
    trees &= ~(girl | (m["bubble"] > 0))
    trees |= (xx > 880) & (yy > 700) & (yy < edge)  # solid hedge band
    trees &= ~(yy > 690) | (xx > 800)
    trees = ndi.binary_opening(trees, iterations=1)
    m["trees"] = _smooth(trees, 1.0)

    # path & railing: left, everything nearer than the river; plus the pavement
    rail_zone = (xx < 840) & (yy > 740)
    railing = rail_zone & (D > 0.2)
    pavement = (yy >= edge) | ((xx >= 800) & (xx <= 900) & (yy > PATH_FAR_Y))
    pavement |= (yy > 900) & (xx < 900)
    path = railing | pavement
    m["path"] = np.clip(_smooth(path, 0.8) + (rail_zone * np.clip((D - 0.16) / 0.1, 0, 1)), 0, 1)
    m["path"] = np.maximum(m["path"], pavement.astype(np.float32))
    return m
