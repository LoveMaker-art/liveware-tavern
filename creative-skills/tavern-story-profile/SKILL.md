---
name: tavern-story-profile
description: Recall stories and manage story preferences（故事档案）.
version: 1.19.9
author: ClawChat Tavern
license: AGPL-3.0-only
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tavern, memory, reflection, preference, 故事档案, 偏好]
    category: creative
---

# Tavern Story Profile

## When to Use

Use this skill when the user asks what the story curator remembers, refers to a previous world, gives durable story preferences, wants a reflection, or asks why a recommendation fits their taste.

Do not store one-off plot facts, role state, model failures, or formatting bugs as user preference.

## Procedure

1. Recall the named world before discussing its history.
2. Use learn for explicit durable preferences.
3. Use reflect-preview before uncertain reflection.
4. Run reflect only when the preview contains reusable preference rather than plot summary.
5. Use card or profile-audit when the user asks to inspect the story profile or recommendation signals.
6. Use note only for an explicit world-local creative direction; never for global format rules.

Commands:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py recall <world> [--last N]
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py learn "preference" --reason "reason"
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py reflect-preview <world>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py reflect <world>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py card
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py profile-audit
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py note <world> "direction"

For detailed criteria, load references/actor-memory.md.
Before writing state, load the Tavern shared contract.

## Pitfalls

- Ordinary chat memory is not the Tavern story profile.
- Story events belong to the story ledger, not actor_self.md.
- Temporary emotion and current relationship state are not durable user preferences.
- A director note is world-local and may be invisible in the frontend; do not use it as hidden corrective prompt storage.

## Verification

After learn or reflect, read the story profile and confirm the new item is durable, specific, attributable to the user, and free of private or unrelated facts.
