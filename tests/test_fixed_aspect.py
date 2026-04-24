"""Unit tests for fixed-aspect (``coord_fixed``) plot composition (Slice 5)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from ggplot2_py import aes, coord_fixed, geom_point, ggplot

import patchwork as pw


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5],
            "y": [2, 4, 1, 3, 5],
            "z": [0.1, 0.2, 0.3, 0.4, 0.5],
        }
    )


@pytest.fixture
def p_fixed(df):
    return ggplot(df) + geom_point(aes(x="x", y="y")) + coord_fixed()


@pytest.fixture
def p_regular(df):
    return ggplot(df) + geom_point(aes(x="x", y="z"))


class TestFixedAspectRespect:
    """``coord_fixed()`` plots populate the respect matrix of the outer gtable."""

    def test_respect_becomes_matrix(self, p_fixed, p_regular):
        composed = p_fixed + p_regular
        gt = pw.patchworkGrob(composed)
        assert isinstance(gt.respect, np.ndarray)

    def test_respect_has_exactly_one_marked_cell(self, p_fixed, p_regular):
        composed = p_fixed + p_regular
        gt = pw.patchworkGrob(composed)
        assert isinstance(gt.respect, np.ndarray)
        assert int((gt.respect == 1).sum()) == 1


class TestNoFixedAspect:
    """Compositions without any fixed-aspect plot keep ``respect`` falsy."""

    def test_default_is_false(self, p_regular):
        composed = p_regular + p_regular
        gt = pw.patchworkGrob(composed)
        if isinstance(gt.respect, np.ndarray):
            assert not gt.respect.any()
        else:
            assert gt.respect is False


class TestFixedAspectWithExplicitWidths:
    """When the user passes explicit widths, the R guard disables respect."""

    def test_explicit_widths_disables_respect(self, p_fixed, p_regular):
        composed = (p_fixed + p_regular) + pw.plot_layout(widths=[1, 1])
        gt = pw.patchworkGrob(composed)
        # Explicit widths mean no ``-1null`` sentinels, so R's guard short-
        # circuits and respect stays at its default False.
        if isinstance(gt.respect, np.ndarray):
            assert not gt.respect.any()
        else:
            assert gt.respect is False
