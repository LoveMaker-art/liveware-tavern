import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "tavern_updater_under_test",
    ROOT / "updater-skill/scripts/update.py",
)
UPDATER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UPDATER)


class UpdaterMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tavern-updater-test-")
        self.root = Path(self.temp.name)
        UPDATER.UPDATE_ROOT = self.root / "updates"
        UPDATER.BASELINE = UPDATER.UPDATE_ROOT / "baseline"
        UPDATER.BACKUPS = UPDATER.UPDATE_ROOT / "backups"
        UPDATER.PLANS = UPDATER.UPDATE_ROOT / "plans"
        UPDATER.STATE = UPDATER.UPDATE_ROOT / "state.json"
        UPDATER.LOCK = UPDATER.UPDATE_ROOT / "update.lock"
        UPDATER.TARGETS = {
            area: self.root / "installed" / area
            for area in ("runtime", "skills", "updater")
        }
        UPDATER.AGENTS_PATH = self.root / "installed/AGENTS.md"
        UPDATER.SKIP_SERVICE = True
        UPDATER.ALLOWED_MANAGED = {
            "runtime": {"server.py"},
            "skills": set(UPDATER.CREATIVE_SKILL_FILES),
            "updater": set(),
        }

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(root, name, content):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_official_skill_stage(self, root, marker="release"):
        for name in UPDATER.CREATIVE_SKILL_FILES:
            self.write(root, name, marker + ":" + name + "\n")

    def test_official_target_not_merged_install_becomes_next_baseline(self):
        base = self.root / "base/runtime"
        current = self.root / "current/runtime"
        incoming_v2 = self.root / "incoming-v2/runtime"
        staged_v2 = self.root / "staged-v2/runtime"
        self.write(base, "server.py", "base\nshared\n")
        self.write(current, "server.py", "base\nshared\nlocal customization\n")
        self.write(incoming_v2, "server.py", "upstream v2\nbase\nshared\n")

        report, conflicts = UPDATER.merge_area(
            "runtime", base, current, incoming_v2, staged_v2, {"server.py"})
        self.assertFalse(conflicts)
        self.assertEqual(report[0]["status"], "merged")
        self.assertIn("local customization", (staged_v2 / "server.py").read_text())

        upstream = self.root / "upstream"
        self.write(upstream / "runtime", "server.py", (incoming_v2 / "server.py").read_text())
        UPDATER.write_baseline(upstream, ["runtime/server.py"], "2.0.0")
        self.assertEqual(
            (UPDATER.BASELINE / "runtime/server.py").read_text(),
            (incoming_v2 / "server.py").read_text(),
        )

        incoming_v3 = self.root / "incoming-v3/runtime"
        staged_v3 = self.root / "staged-v3/runtime"
        self.write(incoming_v3, "server.py", "upstream v3\nbase\nshared\n")
        _report, conflicts = UPDATER.merge_area(
            "runtime",
            UPDATER.BASELINE / "runtime",
            staged_v2,
            incoming_v3,
            staged_v3,
            {"server.py"},
        )
        self.assertFalse(conflicts)
        self.assertIn("upstream v3", (staged_v3 / "server.py").read_text())
        self.assertIn("local customization", (staged_v3 / "server.py").read_text())

    def test_missing_trusted_baseline_never_overwrites_differing_file(self):
        base = self.root / "empty-base/runtime"
        current = self.root / "current/runtime"
        incoming = self.root / "incoming/runtime"
        output = self.root / "output/runtime"
        base.mkdir(parents=True)
        self.write(current, "server.py", "local version\n")
        self.write(incoming, "server.py", "new official version\n")

        report, conflicts = UPDATER.merge_area(
            "runtime", base, current, incoming, output, {"server.py"})
        self.assertEqual(conflicts, ["runtime/server.py"])
        self.assertEqual(report[0]["status"], "conflict")
        self.assertFalse((output / "server.py").exists())

    def test_cached_baseline_rejects_tampering(self):
        upstream = self.root / "upstream"
        self.write(upstream / "runtime", "server.py", "official\n")
        managed = ["runtime/server.py"]
        UPDATER.write_baseline(upstream, managed, "2.0.0")
        self.assertEqual(UPDATER.cached_baseline("2.0.0", managed), UPDATER.BASELINE)

        (UPDATER.BASELINE / "runtime/server.py").write_text("tampered\n", encoding="utf-8")
        self.assertIsNone(UPDATER.cached_baseline("2.0.0", managed))

    def test_official_skills_are_replaced_exactly_and_custom_skill_is_preserved(self):
        staged = self.root / "staged/skills"
        self.write_official_skill_stage(staged)
        self.write(UPDATER.TARGETS["skills"], "tavern/SKILL.md", "old router\n")
        self.write(UPDATER.TARGETS["skills"], "tavern/references/legacy.md", "stale\n")
        self.write(UPDATER.TARGETS["skills"], "custom-skill/SKILL.md", "custom\n")

        UPDATER.replace_official_skills(staged)

        self.assertFalse((UPDATER.TARGETS["skills"] / "tavern/references/legacy.md").exists())
        self.assertEqual((UPDATER.TARGETS["skills"] / "custom-skill/SKILL.md").read_text(), "custom\n")
        self.assertEqual(UPDATER.official_skill_hashes(), UPDATER.official_skill_hashes(staged))

    def test_skill_review_reports_stale_official_files_without_conflict(self):
        incoming = self.root / "incoming/skills"
        output = self.root / "output/skills"
        self.write_official_skill_stage(incoming)
        self.write(UPDATER.TARGETS["skills"], "tavern/references/legacy.md", "local legacy\n")

        report, conflicts = UPDATER.stage_official_skills(
            incoming, output, UPDATER.CREATIVE_SKILL_FILES)

        self.assertFalse(conflicts)
        self.assertIn("replaced", {item["status"] for item in report})
        self.assertEqual(UPDATER.tree_hashes(output), UPDATER.tree_hashes(incoming))

    def test_skill_fingerprint_covers_unlisted_files_inside_official_directories(self):
        path = self.write(UPDATER.TARGETS["skills"], "tavern/local-note.md", "one\n")
        before = UPDATER.managed_fingerprint(["runtime/server.py"])
        path.write_text("two\n", encoding="utf-8")
        after = UPDATER.managed_fingerprint(["runtime/server.py"])
        self.assertNotEqual(before, after)

    def test_agents_file_is_replaced_in_full(self):
        unpacked = self.root / "unpacked"
        plan = self.root / "plan"
        self.write(self.root / "installed", "AGENTS.md", "# Local operations\n\nKeep this note.\n")
        desired = "# AGENTS.md\n\nOfficial routing only.\n"
        self.write(unpacked / "updater/references", "AGENTS.md", desired)

        staged, report = UPDATER.stage_agents(unpacked, plan)

        self.assertEqual(staged.read_text(), desired)
        self.assertNotIn("Keep this note.", staged.read_text())
        self.assertEqual(report["status"], "upstream")

    def test_malformed_release_agents_file_is_rejected(self):
        unpacked = self.root / "unpacked"
        self.write(unpacked / "updater/references", "AGENTS.md", "not canonical\n")

        with self.assertRaisesRegex(RuntimeError, "malformed"):
            UPDATER.stage_agents(unpacked, self.root / "plan")

    def test_complete_skill_directories_and_agents_are_restored_on_rollback(self):
        managed = ["runtime/server.py"] + ["skills/" + name for name in UPDATER.CREATIVE_SKILL_FILES]
        self.write(UPDATER.TARGETS["runtime"], "server.py", "runtime\n")
        self.write(UPDATER.TARGETS["skills"], "tavern/scripts/smoke.py", "legacy\n")
        self.write(UPDATER.TARGETS["skills"], "custom-skill/SKILL.md", "custom\n")
        self.write(self.root / "installed", "AGENTS.md", "local agents\n")
        backup = UPDATER.backup_current("1.19.7", managed)

        staged = self.root / "staged/skills"
        self.write_official_skill_stage(staged)
        UPDATER.replace_official_skills(staged)
        UPDATER.atomic_write_text(UPDATER.AGENTS_PATH, "updated agents\n")
        UPDATER.restore(backup)

        self.assertEqual((UPDATER.TARGETS["skills"] / "tavern/scripts/smoke.py").read_text(), "legacy\n")
        self.assertFalse((UPDATER.TARGETS["skills"] / "tavern-world").exists())
        self.assertEqual((UPDATER.TARGETS["skills"] / "custom-skill/SKILL.md").read_text(), "custom\n")
        self.assertEqual(UPDATER.AGENTS_PATH.read_text(), "local agents\n")

    def test_default_report_omits_file_hashes(self):
        managed = ["runtime/server.py"]
        self.write(UPDATER.TARGETS["runtime"], "server.py", "installed\n")
        plan_id = "concise-report"
        plan_dir = UPDATER.PLANS / plan_id
        plan_dir.mkdir(parents=True)
        plan = {
            "plan_id": plan_id,
            "installed": "1.19.2",
            "target": "1.19.3",
            "ready": True,
            "baseline_trusted": True,
            "baseline_source": "installed-release",
            "baseline_warning": "",
            "validation": {"python": 1, "shell": 0, "javascript": 0},
            "counts": {"upstream": 1},
            "categories": {"backend": 1},
            "conflicts": [],
            "metadata_normalized": [],
            "managed_files": managed,
            "current_fingerprint": UPDATER.managed_fingerprint(managed),
            "files": [{
                "path": "runtime/server.py",
                "category": "backend",
                "status": "upstream",
                "base_sha256": "base",
                "installed_sha256": "installed",
                "release_sha256": "release",
                "metadata_normalized": False,
            }],
        }
        (plan_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            UPDATER.command_report.__wrapped__(SimpleNamespace(plan=plan_id, details=False))
        report = json.loads(output.getvalue())

        self.assertFalse(report["details"])
        self.assertEqual(
            report["changes"],
            [{"path": "runtime/server.py", "category": "backend", "status": "upstream"}],
        )
        self.assertNotIn("installed_sha256", output.getvalue())


class RuntimeStateBoundaryTests(unittest.TestCase):
    def test_existing_actor_profile_is_never_migrated_on_read(self):
        with tempfile.TemporaryDirectory(prefix="tavern-state-test-") as temp:
            state = Path(temp)
            profile = state / "actor_self.md"
            original = "# Personal preference\n\n- Preserve this exact text.\n"
            profile.write_text(original, encoding="utf-8")
            env = os.environ.copy()
            env["TAVERN_STATE_DIR"] = str(state)
            command = (
                "import server; "
                "assert server.actor_self_text() == " + repr(original)
            )
            subprocess.run(
                [sys.executable, "-c", command],
                cwd=ROOT / "skill",
                env=env,
                check=True,
            )
            self.assertEqual(profile.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
