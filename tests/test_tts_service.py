import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from tts_service import TTSService, load_voice_catalog


class _AudioResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class TTSServiceTests(unittest.TestCase):
    def make_service(self, root):
        return TTSService(root, base="", key_provider=lambda: "")

    def test_curated_catalog_matches_previous_preset_count(self):
        voices = load_voice_catalog()
        ids = {item["id"] for item in voices}
        self.assertEqual(len(voices), 9)
        self.assertEqual(len(ids), 9)
        self.assertIn("longanlingxin", ids)
        self.assertIn("longanlufeng", ids)
        self.assertIn("qwen-audio-3.0-tts-plus-longlingxingyi", ids)
        self.assertIn("qwen-audio-3.0-tts-plus-loongolivialin", ids)

    def test_voice_discovery_does_not_expand_curated_presets(self):
        with tempfile.TemporaryDirectory() as root:
            service = TTSService(
                root,
                base="https://example.invalid/v1",
                key_provider=lambda: "test-key",
            )
            response = {
                "data": [
                    {"id": "longanlingxin", "model": service.MODEL, "name": "Updated"},
                    {"id": "qwen-audio-3.0-tts-plus-not-curated", "model": service.MODEL},
                ]
            }
            with mock.patch(
                "tts_service.urllib.request.urlopen",
                return_value=_AudioResponse(json.dumps(response).encode("utf-8")),
            ):
                voices = service.voices(force=True)

            self.assertEqual(len(voices), 9)
            self.assertNotIn(
                "qwen-audio-3.0-tts-plus-not-curated",
                {item["id"] for item in voices},
            )

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
                threading.Thread(target=update, args=("longanlingxin", 1.1)),
                threading.Thread(target=update, args=("longanlufeng", 1.2)),
            ]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            with open(service.config_path, encoding="utf-8") as file:
                saved = json.load(file)
            self.assertEqual(
                set(saved["preset_settings"]),
                {"longanlingxin", "longanlufeng"},
            )
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

    def test_plus_request_forwards_voice_controls(self):
        with tempfile.TemporaryDirectory() as root:
            service = TTSService(
                root,
                base="https://example.invalid/v1",
                key_provider=lambda: "test-key",
            )
            service._voice_cache.update({
                "at": time.monotonic(),
                "voices": list(service._voice_cache["voices"]),
            })
            requests = []

            def fake_urlopen(request, timeout=None):
                requests.append(request)
                return _AudioResponse(b"audio")

            with mock.patch("tts_service.urllib.request.urlopen", fake_urlopen):
                audio = service.generate(
                    "你好",
                    voice="longanlingxin",
                    speed=0.85,
                    instructions="温柔知性，吐字清晰",
                    emotion="serious",
                )

            self.assertEqual(audio, b"audio")
            self.assertEqual(len(requests), 1)
            payload = json.loads(requests[0].data.decode("utf-8"))
            self.assertEqual(payload["model"], "qwen-audio-3.0-tts-plus")
            self.assertEqual(payload["voice"], "longanlingxin")
            self.assertEqual(payload["speed"], 0.85)
            self.assertEqual(payload["instructions"], "温柔知性，吐字清晰")
            self.assertEqual(payload["input"], "[serious]你好")


if __name__ == "__main__":
    unittest.main()
