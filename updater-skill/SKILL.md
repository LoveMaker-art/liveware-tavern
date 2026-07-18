---
name: tavern-updater
description: Review, install, and roll back verified Tavern releases from LoveMaker-art/liveware-tavern. Use when the user asks to check, compare, audit, hot-update, or roll back Tavern backend, official frontend code, the exact seven-skill Tavern suite, or the release-managed AGENTS.md on a Hermes/ClawChat instance. This skill replaces only official skill directories and explicit code allowlists; it never updates identity, persona, assets, starter content, fixtures, custom skills, or persistent data.
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

Legacy instances without this skill, and installations whose updater is older
than `v1.21.0`, must use the official one-command Bootstrap from the latest
stable Release. An explicit
`install-tavern-updater.sh | sh -s -- --apply --confirm` invocation authorizes
that single Bootstrap run to install the skill, report the plan, and apply it.
Conflicts still stop the update and failures still roll back automatically.
This entrypoint installs the latest updater before it reviews the expanded
runtime allowlist and exact-directory skill manifest; do not run an older
updater's `review` or `apply` directly against those manifests.

## Workflow

1. Treat an initial request such as "update Tavern" as permission for inspection only. It does not authorize installation.
2. Run `check` and report installed and latest versions.
3. Run `review` once, then `report --plan <PLAN_ID>` once. Summarize installed/target versions, changed categories, validation, data exclusions, metadata normalization, and real conflicts. Do not print hashes or exhaustive per-file details unless the user asks for them.
4. Stop and wait for a new user reply after the report. Do not infer approval from the user's original update request.
5. The seven official Tavern skill directories are release-owned and replaced exactly after full backup. Do not merge local files into them. Runtime or updater code conflicts still stop the plan; report their paths and do not mutate managed files to force a clean result.
6. Only after the user explicitly approves the reported plan or target version, run `apply --plan <PLAN_ID> --confirm`. The updater rejects plans that were not reported or changed afterward.
7. Report version, plan ID, skill-registration validation, and health result. All seven Tavern skills and the complete release-managed `AGENTS.md` are part of the same update and must never be offered as separate optional follow-ups. Apply failures automatically restore the full pre-update backup.

Use `report --details` only when the user explicitly requests file hashes or conflict diagnosis. The default report is intentionally concise.

During a version upgrade, the updater may automatically migrate exact known fingerprints from
transitional pre-release deployments and may ignore query-string-only changes to local JS/CSS
references in `runtime/web/index.html`. Report these as compatibility migrations or metadata
normalization, not conflicts. Unknown local code remains subject to three-way merge review.

## Boundaries

- Install only a non-draft, non-prerelease GitHub Release from the configured repository.
- Require both release assets; verify archive and per-file SHA256 before review.
- For the `v1.21.0` runtime-module allowlist expansion, installations with an older updater must use the documented one-command Bootstrap so the new updater is installed before release review.
- Never update from `main`, a pull request, an arbitrary URL, or user-provided executable code.
- Never copy, delete, or publish `/opt/data/tavern-state`, `/opt/data/config.yaml`, `.env`, ClawChat databases, sessions, logs, or credentials.
- Resolve the installed version's official Release as the trusted merge base. A verified cached official baseline may be used only when its version, managed-file list, and hashes all match. Never treat current instance files as an official baseline.
- If the installed version predates its own GitHub Release, use only the matching hash-verified historical baseline bundled with the latest stable Release. Never infer a baseline from the current instance or from an arbitrary branch.
- Preserve local frontend and backend edits with a three-way merge against the trusted official baseline. Store the unmodified target Release, not the merged installation, as the next baseline. If no trusted baseline exists, differing runtime or updater files are conflicts.
- Accept an automatic compatibility migration only for an exact updater-owned fingerprint and its declared minimum target version. Never generalize a recognized migration to unknown local content.
- Update only allowlisted backend modules, the eight official `runtime/web` code files, the seven creative skills, the complete release-managed `/opt/data/AGENTS.md`, and this updater; update the updater last.
- Back up the complete existing official skill directories, then replace exactly `tavern`, `tavern-world`, `tavern-cards`, `tavern-worldbooks`, `tavern-story-profile`, `tavern-continuity`, and `tavern-ops`. This cleanly migrates the former single `tavern` skill and removes every stale file inside official directories. Never touch any other skill directory.
- Preserve instance-local edits to managed frontend and backend files with the same three-way review and conflict rules.
- Manage `runtime/actor_self.md` only as the neutral, state-free seed template. Never manage, stage, back up, merge, or overwrite `/opt/data/tavern-state/actor_self.md`, `skill/SOUL.md`, `skill/actor_self.md`, other identity/persona files, runtime or skill assets, frontend backup files, fixtures, starter cards, or any other file under `/opt/data/tavern-state`.
- Apply and roll back runtime files individually. Replace each official skill directory and `/opt/data/AGENTS.md` from complete verified release artifacts after full backup. Never replace the creative-skill root.
- Validate all managed Python, Shell, and JavaScript before installation. After installation, require all seven skills to be structurally valid and registered by Hermes; after restart, verify health, identity, actor-card, production, model, console, and actor surfaces before committing the update.
- Starting the updated service must not run an automatic migration that rewrites existing user state. Data migrations require a separate review and explicit approval outside this skill.
- In the normal Agent workflow, never combine inspection, reporting, and installation: wait between `report` and `apply`. The only exception is a user who directly runs the documented Bootstrap command with both `--apply` and `--confirm`; that explicit command authorizes its single reviewed transaction.
- Serialize review, report, apply, and rollback with the updater lock. After a successful rollback, invalidate the consumed rollback state.
- Read `references/release-format.md` only when preparing or diagnosing a release.
