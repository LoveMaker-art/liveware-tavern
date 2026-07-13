# Tavern Content Modeling

Use this reference before creating, importing, cleaning, or restructuring a tavern world. It defines where each kind of information belongs so Ruotang does not mix role cards, worldbooks, persona, memory, and runtime instructions.

## Core Model

- **World / Production**: the container for one playable story. It owns cast membership, attached lore, story history, scene state, story state, and world-specific direction.
- **Character Card**: one character's identity, voice, motivations, behavior, relationship defaults, first message, examples, and optional character-local instructions (`system_prompt`, `post_history_instructions`).
- **Worldbook / Lore**: facts about the world, places, factions, systems, secrets, objects, history, or public knowledge that should be conditionally injected.
- **Persona / 我的角色**: the user's in-story identity. This is not the user's real-life profile and not a world fact unless other characters know it.
- **Story History**: exact turns that happened in the current world. Preserve it as source-of-truth transcript.
- **Story State**: compressed structured ledger of what has happened, current goals, relationships, secrets, objects, and character state.
- **Scene State**: current lens: location, time, mood, present characters, nearby characters, hidden characters, and open threads.
- **Author Note / Director Note**: world-specific writing direction, tone, pacing, diction, relationship tension, or temporary constraints.
- **System Output Protocol**: internal renderer format such as narration/action markup and dialogue punctuation. This is built into runtime and must not be user-editable.

## Placement Rules

Put information in exactly one primary home:

| Information | Primary Home | Notes |
| --- | --- | --- |
| A character's personality, speech, habits, goals | Character card | Do not duplicate in global lore unless many characters need a short public fact. |
| Character-specific identity instruction, voice anchoring | `system_prompt` (card field) | Weak positional priority (buried in long system message). Use for identity/voice/knowledge boundaries; most content can live in `personality` instead. |
| Per-character last-moment behavioral constraint | `post_history_instructions` (card field) | Strongest injection point (after history, before output contract). Reserve for constraints that must never be forgotten. Optional; many cards don't need it. |
| A faction, kingdom, school, magic system, public history | Worldbook | Split into triggerable entries; keep core premise short. |
| User's in-story name, identity, role, powers, relation to cast | Persona | Add public reputation to lore only when other characters should know it. |
| What happened in play | Story history | Do not rewrite history unless user intentionally edits/branches. |
| Important past events needed after context truncation | Story state | Structured ledger, not prose recap. |
| Current place/time/who is present | Scene state | Updated from recent turns. |
| Reply length, tone, more/less description, relationship tension | Author note | World-specific style direction. |
| Narration/dialogue markup rules | System output protocol | Never put this in worldbook or persona. |
| Search/import/download/liveware/model operations | Tavern runtime / CLI | Operational layer, not story content. |

## Decision Checklist

Before adding any new material, ask:

1. Is this about a specific character's inner logic or voice? Put it in the character card.
2. Is this a world fact, faction, place, rule, secret, object, or historical fact? Put it in worldbook.
3. Is this who the user is inside the story? Put it in persona.
4. Did it happen during play? It belongs to story history and later story state.
5. Is this only about the current camera/scene? It belongs to scene state.
6. Is this about how this world should be written? Put it in author note.
7. Is this a UI/rendering rule? It belongs to runtime prompt/protocol, not editable content.

## Anti-Patterns

- Putting `{{user}}` identity inside imported character cards without adapting it to persona.
- Using worldbook entries as a dumping ground for character personality.
- Making every lore entry constant because keyword design is hard.
- Using broad keys such as `学校`, `商会`, `任务`, `秘密`, or `教团` without secondary triggers.
- Letting a character card's embedded lore conflict with the standalone worldbook extracted at import.
- Treating Ruotang as a character inside every story. Ruotang organizes the tavern; she is not automatically in the scene.
- Putting output format or renderer protocol into author note or worldbook.
- Putting output format or renderer protocol into `system_prompt` — it's buried in the system message and only active when that specific character is present.
- Using `system_prompt` for information that belongs in `personality` or `description` — the positional priority is too weak for primary identity facts.

## Build Order For A New World

1. Define the world container: name, genre, intended mood, and first play goal.
2. Define persona: who the user is in this world and what other characters know.
3. Select or create cast: one primary character first, then supporting characters.
4. Add core lore: premise, factions, places, rules, secrets, and starting conflict.
5. Decide opening: location, time, present characters, immediate tension, first response hook.
6. Add author note only if the world needs a special writing style.
7. Run `diagnose` and `lore-audit` before serious play if the world has many roles/lore entries.

## Fix Order For A Broken World

1. Run `diagnose <world>`.
2. If lore-related, run `lore-audit <world>`.
3. Check persona before editing cards or lore.
4. Check recent story before changing prompts.
5. Make the smallest data fix possible.
6. Regenerate only after structure is clean.
