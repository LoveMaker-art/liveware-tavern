import importlib.util
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class _AudioResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


class TtsDiskCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.env = mock.patch.dict(os.environ, {
            "TAVERN_STATE_DIR": cls.temp.name,
            "TAVERN_MODEL_BASE": "https://example.invalid/v1",
            "TAVERN_TTS_KEY": "test-key",
            "TAVERN_TTS_BASE": "https://example.invalid/v1",
        })
        cls.env.start()
        spec = importlib.util.spec_from_file_location(
            "tavern_server_tts_test",
            ROOT / "skill/server.py",
        )
        cls.server = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.server
        spec.loader.exec_module(cls.server)

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("tavern_server_tts_test", None)
        cls.env.stop()
        cls.temp.cleanup()

    def setUp(self):
        runtime_env = mock.patch.dict(os.environ, {
            "TAVERN_TTS_KEY": "test-key",
            "TAVERN_TTS_BASE": "https://example.invalid/v1",
        })
        runtime_env.start()
        self.addCleanup(runtime_env.stop)
        for directory in (self.server.TTS_CACHE_DIR, self.server.TTS_REFERENCE_DIR):
            shutil.rmtree(directory, ignore_errors=True)
            os.makedirs(directory, mode=0o700)
        try:
            os.remove(self.server.TTS_CONFIG_PATH)
        except FileNotFoundError:
            pass
        self.server._tts_cache.clear()
        self.server._tts_cache_order.clear()
        self.server._tts_cache_last_cleanup = 0.0
        self.server._tts_voice_cache.update({
            "at": time.time(),
            "voices": list(self.server.TTS_FALLBACK_VOICES),
        })

    def test_same_voice_survives_memory_reset_and_voice_change_regenerates(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append(request)
            return _AudioResponse(b"audio-" + str(len(calls)).encode("ascii"))

        with mock.patch.object(self.server.urllib.request, "urlopen", fake_urlopen):
            first = self.server._generate_speech("同一句话")
            cache_files = list(Path(self.server.TTS_CACHE_DIR).glob("*.mp3"))
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(cache_files), 1)
            self.assertEqual(stat.S_IMODE(cache_files[0].stat().st_mode), 0o600)

            old_time = time.time() - 60
            os.utime(cache_files[0], (old_time, old_time))
            self.server._tts_cache.clear()
            self.server._tts_cache_order.clear()
            second = self.server._generate_speech("同一句话")
            self.assertEqual(second, first)
            self.assertEqual(len(calls), 1)
            self.assertGreater(cache_files[0].stat().st_mtime, old_time)

            self.server._save_tts_voice("serena")
            changed = self.server._generate_speech("同一句话")
            self.assertNotEqual(changed, first)
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(list(Path(self.server.TTS_CACHE_DIR).glob("*.mp3"))), 2)

    def test_cleanup_uses_last_use_time_and_preserves_clone_references(self):
        now = time.time()
        old_key = "a" * 64
        recent_key = "b" * 64
        old_cache = Path(self.server._tts_cache_path(old_key))
        recent_cache = Path(self.server._tts_cache_path(recent_key))
        old_cache.write_bytes(b"old")
        recent_cache.write_bytes(b"recent")
        clone_reference = Path(self.server.TTS_REFERENCE_DIR) / ("c" * 43 + ".mp3")
        clone_reference.write_bytes(b"reference")
        old_time = now - (self.server.TTS_CACHE_RETENTION_DAYS * 86400) - 1
        recent_time = now - (self.server.TTS_CACHE_RETENTION_DAYS * 86400) + 1
        os.utime(old_cache, (old_time, old_time))
        os.utime(recent_cache, (recent_time, recent_time))
        os.utime(clone_reference, (old_time, old_time))
        self.server._remember_tts_audio(old_key, b"old")

        removed = self.server._cleanup_tts_disk_cache(force=True, now=now)

        self.assertEqual(removed, 1)
        self.assertFalse(old_cache.exists())
        self.assertTrue(recent_cache.exists())
        self.assertTrue(clone_reference.exists())
        self.assertNotIn(old_key, self.server._tts_cache)


if __name__ == "__main__":
    unittest.main()
