# Tavern Shared Contract

Load this reference before any specialist writes Tavern state.

## Product Boundaries

- A world is the running container for cast, current-world lore, persona, story history, model settings, and local direction.
- Library cards and library worldbooks are reusable templates.
- Adding a library item to a world creates or links world-local state; it must not silently rewrite the reusable source.
- Current-world lore is stored in production-owned worldbook files referenced by production.worldbook_ids.
- Runtime cast profiles are world-local. origin_profile is immutable; profile is the only effective evolving profile.
- The main story curator identity belongs in /opt/data/SOUL.md, never inside a skill.

## State Paths

- Runtime code: /opt/data/apps/tavern-runtime
- Persistent user data: /opt/data/tavern-state
- Shared CLI: /opt/data/skills/creative/tavern/scripts/tavern_cli.py
- System updater: /opt/data/skills/system/tavern-updater

## Mutation Rules

1. Prefer API or CLI operations over direct JSON edits.
2. Run read-only audit, diagnosis, or planning before structural repair.
3. Apply only the scope the user requested.
4. Obtain explicit confirmation before deletion, history rewrite, bulk repair, or any command carrying --apply --confirm.
5. Never overwrite production story history unless the user explicitly requests that exact history edit.
6. Never copy world-local evolved profiles back into library cards unless the user explicitly asks to revise the reusable template.
7. After a write, read the affected API or file and verify the result.

Small UI-equivalent operations explicitly requested by the user, such as attaching a card, setting a persona, or adding one lore entry, may run without a separate planning round.

## Prompt Ownership

Global narration format, punctuation, sentence boundaries, dialogue markup, language selection, and output length belong only to the runtime output protocol in actor.py.

Do not duplicate those rules in:

- character-card system_prompt;
- post_history_instructions;
- worldbook entries;
- director notes;
- story-profile memory;
- story history.

Character cards own character identity and behavior. Worldbooks own world facts. Story state owns current events. Runtime protocol owns output form.

## Security

- Never print or repeat full model or TTS keys.
- Never expose private user state in reports.
- Do not modify SOUL.md, greeting.md, credentials, sessions, or persistent worlds during code maintenance.
- Use tavern-updater for frontend/backend updates; do not improvise update commands in a creative skill.
