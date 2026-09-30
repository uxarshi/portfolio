import './style.css'
import config from './config.js'
import { computeLayout } from './layout.js'
import { createSound } from './sound.js'
import { banner, buildFooter, createMessages, placeDom, pop, setupSoundButton, setupTiltChip } from './ui.js'

const stage = document.getElementById('stage')
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches

function hasWebGL() {
  try {
    const c = document.createElement('canvas')
    return !!c.getContext('webgl2')
  } catch {
    return false
  }
}

const animated = !reducedMotion && hasWebGL()

buildFooter(config)
const sound = config.sound?.enabled !== false ? createSound(config) : null
if (sound) setupSoundButton(sound)
const messages = createMessages(config, { interactive: animated })

let layout = computeLayout(window.innerWidth, window.innerHeight)
placeDom(layout)

let scene = null
function relayout() {
  layout = computeLayout(window.innerWidth, window.innerHeight)
  placeDom(layout)
  scene?.setLayout(layout)
}
window.addEventListener('resize', relayout)
window.visualViewport?.addEventListener('resize', relayout)

async function startScene() {
  // three.js is split into its own chunk, so the still painting and message
  // appear before any of it downloads.
  const [{ createScene }, { createInput }, { createLife }, { createInteraction }] = await Promise.all([
    import('./scene.js'),
    import('./input.js'),
    import('./life.js'),
    import('./interact.js'),
  ])
  const input = createInput({ element: stage, config, onTiltAvailable: setupTiltChip })
  scene = await createScene({ container: stage, config, input })
  const life = await createLife(scene, { messages, config, pop, banner, sound })
  createInteraction({ element: stage, scene, life })
  scene.setLayout(layout)
  scene.compile()
  scene.start()
  // two frames in: the canvas has drawn, fade it in over the still
  requestAnimationFrame(() => requestAnimationFrame(() => scene.canvas.classList.add('ready')))
}

if (animated) {
  const still = document.getElementById('still')
  const go = () => startScene().catch((err) => console.warn('Scene failed, keeping the still image.', err))
  if (still.complete) go()
  else still.addEventListener('load', go, { once: true })
}
