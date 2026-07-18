import unittest

from production_views import production_summary


class ProductionViewTests(unittest.TestCase):
    def test_summary_excludes_story_and_runtime_payloads(self):
        production = {
            "id": "prod_1",
            "name": "World",
            "created_at": 10,
            "card_id": "card_a",
            "card_ids": ["card_a", "card_a", "card_b"],
            "story": [
                {"role": "assistant", "text": "opening", "ts": 11},
                {"role": "user", "text": "hello", "ts": 12},
                {"role": "assistant", "text": "reply", "ts": 13},
            ],
            "runtime_cast": {"large": "payload"},
            "story_state": {"large": "payload"},
        }
        result = production_summary(production)
        self.assertEqual(result["turn_count"], 1)
        self.assertEqual(result["last_ts"], 13)
        self.assertEqual(result["story_count"], 3)
        self.assertEqual(result["card_ids"], ["card_a", "card_b"])
        self.assertNotIn("story", result)
        self.assertNotIn("runtime_cast", result)
        self.assertNotIn("story_state", result)


if __name__ == "__main__":
    unittest.main()
