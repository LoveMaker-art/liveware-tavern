import json
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class CompleteWorldBuildTests(unittest.TestCase):
    def test_external_v3_import_inspects_before_writing(self):
        spec = importlib.util.spec_from_file_location(
            "tavern_cli_external_card_test",
            ROOT / "skill/tools/tavern_cli.py",
        )
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        source = {
            "spec": "chara_card_v3",
            "spec_version": "3.0",
            "data": {
                "name": "Mara",
                "description": "An archivist.",
                "group_only_greetings": ["Everyone looks up."],
            },
        }
        events = []

        def fake_event(event):
            events.append(event)
            if event["type"] == "inspect_card":
                return {
                    "inspection": {
                        "format": "v3",
                        "spec": "chara_card_v3",
                        "spec_version": "3.0",
                        "name": "Mara",
                        "warnings": [],
                    },
                }
            return {"card": {"id": "card_mara", "name": "Mara"}}

        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as file:
            json.dump(source, file)
            file.flush()
            with mock.patch.object(cli, "_event", side_effect=fake_event):
                cli.cmd_import_card(SimpleNamespace(
                    source=file.name,
                    new_world=False,
                    name=None,
                ))

        self.assertEqual([event["type"] for event in events], [
            "inspect_card",
            "import_card_json",
        ])
        self.assertEqual(events[1]["source"], "file")

    def test_v3_group_greeting_becomes_multi_character_opening_alternative(self):
        script = textwrap.dedent(
            f"""
            import json
            import sys
            sys.path.insert(0, {str(ROOT / "skill")!r})
            import server

            first = server.ev_import_card_json({{"card": {{
                "spec": "chara_card_v3",
                "spec_version": "3.0",
                "data": {{
                    "name": "Mara",
                    "description": "An archivist.",
                    "first_mes": "Mara looks up.",
                    "group_only_greetings": ["Everyone in the archive looks up."],
                }},
            }}}})["card"]
            second = server.ev_import_card_json({{"card": {{
                "spec": "chara_card_v2",
                "data": {{"name": "Ivo", "description": "A courier."}},
            }}}})["card"]
            production = server.ev_create_production({{
                "card_ids": [first["id"], second["id"]],
                "name": "Archive",
            }})["production"]
            print(json.dumps(production["story"][0]))
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
        opening = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(opening["text"], "Everyone in the archive looks up.")
        self.assertIn("Mara looks up.", opening["alts"])

    def test_json_apply_output_contains_only_one_json_document(self):
        spec = importlib.util.spec_from_file_location(
            "tavern_cli_world_build_test",
            ROOT / "skill/tools/tavern_cli.py",
        )
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        manifest = {
            "schema": "tavern-world/v1",
            "world": {"name": "测试世界", "opening": "开场。"},
            "characters": [{
                "card": {
                    "spec": "chara_card_v2",
                    "data": {"name": "林舟", "first_mes": "开场。"},
                }
            }],
            "worldbook_entries": [],
            "persona": {"name": "我", "description": "旅人"},
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as file:
            json.dump(manifest, file, ensure_ascii=False)
            file.flush()
            event_result = {
                "production": {"id": "prod_test", "name": "测试世界"},
                "request_id": "test-request",
                "reused": False,
                "verification": {"ok": True},
            }
            output = io.StringIO()
            with mock.patch.object(cli, "_event", return_value=event_result), \
                    mock.patch.object(cli, "_maybe_liveware_entry", return_value=None), \
                    mock.patch("sys.stdout", output):
                cli.cmd_build_world(SimpleNamespace(
                    manifest=file.name,
                    apply=True,
                    confirm=True,
                    request_id="test-request",
                    json=True,
                ))

        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["world_id"], "prod_test")

    def test_atomic_build_is_idempotent_and_rolls_back_failure(self):
        script = textwrap.dedent(
            f"""
            import json
            import sys
            sys.path.insert(0, {str(ROOT / "skill")!r})
            import server

            def card(name, opening):
                return {{
                    "spec": "chara_card_v2",
                    "spec_version": "2.0",
                    "data": {{
                        "name": name,
                        "description": name + "的身份与背景。",
                        "personality": "克制、敏锐。",
                        "scenario": "雨夜的旧车站。",
                        "first_mes": opening,
                    }},
                }}

            manifest = {{
                "schema": "tavern-world/v1",
                "request_id": "test-world-build-001",
                "world": {{"name": "雨夜车站", "opening": "雨落在站台上。"}},
                "characters": [
                    {{"card": card("林舟", "他站在雨里。")}},
                    {{"card": card("沈遥", "她合上伞。")}},
                ],
                "worldbook_entries": [
                    {{
                        "name": "旧车站",
                        "content": "这座车站只在午夜开放。",
                        "constant": True,
                        "keys": [],
                    }}
                ],
                "persona": {{
                    "profile": {{
                        "identity": {{
                            "name": "顾言",
                            "aliases": [],
                            "age": "",
                            "occupation": "",
                            "affiliations": [],
                            "story_role": "归乡者",
                        }},
                        "description": "刚回到故乡。",
                    }}
                }},
            }}

            first = server.ev_build_world({{"manifest": manifest}})
            second = server.ev_build_world({{"manifest": manifest}})
            before = {{
                "productions": len(server.STATE_STORE.list("productions")),
                "cards": len(server.STATE_STORE.list("cards")),
                "worldbooks": len(server.STATE_STORE.list("worldbooks")),
                "active": server._get_state().get("active_production_id"),
            }}

            failed = False
            broken = {{
                "schema": "tavern-world/v1",
                "request_id": "test-world-build-002",
                "world": {{"name": "不完整世界"}},
                "characters": [{{"card": card("无声者", "")}}],
                "worldbook_entries": [
                    {{"content": "用于回滚测试。", "constant": True, "keys": []}}
                ],
                "persona": {{"name": "我", "description": "测试身份"}},
            }}
            try:
                server.ev_build_world({{"manifest": broken}})
            except ValueError:
                failed = True

            after = {{
                "productions": len(server.STATE_STORE.list("productions")),
                "cards": len(server.STATE_STORE.list("cards")),
                "worldbooks": len(server.STATE_STORE.list("worldbooks")),
                "active": server._get_state().get("active_production_id"),
            }}
            print(json.dumps({{
                "first_ok": first["verification"]["ok"],
                "second_reused": second["reused"],
                "same_world": first["production"]["id"] == second["production"]["id"],
                "failed": failed,
                "before": before,
                "after": after,
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
        self.assertTrue(payload["first_ok"])
        self.assertTrue(payload["second_reused"])
        self.assertTrue(payload["same_world"])
        self.assertTrue(payload["failed"])
        self.assertEqual(payload["before"], payload["after"])
        self.assertEqual(payload["before"]["productions"], 1)
        self.assertEqual(payload["before"]["cards"], 2)


if __name__ == "__main__":
    unittest.main()
