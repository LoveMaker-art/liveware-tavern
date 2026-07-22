---
name: tavern-continuity
description: Diagnose and repair Tavern continuity：压缩、剧情账本、角色状态、提示词与生成。Use when a Tavern world becomes inconsistent, story_state or runtime_cast is wrong, object custody/scene facts/secrets/relationships need correction, characters drift, replies are empty or slow, output formatting changes, compression is questioned, or the user asks what context the model received.
version: 1.22.0
author: ClawChat Tavern
license: AGPL-3.0-only
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tavern, continuity, ledger, compression, diagnostics, 连续性]
    category: creative
---

# Tavern Continuity

## Scope

Diagnose first; repair only after an explicit user correction or a diagnosis that identifies `story_state` or `runtime_cast` as the failing layer.

This skill owns:

- continuity diagnosis: compression, prompt construction, generation failures, format drift, stale role state;
- plot-ledger repair: `story_state` scene, facts, objects, secrets, open_threads, timeline, style_notes;
- cast-state repair: `runtime_cast` character/user status, world-local profile, relationships.

Route elsewhere:

- worldbook trigger pollution → `tavern-worldbooks`;
- durable user taste or RP preference → `tavern-story-profile`;
- reusable character-card edits → `tavern-cards`;
- model, restart, health, localization → `tavern-ops`;
- runtime/frontend code changes → updater or engineering workflow.

## Workflow

1. Read the production and latest output before forming a theory.
2. Run `diagnose` and, when needed, `recall`.
3. Separate ownership: character profile, worldbook, story ledger, runtime_cast, runtime protocol.
4. Report evidence, cause, impact, and the narrowest safe fix.
5. For state repair, run `story-fix --plan` or `cast-fix --plan`; apply only after explicit user confirmation with `--apply --confirm`, then verify.

## Commands

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py diagnose <world>
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py recall <world> --last 12
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-audit <world>
python3 /opt/data/skills/creative/tavern-continuity/scripts/tavern_repair.py story-fix <world> "repair request" --plan
python3 /opt/data/skills/creative/tavern-continuity/scripts/tavern_repair.py cast-fix <world> "repair request" --plan
curl -fsS http://127.0.0.1:8799/api/health
```

The compatibility CLI entries `tavern_cli.py story-fix` and `tavern_cli.py cast-fix` delegate to `scripts/tavern_repair.py`.

## References

Load only what the task needs:

- `references/diagnostics.md` for inconsistent worlds, empty/slow replies, role confusion, lore pollution symptoms, and prompt/generation evidence.
- `references/runtime-continuity.md` for compression, story ledger, runtime_cast, message segments, and prompt-construction behavior.
- `references/state-repair.md` before choosing or applying `story-fix`/`cast-fix`.
- `/opt/data/skills/creative/tavern/references/shared-contract.md` before any state write.

## Guardrails

- Never rewrite production story history as a state repair.
- Never edit `origin_profile` or reusable library cards from this skill.
- Never store user taste, output-format rules, or hidden prompts in `story_state`/`runtime_cast`.
- Never apply a repair without first showing the plan and receiving explicit confirmation.
