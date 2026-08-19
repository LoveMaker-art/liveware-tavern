# Conversation Presentation

Use this reference when presenting a proposed or completed world or card in
ClawChat. Keep the answer compact and conversational; do not dump JSON, command
logs, internal IDs, or unavailable UI controls.

## Proposal

```markdown
### 世界预览｜<世界名>

<one-sentence premise>

**你的身份**　<Persona or undecided>
**登场角色**　<names and one short relationship cue>
**核心设定**　<two or three durable facts>
**开场**　<immediate playable hook>
```

Ask one confirmation question only when the user has not already approved the
plan.

## Completed World

```markdown
### 已备好｜<世界名>

<one sentence about what is ready>
```

Then output the bare URL returned by `app-link --app console --json` on its own
line so ClawChat can render the Liveware card. Do not rename the URL in Markdown.

## Reusable Card

Show name, identity, voice, relationship role, and opening hook. If the user
requested the actual card artifact, provide the real stored/downloadable file;
do not substitute a prose preview for the file.
