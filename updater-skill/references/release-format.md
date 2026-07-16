# Release Format

The updater reads the latest stable GitHub Release from `LoveMaker-art/liveware-tavern`.

Required assets:

- `manifest.json`
- `tavern-release.tar.gz`
- `skill-manifest.json`
- `tavern-skill.tar.gz`

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

The runtime archive contains backend application code and the updater itself:

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

The separately verified schema-2 skill archive contains the router and six specialist workflows:

```text
skills/
  tavern/
  tavern-world/
  tavern-cards/
  tavern-worldbooks/
  tavern-story-profile/
  tavern-continuity/
  tavern-ops/
```

The skill manifest includes an exact `managed_files` set and an exact, allowlisted `obsolete_files` retirement set. Old single-skill references are removed only when they match the trusted installed Release; modified files block review. Known legacy developer tools are backed up before retirement. The updater also replaces only the marked Tavern block in `/opt/data/AGENTS.md` and preserves all surrounding content.

Only the listed runtime files, the seven official frontend code files, and the seven creative-skill allowlists are release assets. Developer smoke tools and host-side installers are not skill assets. `runtime/actor_self.md` is the sole identity-adjacent exception: it is a neutral seed template used only when runtime state is absent. `/opt/data/tavern-state/actor_self.md`, `SOUL.md`, other identity/persona files, frontend backups, images and other assets, starter/fixture content, runtime state, and credentials are never release assets. Every regular archive file must appear in its archive's `managed_files` and `files`. Build with `scripts/build_release.py`, then attach all generated assets to a stable GitHub Release tagged `v<version>`.

Every published version intended to serve as a future merge base must retain these
verified assets. During review, the updater resolves the installed version's tagged
Release and uses its unmodified managed files as the three-way merge base. After a
successful update, the unmodified target Release is cached with version and hash
metadata. Merged instance files are never written into the official baseline cache.
