"""Story ledger rules and helpers for Hermes Tavern runtime.

This module intentionally contains deterministic story-state mechanics only:
turn counting, batch rendering/splitting, ledger normalization, trimming, and
shape/reference validation. Model calls, persistence, locks, and background
job scheduling remain owned by server.py.
"""
import json
import os
import re
import time

from continuity_model import (
    normalize_fact_entry,
    normalize_ledger_scene,
    normalize_object_entry,
)
from story_ledger import (
    story_state_has_memory,
    validated_story_state,
)


STORY_STATE_BATCH_TURNS = int(os.environ.get("TAVERN_STORY_STATE_BATCH_TURNS", "15"))
STORY_STATE_MAX_CHARS = max(
    4000, int(os.environ.get("TAVERN_STORY_STATE_MAX_CHARS", "15000")))
STORY_STATE_BATCH_TOKEN_BUDGET = max(
    8000, int(os.environ.get("TAVERN_STORY_STATE_BATCH_TOKEN_BUDGET", "50000")))


def world_turns(story):
    return sum(1 for m in story or [] if m.get("role") == "user")


def compressible_story_turns(story):
    """Keep the latest user turn raw and compress only confirmed history."""
    return max(0, world_turns(story) - 1)


def story_lines_for_turns(p, start_turn, end_turn, response_language="zh"):
    """Render complete story messages for an inclusive user-turn batch."""
    en = response_language == "en"
    cname = "Story response" if en else "故事回复"
    lines = []
    seen_turns = 0
    for message in p.get("story") or []:
        if message.get("role") == "user":
            seen_turns += 1
        if seen_turns < start_turn:
            if start_turn == 1 and seen_turns == 0:
                pass
            else:
                continue
        if seen_turns > end_turn:
            break
        text = (message.get("text") or "").strip().replace("\r\n", "\n")
        if not text:
            continue
        who = ("User" if en else "用户") if message.get("role") == "user" else cname
        turn_label = max(0, seen_turns)
        prefix = f"[Turn {turn_label} · {who}]" if en else f"[第 {turn_label} 轮 · {who}]"
        lines.append(f"{prefix}\n{text}")
    return "\n".join(lines)


def story_batch_segments(
        p, start_turn, end_turn, response_language="zh",
        token_budget=STORY_STATE_BATCH_TOKEN_BUDGET):
    """Split an oversized batch only at complete user-turn boundaries."""
    segments = []
    segment_start = start_turn
    segment_end = start_turn - 1
    segment_parts = []
    segment_tokens = 0
    for turn in range(start_turn, end_turn + 1):
        part = story_lines_for_turns(p, turn, turn, response_language)
        part_tokens = estimate_text_tokens(part)
        if segment_parts and segment_tokens + part_tokens > token_budget:
            segments.append((segment_start, segment_end, "\n".join(segment_parts)))
            segment_start = turn
            segment_parts = []
            segment_tokens = 0
        segment_parts.append(part)
        segment_tokens += part_tokens
        segment_end = turn
    if segment_parts:
        segments.append((segment_start, segment_end, "\n".join(segment_parts)))
    return segments


