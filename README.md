# Liveware Tavern

Liveware Tavern is a stateful, multi-character story application for Hermes Agent and ClawChat. It combines reusable character cards, worldbooks, per-world personas, long-story memory, model selection, and a mobile-friendly Liveware console.

## Repository Layout

- `skill/` - Tavern runtime, frontend, Hermes skill, operational scripts, references, and state-free starter assets.
- `updater-skill/` - Independent Hermes skill for verified in-place updates from GitHub Releases.
- `bootstrap/` - One-time installer for legacy instances that do not have `tavern-updater` yet.
- `scripts/build_release.py` - Builds the signed-by-hash release assets consumed by the updater.

## Data Boundary

Application releases never contain or overwrite instance data. User worlds, cards, worldbooks, stories, model choices, app registration, and identity state live under `/opt/data/tavern-state` on each instance.

Credentials, ClawChat databases, sessions, logs, `.env` files, and `/opt/data/config.yaml` are not part of this repository or release archives.

## Build A Release

```sh
python3 scripts/build_release.py
```

This creates:

```text
dist/manifest.json
dist/tavern-release.tar.gz
dist/skill-manifest.json
dist/tavern-skill.tar.gz
dist/tavern-updater-bootstrap.py
dist/install-tavern-updater.sh
dist/bootstrap-manifest.json
```

Create a stable GitHub Release tagged `v<SKILL.md version>` and attach both files. Mirrored instances can then update through `tavern-updater` without rebuilding the image.

## Bootstrap A Legacy Instance

Download `tavern-updater-bootstrap.py` and `bootstrap-manifest.json` from the
latest stable GitHub Release. Verify the script SHA256 against the manifest,
then run it with Python 3. The bootstrap installs only the updater skill,
replaces or appends the marked Tavern update section in `/opt/data/AGENTS.md`,
and automatically generates `check`, `review`, and `report` output. It never
applies the Tavern update without a new explicit user approval.

Release assets use these stable names:

```text
https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/tavern-updater-bootstrap.py
https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/install-tavern-updater.sh
https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/bootstrap-manifest.json
```

One-command installation and update:

```sh
curl -fsSL https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/install-tavern-updater.sh | sh -s -- --apply --confirm
```

Running this command is the user's explicit authorization to install the
reported conflict-free update. Merge conflicts or failed health checks stop
the process; application failures restore the previous managed files.

## Install The Updater Skill Manually

Place `updater-skill/` at:

```text
/opt/data/skills/system/tavern-updater/
```

The Agent can then check and install a verified stable release after explicit user confirmation.

## License

Copyright (c) 2026 ClawChat Tavern contributors.

Current development is licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See [`LICENSE`](LICENSE). Modified network services must offer their corresponding source code to users as required by AGPL section 13.

Releases through `v1.18.1` remain available under the MIT License that accompanied those releases.
