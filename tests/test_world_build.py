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
            ROOT / "tools/tavern_cli.py",
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

        prepared = {
            "schema": "tavern-card-preparation/v1",
            "plan_id": "prep_test",
            "summary": {"main_character": "Mara", "profile_ready": True},
            "card": {"id": "card_mara", "name": "Mara"},
            "supporting_cards": [],
        }

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
            if event["type"] == "prepare_card":
                return {"preparation": prepared}
            return {"card": {"id": "card_mara", "name": "Mara"}, "supporting_cards": []}

        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as file:
            json.dump(source, file)
            file.flush()
            with mock.patch.object(cli, "_event", side_effect=fake_event):
                cli.cmd_import_card(SimpleNamespace(
                    source=file.name,
                    confirm=True,
                    new_world=False,
                    name=None,
                ))

        self.assertEqual([event["type"] for event in events], [
            "inspect_card",
            "prepare_card",
            "apply_card_preparation",
        ])
        self.assertEqual(events[1]["source"], "file")
        self.assertTrue(events[2]["confirm"])

    def test_v3_group_greeting_becomes_multi_character_opening_alternative(self):
        script = textwrap.dedent(
            f"""
            import json
            import sys
            sys.path.insert(0, {str(ROOT / "app/backend")!r})
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
            ROOT / "tools/tavern_cli.py",
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
            sys.path.insert(0, {str(ROOT / "app/backend")!r})
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

    def test_external_card_in_world_build_is_forced_through_preparation(self):
        source = {
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "data": {
                "name": "顾临川",
                "description": "顾临川是调查员。林夏是与他合作的记者。归潮港在月蚀时封闭旧码头。",
                "personality": "顾临川冷静谨慎。",
                "first_mes": "顾临川合上记录本。",
            },
        }
        prepared = {
            "main_character": {
                "source_refs": ["field-description", "field-personality"],
                "profile": {
                    "identity": {"name": "顾临川", "description": "归潮港调查员。"},
                    "personality": {"traits": ["冷静", "谨慎"]},
                },
            },
            "supporting_characters": [{
                "name": "林夏",
                "source_refs": ["field-description"],
                "profile": {
                    "identity": {"name": "林夏", "description": "与顾临川合作的记者。"},
                    "personality": {"traits": ["敏锐"]},
                },
            }],
            "worldbook_entries": [{
                "source_refs": ["field-description"],
                "name": "归潮港旧码头",
                "content": "归潮港在月蚀时封闭旧码头。",
                "keys": ["归潮港", "月蚀", "旧码头"],
                "constant": False,
                "priority": 5,
                "category": "rule",
            }],
            "unresolved_source_refs": [],
            "warnings": [],
        }
        script = textwrap.dedent(
            f"""
            import json
            import sys
            sys.path.insert(0, {str(ROOT / "app/backend")!r})
            import server

            server.actor.chat = lambda *args, **kwargs: {json.dumps(prepared, ensure_ascii=False)!r}
            manifest = {{
                "schema": "tavern-world/v1",
                "request_id": "external-preparation-001",
                "world": {{"name": "归潮港", "opening": "潮声逼近。"}},
                "characters": [{{"card": {json.dumps(source, ensure_ascii=False)}, "source": "chub"}}],
                "worldbook_entries": [],
                "persona": {{"name": "我", "description": "调查协作者"}},
            }}
            result = server.ev_build_world({{"manifest": manifest}})
            production = result["production"]
            runtime_cast = production["runtime_cast"]
            worldbooks = [server.load_worldbook(wid) for wid in production["worldbook_ids"]]
            print(json.dumps({{
                "ok": result["verification"]["ok"],
                "cast": [
                    {{"name": item["name"], "profile": item["profile"]}}
                    for item in runtime_cast["characters"]
                ],
                "lore": [
                    entry["content"]
                    for book in worldbooks for entry in (book or {{}}).get("entries") or []
                ],
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
        self.assertTrue(payload["ok"])
        self.assertEqual([item["name"] for item in payload["cast"]], ["顾临川", "林夏"])
        self.assertTrue(all(item["profile"]["identity"]["description"] for item in payload["cast"]))
        self.assertEqual(payload["lore"], ["归潮港在月蚀时封闭旧码头。"])


if __name__ == "__main__":
    unittest.main()
