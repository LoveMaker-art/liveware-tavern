# Story Profile And Hermes Projection

## Sources

- `story_profile.json`: canonical active preference profile.
- `profile_events.jsonl`: append-only audit archive; never injected into prompts.
- `profile_eras.json`: bounded summaries of older profile phases.
- `actor_self.md`: rendered compatibility view, not a writable source.
- Managed blocks in `USER.md` and `MEMORY.md`: bounded projections replaced in place.

Content outside managed marker blocks is not owned by Tavern and must be preserved.

## Preference Boundary

Use `learn` for explicit durable preferences such as pacing, emotional tone,
interaction density, boundaries, favored tropes, or disliked narrative habits.
Use `reflect-preview` before uncertain inference. Reflection must not turn a
single scene, temporary emotion, plot fact, bug report, or tool issue into taste.

Confirmed evidence is model-aggregated into bounded taste fields and concrete
`response_adaptations` for `USER.md`. These adaptations may guide recommendations,
story organization, and conversational tone but may not be treated as real-life
personality evidence.

## Story Memory Boundary

Concrete fictional memories come only from successful story-ledger checkpoints.
They are projected into `MEMORY.md` as complete, bounded, explicitly fictional
event lines. General life facts remain ordinary Hermes memory.

Hermes already loads `USER.md` and `MEMORY.md`; do not add a second prompt hook.
Projection revision changes invalidate only stale prompt snapshots so the next
turn reloads current memory without deleting messages or changing the session.

## Maintenance

```sh
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PROFILE="$HERMES_HOME/skills/creative/tavern-story-profile/scripts/profile_memory.py"
python3 "$PROFILE" audit
python3 "$PROFILE" memory-preview
python3 "$PROFILE" memory-sync
python3 "$PROFILE" refresh
python3 "$PROFILE" context
python3 "$PROFILE" confirm <preference-id>
python3 "$PROFILE" reject <preference-id>
python3 "$PROFILE" edit <preference-id> "new text" [--scope tavern|agent_chat|both]
python3 "$PROFILE" lock <preference-id> [--off]
```

Preview before manual synchronization. After a write, audit the profile and
confirm projections remain bounded, attributable, and free of unrelated facts.
