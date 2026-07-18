---
name: tavern
description: Route Tavern requests to one specialist workflow（酒馆路由）.
version: 1.21.1
author: ClawChat Tavern
license: AGPL-3.0-only
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tavern, 酒馆, routing, story-world]
    category: creative
---

# Tavern Router

## When to Use

Use this skill only when a Tavern request is broad, ambiguous, spans several domains, or explicitly asks which Tavern capability should handle the work.

If the request is already specific, load the matching specialist directly.

## Procedure

1. Classify the request by its primary outcome.
2. Load exactly one specialist with skill_view.
3. Load a second specialist only when the task truly crosses ownership boundaries.
4. Let the specialist choose its own references and commands.

Routing map:

| User outcome | Specialist |
| --- | --- |
| Recommend, plan, create, expand, or rebuild a world | tavern-world |
| Find, import, create, normalize, audit, or attach a character card | tavern-cards |
| Create, import, audit, or repair lore and worldbooks | tavern-worldbooks |
| Recall a story or manage durable story preferences | tavern-story-profile |
| Diagnose continuity, compression, cast state, prompts, or generation | tavern-continuity |
| Configure models, restart, verify, or localize Liveware | tavern-ops |
| Review or install Tavern frontend/backend updates | tavern-updater |

Shared command entrypoint:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py <command>

All state-changing specialists must first load:

    skill_view("tavern", "references/shared-contract.md")

## Pitfalls

- Do not load every Tavern specialist for one request. That defeats Hermes progressive disclosure.
- Do not turn this router back into a product manual. Detailed procedures belong to specialist skills.
- Do not create a bundle containing all Tavern skills. Bundles load every member at once.
- Do not use tavern-updater for story data, or creative skills for runtime code updates.

## Verification

Confirm the skill index exposes these independent names:

    tavern
    tavern-world
    tavern-cards
    tavern-worldbooks
    tavern-story-profile
    tavern-continuity
    tavern-ops

Test natural-language routing with one request from each row of the routing map. Only the selected specialist should be loaded.
