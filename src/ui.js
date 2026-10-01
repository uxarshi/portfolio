// DOM bits: thought-bubble messages, footer links, the iOS tilt chip, and
// placing the still image + bubble from the shared layout.

import { bubbleRect } from './layout.js'

const ICONS = {
  email:
    '<rect x="3" y="5.5" width="18" height="13" rx="3"/><path d="m4.5 7.5 7.5 5.5 7.5-5.5"/>',
  instagram:
    '<rect x="3.5" y="3.5" width="17" height="17" rx="5"/><circle cx="12" cy="12" r="3.8"/><circle cx="17.1" cy="6.9" r="1" fill="currentColor" stroke="none"/>',
  linkedin:
    '<rect x="3.5" y="3.5" width="17" height="17" rx="3.5"/><path d="M8.2 10.6V16M8.2 7.9v.1M11.6 16v-5.4M11.6 13.2c0-1.7 1-2.7 2.3-2.7s2.1.9 2.1 2.7V16"/>',
  behance:
    '<path d="M3.5 7.2h4a2.2 2.2 0 0 1 0 4.4h-4zM3.5 11.6h4.6a2.6 2.6 0 0 1 0 5.2H3.5zM14.2 13.8h6.1a3 3 0 1 0-1 2.5M14.8 8h4.5"/>',
  dribbble:
    '<circle cx="12" cy="12" r="8.5"/><path d="M6 6.3c3.6 3.2 9 8.4 11 13M3.6 11c4.8.5 10-.7 13.9-4.9M9.2 3.9c2.6 3.4 5 9.3 5.6 15.9"/>',
}

const LABELS = { email: 'Email', instagram: 'Instagram', linkedin: 'LinkedIn', behance: 'Behance', dribbble: 'Dribbble' }

