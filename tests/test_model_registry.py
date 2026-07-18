import json
import os
import tempfile
import threading
import unittest

from model_registry import ModelRegistry


def registry(path, ping=None, validate=None):
    return ModelRegistry(
        path,
        builtin_base="https://builtin.example/v1",
        builtin_key="builtin-secret",
        builtin_name="deepseek-v4-flash",
        official_models=("deepseek-v4-flash",),
        ping=ping or (lambda override: 7),
        model_info=lambda override: {"model": (override or {}).get("model", "deepseek-v4-flash")},
        validate_base=validate or (lambda base: base),
    )


class ModelRegistryTests(unittest.TestCase):
    def test_add_masks_secret_and_preserves_private_file_mode(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "models.json")
            item = registry(path)
            result = item.add(
                {"name": "custom", "base": "https://models.example/v1", "model": "m1", "key": "secret-1234"}
            )
            self.assertEqual(result["config"]["key_masked"], "**1234")
            self.assertEqual(item.active_override()["model"], "m1")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            public = item.public_view()
            self.assertNotIn("secret-1234", json.dumps(public))
            self.assertTrue(all("key" not in entry for entry in public["configs"] if entry["kind"] == "custom"))

    def test_concurrent_adds_do_not_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as root:
            item = registry(os.path.join(root, "models.json"))
            threads = [
                threading.Thread(
                    target=item.add,
                    args=({
                        "name": f"custom-{index}",
                        "base": f"https://models{index}.example/v1",
                        "model": f"m{index}",
                        "key": f"secret-{index:04d}",
                    },),
                )
                for index in range(8)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            public = item.public_view()
            self.assertEqual(len([entry for entry in public["configs"] if entry["kind"] == "custom"]), 8)

    def test_use_and_delete_fall_back_to_builtin(self):
        with tempfile.TemporaryDirectory() as root:
            item = registry(os.path.join(root, "models.json"))
            added = item.add(
                {"name": "custom", "base": "https://models.example/v1", "model": "m1", "key": "secret-1234"}
            )
            item.use({"id": added["config"]["id"]})
            deleted = item.delete({"id": added["config"]["id"]})
            self.assertEqual(deleted["active"], "builtin")
            self.assertIsNone(item.active_override())

    def test_base_validation_runs_before_ping(self):
        calls = []

        def reject(base):
            raise ValueError("blocked")

        with tempfile.TemporaryDirectory() as root:
            item = registry(os.path.join(root, "models.json"), ping=lambda override: calls.append(override), validate=reject)
            with self.assertRaisesRegex(ValueError, "blocked"):
                item.add({"name": "bad", "base": "http://127.0.0.1", "model": "m", "key": "secret"})
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
