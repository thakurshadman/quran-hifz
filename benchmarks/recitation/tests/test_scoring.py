"""Independent comparison tests using toy words, never generated Qur'an text."""

import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scoring import edit_counts, normalize, reference_words


def source_records(with_opening=False):
    """Synthetic source shape with four opening tokens and 15 passage tokens."""
    opening = "opening one two three"
    records = [{"surah": 1, "ayah": 1, "text_clean": opening}]
    for number, text in enumerate(("a b c d", "e f g", "h i j k", "l m n o"), 1):
        if number == 1 and with_opening:
            text = opening + " " + text
        records.append({"surah": 112, "ayah": number, "text_clean": text})
    return records


class NormalizationTests(unittest.TestCase):
    def test_marks_tatweel_and_whitespace(self):
        self.assertEqual(normalize(" كِتَابٌ\n بــاب\t"), ["كتاب", "باب"])

    def test_recitation_small_letters_are_removed(self):
        # U+06E5 and U+06E6 are letters, not Unicode combining marks.
        self.assertEqual(normalize("ب\u06e5اب ب\u06e6اب"), ["باب", "باب"])

    def test_documented_alef_variants_only(self):
        self.assertEqual(normalize("أ إ آ ٱ ا"), ["ا"] * 5)
        self.assertEqual(normalize("ء ؤ ئ ة ه ى ي"), ["ء", "ؤ", "ئ", "ة", "ه", "ى", "ي"])

    def test_decomposed_alef_matches_composed(self):
        self.assertEqual(normalize("ا\u0654 ا\u0655"), ["ا", "ا"])

    def test_punctuation_has_word_boundaries(self):
        self.assertEqual(normalize("alpha,beta! gamma؟delta"), ["alpha", "beta", "gamma", "delta"])


class WordEditTests(unittest.TestCase):
    def test_independent_edit_examples(self):
        examples = [
            ("", "", (0, 0, 0)),
            ("alpha beta", "alpha beta", (0, 0, 0)),
            ("alpha beta gamma", "alpha wrong gamma", (1, 0, 0)),
            ("alpha beta gamma", "alpha gamma", (0, 1, 0)),
            ("alpha gamma", "alpha beta gamma", (0, 0, 1)),
            ("alpha beta", "", (0, 2, 0)),
            ("", "alpha beta", (0, 0, 2)),
            ("alpha beta gamma delta", "alpha wrong delta extra", (3, 0, 0)),
            ("alpha beta alpha", "alpha alpha", (0, 1, 0)),
        ]
        for reference, heard, expected in examples:
            with self.subTest(reference=reference, heard=heard):
                result = edit_counts(reference.split(), heard.split())
                self.assertEqual(result, dict(zip(("substitutions", "deletions", "insertions"), expected)))
                self.assertEqual(len(heard.split()) - len(reference.split()), result["insertions"] - result["deletions"])

    def test_tie_rule_is_deterministic(self):
        # Either two substitutions or one deletion plus one insertion costs two.
        self.assertEqual(edit_counts(["alpha", "beta"], ["beta", "alpha"]),
                         {"substitutions": 2, "deletions": 0, "insertions": 0})

    def test_inputs_remain_unchanged(self):
        reference, hypothesis = ["a", "b"], ["b", "c"]
        edit_counts(reference, hypothesis)
        self.assertEqual(reference, ["a", "b"])
        self.assertEqual(hypothesis, ["b", "c"])


class SourceBoundaryTests(unittest.TestCase):
    def test_both_source_opening_conventions(self):
        for with_opening in (False, True):
            records = source_records(with_opening)
            original = copy.deepcopy(records)
            self.assertEqual(reference_words(records), list("abcdefghijklmno"))
            self.assertEqual(reference_words(records, "include"),
                             "opening one two three".split() + list("abcdefghijklmno"))
            self.assertEqual(records, original, "comparison must not alter source/display records")

    def test_unrelated_surah_is_not_scored(self):
        records = source_records() + [{"surah": 113, "ayah": 1, "text_clean": "unrelated"}]
        self.assertEqual(reference_words(records), list("abcdefghijklmno"))

    def test_missing_duplicate_and_out_of_order_ayah_rejected(self):
        records = source_records()
        cases = [records[:-1], records + [records[2]],
                 [records[0], records[2], records[1], records[3], records[4]]]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                reference_words(case)

    def test_opening_must_be_unique_and_have_four_words(self):
        records = source_records()
        short = copy.deepcopy(records)
        short[0]["text_clean"] = "only three tokens"
        for case in (records[1:], records + [records[0]], short):
            with self.subTest(case=case), self.assertRaises(ValueError):
                reference_words(case)

    def test_selected_passage_must_have_fifteen_words(self):
        records = source_records()
        for text in ("l m n", "l m n o extra"):
            records[-1]["text_clean"] = text
            with self.subTest(text=text), self.assertRaises(ValueError):
                reference_words(records)

    def test_unknown_scope_rejected(self):
        with self.assertRaises(ValueError):
            reference_words(source_records(), "automatic")


if __name__ == "__main__":
    unittest.main()
