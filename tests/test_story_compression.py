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

        def merge(previous, batch, start, end, source_tokens, language):
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
        def merge(previous, _batch, start, end, source_tokens, language):
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
        production["story"][2]["text"] = "Edited after compression started."
        server.save_production(production)

        result = server._commit_story_state_batch(
            production["id"], {"facts": ["stale"], "turns": 15}, 15, signature)

        self.assertIsNone(result)
        self.assertFalse(server.load_production(production["id"]).get("story_state"))

    def test_foreground_story_commit_preserves_newer_background_ledger(self):
        production = self.production("prod_foreground_merge", turns=16)
        server.save_production(production)
        foreground = server.load_production(production["id"])
        expected_story_signature = server._story_content_signature(foreground["story"])
        prefix_signature = server._story_prefix_signature(foreground["story"], 15)
        committed = server._commit_story_state_batch(
            production["id"], {"facts": ["Committed memory."], "turns": 15},
            15, prefix_signature)
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
            self.assertTrue(server._schedule_story_state("prod_pending"))
            self.assertTrue(started.wait(2))
            self.assertFalse(server._schedule_story_state("prod_pending"))
            release.set()
            for _ in range(200):
                with server._STORY_STATE_JOBS_LOCK:
                    if "prod_pending" not in server._STORY_STATE_JOBS:
                        break
                time.sleep(0.01)
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

    def test_all_story_ledger_fields_are_injected(self):
        state = {
            "timeline": ["timeline"],
            "facts": ["fact"],
            "open_threads": ["thread"],
            "relationships": ["relationship"],
            "character_state": {"Character": ["state"]},
            "user_state": ["user state"],
            "scene_anchor": ["scene"],
            "objects": ["object"],
            "secrets": ["secret"],
            "style_notes": ["style"],
            "turns": 15,
        }

        block = actor._story_state_block(state, "en")

        for value in ("timeline", "fact", "thread", "relationship", "state",
                      "user state", "scene", "object", "secret", "style"):
            self.assertIn(value, block)


if __name__ == "__main__":
    unittest.main()
