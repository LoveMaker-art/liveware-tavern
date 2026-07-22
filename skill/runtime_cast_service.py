"""Runtime cast validation and snapshot-application helpers.

This module is intentionally deterministic: it normalizes model output,
validates evidence and audit coverage, rejects no-op changes, and applies
accepted durable profile/status/relationship diffs to a runtime_cast snapshot.
Model calls, retries, persistence, locks, and background jobs remain in server.py.
"""
import json
import re
import time

from continuity_model import (
    canonical_profile_snapshot as _canonical_profile_snapshot,
    normalize_persistent_status as _normalize_persistent_status,
    normalize_relationships as _normalize_relationships,
    runtime_character as _runtime_character,
)
from story_state_service import clip_memory_text as _clip_memory_text


_PROFILE_CHANGE_FIELDS = {
    "identity": {
        "name", "aliases", "description", "gender", "age", "species",
        "occupation", "affiliations", "story_role",
    },
    "appearance": {"summary", "features"},
    "personality": {"summary", "traits", "values", "motivation", "fears", "boundaries"},
    "expression": {"speech_style", "habits", "mannerisms"},
    "capabilities": {"skills", "powers", "limitations"},
}
_PROFILE_LIST_FIELDS = {
    "aliases", "affiliations", "features", "traits", "values", "fears",
    "boundaries", "habits", "mannerisms", "skills", "powers", "limitations",
}


def _validated_change_evidence(value, start_turn, end_turn):
    values = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    out = []
    for raw in values:
        if not isinstance(raw, dict):
            continue
        try:
            turn = int(raw.get("turn"))
        except (TypeError, ValueError):
            continue
        fact = _clip_memory_text(raw.get("fact"), 300)
        reason = _clip_memory_text(raw.get("reason"), 300)
        if start_turn <= turn <= end_turn and fact:
            item = {"turn": turn, "fact": fact}
            fields = raw.get("fields") or []
            if isinstance(fields, str):
                fields = [fields]
            fields = [str(field).strip() for field in fields if str(field).strip()]
            if fields:
                item["fields"] = list(dict.fromkeys(fields))[:12]
            if reason:
                item["reason"] = reason
            out.append(item)
    return out[:6]


def _merge_profile_changes(current, changes):
    """Apply non-empty whitelisted fields to the current profile."""
    before = _canonical_profile_snapshot(current)
    merged = json.loads(json.dumps(before, ensure_ascii=False))
    incoming = changes if isinstance(changes, dict) else {}
    for section, allowed_fields in _PROFILE_CHANGE_FIELDS.items():
        section_changes = incoming.get(section)
        if not isinstance(section_changes, dict):
            section_changes = {}
        target = merged.setdefault(section, {})
        for field in allowed_fields:
            if field in section_changes:
                raw = section_changes.get(field)
            elif field != "summary":
                misplaced = [values.get(field) for values in incoming.values()
                             if isinstance(values, dict) and field in values]
                if not misplaced:
                    continue
                raw = misplaced[0]
            else:
                continue
            if field in _PROFILE_LIST_FIELDS:
                values = raw if isinstance(raw, list) else ([raw] if raw else [])
                cleaned = []
                for value in values:
                    text = _clip_memory_text(value, 240)
                    if text and text not in cleaned:
                        cleaned.append(text)
                if cleaned:
                    target[field] = cleaned[:12]
            else:
                limit = 2500 if field in ("description", "summary") else 600
                text = _clip_memory_text(raw, limit)
                if text:
                    target[field] = text
    old_name = str((before.get("identity") or {}).get("name") or "").strip()
    new_name = str((merged.get("identity") or {}).get("name") or "").strip()
    if old_name and new_name and old_name != new_name:
        aliases = list((merged.get("identity") or {}).get("aliases") or [])
        if old_name not in aliases:
            aliases.append(old_name)
        merged["identity"]["aliases"] = aliases[:8]
    result = _canonical_profile_snapshot(merged)
    return result, result != before


def _merge_persistent_status_changes(current, changes):
    before = _normalize_persistent_status(current or {})
    merged = dict(before)
    incoming = changes if isinstance(changes, dict) else {}
    for field, limit in (("life_status", 80), ("physical_condition", 600)):
        if field in incoming:
            text = _clip_memory_text(incoming.get(field), limit)
            if text:
                merged[field] = text
    result = _normalize_persistent_status(merged)
    return result, result != before


def _runtime_user_change(raw):
    """Accept the canonical user change object and the common __user__ wrapper."""
    raw = raw if isinstance(raw, dict) else {}
    candidate = raw.get("user_changes")
    if not isinstance(candidate, dict):
        return {}
    wrapped = candidate.get("__user__")
    return wrapped if isinstance(wrapped, dict) else candidate


