import json
from pathlib import Path
import tarfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryHygieneTests(unittest.TestCase):
    def test_legacy_persona_and_tools_are_absent(self):
        forbidden = (
            ROOT / "skill/SOUL.md",
            ROOT / "agentchat/chat_server.py",
            ROOT / "skill/tools/install.sh",
            ROOT / "skill/tools/make_test_card.py",
            ROOT / "skill/tools/smoke.py",
            ROOT / "skill/fixtures/lin.png",
            ROOT / "skill/fixtures/worldbook_rainy_city.json",
        )
        self.assertFalse([str(path.relative_to(ROOT)) for path in forbidden if path.exists()])

    def test_skill_release_contains_complete_split_skill_suite(self):
        archive = ROOT / "dist/tavern-skill.tar.gz"
        manifest_path = ROOT / "dist/skill-manifest.json"
        if not archive.is_file() or not manifest_path.is_file():
            self.skipTest("build release assets before archive validation")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scripts = {
            path
            for path in manifest["managed_files"]
            if "/scripts/" in path
        }
        self.assertEqual(
            scripts,
            {
                "skills/tavern/scripts/bringup.sh",
                "skills/tavern/scripts/provision.sh",
                "skills/tavern/scripts/tavern_cli.py",
            },
        )
        self.assertEqual(manifest["schema"], 3)
        self.assertEqual(manifest["scope"], "tavern-creative-skills")
        self.assertEqual(manifest["install_mode"], "exact-directories")
        self.assertEqual(len(manifest["directories"]), 7)
        self.assertNotIn("obsolete_files", manifest)
        for name in (
                "tavern", "tavern-world", "tavern-cards", "tavern-worldbooks",
                "tavern-story-profile", "tavern-continuity", "tavern-ops"):
            self.assertIn(f"skills/{name}/SKILL.md", manifest["managed_files"])
        with tarfile.open(archive, "r:gz") as package:
            names = {member.name for member in package.getmembers() if member.isfile()}
        self.assertFalse(any(name.endswith("/SOUL.md") for name in names))
        self.assertNotIn("skills/tavern/scripts/install.sh", names)
        self.assertNotIn("skills/tavern/scripts/smoke.py", names)
        self.assertNotIn("skills/tavern/scripts/make_test_card.py", names)
        self.assertEqual(set(manifest["managed_files"]), names)

    def test_release_contains_one_canonical_agents_file(self):
        canonical = ROOT / "updater-skill/references/AGENTS.md"
        self.assertTrue(canonical.is_file())
        self.assertTrue(canonical.read_text(encoding="utf-8").startswith("# AGENTS.md"))
        self.assertFalse((ROOT / "updater-skill/references/agents-block.md").exists())
        self.assertNotIn("tavern-updater:start", canonical.read_text(encoding="utf-8"))

    def test_legacy_baseline_release_is_runtime_only_and_hash_complete(self):
        manifest_path = ROOT / "dist/baseline-v1.14.12-manifest.json"
        archive = ROOT / "dist/tavern-baseline-v1.14.12.tar.gz"
        if not manifest_path.is_file() or not archive.is_file():
            self.skipTest("build release assets before baseline validation")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], 1)
        self.assertEqual(manifest["scope"], "tavern-historical-baseline")
        self.assertEqual(manifest["version"], "1.14.12")
        self.assertEqual(len(manifest["managed_files"]), 12)
        self.assertTrue(all(path.startswith("runtime/") for path in manifest["managed_files"]))
        self.assertFalse(any("tavern-state" in path for path in manifest["managed_files"]))
        with tarfile.open(archive, "r:gz") as package:
            names = {member.name for member in package.getmembers() if member.isfile()}
        self.assertEqual(set(manifest["managed_files"]), names)
        self.assertEqual(set(manifest["files"]), names)

    def test_persona_profile_has_accessible_detail_entry(self):
        app = (ROOT / "skill/reader/app.js").read_text(encoding="utf-8")
        self.assertIn('data-persona-detail="1"', app)
        self.assertIn('role="button"', app)
        self.assertIn("openPersonaDetailSheet", app)


if __name__ == "__main__":
    unittest.main()
