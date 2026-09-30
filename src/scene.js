// WebGL scene: renderer, camera, the painting split into layers, and the
// render loop. Loaded lazily after the still image is on screen.

import {
  WebGLRenderer,
  OrthographicCamera,
  Scene,
  Mesh,
  PlaneGeometry,
  ShaderMaterial,
  TextureLoader,
  CanvasTexture,
  Vector2,
  Vector4,
  LinearFilter,
  LinearMipmapLinearFilter,
  MirroredRepeatWrapping,
  NoColorSpace,
  NoBlending,
  NormalBlending,
  AdditiveBlending,
} from 'three'
import { vertexShader, fragmentShader, FX } from './shaders/layer.js'
import manifest from './layers.json'

const BASE = import.meta.env.BASE_URL
const [W, H] = manifest.size
const EDGE_PAD = 96 // painting px of mirrored image past the painting's edges
const GRID_CELL = 12 // painting px per grid cell for depth-mapped layers
const FX_BY_KIND = { city: FX.river, girl: FX.flutter, trees: FX.sway, leaf: FX.leaf, cat: FX.tail, balloon: FX.balloon }
// room for the scarf / tails to move past their rect, and for the hover rim
const PAD_BY_KIND = { girl: 14, cat: 20, balloon: 8, lamp: 8 }

function loadTexture(loader, url) {
  return new Promise((resolve, reject) => loader.load(url, resolve, undefined, reject))
}

/** Soft warm radial glow, drawn once. */
function glowTexture() {
  const size = 128
  const c = document.createElement('canvas')
  c.width = c.height = size
  const g = c.getContext('2d')
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  grad.addColorStop(0, 'rgba(255, 228, 170, 1)')
  grad.addColorStop(0.25, 'rgba(255, 206, 140, 0.55)')
  grad.addColorStop(0.6, 'rgba(255, 180, 120, 0.14)')
  grad.addColorStop(1, 'rgba(255, 170, 110, 0)')
  g.fillStyle = grad
  g.fillRect(0, 0, size, size)
  const t = new CanvasTexture(c)
  t.colorSpace = NoColorSpace
  return t
}

/** Alpha channel of a loaded texture, for picking by shape. */
function alphaOf(image) {
  const c = document.createElement('canvas')
  c.width = image.width
  c.height = image.height
  const g = c.getContext('2d', { willReadFrequently: true })
  g.drawImage(image, 0, 0)
  const px = g.getImageData(0, 0, c.width, c.height).data
  const a = new Uint8Array(c.width * c.height)
  for (let i = 0; i < a.length; i++) a[i] = px[i * 4 + 3]
  return { w: c.width, h: c.height, a }
}

