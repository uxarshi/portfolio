// Decides where the painting sits on screen: it always fills the screen
// (cover), centred on the girl and her thought bubble. Everything else (still
// image, WebGL scene, bubble) reads from the same layout, so they line up.

import meta from './scene-meta.json'

const OVERSCAN = 1.03 // a little extra so parallax never reveals an edge

export function computeLayout(vw, vh) {
  const [W, H] = meta.size
  const [fx, fy] = meta.focus

  const s = Math.max(vw / W, vh / H) * OVERSCAN
  const w = W * s
  const h = H * s
  // centre the focus point, but never show past the painting's edges
  const x = Math.min(0, Math.max(vw - w, vw / 2 - fx * s))
  const y = Math.min(0, Math.max(vh - h, vh * 0.52 - fy * s))

  return { vw, vh, s, x, y, w, h }
}

/** painting pixel → screen pixel */
export function toScreen(L, px, py) {
  return [L.x + px * L.s, L.y + py * L.s]
}

/** Enlarged thought bubble rectangle (screen px), anchored on the painted one. */
export function bubbleRect(L) {
  const [bx, by, bw, bh] = meta.bubble
  const painted = bw * L.s
  // readable size, but always a bit larger than the painted bubble it covers
  const width = Math.min(Math.max(Math.min(Math.max(painted * 1.6, 220), 340), painted * 1.35), L.vw - 24)
  const height = (width * 190) / 300
  const [sx, sy] = toScreen(L, bx, by + bh / 2) // bottom-centre of painted bubble
  let left = sx - width / 2
  left = Math.min(Math.max(12, left), L.vw - 12 - width)
  // cloud's lowest point sits on the painted one, but stay on screen
  const top = Math.max(12, sy - height * (182 / 190))
  return { left, top, width, height }
}

export { meta }
