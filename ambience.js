// Birdsong under the hero, taken from the intro video's own soundtrack
// (assets/audio/birds.m4a: its cleanest chirps, footsteps filtered out).
// The clip is only 5.6 s, so instead of looping it we keep layering short,
// overlapping snippets of it at slightly different pitch and pan, which
// never repeats audibly. Plays only while Sound is on and the visitor is on
// the promenade (the walk video brings its own audio). Once the projects are
// what's on screen (scrolled there, "Skip to projects" or "Show projects") it
// fades out slowly and stops, and comes back on the way up to the hero.
(function () {
  const hero = document.querySelector('.hp-hero');
  const toggle = document.querySelector('[data-sound-toggle]');
  if (!hero || !toggle) return;

  const CLIP = 'assets/audio/birds.m4a';
  const VOLUME = 0.7;
  const FADE = 1.2;        // s, whole bed in/out
  const FADE_AWAY = 2.5;   // s, slow fade once the projects are on screen
  const work = document.getElementById('work');
  const GRAIN = { min: 1.8, max: 3.4, fade: 0.45, gapMin: 0.9, gapMax: 1.7 };

  let ctx = null, master = null, buffer = null, loading = null;
  let playing = false, timer = 0;

  // The projects are what's on screen: the hero has gone and the "Selected
  // work" heading is near the top (where Skip/Show projects land), or past it.
  function atProjects() {
    return !!work && work.getBoundingClientRect().top <= window.innerHeight * 0.2;
  }

  function glide(target, seconds) {
    const now = ctx.currentTime;
    master.gain.cancelScheduledValues(now);
    master.gain.setValueAtTime(master.gain.value, now);
    master.gain.linearRampToValueAtTime(target, now + seconds);
  }

  function setup() {
    if (ctx) return loading;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 0;
    master.connect(ctx.destination);
    loading = fetch(CLIP)
      .then((r) => r.arrayBuffer())
      .then((data) => new Promise((resolve, reject) => ctx.decodeAudioData(data, resolve, reject)))
      .then((b) => { buffer = b; });
    return loading;
  }

  function grain(when) {
    const len = GRAIN.min + Math.random() * (GRAIN.max - GRAIN.min);
    const offset = Math.random() * Math.max(0, buffer.duration - len);
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.playbackRate.value = 0.95 + Math.random() * 0.1;
    const env = ctx.createGain();
    const peak = 0.55 + Math.random() * 0.45;
    env.gain.setValueAtTime(0, when);
    env.gain.linearRampToValueAtTime(peak, when + GRAIN.fade);
    env.gain.setValueAtTime(peak, when + len - GRAIN.fade);
    env.gain.linearRampToValueAtTime(0, when + len);
    let out = env;
    if (ctx.createStereoPanner) {
      const pan = ctx.createStereoPanner();
      pan.pan.value = (Math.random() * 2 - 1) * 0.5;
      env.connect(pan);
      out = pan;
    }
    src.connect(env);
    out.connect(master);
    src.start(when, offset, len);
  }

  function schedule() {
    if (!playing) return;
    const now = ctx.currentTime;
    grain(now + 0.05);
    const gap = GRAIN.gapMin + Math.random() * (GRAIN.gapMax - GRAIN.gapMin);
    timer = setTimeout(schedule, gap * 1000);
  }

  function start() {
    if (playing) return;
    playing = true;
    // resume() has to be called from the tap itself on iOS Safari
    ctx.resume();
    loading.then(() => {
      if (!playing) return;
      const now = ctx.currentTime;
      glide(VOLUME, FADE);
      grain(now + 0.05);  // two voices straight away so it starts full
      grain(now + 0.6);
      timer = setTimeout(schedule, 1200);
    }).catch((err) => console.warn('[ambience] birdsong unavailable:', err));
  }

  function stop(seconds = FADE * 0.5) {
    if (!playing) return;
    playing = false;
    clearTimeout(timer);
    glide(0, seconds);
  }

  function sync() {
    const soundOn = toggle.getAttribute('aria-pressed') === 'true';
    const onPromenade = !hero.classList.contains('is-walking');
    const away = atProjects();
    if (soundOn && onPromenade && !away && !document.hidden) {
      try { setup(); } catch (err) { return; }
      if (ctx) start();
    } else if (ctx) {
      stop(away ? FADE_AWAY : FADE * 0.5);
    }
  }

  let ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => { ticking = false; sync(); });
  }

  // main.js flips aria-pressed in its own click handler, which runs first.
  toggle.addEventListener('click', sync);
  new MutationObserver(sync).observe(hero, { attributes: true, attributeFilter: ['class'] });
  document.addEventListener('visibilitychange', sync);
  window.addEventListener('scroll', onScroll, { passive: true });
})();
