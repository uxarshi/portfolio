"""Build the "Walk with me" video from the intro video.

1. Sky fix.
Around 5.8-6.2 s the intro video dissolves from one still composition of the
bench scene to a redrawn one (camera static in both, cut to the laptop shot
at frame 286), and the redraw drops the balloons and birds. This cuts them
out of frame 172 (5.74 s, the last clean frame before the dissolve) and
paints them back over every frame from the dissolve to the cut:

- exactly where they were, carrying on the drift they had in the original
  (balloons rising slowly, birds flying up and to the left), measured from
  frames 150-172;
- behind the tree that the redraw adds: wherever its leaves are (found per
  frame, since the leaves move), the leaves stay in front.

From the first dissolve frame the overlay sits exactly on the originals, so
nothing jumps while they fade underneath it.

2. Laptop screen. The video ends on her hands at the laptop; the page then
shows "Show projects" on the screen. The camera is still easing in until the
very last frame, so the screen's corners are measured on that frame.

Writes assets/video/intro-walk.mp4 (original audio copied) and
assets/video/intro-walk.json (the laptop screen's corners in frame pixels).
The source video is never modified.
Run: python3 tools/build_walk.py [--preview DIR]   (needs ffmpeg on PATH, opencv, numpy)
"""
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "final intro video.mp4"
OUT = ROOT / "assets/video/intro-walk.mp4"
W, H = 1920, 1080

REF = 172            # last frame with balloons and birds, before the dissolve
START = 175          # first dissolve frame: overlay goes on here
SETTLED = 186        # dissolve done: the tree is fully in
CUT = 286            # first frame of the laptop shot: overlay off

# Generous boxes (x0, y0, x1, y1) around each one in frame REF, and its drift
# in px per frame, measured over frames 150-172 of the original.
BALLOONS = [
    {"box": (95, 40, 206, 178), "v": (0.0, -0.32)},
    {"box": (242, 86, 352, 224), "v": (0.0, -0.27)},
    {"box": (388, 166, 506, 314), "v": (-0.03, -0.27)},
    {"box": (718, 238, 807, 344), "v": (0.0, -0.23)},
]
BIRDS = [
    {"box": (370, 14, 490, 76), "v": (-0.77, -0.23)},
    {"box": (590, 104, 692, 153), "v": (-0.59, -0.23)},
    {"box": (752, 140, 853, 194), "v": (-0.64, 0.0)},
    {"box": (885, 152, 980, 205), "v": (-0.59, -0.18)},
]
# The redrawn tree only reaches into this corner of the sky.
TREE_ZONE = (560, 0, 1300, 330)

# Laptop screen (the lit display, inside the bezel) in the last frame: TL, TR, BR, BL.
SCREEN = [(598, 307), (1319, 297), (1319, 713), (598, 725)]


def decode(select=None):
    vf = "scale=in_color_matrix=bt709:in_range=tv"
    if select is not None:
        vf = f"select='eq(n\\,{select})'," + vf
    cmd = ["ffmpeg", "-v", "error", "-i", str(SRC), "-vf", vf,
           "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = W * H * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    p.wait()


def encoder():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-framerate", "30000/1001", "-i", "-",
           "-i", str(SRC), "-map", "0:v", "-map", "1:a", "-c:a", "copy",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,"
                  "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(OUT)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def largest(m):
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    if n <= 1:
        return m.astype(np.uint8)
    return (lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])).astype(np.uint8)


def fill_holes(m):
    inv = (1 - m).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(inv)
    out = m.copy()
    for i in range(1, n):
        x, y, w, h, _a = st[i]
        if x > 0 and y > 0 and x + w < m.shape[1] and y + h < m.shape[0]:
            out[lab == i] = 1
    return out


def cut_balloon(img, box):
    """Envelope, ropes and basket. GrabCut finds the envelope; the dark ropes
    and basket below it are added from their own colour, so they're never
    clipped; the envelope (wide rows) is filled out to its convex hull."""
    x0, y0, x1, y1 = box
    crop = img[y0:y1, x0:x1]
    mask = np.zeros(crop.shape[:2], np.uint8)
    bgd, fgd = np.zeros((1, 65)), np.zeros((1, 65))
    cv2.grabCut(crop, mask, (6, 6, x1 - x0 - 12, y1 - y0 - 12), bgd, fgd, 10, cv2.GC_INIT_WITH_RECT)
    gc = largest(np.isin(mask, (cv2.GC_FGD, cv2.GC_PR_FGD)))

    # The envelope is everything down to its last wide row (the neck);
    # include the narrow dome at the top too.
    widths = gc.sum(1)
    env_bottom = np.nonzero(widths > widths.max() * 0.45)[0].max()
    env = np.zeros_like(gc)
    env[:env_bottom + 1] = gc[:env_bottom + 1]
    hull = cv2.convexHull(np.column_stack(np.nonzero(env)[::-1]).astype(np.int32))
    env = np.zeros_like(gc)
    cv2.fillConvexPoly(env, hull, 1)

    # Ropes and basket: dark pixels under the envelope, within its width.
    v = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[..., 2]
    xs = np.nonzero(env.any(0))[0]
    dark = (v < 125).astype(np.uint8)
    below = np.zeros_like(dark)
    below[env_bottom - 4:, xs.min():xs.max() + 1] = 1
    rig = cv2.dilate(dark & below, np.ones((3, 3), np.uint8))
    m = largest(env | rig | (gc & below))
    # close the small gaps between ropes so the basket hangs as one piece
    m = fill_holes(cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)))
    return sprite(crop, m, (x0, y0))


