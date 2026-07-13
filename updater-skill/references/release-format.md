# Release Format

The updater reads the latest stable GitHub Release from `LoveMaker-art/liveware-tavern`.

Required assets:

- `manifest.json`
- `tavern-release.tar.gz`

Manifest schema:

```json
{
  "schema": 2,
  "version": "1.16.0",
  "archive": "tavern-release.tar.gz",
  "sha256": "<archive SHA256>",
  "files": {
    "runtime/server.py": "<file SHA256>"
  }
}
```

The archive contains three managed top-level areas:

```text
runtime/
  actor.py
  server.py
  card_import.py
  actor_self.md
  web/
skill/
  SKILL.md
  scripts/
  references/
updater/
  SKILL.md
  scripts/
  references/
  agents/
```

Runtime state and credentials are never release assets. Every regular archive file must appear in `files`. Build with `scripts/build_release.py`, then attach both generated files to a stable GitHub Release tagged `v<version>`.
