// One quad (or grid) per painted layer.
//
// Everything is positioned in painting pixels (x right, y down) and mapped to
// the screen with the same layout as the still image, so at rest the layers
// stack back into the original painting.
//
// Each layer shifts by (depth - focus) times the camera offset. Standalone
// objects (girl, cats, lamps…) move rigidly at one depth; the trees and path
// are grids whose vertices each read their own depth from the depth map, so
// the far end of the promenade moves less than the near end.
//
// On top of that, each layer can be moved, scaled and turned (uOffset,
// uScale, uRotation around uAnchor) for animation, and a few layers have a
// built-in effect: trees sway, the river ripples, the girl's scarf flutters,
// a turning leaf shows its paler back, a cat's tail swishes, and a balloon
// can have its blue stripes recoloured.
//
// Anything clickable can also be cued: a soft warm rim of light and a touch
// of brightness (uCue, on hover), and a band of light sweeping across it
// (uShine, the idle hint for touch screens, where there is no hover).

export const FX = { none: 0, river: 1, flutter: 2, sway: 3, leaf: 4, tail: 5, balloon: 6 }

const common = /* glsl */ `
  uniform vec4 uRect;       // layer rect in painting px: x, y, w, h
  uniform float uTime;
  uniform float uWind;      // 0..1, breeze strength (gusts)
  uniform float uLife;      // 0 → 1 as the scene wakes up (0 = exactly the painting)
  uniform int uFx;
`

export const vertexShader = /* glsl */ `
  ${common}
  uniform vec4 uPad;        // extra geometry past the rect: left, top, right, bottom (px)
  uniform vec2 uSize;       // painting size in px
  uniform vec4 uLayout;     // painting origin on screen (x, y from top), scale, viewport height
  uniform vec2 uShift;      // painting px moved per unit of (depth - focus)
  uniform float uFocus;     // depth that stays still (the girl)
  uniform float uDepth;     // this layer's depth, or < 0 to read the depth map
  uniform sampler2D uDepthMap;
  uniform vec2 uAnchor;     // painting px that scaling / rotation happen around
  uniform vec2 uScale;
  uniform float uRotation;  // radians, clockwise on screen
  uniform vec2 uOffset;     // extra movement in painting px (animation)
  varying vec2 vUv;

  void main() {
    // uv.y is 1 at the top of the plane; painting y grows downwards
    vec2 p = uRect.xy - uPad.xy + vec2(uv.x, 1.0 - uv.y) * (uRect.zw + uPad.xy + uPad.zw);
    vUv = vec2((p.x - uRect.x) / uRect.z, 1.0 - (p.y - uRect.y) / uRect.w);

    float d = uDepth >= 0.0 ? uDepth : texture2D(uDepthMap, vec2(p.x / uSize.x, 1.0 - p.y / uSize.y)).r;

    vec2 local = (p - uAnchor) * uScale;
    float c = cos(uRotation), sn = sin(uRotation);
    p = uAnchor + vec2(c * local.x - sn * local.y, sn * local.x + c * local.y);
    p += uShift * (d - uFocus) + uOffset;

    vec2 screen = vec2(uLayout.x + p.x * uLayout.z, uLayout.w - (uLayout.y + p.y * uLayout.z));
    gl_Position = projectionMatrix * vec4(screen, 0.0, 1.0);
  }
`

