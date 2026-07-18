import unittest

from continuity_model import (
    ensure_runtime_cast,
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
