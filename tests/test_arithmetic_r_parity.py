"""R-derived arithmetic tests — port of R ``tests/testthat/test-arithmetic.R``.

R's testsuite covers operator combinations across multiple plots; ours
augments the existing ``test_arithmetic.py`` with the multi-plot
compositions R's vdiffr snapshots would catch.
"""
from __future__ import annotations

import numpy as np
import pytest
from ggplot2_py import (
    aes, geom_boxplot, geom_point, ggplot, ggtitle, theme_bw,
)

from patchwork import Patchwork, patchworkGrob


@pytest.fixture
def mtcars_df():
    from patchwork._datasets import mtcars
    return mtcars().reset_index()


@pytest.fixture
def p1(mtcars_df):
    return (ggplot(mtcars_df) + geom_point(aes(x="mpg", y="disp"))
            + ggtitle("Plot 1"))


@pytest.fixture
def p2(mtcars_df):
    return (ggplot(mtcars_df) + geom_boxplot(aes(x="gear", y="disp", group="gear"))
            + ggtitle("Plot 2"))


@pytest.fixture
def p3(mtcars_df):
    return (ggplot(mtcars_df) + geom_point(aes(x="hp", y="wt", colour="mpg"))
            + ggtitle("Plot 3"))


@pytest.fixture
def p4(mtcars_df):
    from ggplot2_py import facet_wrap, geom_bar
    return (ggplot(mtcars_df) + geom_bar(aes(x="gear")) + facet_wrap("~cyl")
            + ggtitle("Plot 4"))


# ---------------------------------------------------------------------------
# R: test_that("`+` works")
# ---------------------------------------------------------------------------


class TestPlusOperator:

    def test_three_plot_addition(self, p1, p2, p3):
        composed = p1 + p2 + p3
        assert isinstance(composed, Patchwork)
        assert len(composed) == 3
        gt = patchworkGrob(composed)
        assert gt is not None

    def test_left_paren_addition(self, p1, p2, p3):
        composed = (p1 + p2) + p3
        assert isinstance(composed, Patchwork)
        assert len(composed) == 3

    def test_right_paren_addition(self, p1, p2, p3):
        # R: `p1 + (p2 + p3)` — adds the patchwork as a nested unit.
        composed = p1 + (p2 + p3)
        assert isinstance(composed, Patchwork)

    def test_add_grob(self, p1):
        from grid_py import text_grob
        composed = p1 + text_grob("test")
        assert isinstance(composed, Patchwork)

    def test_add_theme(self, p1, p2):
        composed = p1 + p2 + theme_bw()
        assert isinstance(composed, Patchwork)
        gt = patchworkGrob(composed)
        assert gt is not None

    def test_add_ndarray_image(self, p1):
        # R's nativeRaster equivalent in Python — uint32 packed RGBA or
        # plain RGB ndarray. patchwork-python routes both through
        # update_ggplot.np.ndarray → wrap_elements(full=...).
        arr = np.zeros((10, 10, 3), dtype=np.uint8)
        composed = p1 + arr
        assert isinstance(composed, Patchwork)


# ---------------------------------------------------------------------------
# R: test_that("`-` works")
# ---------------------------------------------------------------------------


class TestMinusOperator:

    def test_minus_nests_lhs(self, p1, p2, p3):
        # R: `(p1 + p2) - p3` keeps p3 at same nesting level as the lhs.
        composed = (p1 + p2) - p3
        assert isinstance(composed, Patchwork)

    def test_minus_nests_rhs(self, p1, p2, p3):
        composed = p1 - (p2 + p3)
        assert isinstance(composed, Patchwork)


# ---------------------------------------------------------------------------
# R: test_that("`|` and `/` works")
# ---------------------------------------------------------------------------


class TestStackPack:

    def test_stack_three(self, p1, p2, p3):
        # R: `p1 / p2 / p3` — column of 3 (sets ncol=1).
        composed = p1 / p2 / p3
        assert composed.patches.layout.ncol == 1
        assert len(composed) == 3

    def test_pack_four(self, p1, p2, p3, p4):
        # R: `p1 | p2 | p3 | p4` — row of 4 (sets nrow=1).
        composed = p1 | p2 | p3 | p4
        assert composed.patches.layout.nrow == 1
        assert len(composed) == 4

    def test_complex_composition(self, p1, p2, p3, p4):
        # R: `((p1 / p2) | p3) / p4`
        composed = ((p1 / p2) | p3) / p4
        assert composed.patches.layout.ncol == 1
        gt = patchworkGrob(composed)
        assert gt is not None


# ---------------------------------------------------------------------------
# R: test_that("`&` and `*` works")
# ---------------------------------------------------------------------------


class TestAndStar:

    def test_and_recurses_into_nested(self, p1, p2, p3, p4):
        # R: `patchwork & theme_bw()` — applies theme to ALL subplots
        # including those inside nested patchworks.
        patchwork = ((p1 / p2) | p3) / p4
        composed = patchwork & theme_bw()
        assert isinstance(composed, Patchwork)
        gt = patchworkGrob(composed)
        assert gt is not None

    def test_star_only_top_level(self, p1, p2, p3, p4):
        # R: `patchwork * theme_bw()` — applies theme only at the top
        # level (does not recurse into nested patchworks).
        patchwork = ((p1 / p2) | p3) / p4
        composed = patchwork * theme_bw()
        assert isinstance(composed, Patchwork)
        gt = patchworkGrob(composed)
        assert gt is not None
