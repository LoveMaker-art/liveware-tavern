---
name: tavern-world
description: Build Tavern story worlds：推荐、规划、创建与重构。
version: 1.21.5
author: ClawChat Tavern
license: AGPL-3.0-only
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tavern, world, recommendation, planning, 世界, 剧本]
    category: creative
---

# Tavern World Builder

## When to Use

Use this skill when the user wants a world recommendation, a new world from an idea, a prepared opening, a multi-role world, an expanded scenario, or a rebuild from existing material.

Do not use it for deep character-card repair, worldbook trigger repair, long-story diagnosis, or app maintenance.

## Procedure

1. For a recommendation, run recommend before asking unnecessary preference questions.
2. For a loose idea, run plan-world or setup-world without apply.
3. Separate world facts, character facts, persona, and opening scene using the content-modeling reference.
4. Present one compact plan: world premise, cast, lore, persona direction, and opening hook.
5. Create state only after the user confirms the plan.
6. Verify the resulting world, cast, lore groups, persona, and opening.

Commands:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py recommend ["want"] [--external]
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py plan-world "idea"
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py setup-world "idea"
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py setup-world "idea" --apply --confirm
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py new-world --name "name"
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py list

Load only the needed reference:

- references/recommendation-planning.md
- references/content-modeling.md
- references/world-expansion.md
- references/world-rebuild.md
- references/event-driven-update.md

Before writing state, load the Tavern shared contract.

## Pitfalls

- Do not invent an existing or fandom character from memory; hand that step to tavern-cards.
- Do not author or import character fields inside the world workflow; route the card through tavern-cards and its field-mapping contract before attachment.
- Do not place character personality or biography in world lore.
- Do not rewrite an ongoing story opening while rebuilding unless the user explicitly asks.
- Do not create duplicate temporary worlds merely to import cards.

## Verification

Run list and inspect the target world. Confirm its title, cast, worldbook ids, persona scope, and opening match the approved plan without altering other worlds.
