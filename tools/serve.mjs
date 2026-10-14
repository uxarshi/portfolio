// Local preview server for the site, with byte-range support so the intro
// video can seek (Skip jumps to its last frame) and no caching, so a plain
// refresh always shows the latest files.
// Run from anywhere: node "tools/serve.mjs"  →  http://localhost:8765/
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.PORT) || 8765;
const TYPES = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json',
  '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml',
  '.mp4': 'video/mp4', '.m4a': 'audio/mp4',
};

http.createServer((req, res) => {
  let rel = decodeURIComponent(req.url.split('?')[0]);
  if (rel.endsWith('/')) rel += 'index.html';
  const file = path.join(ROOT, rel);
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404);
    return res.end();
  }
  const size = fs.statSync(file).size;
  const head = {
    'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream',
    'Accept-Ranges': 'bytes',
    'Cache-Control': 'no-store',
  };
  const range = /bytes=(\d*)-(\d*)/.exec(req.headers.range || '');
  if (range) {
    const start = Number(range[1]) || 0;
    const end = Math.min(range[2] ? Number(range[2]) : size - 1, size - 1);
    if (start > end) {
      // asked for bytes past the end (e.g. after the file changed size)
      res.writeHead(416, { ...head, 'Content-Range': `bytes */${size}` });
      return res.end();
    }
    res.writeHead(206, { ...head, 'Content-Range': `bytes ${start}-${end}/${size}`, 'Content-Length': end - start + 1 });
    fs.createReadStream(file, { start, end }).pipe(res);
  } else {
    res.writeHead(200, { ...head, 'Content-Length': size });
    fs.createReadStream(file).pipe(res);
  }
}).listen(PORT, () => console.log(`Serving ${ROOT} at http://localhost:${PORT}/`));
