(function () {
  const hero = document.querySelector('.hp-hero');
  const walk = hero.querySelector('.hp-walk');
  const frame = hero.querySelector('.hp-walk-frame');
  const video = hero.querySelector('.hp-walk-video');
  const laptop = hero.querySelector('.hp-laptop');
  const flash = hero.querySelector('.hp-laptop-flash');
  const showProjects = hero.querySelector('[data-show-projects]');
  const walkStart = hero.querySelector('[data-walk-start]');
  const walkControl = hero.querySelector('[data-walk-control]');
  const soundToggle = document.querySelector('[data-sound-toggle]');
  const soundLabel = soundToggle.querySelector('.hp-sound-label');
  const soundMirror = document.querySelector('[data-sound-mirror]');
  const card = hero.querySelector('.hp-card');
  const introToggle = hero.querySelector('[data-intro-toggle]');
  const work = document.getElementById('work');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  // ---------- Focus without a ring for touch and mouse ----------

  // The walk moves focus along (to Skip, the laptop button, then the Work
  // heading) so keyboard and screen-reader users keep their place. Browsers
  // draw a focus ring on those programmatic moves even after a tap, so the
  // ring is only kept when the visitor is actually using the keyboard.
  let keyboardUser = false;
  document.addEventListener('keydown', (e) => { if (!e.metaKey && !e.ctrlKey && !e.altKey) keyboardUser = true; }, true);
  document.addEventListener('pointerdown', () => { keyboardUser = false; }, true);
  function moveFocus(el) {
    if (!el) return;
    if (!keyboardUser) {
      el.classList.add('is-quiet-focus');
      el.addEventListener('blur', () => el.classList.remove('is-quiet-focus'), { once: true });
    }
    el.focus({ preventScroll: true, focusVisible: keyboardUser });
  }

  // ---------- Sound ----------

  let soundOn = false;

  function setSound(on) {
    soundOn = on;
    soundToggle.setAttribute('aria-pressed', String(on));
    soundToggle.setAttribute('aria-label', on ? 'Sound on' : 'Sound off');
    soundLabel.textContent = on ? 'Sound on' : 'Sound off';
    if (soundMirror) {
      soundMirror.setAttribute('aria-pressed', String(on));
      soundMirror.setAttribute('aria-label', on ? 'Sound on' : 'Sound off');
    }
    video.muted = !on;
  }

  soundToggle.addEventListener('click', () => setSound(!soundOn));
  // The intro card's icon-only button drives the header toggle, so the
  // birdsong and every other listener on that toggle stay in sync.
  if (soundMirror) soundMirror.addEventListener('click', () => soundToggle.click());
  setSound(false);

  // ---------- Arriving at Selected work ----------

  // A case study's "All projects" links to index.html#work: land there
  // straight away instead of gliding down past the hero, and line up again
  // once fonts and images are in (unless the visitor has moved on).
  if (location.hash === '#work') {
    const root = document.documentElement;
    root.style.scrollBehavior = 'auto';
    work.scrollIntoView();
    window.addEventListener('load', () => {
      const off = Math.abs(work.getBoundingClientRect().top - (parseFloat(getComputedStyle(work).scrollMarginTop) || 0));
      if (off < 200) work.scrollIntoView();
      requestAnimationFrame(() => { root.style.scrollBehavior = ''; });
    }, { once: true });
  }

  // ---------- Intro card (collapsible on small screens) ----------

  introToggle.addEventListener('click', () => {
    const open = card.classList.toggle('is-collapsed') === false;
    introToggle.setAttribute('aria-expanded', String(open));
    introToggle.setAttribute('aria-label', open ? 'Hide introduction' : 'Show introduction');
  });

  // ---------- Walk with me ----------

  // Where the laptop screen is in the video's last frame (tools/build_walk.py).
  let screenInfo = null;
  fetch('assets/video/intro-walk.json')
    .then((r) => r.json())
    .then((t) => { screenInfo = t; placeLaptop(t); })
    .catch((err) => console.warn('[walk] no laptop screen, the walk will end on Work:', err));

  function placeLaptop(t) {
    const [W, H] = t.frame;
    const [tl, tr, br, bl] = t.screen;
    const cx = (tl[0] + tr[0] + br[0] + bl[0]) / 4;
    const cy = (tl[1] + tr[1] + br[1] + bl[1]) / 4;
    const w = Math.hypot(tr[0] - tl[0], tr[1] - tl[1]);
    const h = (Math.hypot(bl[0] - tl[0], bl[1] - tl[1]) + Math.hypot(br[0] - tr[0], br[1] - tr[1])) / 2;
    const angle = Math.atan2(tr[1] - tl[1], tr[0] - tl[0]);
    Object.assign(laptop.style, {
      left: `${((cx - w / 2) / W) * 100}%`,
      top: `${((cy - h / 2) / H) * 100}%`,
      width: `${(w / W) * 100}%`,
      height: `${(h / H) * 100}%`,
      transform: `rotate(${angle}rad)`,
    });
    laptop.dataset.angle = String(angle);
  }

  // Start fetching the video as soon as the visitor shows intent.
  ['pointerenter', 'focus', 'touchstart'].forEach((type) => {
    walkStart.addEventListener(type, () => { video.preload = 'auto'; }, { once: true, passive: true });
  });

  let state = 'idle';   // idle | walking | cta | pressing | zooming

  // ---------- Framing on narrow screens ----------

  // On a portrait phone only a tall slice of the 16:9 video fits. Each shot
  // gets one steady framing that keeps her in view, and the frame jumps at
  // the cuts, like an edit; the only move is one slow drift in the opening
  // walk, from where the still is framed. Where the whole frame fits
  // (desktop) the pan clamps to zero and nothing moves.
  // [time s, x of the framing centre in video px]; a new shot starts at each CUTS time.
  const FOCUS = [
    [0, 1066], [2.93, 1130],     // walk: slow drift as she crosses the promenade
    [2.94, 1120], [9.5, 1120],   // bench, glasses, laptop out
    [9.55, 962], [11.3, 962],    // laptop
    [11.32, 1085], [13.3, 1085], // close-up
    [13.32, 960], [16, 960],     // laptop, ends on the screen
  ];
  const CUTS = [2.935, 9.54, 11.31, 13.31];
  const FRAME_W = 1920;
  let panX = null, panRaf = 0, panLast = 0, panShot = -1;
  let startX = FOCUS[0][1];   // where the still is framed on this screen, so the fade-in doesn't jump

  function shotOf(t) { let i = 0; while (i < CUTS.length && t >= CUTS[i]) i++; return i; }
  function focusAt(t) {
    const shot = shotOf(t);
    const keys = FOCUS.filter(([kt]) => shotOf(kt) === shot).map((k, i) => (shot === 0 && i === 0 ? [k[0], startX] : k));
    if (t <= keys[0][0]) return keys[0][1];
    for (let i = 1; i < keys.length; i++) {
      const [t0, x0] = keys[i - 1], [t1, x1] = keys[i];
      if (t <= t1) { const k = (t - t0) / (t1 - t0); return x0 + (x1 - x0) * (k * k * (3 - 2 * k)); }
    }
    return keys[keys.length - 1][1];
  }
  function applyPan(x) {
    const fw = frame.offsetWidth, vw = walk.clientWidth;
    const room = Math.max(0, (fw - vw) / 2);
    const dx = Math.max(-room, Math.min(room, (0.5 - x / FRAME_W) * fw));
    frame.style.transform = `translate(calc(-50% + ${dx.toFixed(1)}px), -50%)`;
  }
  function panTick(now) {
    const t = video.currentTime, shot = shotOf(t), target = focusAt(t);
    const dt = Math.min(0.1, (now - panLast) / 1000 || 0);
    panLast = now;
    // Ease towards the target; snap on a cut, a seek, or with reduced motion.
    const jump = panX === null || shot !== panShot || Math.abs(target - panX) > 160 || reducedMotion.matches;
    panX = jump ? target : panX + (target - panX) * (1 - Math.exp(-dt / 0.25));
    panShot = shot;
    applyPan(panX);
    const settled = video.paused && Math.abs(target - panX) < 0.5;
    if ((state === 'walking' || state === 'cta') && !settled) panRaf = requestAnimationFrame(panTick);
  }
  function startPan() {
    const stage = hero.querySelector('.hp-stage').getBoundingClientRect();
    const box = walk.getBoundingClientRect();
    startX = ((box.left + box.width / 2 - stage.left) / stage.width) * FRAME_W;
    cancelAnimationFrame(panRaf); panX = null; panShot = -1; panLast = performance.now(); panTick(panLast);
  }
  function stopPan() { cancelAnimationFrame(panRaf); panX = null; frame.style.transform = ''; }
  window.addEventListener('resize', () => { if (panX !== null) applyPan(panX); });
  video.addEventListener('play', () => {
    if (state !== 'walking') return;
    cancelAnimationFrame(panRaf); panLast = performance.now(); panRaf = requestAnimationFrame(panTick);
  });
  video.addEventListener('seeked', () => { if (state === 'walking' || state === 'cta') { panX = null; panTick(performance.now()); } });

  function startWalk() {
    window.scrollTo({ top: 0, behavior: 'instant' });
    state = 'walking';
    hero.classList.add('is-walking');
    walk.setAttribute('aria-hidden', 'false');
    video.currentTime = 0;
    video.muted = !soundOn;
    startPan();

    // play() must run inside the tap handler so mobile browsers allow it.
    video.play().catch(() => {
      // Some browsers refuse playback with sound; fall back to muted.
      video.muted = true;
      return video.play();
    }).catch(endWalk);
  }

  // The walk ends on her laptop and waits there for the visitor.
  function arriveAtLaptop() {
    if (state !== 'walking') return;
    if (!screenInfo) { endWalk(); showWork(); return; }
    state = 'cta';
    video.pause();
    hero.classList.add('is-cta');
    walkControl.textContent = 'Back to start';
    showProjects.tabIndex = 0;
    moveFocus(showProjects);
  }

  function onWalkControl() {
    if (state === 'walking') {
      // Skip: jump to the end of the walk, where the laptop waits.
      if (Number.isFinite(video.duration)) video.currentTime = video.duration;
      arriveAtLaptop();
    } else if (state === 'cta') {
      endWalk();
      moveFocus(walkStart);
    }
  }

  function endWalk() {
    state = 'idle';
    video.pause();
    hero.classList.remove('is-walking', 'is-playing', 'is-cta', 'is-pressed', 'is-zooming');
    walk.setAttribute('aria-hidden', 'true');
    walkControl.textContent = 'Skip';
    showProjects.tabIndex = -1;
    stopPan();
  }

  // ---------- Show projects ----------

  // Its sounds are made on the spot (no files) and only play with Sound on.
  let audio = null;
  function sfx() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!soundOn || !AC) return null;
    audio = audio || new AC();
    audio.resume();
    const out = audio.createGain();
    out.connect(audio.destination);
    return { ctx: audio, out, now: audio.currentTime + 0.01 };
  }

  function bell(a, freq, t0, peak, decay) {
    const osc = a.ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.value = freq;
    const g = a.ctx.createGain();
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(peak, t0 + 0.015);
    g.gain.exponentialRampToValueAtTime(0.0003, t0 + decay);
    osc.connect(g).connect(a.out);
    osc.start(t0);
    osc.stop(t0 + decay + 0.05);
  }

  // Hover: a faint rising shimmer, like the stars around it catching light.
  let lastHover = 0;
  function playHoverSound() {
    if (performance.now() - lastHover < 500) return;
    const a = sfx();
    if (!a) return;
    lastHover = performance.now();
    [1568, 2093, 2637].forEach((f, i) => bell(a, f, a.now + i * 0.045, 0.022, 0.5));
    const len = Math.round(a.ctx.sampleRate * 0.35);
    const buf = a.ctx.createBuffer(1, len, a.ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.sin(Math.PI * i / len);
    const air = a.ctx.createBufferSource();
    air.buffer = buf;
    const hp = a.ctx.createBiquadFilter();
    hp.type = 'bandpass';
    hp.frequency.setValueAtTime(3000, a.now);
    hp.frequency.linearRampToValueAtTime(6500, a.now + 0.35);
    hp.Q.value = 1.4;
    const g = a.ctx.createGain();
    g.gain.value = 0.035;
    air.connect(hp).connect(g).connect(a.out);
    air.start(a.now);
  }

  // Click: the key tap, a light springy wobble that follows the squash and
  // stretch (same 480 ms), and two soft bell notes as the screen opens.
  const BOUNCE_MS = 480;
  function playPressSound() {
    const a = sfx();
    if (!a) return;
    const { ctx, now } = a;

    const len = Math.round(ctx.sampleRate * 0.03);
    const noise = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = noise.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
    const click = ctx.createBufferSource();
    click.buffer = noise;
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = 3200;
    bp.Q.value = 0.9;
    const clickGain = ctx.createGain();
    clickGain.gain.value = 0.3;
    click.connect(bp).connect(clickGain).connect(a.out);
    click.start(now);

    // the wobble: pitch swings with the squash and stretch and settles
    const dur = BOUNCE_MS / 1000;
    const steps = 64;
    const curve = new Float32Array(steps);
    for (let i = 0; i < steps; i++) {
      const t = i / (steps - 1);
      curve[i] = 260 * (1 + 0.05 * Math.exp(-4 * t) * Math.sin(2 * Math.PI * 1.6 * t));
    }
    const wob = ctx.createOscillator();
    wob.type = 'triangle';
    wob.frequency.setValueCurveAtTime(curve, now, dur);
    const soft = ctx.createBiquadFilter();
    soft.type = 'lowpass';
    soft.frequency.value = 1400;
    const wg = ctx.createGain();
    wg.gain.setValueAtTime(0, now);
    wg.gain.linearRampToValueAtTime(0.1, now + 0.02);
    wg.gain.exponentialRampToValueAtTime(0.002, now + dur);
    wob.connect(soft).connect(wg).connect(a.out);
    wob.start(now);
    wob.stop(now + dur + 0.05);

    bell(a, 880, now + dur * 0.68, 0.06, 0.9);
    bell(a, 1318.5, now + dur * 0.68 + 0.08, 0.06, 0.9);
  }

  showProjects.addEventListener('pointerenter', (e) => {
    if (state === 'cta' && e.pointerType === 'mouse') playHoverSound();
  });

  showProjects.addEventListener('click', () => {
    if (state !== 'cta') return;
    state = 'pressing';
    playPressSound();
    hero.classList.add('is-pressed');
    // The screen flashes open as the bounce settles.
    setTimeout(openWork, reducedMotion.matches ? 0 : BOUNCE_MS * 0.62);
  });

  // The same view "Skip to projects" scrolls to.
  function workScrollTop() {
    const margin = parseFloat(getComputedStyle(work).scrollMarginTop) || 0;
    const top = work.getBoundingClientRect().top + window.scrollY - margin;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    return Math.max(0, Math.min(top, max));
  }

  function showWork(top = workScrollTop()) {
    window.scrollTo({ top, behavior: 'instant' });
    history.replaceState(null, '', '#work');
    work.querySelector('h2').setAttribute('tabindex', '-1');
    moveFocus(work.querySelector('h2'));
  }

  // A static copy of the page as it will look once scrolled to Work, which
  // rides inside the laptop screen and grows to fill the window.
  function buildWorkView(top, vw, vh) {
    const view = document.createElement('div');
    view.className = 'hp-laptop-view';
    view.setAttribute('aria-hidden', 'true');
    view.inert = true;
    const page = document.createElement('div');
    page.className = 'page';
    page.style.cssText = `position:absolute;left:0;top:${-top}px;width:${vw}px`;
    const heroCopy = hero.cloneNode(true);
    heroCopy.classList.remove('is-walking', 'is-playing', 'is-cta', 'is-pressed', 'is-zooming');
    heroCopy.querySelectorAll('.hp-walk, .hp-living').forEach((el) => el.remove());
    page.append(heroCopy);
    document.querySelectorAll('.page > main, .page > footer').forEach((el) => page.append(el.cloneNode(true)));
    page.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'));
    page.querySelectorAll('img[loading]').forEach((el) => el.removeAttribute('loading'));
    view.append(page);
    return view;
  }

  function openWork() {
    const top = workScrollTop();
    if (reducedMotion.matches) {
      endWalk();
      showWork(top);
      return;
    }
    state = 'zooming';
    const vw = document.documentElement.clientWidth;
    const vh = window.innerHeight;
    const sw = laptop.offsetWidth;
    const sh = laptop.offsetHeight;
    const k = Math.max(vw / sw, vh / sh);   // screen just covers the window

    // The view sits centred in the screen at 1/k, so at the end of the zoom
    // it is exactly the window.
    const view = buildWorkView(top, vw, vh);
    Object.assign(view.style, {
      width: `${vw}px`,
      height: `${vh}px`,
      left: `${(sw - vw / k) / 2}px`,
      top: `${(sh - vh / k) / 2}px`,
      transform: `scale(${1 / k})`,
      opacity: '0',
    });
    laptop.insertBefore(view, flash);

    // Zoom about the screen's centre, carrying it to the middle of the
    // window and straightening it.
    const walkBox = walk.getBoundingClientRect();
    const box = laptop.getBoundingClientRect();
    const cx = box.left + box.width / 2;
    const cy = box.top + box.height / 2;
    const angle = parseFloat(laptop.dataset.angle) || 0;
    walk.style.transformOrigin = `${cx - walkBox.left}px ${cy - walkBox.top}px`;
    hero.classList.add('is-zooming');

    flash.animate([{ opacity: 0 }, { opacity: 0.95, offset: 0.3 }, { opacity: 0 }],
      { duration: 520, easing: 'ease-out', fill: 'forwards' });
    view.animate([{ opacity: 0 }, { opacity: 1 }],
      { duration: 160, delay: 120, fill: 'forwards' });
    const zoom = walk.animate([
      { transform: 'none' },
      { transform: `translate(${vw / 2 - cx}px, ${vh / 2 - cy}px) rotate(${-angle}rad) scale(${k})` },
    ], { duration: 1100, delay: 260, easing: 'cubic-bezier(.65, 0, .25, 1)', fill: 'forwards' });

    zoom.finished.then(() => {
      showWork(top);
      endWalk();
      zoom.cancel();
      view.remove();
      flash.getAnimations().forEach((a) => a.cancel());
      walk.style.transformOrigin = '';
    });
  }

  video.addEventListener('playing', () => {
    if (state === 'idle') return;
    hero.classList.add('is-playing');
    moveFocus(walkControl);
  });
  video.addEventListener('ended', arriveAtLaptop);
  video.addEventListener('error', endWalk);

  walkStart.addEventListener('click', startWalk);
  walkControl.addEventListener('click', onWalkControl);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && (state === 'walking' || state === 'cta')) endWalk();
  });

  // Scrolling away mid-walk leaves the walk.
  new IntersectionObserver(([entry]) => {
    if (entry.intersectionRatio < 0.4 && (state === 'walking' || state === 'cta')) endWalk();
  }, { threshold: [0.4] }).observe(hero);
})();
