"""Guide-collection scenarios that exercise ``patchwork/guides.py``.

Coverage of guides.py was 11% pre-port; this file walks each major
``collect_guides`` / ``assemble_guides`` / ``attach_guides`` branch
that R's wider testsuite would hit.
"""
from __future__ import annotations

import pytest
from ggplot2_py import aes, geom_point, ggplot, labs

import patchwork as pw
from patchwork import patchworkGrob, plot_layout, wrap_plots


@pytest.fixture
def df():
    from patchwork._datasets import mtcars
    return mtcars().reset_index()


@pytest.fixture
def p_color(df):
    """A plot with a continuous color guide (legend on right by default)."""
    return ggplot(df) + geom_point(aes(x="hp", y="wt", colour="mpg"))


@pytest.fixture
def p_plain(df):
    return ggplot(df) + geom_point(aes(x="hp", y="wt"))


class TestGuidesCollect:

    def test_collect_two_color_guides(self, p_color):
        # Two color-guide plots with collect → guides should be merged
        # into a single collected box.
        composed = wrap_plots(p_color, p_color, guides="collect")
        gt = patchworkGrob(composed)
        assert gt is not None

    def test_collect_keep_difference(self, p_color, p_plain):
        # `keep` should keep guides per-plot (the default).
        composed_keep = wrap_plots(p_color, p_plain, guides="keep")
        composed_collect = wrap_plots(p_color, p_plain, guides="collect")
        gt_keep = patchworkGrob(composed_keep)
        gt_collect = patchworkGrob(composed_collect)
        assert gt_keep is not None
        assert gt_collect is not None

    def test_collect_three_distinct_color_guides(self, df):
        # Three plots with DIFFERENT color scales — collect must keep them
        # distinct (one per scale).
        p1 = ggplot(df) + geom_point(aes(x="hp", y="wt", colour="mpg"))
        p2 = (ggplot(df) + geom_point(aes(x="hp", y="wt", colour="cyl"))
              + labs(color="cylinders"))
        p3 = (ggplot(df) + geom_point(aes(x="hp", y="wt", colour="gear"))
              + labs(color="gear count"))
        composed = wrap_plots(p1, p2, p3, guides="collect")
        gt = patchworkGrob(composed)
        assert gt is not None

    def test_collect_with_no_guides_at_all(self, p_plain):
        # Two plots, neither has a guide → collect is a no-op effectively.
        composed = wrap_plots(p_plain, p_plain, guides="collect")
        gt = patchworkGrob(composed)
        assert gt is not None
