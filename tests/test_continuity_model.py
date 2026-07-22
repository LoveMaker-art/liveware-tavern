import unittest

from continuity_model import (
    _migrate_legacy_story_context,
    ensure_runtime_cast,
    has_meaningful_story_context,
    hydrate_runtime_cards,
    hydrate_user_persona,
    normalize_relationships,
)


class ContinuityModelTests(unittest.TestCase):
    def test_builds_and_hydrates_canonical_runtime_cast(self):
        card = {
            "id": "card_one",
            "name": "One",
            "description": "A character",
            "personality": "calm",
        }
        production = {
            "cards": [card],
            "persona": {"name": "Player", "description": "human"},
            "story_state": {},
        }
        load = lambda card_id: card if card_id == "card_one" else None
        ids = lambda _production: ["card_one"]
        runtime = ensure_runtime_cast(production, load, ids)
        self.assertEqual(runtime["schema_version"], 3)
        self.assertEqual(runtime["characters"][0]["id"], "card_one")
        self.assertEqual(hydrate_runtime_cards(production, load, ids)[0]["name"], "One")
        self.assertEqual(hydrate_user_persona(production)["name"], "Player")

    def test_fresh_world_does_not_create_an_empty_ledger_shell(self):
        card = {
            "id": "card_one",
            "name": "One",
            "description": "A character\n【当前任务】检查旧相册",
        }
        production = {
            "cards": [card],
            "persona": {"name": "Player"},
            "story_state": {},
        }
        load = lambda card_id: card if card_id == "card_one" else None
        ids = lambda _production: ["card_one"]

        ensure_runtime_cast(production, load, ids)
        ensure_runtime_cast(production, load, ids)

        self.assertEqual(production["story_state"], {})
        empty_shell = {
            "scene": {"time": "", "place": "", "participants": []},
            "facts": [],
            "objects": [],
            "secrets": [],
        }
        self.assertEqual(_migrate_legacy_story_context(empty_shell, [card]), {})
        self.assertFalse(has_meaningful_story_context(empty_shell))

    def test_real_legacy_character_state_is_migrated(self):
        card = {
            "id": "card_one",
            "name": "One",
            "state": {
                "location": "钟楼",
                "goal": "找到失踪的守钟人",
                "condition": "左手受伤",
                "knowledge": ["密门藏在钟后"],
            },
        }

        ledger = _migrate_legacy_story_context({}, [card])

        participant = ledger["scene"]["participants"][0]
        self.assertEqual(participant["character_id"], "card_one")
        self.assertEqual(participant["location"], "钟楼")
        self.assertEqual(participant["activity"], "找到失踪的守钟人")
        self.assertEqual(ledger["facts"][0]["content"], "密门藏在钟后")

    def test_existing_story_ledger_is_preserved_and_normalized(self):
        state = {
            "turns": 15,
            "summary": "他们抵达钟楼。",
            "scene": {"time": "午夜", "place": "钟楼", "participants": []},
            "facts": ["钟楼每晚会倒转一次。"],
            "objects": ["铜钥匙"],
            "secrets": ["守钟人仍然活着。"],
        }

        ledger = _migrate_legacy_story_context(state, [])

        self.assertEqual(ledger["turns"], 15)
        self.assertEqual(ledger["summary"], "他们抵达钟楼。")
        self.assertEqual(ledger["scene"]["place"], "钟楼")
        self.assertEqual(ledger["facts"][0]["content"], "钟楼每晚会倒转一次。")
        self.assertEqual(ledger["objects"][0]["name"], "铜钥匙")
        self.assertEqual(ledger["secrets"][0]["content"], "守钟人仍然活着。")

    def test_relationships_deduplicate_participant_pairs(self):
        characters = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        relations = normalize_relationships([
            {"participants": ["a", "b"], "description": "allies"},
            {"participants": ["b", "a"], "description": "duplicate"},
        ], characters)
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["description"], "allies")


if __name__ == "__main__":
    unittest.main()