def _model_evidence(value, start_turn, end_turn):
    """Normalize compact model evidence strings into canonical turn evidence."""
    if isinstance(value, list):
        return value
    text = _clip_memory_text(value, 500)
    if not text:
        return []
    turns = []
    for match in re.finditer(r"第\s*(\d+)(?:\s*[-—至]\s*(\d+))?\s*轮", text):
        for raw_turn in (match.group(1), match.group(2)):
            if raw_turn:
                turn = int(raw_turn)
                if start_turn <= turn <= end_turn and turn not in turns:
                    turns.append(turn)
    return [{"turn": turn, "fact": text} for turn in turns[:6]]


def _canonicalize_runtime_cast_output(raw, start_turn, end_turn):
    """Accept the prompt's compact field-diff form and convert it for storage."""
    raw = dict(raw) if isinstance(raw, dict) else {}

    def profile_path(field):
        if "." in field:
            return field.split(".", 1)
        matches = [section for section, fields in _PROFILE_CHANGE_FIELDS.items()
                   if field in fields]
        return (matches[0], field) if len(matches) == 1 else ("identity", field)

    def add_field(result, entity_id, field, value, evidence):
        if not entity_id or not field:
            return
        section, name = profile_path(field)
        candidate = result.setdefault(entity_id, {"profile": {}, "evidence": []})
        if section == "persistent_status":
            candidate.setdefault("persistent_status", {})[name] = value
        elif section in _PROFILE_CHANGE_FIELDS and name in _PROFILE_CHANGE_FIELDS[section]:
            candidate.setdefault("profile", {}).setdefault(section, {})[name] = value
        candidate["evidence"].extend(_model_evidence(evidence, start_turn, end_turn))

    def grouped(value, user=False):
        result = {}
        if isinstance(value, dict):
            if user:
                wrapped = value.get("__user__")
                return {"__user__": wrapped} if isinstance(wrapped, dict) else {"__user__": value}
            # The canonical contract uses character ids as object keys. Preserve it
            # exactly; list handling below exists only for older model responses.
            return value
        for item in value if isinstance(value, list) else []:
            if not isinstance(item, dict):
                continue
            entity_id = "__user__" if user else str(
                item.get("id") or item.get("character_id") or "").strip()
            if not entity_id:
                continue
            nested = item.get("changes")
            if isinstance(nested, dict):
                if set(nested).issubset(set(_PROFILE_CHANGE_FIELDS) | {"persistent_status"}):
                    candidate = result.setdefault(
                        entity_id, {"profile": {}, "evidence": []})
                    for section, fields in nested.items():
                        if not isinstance(fields, dict):
                            continue
                        if section == "persistent_status":
                            candidate.setdefault("persistent_status", {}).update(fields)
                        elif section in _PROFILE_CHANGE_FIELDS:
                            candidate.setdefault("profile", {}).setdefault(
                                section, {}).update(fields)
                    candidate["evidence"].extend(
                        _model_evidence(item.get("evidence"), start_turn, end_turn))
                    continue
                for field, detail in nested.items():
                    if isinstance(detail, dict):
                        add_field(result, entity_id, field, detail.get("new_value"),
                                  detail.get("evidence"))
                continue
            field = str(item.get("field") or "").strip()
            add_field(result, entity_id, field, item.get("new_value"), item.get("evidence"))
        for candidate in result.values():
            evidence = []
            for item in candidate.get("evidence") or []:
                if item not in evidence:
                    evidence.append(item)
            candidate["evidence"] = evidence[:6]
        return result

    characters = grouped(raw.get("character_changes"))
    users = grouped(raw.get("user_changes"), user=True)
    embedded_user = characters.pop("__user__", None)
    if embedded_user:
        target = users.setdefault("__user__", {"profile": {}, "evidence": []})
        for section, fields in (embedded_user.get("profile") or {}).items():
            target.setdefault("profile", {}).setdefault(section, {}).update(fields)
        target["evidence"] = (target.get("evidence") or []) + (
            embedded_user.get("evidence") or [])
    raw["character_changes"] = characters
    raw["user_changes"] = users.get("__user__", {})

    relationships = []
    for item in raw.get("relationship_changes") or []:
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        normalized["action"] = str(item.get("action") or "upsert")
        normalized["evidence"] = _model_evidence(
            item.get("evidence"), start_turn, end_turn)
        relationships.append(normalized)
    raw["relationship_changes"] = relationships
    return raw


