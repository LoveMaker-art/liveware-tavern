# Release Format

The updater reads the latest stable GitHub Release from `LoveMaker-art/liveware-tavern`.

Required assets:

- `manifest.json`
- `tavern-release.tar.gz`

Manifest schema:

```json
{
  "schema": 1,
  "version": "1.15.0",
  "archive": "tavern-release.tar.gz",
  "sha256": "<64 lowercase hex characters>"
}
```

The archive must contain exactly these top-level application areas:

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
```

Runtime state and credentials are never release assets. Build releases with the repository's `scripts/build_release.py`, then attach both generated files to a stable GitHub Release whose tag is `v<version>`.
