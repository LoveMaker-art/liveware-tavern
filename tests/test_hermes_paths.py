import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "skills/tavern/scripts/tavern_cli.py"


def load_cli(name):
    spec = importlib.util.spec_from_file_location(name, CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HermesPathTests(unittest.TestCase):
    def test_cli_uses_active_hermes_home(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "profile-home"
            env = {
                "HERMES_HOME": str(home),
                "TAVERN_CONSOLE": "http://127.0.0.1:9876",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                for name in (
                    "TAVERN_DATA_ROOT", "TAVERN_APP_DIR", "TAVERN_STATE_DIR",
                    "TAVERN_APPS_FILE", "TAVERN_SKILL_ROOT", "TAVERN_AGENTS_FILE",
                    "TAVERN_STARTER_DIR",
                ):
                    os.environ.pop(name, None)
                cli = load_cli("tavern_cli_profile_path")

            self.assertEqual(Path(cli.HERMES_HOME), home)
            self.assertEqual(Path(cli.TAVERN_DATA_ROOT), home)
            self.assertEqual(Path(cli.TAVERN_APP_DIR), home / "apps/tavern-runtime")
            self.assertEqual(Path(cli.TAVERN_STATE_DIR), home / "tavern-state")
            self.assertEqual(Path(cli.TAVERN_SKILL_ROOT), home / "skills")
            self.assertEqual(Path(cli.TAVERN_AGENTS_FILE), home / "AGENTS.md")
            self.assertEqual(cli.CONSOLE, "http://127.0.0.1:9876")

    def test_cli_allows_standalone_path_overrides(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = {
                "HERMES_HOME": str(root / "hermes"),
                "TAVERN_DATA_ROOT": str(root / "data"),
                "TAVERN_APP_DIR": str(root / "checkout/app"),
                "TAVERN_STATE_DIR": str(root / "state"),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                cli = load_cli("tavern_cli_standalone_paths")

            self.assertEqual(Path(cli.TAVERN_DATA_ROOT), root / "data")
            self.assertEqual(Path(cli.TAVERN_APP_DIR), root / "checkout/app")
            self.assertEqual(Path(cli.TAVERN_STATE_DIR), root / "state")

    def test_runtime_uses_the_same_profile_root(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "runtime-profile"
            env = dict(os.environ)
            env["HERMES_HOME"] = str(home)
            env.pop("TAVERN_DATA_ROOT", None)
            env.pop("TAVERN_STATE_DIR", None)
            env["PYTHONPATH"] = str(ROOT / "app/backend")
            script = (
                "import actor,json,server,story_profile;"
                "print(json.dumps({"
                "'actor_home':str(actor.HERMES_HOME),"
                "'config':str(actor.HERMES_CONFIG_PATH),"
                "'server_home':server.HERMES_HOME,"
                "'state':server.STATE,"
                "'profile_home':str(story_profile.HERMES_HOME)}))"
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
            paths = json.loads(result.stdout.strip().splitlines()[-1])

            self.assertEqual(Path(paths["actor_home"]).resolve(), home.resolve())
            self.assertEqual(Path(paths["config"]).resolve(), (home / "config.yaml").resolve())
            self.assertEqual(Path(paths["server_home"]).resolve(), home.resolve())
            self.assertEqual(Path(paths["state"]).resolve(), (home / "tavern-state").resolve())
            self.assertEqual(Path(paths["profile_home"]).resolve(), home.resolve())


if __name__ == "__main__":
    unittest.main()
