---
name: tavern-continuity
description: Diagnose Tavern continuity：压缩、角色状态、提示词与生成。
version: 1.21.6
author: ClawChat Tavern
license: AGPL-3.0-only
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tavern, continuity, ledger, compression, diagnostics, 连续性]
    category: creative
---

# Tavern Continuity

## When to Use

Use this skill when a world becomes inconsistent, characters drift, replies are empty or slow, output formatting changes, compression is questioned, role state is stale, or the user asks what context the model actually received.

This is primarily a read-only diagnostic skill.

## Procedure

1. Read the actual production and latest output before forming a theory.
2. Run diagnose and recall the relevant turns.
3. Inspect runtime logs, effective prompt construction, story ledger checkpoint, runtime_cast checkpoint, model timing, and raw provider response as needed.
4. Separate four owners:
   - character profile: durable identity and behavior;
   - worldbook: world facts and knowledge boundaries;
   - story ledger: scene, events, objects, secrets, and open threads;
   - runtime protocol: language and output form.
5. Report concrete evidence, cause, impact, and the narrowest safe fix.
6. Hand code changes to tavern-updater or the engineering workflow; hand data repair to the owning creative skill.

Commands:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py diagnose <world>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py recall <world> --last 12
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-audit <world>
    curl -fsS http://127.0.0.1:8799/api/health

Load only the needed reference:

- references/diagnostics.md
- references/runtime-continuity.md

Load the Tavern shared contract before any repair.

## Pitfalls

- Do not infer prompt behavior from UI symptoms alone.
- Do not add punctuation or format rules to cards, lore, notes, memory, or history.
- Do not clear history as a first response to one bad reply.
- Do not rebuild dynamic character profiles from the full story.
- Do not treat a successful health endpoint as proof that model generation succeeded.

## Verification

A diagnosis is complete only when it names the failing layer and cites observed state or logs. A repair is complete only after a fresh turn succeeds and the unaffected worlds remain unchanged.
