import threading
import time
import unittest

from background_jobs import CoalescingJobRunner


class BackgroundJobTests(unittest.TestCase):
    def test_repeated_running_key_is_coalesced_to_one_rerun(self):
        runner = CoalescingJobRunner(workers=1, max_keys=4, name="test-bg")
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        calls = []

        def job(value):
            calls.append(value)
            if value == 1:
                started.set()
                release.wait(1)
            else:
                finished.set()

        self.assertTrue(runner.submit(("scene", "p1"), job, 1))
        self.assertTrue(started.wait(1))
        self.assertTrue(runner.submit(("scene", "p1"), job, 2))
        self.assertTrue(runner.submit(("scene", "p1"), job, 3))
        release.set()
        self.assertTrue(finished.wait(1))
        self.assertEqual(calls, [1, 3])

    def test_capacity_rejects_new_key_but_accepts_existing_key(self):
        runner = CoalescingJobRunner(workers=1, max_keys=1, name="test-capacity")
        started = threading.Event()
        release = threading.Event()

        def blocked():
            started.set()
            release.wait(1)

        self.assertTrue(runner.submit("one", blocked))
        self.assertTrue(started.wait(1))
        self.assertTrue(runner.submit("one", blocked))
        self.assertFalse(runner.submit("two", lambda: None))
        release.set()


if __name__ == "__main__":
    unittest.main()
