# App icons

| File | Use |
|------|-----|
| `app-logo-192.png` | Web manifest `purpose: "any"` (192×192) |
| `app-logo-512.png` | Web manifest `purpose: "any"` (512×512); also linked as `apple-touch-icon` today |

Source / marketing art also lives under repo `imgs/` and `marketing/assets/`.

## Follow-ups (issue #29)

These assets are **full-bleed opaque** RGBA (no transparent pixels). A proper platform split still needs:

- **Maskable** Android icons with transparent foreground + logo in the adaptive safe zone
- Dedicated **180×180 opaque** `apple-touch-icon` for iOS
- Manifest entries for both `any` and `maskable` purposes

Do not use a transparent maskable foreground as the iOS apple-touch-icon.
