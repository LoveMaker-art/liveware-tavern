import os
from pathlib import Path
import sys
import tempfile
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
        server.STATE = self.temp.name
        for name in ("cards", "worldbooks", "productions"):
            os.makedirs(os.path.join(server.STATE, name), exist_ok=True)
        server._loadout = lambda production: ([], [], {}, "")

    def tearDown(self):
        server.STATE = self.original_state
        server._loadout = self.original_loadout
        server._merge_story_state_batch = self.original_merge
        self.temp.cleanup()

    @staticmethod
    def production(pid):
        return {
            "id": pid,
            "name": "Compression test",
            "story": story_with_turns(30, long_turn=15),
            "story_state": {},
            "runtime": {},
            "cards": [],
            "worldbook_ids": [],
        }

    def test_thirty_uncompressed_turns_commit_two_complete_batches(self):
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
        production = self.production("prod_two_batches")
        server.save_production(production)

        server._summarize_story_state(production)
        saved = server.load_production(production["id"])

        self.assertEqual(calls, [(1, 15, True), (16, 30, True)])
        self.assertEqual(saved["story_state"]["turns"], 30)
        self.assertEqual(actor._fit_history(saved["story"], covered_turns=30), [])

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
        production = self.production("prod_failed_second")
        server.save_production(production)

        server._summarize_story_state(production)
        saved = server.load_production(production["id"])
        covered = saved["story_state"]["turns"]
        raw = actor._fit_history(saved["story"], covered_turns=covered)

        self.assertEqual(covered, 15)
        self.assertEqual(sum(message.get("role") == "user" for message in raw), 15)
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
