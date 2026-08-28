import unittest

from app.ui_theme import contrast_text, stylesheet


class UiThemeTests(unittest.TestCase):
    def test_both_themes_define_semantic_action_and_status_roles(self):
        for theme in ("dark", "light"):
            qss = stylesheet(theme)
            self.assertIn('QPushButton[role="primary"]', qss)
            self.assertIn('QPushButton[role="danger"]', qss)
            self.assertIn('QLabel[status="ok"]', qss)
            self.assertIn('QLabel[status="error"]', qss)

    def test_contrast_text_is_readable_on_light_and_dark_colors(self):
        self.assertEqual(contrast_text("#FFFFFF"), "#000000")
        self.assertEqual(contrast_text("#000000"), "#FFFFFF")


if __name__ == "__main__":
    unittest.main()
