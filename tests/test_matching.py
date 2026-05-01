from __future__ import annotations

import unittest

from gtimer.config import MatchRule
from gtimer.identity import normalize_title, window_key
from gtimer.matching import matches_rule
from gtimer.models import WindowInfo


class MatchingTests(unittest.TestCase):
    def test_title_contains_is_case_insensitive(self) -> None:
        window = WindowInfo("Minecraft 1.20.4 - Multiplayer", "java", "minecraft-launcher")
        rule = MatchRule(title_contains=("minecraft",))

        self.assertTrue(matches_rule(window, rule))

    def test_empty_rule_does_not_match_everything(self) -> None:
        self.assertFalse(matches_rule(WindowInfo("Anything"), MatchRule()))

    def test_ignore_rule_can_match_gtimer_self_focus(self) -> None:
        window = WindowInfo("gTimer", "gtimer", "gtimer")
        rule = MatchRule(title_contains=("gTimer",), class_contains=("gtimer",))

        self.assertTrue(matches_rule(window, rule))

    def test_window_key_prefers_class_and_instance(self) -> None:
        window = WindowInfo("Minecraft 1.20.4", "java", "minecraft-launcher")

        self.assertEqual(window_key(window), "java|minecraft-launcher")

    def test_window_key_falls_back_to_normalized_title(self) -> None:
        self.assertEqual(window_key(WindowInfo("  A   Window  ")), "a window")

    def test_normalize_title_handles_empty_values(self) -> None:
        self.assertEqual(normalize_title(""), "unknown")


if __name__ == "__main__":
    unittest.main()