function svg(paths) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`
}

export function buildFooter(config) {
  const nav = document.getElementById('footer-links')
  nav.innerHTML = ''
  for (const [key, value] of Object.entries(config.links)) {
    if (!value) continue
    let kind = key
    if (key === 'behance' && /dribbble/i.test(value)) kind = 'dribbble'
    if (!ICONS[kind]) continue
    const a = document.createElement('a')
    a.href = kind === 'email' ? `mailto:${value.replace(/^mailto:/, '')}` : value
    if (kind !== 'email') {
      a.target = '_blank'
      a.rel = 'noopener me'
    }
    a.setAttribute('aria-label', kind === 'email' ? `Email ${config.name}` : `${config.name} on ${LABELS[kind]}`)
    a.title = LABELS[kind]
    a.innerHTML = svg(ICONS[kind])
    nav.appendChild(a)
  }
}

/** Cycles the thought-bubble lines with a soft cross-fade. */
export function createMessages(config, { interactive }) {
  const el = document.getElementById('bubble-text')
  let lines = config.messages.map((s) => s.replaceAll('{name}', config.name))
  // "that balloon looks clickable" makes no sense on the still (reduced-motion)
  // version, and on phones it's a tap
  const TAP = { click: 'tap', clicking: 'tapping', clickable: 'tappable' }
  if (!interactive) lines = lines.filter((s) => !/click/i.test(s))
  else if (matchMedia('(pointer: coarse)').matches)
    lines = lines.map((s) => s.replace(/\bclick(ing|able)?\b/gi, (w) => TAP[w.toLowerCase()]))
  const bubble = document.getElementById('bubble')
  let i = 0
  let timer = 0
  let current = ''

  // Long lines get a smaller type size so they always fit inside the cloud
  function setText(text) {
    current = text
    el.textContent = text
    el.style.fontSize = ''
    bubble.classList.toggle('roomy', text.length > 60)
    let size = parseFloat(getComputedStyle(el).fontSize)
    for (let n = 0; n < 20 && (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1); n++) {
      size *= 0.94
      el.style.fontSize = `${size}px`
    }
  }
  if (import.meta.env.DEV) i = Math.max(0, Math.min(lines.length - 1, +new URLSearchParams(location.search).get('msg') || 0))
  setText(lines[i])
  addEventListener('resize', () => setText(current))

  let swap = 0
  function show(next, text) {
    if (text === undefined) i = (next + lines.length) % lines.length
    el.classList.add('out')
    clearTimeout(swap)
    swap = setTimeout(() => {
      setText(text ?? lines[i])
      el.classList.remove('out')
    }, 450)
  }
  function schedule() {
    clearTimeout(timer)
    const last = i === lines.length - 1
    const secs = last ? (config.lastMessageSeconds ?? config.messageSeconds) : config.messageSeconds
    timer = setTimeout(() => {
      show(i + 1)
      schedule()
    }, secs * 1000)
  }
  schedule()

  return {
    next() {
      show(i + 1)
      schedule()
    },
    /** A one-off line (a reaction); the usual lines carry on after it. */
    say(text) {
      show(i, text)
      schedule()
    },
  }
}

const SOUND_ICONS = {
  on: '<path d="M4.5 9.5h3l4-3.5v12l-4-3.5h-3z"/><path d="M15 9.2a4 4 0 0 1 0 5.6M17.6 6.8a7.4 7.4 0 0 1 0 10.4"/>',
  off: '<path d="M4.5 9.5h3l4-3.5v12l-4-3.5h-3z"/><path d="m15.5 9.8 4.4 4.4M19.9 9.8l-4.4 4.4"/>',
}

/** The sound button, top right: birdsong, the river and the cats, on or off. */
export function setupSoundButton(sound) {
  if (!sound.available) return
  const b = document.createElement('button')
  b.id = 'sound'
  b.type = 'button'
  b.className = 'sound-toggle'
  const show = (on) => {
    b.innerHTML = `${svg(SOUND_ICONS[on ? 'on' : 'off'])}<span>Sound ${on ? 'on' : 'off'}</span>`
    b.setAttribute('aria-pressed', on)
    b.setAttribute('aria-label', 'Sound: birdsong, the river and the cats')
    b.title = on ? 'Turn the sound off' : 'Turn the sound on'
  }
  show(sound.on)
  sound.onChange(show)
  b.addEventListener('click', () => sound.toggle())
  document.body.appendChild(b)
}

/** A little symbol that floats up from a point and fades (e.g. a heart). */
export function pop([x, y], text) {
  const el = document.createElement('span')
  el.className = 'pop'
  el.textContent = text
  el.setAttribute('aria-hidden', 'true')
  el.style.left = `${x}px`
  el.style.top = `${y}px`
  document.getElementById('stage').appendChild(el)
  el.addEventListener('animationend', () => el.remove())
}

/** Splits a line in two at the space that best balances the halves. */
function twoLines(text) {
  const words = text.split(' ')
  let best = [text]
  let diff = Infinity
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ')
    const b = words.slice(i).join(' ')
    if (Math.abs(a.length - b.length) < diff) {
      diff = Math.abs(a.length - b.length)
      best = [a, b]
    }
  }
  return best
}

/**
 * A little cloth banner that unrolls on two strings under a balloon, sways,
 * and rolls back up. `place` puts it where the strings meet (screen px) at a
 * `scale`; `leave` rolls it up and removes it.
 */
export function banner(text) {
  const el = document.createElement('div')
  el.className = 'banner'
  el.setAttribute('aria-hidden', 'true')
  el.innerHTML =
    '<div class="banner-sway">' +
    '<svg class="banner-strings" viewBox="0 0 100 10" preserveAspectRatio="none"><path d="M50 0 8 10M50 0 92 10"/></svg>' +
    '<div class="banner-cloth"><span class="banner-ribbon"></span></div></div>'
  el.querySelector('.banner-ribbon').textContent = twoLines(text).join('\n')
  el.firstChild.style.animationDelay = `${-Math.random() * 5}s` // each sways in its own time
  document.getElementById('stage').appendChild(el)
  return {
    place([x, y], scale) {
      el.style.transform = `translate(${x}px, ${y}px) scale(${scale})`
    },
    leave() {
      el.classList.add('leaving')
      setTimeout(() => el.remove(), 1000)
    },
  }
}

/** Places the still image and the enlarged bubble for the current layout. */
export function placeDom(L) {
  const still = document.getElementById('still')
  still.classList.add('placed')
  still.style.width = `${L.w}px`
  still.style.height = `${L.h}px`
  still.style.transform = `translate(${L.x}px, ${L.y}px)`

  const b = bubbleRect(L)
  const bubble = document.getElementById('bubble')
  bubble.style.width = `${b.width}px`
  // `translate` (not `transform`) so the roomy `scale` grows the cloud in place
  bubble.style.translate = `${b.left}px ${b.top}px`
  bubble.style.setProperty('--bubble-w', `${b.width}px`)
  bubble.classList.add('placed')
}

/** iOS only: a small chip, and the first tap anywhere asks for tilt access. */
export function setupTiltChip(request) {
  const chip = document.getElementById('tilt-hint')
  chip.hidden = false
  let asked = false
  const ask = async () => {
    if (asked) return
    asked = true
    chip.hidden = true
    window.removeEventListener('touchend', ask)
    await request()
  }
  chip.addEventListener('click', ask)
  window.addEventListener('touchend', ask, { passive: true })
  // fade the hint away on its own after a while
  setTimeout(() => (chip.hidden = true), 9000)
}
