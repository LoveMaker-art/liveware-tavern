---
name: tavern-worldbooks
description: Manage Tavern worldbooks：设定、触发词、审计与修复。
version: 1.20.6
author: ClawChat Tavern
license: AGPL-3.0-only
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tavern, worldbook, lore, trigger, 世界书, 设定]
    category: creative
---

# Tavern Worldbooks

## When to Use

Use this skill for world facts, locations, rules, organizations, secrets, events, reusable worldbooks, current-world lore, constant entries, trigger entries, trigger-key audits, and conservative lore repair.

Do not use it for character personality, user persona, output-format rules, or runtime code.

## Procedure

1. Decide whether the material belongs in current-world lore or a reusable library worldbook.
2. Use add-lore for natural-language settings and add-worldbook for structured JSON.
3. Choose constant or triggered behavior deliberately.
4. For triggered entries, design specific primary keys and optional secondary or exclusion keys.
5. Run lore-audit after substantial additions.
6. Produce a repair plan before applying mechanical fixes.
7. Verify through the production worldbook API.

Commands:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py add-lore <world> "setting"
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py add-worldbook <jsonfile-or-stdin> --production <world>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-audit <world> [--verbose]
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-fix <world> --plan
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-fix <world> --apply --confirm

Load only the needed reference:

- references/worldbook-authoring.md
- references/lore-audit.md

Before writing state, load the Tavern shared contract.

## Pitfalls

- Do not place character biography, personality, or current status in worldbooks.
- Do not place the user's identity in lore when it belongs to the world-local persona.
- Do not use broad keys that inject an entry in almost every scene.
- Do not duplicate one instruction in both constant lore and a director note.
- Do not add an embedded worldbooks cache back into production JSON.

## Verification

Read /api/production/worldbooks for the target production. Confirm only the intended production-owned files changed, constant entries precede triggered entries in the UI, and trigger entries have usable keys.
