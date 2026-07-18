import unittest

from memory_cache import ByteLRUCache


class ByteLRUCacheTests(unittest.TestCase):
    def test_evicts_least_recently_used_by_byte_budget(self):
        cache = ByteLRUCache(max_items=4, max_bytes=6)
        cache.put("a", b"aaa")
        cache.put("b", b"bb")
        self.assertEqual(cache.get("a"), b"aaa")
        cache.put("c", b"cc")
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.stats()["bytes"], 5)

    def test_replacement_and_item_limit_keep_exact_size(self):
        cache = ByteLRUCache(max_items=2, max_bytes=100)
        cache.put("a", b"1234")
        cache.put("a", b"1")
        cache.put("b", b"22")
        cache.put("c", b"333")
        self.assertIsNone(cache.get("a"))
        self.assertEqual(cache.stats()["bytes"], 5)

    def test_oversized_value_is_not_cached(self):
        cache = ByteLRUCache(max_items=2, max_bytes=3)
        self.assertFalse(cache.put("large", b"1234"))
        self.assertEqual(cache.stats()["items"], 0)

    def test_delete_updates_item_and_byte_counts(self):
        cache = ByteLRUCache(max_items=2, max_bytes=10)
        cache.put("a", b"1234")
        self.assertTrue(cache.delete("a"))
        self.assertFalse(cache.delete("missing"))
        self.assertEqual(cache.stats()["items"], 0)
        self.assertEqual(cache.stats()["bytes"], 0)


if __name__ == "__main__":
    unittest.main()
