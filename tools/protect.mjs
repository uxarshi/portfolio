// Builds the public, password-protected case-study.html from the readable
// copy in private/ (git-ignored, never published).
//
//   CS_PASSWORD='…' node tools/protect.mjs
//
// The whole page, with its private images inlined as data URIs, is encrypted
// with AES-256-GCM; the key comes from the password via PBKDF2-SHA256. The
// published file holds only ciphertext plus a small unlock screen, so the
// content can't be read from the source without the password. The password
// itself is never written to disk; pass it in each time you rebuild.
//
// Edit private/case-study.html (and private/assets/), then run this again.

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { webcrypto as crypto } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SRC = path.join(root, 'private/case-study.html');
const PRIVATE_ASSETS = path.join(root, 'private/assets');
const OUT = path.join(root, 'case-study.html');
const ITERATIONS = 600000;

const password = process.env.CS_PASSWORD;
if (!password) {
  console.error("Set the password: CS_PASSWORD='…' node tools/protect.mjs");
  process.exit(1);
}

let html = readFileSync(SRC, 'utf8');

// Inline the confidential images so they're encrypted along with the text.
// Shared site images (balloons, footer) stay as normal public files.
const MIME = { webp: 'image/webp', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', svg: 'image/svg+xml' };
let inlined = 0;
html = html.replace(/assets\/(cs1-[A-Za-z0-9_.-]+)/g, (m, name) => {
  const file = path.join(PRIVATE_ASSETS, name);
  if (!existsSync(file)) throw new Error('Missing private asset: ' + name);
  inlined++;
  return `data:${MIME[name.split('.').pop().toLowerCase()]};base64,${readFileSync(file).toString('base64')}`;
});

// The unlock screen counts the visit; count unlocks separately instead of twice.
html = html.replace(/<script data-goatcounter[\s\S]*?<\/script>\s*/, '');

const enc = new TextEncoder();
const salt = crypto.getRandomValues(new Uint8Array(16));
const iv = crypto.getRandomValues(new Uint8Array(12));
const baseKey = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']);
const key = await crypto.subtle.deriveKey(
  { name: 'PBKDF2', salt, iterations: ITERATIONS, hash: 'SHA-256' },
  baseKey, { name: 'AES-GCM', length: 256 }, false, ['encrypt']);
const cipher = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, enc.encode(html)));

const b64 = (u8) => Buffer.from(u8).toString('base64');
const payload = JSON.stringify({ v: 1, it: ITERATIONS, s: b64(salt), iv: b64(iv), ct: b64(cipher) });

