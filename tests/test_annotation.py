"""Unit tests for ``annotation`` (Slice 3)."""

from __future__ import annotations

import pytest

from patchwork.annotation import get_level


class TestGetLevel:
    def test_lowercase_letters(self):
        seq = get_level("a")
        assert seq[:5] == ["a", "b", "c", "d", "e"]

    def test_uppercase_letters(self):
        seq = get_level("A")
        assert seq[:5] == ["A", "B", "C", "D", "E"]

    def test_numbers(self):
        seq = get_level("1")
        assert seq[:5] == ["1", "2", "3", "4", "5"]

    def test_lowercase_roman(self):
        seq = get_level("i")
        assert seq[:5] == ["i", "ii", "iii", "iv", "v"]

    def test_uppercase_roman(self):
        seq = get_level("I")
        assert seq[:5] == ["I", "II", "III", "IV", "V"]

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown tag type"):
            get_level("x")

    def test_list_input_direct_passthrough(self):
        seq = get_level([["foo", "bar", "baz"], "more"])
        assert seq == ["foo", "bar", "baz"]


class TestHasTagPlotFiller:
    """R: ``has_tag.plot_filler <- function(x) FALSE``."""

    def test_plot_filler_returns_false(self):
        from patchwork.annotation import has_tag
        from patchwork.add_plot import plot_filler

        assert has_tag(plot_filler()) is False
