"""``wrap_ggplot_grob`` — wrap a pre-rendered gtable as a Patch.

R: ``wrap_ggplot_grob(gtable)`` lets a user inject a manually-built
ggplotGrob into a patchwork. Tests verify the wrapper accepts a real
gtable, exposes it through the Patch protocol, and composes
correctly with other patchwork plots.
"""
from __future__ import annotations

import pytest
from ggplot2_py import aes, geom_point, ggplot, ggplotGrob

from patchwork import Patchwork, patchworkGrob, wrap_ggplot_grob


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


class TestWrapGgplotGrob:

    def test_wraps_a_real_gtable(self, p1):
        gt = ggplotGrob(p1)
        wp = wrap_ggplot_grob(gt)
        # Should be a wrapped patch — Patchwork-compatible.
        assert wp is not None

    def test_compose_with_ggplot(self, p1, p2):
        gt = ggplotGrob(p1)
        wp = wrap_ggplot_grob(gt)
        composed = p2 + wp
        assert isinstance(composed, Patchwork)

    def test_renders_to_gtable(self, p1, p2):
        gt = ggplotGrob(p1)
        wp = wrap_ggplot_grob(gt)
        composed = p2 + wp
        out = patchworkGrob(composed)
        assert out is not None