def _runtime_cast_evidence_shape_error(value, expected_fields=None):
    if not isinstance(value, list) or not value:
        return "evidence must be a non-empty array"
    for item in value:
        if not isinstance(item, dict) or set(item) != {"turn", "fact", "fields"}:
            return "evidence items must contain exactly turn, fact, and fields"
        if not isinstance(item.get("turn"), int):
            return "evidence.turn must be an integer"
        if not isinstance(item.get("fact"), str) or not item.get("fact").strip():
            return "evidence.fact must be a non-empty string"
        fields = item.get("fields")
        if (not isinstance(fields, list) or not fields
                or any(not isinstance(field, str) or not field.strip() for field in fields)):
            return "evidence.fields must be a non-empty string array"
        if expected_fields is not None and set(fields) != set(expected_fields):
            return "evidence.fields does not match the required field set"
    return ""


_RUNTIME_CAST_AUDIT_FIELDS = {
    "name": "profile.identity.name",
    "description": "profile.identity.description",
    "age": "profile.identity.age",
    "occupation": "profile.identity.occupation",
    "affiliations": "profile.identity.affiliations",
    "story_role": "profile.identity.story_role",
    "life_status": "persistent_status.life_status",
    "physical_condition": "persistent_status.physical_condition",
}
_RUNTIME_CAST_AUDIT_DECISIONS = {"update", "keep", "unknown"}


def _runtime_cast_review_error(raw, roster, start_turn, end_turn):
    """Require one complete, conflict-free audit before accepting a cast change set."""
    raw = raw if isinstance(raw, dict) else {}
    expected = {str(item.get("id")) for item in roster if item.get("id")}
    reviewed_raw = raw.get("reviewed_character_ids")
    reviewed = ({str(value) for value in reviewed_raw}
                if isinstance(reviewed_raw, list) else set())
    if reviewed != expected or len(reviewed_raw or []) != len(expected):
        missing = sorted(expected - reviewed)
        extra = sorted(reviewed - expected)
        return "incomplete cast review; missing=%s extra=%s" % (missing, extra)
    if raw.get("user_reviewed") is not True:
        return "user profile was not reviewed"
    audit = raw.get("field_audit")
    expected_audit_ids = expected | {"__user__"}
    if not isinstance(audit, dict) or set(audit) != expected_audit_ids:
        return "field_audit must contain every roster id and __user__ exactly once"
    changes = raw.get("character_changes") if isinstance(
        raw.get("character_changes"), dict) else {}
    audited_paths = set(_RUNTIME_CAST_AUDIT_FIELDS.values())
    for entity_id in sorted(expected_audit_ids):
        decisions = audit.get(entity_id)
        if not isinstance(decisions, dict) or set(decisions) != set(
                _RUNTIME_CAST_AUDIT_FIELDS):
            return "field_audit has an invalid field set for %s" % entity_id
        if any(value not in _RUNTIME_CAST_AUDIT_DECISIONS
               for value in decisions.values()):
            return "field_audit has an invalid decision for %s" % entity_id
        candidate = (_runtime_user_change(raw) if entity_id == "__user__"
                     else changes.get(entity_id) or {})
        emitted = _runtime_cast_changed_field_paths(candidate) & audited_paths
        declared = {
            path for field, path in _RUNTIME_CAST_AUDIT_FIELDS.items()
            if decisions.get(field) == "update"
        }
        if emitted != declared:
            return "field_audit updates do not match emitted changes for %s" % entity_id
        identity_updates = {
            decisions.get(field) for field in (
                "name", "age", "occupation", "affiliations")
        }
        if "update" in identity_updates and decisions.get("description") != "update":
            return "identity changes require an updated description for %s" % entity_id
    conflicts = raw.get("unresolved_conflicts")
    if not isinstance(conflicts, list):
        return "unresolved_conflicts must be an array"
    valid_ids = expected | {"__user__"}
    for conflict in conflicts:
        if not isinstance(conflict, dict):
            return "every unresolved conflict must be an object"
        if set(conflict) != {"entity_id", "field", "description", "evidence"}:
            return "unresolved conflict has an invalid field set"
        if str(conflict.get("entity_id") or "") not in valid_ids:
            return "unresolved conflict has an unknown entity_id"
        if not str(conflict.get("field") or "").strip():
            return "unresolved conflict must name one field"
        if not str(conflict.get("description") or "").strip():
            return "unresolved conflict requires a description"
        evidence_shape_error = _runtime_cast_evidence_shape_error(
            conflict.get("evidence"), {str(conflict.get("field"))})
        if evidence_shape_error:
            return evidence_shape_error
        if not _validated_change_evidence(
                conflict.get("evidence"), start_turn, end_turn):
            return "unresolved conflict requires valid evidence"
    return ""


