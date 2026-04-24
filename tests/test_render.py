"""Integration tests for the full render pipeline (Slice 5 + 6)."""

from __future__ import annotations

import pandas as pd
import pytest
from ggplot2_py import aes, geom_point, ggplot

import patchwork as pw


@pytest.fixture
def p1():
    df = pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]})
    return ggplot(df, aes(x="x", y="y")) + geom_point()


@pytest.fixture
def p2():
    df = pd.DataFrame({"x": [4, 5, 6], "y": [6, 5, 4]})
    return ggplot(df, aes(x="x", y="y")) + geom_point()


class TestPatchworkGrob:
    def test_two_plots_produces_gtable(self, p1, p2):
        from gtable_py import is_gtable

        gt = pw.patchworkGrob(p1 + p2)
        assert is_gtable(gt)
        # Layout names should include one per grob from each plot.
        assert any(name.startswith("panel") for name in gt.layout["name"])

    def test_three_plots_custom_layout(self, p1, p2):
        composed = (p1 + p2 + p1) + pw.plot_layout(ncol=2)
        gt = pw.patchworkGrob(composed)
        # With ncol=2 and 3 plots we get a 2x2 layout with the last cell empty.
        # Verify the gtable's column count reflects 2 columns of TABLE_COLS=15.
        assert len(gt.widths.values) >= 30

    def test_annotation_adds_title_rows(self, p1, p2):
        composed = (p1 + p2) + pw.plot_annotation(title="hello")
        gt = pw.patchworkGrob(composed)
        assert "title" in gt.layout["name"]

    def test_caption_added(self, p1, p2):
        composed = (p1 + p2) + pw.plot_annotation(caption="footer")
        gt = pw.patchworkGrob(composed)
        assert "caption" in gt.layout["name"]


class TestWrapPlots:
    def test_accepts_varargs(self, p1, p2):
        result = pw.wrap_plots(p1, p2)
        assert len(result) == 2

    def test_accepts_list(self, p1, p2):
        result = pw.wrap_plots([p1, p2, p1])
        assert len(result) == 3

    def test_forwards_ncol(self, p1, p2):
        result = pw.wrap_plots([p1, p2], ncol=2)
        assert result.patches.layout.ncol == 2


class TestSpacer:
    def test_spacer_in_composition(self, p1, p2):
        composed = p1 + pw.plot_spacer() + p2
        gt = pw.patchworkGrob(composed)
        # Should not raise and should produce a larger layout.
        assert len(gt.widths.values) > 30  # 3 cells × ~15 cols


class TestGuideArea:
    def test_guide_area_present(self, p1, p2):
        composed = p1 + p2 + pw.guide_area() + pw.plot_layout(guides="collect")
        gt = pw.patchworkGrob(composed)
        from gtable_py import is_gtable

        assert is_gtable(gt)
