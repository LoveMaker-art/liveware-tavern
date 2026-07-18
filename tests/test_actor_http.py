import io
import unittest

import actor


class ActorHttpTests(unittest.TestCase):
    def test_reads_json_within_limit(self):
        self.assertEqual(actor._read_json_response(io.BytesIO(b'{"ok": true}'), 20), {"ok": True})

    def test_rejects_oversized_model_response(self):
        with self.assertRaises(RuntimeError):
            actor._read_json_response(io.BytesIO(b"x" * 11), 10)

    def test_model_timeout_is_bounded(self):
        self.assertGreaterEqual(actor.MODEL_TIMEOUT, 10)
        self.assertLessEqual(actor.MODEL_TIMEOUT, 300)


if __name__ == "__main__":
    unittest.main()
