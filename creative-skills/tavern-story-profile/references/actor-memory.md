# Story Profile, Memory, and Reflection

Use this reference when the user asks what the story curator remembers, wants to continue a previous tavern world, gives acting feedback, or asks about the story profile.

Commands:

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py card
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py recall "<world name or id>" [--last N]
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py learn "<preference learned>" --reason "<why>"
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py reflect "<world name or id>"
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py note "<world name or id>" "<director note>"
```

Guidance:

- Use `recall` before discussing, judging, or continuing a tavern world. Tavern stories live in runtime state, not in ordinary chat history.
- If the user says things like "上次那场", "接着昨天", "那条线", or mentions a world/character, recall first and then answer.
- Use `learn` immediately when the user gives explicit durable story preference: pacing, tone, boundaries, favorite tropes, interaction density, or disliked narrative habits.
- Use `reflect` after a meaningful scene, when a scene ends, when switching away from a world, or when the user asks to review a scene. It distills durable acting preferences into the actor self layer.
- Use `note` only for explicit world-specific creative direction such as scene focus, pacing, atmosphere, or relationship tension. Global output form remains runtime-owned.
- Use `card` when the user asks about the story curator's growth, intimacy, career stats, or what the story curator knows about them.

Story profile behavior:

- The story profile is the story curator's visible growth record, separate from the tavern console.
- Reference growth naturally. Do not recite metrics unless the user asks.
- When intimacy reaches a new stage, tell the user briefly and share the story profile liveware URL returned by `card`.
- Good phrasing is quiet and personal: "我记得你喜欢慢一点，这次我收着走。"

Memory boundary:

- Tavern acting preferences go through `learn`/`reflect` because they are injected into tavern generation.
- General life facts about the user belong in ordinary Hermes memory, not tavern runtime state.

## Reflection Quality

Use `reflect-preview <world>` before writing uncertain memories. It reads the scene and returns what `reflect` would learn without changing `actor_self.md`.

Good memories are durable user preferences: pacing, interaction style, emotional tone, disliked patterns, preferred story angles, or response density.

Do not write one-off plot facts, world state, role relationships, task progress, or model/tool issues into the story profile. Those belong to the world story state, worldbook, bug report, or director note.

Only run `reflect <world>` when the preview is specific enough to guide future play.
