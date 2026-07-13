# Release Format

The updater reads the latest stable GitHub Release from `LoveMaker-art/liveware-tavern`.

Required assets:

- `manifest.json`
- `tavern-release.tar.gz`

Manifest schema:

```json
{
  "schema": 3,
  "scope": "backend-system",
  "version": "1.16.1",
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
  actor_self.md
  .tavern-release-version
updater/
  SKILL.md
  scripts/
  references/
  agents/
```

Frontend files, starter/fixture assets, the creative Tavern skill, runtime state, and credentials are never release assets. Every regular archive file must appear in both `managed_files` and `files`. Build with `scripts/build_release.py`, then attach both generated files to a stable GitHub Release tagged `v<version>`.
