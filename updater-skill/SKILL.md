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
python3 /opt/data/skills/system/tavern-updater/scripts/update.py apply --plan <PLAN_ID> --confirm
python3 /opt/data/skills/system/tavern-updater/scripts/update.py rollback --confirm
```

## Workflow

1. Run `check` and report installed and latest versions.
2. Run `review`. Summarize backend and updater changes; name locally modified and automatically merged files; list every conflict.
3. Never apply a plan with conflicts. Resolve the source changes and run `review` again.
4. Before `apply`, state the reviewed plan ID and that code will restart briefly while `/opt/data/tavern-state` and credentials remain untouched.
5. Run `apply --plan <PLAN_ID> --confirm` only after explicit approval. A plan is rejected if installed or staged files changed after review.
6. Report version, plan ID, and health result. Apply failures automatically restore the full pre-update backup.

## Boundaries

- Install only a non-draft, non-prerelease GitHub Release from the configured repository.
- Require both release assets; verify archive and per-file SHA256 before review.
- Never update from `main`, a pull request, an arbitrary URL, or user-provided executable code.
- Never copy, delete, or publish `/opt/data/tavern-state`, `/opt/data/config.yaml`, `.env`, ClawChat databases, sessions, logs, or credentials.
- Preserve local edits with a three-way merge against the last installed baseline. Never guess through a merge conflict.
- Update only backend runtime files and this updater; update the updater last.
- Never manage `runtime/web`, `runtime/assets`, fixtures, starter cards, `/opt/data/tavern-state`, or `/opt/data/skills/creative/tavern`.
- Read `references/release-format.md` only when preparing or diagnosing a release.
