---
name: tavern-cards
description: Manage Tavern character cards：搜索、导入、规范化与审计。
version: 1.20.6
author: ClawChat Tavern
license: AGPL-3.0-only
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tavern, character-card, sillytavern, chub, 角色卡]
    category: creative
---

# Tavern Character Cards

## When to Use

Use this skill for public-card search, PNG or JSON import, original card creation, localization, semantic normalization, quality audit, repair planning, library inspection, or attaching roles to a world.

Do not use it for worldbook trigger design, story compression, or app operations.

## Procedure

1. Identify whether the requested role is existing, imported, or explicitly original.
2. Existing roles: search first, then import the real card.
3. Original roles: author SillyTavern V2 JSON, then use add-original.
4. Audit the imported card before making it a core role.
5. Distinguish structural normalization from semantic normalization:
   - runtime canonicalization guarantees schema shape;
   - semantic fields still require evidence-based review and repair.
6. Apply `references/field-mapping.md`: align source fields with `profile`, `entry`, and `performance`, and route world lore, Persona, current state, and relationships to their separate owners.
7. Attach the reusable card to the intended world, producing a world-local runtime copy.
8. Verify both library source and world-local effective profile.

Commands:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py search "query"
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py add <path-or-url>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py add-original <jsonfile-or-stdin>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py starter
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py attach-card <world> <card>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py card-audit <card>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py card-fix <card> --plan

Load only the needed reference:

- references/card-workflow.md
- references/card-authoring.md
- references/card-localization.md
- references/field-mapping.md

Before writing state, load the Tavern shared contract.

## Pitfalls

- Never treat automatic schema conversion as proof that identity, voice, relationships, or capabilities were semantically extracted.
- Never duplicate one fact across legacy prose and several canonical fields; canonical fields are the effective structured representation.
- Never write a found card directly into a production JSON file.
- Never modify the reusable library card when only one running world's role has changed.
- Never hand-roll PNG or base64 cards when the importer can handle the source.
- If an imported item is really a world concept rather than a person, route it to tavern-worldbooks.

## Verification

Confirm card-audit reports a playable identity, stable voice, usable opening, no unresolved user placeholder, and no worldbook material mixed into character-only fields. Then confirm the intended world contains a separate runtime_cast copy.
