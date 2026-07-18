import json
import os
import tempfile
import threading
import time
import unittest

from tts_service import TTSService


class TTSServiceTests(unittest.TestCase):
    def make_service(self, root):
        return TTSService(root, base="", key_provider=lambda: "")

    def test_concurrent_preset_updates_preserve_both_voices(self):
        with tempfile.TemporaryDirectory() as root:
            service = self.make_service(root)
            barrier = threading.Barrier(3)
            errors = []

            def update(voice, speed):
                try:
                    barrier.wait()
                    service.save_preset_settings(voice, speed, voice)
                except Exception as error:
                    errors.append(error)

            threads = [
                threading.Thread(target=update, args=("vivian", 1.1)),
                threading.Thread(target=update, args=("serena", 1.2)),
            ]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            with open(service.config_path, encoding="utf-8") as file:
                saved = json.load(file)
            self.assertEqual(set(saved["preset_settings"]), {"vivian", "serena"})
            self.assertEqual(os.stat(service.config_path).st_mode & 0o777, 0o600)

    def test_disk_cache_survives_service_restart(self):
        with tempfile.TemporaryDirectory() as root:
            cache_key = "a" * 64
            first = self.make_service(root)
            first._store_disk_cache(cache_key, b"audio")
            second = self.make_service(root)
            self.assertEqual(second._cached_audio(cache_key), b"audio")
            self.assertEqual(second.cache_stats()["bytes"], 5)

    def test_cleanup_removes_expired_disk_and_memory_entries(self):
        with tempfile.TemporaryDirectory() as root:
            service = self.make_service(root)
            cache_key = "b" * 64
            service._store_disk_cache(cache_key, b"old")
            service.cache.put(cache_key, b"old")
            now = time.time()
            os.utime(service._cache_path(cache_key), (now - 20 * 86400,) * 2)
            self.assertEqual(service.cleanup(force=True, now=now), 1)
            self.assertIsNone(service._cached_audio(cache_key))
            self.assertEqual(service.cache_stats()["items"], 0)


if __name__ == "__main__":
    unittest.main()
