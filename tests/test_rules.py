"""Unit tests for rule-based cleaner, self-corrections, and phrase replacements."""

import unittest
from spic.interpreter.rule_cleaner import RuleCleaner


class TestRuleCleanerSelfCorrections(unittest.TestCase):
    """Test suite for conversational self-corrections, phrase replacements, and deletions."""

    def setUp(self):
        self.cleaner = RuleCleaner()

    def test_phrase_replacement_with_drawer(self):
        """Verify phrase replacement: 'in the left drawer from the drawer' -> 'from the drawer'."""
        text = "select screenshot in the left-drawer from the drawer"
        cleaned = self.cleaner.clean(text)
        self.assertEqual(cleaned, "Select screenshot from the drawer")

    def test_cue_based_self_correction(self):
        """Verify cue-based correction: 'at 3pm, actually 4pm' -> 'at 4pm'."""
        text = "meet at 3pm, actually 4pm"
        cleaned = self.cleaner.clean(text)
        self.assertEqual(cleaned, "Meet at 4pm")

    def test_repetition_correction_with_sorry(self):
        """Verify correction with 'sorry': 'in the left drawer, sorry from the drawer'."""
        text = "put it in the left drawer, sorry from the drawer"
        cleaned = self.cleaner.clean(text)
        self.assertEqual(cleaned, "Put it from the drawer")

    def test_scratch_that_inline_deletion(self):
        """Verify scratch that command deletes the preceding clause."""
        text = "send the email tomorrow morning scratch that send it tonight"
        cleaned = self.cleaner.clean(text)
        self.assertEqual(cleaned, "Send it tonight")


if __name__ == "__main__":
    unittest.main()
