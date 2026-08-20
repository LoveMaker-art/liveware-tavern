import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "app/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
IMPORT_STATE = tempfile.TemporaryDirectory(prefix="tavern-suggest-import-")
os.environ["TAVERN_STATE_DIR"] = IMPORT_STATE.name

import server  # noqa: E402


class SmartReplyTests(unittest.TestCase):
    def test_locale_variants_map_to_the_expected_prompt_language(self):
        self.assertEqual(server._locale_code("zh-CN"), "zh")
        self.assertEqual(server._locale_code("zh_Hans"), "zh")
        self.assertEqual(server._locale_code("zh-Hant"), "zh-Hant")
        self.assertEqual(server._locale_code("zh_TW"), "zh-Hant")
        self.assertEqual(server._locale_code("en-US"), "en")

    def test_context_contains_only_latest_five_dialogue_rounds(self):
        story = [{"role": "char", "text": "开场"}]
        for turn in range(1, 7):
            story.extend((
                {"role": "user", "text": f"用户第{turn}轮"},
                {"role": "char", "text": f"故事第{turn}轮"},
            ))

        context = server._recent_suggestion_context(story, rounds=5, response_language="zh")

        self.assertNotIn("开场", context)
        self.assertNotIn("用户第1轮", context)
        self.assertIn("用户第2轮", context)
        self.assertIn("故事第6轮", context)

    def test_parser_repairs_literal_newlines_locally(self):
        raw = '["*我停下脚步。*\n\n「你听见了吗？」", "回复二。", "回复三。"]'

        suggestions = server._parse_suggestions(raw)

        self.assertEqual(len(suggestions), 3)
        self.assertIn("你听见了吗", suggestions[0])

    def test_parser_accepts_three_tagged_multiline_replies(self):
        raw = """<suggestion>*我停下脚步。*

「你听见了吗？」</suggestion>
<suggestion>回复二。</suggestion>
<suggestion>回复三。</suggestion>"""

        suggestions = server._parse_suggestions(raw)

        self.assertEqual(len(suggestions), 3)
        self.assertIn("你听见了吗", suggestions[0])

    def test_suggest_uses_one_model_call_without_loading_world_data(self):
        story = []
        for turn in range(1, 7):
            story.extend((
                {"role": "user", "text": f"用户第{turn}轮"},
                {"role": "char", "text": f"故事第{turn}轮"},
            ))
        production = {
            "id": "prod_suggest",
            "story": story,
            "response_language": "zh",
            "language_mode": "manual",
        }
        calls = []
        original_load = server.load_production
        original_loadout = server._loadout
        original_chat = server.actor.chat
        original_model = server._active_model
        try:
            server.load_production = lambda _pid: production
            server._loadout = lambda _p: (_ for _ in ()).throw(
                AssertionError("smart replies must not load cards or worldbooks")
            )
            server._active_model = lambda: {"model": "test"}

            def fake_chat(messages, temperature, model, max_tokens=None):
                calls.append(messages)
                self.assertEqual(temperature, 0.75)
                self.assertEqual(max_tokens, 600)
                return (
                    "<suggestion>回复一。</suggestion>"
                    "<suggestion>回复二。</suggestion>"
                    "<suggestion>回复三。</suggestion>"
                )

            server.actor.chat = fake_chat
            result = server.ev_suggest({
                "production_id": production["id"],
                "locale": "zh",
            })
        finally:
            server.load_production = original_load
            server._loadout = original_loadout
            server.actor.chat = original_chat
            server._active_model = original_model

        self.assertEqual(len(calls), 1)
        prompt = calls[0][1]["content"]
        self.assertNotIn("用户第1轮", prompt)
        self.assertIn("用户第2轮", prompt)
        self.assertNotIn("# 角色", prompt)
        self.assertNotIn("# 相关世界设定", prompt)
        self.assertIn("<suggestion>", prompt)
        self.assertEqual(len(result["suggestions"]), 3)

    def test_suggest_prefers_interface_language_over_manual_world_language(self):
        production = {
            "id": "prod_language",
            "story": [
                {"role": "user", "text": "继续"},
                {"role": "char", "text": "故事继续。"},
            ],
            "response_language": "en",
            "language_mode": "manual",
        }
        captured = []
        original_load = server.load_production
        original_chat = server.actor.chat
        original_model = server._active_model
        try:
            server.load_production = lambda _pid: production
            server._active_model = lambda: {"model": "test"}

            def fake_chat(messages, temperature, model, max_tokens=None):
                captured.extend(messages)
                return (
                    "<suggestion>回复一。</suggestion>"
                    "<suggestion>回复二。</suggestion>"
                    "<suggestion>回复三。</suggestion>"
                )

            server.actor.chat = fake_chat
            server.ev_suggest({
                "production_id": production["id"],
                "locale": "zh-CN",
            })
        finally:
            server.load_production = original_load
            server.actor.chat = original_chat
            server._active_model = original_model

        self.assertIn("简体中文", captured[0]["content"])
        self.assertIn("# 最近五轮对话", captured[1]["content"])


if __name__ == "__main__":
    unittest.main()
