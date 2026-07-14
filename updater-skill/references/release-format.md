# Release Format

The updater reads the latest stable GitHub Release from `LoveMaker-art/liveware-tavern`.

Required assets:

- `manifest.json`
- `tavern-release.tar.gz`

Legacy-instance bootstrap assets:

- `tavern-updater-bootstrap.py`
- `install-tavern-updater.sh`
- `bootstrap-manifest.json`

The updater ignores the bootstrap assets. They exist only to install this
updater skill on older instances that predate it.

Manifest schema:

```json
{
  "schema": 4,
  "scope": "tavern-system",
  "version": "1.18.1",
  "archive": "tavern-release.tar.gz",
  "sha256": "<archive SHA256>",
  "managed_files": ["runtime/server.py"],
  "files": {
    "runtime/server.py": "<file SHA256>"
  }
}
```

The archive contains only backend application code and the updater itself:

```text
runtime/
  actor.py
  server.py
  card_import.py
  .tavern-release-version
  web/
    actor.html
    actor.js
    app.js
    bridge.js
    console.css
    i18n.js
    index.html
updater/
  SKILL.md
  scripts/
  references/
  agents/
```

Only the seven listed official frontend code files are release assets. Identity/persona files such as `actor_self.md`, frontend backups, images and other assets, starter/fixture content, the creative Tavern skill, runtime state, and credentials are never release assets. Every regular archive file must appear in both `managed_files` and `files`. Build with `scripts/build_release.py`, then attach both generated files to a stable GitHub Release tagged `v<version>`.
