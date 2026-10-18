import unittest

from lintwright.changelog import parse_changelog
from tests.helpers import BASE_CHANGELOG


class ChangelogTests(unittest.TestCase):
    def test_valid_entry(self):
        entry = parse_changelog(BASE_CHANGELOG)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.package, "demo")
        self.assertEqual(entry.version, "1.0-1")
        self.assertEqual(entry.distribution, "noble")
        self.assertEqual(entry.urgency, "medium")
        self.assertEqual(entry.maintainer_name, "Test Person")
        self.assertEqual(entry.maintainer_email, "test@example.com")
        self.assertIsNotNone(entry.date)
        self.assertEqual(entry.problems, [])

    def test_has_revision(self):
        self.assertTrue(parse_changelog(BASE_CHANGELOG).has_revision)
        native = BASE_CHANGELOG.replace("demo (1.0-1)", "demo (1.0)")
        self.assertFalse(parse_changelog(native).has_revision)

    def test_missing_signature_is_recorded(self):
        text = "demo (1.0-1) noble; urgency=medium\n\n  * change\n"
        entry = parse_changelog(text)
        self.assertEqual([problem[0] for problem in entry.problems], ["changelog-signature"])

    def test_invalid_date_is_recorded(self):
        text = BASE_CHANGELOG.replace("Mon, 05 Oct 2026 10:00:00 +0000", "not a date")
        entry = parse_changelog(text)
        self.assertEqual([problem[0] for problem in entry.problems], ["changelog-signature"])

    def test_bad_header_returns_none(self):
        self.assertIsNone(parse_changelog("demo 1.0\n\n  * oops\n"))

    def test_trailing_blank_lines_do_not_break_parsing(self):
        entry = parse_changelog(BASE_CHANGELOG + "\n")
        self.assertEqual(entry.package, "demo")

    def test_body_is_captured(self):
        self.assertIn("Initial release", parse_changelog(BASE_CHANGELOG).body)


if __name__ == "__main__":
    unittest.main()