def estimate_text_tokens(text):
    """Cheap trigger-only token estimate: CJK ~= 1 token, other text ~= 4 chars/token."""
    cjk = 0
    other = 0
    for ch in text or "":
        if "一" <= ch <= "鿿" or "぀" <= ch <= "ヿ" or "가" <= ch <= "힯":
            cjk += 1
        elif not ch.isspace():
            other += 1
    return cjk + max(1, (other + 3) // 4) if (cjk or other) else 0


def story_token_estimate(story):
    return sum(estimate_text_tokens(m.get("text") or "") for m in story or [])


def clip_memory_text(value, limit):
    text = str(value or "").strip().lstrip("-•").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text[:limit].rstrip()


def normalize_story_state(
        raw, turns, source_tokens, valid_ids=None,
        max_chars=STORY_STATE_MAX_CHARS):
    if not isinstance(raw, dict):
        raw = {}

    limits = {
        "timeline": (12, 120),
        "open_threads": (12, 140),
        "style_notes": (6, 120),
    }

    def arr(key):
        max_items, max_len = limits[key]
        vals = raw.get(key) or []
        if isinstance(vals, str):
            vals = [vals]
        out = []
        for v in vals:
            x = clip_memory_text(v, max_len)
            if x and x not in out:
                out.append(x)
            if len(out) >= max_items:
                break
        return out

    state = {
        "timeline": arr("timeline"),
        "facts": [],
        "open_threads": arr("open_threads"),
        "objects": [],
        "secrets": [],
        "scene": normalize_ledger_scene(raw.get("scene"), valid_ids),
        "style_notes": arr("style_notes"),
        "turns": turns,
        "source_tokens": source_tokens,
        "updated_at": int(time.time()),
    }
    fact_values = raw.get("facts") or []
    if isinstance(fact_values, (str, dict)):
        fact_values = [fact_values]
    for value in fact_values:
        fact = normalize_fact_entry(value, valid_ids)
        if fact and fact["id"] not in {item["id"] for item in state["facts"]}:
            state["facts"].append(fact)
        if len(state["facts"]) >= 24:
            break
    object_values = raw.get("objects") or []
    if isinstance(object_values, (str, dict)):
        object_values = [object_values]
    for value in object_values:
        obj = normalize_object_entry(value, valid_ids)
        if obj and obj["id"] not in {item["id"] for item in state["objects"]}:
            state["objects"].append(obj)
        if len(state["objects"]) >= 16:
            break
    secret_values = raw.get("secrets") or []
    if isinstance(secret_values, (str, dict)):
        secret_values = [secret_values]
    for value in secret_values:
        secret = normalize_fact_entry(value, valid_ids, secret=True)
        if secret and secret["id"] not in {item["id"] for item in state["secrets"]}:
            state["secrets"].append(secret)
        if len(state["secrets"]) >= 16:
            break
    return trim_story_state_to_budget(state, max_chars)


def story_state_chars(state):
    return len(json.dumps(state or {}, ensure_ascii=False, separators=(",", ":")))


def trim_story_state_to_budget(state, max_chars):
    """Bound ledger size while removing transient details before protected memory."""
    state = dict(state or {})

    primary_order = (
        "style_notes", "timeline", "facts", "objects",
    )
    protected_order = ("open_threads", "secrets")
    while story_state_chars(state) > max_chars:
        changed = False
        for key in primary_order:
            values = list(state.get(key) or [])
            if values:
                values.pop(0)
                state[key] = values
                changed = True
                break
        if not changed:
            for key in protected_order:
                values = list(state.get(key) or [])
                if values:
                    values.pop(0)
                    state[key] = values
                    changed = True
                    break
        if not changed:
            break
    return state


def story_state_quality_ok(previous, current):
    """Reject catastrophic memory loss without adding another model call."""
    if not story_state_has_memory(previous):
        return True

    def count(keys, state):
        return sum(len(state.get(key) or []) for key in keys)

    old_protected = count(("open_threads", "objects", "secrets"), previous)
    new_protected = count(("open_threads", "objects", "secrets"), current)
    if old_protected >= 6 and new_protected < 2:
        return False

    old_history = count(("timeline", "facts"), previous)
    new_history = count(("timeline", "facts"), current)
    if old_history >= 6 and new_history < 2:
        return False

    return True


def validated_story_state_for_batch(state, story, batch_turns=STORY_STATE_BATCH_TURNS):
    """Return a ledger only when it safely replaces confirmed raw turns."""
    return validated_story_state(state, story, batch_turns)


def effective_story_state(p, batch_turns=STORY_STATE_BATCH_TURNS):
    return validated_story_state_for_batch(
        (p or {}).get("story_state") or {}, (p or {}).get("story") or [],
        batch_turns)


def story_state_reference_error(raw, valid_ids):
    """Reject model output that uses names or unknown ids in ledger references."""
    raw = raw if isinstance(raw, dict) else {}
    allowed = {str(value) for value in (valid_ids or set()) if value}
    if not allowed:
        return ""
    invalid = []
    for key in ("facts", "secrets"):
        values = raw.get(key) or []
        values = values if isinstance(values, list) else [values]
        for entry in values:
            if isinstance(entry, dict):
                invalid.extend("%s.known_by=%s" % (key, value)
                               for value in (entry.get("known_by") or [])
                               if str(value) not in allowed)
    values = raw.get("objects") or []
    values = values if isinstance(values, list) else [values]
    for entry in values:
        if isinstance(entry, dict):
            holder = str(entry.get("holder") or "").strip()
            if holder and holder not in allowed:
                invalid.append("objects.holder=%s" % holder)
    scene = raw.get("scene") if isinstance(raw.get("scene"), dict) else {}
    for entry in scene.get("participants") or []:
        if isinstance(entry, dict):
            cid = str(entry.get("character_id") or entry.get("id") or "").strip()
            if not cid or cid not in allowed:
                invalid.append("scene.character_id=%s" % (cid or "<empty>"))
    return "invalid story ledger references: %s" % invalid[:8] if invalid else ""


def story_state_shape_error(raw):
    """Keep the model contract and the normalized ledger schema in lockstep."""
    if not isinstance(raw, dict):
        return "story ledger must be an object"
    required = {
        "timeline", "facts", "open_threads", "objects", "secrets",
        "scene", "style_notes",
    }
    if set(raw) != required:
        return "story ledger has an invalid top-level field set"
    for key in ("timeline", "facts", "open_threads", "objects", "secrets", "style_notes"):
        if not isinstance(raw.get(key), list):
            return "%s must be an array" % key
    for key in ("timeline", "open_threads", "style_notes"):
        if any(not isinstance(item, str) or not item.strip() for item in raw.get(key)):
            return "%s items must be non-empty strings" % key
    for key in ("facts", "secrets"):
        for item in raw.get(key):
            if not isinstance(item, dict) or set(item) != {"id", "content", "known_by"}:
                return "%s items must contain exactly id, content, and known_by" % key
            if not str(item.get("id") or "").strip() or not str(item.get("content") or "").strip():
                return "%s items require non-empty id and content" % key
            if (not isinstance(item.get("known_by"), list)
                    or any(not isinstance(value, str) or not value.strip()
                           for value in item.get("known_by"))):
                return "%s.known_by must be an array" % key
    for item in raw.get("objects"):
        if not isinstance(item, dict) or set(item) != {
                "id", "name", "status", "holder", "location"}:
            return "objects items must contain exactly id, name, status, holder, and location"
        if not str(item.get("id") or "").strip() or not str(item.get("name") or "").strip():
            return "objects items require non-empty id and name"
        if any(not isinstance(item.get(key), str) for key in ("status", "holder", "location")):
            return "objects status, holder, and location must be strings"
    scene = raw.get("scene")
    if not isinstance(scene, dict) or set(scene) != {"time", "place", "participants"}:
        return "scene must contain exactly time, place, and participants"
    if not isinstance(scene.get("participants"), list):
        return "scene.participants must be an array"
    if any(not isinstance(scene.get(key), str) for key in ("time", "place")):
        return "scene time and place must be strings"
    for item in scene.get("participants"):
        if not isinstance(item, dict) or set(item) != {
                "character_id", "location", "activity", "condition"}:
            return "scene participants have an invalid field set"
        if any(not isinstance(item.get(key), str) for key in (
                "character_id", "location", "activity", "condition")):
            return "scene participant values must be strings"
    return ""
