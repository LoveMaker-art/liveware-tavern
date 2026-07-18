import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill"))
IMPORT_STATE = tempfile.TemporaryDirectory(prefix="tavern-story-import-")
os.environ["TAVERN_STATE_DIR"] = IMPORT_STATE.name

import actor  # noqa: E402
import server  # noqa: E402


def story_with_turns(count, long_turn=None):
    story = [{"id": "opening", "role": "char", "text": "Opening scene."}]
    for turn in range(1, count + 1):
        user_text = "Long semantic turn. " * 1000 if turn == long_turn else f"User turn {turn}."
        story.extend((
            {"id": f"u{turn}", "role": "user", "text": user_text},
            {"id": f"a{turn}", "role": "char", "text": f"Actor turn {turn}."},
        ))
    return story


class StoryCompressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tavern-story-state-test-")
        self.original_state = server.STATE
        self.original_loadout = server._loadout
        self.original_merge = server._merge_story_state_batch
        self.original_batch_budget = server.STORY_STATE_BATCH_TOKEN_BUDGET
        server.STATE = self.temp.name
        for name in ("cards", "worldbooks", "productions"):
            os.makedirs(os.path.join(server.STATE, name), exist_ok=True)
        server._loadout = lambda production: ([], [], {}, "")

    def tearDown(self):
        server.STATE = self.original_state
        server._loadout = self.original_loadout
        server._merge_story_state_batch = self.original_merge
        server.STORY_STATE_BATCH_TOKEN_BUDGET = self.original_batch_budget
        self.temp.cleanup()

    @staticmethod
    def production(pid, turns=30):
        return {
            "id": pid,
            "name": "Compression test",
            "story": story_with_turns(turns, long_turn=15),
            "story_state": {},
            "runtime": {},
            "cards": [],
            "worldbook_ids": [],
        }

    def test_only_confirmed_turns_are_compressible(self):
        self.assertEqual(server._compressible_story_turns(story_with_turns(15)), 14)
        self.assertEqual(server._compressible_story_turns(story_with_turns(16)), 15)
        self.assertEqual(server._compressible_story_turns(story_with_turns(31)), 30)

    def test_thirty_one_turns_commit_two_batches_and_keep_latest_raw(self):
        calls = []

        def merge(previous, batch, start, end, source_tokens, language, roster):
            calls.append((start, end, batch.count("Long semantic turn.") == 1000 if end == 15 else True))
            return {
                "facts": [f"Covered through turn {end}."],
                "turns": end,
                "source_tokens": source_tokens,
                "response_language": language,
            }

        server._merge_story_state_batch = merge
        production = self.production("prod_two_batches", turns=31)
        server.save_production(production)

        server._summarize_story_state(production)
        saved = server.load_production(production["id"])

        self.assertEqual(calls, [(1, 15, True), (16, 30, True)])
        self.assertEqual(saved["story_state"]["turns"], 30)
        raw = actor._fit_history(saved["story"], covered_turns=30)
        self.assertEqual(sum(message.get("role") == "user" for message in raw), 1)
        self.assertEqual(raw[-1]["id"], "a31")

    def test_failed_second_batch_keeps_first_ledger_and_remaining_raw_turns(self):
        def merge(previous, _batch, start, end, source_tokens, language, roster):
            if start == 16:
                return None
            return {
                "facts": ["First batch is valid."],
                "turns": end,
                "source_tokens": source_tokens,
                "response_language": language,
            }

        server._merge_story_state_batch = merge
        production = self.production("prod_failed_second", turns=31)
        server.save_production(production)

        server._summarize_story_state(production)
        saved = server.load_production(production["id"])
        covered = saved["story_state"]["turns"]
        raw = actor._fit_history(saved["story"], covered_turns=covered)

        self.assertEqual(covered, 15)
        self.assertEqual(sum(message.get("role") == "user" for message in raw), 16)
        self.assertIn("turns 16-30", saved["runtime"]["story_state_error"])

    def test_history_edit_rejects_stale_batch_commit(self):
        production = self.production("prod_edit_guard")
        server.save_production(production)
        signature = server._story_prefix_signature(production["story"], 15)
        cast_state = server._ensure_runtime_cast(production)
        expected_cast_revision = int(cast_state.get("revision") or 0)
        next_cast = dict(cast_state)
        next_cast["applied_turn"] = 15
        next_cast["revision"] = expected_cast_revision + 1
        production["story"][2]["text"] = "Edited after compression started."
        server.save_production(production)

        result = server._commit_story_state_batch(
            production["id"], {"facts": ["stale"], "turns": 15}, next_cast,
            15, signature, expected_cast_revision)

        self.assertIsNone(result)
        self.assertFalse(server._story_state_has_memory(
            server.load_production(production["id"]).get("story_state")))

    def test_foreground_story_commit_preserves_newer_background_ledger(self):
        production = self.production("prod_foreground_merge", turns=16)
        server.save_production(production)
        foreground = server.load_production(production["id"])
        expected_story_signature = server._story_content_signature(foreground["story"])
        prefix_signature = server._story_prefix_signature(foreground["story"], 15)
        cast_state = server._ensure_runtime_cast(foreground)
        expected_cast_revision = int(cast_state.get("revision") or 0)
        next_cast = dict(cast_state)
        next_cast["applied_turn"] = 15
        next_cast["revision"] = expected_cast_revision + 1
        committed = server._commit_story_state_batch(
            production["id"], {"facts": ["Committed memory."], "turns": 15},
            next_cast, 15, prefix_signature, expected_cast_revision)
        self.assertIsNotNone(committed)

        foreground["story"].extend((
            {"id": "u17", "role": "user", "text": "User turn 17."},
            {"id": "a17", "role": "char", "text": "Actor turn 17."},
        ))
        server._commit_foreground_story(foreground, expected_story_signature)
        saved = server.load_production(production["id"])

        self.assertEqual(saved["story_state"]["turns"], 15)
        self.assertEqual(saved["story_state"]["covered_signature"], prefix_signature)
        self.assertEqual(saved["story"][-1]["id"], "a17")

    def test_historical_edit_is_rejected(self):
        production = self.production("prod_historical_edit", turns=16)
        server.save_production(production)

        with self.assertRaisesRegex(ValueError, "latest turn"):
            server.ev_edit_message({
                "production_id": production["id"],
                "message_id": "u10",
                "text": "Edited old history.",
                "continue_after": False,
            })

        saved = server.load_production(production["id"])
        self.assertEqual(server._world_turns(saved["story"]), 16)

    def test_empty_ledger_never_hides_raw_history(self):
        story = story_with_turns(16)
        messages = actor.build_messages(
            [], [], {}, story, story_state={"turns": 15}, response_language="en")

        self.assertNotIn("## Story state", messages[0]["content"])
        self.assertEqual(sum(message.get("role") == "user" for message in messages), 16)

    def test_schedule_while_running_is_rechecked(self):
        started = threading.Event()
        release = threading.Event()
        calls = []
        original_maybe = server._maybe_auto_story_state

        def fake_maybe(pid):
            calls.append(pid)
            if len(calls) == 1:
                started.set()
                release.wait(2)

        server._maybe_auto_story_state = fake_maybe
        try:
            production = self.production("prod_pending", turns=16)
            server.save_production(production)
            self.assertTrue(server._schedule_story_state("prod_pending"))
            self.assertTrue(started.wait(2))
            self.assertFalse(server._schedule_story_state("prod_pending"))
            release.set()
            key = ("story_state", "prod_pending")
            for _ in range(200):
                if not server.BACKGROUND_JOBS.is_active(key):
                    break
                time.sleep(0.01)
            self.assertFalse(server.BACKGROUND_JOBS.is_active(key))
            self.assertEqual(calls, ["prod_pending", "prod_pending"])
        finally:
            release.set()
            server._maybe_auto_story_state = original_maybe

    def test_story_state_is_bounded_and_catastrophic_loss_is_rejected(self):
        raw = {
            key: [("x" * 200) + str(i) for i in range(30)]
            for key in ("timeline", "facts", "open_threads", "relationships",
                        "user_state", "scene_anchor", "objects", "secrets", "style_notes")
        }
        raw["character_state"] = {
            "Character " + str(i): [("state" * 50) + str(j) for j in range(12)]
            for i in range(20)
        }
        state = server._normalize_story_state(raw, 15, 1000)

        self.assertLessEqual(server._story_state_chars(state), server.STORY_STATE_MAX_CHARS)
        previous = {
            "facts": ["fact"] * 6,
            "open_threads": ["thread"] * 6,
            "character_state": {"A": ["a"], "B": ["b"], "C": ["c"]},
        }
        self.assertFalse(server._story_state_quality_ok(previous, {"facts": [], "open_threads": []}))

    def test_oversized_batch_splits_only_on_turn_boundaries(self):
        production = self.production("prod_segments", turns=15)
        server.STORY_STATE_BATCH_TOKEN_BUDGET = 20
        segments = server._story_batch_segments(production, 1, 15)

        self.assertGreater(len(segments), 1)
        self.assertEqual(segments[0][0], 1)
        self.assertEqual(segments[-1][1], 15)
        for index, (start, end, text) in enumerate(segments):
            self.assertLessEqual(start, end)
            self.assertTrue(text.strip())
            if index:
                self.assertEqual(start, segments[index - 1][1] + 1)

    def test_plot_ledger_fields_are_injected_and_cast_fields_are_excluded(self):
        state = {
            "timeline": ["timeline"],
            "facts": ["fact"],
            "open_threads": ["thread"],
            "relationships": ["relationship"],
            "character_state": {"Character": ["state"]},
            "user_state": ["user state"],
            "scene": {"time": "scene time", "place": "scene place"},
            "objects": ["object"],
            "secrets": ["secret"],
            "style_notes": ["style"],
            "turns": 15,
        }

        block = actor._story_state_block(state, "en")

        for value in ("timeline", "fact", "thread", "scene time", "scene place",
                      "object", "secret", "style"):
            self.assertIn(value, block)
        for value in ("relationship", "user state"):
            self.assertNotIn(value, block)

    def test_runtime_cast_applies_only_evidence_backed_durable_changes(self):
        previous = {
            "schema_version": 3,
            "applied_turn": 0,
            "revision": 2,
            "characters": [server._runtime_character({
                "id": "card_a",
                "name": "A",
                "description": "Original identity.",
            })],
            "relationships": [],
        }
        raw = {
            "character_changes": {
                "card_a": {
                    "profile": {"identity": {"occupation": "Captain"}},
                    "persistent_status": {"life_status": "Active"},
                    "evidence": [{
                        "turn": 3,
                        "fact": "A formally accepted the captaincy.",
                        "reason": "occupation and life_status changed durably.",
                    }],
                },
            },
            "user_changes": {},
            "relationship_changes": [],
        }

        result = server._normalize_runtime_cast_result(raw, previous, 1, 15)

        self.assertEqual(result["characters"][0]["profile"]["identity"]["occupation"], "Captain")
        self.assertEqual(result["characters"][0]["persistent_status"]["life_status"], "Active")
        self.assertEqual(result["applied_turn"], 15)

    def test_runtime_cast_ignores_profile_change_without_evidence(self):
        previous = {
            "schema_version": 3,
            "applied_turn": 0,
            "revision": 1,
            "characters": [server._runtime_character({
                "id": "card_a",
                "name": "A",
                "description": "Original identity.",
            })],
            "relationships": [],
        }
        raw = {
            "character_changes": {
                "card_a": {"profile": {"identity": {"occupation": "Captain"}}},
            },
        }

        result = server._normalize_runtime_cast_result(raw, previous, 1, 15)

        self.assertEqual(result["characters"][0]["profile"]["identity"]["occupation"], "")

    @staticmethod
    def runtime_cast_audit(decision="unknown"):
        return {
            field: decision
            for field in server._RUNTIME_CAST_AUDIT_FIELDS
        }

    def test_runtime_cast_review_allows_empty_fields_to_remain_unknown(self):
        roster = [{"id": "card_a", "name": "A"}]
        raw = {
            "reviewed_character_ids": ["card_a"],
            "user_reviewed": True,
            "field_audit": {
                "card_a": self.runtime_cast_audit(),
                "__user__": self.runtime_cast_audit(),
            },
            "unresolved_conflicts": [],
            "character_changes": {},
            "user_changes": {},
            "relationship_changes": [],
        }

        self.assertEqual(server._runtime_cast_review_error(raw, roster, 1, 15), "")

    def test_runtime_cast_review_rejects_audit_update_without_change(self):
        roster = [{"id": "card_a", "name": "A"}]
        card_a_audit = self.runtime_cast_audit()
        card_a_audit["occupation"] = "update"
        raw = {
            "reviewed_character_ids": ["card_a"],
            "user_reviewed": True,
            "field_audit": {
                "card_a": card_a_audit,
                "__user__": self.runtime_cast_audit(),
            },
            "unresolved_conflicts": [],
            "character_changes": {},
            "user_changes": {},
            "relationship_changes": [],
        }

        self.assertIn(
            "field_audit updates do not match emitted changes",
            server._runtime_cast_review_error(raw, roster, 1, 15),
        )

    def test_runtime_cast_review_requires_description_with_identity_change(self):
        roster = [{"id": "card_a", "name": "A"}]
        card_a_audit = self.runtime_cast_audit()
        card_a_audit["occupation"] = "update"
        raw = {
            "reviewed_character_ids": ["card_a"],
            "user_reviewed": True,
            "field_audit": {
                "card_a": card_a_audit,
                "__user__": self.runtime_cast_audit(),
            },
            "unresolved_conflicts": [],
            "character_changes": {
                "card_a": {
                    "profile": {"identity": {"occupation": "Captain"}},
                },
            },
            "user_changes": {},
            "relationship_changes": [],
        }

        self.assertIn(
            "identity changes require an updated description",
            server._runtime_cast_review_error(raw, roster, 1, 15),
        )


if __name__ == "__main__":
    unittest.main()
