"""LaMa inpainting (ONNX, fixed 512x512 input) for arbitrary-size holes.

Small holes are filled at full resolution. Big holes get a coarse pass on a
downscaled crop, then a full-resolution pass along their edges, which is the
only part that can ever be revealed by parallax.
"""
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image
from scipy import ndimage as ndi

MODEL = Path(__file__).resolve().parent.parent / "lama_fp32.onnx"
N = 512
_sess = None


def _session():
    global _sess
    if _sess is None:
        if not MODEL.exists():
            raise SystemExit(
                f"LaMa model not found at {MODEL}.\n"
                "Download it with:\n  curl -L -o tools/lama_fp32.onnx "
                "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx"
            )
        _sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _sess


def _run(crop, hole):
    """crop: HxWx3 float 0..1 with H,W <= 512; hole: HxW bool. Returns filled crop."""
    h, w = hole.shape
    img = np.zeros((N, N, 3), np.float32)
    msk = np.zeros((N, N), np.float32)
    img[:h, :w] = crop
    msk[:h, :w] = hole
    # pad by mirroring so the model sees plausible context at the border
    if h < N:
        img[h:, :w] = crop[::-1][: N - h] if N - h <= h else np.resize(crop[::-1], (N - h, w, 3))
    if w < N:
        img[:, w:] = img[:, :w][:, ::-1][:, : N - w] if N - w <= w else np.resize(img[:, :w][:, ::-1], (N, N - w, 3))
    out = _session().run(None, {"image": img.transpose(2, 0, 1)[None], "mask": msk[None, None]})[0][0]
    out = np.clip(out.transpose(1, 2, 0) / 255.0, 0, 1)[:h, :w]
    return np.where(hole[..., None], out, crop)


def _fill_box(img, hole, x0, y0, x1, y1):
    crop, h = img[y0:y1, x0:x1], hole[y0:y1, x0:x1]
    if not h.any():
        return
    ch, cw = h.shape
    if ch <= N and cw <= N:
        img[y0:y1, x0:x1] = _run(crop, h)
        return
    k = N / max(ch, cw)
    sw, sh = max(8, int(cw * k)), max(8, int(ch * k))
    small = np.asarray(Image.fromarray((crop * 255).astype(np.uint8)).resize((sw, sh), Image.LANCZOS)) / 255.0
    hs = np.asarray(Image.fromarray(h.astype(np.uint8) * 255).resize((sw, sh), Image.BILINEAR)) > 0
    hs = ndi.binary_dilation(hs, iterations=2)
    filled = _run(small.astype(np.float32), hs)
    up = np.asarray(Image.fromarray((filled * 255).astype(np.uint8)).resize((cw, ch), Image.BICUBIC)) / 255.0
    img[y0:y1, x0:x1] = np.where(h[..., None], up, crop)


def inpaint(img, hole, context=48, band=56):
    """Fill `hole` (bool HxW) in `img` (float RGB 0..1). Returns a new image."""
    img = img.astype(np.float32).copy()
    H, W = hole.shape
    lab, n = ndi.label(ndi.binary_dilation(hole, iterations=12))
    for sl in ndi.find_objects(lab):
        y0, y1 = max(0, sl[0].start - context), min(H, sl[0].stop + context)
        x0, x1 = max(0, sl[1].start - context), min(W, sl[1].stop + context)
        big = (y1 - y0) > N or (x1 - x0) > N
        _fill_box(img, hole, x0, y0, x1, y1)
        if big:
            # sharpen the part that parallax can reveal: the rim of the hole
            rim = hole & ndi.binary_dilation(~hole, iterations=band)
            step = N - 128
            for ty in range(y0, max(y0 + 1, y1 - 128), step):
                for tx in range(x0, max(x0 + 1, x1 - 128), step):
                    by1, bx1 = min(H, ty + N), min(W, tx + N)
                    r = rim[ty:by1, tx:bx1]
                    if r.any():
                        img[ty:by1, tx:bx1] = _run(img[ty:by1, tx:bx1], r)
    return img
