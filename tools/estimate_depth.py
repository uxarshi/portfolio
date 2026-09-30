"""
Estimate a depth map for the illustration with Depth Anything V2 (small, ONNX).

Only needed if you change the source painting. The result is saved to
art/<name>_depth.png (bright = near) and is already committed, so the normal
build does not need this script.

    pip3 install onnxruntime pillow numpy
    curl -L -o tools/da2s.onnx \
      https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx
    python3 tools/estimate_depth.py            # uses art/landscape.png
    python3 tools/estimate_depth.py floor2     # or another painting in art/
"""
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
NAME = sys.argv[1] if len(sys.argv) > 1 else "landscape"
SRC = ROOT / "art" / f"{NAME}.png"
MODEL = ROOT / "tools" / "da2s.onnx"
OUT = ROOT / "art" / f"{NAME}_depth.png"

im = Image.open(SRC).convert("RGB")
W, H = im.size
sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
name = sess.get_inputs()[0].name

# Model works on multiples of 14 px; ~1036 px on the short side keeps edges crisp.
k = 1036 / min(W, H)
h = int(round(H * k / 14)) * 14
w = int(round(W * k / 14)) * 14
x = np.asarray(im.resize((w, h), Image.BICUBIC)).astype(np.float32) / 255.0
x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
x = x.transpose(2, 0, 1)[None].astype(np.float32)

d = sess.run(None, {name: x})[0].squeeze()
d = (d - d.min()) / (d.max() - d.min())
Image.fromarray((d * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC).save(OUT)
print("wrote", OUT)
