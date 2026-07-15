---
name: tavern-updater
description: Review, merge, install, and roll back verified Tavern releases from LoveMaker-art/liveware-tavern. Use when the user asks to check, compare, audit, hot-update, or roll back Tavern backend, official frontend code, or the operational Tavern skill on a Hermes/ClawChat instance. This skill updates only explicit allowlists and never updates identity, persona, assets, starter content, fixtures, or persistent data.
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

Legacy instances without this skill may use the official one-command
Bootstrap from the latest stable Release. An explicit
`install-tavern-updater.sh | sh -s -- --apply --confirm` invocation authorizes
that single Bootstrap run to install the skill, report the plan, and apply it.
Conflicts still stop the update and failures still roll back automatically.

## Workflow

1. Treat an initial request such as "update Tavern" as permission for inspection only. It does not authorize installation.
2. Run `check` and report installed and latest versions.
3. Run `review` once, then `report --plan <PLAN_ID>` once. Summarize installed/target versions, changed categories, validation, data exclusions, metadata normalization, and real conflicts. Do not print hashes or exhaustive per-file details unless the user asks for them.
4. Stop and wait for a new user reply after the report. Do not infer approval from the user's original update request.
5. A Tavern Skill version mismatch is informational: the updater normalizes the release-owned `version:` field during three-way merge. Never edit `SKILL.md` merely to align version numbers. If real conflicts remain, report their paths and stop; do not search temporary directories or mutate managed files to force a clean plan.
6. Only after the user explicitly approves the reported plan or target version, run `apply --plan <PLAN_ID> --confirm`. The updater rejects plans that were not reported or changed afterward.
7. Report version, plan ID, and health result. The operational Tavern skill is part of the same update and must never be offered as a separate optional follow-up. Apply failures automatically restore the full pre-update backup.

Use `report --details` only when the user explicitly requests file hashes or conflict diagnosis. The default report is intentionally concise.

## Boundaries

- Install only a non-draft, non-prerelease GitHub Release from the configured repository.
- Require both release assets; verify archive and per-file SHA256 before review.
- Never update from `main`, a pull request, an arbitrary URL, or user-provided executable code.
- Never copy, delete, or publish `/opt/data/tavern-state`, `/opt/data/config.yaml`, `.env`, ClawChat databases, sessions, logs, or credentials.
- Resolve the installed version's official Release as the trusted merge base. A verified cached official baseline may be used only when its version, managed-file list, and hashes all match. Never treat current instance files as an official baseline.
- Preserve local edits with a three-way merge against that trusted official baseline. Store the unmodified target Release, not the merged installation, as the next baseline. If no trusted baseline exists, treat every differing existing file as a conflict instead of overwriting it.
- Update only allowlisted backend files, the seven official `runtime/web` code files, the Tavern skill's `SKILL.md`/references/scripts, and this updater; update the updater last.
- Preserve instance-local edits to managed frontend and backend files with the same three-way review and conflict rules.
- Manage `runtime/actor_self.md` only as the neutral, state-free seed template. Never manage, stage, back up, merge, or overwrite `/opt/data/tavern-state/actor_self.md`, `skill/SOUL.md`, `skill/actor_self.md`, other identity/persona files, runtime or skill assets, frontend backup files, fixtures, starter cards, or any other file under `/opt/data/tavern-state`.
- Apply and roll back individual managed files atomically. Never replace the complete runtime or skill directory.
- Validate all managed Python, Shell, and JavaScript before installation. After restart, verify health, identity, actor-card, production, model, console, and actor surfaces before committing the update.
- Starting the updated service must not run an automatic migration that rewrites existing user state. Data migrations require a separate review and explicit approval outside this skill.
- In the normal Agent workflow, never combine inspection, reporting, and installation: wait between `report` and `apply`. The only exception is a user who directly runs the documented Bootstrap command with both `--apply` and `--confirm`; that explicit command authorizes its single reviewed transaction.
- Serialize review, report, apply, and rollback with the updater lock. After a successful rollback, invalidate the consumed rollback state.
- Read `references/release-format.md` only when preparing or diagnosing a release.
