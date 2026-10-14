"""Hold one background while she turns and sits (frames 88-149, 2.94-4.97 s).

In the source the close shot starts on a standing composition (88-105), then
the AI cross-dissolves the whole background into the seated composition
(106-117) while the camera keeps pushing in until it settles at frame 150.
Here the background of frame 150 (the seated shot once the camera has
stopped) is used for the whole stretch, with her cut out of every frame and
laid over it:

  118-149  she is tracked on herself (head, hijab, dress: the camera push
           grows her faster than the distant background) and held where she
           sits in frame 150, so she stays put on the bench.
  88-105   she keeps her own movement but is placed (V) at her seat, at
           nearly her seated size, so she covers what she will hide.
  106-117  (the dissolve) her placement eases from one to the other.

The parts of frame 150's background she uncovers on the way are filled with
LaMa in native-resolution tiles. Frames 0-87 and 150-end are untouched, and
the soundtrack is copied as is.

Base: source/intro-walk-before-sit-fix.mp4 (the live video before this fix).
Writes assets/video/intro-walk-preview.mp4; once approved,
python3 tools/fix_sit_bg.py --apply copies it over assets/video/intro-walk.mp4.

Needs opencv, onnxruntime, rembg (isnet-anime) and ../my website/tools/lama_fp32.onnx.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image
from rembg import new_session, remove

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "source/intro-walk-before-sit-fix.mp4"
LIVE = ROOT / "assets/video/intro-walk.mp4"
OUT = ROOT / "assets/video/intro-walk-preview.mp4"
LAMA = ROOT.parent / "my website/tools/lama_fp32.onnx"
W, H = 1920, 1080

FIRST, PLATE = 88, 150          # frames FIRST..PLATE-1 are rebuilt over frame PLATE
A_LAST, B_FIRST = 105, 118      # standing shot ends / seated shot is clean from
STAND_RATIO = 0.85              # standing head width / seated head width
STAND_DX = -40                  # standing head centre relative to her seated head (px)
SMOOTH = 2.5                    # frames: smoothing of her head path (cancels leftover judder)
EXTRA = 10                      # untouched frames after PLATE used to anchor that smoothing
LAP_TOP, LAP_RIGHT = 975, 1160  # her lap in frame PLATE: below her hands, left of the bag
STAND_TOP = 48                  # highest her head may reach while standing (px from the top)


def frames(path):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "scale=in_color_matrix=bt709:in_range=tv",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    while True:
        buf = p.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    p.wait()


# ---------- matte ----------

_session = None


def matte(img):
    """Soft alpha of her (hijab, dress, bag, hands); bench slivers dropped."""
    global _session
    if _session is None:
        _session = new_session("isnet-anime")
    a = np.asarray(remove(Image.fromarray(img[:, :, ::-1]), session=_session, only_mask=True), np.float32) / 255
    n, lab, st, _ = cv2.connectedComponentsWithStats((a > 0.5).astype(np.uint8))
    if n > 1:
        big = 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])
        keep = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 0.03 * st[big, cv2.CC_STAT_AREA]])
        a *= cv2.dilate(keep.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    # pull the edge in a touch: the outermost pixels carry the old background
    return np.clip((cv2.erode(a, np.ones((3, 3), np.uint8)) - 0.08) / 0.92, 0, 1)


# ---------- camera ----------

_sift = cv2.SIFT_create(6000)


def similarity(src, dst, src_alpha, dst_alpha, on="background"):
    """Similarity taking src onto dst, matched on the background (she is
    masked out) or on her (background masked out)."""
    g = lambda im: cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    if on == "background":
        m = lambda a: ((cv2.dilate((a > 0.1).astype(np.uint8), np.ones((41, 41), np.uint8)) == 0) * 255).astype(np.uint8)
    else:
        m = lambda a: ((cv2.erode((a > 0.5).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0) * 255).astype(np.uint8)
    k1, d1 = _sift.detectAndCompute(g(src), m(src_alpha))
    k2, d2 = _sift.detectAndCompute(g(dst), m(dst_alpha))
    ms = [a for a, b in cv2.BFMatcher().knnMatch(d1, d2, k=2) if a.distance < 0.75 * b.distance]
    if len(ms) < 8:
        return None, 0
    A, inl = cv2.estimateAffinePartial2D(np.float32([k1[x.queryIdx].pt for x in ms]),
                                        np.float32([k2[x.trainIdx].pt for x in ms]), ransacReprojThreshold=4)
    return (A, int(inl.sum())) if A is not None else (None, 0)


def to_params(A):
    s = np.hypot(A[0, 0], A[1, 0])
    return np.array([np.log(s), np.arctan2(A[1, 0], A[0, 0]), A[0, 2], A[1, 2]])


def to_affine(p):
    s, r = np.exp(p[0]), p[1]
    return np.array([[s * np.cos(r), -s * np.sin(r), p[2]], [s * np.sin(r), s * np.cos(r), p[3]]])


def smooth_fit(ns, ps, ws, out, deg=3):
    """Robust weighted polynomial fit of each parameter against progress
    (ns: progress of each sample; out: {frame: progress} to evaluate)."""
    ns, ps, ws = np.asarray(ns, float), np.asarray(ps), np.asarray(ws, float)
    keep = np.ones(len(ns), bool)
    for _ in range(3):
        res = np.zeros(len(ns))
        coefs = []
        for j in range(ps.shape[1]):
            c = np.polyfit(ns[keep], ps[keep, j], deg, w=np.sqrt(ws[keep]))
            coefs.append(c)
            r = np.abs(np.polyval(c, ns) - ps[:, j])
            res = np.maximum(res, r / (1.4826 * np.median(r[keep]) + 1e-6))
        keep = (res < 3) | (ws >= 5000)
    return {n: np.array([np.polyval(c, x) for c in coefs]) for n, x in out.items()}


def progress(src, alpha, ns):
    """How far she has moved by each frame, in px. The source is unevenly
    timed (24 fps made 29.97: about one frame in five is a repeat or a blend),
    so corrections are laid out along this, not along the frame number:
    otherwise she jerks against the still background on every repeat."""
    g = lambda f: cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    tau = {ns[0]: 0.0}
    for a, b in zip(ns, ns[1:]):
        flow = cv2.calcOpticalFlowFarneback(g(src[a]), g(src[b]), None, 0.5, 4, 25, 3, 5, 1.2, 0)
        m = cv2.resize(alpha[b], (W // 2, H // 2)) > 0.5
        tau[b] = tau[a] + float(np.hypot(*np.median(flow[m], axis=0)))
    return tau


def midway(a, b):
    """The frame halfway between two (image, alpha) pairs, by optical flow."""
    g = lambda im, al: cv2.cvtColor((im * al[:, :, None]).astype(np.uint8), cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(g(*a), g(*b), None, 0.5, 5, 31, 3, 7, 1.5, 0)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    def pull(pair, f):
        mx, my = xx + f[..., 0], yy + f[..., 1]
        return (cv2.remap(pair[0], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE),
                cv2.remap(pair[1], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE))
    ia, aa = pull(a, -0.5 * flow)
    ib, ab = pull(b, 0.5 * flow)
    return ((ia.astype(np.float32) + ib) / 2).astype(np.uint8), (aa + ab) / 2


def head(alpha):
    ys, xs = np.nonzero(alpha > 0.5)
    top = ys.min()
    hx = np.nonzero((alpha[top:top + 120] > 0.5).any(0))[0]
    return (hx.min() + hx.max()) / 2, hx.max() - hx.min(), top


# ---------- plate ----------

_lama = None


def lama_fill(img, hole):
    """Inpaint `hole` (bool) one window per patch (as in build_hero.py)."""
    global _lama
    if _lama is None:
        _lama = ort.InferenceSession(str(LAMA), providers=["CPUExecutionProvider"])
    out = img.copy()
    n, lab, st, _ = cv2.connectedComponentsWithStats(hole.astype(np.uint8))
    for i in range(1, n):
        x, y, w, h, _a = st[i]
        size = max(int(max(w, h) * 2.2), 256)
        cx, cy = x + w // 2, y + h // 2
        X0 = int(np.clip(cx - size // 2, 0, max(0, W - size)))
        Y0 = int(np.clip(cy - size // 2, 0, max(0, H - size)))
        X1, Y1 = min(W, X0 + size), min(H, Y0 + size)
        crop = out[Y0:Y1, X0:X1]
        m = (lab[Y0:Y1, X0:X1] == i).astype(np.uint8)
        ci = cv2.resize(crop, (512, 512), interpolation=cv2.INTER_AREA)
        cm = cv2.resize(m, (512, 512), interpolation=cv2.INTER_NEAREST)
        r = _lama.run(None, {"image": ci[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255,
                             "mask": (cm > 0)[None, None].astype(np.float32)})[0][0].transpose(1, 2, 0)[:, :, ::-1]
        if r.max() <= 1.5:
            r = r * 255
        r = cv2.resize(np.clip(r, 0, 255).astype(np.uint8), (X1 - X0, Y1 - Y0), interpolation=cv2.INTER_CUBIC)
        crop[m > 0] = r[m > 0]
    return out


def main():
    if "--apply" in sys.argv:
        shutil.copyfile(OUT, LIVE)
        print("copied", OUT.name, "over", LIVE.name)
        return
    if not BASE.exists():
        shutil.copyfile(LIVE, BASE)

    src = {}
    for i, f in enumerate(frames(BASE)):
        if FIRST <= i <= PLATE + EXTRA:
            src[i] = f.copy()
        if i > PLATE + EXTRA:
            break
    cache = Path(tempfile.gettempdir()) / "fix_sit_bg_mattes.npz"
    z = np.load(cache) if cache.exists() and cache.stat().st_mtime > BASE.stat().st_mtime else None
    if z is not None and all(str(n) in z for n in src):
        alpha = {n: z[str(n)].astype(np.float32) / 255 for n in src}
    else:
        print("matting", len(src), "frames")
        alpha = {n: matte(f) for n, f in src.items()}
        np.savez_compressed(cache, **{str(n): (a * 255).astype(np.uint8) for n, a in alpha.items()})

    tau = progress(src, alpha, list(range(FIRST, PLATE + 1)))

    # seated shot: pin her head (size, centre, top; smoothed) to where it is at
    # PLATE. Matching features on her fails (flat crayon colour, moving hands)
    # and the background undercounts how fast she grows as the camera pushes in.
    ns = list(range(B_FIRST, PLATE + 1))
    hm = np.array([head(alpha[n]) for n in ns], float)
    ts = [tau[n] for n in ns]
    fit = lambda col: np.polyval(np.polyfit(ts, hm[:, col], 3), ts)
    hx, hw, ht = fit(0), fit(1), fit(2)
    hx, hw, ht = hx - hx[-1] + hm[-1, 0], hw * hm[-1, 1] / hw[-1], ht - ht[-1] + hm[-1, 2]
    TB = {}
    for i, n in enumerate(ns):
        k = hm[-1, 1] / hw[i]
        TB[n] = np.array([np.log(k), 0.0, hm[-1, 0] - k * hx[i], hm[-1, 2] - k * ht[i]])
    TB[PLATE] = np.zeros(4)

    # standing shot: camera n -> A_LAST
    ns, ps, ws = [], [], []
    for n in range(FIRST, A_LAST):
        A, inl = similarity(src[n], src[A_LAST], alpha[n], alpha[A_LAST])
        if A is None or inl < 12:
            continue
        ns.append(tau[n]); ps.append(to_params(A)); ws.append(inl)
    ns.append(tau[A_LAST]); ps.append(np.zeros(4)); ws.append(5000)
    TA = smooth_fit(ns, ps, ws, {n: tau[n] for n in range(FIRST, A_LAST + 1)}, deg=2)
    TA[A_LAST] = np.zeros(4)

    # V: standing shot -> plate coordinates, at her seat, a little smaller than
    # seated, head kept in frame (she runs off the bottom edge either way)
    hx_b, hw_b, _ = head(cv2.warpAffine(alpha[B_FIRST], to_affine(TB[B_FIRST]), (W, H)))
    hx_a, hw_a, _ = head(alpha[A_LAST])
    s = max(1.0, STAND_RATIO * hw_b / hw_a)
    tops = [head(cv2.warpAffine(alpha[n], to_affine(TA[n]), (W, H)))[2] for n in range(FIRST, A_LAST + 1)]
    ty = STAND_TOP - s * min(tops)
    tx = (hx_b + STAND_DX) - s * hx_a
    V = np.array([np.log(s), 0.0, tx, ty])
    print(f"seated head x {hx_b:.0f} w {hw_b}, standing head x {hx_a:.0f} w {hw_a} -> V scale {s:.3f} tx {tx:.0f} ty {ty:.0f}")

    def compose(p, q):     # affine of q applied after p
        A, B = np.vstack([to_affine(p), [0, 0, 1]]), np.vstack([to_affine(q), [0, 0, 1]])
        return to_params((B @ A)[:2])

    T = {}
    seated = {n: 0.0 for n in range(FIRST, A_LAST + 1)}
    seated.update({n: 1.0 for n in range(B_FIRST, PLATE + 1)})
    for n in range(FIRST, A_LAST + 1):
        T[n] = compose(TA[n], V)
    for n in range(B_FIRST, PLATE + 1):
        T[n] = TB[n]
    for n in range(A_LAST + 1, B_FIRST):
        u = (tau[n] - tau[A_LAST]) / (tau[B_FIRST] - tau[A_LAST])
        u = u * u * (3 - 2 * u)
        T[n] = (1 - u) * T[A_LAST] + u * T[B_FIRST]
        seated[n] = u

    # last pass: smooth the path of her head (top centre) as it lands in the
    # frame, and shift each frame onto it. Frames after PLATE are untouched
    # and anchor the end, so the join stays seamless.
    seq = list(range(FIRST, PLATE + EXTRA + 1))
    pts = []
    for n in seq:
        M = to_affine(T.get(n, np.zeros(4)))
        hx_, _, ht_ = head(alpha[n])
        pts.append(M @ np.array([hx_, ht_, 1.0]))
    pts = np.array(pts)
    pad = int(4 * SMOOTH)
    padded = np.vstack([np.repeat(pts[:1], pad, 0), pts])
    k = np.exp(-0.5 * (np.arange(-pad, pad + 1) / SMOOTH) ** 2)
    k /= k.sum()
    sm = np.array([np.convolve(np.pad(padded[:, j], (0, pad), mode="edge"), k, mode="valid") for j in range(2)]).T[:len(seq)]
    for i, n in enumerate(seq):
        if n >= PLATE:
            break
        taper = min(1.0, (PLATE - n) / 4)
        T[n] = T[n] + np.array([0, 0, *(sm[i] - pts[i]) * taper])

    warped = {}
    for n in range(FIRST, PLATE):
        M = to_affine(T[n])
        warped[n] = (cv2.warpAffine(src[n], M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE),
                     cv2.warpAffine(alpha[n], M, (W, H), flags=cv2.INTER_LINEAR))
        # keep her running off the bottom edge when she is lifted a little
        a = warped[n][1]
        last = np.nonzero(a.max(1) > 0.5)[0].max()
        if last < H - 1:
            a[last:] = a[last:last + 1]
            warped[n][0][last:] = warped[n][0][last:last + 1]

    # the source repeats a frame now and then (she freezes for a frame):
    # rebuild those as the in-between of their neighbours, along the motion
    for n in range(FIRST + 1, PLATE - 1):
        if np.abs(src[n].astype(np.int16) - src[n - 1]).mean() < 2:
            warped[n] = midway(warped[n - 1], warped[n + 1])
            print("in-between for repeated frame", n)

    # plate: frame PLATE with what she uncovers filled in
    hole = cv2.dilate((alpha[PLATE] > 0.02).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
    seen = np.zeros((H, W), bool)
    for n in range(FIRST, PLATE):
        seen |= warped[n][1] < 0.98
    fill = cv2.dilate((hole & seen).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    print("uncovered", int(fill.sum()), "px of background")
    # inpaint her whole outline so LaMa only sees real background as context,
    # then use it only where she ever uncovers it
    filled = lama_fill(src[PLATE], hole)
    plate = src[PLATE].copy()
    plate[fill] = filled[fill]

    # her lap hardly moves once she sits, but the matte keeps losing it (the
    # path showed through and it flickered): frame PLATE's lap stays under
    # her, coming in as she sits down
    yy, xx = np.mgrid[0:H, 0:W]
    # (the block under and around it, shadow between lap and bag included)
    near = cv2.dilate((alpha[PLATE] > 0.5).astype(np.uint8), np.ones((45, 45), np.uint8)) > 0
    lap = (near & (yy >= LAP_TOP) & (xx <= LAP_RIGHT)).astype(np.float32)
    lap = cv2.GaussianBlur(lap, (0, 0), 6)

    out = {}
    for n in range(FIRST, PLATE):
        img, a = warped[n]
        L = (lap * seated[n])[:, :, None]
        bg = plate * (1 - L) + src[PLATE] * L
        a3 = a[:, :, None]
        out[n] = (bg * (1 - a3) + img * a3).astype(np.uint8)

    cv2.imwrite(str(ROOT / "source/sit-plate.jpg"), plate, [cv2.IMWRITE_JPEG_QUALITY, 95])

    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-framerate", "30000/1001", "-i", "-",
           "-i", str(BASE), "-map", "0:v", "-map", "1:a", "-c:a", "copy",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,"
                  "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(OUT)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i, f in enumerate(frames(BASE)):
        enc.stdin.write((out.get(i, f)).tobytes())
    enc.stdin.close()
    enc.wait()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
