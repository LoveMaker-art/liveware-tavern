# Tavern

> [!IMPORTANT]
> **Tavern is an open-source, agent-compatible multi-character storytelling system.** The core runtime can run as an independent web application, integrate with an Agent through its HTTP API or command-line tools, or be exposed inside ClawChat through the optional Liveware adapter.
>
> **Tavern 是一个开源、可适配 Agent 的多角色互动故事系统。** 核心运行时可以作为独立 Web 应用运行，也可以通过 HTTP API 或命令行工具接入 Agent；在 ClawChat 中，还可以选择使用 Liveware 适配层作为应用入口。

Tavern is not defined by Liveware. Its core consists of a stateful Python runtime, a browser frontend, and a local JSON data layer. It provides reusable character cards, worldbooks, per-world personas, multi-character conversations, long-story continuity, model selection, text-to-speech, and mobile-friendly reading and interaction.

Liveware is one optional delivery channel for ClawChat. Hermes skills are one first-party Agent integration. Neither is required to run the core Tavern application.

## Architecture

Tavern is divided into three layers:

1. **Core runtime** - `server.py`, the browser frontend in `web/`, model access, and state stored under `TAVERN_STATE_DIR`. This layer can run independently.
2. **Agent integration** - the included Hermes skills let an Agent create worlds, import and normalize cards, manage continuity, operate the application, and update the system. Other Agent frameworks can integrate through the same HTTP API or CLI with their own adapter.
3. **ClawChat integration** - the optional Hook, Liveware registration, and tunnel expose the running application inside ClawChat. They are not part of the core execution requirement.

Agent-compatible does not mean that one framework-specific installer can configure every Agent automatically. The core runtime is reusable; the included skills, Hook, `AGENTS.md`, and updater target the Hermes `/opt/data` layout. Other Agent frameworks should keep the runtime and provide an adapter for their own tool, identity, memory, and lifecycle conventions.

## Deployment Modes

### Standalone Web Application

The standalone runtime needs Python 3, PyYAML, a writable state directory, and an OpenAI-compatible chat-completions endpoint.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r skill/requirements.txt

export TAVERN_STATE_DIR="$PWD/tavern-state"
export TAVERN_MODEL_BASE="https://your-model-provider.example/v1"
export TAVERN_MODEL_KEY="your-api-key"
export TAVERN_MODEL="deepseek-v4-flash"
export TAVERN_HOST="127.0.0.1"

python3 skill/server.py --port 8799
```

Open `http://127.0.0.1:8799/` in a browser. The bundled official text-model identifier is `deepseek-v4-flash`; other OpenAI-compatible models can be added through Tavern's custom-model configuration. ClawChat identity sync, Liveware registration, and Agent-managed workflows are unavailable unless their adapters are installed.

### Hermes Agent Integration

The repository includes a Tavern routing skill and specialist Hermes skills for world construction, continuity, story profiles, operations, and visual customization. The managed release layout places the runtime under `/opt/data/apps/tavern-runtime`, persistent state under `/opt/data/tavern-state`, and skills under `/opt/data/skills`.

The bundled updater performs a compatibility review before replacing managed runtime, frontend, skill, and `AGENTS.md` files. Instance data remains outside the release boundary.

### ClawChat Liveware Integration

On ClawChat, the optional gateway-startup Hook provisions or restores the Liveware applications, starts the same Tavern runtime, binds the tunnel, and registers the Tavern and Story Profile entries. The browser application and its data remain the same core Tavern system used in standalone mode.

## Repository Layout

- `skill/` - Core Tavern runtime, browser frontend, state-free starter content, and compatibility references.
- `creative-skills/` - The Tavern router and specialist Hermes Agent skills.
- `updater-skill/` - Verified in-place updater for the managed Hermes deployment layout.
- `bootstrap/` - Installer that refreshes the updater before a managed update review.
- `scripts/build_release.py` - Builds hash-manifested release assets.
- `tests/` - Runtime, API, import, continuity, security, and frontend tests.

## Data Boundary

Application releases never contain or overwrite instance data. In the managed Hermes layout, user worlds, cards, worldbooks, stories, model choices, app registration, and identity state live under `/opt/data/tavern-state`.

Credentials, ClawChat databases, sessions, logs, `.env` files, and `/opt/data/config.yaml` are not part of this repository or release archives.

In standalone deployments, set `TAVERN_STATE_DIR` to choose the persistent data location.

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

Create a stable GitHub Release tagged `v<VERSION>` and attach every generated asset. Managed Hermes deployments can then update the runtime, atomically replace the official creative-skill directories, remove obsolete managed skill directories, update the updater, and replace the release-managed `AGENTS.md` through one reviewed transaction. Custom skill directories remain untouched. Verified historical baselines allow older managed deployments to complete the same three-way review.

## Bootstrap A Managed Hermes Deployment

Download `tavern-updater-bootstrap.py` and `bootstrap-manifest.json` from the latest stable GitHub Release. Verify the script SHA256 against the manifest, then run it with Python 3. The bootstrap backs up and refreshes only the updater skill, then generates `check`, `review`, and `report` output using the target release's compatibility rules.

During review it does not replace `/opt/data/AGENTS.md`, runtime code, creative skills, frontend code, or user data, and it never applies the Tavern update without explicit approval.

Release assets use these stable names:

```text
https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/tavern-updater-bootstrap.py
https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/install-tavern-updater.sh
https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/bootstrap-manifest.json
```

One-command installation and update for a compatible Hermes `/opt/data` deployment:

```sh
curl -fsSL https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/install-tavern-updater.sh | sh -s -- --apply --confirm
```

Running this command is explicit authorization to install the reported conflict-free update. Merge conflicts or failed health checks stop the process; application failures restore the previous managed files. For a non-Hermes Agent or a different filesystem layout, use the standalone runtime and build a framework-specific adapter instead of running this installer unchanged.

## Install The Updater Skill Manually

For the managed Hermes layout, place `updater-skill/` at:

```text
/opt/data/skills/system/tavern-updater/
```

The Agent can then check and install a verified stable release after explicit user confirmation. Every update review starts through the verified Bootstrap, even when the updater is already installed, so managed-file additions or removals cannot make an older updater reject a newer release format before refreshing itself.

## License

Copyright (c) 2026 ClawChat Tavern contributors.

Current development is licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See [`LICENSE`](LICENSE). Modified network services must offer their corresponding source code to users as required by AGPL section 13.

Releases through `v1.18.1` remain available under the MIT License that accompanied those releases.
