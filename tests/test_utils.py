"""Unit tests for internal utilities (Slice 0)."""

from __future__ import annotations

import math

import pytest

from patchwork._utils import (
    WAIVER,
    arg_match,
    as_roman,
    ave_max,
    ave_min,
    canonicalize_colour,
    is_abs_unit,
    is_waiver,
    modify_list,
    rep_len,
    tail,
    unit_type_name,
)


class TestWaiver:
    def test_WAIVER_is_a_waiver(self):
        assert is_waiver(WAIVER)

    def test_None_is_not_a_waiver(self):
        assert not is_waiver(None)


class TestArgMatch:
    def test_valid_value(self):
        assert arg_match("a", ("a", "b", "c")) == "a"

    def test_invalid_value_raises_with_arg_name(self):
        with pytest.raises(ValueError, match="guides"):
            arg_match("x", ("a", "b"), arg="guides")


class TestModifyList:
    def test_overrides_default(self):
        out = modify_list({"a": 1, "b": 2}, {"b": 3})
        assert out == {"a": 1, "b": 3}

    def test_drops_none(self):
        out = modify_list({"a": 1, "b": 2}, {"b": None})
        assert out == {"a": 1, "b": 2}

    def test_drops_waiver(self):
        out = modify_list({"a": 1, "b": 2}, {"b": WAIVER})
        assert out == {"a": 1, "b": 2}


class TestRepLen:
    def test_recycles(self):
        assert rep_len([1, 2], 5) == [1, 2, 1, 2, 1]

    def test_truncates(self):
        assert rep_len([1, 2, 3], 2) == [1, 2]

    def test_scalar(self):
        assert rep_len(7, 3) == [7, 7, 7]


class TestTail:
    def test_positive_n(self):
        assert tail([1, 2, 3, 4, 5], 2) == [4, 5]

    def test_negative_n(self):
        assert tail([1, 2, 3, 4, 5], -2) == [3, 4, 5]

    def test_n_zero(self):
        assert tail([1, 2, 3], 0) == []


class TestAsRoman:
    @pytest.mark.parametrize(
        "n,expected",
        [(1, "I"), (4, "IV"), (9, "IX"), (17, "XVII"), (40, "XL"), (90, "XC"), (100, "C")],
    )
    def test_values(self, n, expected):
        assert as_roman(n) == expected

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            as_roman(0)
        with pytest.raises(ValueError):
            as_roman(4000)


class TestCanonicalizeColour:
    def test_passes_none(self):
        assert canonicalize_colour(None) is None

    def test_normalises_duplicate_representations(self):
        a = canonicalize_colour("red")
        b = canonicalize_colour("#FF0000")
        # The key property is equality across equivalent inputs.
        assert a == b or a.lower() == b.lower()


class TestAve:
    def test_ave_min(self):
        # groups: a=[1,3], b=[5,2]  → min(a)=1, min(b)=2
        values = [1, 5, 3, 2]
        keys = ["a", "b", "a", "b"]
        assert ave_min(values, keys) == [1, 2, 1, 2]

    def test_ave_max(self):
        values = [1, 5, 3, 2]
        keys = ["a", "b", "a", "b"]
        assert ave_max(values, keys) == [3, 5, 3, 5]


class TestUnitType:
    def test_unit_type_name_on_unit(self):
        from grid_py import Unit

        u = Unit([1, 2], ["mm", "cm"])
        assert unit_type_name(u) == ["mm", "cm"]

    def test_is_abs_unit_mm(self):
        from grid_py import Unit

        assert is_abs_unit(Unit([1], ["mm"]))

    def test_is_abs_unit_null(self):
        from grid_py import Unit

        assert not is_abs_unit(Unit([1], ["null"]))
