import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "tavern_card_import_under_test",
    ROOT / "skill/card_import.py",
)
CARD_IMPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CARD_IMPORT)


class CharacterCardMappingTests(unittest.TestCase):
    def test_structured_description_maps_to_canonical_sections(self):
        card = {
            "name": "林岚",
            "description": """<角色 name="林岚">
<身份>- 城市记者</身份>
<外观>- 黑色短发</外观>
<性格>- 克制\n- 好奇</性格>
<表达>- 句子简短，很少反问</表达>
<能力>- 调查\n- 摄影</能力>
<背景>- 正在追查旧案</背景>
<关系>- 周衡：前搭档，三年前决裂</关系>
</角色>""",
            "scenario": "雨夜重逢",
            "first_mes": "她收起相机，看向门口。",
            "mes_example": "{{char}}: 先说事实。",
            "system_prompt": "保持角色知识边界。",
            "post_history_instructions": "不要替用户行动。",
        }

        profile = CARD_IMPORT.canonical_profile(card)
        entry = CARD_IMPORT.canonical_entry(card)
        performance = CARD_IMPORT.canonical_performance(card)

        self.assertEqual(profile["identity"]["name"], "林岚")
        self.assertEqual(profile["identity"]["description"], "城市记者")
        self.assertEqual(profile["appearance"]["summary"], "黑色短发")
        self.assertEqual(profile["personality"]["traits"], ["克制", "好奇"])
        self.assertEqual(profile["expression"]["speech_style"], "句子简短，很少反问")
        self.assertEqual(profile["capabilities"]["skills"], ["调查", "摄影"])
        self.assertEqual(profile["background"]["summary"], "正在追查旧案")
        self.assertEqual(entry["initial_scenario"], "雨夜重逢")
        self.assertEqual(entry["first_message"], "她收起相机，看向门口。")
        self.assertEqual(entry["example_dialogue"], "{{char}}: 先说事实。")
        self.assertEqual(performance["system_prompt"], "保持角色知识边界。")
        self.assertEqual(performance["post_history_instructions"], "不要替用户行动。")
        self.assertEqual(
            CARD_IMPORT.canonical_relationship_hints(card),
            ["周衡：前搭档，三年前决裂"],
        )

    def test_explicit_profile_overrides_extension_and_legacy_prose(self):
        card = {
            "name": "旧名字",
            "personality": "旧性格散文",
            "extensions": {
                "tavern": {
                    "profile": {
                        "identity": {"name": "扩展名字", "age": "28"},
                        "personality": {"motivation": "寻找真相"},
                    },
                },
            },
            "profile": {
                "identity": {"name": "林岚", "occupation": "记者"},
                "personality": {"summary": "", "traits": ["克制"]},
            },
        }

        profile = CARD_IMPORT.canonical_profile(card)

        self.assertEqual(profile["identity"]["name"], "林岚")
        self.assertEqual(profile["identity"]["age"], "28")
        self.assertEqual(profile["identity"]["occupation"], "记者")
        self.assertEqual(profile["personality"]["summary"], "")
        self.assertEqual(profile["personality"]["traits"], ["克制"])
        self.assertEqual(profile["personality"]["motivation"], "寻找真相")

    def test_normalization_preserves_worldbook_unknown_extensions_and_scene_notes(self):
        source = {
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "vendor_root": {"keep": "root"},
            "data": {
                "name": "林岚",
                "description": "记者\n【当前状态】左臂受伤",
                "character_book": {"name": "雾城", "entries": []},
                "extensions": {"vendor_extension": {"keep": True}},
                "vendor_data": {"keep": "data"},
            },
        }

        normalized = CARD_IMPORT.normalize_card(source)

        self.assertEqual(normalized["character_book"]["name"], "雾城")
        self.assertTrue(normalized["extensions"]["vendor_extension"]["keep"])
        self.assertEqual(normalized["source_format"], "v2")
        self.assertEqual(normalized["source_unknown"]["root"]["vendor_root"]["keep"], "root")
        self.assertEqual(normalized["source_unknown"]["data"]["vendor_data"]["keep"], "data")
        self.assertEqual(CARD_IMPORT.canonical_scene_notes(source["data"]), ["左臂受伤"])
        self.assertIn("profile", normalized)
        self.assertIn("entry", normalized)
        self.assertIn("performance", normalized)

    def test_v1_legacy_aliases_map_without_becoming_v2(self):
        normalized = CARD_IMPORT.normalize_card({
            "char_name": "旧馆主",
            "char_persona": "经营山间旅店的沉静女子。",
            "world_scenario": "暴雨封山。",
            "char_greeting": "她放下灯，看向门外。",
            "example_dialogue": "{{char}}: 今夜别赶路。",
            "legacy_vendor_flag": True,
        })

        self.assertEqual(normalized["source_format"], "v1")
        self.assertEqual(normalized["name"], "旧馆主")
        self.assertEqual(normalized["description"], "经营山间旅店的沉静女子。")
        self.assertEqual(normalized["scenario"], "暴雨封山。")
        self.assertEqual(normalized["first_mes"], "她放下灯，看向门外。")
        self.assertEqual(normalized["mes_example"], "{{char}}: 今夜别赶路。")
        self.assertTrue(normalized["source_unknown"]["data"]["legacy_vendor_flag"])

    def test_v3_metadata_and_unknown_fields_are_preserved(self):
        normalized = CARD_IMPORT.normalize_card({
            "spec": "chara_card_v3",
            "spec_version": "3.0",
            "data": {
                "name": "Mara",
                "description": "An archivist.",
                "assets": [{"type": "icon", "uri": "embeded://portrait.png", "ext": "png"}],
                "creator_notes_multilingual": {"zh-CN": "作者说明"},
                "source": ["https://example.com/card"],
                "group_only_greetings": ["The whole crew looks up."],
                "creation_date": 123,
                "modification_date": 456,
                "future_v4_hint": {"keep": True},
            },
        })

        self.assertEqual(normalized["source_format"], "v3")
        self.assertEqual(normalized["group_only_greetings"], ["The whole crew looks up."])
        self.assertEqual(normalized["source_urls"], ["https://example.com/card"])
        self.assertEqual(normalized["assets"][0]["type"], "icon")
        self.assertEqual(normalized["creator_notes_multilingual"]["zh-CN"], "作者说明")
        self.assertTrue(normalized["source_unknown"]["data"]["future_v4_hint"]["keep"])

    def test_missing_name_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "缺少 name"):
            CARD_IMPORT.normalize_card({
                "spec": "chara_card_v3",
                "spec_version": "3.0",
                "data": {"description": "No name"},
            })

    def test_skill_contract_names_every_canonical_section(self):
        contract = (ROOT / "creative-skills/tavern-world/references/field-mapping.md").read_text(
            encoding="utf-8")
        for field in (
                "profile.identity", "profile.appearance", "profile.personality",
                "profile.expression", "profile.capabilities", "profile.background",
                "entry.initial_scenario", "entry.first_message", "entry.example_dialogue",
                "performance.system_prompt", "performance.post_history_instructions"):
            self.assertIn(field, contract)


if __name__ == "__main__":
    unittest.main()
