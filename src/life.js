// Phase 3: the scene's ambient life (breeze, bobbing balloons, circling
// birds, falling leaves, lamp glow, cats' tails) and how things react
// when clicked or tapped.
//
// Everything eases in over the first few seconds, so the first frames still
// match the painting exactly while the canvas fades in over the still image.

import leafSet from './leaves.json'

const TAU = Math.PI * 2
const clamp01 = (v) => Math.min(1, Math.max(0, v))
const smooth = (a, b, x) => {
  const t = clamp01((x - a) / (b - a))
  return t * t * (3 - 2 * t)
}
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
const rand = (a, b) => a + Math.random() * (b - a)
const pickOne = (list) => list[Math.floor(Math.random() * list.length)]

export async function createLife(scene, { messages, config, pop, banner, sound }) {
  const { manifest, layers, sprites, addSprite, shared } = scene
  const [W, H] = manifest.size
  const ofKind = (k) => sprites.filter((s) => s.kind === k)
  const now = () => shared.uTime.value
  let wake = 0

  // ── wind: a steady breeze with slow gusts, shared by everything ────────────
  function wind(t) {
    const swell = 0.5 + 0.5 * Math.sin(t * 0.23) * Math.sin(t * 0.071 + 1.2)
    const gust = Math.max(0, Math.sin(t * 0.11 + 0.8)) ** 6
    return clamp01(0.25 + 0.45 * swell + 0.35 * gust)
  }

  // ── balloons: bob and swing from the top; clicked, they rise and return ────
  // (lowering a little banner with a kind word while they're up)
  // A few more on the left of the sky: copies of the big painted balloon,
  // smaller and hazier the farther they are, each with its own stripe colour
  // (all below painting y ~290, the top edge of the sky on a 16:9 screen)
  const EXTRA_BALLOONS = [
    { at: [135, 335], h: 74, depth: 0.066, stripe: [0.95, 0.66, 0.72], haze: 0.04 }, // pink
    { at: [250, 335], h: 50, depth: 0.058, stripe: [0.76, 0.7, 0.92], haze: 0.07 }, // lavender
    { at: [395, 400], h: 40, depth: 0.052, stripe: null, haze: 0.08 }, // the painted blue
    { at: [480, 520], h: 46, depth: 0.055, stripe: [0.98, 0.86, 0.58], haze: 0.08 }, // butter yellow
    { at: [130, 470], h: 28, depth: 0.036, stripe: null, haze: 0.22 }, // far blue
    { at: [255, 520], h: 36, depth: 0.042, stripe: [0.96, 0.6, 0.46], haze: 0.15 }, // coral
    { at: [705, 505], h: 30, depth: 0.038, stripe: [0.64, 0.84, 0.74], haze: 0.2 }, // mint
  ]
  const big = layers['balloon-1']
  EXTRA_BALLOONS.forEach((b, i) => {
    const w = (b.h * big.rect[2]) / big.rect[3]
    const s = addSprite({
      name: `balloon-extra-${i + 1}`,
      kind: 'balloon',
      rect: [b.at[0] - w / 2, b.at[1] - b.h / 2, w, b.h],
      depth: b.depth,
      map: big.u.uMap.value,
      renderOrder: big.mesh.renderOrder - 0.5 + b.depth, // farther ones behind
    })
    s.image = big.image // for clicking
    if (b.stripe) s.u.uStripe.value.set(...b.stripe, 0.9)
    s.u.uHaze.value = b.haze
  })
  const balloons = ofKind('balloon').map((s) => {
    const [x, y, w] = s.rect
    s.u.uAnchor.value.set(x + w / 2, y + 4)
    return { s, ph: rand(0, TAU), period: rand(6, 9), lift: rand(95, 130), poked: -1e9, banner: null, line: '' }
  })
  const biggest = Math.max(...balloons.map((b) => b.s.rect[3]))
  let words = [] // the banner lines not yet seen this round, shuffled
  function raiseBanner(b) {
    const up = balloons.filter((o) => o.banner).map((o) => o.line)
    if (!words.length) {
      // a new round: everything, except what's still hanging from a balloon
      words = (config.banners || []).filter((w) => !up.includes(w)).sort(() => Math.random() - 0.5)
    }
    if (!words.length) return
    b.line = words.pop()
    b.banner = banner(b.line)
    placeBanner(b)
  }
  function placeBanner(b) {
    // hung under the basket; a little smaller under the far balloons
    const [x, y, w, h] = b.s.rect
    b.banner.place(scene.toScreen(b.s, x + w / 2, y + h + 1), 0.8 + 0.3 * (h / biggest))
  }
  function updateBalloon(b, t) {
    const age = t - b.poked
    // up over 3 s, hang for 2 s, sink back over 8 s
    const up = age < 3 ? easeInOut(age / 3) : age < 5 ? 1 : age < 13 ? 1 - easeInOut((age - 5) / 8) : 0
    const bob = Math.sin((t / b.period) * TAU + b.ph) * 3
    b.s.u.uOffset.value.set(Math.sin(t * 0.21 + b.ph) * 2.5 * wake, bob * wake - up * b.lift)
    b.s.u.uRotation.value = (Math.sin(t * 0.5 + b.ph) * 0.015 + up * Math.sin(t * 1.3 + b.ph) * 0.05) * wake
    if (b.banner) {
      // rolled back up as the balloon nears home
      if (age > 11) {
        b.banner.leave()
        b.banner = null
      } else placeBanner(b)
    }
  }

  // ── birds: they just drift, in slow wide circles ──────────────────────────
  const birds = ofKind('bird').map((s) => ({
    s,
    ph: rand(0, TAU),
    rx: rand(16, 28),
    ry: rand(7, 12),
    speed: TAU / rand(30, 42),
  }))
  function updateBird(b, t) {
    const a = t * b.speed + b.ph
    const ox = (Math.cos(a) - Math.cos(b.ph)) * b.rx * wake
    const oy = (Math.sin(a) - Math.sin(b.ph)) * b.ry * wake + Math.sin(t * 0.8 + b.ph) * 1.5 * wake
    b.s.u.uOffset.value.set(ox, oy)
  }

  // ── leaves (cut from a reference sheet by tools/build_leaves.py) ──────────
  // Each one swings like a pendulum as it falls: fastest mid-swing, slowing
  // and tilting up at each end. The wind carries it to the right, and the flat
  // ones flip over now and then, showing their paler back. Three distances:
  // far ones over the river and behind the trees, mid ones that land on the
  // path and fade, and a few big ones sweeping past close to the camera.
  const leaves = []
  if (config.motion.leaves) {
    const leafMaps = await scene.loadTextures(leafSet.map((l) => l.file))
    const flatOnes = leafSet.map((l, i) => i).filter((i) => leafSet[i].flat)
    const BANDS = {
      far: { n: 16, size: [22, 32], depth: [0.08, 0.2], vx: [16, 28], vy: [9, 15], swing: [10, 18],
        order: layers.trees.mesh.renderOrder - 0.5, haze: 0.1 },
      mid: { n: 8, size: [32, 44], depth: [0.28, 0.45], vx: [22, 34], vy: [14, 22], swing: [14, 24],
        order: layers.girl.mesh.renderOrder - 0.5, haze: 0.05 },
      near: { n: 3, size: [80, 110], depth: [0.82, 0.95], vx: [55, 80], vy: [30, 45], swing: [30, 50],
        order: 1000, haze: 0 },
    }
    for (const [band, b] of Object.entries(BANDS)) {
      for (let i = 0; i < b.n; i++) {
        const k = band === 'near' ? pickOne(flatOnes) : Math.floor(Math.random() * leafSet.length)
        const [tw, th] = leafSet[k].size
        const sc = rand(...b.size) / Math.max(tw, th)
        const [w, h] = [tw * sc, th * sc]
        const s = addSprite({
          name: `leaf-${band}-${i}`,
          kind: 'leaf',
          // parked in the middle of the painting; uOffset moves it
          rect: [W / 2 - w / 2, H / 2 - h / 2, w, h],
          depth: rand(...b.depth),
          map: leafMaps[k],
          opacity: 0,
          renderOrder: b.order + i * 0.001,
        })
        s.u.uHaze.value = b.haze
        leaves.push(spawn({ s, band, b, flat: leafSet[k].flat }, true))
      }
    }
  }

  function spawn(l, first) {
    const { b } = l
    const near = l.band === 'near'
    // where it would touch the pavement at its depth (far ones: the river)
    l.landY = l.band === 'mid' ? 740 + 360 * l.s.depth + rand(-8, 8) : l.band === 'far' ? rand(700, 745) : H + 90
    if (first && !near) {
      // scattered over the scene already, fading in as the scene wakes up
      l.pos = [rand(0, W), rand(40, Math.min(640, l.landY - 60))]
    } else if (Math.random() < 0.3 && !near) {
      l.pos = [rand(0, W * 0.8), -40] // from above
    } else {
      l.pos = [-60 - rand(0, near ? 700 : 220), near ? rand(0, H * 0.6) : rand(20, 560)] // from the left
    }
    l.appear = first && !near
    l.vx = rand(...b.vx)
    l.vy = rand(...b.vy)
    l.swingA = rand(...b.swing)
    l.swingW = near ? rand(0.9, 1.4) : rand(1.1, 1.8)
    l.ph = rand(0, TAU)
    l.rot0 = rand(-0.6, 0.6)
    l.spin = rand(-0.15, 0.15)
    l.turn = rand(0, TAU)
    l.turnRate = rand(0.5, 1.2)
    l.side = Math.random() < 0.7 ? 1 : -1 // -1: showing its back
    l.flipStart = -1
    l.nextFlip = now() + rand(2, 9)
    l.landed = -1
    return l
  }

  function updateLeaf(l, t, dt, w) {
    const u = l.s.u
    const go = l.band === 'near' ? 1 : wake
    let opacity = l.appear ? wake : 1

    if (l.landed >= 0) {
      // lying on the path for a few seconds, then gone
      const age = t - l.landed
      opacity *= 1 - smooth(3.5, 5.5, age)
      if (age > 5.6) spawn(l, false)
      u.uOpacity.value = opacity
      return
    }

    const phase = t * l.swingW + l.ph
    l.pos[0] += (l.vx * (0.35 + w) + l.swingA * l.swingW * Math.cos(phase)) * dt * go
    l.pos[1] += l.vy * (0.3 + 0.95 * Math.cos(phase) ** 2) * dt * go
    l.rot0 += l.spin * dt * go
    l.turn += l.turnRate * (0.5 + w) * dt * go

    // mostly a gentle rock, never close to edge-on (a flat sprite seen
    // edge-on is just a line, which looks like it vanishes). Now and then a
    // flat leaf flips over quickly, more often in gusts, and carries on
    // showing its other side
    const wobble = 0.78 + 0.22 * Math.cos(l.turn)
    let c = l.side * wobble
    if (l.flat && go > 0.5) {
      if (l.flipStart < 0 && t > l.nextFlip) l.flipStart = t
      if (l.flipStart >= 0) {
        const k = (t - l.flipStart) / 0.7
        if (k >= 1) {
          l.side = -l.side
          l.flipStart = -1
          l.nextFlip = t + rand(3, 10) / (0.6 + w)
          c = l.side * wobble
        } else c = l.side * Math.cos(easeInOut(k) * Math.PI) * wobble
      }
    }
    const sx = Math.sign(c || 1) * Math.max(Math.abs(c), 0.12)
    const sy = 0.92 + 0.08 * Math.cos(l.turn * 0.6 + l.ph)

    if (l.band === 'far') opacity *= 1 - smooth(l.landY - 30, l.landY, l.pos[1]) // into the river
    // on the left, the pavement only starts below the flower bed's curb
    const ground = l.pos[0] < 840 ? Math.max(l.landY, 1012 - 0.2175 * l.pos[0] + 8) : l.landY
    if (l.pos[1] >= (l.band === 'mid' ? ground : l.landY)) {
      if (l.band === 'mid') {
        // settle: flat on the ground, seen at a slant
        l.landed = t
        u.uScale.value.set(Math.sign(sx) * Math.max(Math.abs(sx), 0.8), 0.55)
        u.uFlip.value = Math.sign(sx)
      } else spawn(l, false)
      return
    }
    if (l.pos[0] > W + 80) spawn(l, false)

    u.uOffset.value.set(l.pos[0] - W / 2, l.pos[1] - H / 2)
    u.uRotation.value = l.rot0 + 0.55 * Math.sin(phase) * go
    u.uScale.value.set(sx, sy)
    u.uFlip.value = c
    u.uOpacity.value = opacity * (l.band === 'near' ? 0.95 : 1)
  }

  // ── lamp glow: the lanterns start dark; a click switches one on or off ─────
  const glowMap = scene.glowTexture()
  const lampSprites = ofKind('lamp')
  const heads = [
    ...lampSprites.map((s, i) => ({ at: s.head, depth: s.depth, r: [58, 38, 26][i] ?? 24, lamp: s })),
    ...manifest.farLampHeads.map((at, i) => ({ at, depth: 0.18, r: [15, 12, 10][i] ?? 9, lamp: null })),
  ]
  const glows = heads.map((g, i) => {
    const s = addSprite({
      name: `glow-${i}`,
      kind: 'glow',
      rect: [g.at[0] - g.r, g.at[1] - g.r, g.r * 2, g.r * 2],
      depth: g.depth,
      map: glowMap,
      additive: true,
      opacity: 0,
      renderOrder: 900 + i,
    })
    return { s, lamp: g.lamp, ph: rand(0, TAU), on: false, switched: -1e9, hinted: -1e9, hover: 0 }
  })
  function switchLamp(g, t) {
    g.on = !g.on
    g.switched = t
    // the far lamps across the river (too small to click) follow: on, one
    // after another, with the first lantern, and off with the last
    const anyOn = glows.some((o) => o.lamp && o.on)
    glows
      .filter((o) => !o.lamp && o.on !== anyOn)
      .forEach((o, i) => {
        o.on = anyOn
        o.switched = t + 0.6 + i * 0.35
      })
  }
  function updateGlow(g, t) {
    const flicker = 0.93 + 0.07 * Math.sin(t * 7.3 + g.ph) * Math.sin(t * 3.1 + g.ph * 2)
    const breathe = 0.85 + 0.15 * Math.sin(t * 0.6 + g.ph)
    const age = t - g.switched
    // switching on: a quick stutter, then a bright flare that settles.
    // Switching off: a quick fade
    let lit
    if (age < 0) lit = g.on ? 0 : 1 // about to follow the others
    else if (g.on) lit = age < 0.5 ? (Math.sin(age * 60) > 0 ? 1 : 0.1) : 1
    else lit = 1 - smooth(0, 0.35, age)
    const flare = g.on && age >= 0.5 && age < 4 ? 1.1 * Math.exp(-(age - 0.5) * 1.2) : 0
    // hinting that it can be clicked: the lantern swells a little, once
    const ha = t - g.hinted
    const swell = ha < 1.8 ? Math.sin((Math.PI * ha) / 1.8) : 0
    const warm = Math.max(swell, g.hover) * 0.14
    g.s.u.uOpacity.value = Math.max(0, (0.32 * breathe * flicker * lit + flare * 0.5 + warm) * wake)
  }

  // ── cats: breathe and now and then swish their tails; clicked, a wag ──────
  const cats = ofKind('cat').map((s) => {
    const [x, y, w, h] = s.rect
    s.u.uAnchor.value.set(x + w / 2, y + h - 3) // their feet
    s.u.uTail.value.set(...s.tail)
    return { s, ph: rand(0, TAU), period: rand(2.8, 3.6), poked: -1e9, phase: rand(0, TAU),
      swishAt: rand(2, 8), swishStart: -1 }
  })
  function updateCat(c, t, dt) {
    const b = Math.sin((t / c.period) * TAU + c.ph) * wake
    c.s.u.uScale.value.set(1 + 0.004 * b, 1 + 0.01 * b)

    // a slow, lazy swish every so often
    if (c.swishStart < 0 && t > c.swishAt) c.swishStart = t
    let lazy = 0
    if (c.swishStart >= 0) {
      const k = (t - c.swishStart) / 3
      lazy = Math.sin(Math.PI * clamp01(k))
      if (k >= 1) {
        c.swishStart = -1
        c.swishAt = t + rand(6, 14)
      }
    }
    // clicked: a quick excited wag that dies down over ~3 s
    const age = t - c.poked
    const wag = age < 4 ? smooth(0, 0.12, age) * Math.exp(-Math.max(0, age - 0.5) * 1.3) : 0

    // the phase runs continuously (faster when wagging), so nothing jumps
    c.phase += (2.2 + 1.5 * lazy + 11 * wag) * dt
    c.s.u.uTailAmp.value = (0.05 + 0.14 * lazy) * wake + 0.45 * wag
    c.s.u.uTailPhase.value = c.phase
  }

  // ── cues: showing what can be clicked ─────────────────────────────────────
  // With a mouse, whatever is under the pointer gets a soft rim of light. And
  // every so often (useful on touch screens, where there is no hover) one
  // thing gets a gentle sweep of light, until each kind has been clicked once.
  const CUE = { balloon: 1, cat: 0.9, lamp: 0.75 } // rim strength by kind
  const SHINE = 1.3 // seconds for a sweep
  const cues = [...balloons.map((b) => b.s), ...cats.map((c) => c.s), ...lampSprites].map((s) => ({
    s, v: 0, shineAt: -1e9, glow: glows.find((g) => g.lamp === s),
  }))
  let hovered = null
  const found = new Set() // kinds the visitor has already clicked
  let nextHint = 6
  let hintTurn = Math.floor(rand(0, 3))

  function onScreen(s) {
    const [x, y, w, h] = s.rect
    const [sx, sy] = scene.toScreen(s, x + w / 2, y + h / 2)
    const [vw, vh] = scene.viewport()
    return sx > 20 && sx < vw - 20 && sy > 20 && sy < vh - 60
  }
  function hint(t) {
    const kinds = ['balloon', 'cat', 'lamp'].filter((k) => !found.has(k))
    if (!kinds.length) return
    const kind = kinds[hintTurn++ % kinds.length]
    const pool = cues.filter((c) => c.s.kind === kind && onScreen(c.s) && c.s.u.uOpacity.value > 0.5)
    if (!pool.length) return
    const c = pickOne(pool)
    c.shineAt = t
    if (c.glow) c.glow.hinted = t
  }
  function updateCues(t, dt) {
    if (t > nextHint) {
      if (!hovered) hint(t)
      nextHint = t + rand(7, 11)
    }
    const ease = 1 - Math.exp(-dt * 9)
    for (const c of cues) {
      const k = (t - c.shineAt) / SHINE
      const shining = k >= 0 && k <= 1
      const target = c.s === hovered ? 1 : shining ? 0.45 * Math.sin(Math.PI * k) : 0
      c.v += (target - c.v) * ease
      c.s.u.uCue.value = c.v * CUE[c.s.kind] * wake
      c.s.u.uShine.value = shining ? k : -1
      if (c.glow) c.glow.hover = c.s === hovered ? c.v : 0
    }
  }

  /** The pointer is over this sprite (or null). */
  function hover(s) {
    hovered = s && cues.some((c) => c.s === s) ? s : null
  }

  // ── per frame ──────────────────────────────────────────────────────────────
  scene.onFrame.push((dt, t) => {
    wake = smooth(0.6, 4, t)
    const w = wind(t) * wake
    shared.uWind.value = w
    shared.uLife.value = wake
    for (const b of balloons) updateBalloon(b, t)
    for (const b of birds) updateBird(b, t)
    for (const l of leaves) updateLeaf(l, t, dt, w)
    for (const g of glows) updateGlow(g, t)
    for (const c of cats) updateCat(c, t, dt)
    updateCues(t, dt)
  })

  // ── reactions ──────────────────────────────────────────────────────────────
  const lines = config.reactions || {}
  let balloonTaps = 0
  function say(kind) {
    if (kind === 'balloon' && balloonTaps < (lines.balloonFirst?.length || 0)) {
      messages.say(lines.balloonFirst[balloonTaps++])
    } else if (lines[kind]?.length) messages.say(pickOne(lines[kind]))
  }

  /** React to a click / tap on a sprite (from scene.pick). */
  function poke(s) {
    const t = now()
    found.add(s.kind)
    if (s.kind === 'balloon') {
      const b = balloons.find((b) => b.s === s)
      if (t - b.poked > 13) {
        b.poked = t
        say('balloon')
        raiseBanner(b)
        const [x, y, w, h] = s.rect
        const at = scene.toScreen(s, x + w / 2, y + h / 2)
        const size = h / Math.max(...balloons.map((o) => o.s.rect[3]))
        sound?.balloon({ size, pan: (at[0] / scene.viewport()[0]) * 2 - 1 })
      }
    } else if (s.kind === 'cat') {
      const c = cats.find((c) => c.s === s)
      if (t - c.poked > 1.5) {
        c.poked = t
        const [x, y, w] = s.rect
        const at = scene.toScreen(s, x + w / 2, y)
        pop(at, '♥')
        say('cat')
        sound?.cat(s.name, { pan: (at[0] / scene.viewport()[0]) * 2 - 1 })
      }
    } else if (s.kind === 'lamp') {
      const g = glows.find((g) => g.lamp === s)
      if (g && t - g.switched > 0.6) {
        switchLamp(g, t)
        const [x, y, w] = s.rect
        const at = scene.toScreen(s, x + w / 2, y)
        sound?.lamp({ on: g.on, pan: (at[0] / scene.viewport()[0]) * 2 - 1 })
      }
    } else if (s.kind === 'girl') {
      messages.next()
    }
  }

  return { poke, hover, pickable: ['balloon', 'cat', 'lamp', 'girl'] }
}
