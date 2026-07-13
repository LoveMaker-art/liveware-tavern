---
name: tavern-updater
description: Review, merge, install, and roll back verified Tavern backend-system releases from LoveMaker-art/liveware-tavern. Use when the user asks to check, compare, audit, hot-update, or roll back Tavern server-side application code on a Hermes/ClawChat instance. This skill never updates Tavern frontend, starter content, fixtures, persistent data, or the creative Tavern skill.
---

# Tavern Updater

Use the bundled updater; do not improvise `git pull`, overwrite state, or execute scripts from an unverified branch.

## Commands

```sh
python3 /opt/data/skills/system/tavern-updater/scripts/update.py check
python3 /opt/data/skills/system/tavern-updater/scripts/update.py review
python3 /opt/data/skills/system/tavern-updater/scripts/update.py report --plan <PLAN_ID>
python3 /opt/data/skills/system/tavern-updater/scripts/update.py apply --plan <PLAN_ID> --confirm
python3 /opt/data/skills/system/tavern-updater/scripts/update.py rollback --confirm
```

## Workflow

1. Treat an initial request such as "update Tavern" as permission for inspection only. It does not authorize installation.
2. Run `check` and report installed and latest versions.
3. Run `review`, then `report --plan <PLAN_ID>`. Report the exact backend/updater files, statuses, installed and release hashes, conflicts, baseline warning, and excluded paths.
4. Stop and wait for a new user reply after the report. Do not infer approval from the user's original update request.
5. Never apply a plan with conflicts. Resolve the source changes and run `review` again.
6. Only after the user explicitly approves the reported plan or target version, run `apply --plan <PLAN_ID> --confirm`. The updater rejects plans that were not reported or changed afterward.
7. Report version, plan ID, and health result. Apply failures automatically restore the full pre-update backup.

## Boundaries

- Install only a non-draft, non-prerelease GitHub Release from the configured repository.
- Require both release assets; verify archive and per-file SHA256 before review.
- Never update from `main`, a pull request, an arbitrary URL, or user-provided executable code.
- Never copy, delete, or publish `/opt/data/tavern-state`, `/opt/data/config.yaml`, `.env`, ClawChat databases, sessions, logs, or credentials.
- Preserve local edits with a three-way merge against the last installed baseline. Never guess through a merge conflict.
- Update only backend runtime files and this updater; update the updater last.
- Never manage `runtime/web`, `runtime/assets`, fixtures, starter cards, `/opt/data/tavern-state`, or `/opt/data/skills/creative/tavern`.
- Never combine inspection, reporting, and installation into one unattended action. A user interaction boundary is mandatory between `report` and `apply`.
- Read `references/release-format.md` only when preparing or diagnosing a release.
