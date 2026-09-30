// ─────────────────────────────────────────────────────────────────────────────
//  Everything personal lives here. Edit, save, and the page (and its <head>
//  tags: title, description, social preview) update on the next dev reload /
//  build. Leave a link as '' to hide its icon.
// ─────────────────────────────────────────────────────────────────────────────

const config = {
  name: 'Arshi Shayesta',
  tagline: 'User Experience Designer',

  // Shown one at a time in the girl's thought bubble. `{name}` is replaced
  // with the name above.
  messages: [
    "Hi, I'm Arshi",
    'My portfolio is getting a little refresh…',
    'New work is on its way, back soon',
    'Psst.. that balloon looks suspiciously clickable.',
  ],
  messageSeconds: 5, // how long each line stays before fading to the next

  // What she thinks when someone clicks things in the scene (one is picked at
  // random). Clicking the girl herself skips to the next message above.
  reactions: {
    balloon: ['Up, up and away 🎈', 'Wheee!', 'Bring it back down soon!'],
    cat: ['Mrrp? 🐾', 'The cats say hi', 'Pspsps…'],
  },

  // A tapped balloon lowers a little banner with one of these as it rises.
  // None repeats until all have been seen, and never two of the same at once
  banners: [
    'Keep going, gently.',
    'Never stop becoming.',
    'Fall. Rise. Continue.',
    'Keep moving forward.',
    'Make something meaningful.',
    'Turn ideas into reality.',
    'Your story continues.',
    'Progress, not perfection.',
    'Trust His timing.',
    'His plan, your patience.',
  ],

  links: {
    email: '', // plain address, mailto: is added for you
    instagram: '',
    linkedin: 'https://www.linkedin.com/in/ashayesta/',
    behance: '', // hidden for now; was https://www.behance.net/arshi_shayesta (or a Dribbble URL)
  },

  // <head> / social preview. `url` should be the final address of the site
  // (e.g. https://yourname.com). It is needed for the preview image to show
  // up on some platforms.
  site: {
    title: 'Arshi Shayesta · Portfolio coming soon',
    description:
      'A little riverside scene to wander around while my portfolio gets a refresh. New design work is on its way.',
    url: 'https://uxarshi.com',
    ogImage: 'og.jpg',
    themeColor: '#f6d9c8',
  },

  // Nature sounds (birdsong and the river), switched on with the speaker
  // button in the footer. Always off until the visitor turns it on.
  sound: {
    enabled: true, // false hides the button
    volume: 0.8, // 0..1
  },

  // Motion tuning.
  motion: {
    parallax: 0.04, // screen-height fraction moved per unit of depth away from the girl
    verticalRatio: 0.55, // vertical movement relative to horizontal
    leaves: false, // falling leaves drifting through the scene (true to bring them back)
    idleDrift: 0.22, // gentle automatic sway when nobody is interacting (0 = off)
    tiltRange: 18, // degrees of phone tilt for full movement
    maxPixelRatio: 2,
  },
}

export default config
