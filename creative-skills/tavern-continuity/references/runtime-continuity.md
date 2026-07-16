# Runtime Continuity Model

## Confirmed History

The latest user turn remains raw and unconfirmed. The runtime compresses only completed user/assistant turns.

## Fifteen-Turn Checkpoint

- STORY_STATE_BATCH_TURNS defaults to 15.
- Each successful batch advances the plot-ledger checkpoint and runtime-cast checkpoint atomically.
- A failed ledger or cast update advances neither checkpoint.
- The same batch is retried later after failure.
- Backlogged stories are processed in complete chronological 15-turn batches.

## Plot Ledger Ownership

The story ledger owns:

- current scene, locations, participants, and activities;
- completed and ongoing events;
- causal facts and knowledge boundaries;
- key objects and custody;
- secrets, promises, conflicts, and open threads.

The ledger is bounded by STORY_STATE_MAX_CHARS, currently defaulting to 15000 characters. Size reduction removes duplicates, expired scene detail, and inconsequential completed actions before protected memory.

When a valid ledger covers confirmed turns, those covered raw messages are replaced in model context by the ledger. Uncovered recent turns remain raw. Frontend story display remains unchanged.

## Runtime Cast Ownership

runtime_cast is the sole world-local authority for effective character and user profiles.

- origin_profile and origin_user_profile are immutable entry snapshots.
- profile and user_profile are the only effective profiles.
- Persistent status and relationships contain durable changes only.
- Temporary emotion, action, location, clothing, short-term goal, knowledge, and held objects stay in the story ledger.

Character evolution uses only the same newly confirmed 15-turn batch as the ledger. It must never replay the full story.

## Rebuild Rule

If the plot ledger is invalid or explicitly rebuilt:

1. Rebuild only the ledger in chronological batches.
2. Preserve current effective profiles, persistent statuses, and relationships.
3. Move the preserved cast checkpoint to the rebuilt ledger boundary.
4. Do not call the character-state model during ledger rebuild.

## Diagnostic Checks

Compare:

- compressible confirmed turns;
- story_state.turns;
- runtime_cast.applied_turn;
- runtime_cast revision and last error;
- ledger size and required fields;
- raw messages actually selected by actor.py;
- prompt size and model response timing.

The story_state and runtime_cast checkpoints should match after every successful batch.
