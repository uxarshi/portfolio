# Portfolio: under construction

A living, hand-painted riverside scene (Vite + three.js) shown while the real
portfolio is being updated.

> **Status: Phase 1 (depth-map parallax prototype).** Layers, ambient animation
> and interactions come in the next phases.

## Run it

```bash
npm install
npm run dev       # http://localhost:5173
npm run build     # static site in dist/
npm run preview   # serve dist/ locally
```

Upload the **`dist/`** folder to any static host (Netlify, Vercel, GitHub
Pages…). Paths are relative, so it also works from a sub-folder.

## Change your name, messages and links

Everything personal is in **`src/config.js`**:

- `name`, `tagline`: shown in the footer and page title
- `messages`: the lines in the thought bubble (`{name}` is replaced)
- `reactions`: what she thinks when a balloon or cat is clicked
- `links`: email, Instagram, LinkedIn, Behance/Dribbble (leave `''` to hide one)
- `site`: page title, description, and the final `url` (needed so the social
  preview image works everywhere)
- `motion`: parallax strength, idle drift, tilt sensitivity, pixel-ratio cap

The `<head>` tags (title, description, Open Graph/Twitter preview) are filled
from this file automatically at build time.

## How it works

- `public/scene/scene.webp`: the landscape painting (`art/landscape.png`,
  WebP q95, visually identical to the PNG). It always fills the screen,
  centred on the girl and bubble, and shows immediately.
- `public/layers/*.webp` + `src/layers.json`: the same painting split into
  layers (sky, city, balloons, birds, leaves, trees, path, lamps, benches,
  cats, girl) with what was hidden behind each one painted in.
- `src/scene.js` + `src/shaders/layer.js`: draws the layers back to front.
  Each shifts by its depth relative to the girl, so she stays still; the trees
  and path follow the depth map (`public/layers/depth.webp`) so their far end
  moves less than the near end. The WebGL scene fades in over the still image
  once loaded. With *reduce motion* enabled, only the still + message are shown.
- `src/life.js`: the scene's ambient life. A breeze with slow gusts sways the
  trees and the girl's scarf, the river ripples, balloons bob, birds circle,
  leaves fall on the breeze (far ones, ones that land on the path, and a few
  big ones close to the camera). It all
  eases in over the first seconds, so the fade from the still is seamless.
- `src/interact.js`: click / tap a balloon (a soft "dub", it rises, then drifts back), a
  cat (it wags its tail, and a heart), a lamp (it switches on or off; they
  start dark, and the far ones follow) or the girl (next message). On touch, only a tap counts, so
  dragging to look around never triggers anything.
- Rendering pauses when the tab is hidden; device pixel ratio is capped at 2.
- In dev, `?cam=x,y` (each -1..1) pins the camera, e.g. `?cam=1,1`, to check
  the extremes.

### Rebuilding the image assets

Only needed if the painting changes:

```bash
pip3 install pillow numpy scipy onnxruntime
# optional, new depth map (Depth Anything V2 small):
curl -L -o tools/da2s.onnx https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx
python3 tools/estimate_depth.py          # art/landscape.png -> art/landscape_depth.png
# refine depth, export WebP + og.jpg:
npm run assets
# split into layers (needs tools/lama_fp32.onnx and opencv-python-headless;
# plates are cached in art/_plates.npz, pass --fresh to repaint them):
python3 tools/build_layers.py
# the falling leaves, cut from art/leaves_sheet.png:
python3 tools/build_leaves.py
```

If you change the painting, update the girl / bubble / balloon coordinates in
the `PAINTINGS` table at the top of `tools/build_phase1.py`.

## Files

```
index.html              page shell + <head> placeholders
src/config.js           ← your name, messages, links
src/main.js             boot: still first, then the scene
src/layout.js           keeps the girl + bubble in focus on any screen shape
src/scene.js            three.js renderer, layers, picking, render loop, tab-pause
src/shaders/layer.js    GLSL: parallax, sway, river ripple, scarf flutter
src/life.js             ambient animation + reactions
src/interact.js         click / tap handling
src/input.js            mouse / touch-drag / tilt (with the iOS permission tap)
src/ui.js               bubble messages, footer links, tilt hint, hearts
tools/                  Python asset pipeline
art/                    source paintings + raw depth maps
```
