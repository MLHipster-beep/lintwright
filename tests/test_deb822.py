import unittest

from lintwright.deb822 import Deb822Error, parse_paragraphs, split_list


class ParseParagraphsTests(unittest.TestCase):
    def test_single_paragraph(self):
        paragraphs = parse_paragraphs("Source: demo\nMaintainer: A <a@example.com>\n")
        self.assertEqual(len(paragraphs), 1)
        self.assertEqual(paragraphs[0].get("Source"), "demo")
        self.assertEqual(paragraphs[0].field_lines["Maintainer"], 2)

    def test_two_paragraphs(self):
        text = "Source: demo\n\nPackage: demo\nArchitecture: all\n"
        paragraphs = parse_paragraphs(text)
        self.assertEqual(len(paragraphs), 2)
        self.assertEqual(paragraphs[1].get("Package"), "demo")
        self.assertEqual(paragraphs[1].start_line, 3)

    def test_continuation_lines_are_folded(self):
        # dpkg strips exactly one leading space from a continuation line, so
        # the parser does the same rather than preserving raw indentation.
        text = "Description: synopsis\n extended line one\n extended line two\n"
        paragraph = parse_paragraphs(text)[0]
        self.assertEqual(
            paragraph.get("Description"),
            "synopsis\nextended line one\nextended line two",
        )

    def test_comment_lines_are_skipped(self):
        paragraph = parse_paragraphs("# a note\nSource: demo\n")[0]
        self.assertEqual(paragraph.get("Source"), "demo")

    def test_duplicate_field_is_rejected(self):
        with self.assertRaises(Deb822Error) as caught:
            parse_paragraphs("Source: a\nSource: b\n")
        self.assertEqual(caught.exception.line, 2)

    def test_orphan_continuation_is_rejected(self):
        with self.assertRaises(Deb822Error) as caught:
            parse_paragraphs(" leading space with no field\n")
        self.assertEqual(caught.exception.line, 1)

    def test_malformed_line_is_rejected(self):
        with self.assertRaises(Deb822Error):
            parse_paragraphs("this is not a field\n")

    def test_get_is_case_insensitive(self):
        paragraph = parse_paragraphs("Source: demo\n")[0]
        self.assertEqual(paragraph.get("source"), "demo")
        self.assertTrue(paragraph.has("SOURCE"))

    def test_split_list_trims_and_drops_empties(self):
        self.assertEqual(split_list("a, b ,,c"), ["a", "b", "c"])

    def test_empty_input(self):
        self.assertEqual(parse_paragraphs(""), [])

    def test_blank_line_inside_description_starts_new_paragraph(self):
        text = "Description: synopsis\n\nPackage: demo\n"
        self.assertEqual(len(parse_paragraphs(text)), 2)


if __name__ == "__main__":
    unittest.main()