export async function createScene({ container, config, input }) {
  const renderer = new WebGLRenderer({ antialias: false, alpha: false, powerPreference: 'default' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, config.motion.maxPixelRatio))
  renderer.setClearColor(0xf7d9c9, 1)
  container.appendChild(renderer.domElement)

  const camera = new OrthographicCamera(0, 1, 1, 0, -10, 10)
  const scene = new Scene()

  const loader = new TextureLoader()
  const city = manifest.layers.find((l) => l.waterMask)
  const trees = manifest.layers.find((l) => l.swayMap)
  const [depthMap, waterMap, swayMap, ...maps] = await Promise.all([
    loadTexture(loader, `${BASE}${manifest.depthMap}`),
    loadTexture(loader, `${BASE}${city?.waterMask ?? manifest.depthMap}`),
    loadTexture(loader, `${BASE}${trees?.swayMap ?? manifest.depthMap}`),
    ...manifest.layers.map((l) => loadTexture(loader, `${BASE}${l.file}`)),
  ])
  depthMap.colorSpace = NoColorSpace
  depthMap.minFilter = depthMap.magFilter = LinearFilter
  depthMap.generateMipmaps = false
  for (const t of [waterMap, swayMap]) {
    t.colorSpace = NoColorSpace
    t.minFilter = t.magFilter = LinearFilter
    t.generateMipmaps = false
  }

  // shared by every layer, updated once per frame / resize
  const shared = {
    uSize: { value: new Vector2(W, H) },
    uLayout: { value: new Vector4() },
    uShift: { value: new Vector2() },
    uFocus: { value: manifest.girlDepth },
    uDepthMap: { value: depthMap },
    uTime: { value: 0 },
    uWind: { value: 0 },
    uLife: { value: 0 },
    uPx: { value: 1 },
  }

  const layers = {} // by name
  const sprites = [] // every drawn sprite, in draw order
  let order = 0

  /**
   * Adds one sprite. `rect` is where its texture sits in the painting;
   * `depth` a number, or 'map' to follow the depth map.
   */
  function addSprite({ name, kind, rect, depth, map, additive = false, opacity = 1, renderOrder }) {
    const [x, y, w, h] = rect
    // layers that reach the painting's edge carry on past it, mirrored, so
    // moving them never opens a gap at the side of the screen
    const extra = PAD_BY_KIND[kind] || 0
    const pad = new Vector4(
      x <= 0 ? EDGE_PAD : extra,
      y <= 0 ? EDGE_PAD : extra,
      x + w >= W ? EDGE_PAD : extra,
      y + h >= H ? EDGE_PAD : extra,
    )
    if (x <= 0 || y <= 0 || x + w >= W || y + h >= H) map.wrapS = map.wrapT = MirroredRepeatWrapping

    const byMap = depth === 'map'
    const geometry = byMap
      ? new PlaneGeometry(1, 1, Math.ceil((w + pad.x + pad.z) / GRID_CELL), Math.ceil((h + pad.y + pad.w) / GRID_CELL))
      : new PlaneGeometry(1, 1)
    const opaque = kind === 'sky'
    const material = new ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: {
        ...shared,
        uMap: { value: map },
        uRect: { value: new Vector4(x, y, w, h) },
        uPad: { value: pad },
        uDepth: { value: byMap ? -1 : depth },
        uFx: { value: FX_BY_KIND[kind] ?? FX.none },
        uAnchor: { value: new Vector2(x + w / 2, y + h / 2) },
        uScale: { value: new Vector2(1, 1) },
        uRotation: { value: 0 },
        uOffset: { value: new Vector2() },
        uOpacity: { value: opacity },
        uFlip: { value: 1 },
        uHaze: { value: 0 },
        uStripe: { value: new Vector4(1, 1, 1, 0) },
        uSway: { value: depthMap }, // any texture until the trees layer sets its own
        uWater: { value: depthMap }, // any texture until the city layer sets its own
        uWaterRect: { value: new Vector4(0, 0, 1, 1) },
        uTail: { value: new Vector4() },
        uTailAmp: { value: 0 },
        uTailPhase: { value: 0 },
        uTailRest: { value: 0 },
        uCue: { value: 0 },
        uShine: { value: -1 },
      },
      transparent: !opaque,
      blending: opaque ? NoBlending : additive ? AdditiveBlending : NormalBlending,
      depthTest: false,
      depthWrite: false,
    })
    const mesh = new Mesh(geometry, material)
    mesh.frustumCulled = false // positions are computed in the shader
    mesh.renderOrder = renderOrder ?? order++
    scene.add(mesh)
    const sprite = { name, kind, rect, depth, mesh, u: material.uniforms, alpha: null }
    sprites.push(sprite)
    return sprite
  }

  // colours pass straight through (no colour-space conversion) so the WebGL
  // frame matches the still <img> underneath
  function prepare(map) {
    map.colorSpace = NoColorSpace
    map.minFilter = LinearMipmapLinearFilter
    map.generateMipmaps = true
    return map
  }

  manifest.layers.forEach((l, i) => {
    const map = prepare(maps[i])
    // keeps the manifest's extras too (a lamp's head, the river rect…)
    layers[l.name] = Object.assign(addSprite({ ...l, map }), l, { image: map.image })
    if (l.swayMap) layers[l.name].u.uSway.value = swayMap
    if (l.waterMask) {
      const u = layers[l.name].u
      u.uWater.value = waterMap
      u.uWaterRect.value.set(...l.river)
    }
  })

  // ── picking ────────────────────────────────────────────────────────────────
  let layout = null
  let parallaxPx = 0 // painting px per unit of (depth - focus) at full offset

  /** Where a painting point of this sprite currently is drawn (painting px). */
  function toSpriteSource(s, qx, qy) {
    const u = s.u
    const d = typeof s.depth === 'number' ? s.depth : manifest.girlDepth
    let x = qx - shared.uShift.value.x * (d - manifest.girlDepth) - u.uOffset.value.x - u.uAnchor.value.x
    let y = qy - shared.uShift.value.y * (d - manifest.girlDepth) - u.uOffset.value.y - u.uAnchor.value.y
    const c = Math.cos(-u.uRotation.value)
    const sn = Math.sin(-u.uRotation.value)
    ;[x, y] = [c * x - sn * y, sn * x + c * y]
    return [u.uAnchor.value.x + x / u.uScale.value.x, u.uAnchor.value.y + y / u.uScale.value.y]
  }

  function opaqueAt(s, px, py) {
    const [x0, y0, w, h] = s.rect
    const lx = Math.floor(px - x0)
    const ly = Math.floor(py - y0)
    if (lx < 0 || ly < 0 || lx >= w || ly >= h) return false
    s.alpha ??= alphaOf(s.image)
    const ax = Math.min(s.alpha.w - 1, Math.floor((lx / w) * s.alpha.w))
    const ay = Math.min(s.alpha.h - 1, Math.floor((ly / h) * s.alpha.h))
    return s.alpha.a[ay * s.alpha.w + ax] > 70
  }

  /**
   * The top-most sprite of one of `kinds` under a screen point, or null.
   * `radius` (screen px) makes small things easier to hit.
   */
  function pick(sx, sy, kinds, radius = 6) {
    if (!layout) return null
    const qx = (sx - layout.x) / layout.s
    const qy = (sy - layout.y) / layout.s
    const r = radius / layout.s
    const probes = [[0, 0], [r, 0], [-r, 0], [0, r], [0, -r]]
    for (let i = sprites.length - 1; i >= 0; i--) {
      const s = sprites[i]
      if (!kinds.includes(s.kind) || !s.image || s.u.uOpacity.value < 0.3) continue
      for (const [dx, dy] of probes) {
        const [px, py] = toSpriteSource(s, qx + dx, qy + dy)
        if (opaqueAt(s, px, py)) return s
      }
    }
    return null
  }

  /** painting px → screen px, for a point riding on a sprite. */
  function toScreen(s, px, py) {
    const d = typeof s.depth === 'number' ? s.depth : manifest.girlDepth
    const u = s.u
    const x = px + shared.uShift.value.x * (d - manifest.girlDepth) + u.uOffset.value.x
    const y = py + shared.uShift.value.y * (d - manifest.girlDepth) + u.uOffset.value.y
    return [layout.x + x * layout.s, layout.y + y * layout.s]
  }

  function setLayout(L) {
    layout = L
    renderer.setSize(L.vw, L.vh, false)
    camera.right = L.vw
    camera.top = L.vh
    camera.updateProjectionMatrix()
    shared.uLayout.value.set(L.x, L.y, L.s, L.vh)
    shared.uPx.value = 1 / L.s
    parallaxPx = (config.motion.parallax * L.vh) / L.s
  }

  // ── loop ───────────────────────────────────────────────────────────────────
  const onFrame = []
  let last = performance.now()
  let time = 0
  function frame(now) {
    const dt = Math.min((now - last) / 1000, 0.1)
    last = now
    time += dt
    const p = input.update(dt, now / 1000)
    // camera right / up: near things slide left / down, far things the other way
    shared.uShift.value.set(-p.x * parallaxPx, p.y * parallaxPx * config.motion.verticalRatio)
    shared.uTime.value = time
    for (const fn of onFrame) fn(dt, time)
    renderer.render(scene, camera)
  }

  let running = false
  function start() {
    if (running) return
    running = true
    last = performance.now()
    renderer.setAnimationLoop(frame)
  }
  function stop() {
    running = false
    renderer.setAnimationLoop(null)
  }

  // pause completely while the tab is hidden
  document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()))

  return {
    canvas: renderer.domElement,
    manifest,
    layers,
    sprites,
    shared,
    addSprite,
    glowTexture,
    /** Loads extra sprite textures (e.g. the drifting leaves). */
    loadTextures: (files) => Promise.all(files.map((f) => loadTexture(loader, `${BASE}${f}`).then(prepare))),
    pick,
    toScreen,
    /** Screen size in px (for keeping hints to things that are on screen). */
    viewport: () => (layout ? [layout.vw, layout.vh] : [innerWidth, innerHeight]),
    onFrame,
    setLayout,
    start,
    stop,
    // compile after life.js has added its sprites, so the first frame is ready
    compile: () => renderer.compile(scene, camera),
  }
}