export const fragmentShader = /* glsl */ `
  ${common}
  uniform sampler2D uMap;
  uniform float uOpacity;
  uniform float uFlip;      // leaves: cos of the turn, < 0 = back side showing
  uniform float uHaze;      // leaves, balloons: 0..1 of evening haze (far ones)
  uniform sampler2D uSway;  // trees: how much each pixel sways (0 on trunks and branches)
  uniform sampler2D uWater; // river: 1 where the water ripples, 0 on the far railing
  uniform vec4 uWaterRect;  // river: where uWater sits (painting px)
  uniform vec4 uStripe;     // balloons: new colour for the blue stripes (rgb), and how much (a)
  uniform vec4 uTail;       // cats: tail base xy, tip xy (painting px)
  uniform float uTailAmp;   // cats: swish at the tip, radians
  uniform float uTailPhase; // cats: phase of the swish
  uniform float uTailRest;  // cats: a still curl of the whole tail (radians, + = towards the left)
  uniform float uCue;       // clickable things: 0..1 highlight (hover / hint)
  uniform float uShine;     // clickable things: 0..1 progress of a light sweep, < 0 = none
  uniform float uPx;        // painting px per screen px
  varying vec2 vUv;

  void main() {
    vec2 uv = vUv;
    // painting px of this fragment, for the effects below
    vec2 p = uRect.xy + vec2(uv.x, 1.0 - uv.y) * uRect.zw;
    float glint = 0.0;

    if (uFx == ${FX.river}) {
      // ripple the reflections sideways, fading out at the far bank and
      // behind the flower bed
      float w = uLife * smoothstep(744.0, 758.0, p.y) * (1.0 - smoothstep(805.0, 830.0, p.y)) * (1.0 - smoothstep(780.0, 860.0, p.x));
      w *= texture2D(uWater, clamp((p - uWaterRect.xy) / uWaterRect.zw, 0.0, 1.0) * vec2(1.0, -1.0) + vec2(0.0, 1.0)).r;
      float dx = sin(p.y * 0.8 + uTime * 1.7) * 0.7 + sin(p.y * 0.31 - uTime * 1.1 + p.x * 0.012) * 0.6;
      float dy = sin(p.x * 0.05 + uTime * 1.3) * 0.3;
      uv += vec2(dx, -dy) * w / uRect.zw;
      glint = pow(max(0.0, sin(p.x * 0.045 + 3.0 * sin(p.y * 0.6 + uTime * 0.7) + uTime * 1.3)), 14.0) * w;
    } else if (uFx == ${FX.sway}) {
      // the foliage sways in the breeze, more towards the top; the trunks and
      // main branches stay put. A pixel only moves as far as the map allows
      // both here and where it samples from, so no trunk is dragged along
      float s = sin(uTime * 1.1 + p.x * 0.013 + p.y * 0.004) + 0.4 * sin(uTime * 2.3 + p.x * 0.03 - p.y * 0.01);
      vec2 d = vec2(s * 4.0, 0.35 * sin(uTime * 1.7 + p.x * 0.02)) * uWind;
      d *= texture2D(uSway, uv).r;
      vec2 from = uv - vec2(d.x, -d.y) / uRect.zw;
      d *= texture2D(uSway, from).r;
      uv -= vec2(d.x, -d.y) / uRect.zw;
    } else if (uFx == ${FX.tail}) {
      // turn each point around the tail's base by an angle that grows towards
      // the tip, as a wave running down the tail, so it curls rather than
      // swinging stiff. Only a cone around the tail moves, never the body
      vec2 base = uTail.xy;
      vec2 axis = uTail.zw - base;
      float len = length(axis);
      vec2 v = p - base;
      float r = length(v) / len;
      float ang = acos(clamp(dot(v, axis) / max(length(v) * len, 1e-4), -1.0, 1.0));
      float w = (1.0 - smoothstep(0.6, 0.95, ang)) * (1.0 - smoothstep(1.3, 1.6, r));
      float a = (uTailRest * smoothstep(0.0, 0.5, r) - uTailAmp * sin(uTailPhase - 2.2 * r) * smoothstep(0.05, 1.0, r)) * w;
      float c = cos(a), sn = sin(a);
      p = base + vec2(c * v.x - sn * v.y, sn * v.x + c * v.y);
      uv = vec2((p.x - uRect.x) / uRect.z, 1.0 - (p.y - uRect.y) / uRect.w);
    } else if (uFx == ${FX.flutter}) {
      // the girl in the breeze: the scarf ripples out to its tip, and the
      // dress billows along its right side and hem. Face, bag, hands and shoes
      // stay still
      float gust = uLife * (0.55 + 1.3 * uWind);
      // scarf: the band from her shoulder to the tip, more towards the tip
      float ws = smoothstep(872.0, 990.0, p.x) * smoothstep(640.0, 665.0, p.y) * (1.0 - smoothstep(738.0, 752.0, p.y));
      vec2 ds = vec2(sin(uTime * 2.3 - p.y * 0.07 - p.x * 0.02) * 1.6,
                     sin(uTime * 3.4 - p.x * 0.085) * 3.4) * ws;
      // dress: the flared right side and the hem, not the shoes (bottom left)
      float wd = smoothstep(875.0, 985.0, p.x) * smoothstep(760.0, 820.0, p.y);
      wd = max(wd, smoothstep(870.0, 920.0, p.x) * smoothstep(850.0, 895.0, p.y));
      wd *= 1.0 - smoothstep(918.0, 934.0, p.y);
      vec2 dd = vec2(sin(uTime * 2.0 - p.y * 0.05 + p.x * 0.02) * 2.4,
                     sin(uTime * 2.7 - p.x * 0.06) * 1.3) * wd;
      uv -= (ds + dd) * gust / uRect.zw;
    }

    vec4 c = texture2D(uMap, uv);
    c.rgb += glint * 0.06;
    if (uFx == ${FX.leaf}) {
      // the underside of a leaf is paler and duller; edge-on it catches less light
      float grey = dot(c.rgb, vec3(0.3, 0.59, 0.11));
      c.rgb = mix(c.rgb, grey * vec3(1.1, 0.98, 0.84), 0.28 * step(uFlip, 0.0));
      c.rgb *= 0.84 + 0.16 * abs(uFlip);
      c.rgb = mix(c.rgb, vec3(0.99, 0.84, 0.76), uHaze);
    } else if (uFx == ${FX.balloon}) {
      // only the bluish stripes change colour (keeping their light and shade);
      // the cream ones stay cream
      const vec3 luma = vec3(0.3, 0.59, 0.11);
      vec3 tint = uStripe.rgb * (dot(c.rgb, luma) / dot(uStripe.rgb, luma));
      c.rgb = mix(c.rgb, tint, smoothstep(0.02, 0.1, c.b - c.r) * uStripe.a);
      c.rgb = mix(c.rgb, vec3(0.99, 0.84, 0.76), uHaze);
    }

    const vec3 light = vec3(1.0, 0.95, 0.84);
    if (uShine >= 0.0) {
      // a soft diagonal band of light passing over it, top left to bottom right
      float along = 0.5 * (vUv.x + 1.0 - vUv.y);
      float band = exp(-pow((along - mix(-0.3, 1.3, uShine)) / 0.09, 2.0));
      c.rgb = mix(c.rgb, light, band * 0.3);
    }
    if (uCue > 0.001) {
      // a thin rim of warm light just outside its outline, a few screen px wide
      float ring = 0.0;
      for (int i = 0; i < 8; i++) {
        float a = float(i) * 0.7853982;
        vec2 d = vec2(cos(a), sin(a)) * uPx / uRect.zw;
        ring = max(ring, texture2D(uMap, uv + d * 1.5).a);
        ring = max(ring, 0.55 * texture2D(uMap, uv + d * 3.5).a);
      }
      float halo = ring * (1.0 - c.a) * 0.6 * uCue;
      c.rgb *= 1.0 + 0.07 * uCue;
      float a = c.a + halo;
      c.rgb = (c.rgb * c.a + light * halo) / max(a, 1e-4);
      c.a = a;
    }
    gl_FragColor = vec4(c.rgb, c.a * uOpacity);
  }
`
