# Tavern Shared Contract

Load this reference before any specialist writes Tavern state.

## Ownership

- Runtime code: `/opt/data/apps/tavern-runtime`
- Persistent instance data: `/opt/data/tavern-state`
- Shared CLI: `/opt/data/skills/creative/tavern/scripts/tavern_cli.py`
- Release updates: `/opt/data/skills/system/tavern-updater`
- Agent identity: `/opt/data/SOUL.md`, never inside a Tavern skill

Library cards and worldbooks are reusable templates. Each world owns its Persona,
story, lore references, direction, and evolving runtime cast. `origin_profile` is
immutable; the world-local `profile` is the effective evolving profile.

## Mutation Contract

1. Use supported CLI or API operations; never edit state JSON directly.
2. Read or audit the target before structural repair.
3. Change only the requested scope.
4. Obtain explicit confirmation before deletion, history rewrite, bulk repair,
   or any `--apply --confirm` command.
5. Never copy world-local evolution back into a reusable card unless explicitly asked.
6. Verify the returned identifier and stored result after every write.

Small UI-equivalent changes explicitly requested by the user, such as attaching
one card or adding one lore entry, do not need a second planning round.

## CLI Results

- Use `--json` whenever supported.
- Treat `ok`, returned identifiers, and verification fields as authoritative.
- Do not infer success from decorative terminal prose.
- Use `doctor --json` for availability or routing uncertainty.

## Prompt Boundary

Global language, punctuation, dialogue markup, formatting, and output length
belong only to the runtime protocol. Do not duplicate them in card prompts,
worldbooks, director notes, story profile, or story history.

## Security

- Never reveal full model or TTS keys or private user state.
- Code maintenance must not alter `SOUL.md`, greeting, credentials, sessions, or
  persistent worlds.
- Use `tavern-updater` for application releases; do not improvise `git pull` or
  overwrite release-managed code from a creative skill.
