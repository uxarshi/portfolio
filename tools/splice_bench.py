"""Splice regenerated bench-scene clips into the walk video.

Takes the output of build_walk.py (saved as
source/intro-walk-before-bench-fix.mp4; copy it there again if you rebuild)
and replaces the bench scene with clips generated on Higgsfield (Wan 3.0,
1080p), each lined up with the source frame it joins and retimed to exactly
fill the frames it replaces, so the soundtrack stays in sync:

  172-285  source/bench-glasses.mp4  glasses on, laptop closed onto her lap
           (start: frame 172; end: source/bench-end-frame.jpg)

The clip's colours are matched to frame 172 frame by frame (generators
drift warm).

The laptop's logo in the first frames of the over-the-shoulder shot (286-305)
is a smudged blob in the source; it is painted out and redrawn from a clean
silhouette (source/apple-logo-mask.png) at the same place, size, tilt and
colour, frame by frame (fix_logo).

Writes assets/video/intro-walk-preview.mp4. Once approved, copy it over
assets/video/intro-walk.mp4 (python3 tools/splice_bench.py --apply).
"""
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "source/intro-walk-before-bench-fix.mp4"   # output of build_walk.py
LIVE = ROOT / "assets/video/intro-walk.mp4"
OUT = ROOT / "assets/video/intro-walk-preview.mp4"
W, H = 1920, 1080
COLOR_REF = 172           # every clip's colours are matched to this source frame
# (first frame replaced, first frame kept after, clip, which end of the clip is
#  an exact source frame to line it up on)
SEGMENTS = [
    (172, 286, ROOT / "source/bench-glasses.mp4", "start", None),
]
REF_REGION = (0, 0, 820, 1080)   # sky, town, river, railing: she is never there


def color_match(clip, ref):
    """Per-frame Lab mean/std correction so the clip's colours and light stay
    exactly those of the reference frame (generators drift warm), measured on
    REF_REGION and smoothed over time so it never flickers."""
    x0, y0, x1, y1 = REF_REGION
    def stats(img):
        lab = cv2.cvtColor(np.ascontiguousarray(img[y0:y1, x0:x1]), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
        return lab.mean(0), lab.std(0) + 1e-3
    rm, rs = stats(ref)
    params = np.array([np.concatenate(stats(f)) for f in clip])
    k = 7
    pad = np.pad(params, ((k, k), (0, 0)), mode="edge")
    params = np.array([pad[i:i + 2 * k + 1].mean(0) for i in range(len(params))])
    out = []
    for f, p in zip(clip, params):
        m, sd = p[:3], p[3:]
        lab = cv2.cvtColor(f, cv2.COLOR_BGR2LAB).astype(np.float32)
        lab = (lab - m) / sd * rs + rm
        out.append(cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR))
    return out


def frames(path, scale=None):
    vf = "scale=in_color_matrix=bt709:in_range=tv"
    if scale:
        vf += f",scale={scale[0]}:{scale[1]}:flags=lanczos"
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf, "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, check=True)
    return np.frombuffer(p.stdout, np.uint8).reshape(-1, H, W, 3)


def align(a, b):
    """Affine taking clip frame a onto base frame b (matched on the background)."""
    sift = cv2.SIFT_create(8000)
    g = lambda im: cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    k1, d1 = sift.detectAndCompute(g(a), None)
    k2, d2 = sift.detectAndCompute(g(b), None)
    m = [x for x, y in cv2.BFMatcher().knnMatch(d1, d2, k=2) if x.distance < 0.75 * y.distance]
    A, inl = cv2.estimateAffinePartial2D(np.float32([k1[x.queryIdx].pt for x in m]),
                                         np.float32([k2[x.trainIdx].pt for x in m]),
                                         method=cv2.RANSAC, ransacReprojThreshold=3)
    print(f"aligned on {int(inl.sum())} points, scale {np.hypot(A[0, 0], A[1, 0]):.4f}, "
          f"shift ({A[0, 2]:.1f}, {A[1, 2]:.1f})")
    return A


