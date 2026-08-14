# Liveware Tavern

> [!IMPORTANT]
> **Nora-specific component, not a universal Agent plugin.** This repository is the source and release channel for the Tavern component built specifically for **Nora**, the author's own Hermes Agent on ClawChat. The installer and updater are intended only for official Nora instances and mirrors derived from the Nora image. They are not supported as a way to add Tavern to an arbitrary Hermes or ClawChat Agent.
>
> **这是诺拉的专属组件，并非通用 Agent 插件。** 本仓库是作者自己的 ClawChat Hermes Agent「诺拉」所使用的酒馆组件及其版本发布渠道。安装器和更新器仅面向官方诺拉实例，以及基于诺拉镜像创建的实例；不能将其理解为给任意 Hermes 或 ClawChat Agent 一键添加酒馆的通用方案。

Liveware Tavern is Nora's stateful, multi-character story application. It combines reusable character cards, worldbooks, per-world personas, long-story memory, model selection, and a mobile-friendly Liveware console.

## Project Scope

Supported use:

- Updating an official Nora instance.
- Updating a mirrored instance originally created from the Nora image.
- Reviewing or adapting the source under the terms of the AGPL license.

Not supported:

- Installing Tavern directly into an unrelated Hermes or ClawChat Agent.
- Treating the included skills, `AGENTS.md`, hooks, runtime, or identity integration as a drop-in general-purpose package.
- Assuming compatibility with another Agent's personality, memory layout, skills, Liveware registration, or existing application data.

The source is public for transparency, version delivery, and licensed adaptation. Integrating it into another Agent requires an independent compatibility review and corresponding code changes; the release installer does not perform that adaptation.

## Repository Layout

- `skill/` - Tavern runtime, frontend source, and state-free offline starter cards.
- `creative-skills/` - The lightweight Tavern router plus five specialist Hermes skills.
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
dist/baseline-v1.14.12-manifest.json
dist/tavern-baseline-v1.14.12.tar.gz
```

Create a stable GitHub Release tagged `v<VERSION>` and attach every generated asset. Nora mirrors can then update the runtime, atomically replace the exact six official creative-skill directories, delete the two obsolete construction-skill directories, update the updater, and replace the complete release-managed `AGENTS.md` through one reviewed transaction. Custom skill directories remain untouched. Verified historical-baseline assets let legacy Nora instances complete the same three-way review when their original version predates this repository's stable Releases.

## Bootstrap A Legacy Instance

Download `tavern-updater-bootstrap.py` and `bootstrap-manifest.json` from the
latest stable GitHub Release. Verify the script SHA256 against the manifest,
then run it with Python 3. The bootstrap backs up and refreshes only the updater
skill, then automatically generates `check`, `review`, and `report` output with
the target release's own compatibility rules. It does not replace
`/opt/data/AGENTS.md`, runtime code, creative skills, frontend code, or user data
during review, and never applies the Tavern update without explicit approval.

Release assets use these stable names:

```text
https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/tavern-updater-bootstrap.py
https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/install-tavern-updater.sh
https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/bootstrap-manifest.json
```

One-command installation and update for an official Nora instance or Nora-derived mirror:

```sh
curl -fsSL https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/install-tavern-updater.sh | sh -s -- --apply --confirm
```

Do not run this command on an unrelated Agent. On a supported Nora instance,
running it is the user's explicit authorization to install the reported
conflict-free update. Merge conflicts or failed health checks stop the process;
application failures restore the previous managed files.

## Install The Updater Skill Manually

Place `updater-skill/` at:

```text
/opt/data/skills/system/tavern-updater/
```

Nora can then check and install a verified stable release after explicit user confirmation. Every update review starts through the verified Bootstrap, even when the updater is already installed, so managed-file additions or removals can never make an older updater reject a newer release format before it has refreshed itself.

## License

Copyright (c) 2026 ClawChat Tavern contributors.

Current development is licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See [`LICENSE`](LICENSE). Modified network services must offer their corresponding source code to users as required by AGPL section 13.

Releases through `v1.18.1` remain available under the MIT License that accompanied those releases.
