# Arshi Shayesta: portfolio (static HTML export)

Plain HTML, CSS and a little vanilla JS. No build step and no dependencies. Open `index.html` in a browser.

## Files

| File | What it is |
|---|---|
| `index.html` | Homepage: hero, Selected work (4 project cards), About me, footer. Responsive down to phone width. |
| `case-study.html` | Case study No. 1, "Redesigning a national credit-reporting app": 11 sections with a sticky tab bar. |
| `assets/` | All images, referenced with relative paths (`assets/...`). |

## How the pages are built

- Styles are mostly inline. Each page's `<head>` has one `<style>` block with hover/focus states and the responsive `@media` rules (class names start with `hp-`/`wk-` on the homepage and `cs-` in the case study).
- Fonts load from Google Fonts: Bricolage Grotesque (headings), Instrument Sans (body), Caveat (handwritten notes), plus Roboto and Tajawal for the app's type samples.
- Scripts are at the bottom of each page:
  - `index.html`: sound toggle (visual state only) and the mobile "show introduction" handle on the hero card.
  - `case-study.html`: highlights the tab for the section in view.
- Project cards 2 to 4 on the homepage are still placeholders (`[Project image]`, links to `#case-2` and so on).

## Theme

Page `#F6ECDA` · paper `#FBF4E6` · ink `#1D2340` · muted `#4B5068` · accent `#3D52A0` · rust `#A3472A`.
Tints: sky `#C4D7F1`, peach `#F4CDB0`, lavender `#D3CFEE`, sage `#D3E2BE`. The client app's own colours: navy `#003972`, gold `#EAA203`.

## NDA rules for the case study (keep these)

- Never name the client or product, and don't show its logo.
- No bank names, currency, or other cues that identify the country.
- Credit-score band names stay hidden or blurred.
- All data in images is dummy, and sensitive fields are blurred.