def cut_bird(img, box):
    x0, y0, x1, y1 = box
    crop = img[y0:y1, x0:x1]
    v = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[..., 2]
    m = largest(v < 135)
    m = fill_holes(cv2.dilate(m, np.ones((3, 3), np.uint8)))
    return sprite(crop, m, (x0, y0))


def sprite(crop, m, origin):
    a = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 0.8)
    a = np.clip((a - 0.5) * 1.8 + 0.5, 0, 1) * (cv2.dilate(m, np.ones((3, 3), np.uint8)) > 0)
    return {"rgb": crop.astype(np.float32), "a": a, "m": m, "origin": np.array(origin, float)}


def leaf_mask(img):
    """Where the redrawn tree's leaves and branches are (1), within TREE_ZONE."""
    zx0, zy0, zx1, zy1 = TREE_ZONE
    c = img[zy0:zy1, zx0:zx1]
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV).astype(int)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    b = cv2.cvtColor(c, cv2.COLOR_BGR2LAB)[..., 2].astype(int)
    lavender = b < 140   # the bluish sky streaks
    m = ((v < 205) & ~lavender) | ((h >= 18) & (h <= 95) & (s > 90)) | (s > 228) | (v < 120)
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= 150]).astype(np.float32)
    keep = cv2.GaussianBlur(keep, (0, 0), 0.8)
    full = np.zeros((H, W), np.float32)
    full[zy0:zy1, zx0:zx1] = keep
    return full


def paste(frame, s, pos, cover=None, fade=1.0):
    """Alpha-blend sprite s with its top-left at pos (sub-pixel), hidden where cover is 1."""
    h, w = s["a"].shape
    x, y = pos
    ix, iy = int(np.floor(x)) - 1, int(np.floor(y)) - 1
    M = np.float32([[1, 0, x - ix], [0, 1, y - iy]])
    rgb = cv2.warpAffine(s["rgb"], M, (w + 2, h + 2), flags=cv2.INTER_LINEAR)
    a = cv2.warpAffine(s["a"], M, (w + 2, h + 2), flags=cv2.INTER_LINEAR) * fade
    X0, Y0 = max(ix, 0), max(iy, 0)
    X1, Y1 = min(ix + w + 2, W), min(iy + h + 2, H)
    if X1 <= X0 or Y1 <= Y0:
        return
    sx, sy = X0 - ix, Y0 - iy
    rgb = rgb[sy:sy + Y1 - Y0, sx:sx + X1 - X0]
    a = a[sy:sy + Y1 - Y0, sx:sx + X1 - X0]
    if cover is not None:
        a = a * (1 - cover[Y0:Y1, X0:X1])
    a = a[..., None]
    region = frame[Y0:Y1, X0:X1].astype(np.float32)
    frame[Y0:Y1, X0:X1] = np.clip(rgb * a + region * (1 - a), 0, 255).astype(np.uint8)


def main():
    settled_leaves = leaf_mask(next(decode(select=SETTLED)))
    things = None
    enc = encoder()
    previews = {}
    for n, frame in enumerate(decode()):
        if n == REF:
            things = [dict(b, s=cut_balloon(frame, b["box"])) for b in BALLOONS] + \
                     [dict(b, s=cut_bird(frame, b["box"])) for b in BIRDS]
            previews["cutouts"] = outline(frame, things)
        if START <= n < CUT:
            frame = frame.copy()
            # During the dissolve the tree fades in, so its cover does too.
            if n < SETTLED:
                cover = settled_leaves * ((n - START + 1) / (SETTLED - START + 1))
            else:
                cover = leaf_mask(frame)
            for t in things:
                pos = t["s"]["origin"] + np.array(t["v"]) * (n - REF)
                paste(frame, t["s"], pos, cover)
            if n in (176, 182, 190, 240, 285):
                previews[str(n)] = frame.copy()
        enc.stdin.write(np.ascontiguousarray(frame).tobytes())
    enc.stdin.close()
    enc.wait()
    if "--preview" in sys.argv:
        preview_dir = Path(sys.argv[sys.argv.index("--preview") + 1])
        preview_dir.mkdir(parents=True, exist_ok=True)
        for k, img in previews.items():
            cv2.imwrite(str(preview_dir / f"{k}.png"), img)
    laptop = {"frame": [W, H], "screen": SCREEN}
    OUT.with_suffix(".json").write_text(json.dumps(laptop, indent=1))
    print("wrote", OUT)


def outline(frame, things):
    ov = frame.copy()
    for t in things:
        x0, y0 = t["s"]["origin"].astype(int)
        cnt, _ = cv2.findContours(t["s"]["m"], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(ov, [c + (x0, y0) for c in cnt], -1, (255, 0, 255), 1)
    return ov


if __name__ == "__main__":
    main()
