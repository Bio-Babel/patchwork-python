"""``wrap_plots`` — packing helpers around plot_layout.

R: ``wrap_plots(...)`` packs an arbitrary number of ggplots into a
single patchwork, optionally accepting layout kwargs (ncol, nrow,
widths, heights, guides, design, etc.). Tests cover (a) the
positional-args path, (b) the iterable path, (c) layout kwarg
forwarding, (d) design-string path.
"""
from __future__ import annotations

import pytest
from ggplot2_py import aes, geom_point, ggplot

from patchwork import Patchwork, patchworkGrob, wrap_plots


@pytest.fixture
def df():
    from patchwork._datasets import mtcars
    return mtcars().reset_index()


@pytest.fixture
def p1(df):
    return ggplot(df) + geom_point(aes(x="mpg", y="disp"))


@pytest.fixture
def p2(df):
    return ggplot(df) + geom_point(aes(x="hp", y="wt"))


@pytest.fixture
def p3(df):
    return ggplot(df) + geom_point(aes(x="cyl", y="qsec"))


class TestWrapPlots:

    def test_positional_args(self, p1, p2, p3):
        composed = wrap_plots(p1, p2, p3)
        assert isinstance(composed, Patchwork)
        assert len(composed) == 3

    def test_iterable_arg(self, p1, p2, p3):
        composed = wrap_plots([p1, p2, p3])
        assert isinstance(composed, Patchwork)
        assert len(composed) == 3

    def test_ncol_kwarg(self, p1, p2, p3):
        composed = wrap_plots(p1, p2, p3, ncol=2)
        assert composed.patches.layout.ncol == 2

    def test_nrow_kwarg(self, p1, p2, p3):
        composed = wrap_plots(p1, p2, p3, nrow=3)
        assert composed.patches.layout.nrow == 3

    def test_design_kwarg(self, p1, p2):
        # A 2-cell design.
        composed = wrap_plots(p1, p2, design="A\nB")
        assert composed.patches.layout.design is not None

    def test_guides_kwarg(self, p1, p2):
        composed = wrap_plots(p1, p2, guides="collect")
        assert composed.patches.layout.guides == "collect"

    def test_renders_to_gtable(self, p1, p2, p3):
        composed = wrap_plots(p1, p2, p3, ncol=2)
        gt = patchworkGrob(composed)
        assert gt is not None

    def test_single_plot(self, p1):
        # Single-plot wrap is still a Patchwork.
        composed = wrap_plots(p1)
        assert isinstance(composed, Patchwork)
        assert len(composed) == 1

    def test_widths_kwarg(self, p1, p2):
        composed = wrap_plots(p1, p2, widths=[1, 2])
        # patches.layout.widths is a 1-d list (or Unit); just confirm it's set.
        assert composed.patches.layout.widths is not None

    def test_heights_kwarg(self, p1, p2):
        composed = wrap_plots(p1, p2, heights=[1, 2])
        assert composed.patches.layout.heights is not None

    def test_byrow_kwarg(self, p1, p2, p3):
        composed = wrap_plots(p1, p2, p3, ncol=2, byrow=False)
        assert composed.patches.layout.byrow is False

    def test_tag_level_kwarg(self, p1, p2):
        composed = wrap_plots(p1, p2, tag_level="new")
        assert composed.patches.layout.tag_level == "new"
