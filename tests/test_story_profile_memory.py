import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill"))

import story_profile


class StoryProfileMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.memories = self.root / "memories"
        self.old_memories_dir = os.environ.get("TAVERN_HERMES_MEMORIES_DIR")
        os.environ["TAVERN_HERMES_MEMORIES_DIR"] = str(self.memories)
        self.seed = self.root / "actor_self.md"
        self.seed.write_text(
            "# 主理人\n\n# 我对你的了解（个性化 · 会随相处更新）\n\n"
            "- 喜欢克制推进\n\n# 成长记（最近的共同经历）\n\n- （还没有共同经历。）\n",
            encoding="utf-8",
        )

    def tearDown(self):
        if self.old_memories_dir is None:
            os.environ.pop("TAVERN_HERMES_MEMORIES_DIR", None)
        else:
            os.environ["TAVERN_HERMES_MEMORIES_DIR"] = self.old_memories_dir
        self.temp.cleanup()

    def test_sync_replaces_tavern_blocks_and_preserves_other_hermes_content(self):
        profile = story_profile.ensure_profile(self.state, self.seed)
        profile["taste_profile"] = {
            "pacing": ["克制推进"],
            "character_styles": [],
            "relationship_dynamics": [],
            "story_themes": [],
            "narrative_style": [],
            "interaction_preferences": [],
            "boundaries": [],
        }
        profile["shared_story_memory"] = [{
            "world": "雨夜钟楼",
            "covered_turns": 15,
            "events": ["用户与守塔人找到了地下室入口。"],
            "open_threads": ["入口后的房间仍未探索。"],
        }]
        self.memories.mkdir(exist_ok=True)
        (self.memories / "USER.md").write_text("# Existing user facts\n", encoding="utf-8")
        (self.memories / "MEMORY.md").write_text(
            "<!-- TAVERN_SHARED_MEMORY_START -->\n"
            "## 与用户的故事记忆\n- 虚构剧情\n"
            "<!-- TAVERN_SHARED_MEMORY_END -->\n\n"
            "# Existing Hermes memory\n- Keep me\n",
            encoding="utf-8",
        )

        story_profile.sync_hermes_memories(profile, self.memories)

        user = (self.memories / "USER.md").read_text(encoding="utf-8")
        memory = (self.memories / "MEMORY.md").read_text(encoding="utf-8")
        self.assertIn("剧情节奏：克制推进", user)
        self.assertIn("# Existing user facts", user)
        self.assertIn("TAVERN_SHARED_MEMORY_START", memory)
        self.assertIn("### 雨夜钟楼（账本整理至第 15 轮）", memory)
        self.assertIn("用户与守塔人找到了地下室入口。", memory)
        self.assertNotIn("- 虚构剧情", memory)
        self.assertIn("# Existing Hermes memory\n- Keep me", memory)

    def test_story_state_is_projected_into_shared_memory(self):
        production = {
            "id": "world-1",
            "name": "雨夜钟楼",
            "updated_at": 12,
            "story_state": {
                "turns": 30,
                "updated_at": 12,
                "timeline": ["发现钟楼密道。", "确认守塔人的真实身份。"],
                "open_threads": ["密道尽头仍未探索。"],
            },
        }

        worlds = story_profile.sync_story_states(self.state, self.seed, [production])

        self.assertEqual(worlds[0]["covered_turns"], 30)
        persisted = json.loads((self.state / story_profile.PROFILE_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(persisted["shared_story_memory"][0]["world"], "雨夜钟楼")
        memory = (self.memories / "MEMORY.md").read_text(encoding="utf-8")
        self.assertIn("确认守塔人的真实身份。", memory)
        self.assertIn("密道尽头仍未探索。", memory)


if __name__ == "__main__":
    unittest.main()