LOGO_MASK = ROOT / "source/apple-logo-mask.png"
# Frames with the closed lid in view, and where to look for the logo on it
# (the lid starts to lift at 299 and is nearly edge-on at 304-305).
LOGO_FRAMES = [(n, (860, 720, 1100, 870)) for n in range(286, 304)] + \
              [(n, (900, 722, 1050, 762)) for n in (304, 305)]


def fix_logo(frames_out):
    apple = cv2.imread(str(LOGO_MASK), cv2.IMREAD_GRAYSCALE)
    for n, (x0, y0, x1, y1) in LOGO_FRAMES:
        f = frames_out[n].copy()
        pad = 150
        X0, Y0, X1, Y1 = max(x0 - pad, 0), max(y0 - pad, 0), min(x1 + pad, W), min(y1 + pad, H)
        crop = f[y0:y1, x0:x1]
        if y1 - y0 > 80:
            big = f[Y0:Y1, X0:X1]
            bg = cv2.medianBlur(big, 151)[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0].astype(np.float32)
        else:
            # lid nearly edge-on: the logo is a thin streak; a grey opening
            # wipes it off the lid to give the background under it
            bg = cv2.morphologyEx(crop, cv2.MORPH_OPEN,
                                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (35, 35))).astype(np.float32)
        lum = (crop.astype(np.float32) - bg).mean(2)
        m = (lum > 9).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        k, lab, st, _ = cv2.connectedComponentsWithStats(m)
        if k <= 1:
            continue
        i = 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])
        bx, by, bw, bh, _a = st[i]
        blob = (lab == i).astype(np.uint8)
        colour = np.median(crop[blob > 0], axis=0).astype(np.float32)
        # paint the blob out (the lid is a smooth gradient)
        hole = cv2.dilate(blob, np.ones((3, 3), np.uint8), iterations=3)
        clean = cv2.inpaint(crop, hole, 5, cv2.INPAINT_TELEA).astype(np.float32)
        # the clean logo, fitted to the blob's box (that box carries the lid's tilt)
        a = cv2.resize(apple, (bw, bh), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
        a = cv2.GaussianBlur(a, (0, 0), 0.6)[..., None]
        grain = np.random.default_rng(n).normal(0, 3, (bh, bw, 1)).astype(np.float32)
        region = clean[by:by + bh, bx:bx + bw]
        clean[by:by + bh, bx:bx + bw] = (colour + grain) * a + region * (1 - a)
        f[y0:y1, x0:x1] = np.clip(clean, 0, 255).astype(np.uint8)
        frames_out[n] = f


def main():
    if "--apply" in sys.argv:
        shutil.copyfile(OUT, LIVE)
        print("copied", OUT.name, "over", LIVE.name)
        return
    base = frames(BASE)
    out = list(base)
    for first, cut, clip_path, anchor, pieces in SEGMENTS:
        if not clip_path.exists():
            print("skipping", clip_path.name, "(not there)")
            continue
        print(clip_path.name)
        clip = frames(clip_path, (W, H))
        A = align(clip[0], base[first]) if anchor == "start" else align(clip[-1], base[cut])
        clip = color_match(clip, base[COLOR_REF])
        pieces = pieces or [(0, len(clip) - 1)]
        n = cut - first
        lengths = [b - a + 1 for a, b in pieces]
        counts = [round(n * L / sum(lengths)) for L in lengths]
        counts[-1] = n - sum(counts[:-1])
        k = first
        for (a, b), cnt in zip(pieces, counts):
            for i in range(cnt):
                t = a + (i * (b - a) / (cnt - 1) if cnt > 1 else 0)
                j, f = int(t), t - int(t)
                img = clip[j].astype(np.float32) * (1 - f) + clip[min(j + 1, b)].astype(np.float32) * f
                out[k] = cv2.warpAffine(img.astype(np.uint8), A, (W, H), flags=cv2.INTER_CUBIC,
                                        borderMode=cv2.BORDER_REFLECT)
                k += 1
    fix_logo(out)
    print("frames", len(out), "(base", len(base), ")")

    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-framerate", "30000/1001", "-i", "-",
           "-i", str(BASE), "-map", "0:v", "-map", "1:a", "-c:a", "copy",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,"
                  "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(OUT)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in out:
        enc.stdin.write(np.ascontiguousarray(f).tobytes())
    enc.stdin.close()
    enc.wait()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