const gate = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Case study: password required – Arshi Shayesta</title>
<meta name="robots" content="noindex, nofollow">
<link rel="icon" href="assets/favicon-32.png" sizes="32x32">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600..800&family=Caveat:wght@600&family=Instrument+Sans:wght@400;500;600&display=swap">
<script data-goatcounter="https://uxarshi.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px 16px;background:#FAF4E8;color:#1D2340;font:400 17px/1.55 'Instrument Sans',system-ui,sans-serif}
.lock{width:min(460px,100%);padding:36px 32px 30px;background:#FDF9F1;border:1.5px solid #1D2340;border-radius:30px 24px 32px 26px/26px 32px 24px 30px;box-shadow:0 28px 56px -28px rgba(45,30,15,.45)}
.no{margin:0 0 6px;font:600 26px/1 Caveat,cursive}
.eyebrow{margin:0 0 10px;font-size:13px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#4B5068}
h1{margin:0;font:800 32px/1.1 'Bricolage Grotesque',sans-serif;letter-spacing:-.02em}
.lede{margin:12px 0 24px;color:#4B5068}
label{display:block;margin-bottom:8px;font-size:15px;font-weight:600}
.row{display:flex;gap:10px}
input{flex:1;min-width:0;height:52px;padding:0 16px;border:1.5px solid #1D2340;border-radius:14px;background:#fff;font:inherit;color:#1D2340}
input:focus{outline:3px solid #D2603A;outline-offset:2px}
button{height:52px;padding:0 22px;border:1.5px solid #1D2340;border-radius:14px;background:#3D52A0;color:#fff;font:600 16px 'Instrument Sans',sans-serif;cursor:pointer}
button:hover{background:#33468C}button:disabled{opacity:.7;cursor:progress}
button:focus-visible{outline:3px solid #D2603A;outline-offset:3px}
.hint{display:flex;gap:8px;align-items:flex-start;margin:14px 0 0;font-size:15px;color:#4B5068}
.hint svg{flex:none;margin-top:3px}
.error{min-height:24px;margin:10px 0 0;font-size:15px;font-weight:600;color:#A3472A}
.back{display:inline-block;margin-top:18px;font-size:15px;font-weight:600;color:#1D2340}
.back:hover{color:#3D52A0}
@media (max-width:420px){.lock{padding:28px 20px 24px}.row{flex-direction:column}input{flex:none;width:100%}button{width:100%}}
</style>
</head>
<body>
<main class="lock">
  <p class="no" aria-hidden="true">No. 1</p>
  <p class="eyebrow">Case study · Under NDA</p>
  <h1>Redesigning a national credit-reporting app</h1>
  <p class="lede">This project is confidential, so it's password protected.</p>
  <form id="unlock" autocomplete="off">
    <label for="pw">Password</label>
    <div class="row">
      <input id="pw" type="password" required autofocus aria-describedby="hint error">
      <button type="submit" id="go">Unlock</button>
    </div>
    <p class="hint" id="hint"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.6.5 1.1 1.3 1.1 2.2h5c0-.9.5-1.7 1.1-2.2A6 6 0 0 0 12 3z"/></svg><span>Hint: you'll find the password in my CV.</span></p>
    <p class="error" id="error" role="alert"></p>
  </form>
  <a class="back" href="index.html#work">← All projects</a>
</main>
<script id="payload" type="application/json">${payload}</script>
<script>
(function () {
  var data = JSON.parse(document.getElementById('payload').textContent);
  var form = document.getElementById('unlock'), input = document.getElementById('pw');
  var go = document.getElementById('go'), error = document.getElementById('error');
  var STORE = 'cs1-key';
  function bytes(b64) { var s = atob(b64), u = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; }
  function open(key) {
    return crypto.subtle.decrypt({ name: 'AES-GCM', iv: bytes(data.iv) }, key, bytes(data.ct)).then(function (buf) {
      return new TextDecoder().decode(buf);
    });
  }
  function show(html) {
    document.open(); document.write(html); document.close();
  }
  function count() {
    try { if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path: 'case-study-1-unlocked', title: 'Case study 1 (unlocked)', event: true }); } catch (e) {}
  }
  // Already unlocked in this tab: open straight away.
  try {
    var saved = sessionStorage.getItem(STORE);
    if (saved) {
      crypto.subtle.importKey('raw', bytes(saved), 'AES-GCM', false, ['decrypt'])
        .then(open).then(show).catch(function () { sessionStorage.removeItem(STORE); });
    }
  } catch (e) {}
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    error.textContent = '';
    go.disabled = true; go.textContent = 'Unlocking…';
    var key;
    crypto.subtle.importKey('raw', new TextEncoder().encode(input.value), 'PBKDF2', false, ['deriveKey'])
      .then(function (base) {
        return crypto.subtle.deriveKey({ name: 'PBKDF2', salt: bytes(data.s), iterations: data.it, hash: 'SHA-256' },
          base, { name: 'AES-GCM', length: 256 }, true, ['decrypt']);
      })
      .then(function (k) { key = k; return open(k); })
      .then(function (html) {
        count();
        return crypto.subtle.exportKey('raw', key).then(function (raw) {
          try { sessionStorage.setItem(STORE, btoa(String.fromCharCode.apply(null, new Uint8Array(raw)))); } catch (e) {}
        }).then(function () { show(html); });
      })
      .catch(function () {
        go.disabled = false; go.textContent = 'Unlock';
        error.textContent = "That password didn't work. Please try again.";
        input.select();
      });
  });
})();
</script>
</body>
</html>
`;

writeFileSync(OUT, gate);
console.log(`case-study.html written: ${inlined} private images inlined, ${(gate.length / 1024).toFixed(0)} KB`);
