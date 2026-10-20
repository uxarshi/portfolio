"""Even out the stop-motion feel in the walk video.

Parts of the walk were made at a lower frame rate and padded to 29.97 fps
(repeated and blended frames), and the sit-down slows almost to a stop and
then lurches. Inside each shot this measures how far things actually move
between frames (optical flow), lays the frames out so motion advances at an
even, gently smoothed pace, and synthesises the in-between frames from the
flow. Shot boundaries, frame count, length and audio are unchanged, and the
first frame of every shot is kept exactly (frame 0 must match the hero still).

    python3 tools/smooth_motion.py                 # writes private/previews/intro-walk-smooth.mp4
    python3 tools/smooth_motion.py --apply         # replaces assets/video/intro-walk.mp4

BASE is the current live video; its pre-smoothing copy is kept in private/.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "assets/video/intro-walk.mp4"
BACKUP = ROOT / "private/originals/intro-walk-before-smooth.mp4"
MASTER = ROOT / "private/originals/intro-walk-15mbps.mp4"   # high-bitrate master: avoid compressing twice
PREVIEW = ROOT / "private/previews/intro-walk-smooth.mp4"

# Frame ranges [start, end) to retime: walk, sit-down, glasses -> laptop.
# The cuts sit at frames 88, 286, 339 and 399; shots after 286 are left alone.
# (start, end, ghost limit, fast px): the bench clip (AI generated, then
# retimed with crossfades) needs a stricter ghost filter and less synthesis.
# fast < 0: real frames only, never synthesised (rigid glasses/laptop bend when warped)
# The bench shot (172-285, AI generated) is left as in the source: its glasses
# and laptop are rigid, and both synthesising and skipping its crossfaded
# frames bent or doubled them (tried, rejected by eye).
SEGMENTS = [(0, 88, 0.32, 14.0), (88, 172, 0.32, 14.0)]
SIGMA = 5.0          # frames; how much the pace is smoothed inside a shot
FLOW_SCALE = 0.5     # optical flow is computed at half resolution
# Ghosted source frames the detector misses (checked by eye: see-through hands
# as she lowers them from the glasses).
EXCLUDE = {222, 223, 225}
# Moments left exactly as in the source: the laptop is lifted out of the bag
# too fast and too far between clean frames to synthesise; warping one frame
# that far bends it. Smoothing eases into and out of these ranges.
KEEP = []
KEEP_EASE = 8          # frames
KEEP_MODE = "source"   # "source": original frames (see-through crossfades) | "hold": nearest clean frame
FAST = 14.0          # px between clean frames above which no in-between is invented
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"


def read_frames(path):
    cap = cv2.VideoCapture(str(path))
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    return frames


DIS = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)


def flow(a, b):
    """Dense flow a -> b, kept at FLOW_SCALE resolution (in full-res pixels)."""
    ga = cv2.cvtColor(cv2.resize(a, None, fx=FLOW_SCALE, fy=FLOW_SCALE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(cv2.resize(b, None, fx=FLOW_SCALE, fy=FLOW_SCALE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return DIS.calc(ga, gb, None) / FLOW_SCALE


def full(f, shape):
    return cv2.resize(f, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)


def motion(f):
    """How far the moving parts moved: 95th percentile of flow magnitude."""
    mag = np.hypot(f[..., 0], f[..., 1])
    return float(np.percentile(mag, 95))


def warp(img, f, k):
    """Sample img at x + k * f(x)."""
    h, w = img.shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    k = np.float32(k)
    return cv2.remap(img, (gx + k * f[..., 0]).astype(np.float32), (gy + k * f[..., 1]).astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def between(a, b, fab, fba, t, mix=True):
    """Frame at fraction t from a to b, from flow in both directions."""
    if t < 0.02:
        return a
    if t > 0.98:
        return b
    fab, fba = full(fab, a.shape), full(fba, a.shape)
    if not mix:
        # Bend the nearer real frame along the motion instead of mixing two:
        # no see-through doubles on fast hands.
        return warp(a, fba, t) if t < 0.5 else warp(b, fab, 1 - t)
    wa = warp(a, fba, t)        # pull a forward along the motion
    wb = warp(b, fab, 1 - t)    # pull b back along the motion
    return cv2.addWeighted(wa, 1 - t, wb, t, 0)


def smooth_progress(p, sigma):
    """Gaussian-smoothed copy of p with both ends pinned, kept increasing."""
    n = len(p)
    r = int(3 * sigma) + 1
    x = np.arange(-r, r + 1)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()
    pad = np.concatenate([2 * p[0] - p[r:0:-1], p, 2 * p[-1] - p[-2:-r - 2:-1]])
    q = np.convolve(pad, k, mode="valid")
    # pin the ends exactly, blending the correction in so nothing jumps
    ramp = np.linspace(0, 1, n)
    q = q + (p[0] - q[0]) * (1 - ramp) + (p[-1] - q[-1]) * ramp
    return np.maximum.accumulate(q)


def small(f):
    return cv2.cvtColor(cv2.resize(f, (480, 270), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)


def blended(seg, limit=0.32):
    """Indices of frames that are a crossfade of their neighbours (ghosts)."""
    g = [small(f) for f in seg]
    out = set()
    for i in range(1, len(seg) - 1):
        nb = np.abs(g[i - 1] - g[i + 1]).mean()
        if nb < 1.0:
            continue
        blend = np.abs(g[i] - 0.5 * (g[i - 1] + g[i + 1])).mean() / nb
        near = min(np.abs(g[i] - g[i - 1]).mean(), np.abs(g[i] - g[i + 1]).mean()) / nb
        if blend < limit and near > 0.30:
            out.add(i)
    return out


def ghostiness(frames):
    g = [small(f) for f in frames]
    n = 0
    for i in range(1, len(g) - 1):
        nb = np.abs(g[i - 1] - g[i + 1]).mean()
        if nb >= 1.0 and np.abs(g[i] - 0.5 * (g[i - 1] + g[i + 1])).mean() / nb < 0.32 \
                and min(np.abs(g[i] - g[i - 1]).mean(), np.abs(g[i] - g[i + 1]).mean()) / nb > 0.35:
            n += 1
    return n


def retime(frames, a, b, limit=0.32, fast=None):
    fast = FAST if fast is None else fast
    seg = frames[a:b]
    n = len(seg)
    ghosts = blended(seg, limit) | {i - a for i in EXCLUDE if a < i < b - 1}
    keys = [i for i in range(n) if i not in ghosts]           # clean source frames only
    kf = [seg[i] for i in keys]
    fwd = [flow(kf[i], kf[i + 1]) for i in range(len(kf) - 1)]
    bwd = [flow(kf[i + 1], kf[i]) for i in range(len(kf) - 1)]
    m = np.array([motion(f) for f in fwd])
    pk = np.concatenate([[0.0], np.cumsum(m)])
    # progress at every original frame position, with ghosts placed between their keys
    p = np.interp(np.arange(n), keys, pk) + np.arange(n) * 1e-4
    q = smooth_progress(p, SIGMA)
    keep = np.zeros(n)
    for k0, k1 in KEEP:
        for j in range(n):
            g = a + j
            if k0 <= g < k1:
                keep[j] = 1
            elif k0 - KEEP_EASE <= g < k0:
                keep[j] = max(keep[j], (g - (k0 - KEEP_EASE)) / KEEP_EASE)
            elif k1 <= g < k1 + KEEP_EASE:
                keep[j] = max(keep[j], 1 - (g - k1 + 1) / KEEP_EASE)
    q = (1 - keep) * q + keep * p                             # follow the source's own timing there
    out = []
    for j in range(n):
        if keep[j] >= 1:
            if KEEP_MODE == "hold":                           # nearest clean real frame: no ghosts, no bending
                out.append(seg[min(keys, key=lambda kk: abs(kk - j))])
            else:
                out.append(seg[j])                            # the original frame, untouched
            continue
        x = np.interp(q[j], pk + np.array(keys) * 1e-4, np.arange(len(kf)))   # position among clean keys
        i = min(int(np.floor(x)), len(kf) - 2)
        t = x - i
        if fast < 0:                                          # nearest clean real frame
            out.append(kf[i] if t < 0.5 else kf[i + 1])
        else:                                                 # fast motion: warp one frame, don't mix
            out.append(between(kf[i], kf[i + 1], fwd[i], bwd[i], t, mix=m[i] <= fast))
    out[0] = seg[0]                                           # first frame of the shot stays exact
    before = np.std(np.diff(p)) / max(np.mean(np.diff(p)), 1e-6)
    print(f"  frames {a}-{b - 1}: {len(ghosts)} blended source frames skipped, "
          f"ghost frames {ghostiness(seg)} -> {ghostiness(out)}")
    return out


# Frames 88-149 were rebuilt by tools/fix_sit_bg.py from cut-outs of her, and
# the matte trimmed her thin dark outline; frame 150 is untouched, so the
# outline popped back in at once. Fade it in over the frames before 150 by
# borrowing frame 150's outline, warped onto each frame (darken only).
OUTLINE_FROM, OUTLINE_TO = 132, 150
OUTLINE_BOX = (0, 950, 820, 1560)        # y0, y1, x0, x1 around her head and scarf


def bridge_outline(frames):
    y0, y1, x0, x1 = OUTLINE_BOX
    ref = frames[OUTLINE_TO]
    n = OUTLINE_TO - OUTLINE_FROM
    for k in range(OUTLINE_FROM, OUTLINE_TO):
        u = (k - OUTLINE_FROM + 1) / (n + 1)
        w = u * u * (3 - 2 * u)                               # smoothstep ramp
        cur = frames[k][y0:y1, x0:x1].astype(np.float32)
        r = ref[y0:y1, x0:x1]
        f = full(flow(frames[k][y0:y1, x0:x1], r), cur.shape)  # where each pixel of k sits in 150
        warped = warp(r, f, 1.0).astype(np.float32)
        lum = warped.mean(axis=2, keepdims=True)
        line = np.clip((95 - lum) / 45, 0, 1)                  # only frame 150's dark ink
        # keep only ink that borders the blue scarf (its outline), not sweater creases
        hsv = cv2.cvtColor(warped.astype(np.uint8), cv2.COLOR_BGR2HSV)
        scarf = ((hsv[..., 0] > 95) & (hsv[..., 0] < 125) & (hsv[..., 1] > 120) & (hsv[..., 2] > 70)).astype(np.uint8)
        near = cv2.dilate(scarf, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))).astype(np.float32)
        line = line * cv2.GaussianBlur(near, (5, 5), 0)[..., None]
        # ...and only where this frame has no ink of its own close by (the
        # trimmed outline), so lines it already has aren't doubled.
        own = (cur.mean(axis=2) < 60).astype(np.uint8)
        own = cv2.dilate(own, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
        line = line * (1 - cv2.GaussianBlur(own.astype(np.float32), (5, 5), 0))[..., None]
        darker = np.maximum(0, cur - warped)
        out = cur - w * line * darker
        frames[k] = frames[k].copy()
        frames[k][y0:y1, x0:x1] = np.clip(out, 0, 255).astype(np.uint8)


def encode(frames, dst, fps="30000/1001"):
    h, w = frames[0].shape[:2]
    dst.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([
        FFMPEG, "-v", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", fps, "-i", "-",
        "-i", str(MASTER if MASTER.exists() else BASE), "-map", "0:v", "-map", "1:a?",
        "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(dst)], stdin=subprocess.PIPE)
    for f in frames:
        proc.stdin.write(f.tobytes())
    proc.stdin.close()
    if proc.wait():
        sys.exit("ffmpeg failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="replace the live video with the result")
    ap.add_argument("--keep-mode", choices=["source", "hold"], default=KEEP_MODE)
    ap.add_argument("--out", default=str(PREVIEW))
    args = ap.parse_args()
    globals().update(KEEP_MODE=args.keep_mode, PREVIEW=Path(args.out))
    src = MASTER if MASTER.exists() else (BACKUP if BACKUP.exists() else BASE)
    print("reading", src.relative_to(ROOT))
    frames = read_frames(src)
    print(len(frames), "frames")
    frames = list(frames)
    bridge_outline(frames)
    out = list(frames)
    for a, b, limit, fast in SEGMENTS:
        out[a:b] = retime(frames, a, b, limit, fast)
    encode(out, PREVIEW)
    print("preview:", PREVIEW)
    if args.apply:
        if not BACKUP.exists():
            BACKUP.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BASE, BACKUP)
        shutil.copy2(PREVIEW, BASE)
        print("applied ->", BASE.relative_to(ROOT), "(previous kept at", BACKUP.relative_to(ROOT), ")")


if __name__ == "__main__":
    main()
