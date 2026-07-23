---
name: tavern-world-visuals
description: "Design, apply, inspect, or reset a per-world Tavern visual theme, including durable user backgrounds, palette, typography, reading width, top title bar, and right-side world panel（世界视觉、背景、字体、配色、主题）."
version: 1.22.1
author: ClawChat Tavern
license: AGPL-3.0-only
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tavern, world, visual-design, theme, 世界视觉, 主题]
    category: creative
    related_skills: [tavern-world, tavern-ops]
---

# Tavern World Visuals

## Purpose

Give one Tavern world a coherent visual identity without changing its story, cards, worldbooks, prompts, controls, or shared navigation. A world theme covers the story stage, its top title bar, and the right-side world information panel. The left world rail stays neutral so switching worlds remains predictable.

## Workflow

1. Load `skill_view("tavern", "references/shared-contract.md")`.
2. Inspect the exact target world:

       python3 ${HERMES_SKILL_DIR}/scripts/world_theme.py inspect --world "world name or id"

3. Infer one restrained direction from the premise, cast, lore, and opening. Ask a preference question only when the world has no usable visual signal.
4. Load `skill_view("tavern-world-visuals", "references/theme-schema.md")` before writing theme JSON.
5. If the user supplied an image, import it before authoring the theme:

       python3 ${HERMES_SKILL_DIR}/scripts/world_theme.py import-background \
         --world "world name or id" --source "/local/file.png or https://..." \
         --target "desktop|mobile|both" --apply --confirm

   The importer validates the real image bytes, stores them durably, verifies the browser URL, and preserves the world's existing palette while replacing its background. Use the returned `background.url` in later theme JSON edits.
6. Write only supported fields to a temporary JSON file. If the user asked only for ideas, present a compact proposal and stop.
7. Validate the JSON. Validation also probes the background URL and fails if the browser cannot load it:

       python3 ${HERMES_SKILL_DIR}/scripts/world_theme.py validate --json /tmp/world-theme.json

8. Apply through the runtime API:

       python3 ${HERMES_SKILL_DIR}/scripts/world_theme.py apply \
         --world "world name or id" --json /tmp/world-theme.json --confirm

9. Re-run `inspect`. Report the resulting atmosphere briefly; do not narrate commands or claim success before validation and saved-state verification both pass.

To restore the standard appearance:

    python3 ${HERMES_SKILL_DIR}/scripts/world_theme.py clear --world "world name or id" --confirm

## Background Placement

- Persistent filesystem location:

      /opt/data/tavern-state/world-assets/<world-id>/<content-hash>.<ext>

- URL stored in the world theme:

      /world-assets/<world-id>/<content-hash>.<ext>

- Supported imported formats: PNG, JPEG, and WebP.
- Default maximum file size: 12 MiB.
- Never place user images in `/opt/data/apps/tavern-runtime/web/`. That directory is application code and may be replaced by an update.
- Never point a theme at `/opt/data/...`; filesystem paths are not browser URLs.
- A direct durable HTTPS image URL is allowed, but importing it is preferred because it avoids hotlink expiry, authentication, and third-party blocking.

## Design Rules

- Keep the left world rail and the structure of controls unchanged.
- Let `surface`, `text`, `muted`, `border`, `accent`, and `font` carry the same identity into the title bar and right panel.
- Use the background image only on the story stage. The right panel should remain a readable solid surface.
- Use `background_fit: contain` for group portraits or posters that must remain complete. Use `cover` for textures and scenic backdrops that should fill the stage.
- When `contain` leaves unused space, Tavern fills it with a subdued `cover` copy of the same device-specific image. Both layers share the story viewport so their focal points stay aligned; the ambient copy remains low-saturation, dim, and strongly softened instead of competing with the clear artwork. Do not replace it with a solid bar or a full-stage mask.
- Keep desktop and mobile artwork independent when both are available. Import landscape art with `--target desktop` and portrait art with `--target mobile`; use `background_fit_mobile` and `background_position_mobile` for the mobile crop.
- Use `reading_surface: glass` for a local translucent reading plate around text, `solid` for maximum readability, and `plain` for no text plate. Do not restore a full-stage overlay when the user asks only to improve text readability.
- Keep body text readable. Use a translucent `overlay` with background images and target at least 4.5:1 text contrast.
- Use one coherent palette rather than unrelated colors for every surface.
- Do not output or store raw CSS, HTML, JavaScript, font URLs, data URLs, widgets, animations, or executable content.
- Do not put visual instructions into worldbooks, character cards, prompts, or story messages.

## Boundaries

- World content belongs to `tavern-world`.
- Character-card work belongs to `tavern-cards`.
- Runtime or shared UI code belongs to `tavern-ops` or the updater workflow.
- Clearing a theme does not delete imported images or touch story data.
- The helper rejects ambiguous world names, unsupported fields, invalid images, inaccessible assets, and unconfirmed state changes.
