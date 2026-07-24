# Event-Driven World Update

Use this reference when a confirmed event changes an existing world's durable
premise, cast, lore, Persona, or opening.

## Procedure

1. Read the current world with `diagnose`, `lore-audit`, and `recall`.
2. Research source material when the event depends on canon. Do not guess.
3. Classify each proposed change by owner:
   - durable world fact or event premise → worldbook;
   - one world's evolving role → runtime cast;
   - reusable character template → library card, only with explicit approval;
   - user's in-world identity → Persona;
   - events already played → story ledger, not static lore.
4. Present one before/after plan and get confirmation.
5. Apply supported events or CLI commands. Never edit state JSON directly.
6. Do not rewrite an ongoing world's opening unless the user explicitly asks.
7. Run `diagnose` and `lore-audit` again.

## Adding Characters

Import a new original or external card into the library without `--new-world`,
then attach it to the existing world. Importing a card must not create an
orphan world.

## Trigger Hygiene

Event entries should use specific scene signals, named incidents, locations, or
relationship states. Generic words such as “学校”, “组织”, or a frequently used
character name make triggered lore effectively constant.

## Verification

Confirm only the intended world changed, the existing story remains intact,
cast and lore are coherent, and no duplicate world was created.
