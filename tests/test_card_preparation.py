import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

import card_preparation


ROOT = Path(__file__).resolve().parents[1]


def mixed_card():
    return {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "data": {
            "name": "苏玉鸾",
            "description": "",
            "personality": "",
            "scenario": "春日的旧书院。",
            "first_mes": "苏玉鸾合上书，抬眼看向来客。",
            "character_book": {
                "name": "旧书院",
                "entries": [
                    {
                        "name": "苏玉鸾",
                        "keys": ["苏玉鸾"],
                        "content": "苏玉鸾是书院先生，二十七岁，克制而敏锐，说话简洁。",
                    },
                    {
                        "name": "沈砚",
                        "keys": ["沈砚"],
                        "content": "沈砚是负责送信的青年，谨慎、守诺。",
                    },
                    {
                        "name": "书院规矩",
                        "keys": ["书院", "禁书库"],
                        "content": "旧书院的禁书库只在月圆之夜开放。",
                    },
                ],
            },
        },
    }


def model_result():
    return {
        "main_character": {
            "source_entry_ids": ["entry-0"],
            "profile": {
                "identity": {
                    "name": "苏玉鸾", "aliases": [],
                    "description": "旧书院先生。", "gender": "", "age": "27",
                    "species": "", "occupation": "书院先生",
                    "affiliations": ["旧书院"], "story_role": "核心角色",
                },
                "appearance": {"summary": "", "features": [], "attire": []},
                "personality": {
                    "summary": "", "traits": ["克制", "敏锐"], "values": [],
                    "motivation": "", "fears": [], "boundaries": [],
                },
                "expression": {"speech_style": "简洁", "habits": [], "mannerisms": []},
                "capabilities": {"skills": [], "powers": [], "limitations": []},
                "background": {"summary": "", "key_history": []},
            },
            "entry": {
                "initial_scenario": "春日的旧书院。",
                "first_message": "苏玉鸾合上书，抬眼看向来客。",
                "example_dialogue": "",
            },
            "performance": {"system_prompt": "", "post_history_instructions": ""},
        },
        "supporting_characters": [{
            "name": "沈砚",
            "source_entry_ids": ["entry-1"],
            "profile": {
                "identity": {"name": "沈砚", "description": "负责送信的青年。", "occupation": "信使"},
                "personality": {"traits": ["谨慎", "守诺"]},
            },
        }],
        "worldbook_entries": [{
            "source_entry_ids": ["entry-2"],
            "name": "书院规矩",
            "content": "旧书院的禁书库只在月圆之夜开放。",
            "keys": ["书院", "禁书库"],
            "constant": False,
            "priority": 6,
            "category": "rule",
        }],
        "unresolved_entry_ids": [],
        "warnings": [],
    }


class CardPreparationTests(unittest.TestCase):
    def test_mixed_embedded_lore_is_split_without_blank_main_profile(self):
        calls = []

        def chat(messages, **kwargs):
            calls.append((messages, kwargs))
            return json.dumps(model_result(), ensure_ascii=False)

        plan = card_preparation.prepare_card(mixed_card(), chat)

        self.assertEqual(len(calls), 1)
        self.assertEqual(plan["card"]["profile"]["identity"]["name"], "苏玉鸾")
        self.assertEqual(plan["card"]["profile"]["identity"]["occupation"], "书院先生")
        self.assertIn("<身份>", plan["card"]["description"])
        self.assertEqual([card["name"] for card in plan["supporting_cards"]], ["沈砚"])
        entries = plan["card"]["character_book"]["entries"]
        self.assertEqual(len(entries), 1)
        self.assertIn("禁书库", entries[0]["content"])
        self.assertNotIn("苏玉鸾是", entries[0]["content"])
        self.assertNotIn("沈砚是", entries[0]["content"])
        self.assertEqual(plan["summary"]["main_character_entries"], 1)
        self.assertEqual(plan["summary"]["worldbook_entries"], 1)
        self.assertEqual(plan["summary"]["supporting_characters"], ["沈砚"])
        self.assertTrue(plan["plan_id"].startswith("prep_"))
        card_preparation.validate_plan(plan)

    def test_invalid_first_response_retries_same_model_once(self):
        responses = [
            json.dumps({**model_result(), "worldbook_entries": []}, ensure_ascii=False),
            json.dumps(model_result(), ensure_ascii=False),
        ]

        def chat(messages, **kwargs):
            return responses.pop(0)

        plan = card_preparation.prepare_card(mixed_card(), chat)

        self.assertFalse(responses)
        self.assertEqual(plan["summary"]["worldbook_entries"], 1)

    def test_empty_profile_is_rejected_without_fallback_card(self):
        result = model_result()
        result["main_character"]["profile"] = {"identity": {"name": "苏玉鸾"}}

        with self.assertRaisesRegex(ValueError, "主角色资料"):
            card_preparation.prepare_card(
                mixed_card(), lambda *_args, **_kwargs: json.dumps(result, ensure_ascii=False))

    def test_modified_plan_is_rejected(self):
        plan = card_preparation.prepare_card(
            mixed_card(), lambda *_args, **_kwargs: json.dumps(model_result(), ensure_ascii=False))
        changed = copy.deepcopy(plan)
        changed["card"]["name"] = "被修改"

        with self.assertRaisesRegex(ValueError, "已被修改"):
            card_preparation.validate_plan(changed)

    def test_server_preview_is_read_only_and_confirmed_apply_is_idempotent(self):
        source = json.dumps(mixed_card(), ensure_ascii=False)
        response = json.dumps(model_result(), ensure_ascii=False)
        script = textwrap.dedent(
            f"""
            import json
            import sys
            sys.path.insert(0, {str(ROOT / 'skill')!r})
            import server

            server.actor.chat = lambda *args, **kwargs: {response!r}
            source = json.loads({source!r})
            before = {{
                "cards": len(server.STATE_STORE.list("cards")),
                "worldbooks": len(server.STATE_STORE.list("worldbooks")),
            }}
            plan = server.ev_prepare_card({{"card": source, "source": "file"}})["preparation"]
            preview = {{
                "cards": len(server.STATE_STORE.list("cards")),
                "worldbooks": len(server.STATE_STORE.list("worldbooks")),
            }}
            first = server.ev_apply_card_preparation({{
                "preparation": plan,
                "confirm": True,
            }})
            second = server.ev_apply_card_preparation({{
                "preparation": plan,
                "confirm": True,
            }})
            after = {{
                "cards": len(server.STATE_STORE.list("cards")),
                "worldbooks": len(server.STATE_STORE.list("worldbooks")),
            }}
            print(json.dumps({{
                "before": before,
                "preview": preview,
                "after": after,
                "main_profile": first["card"]["profile"],
                "supporting": [item["name"] for item in first["supporting_cards"]],
                "reused": second["reused"],
            }}, ensure_ascii=False))
            """
        )
        with tempfile.TemporaryDirectory() as state:
            env = dict(os.environ)
            env["TAVERN_STATE_DIR"] = state
            env["TAVERN_MODEL_KEY"] = ""
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["before"], {"cards": 0, "worldbooks": 0})
        self.assertEqual(payload["preview"], payload["before"])
        self.assertEqual(payload["after"], {"cards": 2, "worldbooks": 1})
        self.assertEqual(payload["supporting"], ["沈砚"])
        self.assertEqual(payload["main_profile"]["identity"]["occupation"], "书院先生")
        self.assertTrue(payload["reused"])


if __name__ == "__main__":
    unittest.main()
