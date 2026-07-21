---
name: tavern-story-profile
description: Recall stories, maintain the structured story profile, and synchronize model-aggregated taste and bounded plot-ledger memory into Hermes.
version: 1.21.7
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

Use this skill when the user asks what the story curator remembers, refers to a previous world, gives durable story preferences, wants a reflection, asks why a recommendation fits their taste, or wants those preferences reflected in ordinary conversation.

Do not store one-off plot facts, role state, model failures, or formatting bugs as user preference.

## Procedure

1. Recall the named world before discussing its history.
2. Use learn for explicit durable preferences.
3. Use reflect-preview before uncertain reflection.
4. Run reflect only when the preview contains reusable preference rather than plot summary.
5. Use card or profile-audit when the user asks to inspect the story profile or recommendation signals.
6. Use note only for an explicit world-local creative direction; never for global format rules.
7. Treat `/opt/data/tavern-state/story_profile.json` as the only active story-profile source. `actor_self.md` is a rendered compatibility view.
8. Use `memory-preview` before a manual profile sync. Never append Tavern material directly to `USER.md` or `MEMORY.md`.
9. The compact taste profile is model-aggregated from confirmed reflection notes. Runtime code may validate and render it, but must not derive taste through keyword rules.
10. Concrete shared events come from each world's successful model-generated `story_state`; never infer plot memory from preference notes.

Commands:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py recall <world> [--last N]
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py learn "preference" --reason "reason"
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py reflect-preview <world>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py reflect <world>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py card
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py profile-audit
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py note <world> "direction"
    python3 /opt/data/skills/creative/tavern-story-profile/scripts/profile_memory.py audit
    python3 /opt/data/skills/creative/tavern-story-profile/scripts/profile_memory.py memory-preview
    python3 /opt/data/skills/creative/tavern-story-profile/scripts/profile_memory.py memory-sync
    python3 /opt/data/skills/creative/tavern-story-profile/scripts/profile_memory.py refresh
    python3 /opt/data/skills/creative/tavern-story-profile/scripts/profile_memory.py confirm <preference_id>
    python3 /opt/data/skills/creative/tavern-story-profile/scripts/profile_memory.py reject <preference_id>
    python3 /opt/data/skills/creative/tavern-story-profile/scripts/profile_memory.py edit <preference_id> "new text" [--scope tavern|ruotang_chat|both]
    python3 /opt/data/skills/creative/tavern-story-profile/scripts/profile_memory.py lock <preference_id> [--off]

For detailed criteria, load references/actor-memory.md.
Before writing state, load the Tavern shared contract.

## Pitfalls

- Ordinary chat memory is not the Tavern story profile.
- Story preferences may inform recommendations and the story curator's understanding of how the user likes to play.
- Story events belong to the story ledger, not actor_self.md.
- Temporary emotion and current relationship state are not durable user preferences.
- A director note is world-local and may be invisible in the frontend; do not use it as hidden corrective prompt storage.

## Verification

After learn or reflect, run `profile_memory.py audit`. Confirm the new item is durable, specific, attributable to the user, and free of private or unrelated facts. `USER.md` receives the bounded model-aggregated taste profile; `MEMORY.md` receives bounded concrete events from successful model-generated story ledgers. Both fixed marker blocks are replaced atomically and never appended without limit.
