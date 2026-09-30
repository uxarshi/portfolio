import { defineConfig } from 'vite'
import config from './src/config.js'

const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

// Fills the %PLACEHOLDERS% in index.html from src/config.js, so the title,
// description and social preview tags are edited in one place.
function configHead() {
  return {
    name: 'config-head',
    transformIndexHtml(html) {
      const { site, name, tagline } = config
      const base = site.url ? site.url.replace(/\/?$/, '/') : ''
      const vars = {
        TITLE: site.title,
        DESCRIPTION: site.description,
        NAME: name,
        TAGLINE: tagline,
        URL: base,
        OG_IMAGE: base + site.ogImage,
        THEME: site.themeColor,
      }
      return html.replace(/%(\w+)%/g, (m, k) => (k in vars ? esc(vars[k]) : m))
    },
  }
}

export default defineConfig({
  base: './', // relative paths: works on Netlify, Vercel and GitHub Pages sub-folders
  plugins: [configHead()],
  build: {
    assetsInlineLimit: 0,
    target: 'es2020',
  },
})
