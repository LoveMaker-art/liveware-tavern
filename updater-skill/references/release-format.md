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
  actor_self.md
  background_jobs.py
  card_import.py
  continuity_model.py
  memory_cache.py
  model_registry.py
  production_views.py
  request_security.py
  runtime_http.py
  server.py
  state_store.py
  story_ledger.py
  tts_service.py
  .tavern-release-version
  web/
    actor.html
    actor.js
    app.js
    bridge.js
    console.css
    i18n.js
    index.html
    security.js
updater/
  SKILL.md
  scripts/
  references/
  agents/
```

The separately verified skill archive contains the router and six specialist workflows:

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

The schema-3 skill manifest declares `install_mode: exact-directories`, the exact seven official directory names, and the complete file/hash set. The updater backs up every existing official directory and replaces those directories completely; this migrates the former single `tavern` skill without retaining stale files. Skill directories outside the declared seven are never touched. The updater also takes the canonical `AGENTS.md` from the verified updater archive, backs up the installed file, and replaces `/opt/data/AGENTS.md` completely.

Legacy versions without their own GitHub Release may be represented by two additional assets on the latest stable Release: `baseline-v<VERSION>-manifest.json` and `tavern-baseline-v<VERSION>.tar.gz`. The archive contains only the exact allowlisted runtime tree. Its schema-1 manifest binds the version, archive SHA256, complete file list, every file hash, and embedded `.tavern-release-version` marker. It is a merge base only; it is never installed directly and never contains skills, updater code, credentials, identity state, or Tavern user data.

`v1.21.0` expands the managed runtime allowlist with the refactored service modules and `web/security.js`. Installations carrying an older updater must use the verified one-command Bootstrap, which installs the target release's updater before it reviews or applies the expanded runtime manifest. Historical releases and the `v1.14.12` bundled baseline continue to validate against their original 4-backend/7-frontend runtime allowlist.

Only the listed runtime files, the eight official frontend code files, and the exact contents of the seven declared creative-skill directories are release assets. Developer smoke tools and host-side installers are not skill assets. `runtime/actor_self.md` is the sole identity-adjacent exception: it is a neutral seed template used only when runtime state is absent. `/opt/data/tavern-state/actor_self.md`, `SOUL.md`, other identity/persona files, frontend backups, images and other assets, starter/fixture content, runtime state, credentials, and nonofficial skill directories are never release assets. Every regular archive file must appear in its archive's `managed_files` and `files`. Build with `scripts/build_release.py`, then attach all generated assets to a stable GitHub Release tagged `v<version>`.

Every published version intended to serve as a future merge base must retain these
verified assets. During review, the updater resolves the installed version's tagged
Release and uses its unmodified managed files as the three-way merge base. After a
successful update, the unmodified target Release is cached with version and hash
metadata. Merged instance files are never written into the official baseline cache.
The target skill manifest must exactly match the current official allowlist. A verified
historical split-skill manifest may contain a safe subset of that allowlist, but it must
still include every official skill's `SKILL.md` and may never introduce an unknown path.