def _runtime_cast_changed_field_paths(candidate):
    """Return the canonical field paths emitted by one profile change object."""
    candidate = candidate if isinstance(candidate, dict) else {}
    paths = set()
    profile = candidate.get("profile") if isinstance(candidate.get("profile"), dict) else {}
    for section, values in profile.items():
        if isinstance(values, dict):
            paths.update("profile.%s.%s" % (section, field) for field in values)
    status = candidate.get("persistent_status")
    if isinstance(status, dict):
        paths.update("persistent_status.%s" % field for field in status)
    return paths


def _runtime_cast_shape_error(raw, roster, start_turn, end_turn):
    raw = raw if isinstance(raw, dict) else {}
    required_top_level = {
        "reviewed_character_ids", "user_reviewed", "field_audit",
        "unresolved_conflicts",
        "character_changes", "user_changes", "relationship_changes",
    }
    if set(raw) != required_top_level:
        return "runtime cast output has an invalid top-level field set"
    valid_ids = {str(item.get("id")) for item in roster if item.get("id")}
    changes = raw.get("character_changes")
    if not isinstance(changes, dict):
        return "character_changes must be an object"
    unknown_ids = sorted(set(changes) - valid_ids)
    if unknown_ids:
        return "unknown character ids: %s" % unknown_ids
    candidates = list(changes.values())
    raw_user_change = raw.get("user_changes")
    if not isinstance(raw_user_change, dict):
        return "user_changes must be an object"
    user_change = _runtime_user_change(raw)
    if user_change:
        candidates.append(user_change)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            return "every change must be an object"
        if not candidate:
            continue
        if set(candidate) - {"profile", "persistent_status", "evidence"}:
            return "change object has unknown fields"
        profile = candidate.get("profile")
        if profile is not None:
            if not isinstance(profile, dict):
                return "profile must be an object"
            if set(profile) - set(_PROFILE_CHANGE_FIELDS):
                return "unknown profile section"
            for section, fields in profile.items():
                if not isinstance(fields, dict) or set(fields) - _PROFILE_CHANGE_FIELDS[section]:
                    return "invalid fields in profile.%s" % section
                for field, value in fields.items():
                    if field in _PROFILE_LIST_FIELDS:
                        if (not isinstance(value, list)
                                or any(not isinstance(item, str) or not item.strip()
                                       for item in value)):
                            return "profile.%s.%s must be a non-empty string array" % (
                                section, field)
                    elif not isinstance(value, str) or not value.strip():
                        return "profile.%s.%s must be a non-empty string" % (section, field)
        status = candidate.get("persistent_status")
        if status is not None and (
                not isinstance(status, dict)
                or set(status) - {"life_status", "physical_condition"}):
            return "invalid persistent_status"
        if isinstance(status, dict) and any(
                not isinstance(value, str) or not value.strip() for value in status.values()):
            return "persistent_status values must be non-empty strings"
        if not _validated_change_evidence(candidate.get("evidence"), start_turn, end_turn):
            return "every non-empty change needs valid evidence"
        emitted_fields = _runtime_cast_changed_field_paths(candidate)
        evidence_shape_error = _runtime_cast_evidence_shape_error(
            candidate.get("evidence"))
        if evidence_shape_error:
            return evidence_shape_error
        evidence_fields = {
            field
            for evidence in _validated_change_evidence(
                candidate.get("evidence"), start_turn, end_turn)
            for field in evidence.get("fields") or []
        }
        if emitted_fields != evidence_fields:
            return "change evidence fields must exactly match emitted fields"
    if not isinstance(raw.get("relationship_changes"), list):
        return "relationship_changes must be an array"
    for change in raw.get("relationship_changes") or []:
        if not isinstance(change, dict):
            return "every relationship change must be an object"
        if set(change) != {"participants", "action", "description", "evidence"}:
            return "relationship change has an invalid field set"
        participants = change.get("participants")
        normalized_participants = ([str(value) for value in participants]
                                   if isinstance(participants, list) else [])
        if (len(normalized_participants) != 2 or len(set(normalized_participants)) != 2
                or any(str(value) not in valid_ids | {"__user__"} for value in participants)):
            return "relationship changes require two valid participant ids"
        action = str(change.get("action") or "").strip().lower()
        if action not in {"upsert", "remove"}:
            return "relationship action must be upsert or remove"
        if action == "upsert" and not str(change.get("description") or "").strip():
            return "upsert relationship changes require description"
        evidence_shape_error = _runtime_cast_evidence_shape_error(
            change.get("evidence"), {"relationship"})
        if evidence_shape_error:
            return evidence_shape_error
        if not _validated_change_evidence(change.get("evidence"), start_turn, end_turn):
            return "relationship changes require valid evidence"
    return ""


