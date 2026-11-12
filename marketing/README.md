# Marketing site

Concept landing page only: the pricing, trial, and signup shown in `index.html` and `guide.html` are not implemented in the app.

Static landing pages (`index.html`, `guide.html`) served by nginx in production (see `docs/DEPLOY.md`).

## Assets

Runtime media lives under **`assets/`** as **symlinks** to the design library:

```text
marketing/assets/<file>  →  ../../imgs/<file>
```

Only files referenced by the HTML/JS are linked (logos, app icons, favicon, intro video). Design sources (`.xcf`, badge samples, unused lockups) stay under `imgs/` only.

HTML keeps `href="assets/…"` paths so local open and nginx roots under `marketing/` continue to work.

### Docker

The image copies `imgs/` and `marketing/`. The entrypoint stages marketing onto tmpfs with `cp -aL` so symlinks are resolved into real files for self-contained RAM-backed serving.
