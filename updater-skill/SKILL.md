---
name: tavern-updater
description: Review, install, and roll back verified Tavern releases from LoveMaker-art/liveware-tavern. Use when the user asks to check, compare, audit, hot-update, or roll back Tavern backend, official frontend code, the exact six-skill Tavern suite, or the release-managed AGENTS.md on a Hermes/ClawChat instance. This skill replaces only official skill directories and explicit code allowlists; it never updates identity, persona, assets, starter content, fixtures, custom skills, or persistent data.
---

# Tavern Updater

Use the bundled updater; do not improvise `git pull`, overwrite state, or execute scripts from an unverified branch.

## Canonical entrypoint

Every check, review, or update request must begin by running the verified latest
Bootstrap without `--apply`:

```sh
curl -fsSL https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/install-tavern-updater.sh | sh
```

This is updater self-refresh, not Tavern installation. It verifies the latest
stable Release, backs up and refreshes only `tavern-updater`, then uses that
exact updater to produce `check`, `review`, and `report` in one run. Do not call
an already-installed updater's `review` against a newer manifest first. If a
legacy updater reports an allowlist, schema, or managed-file mismatch,
automatically use this canonical entrypoint and continue the review; do not ask
the user to choose whether Bootstrap is needed.

The Bootstrap output includes the reported `plan_id`. Show one concise report
and wait for explicit approval. It must not replace `AGENTS.md`, runtime code,
creative skills, frontend code, or user data during this review phase.

## Apply and rollback

```sh
python3 /opt/data/skills/system/tavern-updater/scripts/update.py apply --plan <PLAN_ID> --confirm
python3 /opt/data/skills/system/tavern-updater/scripts/update.py rollback --confirm
```

All installed versions use the same Bootstrap-first review path, including
instances without this skill and instances whose older updater cannot parse a
new release manifest. An explicit
`install-tavern-updater.sh | sh -s -- --apply --confirm` invocation authorizes
that single Bootstrap run to install the skill, report the plan, and apply it.
Conflicts still stop the update and failures still roll back automatically.
This entrypoint refreshes the updater before it reviews the target runtime
allowlist and exact-directory skill manifest.

## Workflow

1. Treat an initial request such as "update Tavern" as permission for inspection only. It does not authorize installation.
2. Run the canonical Bootstrap entrypoint once. It refreshes the updater and returns `check`, `review`, and `report` output from the current release format.
3. Summarize installed/target versions, changed categories, validation, data exclusions, metadata normalization, and real conflicts. Do not print hashes or exhaustive per-file details unless the user asks for them.
4. Stop and wait for a new user reply after the report. Do not infer approval from the user's original update request.
5. The six official Tavern skill directories are release-owned and replaced exactly after full backup. Delete obsolete `tavern-cards` and `tavern-worldbooks` directories during migration; never leave them installed or registered. Their transaction copy exists only for automatic rollback if the update fails. Do not merge local files into official directories. Runtime or updater code conflicts still stop the plan; report their paths and do not mutate managed files to force a clean result.
6. Only after the user explicitly approves the reported plan or target version, run `apply --plan <PLAN_ID> --confirm`. The updater rejects plans that were not reported or changed afterward.
7. Report version, plan ID, skill-registration validation, and health result. All six Tavern skills and the complete release-managed `AGENTS.md` are part of the same update and must never be offered as separate optional follow-ups. Apply failures automatically restore the full pre-update backup.

Use `report --details` only when the user explicitly requests file hashes or conflict diagnosis. The default report is intentionally concise.

During a version upgrade, the updater may automatically migrate exact known fingerprints from
transitional pre-release deployments and may ignore query-string-only changes to local JS/CSS
references in `runtime/web/index.html`. Report these as compatibility migrations or metadata
normalization, not conflicts. Unknown local code remains subject to three-way merge review.

## Boundaries

- Install only a non-draft, non-prerelease GitHub Release from the configured repository.
- Require both release assets; verify archive and per-file SHA256 before review.
- Always refresh the updater through the verified latest Bootstrap before release review. Updater age is not a reliable compatibility signal because a later release may add or retire managed files.
- Never update from `main`, a pull request, an arbitrary URL, or user-provided executable code.
- Never copy, delete, or publish `/opt/data/tavern-state`, `/opt/data/config.yaml`, `.env`, ClawChat databases, sessions, logs, or credentials.
- Resolve the installed version's official Release as the trusted merge base. A verified cached official baseline may be used only when its version, managed-file list, and hashes all match. Never treat current instance files as an official baseline.
- If the installed version predates its own GitHub Release, use only the matching hash-verified historical baseline bundled with the latest stable Release. Never infer a baseline from the current instance or from an arbitrary branch.
- Preserve local frontend and backend edits with a three-way merge against the trusted official baseline. Store the unmodified target Release, not the merged installation, as the next baseline. If no trusted baseline exists, differing runtime or updater files are conflicts.
- Accept an automatic compatibility migration only for an exact updater-owned fingerprint and its declared minimum target version. Never generalize a recognized migration to unknown local content.
- Update only allowlisted backend modules, the eight official `runtime/web` code files, the six creative skills, the complete release-managed `/opt/data/AGENTS.md`, and this updater; update the updater last.
- Back up the complete existing official skill directories, then replace exactly `tavern`, `tavern-world`, `tavern-story-profile`, `tavern-continuity`, `tavern-ops`, and `tavern-world-visuals`. Delete obsolete `tavern-cards` and `tavern-worldbooks`; do not install or register them. Their transaction copy may be used only for automatic rollback. Never touch any other skill directory.
- Preserve instance-local edits to managed frontend and backend files with the same three-way review and conflict rules.
- Manage `runtime/actor_self.md` only as the neutral, state-free seed template. Never manage, stage, back up, merge, or overwrite `/opt/data/tavern-state/actor_self.md`, `skill/SOUL.md`, `skill/actor_self.md`, other identity/persona files, runtime or skill assets, frontend backup files, fixtures, starter cards, or any other file under `/opt/data/tavern-state`.
- Apply and roll back runtime files individually. Replace each official skill directory and `/opt/data/AGENTS.md` from complete verified release artifacts after full backup. Never replace the creative-skill root.
- Validate all managed Python, Shell, and JavaScript before installation. After installation, require all six skills to be structurally valid and registered by Hermes; after restart, verify health, identity, actor-card, production, model, console, and actor surfaces before committing the update.
- Starting the updated service must not run an automatic migration that rewrites existing user state. Data migrations require a separate review and explicit approval outside this skill.
- In the normal Agent workflow, Bootstrap may combine updater self-refresh, inspection, and reporting, but never Tavern installation: wait between `report` and `apply`. The only exception is a user who directly runs the documented Bootstrap command with both `--apply` and `--confirm`; that explicit command authorizes its single reviewed transaction.
- Serialize review, report, apply, and rollback with the updater lock. After a successful rollback, invalidate the consumed rollback state.
- Read `references/release-format.md` only when preparing or diagnosing a release.
