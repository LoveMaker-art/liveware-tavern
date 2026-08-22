import io
import json
import unittest
from unittest import mock

import actor


class ActorHttpTests(unittest.TestCase):
    def test_traditional_chinese_locale_and_format_contract(self):
        for locale in ("zh-Hant", "zh_Hant"):
            self.assertEqual(actor._language_code(locale), "zh-Hant")
        self.assertEqual(actor._language_code("zh"), "zh")
        self.assertEqual(actor._language_code("fr"), "en")
        rules = actor.format_rules("zh-Hant")
        self.assertIn("全部回覆使用繁體中文", rules)
        self.assertNotIn("全部回复使用简体中文", rules)

    def test_reads_json_within_limit(self):
        self.assertEqual(actor._read_json_response(io.BytesIO(b'{"ok": true}'), 20), {"ok": True})

    def test_rejects_oversized_model_response(self):
        with self.assertRaises(RuntimeError):
            actor._read_json_response(io.BytesIO(b"x" * 11), 10)

    def test_model_timeout_is_bounded(self):
        self.assertGreaterEqual(actor.MODEL_TIMEOUT, 10)
        self.assertLessEqual(actor.MODEL_TIMEOUT, 300)

    def test_thinking_mode_is_only_forwarded_when_explicit(self):
        plain = actor._payload([], 0.1, False)
        controlled = actor._payload(
            [], 0.1, False, request_options={"thinking_mode": False, "unknown": "ignored"})
        self.assertNotIn("thinking_mode", plain)
        self.assertEqual(controlled["thinking_mode"], False)
        self.assertNotIn("unknown", controlled)

    def test_smart_reply_controls_are_strictly_whitelisted(self):
        payload = actor._payload(
            [],
            0.75,
            False,
            request_options={
                "reasoning_effort": "low",
                "response_format": {"type": "json_object", "extra": "ignored"},
                "unknown": "ignored",
            },
        )

        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertNotIn("unknown", payload)

        rejected = actor._payload(
            [],
            0.75,
            False,
            request_options={
                "reasoning_effort": "none",
                "response_format": {"type": "json_schema"},
            },
        )
        self.assertNotIn("reasoning_effort", rejected)
        self.assertNotIn("response_format", rejected)

    def test_content_filter_is_reported_as_upstream_rejection(self):
        response = io.BytesIO(json.dumps({
            "choices": [{"message": {"content": ""}, "finish_reason": "content_filter"}],
            "usage": {},
        }).encode())
        with mock.patch.object(actor, "_request", return_value=object()), mock.patch.object(
                actor.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "上游拒绝"):
                actor._chat_once([{"role": "user", "content": "test"}])

    def test_empty_stop_response_is_rejected(self):
        response = io.BytesIO(json.dumps({
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
            "usage": {},
        }).encode())
        with mock.patch.object(actor, "_request", return_value=object()), mock.patch.object(
                actor.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "空内容"):
                actor._chat_once([{"role": "user", "content": "test"}])


if __name__ == "__main__":
    unittest.main()