def _runtime_cast_noop_error(raw, previous, persona=None):
    """Reject claimed updates that do not change the current authoritative cast."""
    raw = raw if isinstance(raw, dict) else {}
    previous = previous if isinstance(previous, dict) else {}
    persona = persona if isinstance(persona, dict) else {}
    changes = raw.get("character_changes") or {}
    current_by_id = {
        str(item.get("id")): item
        for item in previous.get("characters") or [] if isinstance(item, dict)
    }
    for entity_id, candidate in changes.items():
        current = current_by_id.get(str(entity_id)) or {}
        _, profile_changed = _merge_profile_changes(
            current.get("profile") or {}, candidate.get("profile") or {})
        _, status_changed = _merge_persistent_status_changes(
            current.get("persistent_status") or {}, candidate.get("persistent_status") or {})
        if not profile_changed and not status_changed:
            return "character change does not alter current_cast: %s" % entity_id

    user_change = _runtime_user_change(raw)
    if user_change:
        current_user_profile = previous.get("user_profile") or persona.get("profile") or {}
        _, profile_changed = _merge_profile_changes(
            current_user_profile, user_change.get("profile") or {})
        _, status_changed = _merge_persistent_status_changes(
            previous.get("user_status") or {}, user_change.get("persistent_status") or {})
        if not profile_changed and not status_changed:
            return "user change does not alter current_cast"

    relationships = {
        "|".join(sorted(str(value) for value in item.get("participants") or [])):
            str(item.get("description") or "").strip()
        for item in previous.get("relationships") or [] if isinstance(item, dict)
    }
    for change in raw.get("relationship_changes") or []:
        key = "|".join(sorted(str(value) for value in change.get("participants") or []))
        action = str(change.get("action") or "").strip().lower()
        if action == "remove" and key not in relationships:
            return "relationship removal does not alter current_cast: %s" % key
        if action == "upsert" and relationships.get(key) == str(
                change.get("description") or "").strip():
            return "relationship update does not alter current_cast: %s" % key
    return ""


def _normalize_runtime_cast_result(raw, previous, start_turn, end_turn, persona=None):
    """Validate an evidence-backed change set and apply it to one durable cast snapshot."""
    raw = raw if isinstance(raw, dict) else {}
    previous = previous if isinstance(previous, dict) else {}
    raw_changes = raw.get("character_changes") if isinstance(raw.get("character_changes"), dict) else {}
    characters = []
    for old in previous.get("characters") or []:
        if not isinstance(old, dict):
            continue
        item = _runtime_character(old, applied_turn=int(previous.get("applied_turn") or 0))
        candidate = raw_changes.get(str(item.get("id")))
        evidence = _validated_change_evidence(
            candidate.get("evidence") if isinstance(candidate, dict) else None,
            start_turn, end_turn)
        profile_changed = status_changed = False
        if evidence:
            item["profile"], profile_changed = _merge_profile_changes(
                item.get("profile") or {}, candidate.get("profile") or {})
            item["persistent_status"], status_changed = _merge_persistent_status_changes(
                item.get("persistent_status") or {}, candidate.get("persistent_status") or {})
        if profile_changed:
            item["profile_updated_turn"] = end_turn
            item["last_change_evidence"] = evidence
        if status_changed:
            item["status_updated_turn"] = end_turn
            item["last_change_evidence"] = evidence
        identity = item["profile"]["identity"]
        item["name"] = identity.get("name") or item.get("name") or ""
        item["description"] = identity.get("description") or ""
        item["personality"] = item["profile"]["personality"].get("summary") or ""
        characters.append(item)

    previous_user_profile = _canonical_profile_snapshot(
        previous.get("user_profile") or (persona or {}).get("profile") or persona or {})
    previous_user_status = _normalize_persistent_status(previous.get("user_status") or {})
    user_profile = previous_user_profile
    user_status = previous_user_status
    user_profile_changed = user_status_changed = False
    user_candidate = _runtime_user_change(raw)
    user_evidence = _validated_change_evidence(user_candidate.get("evidence"), start_turn, end_turn)
    if user_evidence:
        user_profile, user_profile_changed = _merge_profile_changes(
            previous_user_profile, user_candidate.get("profile") or {})
        user_status, user_status_changed = _merge_persistent_status_changes(
            previous_user_status, user_candidate.get("persistent_status") or {})

    previous_relationships = _normalize_relationships(
        previous.get("relationships") or [], characters, persona or {})
    relationships_by_key = {
        "|".join(item.get("participants") or []): dict(item)
        for item in previous_relationships
    }
    valid_ids = {str(item.get("id")) for item in characters if item.get("id")}
    valid_ids.add("__user__")
    relation_changes = raw.get("relationship_changes")
    if not isinstance(relation_changes, list):
        relation_changes = []
    for change in relation_changes:
        if not isinstance(change, dict):
            continue
        evidence = _validated_change_evidence(change.get("evidence"), start_turn, end_turn)
        participants = sorted({str(value) for value in (change.get("participants") or [])})
        if not evidence or len(participants) != 2 or any(value not in valid_ids for value in participants):
            continue
        key = "|".join(participants)
        action = str(change.get("action") or "upsert").strip().lower()
        if action == "remove":
            relationships_by_key.pop(key, None)
            continue
        description = _clip_memory_text(change.get("description"), 300)
        if action == "upsert" and description:
            relationships_by_key[key] = {
                "participants": participants,
                "description": description,
                "updated_turn": end_turn,
            }
    relationships = _normalize_relationships(
        list(relationships_by_key.values()), characters, persona or {})

    result = {
        "schema_version": 3,
        "applied_turn": end_turn,
        "revision": int(previous.get("revision") or 0) + 1,
        "characters": characters,
        "origin_user_profile": _canonical_profile_snapshot(
            previous.get("origin_user_profile") or previous_user_profile),
        "user_profile": user_profile,
        "user_profile_updated_turn": (
            end_turn if user_profile_changed
            else int(previous.get("user_profile_updated_turn") or 0)),
        "user_status": user_status,
        "user_status_updated_turn": (
            end_turn if user_status_changed
            else int(previous.get("user_status_updated_turn") or 0)),
        "relationships": relationships,
        "updated_at": int(time.time()),
    }
    if user_profile_changed or user_status_changed:
        result["user_last_change_evidence"] = user_evidence
    elif previous.get("user_last_change_evidence"):
        result["user_last_change_evidence"] = previous.get("user_last_change_evidence")
    return result


