import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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
            for area in ("runtime", "skill", "updater")
        }
        UPDATER.ALLOWED_MANAGED = {
            "runtime": {"server.py"},
            "skill": set(),
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
