# World Theme Schema

Use this reference only when authoring or reviewing a Tavern world theme.

## Shape

```json
{
  "version": 1,
  "theme": {
    "accent": "#b85c38",
    "background": "#171311",
    "surface": "#211b18",
    "text": "#f4ece5",
    "secondary_text": "#d5c1b4",
    "muted": "#a68d7e",
    "border": "#493a32",
    "user_message": "#332823",
    "overlay": "#120c08aa",
    "font": "literary",
    "narration_font": "classic",
    "content_width": 560,
    "background_position": "center",
    "background_fit": "contain",
    "background_position_mobile": "center",
    "background_fit_mobile": "cover",
    "reading_surface": "glass"
  },
  "assets": {
    "background_desktop": "/world-assets/prod_example/desktop.webp",
    "background_mobile": "/world-assets/prod_example/mobile.webp"
  }
}
```

Every field is optional. Omit fields that should inherit the standard Tavern appearance.

## Fields

| Field | Accepted value | Visible effect |
| --- | --- | --- |
| `accent` | Hex color | Send button, focus, and story controls |
| `background` | Hex color | Story reading area and input background |
| `surface` | Hex color | Composer, top title bar, and right-side panel surface |
| `text` | Hex color | Character response, title, and right-panel primary text |
| `secondary_text` | Hex color | User message text |
| `muted` | Hex color | Narration and subdued title/panel text |
| `border` | Hex color | Stage, composer, title bar, and right-panel boundaries |
| `user_message` | Hex color | User message surface |
| `overlay` | Hex color, preferably `#RRGGBBAA` | Readability layer over the background image |
| `font` | `default`, `literary`, `modern`, `classic`, `typewriter` | Story, input, title bar, and right-panel body font |
| `narration_font` | Same presets | Narration font |
| `content_width` | Integer from 360 to 760 | Maximum reading-column width in pixels |
| `background_position` | `center`, `top`, `bottom`, `left`, `right`, or corner pair | Background crop focus |
| `background_fit` | `cover` or `contain` | `cover` fills and crops; `contain` shows the complete image without stretching |
| `background_position_mobile` | Same values as `background_position` | Mobile crop focus |
| `background_fit_mobile` | `cover` or `contain` | Mobile-only fitting mode |
| `reading_surface` | `plain`, `glass`, or `solid` | Optional local reading surface behind message text; it never covers the whole background |
| `assets.background_desktop` | `/world-assets/...` or HTTPS URL | Desktop/tablet story background |
| `assets.background_mobile` | `/world-assets/...` or HTTPS URL | Mobile story background |
| `assets.background` | Same values | Backward-compatible fallback when separate images are absent |

Hex colors accept 3, 4, 6, or 8 digits. Use 8 digits for alpha; `#00000080` is black at roughly 50% opacity.

## Composition

- Dark image: use light `text`, softer `muted`, and a dark translucent `overlay`.
- Character group or poster: use `contain` so people are not cropped; the world background color fills any unused space.
- Texture or scenic backdrop: use `cover` so the stage is filled edge to edge.
- Use `glass` when the image should stay visible around readable text. Use `solid` only for very busy backgrounds; use `plain` when the image itself provides enough contrast.
- Light image: use dark text and a pale translucent overlay such as `#fffdf8cc`.
- Dialogue-heavy world: use 500-620 px width and a quiet user-message surface.
- Long-form literary world: use `literary` or `classic`; keep body size and controls unchanged.
- Technical or archival world: `modern` or `typewriter` may be suitable, but do not use typewriter for long dense passages unless requested.

Check text against the effective background. Aim for at least 4.5:1 contrast for body text and do not rely on the image itself to provide contrast.

## Persistent Backgrounds

Use `import-background` for user files and remote images. It writes immutable, content-addressed assets under:

```text
/opt/data/tavern-state/world-assets/<world-id>/<content-hash>.<ext>
```

The corresponding browser URL is:

```text
/world-assets/<world-id>/<content-hash>.<ext>
```

Do not manually copy images into the runtime `web/` directory. Theme validation performs an HTTP probe, so an inaccessible or incorrectly placed image fails before the world is changed.

## Unsupported

Do not include arbitrary CSS, HTML, JavaScript, font URLs, `data:` URLs, layout templates, widgets, animations, or control definitions. Unknown and invalid fields are rejected by the helper before any state change.