def _runtime_cast_system_prompt(language):
    """Return the single semantic and serialization contract for cast updates."""
    schema = r'''{
  "reviewed_character_ids": ["<character_id>"],
  "user_reviewed": true,
  "field_audit": {
    "<character_id>": {
      "name": "update|keep|unknown",
      "description": "update|keep|unknown",
      "age": "update|keep|unknown",
      "occupation": "update|keep|unknown",
      "affiliations": "update|keep|unknown",
      "story_role": "update|keep|unknown",
      "life_status": "update|keep|unknown",
      "physical_condition": "update|keep|unknown"
    },
    "__user__": {
      "name": "update|keep|unknown",
      "description": "update|keep|unknown",
      "age": "update|keep|unknown",
      "occupation": "update|keep|unknown",
      "affiliations": "update|keep|unknown",
      "story_role": "update|keep|unknown",
      "life_status": "update|keep|unknown",
      "physical_condition": "update|keep|unknown"
    }
  },
  "unresolved_conflicts": [
    {
      "entity_id": "<character_id>|__user__",
      "field": "<canonical_field_path>",
      "description": "<conflicting facts>",
      "evidence": [
        {"turn": 1, "fact": "<fact from this batch>", "fields": ["<canonical_field_path>"]}
      ]
    }
  ],
  "character_changes": {
    "<character_id>": {
      "profile": {
        "identity": {"occupation": "<new confirmed value>"}
      },
      "evidence": [
        {
          "turn": 1,
          "fact": "<fact from this batch>",
          "fields": ["profile.identity.occupation"]
        }
      ]
    }
  },
  "user_changes": {
    "profile": {
      "identity": {"affiliations": ["<new confirmed value>"]}
    },
    "evidence": [
      {
        "turn": 1,
        "fact": "<fact from this batch>",
        "fields": ["profile.identity.affiliations"]
      }
    ]
  },
  "relationship_changes": [
    {
      "participants": ["<character_id>|__user__", "<character_id>|__user__"],
      "action": "upsert|remove",
      "description": "<current durable relationship; required for upsert>",
      "evidence": [
        {"turn": 1, "fact": "<fact from this batch>", "fields": ["relationship"]}
      ]
    }
  ]
}'''
    if language == "en":
        return (
            "# Task\n\n"
            "Maintain the single effective long-term cast registry for an interactive story. "
            "Compare current_cast with the complete new_story_batch and output only confirmed durable changes. "
            "Never continue, summarize, explain, or judge the story.\n\n"
            "# Sources and authority\n\n"
            "current_cast is the sole current truth. origin_profile is read-only historical reference. "
            "new_story_batch is the only source that may establish a new change. story_ledger may cross-check continuity but cannot independently prove a change. "
            "Within the batch, a later explicit confirmation supersedes an earlier intermediate state. "
            "Every field is optional and may remain empty. Never infer, fabricate, or fill a field merely to complete a profile.\n\n"
            "# What belongs here\n\n"
            "Store only facts expected to remain true beyond the current scene. Temporary emotion, action, location, clothing, short-term goal, knowledge, inventory, and scene activity belong to the story ledger. "
            "A name, identity, affiliation, status, or ability may change only when the batch explicitly establishes the new durable fact. "
            "A personality or expression field may change only after an explicit lasting transformation or consistent evidence across multiple independent turns. "
            "For __user__, record only explicit user statements, choices, or objectively completed facts; never infer feelings, intent, personality, or decisions.\n\n"
            "# Field catalog\n\n"
            "profile.identity: name (current official name, string); aliases (confirmed durable alternate names, string[]); "
            "description (optional display summary consistent with structured fields, string); gender (explicit durable gender identity, string); "
            "age (confirmed age, string); species (confirmed species, string); occupation (confirmed profession or student stage, string); "
            "affiliations (school, class, employer, faction, or organization, string[]); story_role (narrative function such as protagonist or mentor, string).\n"
            "profile.appearance: summary (durable overall appearance, string); features (durable distinctive features, string[]).\n"
            "profile.personality: summary (durable personality summary, string); traits, values, fears, boundaries (durable string[]); motivation (durable long-term motivation, string).\n"
            "profile.expression: speech_style (stable speaking style, string); habits and mannerisms (stable string[]).\n"
            "profile.capabilities: skills, powers, limitations (durable string[]).\n"
            "persistent_status: life_status (durable living/dead/missing state, string); physical_condition (long-term or irreversible physical condition, string).\n\n"
            "# Review and change rules\n\n"
            "Review every roster id and __user__. reviewed_character_ids contains every roster id exactly once and never __user__; user_reviewed is true. "
            "field_audit contains every roster id and __user__ exactly once. For each audited field use update only when this batch proves a new durable value, keep when current_cast remains accurate, and unknown when evidence is insufficient. "
            "An update decision must emit that exact canonical field with evidence; keep and unknown must not emit it. Whenever name, age, occupation, or affiliations is updated, description must also be updated to a compact display summary consistent with all resulting structured identity fields. "
            "Output only values that differ from current_cast. Empty current fields are valid and do not require completion. "
            "identity.description is display text, not an authoritative substitute for structured fields. "
            "Put a genuine unresolved contradiction in unresolved_conflicts and omit only the disputed field. "
            "Update a relationship only when the batch explicitly establishes or ends a durable bond, commitment, alliance, kinship, social role, or power relationship. "
            "A single affectionate moment, argument, conversation, cooperation, suspicion, or temporary emotion is not a durable relationship change.\n\n"
            "# Serialization contract\n\n"
            "Return one JSON object matching the exact schema below. Do not rename keys, use arrays in place of objects, add wrapper objects, or add keys not shown. "
            "field_audit must use exactly the eight shown keys for every entity, with only update, keep, or unknown as values. "
            "character_changes is an object keyed by roster character id; do not place id or character_id inside an item. user_changes is one object, never an array. "
            "Omit unchanged profile sections and fields. Use {} and [] when there are no changes. Every non-empty entity change has evidence. "
            "Each evidence item uses a turn inside range, a verbatim factual paraphrase, and fields containing canonical paths for exactly the fields supported by that evidence. "
            "Across an entity, evidence.fields must cover every emitted changed field exactly; examples are profile.identity.age and persistent_status.life_status. "
            "A durable fact written in identity.description must also be present in its canonical structured field; description is never a substitute for name, aliases, age, occupation, or affiliations. "
            "All evidence objects use exactly turn, fact, and fields. Conflict evidence names the disputed field; relationship evidence uses fields=[\"relationship\"]. Relationships use exactly two valid ids and action upsert or remove. Output JSON only.\n\n"
            "# Exact JSON schema template\n\n" + schema
        )
    return (
        "# 任务\n\n"
        "你负责维护互动故事中唯一生效的长期角色档案。对照 current_cast 审查完整的 new_story_batch，只输出已经确认的长期变化。"
        "不得续写、总结、解释或评价剧情。\n\n"
        "# 数据来源与权威\n\n"
        "current_cast 是当前唯一事实，origin_profile 只是只读的初始参考。只有 new_story_batch 能建立新的变化；story_ledger 只能交叉核对连续性，不能单独证明角色变化。"
        "同一批内较晚明确确认的事实覆盖较早的中间状态。所有字段均为可选并允许为空，不得为了补全档案而推断、编造或填写。\n\n"
        "# 收录边界\n\n"
        "只保存预计在当前场景结束后仍然成立的事实。临时情绪、动作、地点、着装、短期目标、认知、持有物和场景活动归剧情账本。"
        "姓名、身份、所属、状态或能力只有在本批明确建立新的长期事实时才能改变。性格与表达方式只有在原文明示长期转变，或多个独立回合持续证明时才能改变。"
        "用户角色只记录用户明确陈述、明确选择或剧情中客观完成的事实；不得推断用户的感受、意图、性格或决定。\n\n"
        "# 字段目录\n\n"
        "profile.identity：name=当前正式姓名，字符串；aliases=已经确认且会持续使用的别名或代号，字符串数组；"
        "description=与结构字段一致的可选展示摘要，字符串；gender=原文明示的长期性别身份，字符串；"
        "age=已经确认的具体年龄，字符串；species=已经确认的种族，字符串；occupation=已经确认的职业或学业阶段，字符串；"
        "affiliations=学校、班级、单位、阵营或组织，字符串数组；story_role=主角、对手、导师等剧情职能，字符串。\n"
        "profile.appearance：summary=长期整体外貌，字符串；features=稳定且有辨识度的外貌特征，字符串数组。\n"
        "profile.personality：summary=长期性格概述，字符串；traits=性格特质，values=价值观，fears=长期恐惧，boundaries=稳定边界，均为字符串数组；motivation=长期动机，字符串。\n"
        "profile.expression：speech_style=稳定说话方式，字符串；habits=稳定习惯，mannerisms=稳定行为特征，均为字符串数组。\n"
        "profile.capabilities：skills=技能，powers=特殊能力，limitations=长期限制，均为字符串数组。\n"
        "persistent_status：life_status=存活、死亡、失踪等长期生命状态，字符串；physical_condition=长期或不可逆身体情况，字符串。\n\n"
        "# 审查与变化规则\n\n"
        "逐一审查 roster 中每个角色和 __user__。reviewed_character_ids 必须且只能包含全部 roster 角色 id，每个一次，不包含 __user__；user_reviewed 固定为 true。"
        "field_audit 必须且只能包含全部 roster 角色 id 和 __user__，每个一次。每个审查字段只能填写 update、keep 或 unknown：本批明确证明新的长期值时填 update；current_cast 仍准确时填 keep；证据不足时填 unknown。"
        "填 update 的字段必须在变更对象中输出对应规范字段并附证据；填 keep 或 unknown 的字段不得输出。name、age、occupation 或 affiliations 任一更新时，description 也必须更新为与最终结构身份一致的简洁展示摘要。"
        "character_changes 与 user_changes 只能输出相对 current_cast 已经确认的差异。当前字段为空也是合法状态，不要求补全。"
        "identity.description 只是展示文本，不是结构事实的替代品。"
        "真实且尚未解决的冲突写入 unresolved_conflicts，只停止更新有争议的字段。"
        "只有本批明确建立或结束长期亲属、承诺、结盟、社会身份、权力关系或其他持续关系时，才能更新 relationship_changes。"
        "单次亲密、争吵、对话、合作、怀疑或临时情绪都不构成长期关系变化。\n\n"
        "# 序列化契约\n\n"
        "只返回一个严格符合下方模板的 JSON 对象。不得改名字段，不得用数组代替对象，不得增加包装层，不得增加模板外字段。"
        "field_audit 必须为每个实体完整输出模板中的八个字段，值只能是 update、keep 或 unknown。"
        "character_changes 必须是以角色 id 为键的对象，条目内部不得再写 id 或 character_id；user_changes 必须是单个对象，不能是数组。"
        "未变化的档案分区和字段不要输出；没有内容时使用 {} 或 []。每个非空角色变更都必须包含 evidence。"
        "每条 evidence 必须包含 range 内的 turn、对该回合事实的准确转述 fact，以及该证据直接支持的规范字段路径 fields。"
        "同一角色全部 evidence.fields 必须恰好覆盖其输出的每个变更字段；字段路径示例：profile.identity.age、persistent_status.life_status。"
        "写入 identity.description 的长期身份事实必须同时写入对应结构字段；description 不能代替 name、aliases、age、occupation 或 affiliations。"
        "所有 evidence 对象必须且只能包含 turn、fact、fields。冲突证据的 fields 填被争议字段；关系证据固定填写 fields=[\"relationship\"]。关系变更必须填写两个有效 id，以及 upsert 或 remove。除 JSON 外不要输出任何内容。\n\n"
        "# 唯一 JSON 结构模板\n\n" + schema
    )
