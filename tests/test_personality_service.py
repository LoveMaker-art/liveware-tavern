import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PersonalityServiceTests(unittest.TestCase):
    def setUp(self):
        self.previous = os.environ.get("TAVERN_PERSONALITY_FILE")
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "SOUL.md"
        os.environ["TAVERN_PERSONALITY_FILE"] = str(self.path)
        self.service = load_module(
            "personality_service_test",
            ROOT / "app/backend/personality_service.py",
        )

    def tearDown(self):
        self.tempdir.cleanup()
        if self.previous is None:
            os.environ.pop("TAVERN_PERSONALITY_FILE", None)
        else:
            os.environ["TAVERN_PERSONALITY_FILE"] = self.previous

    def test_atomic_write_and_revision_conflict(self):
        initial = self.service.read_document()
        saved = self.service.write_document("# Soul\n\nWarm.", initial["revision"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), "# Soul\n\nWarm.\n")
        self.assertNotEqual(saved["revision"], initial["revision"])
        with self.assertRaises(self.service.PersonalityConflict):
            self.service.write_document("Stale", initial["revision"])

    def test_rejects_empty_and_oversized_documents(self):
        revision = self.service.read_document()["revision"]
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            self.service.write_document("  ", revision)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.service.write_document("x" * 20_001, revision)


class SoulReloadPluginTests(unittest.TestCase):
    def test_cache_is_evicted_only_after_soul_changes(self):
        with tempfile.TemporaryDirectory() as tempdir:
            previous = os.environ.get("HERMES_HOME")
            os.environ["HERMES_HOME"] = tempdir
            soul = Path(tempdir) / "SOUL.md"
            soul.write_text("first", encoding="utf-8")
            plugin = load_module(
                "tavern_soul_reload_test",
                ROOT / "skills/tavern/plugins/tavern-soul-reload/__init__.py",
            )

            class Context:
                callback = None

                def register_hook(self, name, callback):
                    self.name = name
                    self.callback = callback

            class Agent:
                pass

            class Gateway:
                def __init__(self):
                    import threading
                    self._agent_cache_lock = threading.Lock()
                    self._agent_cache = {"session": (Agent(), "sig")}
                    self.released = []

                def _release_evicted_agent_soft(self, agent):
                    self.released.append(agent)

            try:
                context = Context()
                plugin.register(context)
                gateway = Gateway()
                context.callback(gateway=gateway)
                self.assertEqual(len(gateway._agent_cache), 1)
                soul.write_text("second", encoding="utf-8")
                context.callback(gateway=gateway)
                self.assertEqual(gateway._agent_cache, {})
                self.assertEqual(len(gateway.released), 1)
            finally:
                if previous is None:
                    os.environ.pop("HERMES_HOME", None)
                else:
                    os.environ["HERMES_HOME"] = previous


if __name__ == "__main__":
    unittest.main()
