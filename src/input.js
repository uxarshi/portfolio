// Turns mouse, touch-drag and phone tilt into one smooth "camera offset"
// (x right, y up, both -1..1). When nobody is interacting, a slow drift keeps
// the scene breathing.

const clamp = (v, a = -1, b = 1) => Math.min(b, Math.max(a, v))

export function createInput({ element, config, onTiltAvailable }) {
  const m = config.motion
  const target = { x: 0, y: 0 }
  const current = { x: 0, y: 0 }
  let lastActive = -1e9 // seconds, time of last real input
  let idleMix = 1 // 1 = idle drift fully on
  let source = 'none' // 'mouse' | 'drag' | 'tilt'

  const now = () => performance.now() / 1000

  // ── mouse (desktop) ────────────────────────────────────────────────────────
  window.addEventListener('pointermove', (e) => {
    if (e.pointerType !== 'mouse') return
    target.x = clamp((e.clientX / window.innerWidth) * 2 - 1)
    target.y = clamp(-((e.clientY / window.innerHeight) * 2 - 1))
    source = 'mouse'
    lastActive = now()
  })
  document.documentElement.addEventListener('mouseleave', () => {
    if (source !== 'mouse') return
    target.x = target.y = 0
    source = 'none'
  })

  // ── touch drag (phones without tilt, or before tilt is allowed) ────────────
  let drag = null
  element.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse') return
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY, ox: target.x, oy: target.y }
  })
  window.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return
    const range = Math.min(window.innerWidth, window.innerHeight) * 0.45
    // dragging the painting right shows more of its left side
    target.x = clamp(drag.ox - (e.clientX - drag.x) / range)
    target.y = clamp(drag.oy + (e.clientY - drag.y) / range)
    source = 'drag'
    lastActive = now()
  })
  const endDrag = (e) => {
    if (!drag || e.pointerId !== drag.id) return
    drag = null
    if (source === 'drag') {
      target.x = target.y = 0 // ease back to rest
      source = 'none'
    }
  }
  window.addEventListener('pointerup', endDrag)
  window.addEventListener('pointercancel', endDrag)

  // ── device tilt ───────────────────────────────────────────────────────────
  let base = null
  function onOrient(e) {
    if (e.gamma == null || e.beta == null) return
    const angle = (screen.orientation && screen.orientation.angle) || window.orientation || 0
    let x = e.gamma
    let y = e.beta
    if (angle === 90) [x, y] = [e.beta, -e.gamma]
    else if (angle === -90 || angle === 270) [x, y] = [-e.beta, e.gamma]
    if (!base) base = { x, y }
    // let the resting angle follow slowly, so holding the phone differently
    // doesn't lock the view to one side
    base.x += (x - base.x) * 0.004
    base.y += (y - base.y) * 0.004
    if (drag) return
    target.x = clamp((x - base.x) / m.tiltRange)
    target.y = clamp((y - base.y) / m.tiltRange)
    source = 'tilt'
    lastActive = now()
  }

  const needsPermission =
    typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function'
  const isTouch = matchMedia('(pointer: coarse)').matches

  if (!needsPermission) {
    window.addEventListener('deviceorientation', onOrient)
  } else if (isTouch) {
    // iOS: the permission prompt may only be opened from a tap
    onTiltAvailable?.(async () => {
      try {
        const res = await DeviceOrientationEvent.requestPermission()
        if (res === 'granted') window.addEventListener('deviceorientation', onOrient)
        return res === 'granted'
      } catch {
        return false
      }
    })
  }

  // dev only: ?cam=x,y pins the camera offset, for checking the extremes
  const pinned = import.meta.env.DEV && new URLSearchParams(location.search).get('cam')?.split(',').map(Number)

  // ── per-frame update ──────────────────────────────────────────────────────
  function update(dt, t) {
    if (pinned) return { x: pinned[0] || 0, y: pinned[1] || 0 }
    const idle = t - lastActive > 2.5 && !drag
    idleMix += ((idle ? 1 : 0) - idleMix) * (1 - Math.exp(-dt * 0.8))

    const drift = m.idleDrift
    const ix = Math.sin(t * 0.21) * 0.8 * drift + Math.sin(t * 0.083 + 1.3) * 0.4 * drift
    const iy = Math.sin(t * 0.17 + 0.6) * 0.5 * drift

    const tx = target.x * (1 - idleMix) + ix * idleMix
    const ty = target.y * (1 - idleMix) + iy * idleMix

    const k = 1 - Math.exp(-dt * (source === 'tilt' ? 4 : 2.6))
    current.x += (tx - current.x) * k
    current.y += (ty - current.y) * k
    return current
  }

  return { update }
}
