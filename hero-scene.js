// Brings the hero still to life: balloons drift, cats breathe and flick
// their tails, the girl's scarf and dress move in the wind, lamps glow.
// Everything is cut from frame 0 of the intro video (tools/build_hero.py),
// so at rest the canvas is pixel-identical to assets/hero.jpg underneath it.
(function () {
  const hero = document.querySelector('.hp-hero');
  const stage = hero && hero.querySelector('.hp-stage');
  if (!stage) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const MOTION = {
    balloon: { lift: 7, sway: 2.2, tilt: 0.012 },  // frame px / radians
    breath: { amount: 0.012, period: 2.8 },        // cats, scale from the feet
    tail: { angle: 0.16, period: 3.4 },            // radians at the tip
    scarf: { amp: 3.2, speed: 7.5, wave: 0.05 },   // swift ripple along the tail
    dress: { amp: 2.4, speed: 4.2, wave: 0.03 },   // slower sway at the hem
    lamp: { glow: 0.22, pulse: 0.06 },
    water: { amp: 1.1, speed: 1.6, glint: 0.05 },  // horizontal shimmer, frame px
    settle: 0.45,                                  // s to calm down when the walk starts
  };

  const canvas = document.createElement('canvas');
  canvas.className = 'hp-living';
  canvas.setAttribute('aria-hidden', 'true');
  const gl = canvas.getContext('webgl', { premultipliedAlpha: true, alpha: true, antialias: false });
  if (!gl) return;

  const VS = `
    attribute vec2 aPos;           // 0..1 quad corner
    uniform vec4 uQuad;            // x, y, w, h in frame px
    uniform vec2 uFrame;
    varying vec2 vP;               // frame px
    void main() {
      vP = uQuad.xy + aPos * uQuad.zw;
      vec2 clip = vP / uFrame * 2.0 - 1.0;
      gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
    }`;

  const FS = `
    precision highp float;
    varying vec2 vP;
    uniform sampler2D uTex, uMap;
    uniform vec4 uRect;            // sprite rect in frame px
    uniform vec2 uOffset, uAnchor, uScale;
    uniform float uRot, uTime, uAmp;
    uniform int uMode;             // 0 plain, 1 wind (girl), 2 tail (cat), 3 glow, 4 plate + river
    uniform vec4 uWaterRect;
    uniform vec3 uWater;           // amp, speed, glint
    uniform vec2 uTailBase;
    uniform float uTailAngle;
    uniform vec4 uScarf, uDress;   // amp, speed, wave, -
    uniform float uGlow;

    vec2 rot(vec2 v, float a) { float c = cos(a), s = sin(a); return vec2(c * v.x - s * v.y, s * v.x + c * v.y); }

    float water(vec2 p) {
      vec2 uv = (p - uWaterRect.xy) / uWaterRect.zw;
      if (uv.x < 0.0 || uv.y < 0.0 || uv.x > 1.0 || uv.y > 1.0) return 0.0;
      return texture2D(uMap, uv).r;
    }

    void main() {
      if (uMode == 4) {
        vec4 col = texture2D(uTex, vP / uRect.zw);
        float w = water(vP) * uAmp;
        if (w > 0.0) {
          float t = uTime * uWater.y;
          // painted strokes are horizontal: slide thin bands sideways, like ripples
          float dx = sin(vP.y * 0.9 + t + 2.0 * sin(vP.x * 0.013 + t * 0.25)) * uWater.x;
          vec2 s = vP + vec2(dx, 0.0);
          vec4 moved = texture2D(uTex, s / uRect.zw);
          col = mix(col, moved, w * water(s));
          col.rgb *= 1.0 + uWater.z * w * sin(vP.x * 0.06 - t * 1.1 + vP.y * 0.4);
        }
        gl_FragColor = col;
        return;
      }
      if (uMode == 3) {
        float d = length(vP - uAnchor) / uRect.z;
        float g = exp(-d * d * 3.2) * uGlow;
        gl_FragColor = vec4(vec3(1.0, 0.78, 0.48) * g, 0.0);
        return;
      }
      // Undo the sprite's transform: where in the still did this pixel come from?
      vec2 q = uAnchor + rot(vP - uOffset - uAnchor, -uRot) / uScale;
      vec2 uv = (q - uRect.xy) / uRect.zw;

      if (uMode == 1) {
        float w = texture2D(uMap, uv).r * uAmp;
        float t = uTime;
        // scarf: ripples run from the shoulder out to the tip
        vec2 s = vec2(
          0.45 * sin(q.y * uScarf.z * 1.3 - t * uScarf.y * 0.8),
          sin(q.x * uScarf.z - t * uScarf.y) + 0.35 * sin(q.x * uScarf.z * 2.1 - t * uScarf.y * 1.6)
        ) * uScarf.x;
        // dress: the hem sways sideways, waves travelling down the skirt
        vec2 d = vec2(
          sin(q.y * uDress.z - t * uDress.y + q.x * 0.01) + 0.3 * sin(q.y * uDress.z * 2.3 - t * uDress.y * 1.7),
          0.25 * sin(q.x * uDress.z - t * uDress.y)
        ) * uDress.x;
        float scarfZone = step(q.y, 775.0);
        q -= w * mix(d, s, scarfZone);
        uv = (q - uRect.xy) / uRect.zw;
      } else if (uMode == 2) {
        float w = texture2D(uMap, uv).r;
        q = uTailBase + rot(q - uTailBase, -uTailAngle * w);
        uv = (q - uRect.xy) / uRect.zw;
      }

      if (uv.x < 0.0 || uv.y < 0.0 || uv.x > 1.0 || uv.y > 1.0) discard;
      gl_FragColor = texture2D(uTex, uv);
    }`;

  function shader(type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  const prog = gl.createProgram();
  gl.attachShader(prog, shader(gl.VERTEX_SHADER, VS));
  gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FS));
  gl.linkProgram(prog);
  gl.useProgram(prog);
  const U = {};
  ['uQuad', 'uFrame', 'uTex', 'uMap', 'uRect', 'uOffset', 'uAnchor', 'uScale', 'uRot', 'uTime', 'uAmp',
    'uMode', 'uTailBase', 'uTailAngle', 'uScarf', 'uDress', 'uGlow', 'uWaterRect', 'uWater'].forEach((n) => { U[n] = gl.getUniformLocation(prog, n); });

  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW);
  const aPos = gl.getAttribLocation(prog, 'aPos');
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  gl.uniform1i(U.uTex, 0);
  gl.uniform1i(U.uMap, 1);

  function loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = src;
    });
  }
  function texture(img) {
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return t;
  }

  // Small deterministic jitter so every balloon and cat keeps its own rhythm.
  const rand = (i, k) => { const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); };

  let scene, plate, waterMap, sprites, W, H;
  let amp = 1, ampTarget = 1, running = false, raf = 0, last = 0, clock = 0;
  let onScreen = true;

  async function init() {
    const res = await fetch('assets/hero/scene.json');
    scene = await res.json();
    [W, H] = scene.size;
    plate = texture(await loadImage('assets/hero/plate.jpg'));
    waterMap = texture(await loadImage(scene.water.map));
    sprites = await Promise.all(scene.sprites.map(async (s, i) => {
      const [img, map] = await Promise.all([
        loadImage(s.src),
        s.wind || s.tail ? loadImage((s.wind || s.tail).map) : null,
      ]);
      return Object.assign({}, s, {
        tex: texture(img),
        map: map ? texture(map) : null,
        phase: rand(i, 1) * Math.PI * 2,
        period: 6 + rand(i, 2) * 4,
        depth: Math.min(1, s.rect[3] / 150),   // bigger balloons are nearer: move more
      });
    }));
    stage.insertBefore(canvas, stage.querySelector('.hp-scene').nextSibling);
    resize();
    new ResizeObserver(resize).observe(stage);
    draw(0);
    requestAnimationFrame(() => canvas.classList.add('is-ready'));
    sync();
    new MutationObserver(sync).observe(hero, { attributes: true, attributeFilter: ['class'] });
    document.addEventListener('visibilitychange', sync);
    new IntersectionObserver(([entry]) => { onScreen = entry.isIntersecting; sync(); }).observe(hero);
  }

  function resize() {
    const r = stage.getBoundingClientRect();
    // The art is 1920 px wide; drawing more pixels than that adds nothing.
    const scale = Math.min(window.devicePixelRatio || 1, W / Math.max(1, r.width));
    canvas.width = Math.round(r.width * scale);
    canvas.height = Math.round(r.height * scale);
    gl.viewport(0, 0, canvas.width, canvas.height);
    if (!running && sprites) draw(clock);
  }

  function setQuad(x, y, w, h) { gl.uniform4f(U.uQuad, x, y, w, h); }

  function draw(t) {
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(U.uFrame, W, H);
    gl.uniform1f(U.uTime, t);
    gl.uniform1f(U.uAmp, amp);

    // Plate, with the river rippling
    gl.uniform1i(U.uMode, 4);
    gl.uniform4f(U.uWaterRect, ...scene.water.rect);
    gl.uniform3f(U.uWater, MOTION.water.amp, MOTION.water.speed, MOTION.water.glint);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, waterMap);
    gl.uniform4f(U.uRect, 0, 0, W, H);
    gl.uniform2f(U.uOffset, 0, 0);
    gl.uniform2f(U.uAnchor, 0, 0);
    gl.uniform2f(U.uScale, 1, 1);
    gl.uniform1f(U.uRot, 0);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, plate);
    setQuad(0, 0, W, H);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    for (const s of sprites) {
      const [x, y, w, h] = s.rect;
      let ox = 0, oy = 0, rotA = 0, sx = 1, sy = 1;
      let ax = x + w / 2, ay = y + h / 2;
      let mode = 0, pad = 0;

      if (s.kind === 'balloon') {
        const p = (t / s.period) * Math.PI * 2 + s.phase;
        const k = MOTION.balloon, d = 0.55 + 0.45 * s.depth;
        oy = Math.sin(p) * k.lift * d;
        ox = Math.sin(p * 0.53 + 1.3) * k.sway * d;
        rotA = Math.sin(p * 0.53 + 0.4) * k.tilt;
        ay = y;                                // tilt hangs from the envelope top
        pad = 12;
      } else if (s.kind === 'cat') {
        const k = MOTION.breath;
        const b = Math.sin((t / (k.period + s.phase * 0.1)) * Math.PI * 2 + s.phase);
        sy = 1 + b * k.amount;
        sx = 1 + b * k.amount * 0.35;
        [ax, ay] = s.anchor;
        pad = 4;
        if (s.tail) {
          mode = 2;
          const tk = MOTION.tail;
          const tp = (t / tk.period) * Math.PI * 2 + s.phase;
          // lazy swish, with a quicker flick layered on now and then
          const flick = Math.pow(Math.max(0, Math.sin(tp * 0.37)), 8) * Math.sin(tp * 3.1);
          gl.uniform2f(U.uTailBase, s.tail.base[0], s.tail.base[1]);
          gl.uniform1f(U.uTailAngle, (Math.sin(tp) * 0.7 + flick * 0.6) * tk.angle * amp);
          pad = 14;
        }
      } else if (s.kind === 'girl') {
        mode = 1;
        pad = 10;
        const a = MOTION.scarf, d = MOTION.dress;
        gl.uniform4f(U.uScarf, a.amp, a.speed, a.wave, 0);
        gl.uniform4f(U.uDress, d.amp, d.speed, d.wave, 0);
      }

      gl.uniform1i(U.uMode, mode);
      gl.uniform4f(U.uRect, x, y, w, h);
      gl.uniform2f(U.uOffset, ox * amp, oy * amp);
      gl.uniform2f(U.uAnchor, ax, ay);
      gl.uniform2f(U.uScale, 1 + (sx - 1) * amp, 1 + (sy - 1) * amp);
      gl.uniform1f(U.uRot, rotA * amp);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, s.tex);
      if (s.map) {
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, s.map);
      }
      setQuad(x - pad, y - pad, w + pad * 2, h + pad * 2);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }

    // Lamp glow
    gl.uniform1i(U.uMode, 3);
    scene.lamps.forEach((l, i) => {
      const k = MOTION.lamp;
      const flicker = Math.sin(t * 1.3 + i * 1.7) * 0.6 + Math.sin(t * 3.7 + i) * 0.4;
      const r = l.r * 1.6;
      gl.uniform2f(U.uAnchor, l.x, l.y);
      gl.uniform4f(U.uRect, 0, 0, r, r);
      gl.uniform1f(U.uGlow, (k.glow + flicker * k.pulse) * amp);
      setQuad(l.x - r * 1.5, l.y - r * 1.5, r * 3, r * 3);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    });
  }

  function frame(now) {
    const dt = last ? Math.min(0.05, (now - last) / 1000) : 0;
    last = now;
    clock += dt;
    // Ease in on load, ease out when the walk starts so the video picks up from rest.
    const step = dt / MOTION.settle;
    amp = ampTarget > amp ? Math.min(ampTarget, amp + step) : Math.max(ampTarget, amp - step);
    draw(clock);
    raf = requestAnimationFrame(frame);
  }

  function sync() {
    const walking = hero.classList.contains('is-walking');
    const hidden = document.hidden || !onScreen || hero.classList.contains('is-playing');
    ampTarget = walking ? 0 : 1;
    if (hidden && running) {
      cancelAnimationFrame(raf);
      running = false;
    } else if (!hidden && !running) {
      if (!walking) amp = 0;
      last = 0;
      running = true;
      raf = requestAnimationFrame(frame);
    }
  }

  init().catch((err) => console.warn('[hero] living scene unavailable, showing the still:', err));
})();
