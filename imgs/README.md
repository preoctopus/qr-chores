# Design assets

Canonical **brand / marketing art** for QR Chores. Edit here; do not re-copy into other trees.

| Path | Role |
|------|------|
| `logo-*-wide.jpg`, `appicon-new-*.jpg`, `large-favicon.png` | Logos and icons used by the marketing site |
| `chorequest_logo_intro.mp4` | Marketing hero / intro video |
| `applogo-*-sharp.jpg`, `vertical-*.jpg` / `.png` | Alternate lockups (print, stickers, future use) |
| `*.xcf` | Editable GIMP sources |
| `badge_samples.png` | Achievement badge exploration (design-only; not shipped in the Docker image) |

## Consumers

- **`marketing/assets/`** — relative **symlinks** into this directory for the files the static marketing site loads. Do not store duplicate binaries there.
- **`src/qr_chores/static/`** — runtime PWA icons / favicon for the app (derived exports; keep separately so deploys stay small).

When you update a logo used by marketing, replace the file in `imgs/`; the marketing symlinks pick it up automatically.
