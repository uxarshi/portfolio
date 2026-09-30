// Clicking and tapping things in the painting. A touch only counts as a tap
// if it barely moved (otherwise it was a drag to look around).

export function createInteraction({ element, scene, life }) {
  const coarse = matchMedia('(pointer: coarse)').matches
  const radius = coarse ? 16 : 5 // screen px of forgiveness around shapes
  const at = (e) => scene.pick(e.clientX, e.clientY, life.pickable, radius)

  // hover: show that something can be clicked (pointer, and a soft rim of
  // light around it)
  let hovering = null
  const setHover = (hit) => {
    if (hit === hovering) return
    hovering = hit
    element.style.cursor = hit ? 'pointer' : ''
    life.hover(hit)
  }
  window.addEventListener('pointermove', (e) => {
    if (e.pointerType !== 'mouse') return
    setHover(e.target === element || element.contains(e.target) ? at(e) : null)
  })
  document.documentElement.addEventListener('pointerleave', () => setHover(null))

  let down = null
  element.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return
    down = { id: e.pointerId, x: e.clientX, y: e.clientY, t: performance.now() }
  })
  window.addEventListener('pointerup', (e) => {
    if (!down || e.pointerId !== down.id) return
    const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y)
    const quick = performance.now() - down.t < 600
    down = null
    if (moved > (coarse ? 12 : 6) || !quick) return
    const hit = at(e)
    if (hit) life.poke(hit)
  })
  window.addEventListener('pointercancel', () => (down = null))
}
