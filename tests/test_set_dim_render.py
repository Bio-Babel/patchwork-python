"""``set_dim`` render path — exercise ``_apply_fixed_dim_margins``.

R: ``ggplot_gtable.fixed_dim_build`` rewrites the rendered table's
outer margins. Python folds this into ``_apply_fixed_dim_margins``
called inside ``plot_table.GGPlot``. Tests confirm the rendered
gtable's outer margins really do equal the captured dim.
"""
from __future__ import annotations

import pytest
from ggplot2_py import (
    aes, find_panel, geom_point, ggplot, ggtitle,
)
from grid_py import convert_height, convert_width

import patchwork as pw
from patchwork.core import plot_table


@pytest.fixture
def df():
    from patchwork._datasets import mtcars
    return mtcars().reset_index()


def _outer_margins_mm(gt):
    pp = find_panel(gt)
    w = convert_width(gt.widths, "mm").values
    h = convert_height(gt.heights, "mm").values
    return (
        list(w[: pp["l"] - 1]),
        list(w[pp["r"]:]),
        list(h[: pp["t"] - 1]),
        list(h[pp["b"]:]),
    )


class TestSetDimRendersWithCapturedMargins:

    def test_round_trip_set_dim(self, df):
        # Two plots with different left-axis widths.
        p_short = ggplot(df) + geom_point(aes(x="hp", y="mpg"))
        p_long = (ggplot(df)
                  + geom_point(aes(x="hp", y="disp", colour="cyl"))
                  + ggtitle("Plot with title + colour guide"))

        # Capture p_long's dim and apply to p_short.
        d = pw.get_dim(p_long)
        p_aligned = pw.set_dim(p_short, d)

        # Render aligned plot — must use the captured margins.
        gt = plot_table(p_aligned, "auto")
        l, r, t, b = _outer_margins_mm(gt)

        # Each component should match the captured PlotDimension.
        assert len(l) == len(d.l), f"l length: {len(l)} vs {len(d.l)}"
        assert len(r) == len(d.r)
        assert len(t) == len(d.t)
        assert len(b) == len(d.b)
        for actual, expected in zip(l, d.l):
            assert abs(actual - expected) < 1e-6, f"l mismatch: {actual} vs {expected}"
        for actual, expected in zip(r, d.r):
            assert abs(actual - expected) < 1e-6
        for actual, expected in zip(t, d.t):
            assert abs(actual - expected) < 1e-6
        for actual, expected in zip(b, d.b):
            assert abs(actual - expected) < 1e-6

    def test_align_patches_uniform_margins(self, df):
        # After align_patches, every plot must have IDENTICAL outer margins.
        p1 = ggplot(df) + geom_point(aes(x="mpg", y="disp"))
        p2 = (ggplot(df) + geom_point(aes(x="hp", y="wt", colour="cyl"))
              + ggtitle("With guide"))
        p3 = ggplot(df) + geom_point(aes(x="cyl", y="qsec")) + ggtitle("With title")

        aligned = pw.align_patches(p1, p2, p3)
        margins = []
        for p in aligned:
            gt = plot_table(p, "auto")
            margins.append(_outer_margins_mm(gt))

        ref = margins[0]
        for i, m in enumerate(margins[1:], 1):
            for axis_idx, axis_name in enumerate("lrtb"):
                assert m[axis_idx] == pytest.approx(ref[axis_idx]), \
                    f"plot {i} {axis_name} differs from plot 0"
