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

    def test_skill_release_contains_only_operational_scripts(self):
        archive = ROOT / "dist/tavern-skill.tar.gz"
        manifest_path = ROOT / "dist/skill-manifest.json"
        if not archive.is_file() or not manifest_path.is_file():
            self.skipTest("build release assets before archive validation")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scripts = {
            path
            for path in manifest["managed_files"]
            if path.startswith("skill/scripts/")
        }
        self.assertEqual(
            scripts,
            {
                "skill/scripts/bringup.sh",
                "skill/scripts/provision.sh",
                "skill/scripts/tavern_cli.py",
            },
        )
        with tarfile.open(archive, "r:gz") as package:
            names = {member.name for member in package.getmembers() if member.isfile()}
        self.assertNotIn("skill/SOUL.md", names)
        self.assertEqual(set(manifest["managed_files"]), names)

    def test_persona_profile_has_accessible_detail_entry(self):
        app = (ROOT / "skill/reader/app.js").read_text(encoding="utf-8")
        self.assertIn('data-persona-detail="1"', app)
        self.assertIn('role="button"', app)
        self.assertIn("openPersonaDetailSheet", app)


if __name__ == "__main__":
    unittest.main()
