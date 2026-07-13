---
name: tavern-updater
description: Update the installed Tavern Liveware runtime and Tavern skill from verified releases of LoveMaker-art/liveware-tavern. Use when the user asks to check for, install, update, roll back, or explain Tavern application updates on a Hermes/ClawChat instance.
---

# Tavern Updater

Use the bundled updater; do not improvise `git pull`, overwrite state, or execute scripts from an unverified branch.

## Commands

```sh
python3 /opt/data/skills/system/tavern-updater/scripts/update.py check
python3 /opt/data/skills/system/tavern-updater/scripts/update.py apply --confirm
python3 /opt/data/skills/system/tavern-updater/scripts/update.py rollback --confirm
```

## Workflow

1. Run `check` and tell the user the installed and latest release versions.
2. Before `apply`, state that runtime code and the Tavern skill will change while `/opt/data/tavern-state` and credentials remain untouched.
3. Run `apply --confirm` only after the user explicitly approves the update.
4. Report the installed version and health-check result. If apply fails, the updater rolls back automatically.

## Boundaries

- Install only a non-draft, non-prerelease GitHub Release from the configured repository.
- Require both `manifest.json` and `tavern-release.tar.gz`; verify SHA256 before extraction.
- Never update from `main`, a pull request, an arbitrary URL, or user-provided executable code.
- Never copy, delete, or publish `/opt/data/tavern-state`, `/opt/data/config.yaml`, `.env`, ClawChat databases, sessions, logs, or credentials.
- Do not edit the updater itself during an application update.
- Read `references/release-format.md` only when preparing or diagnosing a release.
