---
name: tavern-world
description: Build complete Tavern worlds from an idea or existing material, including research, character cards, worldbooks, the user's persona, opening scene, atomic import, and verification.
version: 1.23.1
author: ClawChat Tavern
license: AGPL-3.0-only
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tavern, world, character-card, worldbook, persona, 世界, 角色卡, 世界书]
    category: creative
---

# Tavern World Builder

## When to Use

Use this skill when the user wants to find, recommend, create, import, localize,
expand, rebuild, or repair a playable Tavern world. A complete world may include:

- reusable or original character cards;
- worldbook entries and trigger rules;
- the user's world-local persona;
- an opening scene;
- the final Tavern Liveware entry.

This is one workflow. Do not split character-card and worldbook preparation into
separate user-visible jobs when they serve the same world.

Do not use this skill for app deployment, model configuration, long-story
continuity repair, story-profile memory, or visual theme work.

## Procedure

1. Inspect the request and current Tavern state. Do not create data yet.
2. Load only the references needed for the requested source and content type.
3. If existing material is requested, search before creating. Prefer public,
   directly downloadable JSON/PNG artifacts with visible creator/source
   attribution. Never invent a claimed public or fandom card from memory.
4. Run `inspect-card` on every external artifact before importing it. Accept
   recognized V1/V2/V3 JSON, PNG/APNG, or V3 CHARX only; an HTML page, ordinary
   image, or malformed archive is not a character card.
5. Import through `import-card`. Then run `card-audit` and route character
   facts, shared lore, the user's identity, relationships, and current scene to
   their correct owners. Structural conversion does not replace semantic review.
6. Separate each fact into exactly one owner:
   character profile, worldbook, user persona, opening scene, or live story.
7. Present one compact conversation card containing the world premise, user role,
   cast, core lore, and opening hook. Follow
   `tavern/references/conversation-cards.md`; do not dump JSON or imitate
   unavailable buttons. Ask for confirmation once if the user has not already
   approved.
8. Assemble one world manifest. Preview it with `build-world` without `--apply`.
9. After confirmation, run the same manifest once with
   `--apply --confirm --request-id <stable-id> --json`.
10. Treat `verification.ok: true` as success. On failure, report the error; do not
   create replacement worlds or manually delete state files.
11. Return a compact result and the bare URL from `app-link --app console`. Do not
   expose tool narration between construction steps.

## Commands

Read and research:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py list
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py search "query"
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py inspect-card <file-or-url>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py starter
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py recommend ["want"] [--external]
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py plan-world "idea"
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py card-audit <card>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-audit <world>

Import reusable material without creating a world:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py import-card <file-url-or-chub-path>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py add <chub-path-or-url>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py add-original <card-json>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py add-worldbook <worldbook-json>

Build and verify the complete world:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py build-world <manifest-json>
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py build-world <manifest-json> --apply --confirm --request-id <stable-id> --json
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py verify-world <world> --json
    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py app-link --app console

Use `--new-world` with `add`, `add-original`, or `starter` only when the user
explicitly requests a one-card world. Complete multi-part worlds must use
`build-world`.

## References

Load only what the current task needs:

- `references/complete-world-workflow.md` for the manifest and atomic workflow.
- `references/content-modeling.md` for fact ownership.
- `references/card-workflow.md` and `references/field-mapping.md` for imports.
- `references/card-authoring.md` for original cards.
- `references/card-localization.md` for localization.
- `references/worldbook-authoring.md` for lore and trigger design.
- `references/lore-audit.md` for worldbook repair.
- `references/recommendation-planning.md` for recommendations.
- `references/world-expansion.md` or `references/world-rebuild.md` for existing worlds.
- `references/event-driven-update.md` for confirmed changes to live state.

Before writing state, load the Tavern shared contract.
Before presenting a proposed or completed world in chat, load `tavern/references/conversation-cards.md`.

## Pitfalls

- Never create one temporary world per imported card.
- Never call an external card "compatible" until `inspect-card` succeeds.
- Never use `add-original` for a card found online; preserve its external provenance with `import-card`.
- Never edit production, card, or worldbook JSON files directly.
- Never use cleanup as the normal completion path.
- Never place the same fact in both a character card and a worldbook.
- Never place the user's identity in a character card or worldbook.
- Never modify a reusable library card when only one world's runtime role changed.
- Never claim completion without checking the returned verification object.

## Verification

Confirm all of the following:

- exactly one intended world was created or changed;
- the world is active;
- cast order and character identities match the approved plan;
- worldbook entries and trigger modes match the manifest;
- the user's persona is present and world-local;
- the opening exists;
- unrelated worlds, cards, worldbooks, and stories are unchanged.
