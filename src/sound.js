// Ambient sound: birdsong and a faint breeze, made on the fly with the Web
// Audio API (no audio files to download). Off until the visitor turns it on
// (browsers only allow sound after a click or tap anyway); the choice is
// remembered, and if it was on, it comes back with the first click or key.
//
// The air is filtered noise: a very quiet breeze that now and then swells and
// fades. The birds
// are whistled sine tones swept in pitch, a few kinds with their own songs,
// each at its own distance and side, with a little echo of open air.
//
// The cats answer when clicked: a meow (a buzzy voice through a mouth that
// opens "mm-eee" and closes "-ow"). A balloon, poked, gives a soft rubbery
// "dub"; a lamp, the click of its switch and the buzz of the bulb catching.

const KEY = 'sound'
const rand = (a, b) => a + Math.random() * (b - a)
const randInt = (a, b) => Math.floor(rand(a, b + 1))
const pickOne = (list) => list[Math.floor(Math.random() * list.length)]

function remembered() {
  try {
    return localStorage.getItem(KEY) === 'on'
  } catch {
    return false
  }
}
function remember(on) {
  try {
    localStorage.setItem(KEY, on ? 'on' : 'off')
  } catch {}
}

export function createSound(config) {
  const volume = config.sound?.volume ?? 0.8
  const AC = window.AudioContext || window.webkitAudioContext
  let ctx = null
  let master, verb, breeze, breezeFilter
  let birds = []
  let nextGust = 0
  let timer = 0
  let on = false
  let running = false // on, and actually playing (after a click or tap)
  let stopping = 0
  const listeners = []

  // ── building blocks ────────────────────────────────────────────────────────

  /** Seamlessly looping stereo pink noise. */
  function noiseBuffer(seconds) {
    const n = Math.floor(seconds * ctx.sampleRate)
    const fade = Math.floor(0.5 * ctx.sampleRate)
    const buf = ctx.createBuffer(2, n, ctx.sampleRate)
    for (let ch = 0; ch < 2; ch++) {
      const a = new Float32Array(n + fade)
      let b0 = 0, b1 = 0, b2 = 0
      for (let i = 0; i < a.length; i++) {
        const w = Math.random() * 2 - 1
        b0 = 0.99765 * b0 + w * 0.099046
        b1 = 0.963 * b1 + w * 0.2965164
        b2 = 0.57 * b2 + w * 1.0526913
        a[i] = (b0 + b1 + b2 + w * 0.1848) * 0.16
      }
      // cross-fade the tail into the head so the loop has no seam
      const out = buf.getChannelData(ch)
      for (let i = 0; i < n; i++) {
        if (i < fade) {
          const k = i / fade
          out[i] = a[i] * Math.sqrt(k) + a[n + i] * Math.sqrt(1 - k)
        } else out[i] = a[i]
      }
    }
    return buf
  }

  /** A soft room of open air: decaying stereo noise, darker as it fades. */
  function impulse(seconds) {
    const n = Math.floor(seconds * ctx.sampleRate)
    const buf = ctx.createBuffer(2, n, ctx.sampleRate)
    for (let ch = 0; ch < 2; ch++) {
      const d = buf.getChannelData(ch)
      let lp = 0
      for (let i = 0; i < n; i++) {
        const t = i / n
        lp += (Math.random() * 2 - 1 - lp) * (0.9 - 0.75 * t)
        d[i] = lp * Math.pow(1 - t, 3) * (i < 200 ? i / 200 : 1)
      }
    }
    return buf
  }

  /** A slow wobble added to an audio parameter. */
  function lfo(rate, depth, param) {
    const o = ctx.createOscillator()
    o.frequency.value = rate
    const g = ctx.createGain()
    g.gain.value = depth
    o.connect(g).connect(param)
    o.start()
  }

  function loop(buffer, rate = 1, offset = 0) {
    const s = ctx.createBufferSource()
    s.buffer = buffer
    s.loop = true
    s.playbackRate.value = rate
    s.start(ctx.currentTime, offset)
    return s
  }

  // soft attack, fuller middle, gentle release
  const ENVELOPE = Float32Array.from({ length: 48 }, (_, i) => {
    const x = i / 47
    return Math.pow(Math.sin(Math.PI * Math.pow(x, 0.7)), 0.9)
  })
  let whistle = null // a sine with a hint of overtone, like a real bird's

  /**
   * One whistled note. `sweep` is a list of [time 0..1, Hz] the pitch passes
   * through; `vib` a quick warble in Hz at `vibRate`.
   */
  function tone(dest, t, dur, sweep, amp, { vib = 0, vibRate = 0, wave = whistle } = {}) {
    const o = ctx.createOscillator()
    if (wave) o.setPeriodicWave(wave)
    const f = o.frequency
    f.setValueAtTime(sweep[0][1], t)
    for (const [k, hz] of sweep.slice(1)) f.exponentialRampToValueAtTime(hz, t + k * dur)
    const g = ctx.createGain()
    g.gain.value = 0
    g.gain.setValueCurveAtTime(ENVELOPE.map((v) => v * amp), t, dur)
    o.connect(g).connect(dest)
    if (vib) {
      const v = ctx.createOscillator()
      v.frequency.value = vibRate
      const vg = ctx.createGain()
      vg.gain.value = vib
      v.connect(vg).connect(f)
      v.start(t)
      v.stop(t + dur + 0.05)
    }
    o.start(t)
    o.stop(t + dur + 0.05)
  }

  // ── the river ──────────────────────────────────────────────────────────────

  function river() {
    // a very quiet breeze: soft, dark air that now and then swells and fades
    // away again (kept low and rounded so it never sounds like rushing water)
    breezeFilter = ctx.createBiquadFilter()
    breezeFilter.type = 'bandpass'
    breezeFilter.frequency.value = 450
    breezeFilter.Q.value = 0.5
    const soft = ctx.createBiquadFilter()
    soft.type = 'lowpass'
    soft.frequency.value = 900
    breeze = ctx.createGain()
    breeze.gain.value = 0
    loop(noiseBuffer(13), 0.8, 2.1).connect(breezeFilter).connect(soft).connect(breeze)
    breeze.connect(master)
    breeze.connect(verb)
  }

  function scheduleWater(until) {
    while (nextGust < until) {
      // one breath of air: rises slowly, hangs a moment, drifts away
      const t = nextGust
      const len = rand(7, 12)
      breezeFilter.frequency.setTargetAtTime(rand(350, 700), t, 1)
      breeze.gain.setTargetAtTime(rand(0.02, 0.036), t, len * 0.3)
      breeze.gain.setTargetAtTime(0, t + len * 0.55, len * 0.3)
      nextGust = t + len + rand(2.5, 6)
    }
  }

  // ── the birds ──────────────────────────────────────────────────────────────
  // Each kind has its song: a few notes it sings, with small variations, and
  // how long it waits between songs. `p` shifts one bird's pitch a little, so
  // two of a kind never sound identical.

  const SONGS = {
    // short bright chirps, a busy little bird on a branch
    sparrow(b, out, t) {
      const n = randInt(3, 6)
      let at = t
      for (let i = 0; i < n; i++) {
        const f = b.p * rand(0.95, 1.05)
        tone(out, at, rand(0.05, 0.075), [[0, 3600 * f], [0.4, 5400 * f], [1, 4100 * f]], 0.9)
        at += rand(0.1, 0.16)
      }
      return at - t
    },
    // a sweet caroling phrase, notes chosen from its own little melody
    robin(b, out, t) {
      b.motif ??= Array.from({ length: 6 }, () => ({
        f: rand(2300, 3600) * b.p, glide: rand(-0.22, 0.2), dur: rand(0.13, 0.26),
      }))
      const start = randInt(0, 2)
      const n = randInt(3, 5)
      let at = t
      for (let i = 0; i < n; i++) {
        const m = b.motif[(start + i) % b.motif.length]
        const f = m.f * rand(0.98, 1.02)
        tone(out, at, m.dur, [[0, f], [0.35, f * (1 + m.glide * 0.4)], [1, f * (1 + m.glide)]], 0.75,
          { vib: rand(30, 70), vibRate: rand(14, 22) })
        at += m.dur + rand(0.06, 0.11)
      }
      return at - t
    },
    // two whistled notes, then a fast silvery trill that falls away
    warbler(b, out, t) {
      let at = t
      tone(out, at, 0.12, [[0, 4300 * b.p], [1, 4500 * b.p]], 0.6)
      at += 0.18
      tone(out, at, 0.12, [[0, 3700 * b.p], [1, 3500 * b.p]], 0.6)
      at += 0.2
      const n = randInt(8, 13)
      for (let i = 0; i < n; i++) {
        const k = b.p * (1 - 0.14 * (i / n))
        tone(out, at, 0.035, [[0, 6200 * k], [1, 4400 * k]], 0.55 * (1 - 0.4 * (i / n)))
        at += 0.052
      }
      return at - t
    },
    // "tea-cher, tea-cher, tea-cher"
    tit(b, out, t) {
      const n = randInt(2, 4)
      let at = t
      for (let i = 0; i < n; i++) {
        tone(out, at, 0.09, [[0, 5200 * b.p], [1, 4900 * b.p]], 0.5)
        tone(out, at + 0.13, 0.1, [[0, 3900 * b.p], [1, 3600 * b.p]], 0.5)
        at += 0.36
      }
      return at - t
    },
    // a dove somewhere far off: "hoo, hoo-hooo, hoo"
    dove(b, out, t) {
      const f = 520 * b.p
      const notes = [[0.3, 0.97], [0.22, 1.04], [0.62, 1], [0.34, 0.95]]
      let at = t
      for (const [dur, k] of notes) {
        tone(out, at, dur, [[0, f * k * 0.96], [0.3, f * k], [1, f * k * 0.93]], 1.4, { wave: null })
        at += dur + 0.12
      }
      return at - t
    },
  }

  // who is in the trees: where they sit (pan -1 left .. 1 right), how far
  // (0 near .. 1 far) and how long they rest between songs
  const CAST = [
    { kind: 'robin', pan: -0.55, far: 0.35, rest: [3.5, 9], p: 1 },
    { kind: 'sparrow', pan: 0.6, far: 0.4, rest: [6, 14], p: 1.02 },
    { kind: 'warbler', pan: -0.15, far: 0.75, rest: [9, 18], p: 0.97 },
    { kind: 'tit', pan: 0.35, far: 0.65, rest: [11, 22], p: 1 },
    { kind: 'robin', pan: 0.8, far: 0.85, rest: [8, 16], p: 1.12 },
    { kind: 'dove', pan: -0.8, far: 1, rest: [22, 40], p: 1 },
  ]

  function makeBirds() {
    return CAST.map((c) => {
      // farther birds are quieter, duller and more echoey
      const gain = ctx.createGain()
      gain.gain.value = 0.15 * (1 - 0.65 * c.far)
      const dull = ctx.createBiquadFilter()
      dull.type = 'lowpass'
      dull.frequency.value = 9000 - 5500 * c.far
      const pan = ctx.createStereoPanner()
      pan.pan.value = c.pan
      const send = ctx.createGain()
      send.gain.value = 0.25 + 0.5 * c.far
      gain.connect(dull).connect(pan)
      pan.connect(master)
      pan.connect(send).connect(verb)
      return { ...c, out: gain, next: 0 }
    })
  }

  function scheduleBirds(until) {
    for (const b of birds) {
      while (b.next < until) {
        const len = SONGS[b.kind](b, b.out, b.next)
        // songbirds often sing a few songs in a row, then pause longer
        const bout = b.kind !== 'dove' && Math.random() < 0.35
        b.next += len + (bout ? rand(1.2, 3) : rand(...b.rest))
      }
    }
  }

  // ── the cats ───────────────────────────────────────────────────────────────
  // Each has its own voice: how high it meows

  const VOICES = {
    'cat-white': { f: 640 },
    'cat-orange': { f: 520 },
    'cat-grey': { f: 720 },
  }

  /** Where the sound comes from: stereo pan, and a touch of echo. */
  function outAt(pan) {
    const p = ctx.createStereoPanner()
    p.pan.value = Math.max(-0.8, Math.min(0.8, pan))
    const send = ctx.createGain()
    send.gain.value = 0.18
    p.connect(master)
    p.connect(send).connect(verb)
    return p
  }

  function meow(v, out, t) {
    const dur = rand(0.55, 0.85)
    const f = v.f * rand(0.92, 1.08)
    // the voice: a buzzy tone that rises, holds, and falls away at the end
    const o = ctx.createOscillator()
    o.type = 'sawtooth'
    o.frequency.setValueAtTime(f * 0.82, t)
    o.frequency.exponentialRampToValueAtTime(f * 1.14, t + dur * 0.2)
    o.frequency.exponentialRampToValueAtTime(f * 1.2, t + dur * 0.45)
    o.frequency.exponentialRampToValueAtTime(f * 0.7, t + dur)
    const vib = ctx.createOscillator()
    vib.frequency.value = rand(5, 7)
    const vg = ctx.createGain()
    vg.gain.value = f * 0.015
    vib.connect(vg).connect(o.frequency)

    // the mouth: formants moving from "mm" through "ee" to "ow"
    const mouth = ctx.createGain()
    const shape = [
      // [start Hz, open Hz ("ee"), end Hz ("ow"), level]
      [420, 900, 640, 1],
      [1250, 1900, 1050, 0.55],
      [2800, 3100, 2600, 0.2],
    ]
    for (const [a, b, c, level] of shape) {
      const bp = ctx.createBiquadFilter()
      bp.type = 'bandpass'
      bp.Q.value = 7
      bp.frequency.setValueAtTime(a, t)
      bp.frequency.linearRampToValueAtTime(b, t + dur * 0.35)
      bp.frequency.linearRampToValueAtTime(c, t + dur)
      const g = ctx.createGain()
      g.gain.value = level
      o.connect(bp).connect(g).connect(mouth)
    }
    // lips: closed at first ("m"), open wide, rounding at the end
    const lips = ctx.createBiquadFilter()
    lips.type = 'lowpass'
    lips.frequency.setValueAtTime(700, t)
    lips.frequency.exponentialRampToValueAtTime(4200, t + dur * 0.25)
    lips.frequency.exponentialRampToValueAtTime(1500, t + dur)

    const env = ctx.createGain()
    env.gain.value = 0
    const k = 0.55
    env.gain.setValueCurveAtTime(ENVELOPE.map((e, i) => e * k * (i < 24 ? 1 : 1 - 0.3 * ((i - 24) / 23))), t, dur)
    mouth.connect(lips).connect(env).connect(out)

    o.start(t)
    vib.start(t)
    o.stop(t + dur + 0.05)
    vib.stop(t + dur + 0.05)
    return dur
  }

  /**
   * A cat was clicked: it meows, from `pan` (-1 left .. 1 right). Only while
   * the sound is on.
   */
  function cat(name, { pan = 0 } = {}) {
    if (!running || !ctx) return
    const v = VOICES[name] ?? VOICES['cat-white']
    const out = outAt(pan)
    const t = ctx.currentTime + 0.03
    const len = meow(v, out, t)
    // now and then a second, shorter one
    if (Math.random() < 0.25) meow({ f: v.f * 1.08 }, out, t + len + rand(0.15, 0.3))
  }

  // ── the balloons ───────────────────────────────────────────────────────────
  // A soft rubbery "dub": a low tone that drops quickly in pitch, a brighter
  // overtone that dies away first, and the muffled tap of a fingertip.
  // Smaller (farther) balloons sound a little higher and quieter.

  /**
   * A balloon was clicked, from `pan` (-1 left .. 1 right); `size` 0 (tiny)
   * .. 1 (the biggest). Only while the sound is on.
   */
  function balloon({ pan = 0, size = 1 } = {}) {
    if (!running || !ctx) return
    const out = outAt(pan)
    const t = ctx.currentTime + 0.02
    const f = 170 * (1.6 - 0.6 * size) * rand(0.95, 1.05)
    const amp = 0.35 + 0.35 * size
    for (const [k, level, len] of [[1, 1, 0.34], [2.4, 0.3, 0.12]]) {
      const o = ctx.createOscillator()
      o.frequency.setValueAtTime(f * k * 1.8, t)
      o.frequency.exponentialRampToValueAtTime(f * k, t + 0.05)
      o.frequency.exponentialRampToValueAtTime(f * k * 0.8, t + len)
      const g = ctx.createGain()
      g.gain.setValueAtTime(0, t)
      g.gain.linearRampToValueAtTime(amp * level, t + 0.008)
      g.gain.exponentialRampToValueAtTime(0.001, t + len)
      o.connect(g).connect(out)
      o.start(t)
      o.stop(t + len + 0.05)
    }
    snap(out, t, 'lowpass', 900, amp * 0.5)
  }

  const bursts = {}
  /** A short tick of noise through a filter, for taps and clicks. */
  function snap(out, t, type, hz, level, seconds = 0.04) {
    const n = Math.floor(seconds * ctx.sampleRate)
    if (!bursts[n]) {
      bursts[n] = ctx.createBuffer(1, n, ctx.sampleRate)
      const d = bursts[n].getChannelData(0)
      for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n) ** 3
    }
    const s = ctx.createBufferSource()
    s.buffer = bursts[n]
    const f = ctx.createBiquadFilter()
    f.type = type
    f.frequency.value = hz
    f.Q.value = type === 'bandpass' ? 1.5 : 0.7
    const g = ctx.createGain()
    g.gain.value = level
    s.connect(f).connect(g).connect(out)
    s.start(t)
  }

  // ── the lamps ──────────────────────────────────────────────────────────────
  // The click of a switch (press, then a lighter release). Switched on, the
  // bulb catches with a mains buzz that stutters in time with its flicker
  // (the first 0.5 s, see life.js), then settles into a faint hum that fades.

  /** A lamp was clicked, now `on` or off, from `pan`. Only while the sound is on. */
  function lamp({ on = true, pan = 0 } = {}) {
    if (!running || !ctx) return
    const out = outAt(pan)
    const t = ctx.currentTime + 0.02
    snap(out, t, 'bandpass', on ? 2600 : 2100, 0.7, 0.012)
    snap(out, t + 0.035, 'bandpass', on ? 3200 : 2500, 0.3, 0.01)
    if (!on) return

    const o = ctx.createOscillator()
    o.type = 'sawtooth'
    o.frequency.value = 100
    const warm = ctx.createBiquadFilter()
    warm.type = 'lowpass'
    warm.frequency.value = 1400
    const g = ctx.createGain()
    g.gain.value = 0
    const period = (2 * Math.PI) / 60 // the flicker's rhythm
    for (let a = t + 0.03; a < t + 0.5; a += period) {
      g.gain.setTargetAtTime(0.09, a, 0.004)
      g.gain.setTargetAtTime(0.01, a + period / 2, 0.004)
    }
    g.gain.setTargetAtTime(0.05, t + 0.5, 0.02)
    g.gain.setTargetAtTime(0, t + 0.8, 0.5)
    o.connect(warm).connect(g).connect(out)
    o.start(t)
    o.stop(t + 3.5)
  }

  // ── running ────────────────────────────────────────────────────────────────

  function build() {
    ctx = new AC()
    whistle = ctx.createPeriodicWave(new Float32Array([0, 0, 0, 0]), new Float32Array([0, 1, 0.1, 0.03]))
    master = ctx.createGain()
    master.gain.value = 0
    // keeps the odd loud moment in check
    const calm = ctx.createDynamicsCompressor()
    calm.threshold.value = -20
    calm.ratio.value = 3
    calm.attack.value = 0.01
    calm.release.value = 0.3
    master.connect(calm).connect(ctx.destination)
    verb = ctx.createConvolver()
    verb.buffer = impulse(2.6)
    const wet = ctx.createGain()
    wet.gain.value = 0.3
    verb.connect(wet).connect(master)
    river()
    birds = makeBirds()
  }

  function tick() {
    const until = ctx.currentTime + 0.8
    scheduleWater(until)
    scheduleBirds(until)
  }

  async function start() {
    if (!AC) return
    running = true
    clearTimeout(stopping)
    if (!ctx) build()
    await ctx.resume()
    const t = ctx.currentTime
    // the first birds a few seconds in, not all at once
    nextGust = Math.max(nextGust, t + 0.5)
    birds.forEach((b, i) => (b.next = Math.max(b.next, t + (i === 0 ? rand(1, 2.5) : rand(2, 12)))))
    master.gain.cancelScheduledValues(t)
    master.gain.setValueAtTime(master.gain.value, t)
    master.gain.linearRampToValueAtTime(volume, t + 2.5)
    clearInterval(timer)
    timer = setInterval(tick, 250)
    tick()
  }

  function stop() {
    running = false
    if (!ctx) return
    const t = ctx.currentTime
    master.gain.cancelScheduledValues(t)
    master.gain.setValueAtTime(master.gain.value, t)
    master.gain.linearRampToValueAtTime(0, t + 0.8)
    clearInterval(timer)
    stopping = setTimeout(() => ctx.suspend(), 900)
  }

  function set(value) {
    on = value
    remember(on)
    on ? start() : stop()
    for (const fn of listeners) fn(on)
  }

  // pause while the tab is hidden
  document.addEventListener('visibilitychange', () => {
    if (!ctx || !on) return
    if (document.hidden) {
      clearInterval(timer)
      ctx.suspend()
    } else if (running) start()
  })

  // it was on last time: come back with the first click, tap or key
  if (AC && remembered()) {
    on = true
    const wake = (e) => {
      if (e.target.closest?.('#sound')) return // the button itself handles it
      window.removeEventListener('pointerdown', wake, true)
      window.removeEventListener('keydown', wake, true)
      if (on) start()
    }
    window.addEventListener('pointerdown', wake, true)
    window.addEventListener('keydown', wake, true)
  }

  return {
    available: !!AC,
    get on() {
      return on
    },
    // on but still waiting for a click to be allowed to play: that click starts it
    toggle: () => (on && !running ? start() : set(!on)),
    /** Called with true / false whenever it is switched. */
    onChange: (fn) => listeners.push(fn),
    cat,
    balloon,
    lamp,
  }
}
