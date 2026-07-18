import unittest

from story_ledger import story_prefix_signature, story_token_prefixes, validated_story_state


def story(turns):
    messages = [{"id": "opening", "role": "assistant", "text": "opening"}]
    for turn in range(1, turns + 1):
        messages.extend(
            [
                {"id": f"u{turn}", "role": "user", "text": f"user {turn}"},
                {"id": f"a{turn}", "role": "assistant", "text": f"assistant {turn}"},
            ]
        )
    return messages


class StoryLedgerTests(unittest.TestCase):
    def test_token_prefixes_scan_messages_by_complete_user_turn(self):
        messages = [
            {"role": "assistant", "text": "opening"},
            {"role": "user", "text": "one"},
            {"role": "assistant", "text": "reply"},
            {"role": "user", "text": "two"},
            {"role": "assistant", "text": "tail"},
        ]
        totals = story_token_prefixes(messages, len)
        self.assertEqual(totals[1], len("openingonereply"))
        self.assertEqual(totals[2], len("openingonereplytwotail"))

    def test_accepts_signed_complete_batch_with_raw_tail(self):
        messages = story(16)
        state = {
            "turns": 15,
            "timeline": ["event"],
            "covered_signature": story_prefix_signature(messages, 15),
        }
        self.assertIs(validated_story_state(state, messages), state)

    def test_rejects_stale_partial_future_and_mismatched_ledgers(self):
        messages = story(16)
        base = {"turns": 15, "timeline": ["event"]}
        cases = (
            {**base, "stale": True},
            {**base, "turns": 14},
            {**base, "turns": 30},
            {**base, "covered_signature": "wrong"},
            {"turns": 15},
        )
        for state in cases:
            with self.subTest(state=state):
                self.assertEqual(validated_story_state(state, messages), {})


if __name__ == "__main__":
    unittest.main()
