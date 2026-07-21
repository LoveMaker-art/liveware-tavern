import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "creative-skills/tavern-world-visuals/scripts/world_theme.py"
SPEC = importlib.util.spec_from_file_location("tavern_world_theme", MODULE_PATH)
WORLD_THEME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORLD_THEME)


class WorldThemeTests(unittest.TestCase):
    def test_normalize_theme_keeps_only_supported_declarative_fields(self):
        normalized, warnings = WORLD_THEME.normalize_theme({
            "version": 1,
            "theme": {
                "accent": "#AABBCC",
                "content_width": 580,
                "background_fit": "contain",
                "background_fit_mobile": "cover",
                "reading_surface": "glass",
            },
            "assets": {
                "background_desktop": "/world-assets/prod_example/desktop.webp",
                "background_mobile": "https://example.com/mobile.png",
            },
        })

        self.assertEqual(normalized["theme"]["accent"], "#aabbcc")
        self.assertEqual(normalized["theme"]["content_width"], 580)
        self.assertEqual(normalized["theme"]["background_fit_mobile"], "cover")
        self.assertEqual(normalized["assets"]["background_mobile"], "https://example.com/mobile.png")
        self.assertTrue(warnings)

    def test_normalize_theme_rejects_executable_or_inline_assets(self):
        for value in ("javascript:alert(1)", "data:image/png;base64,AAAA", "http://example.com/a.png"):
            with self.subTest(value=value):
                with self.assertRaises(WORLD_THEME.ThemeError):
                    WORLD_THEME.normalize_theme({"assets": {"background": value}})

    def test_normalize_theme_rejects_unknown_fields(self):
        with self.assertRaisesRegex(WORLD_THEME.ThemeError, "Unknown theme fields"):
            WORLD_THEME.normalize_theme({"theme": {"custom_css": "body{}"}})


if __name__ == "__main__":
    unittest.main()
