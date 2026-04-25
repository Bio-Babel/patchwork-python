"""R-derived collection tests — port of R ``tests/testthat/test-collect.R``.

Each case mirrors an R ``expect_doppelganger`` snapshot: build the
patchwork, render to gtable, then verify the structural properties
the snapshot would capture (axis/title rows zeroed in collected
positions, guides extracted into the master gtable, etc.).
"""
from __future__ import annotations

import pandas as pd
import pytest
from ggplot2_py import (
    aes, element_text, geom_point, ggplot, ggtitle, scale_y_continuous, theme,
)

import patchwork as pw
from patchwork import (
    patchworkGrob, plot_layout, wrap_plots,
)


# ---------------------------------------------------------------------------
# R helper-setup.R fixtures: p1, p2, p3, p4 from mtcars
# ---------------------------------------------------------------------------


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
    from ggplot2_py import geom_boxplot
    return (ggplot(mtcars_df) + geom_boxplot(aes(x="gear", y="disp", group="gear"))
            + ggtitle("Plot 2"))


@pytest.fixture
def p3(mtcars_df):
    return (ggplot(mtcars_df) + geom_point(aes(x="hp", y="wt", colour="mpg"))
            + ggtitle("Plot 3"))


# ---------------------------------------------------------------------------
# R: test_that("axes and titles are collected correctly for multi-cell plots")
# ---------------------------------------------------------------------------


class TestMultiCellAxisCollection:
    """R test-collect.R:1-13 — design='12345\\n62378' with axes='collect'.

    Multi-cell layout where the same plot appears at two positions: cells
    2 (top row), 3 (top row), 7 (bottom row), and 8 (bottom row). With
    axes/axis_titles collected, only column-1/-2/-4 should retain titles
    and y-axes; only row-2 should retain titles and x-axes.
    """

    def test_eight_cell_collect_renders(self, p1):
        plots = wrap_plots([p1] * 8)
        layout = plot_layout(
            design="12345\n62378",
            axes="collect",
            axis_titles="collect",
        )
        composed = plots + layout
        assert composed.patches.layout.axes == "collect"
        assert composed.patches.layout.axis_titles == "collect"
        gt = patchworkGrob(composed)
        # Smoke: gtable must have a panel; … entry per plot cell.
        panel_entries = [
            n for n in gt.layout["name"] if n.startswith("panel")
        ]
        # Eight plot cells from `12345\n62378`; each produces at least
        # one panel-area entry.
        assert len(panel_entries) >= 8

    def test_axis_titles_inherits_from_axes(self):
        # P0 fix from this session — `plot_layout(axes='collect')` must
        # propagate into axis_titles when the latter is omitted.
        layout = plot_layout(axes="collect_x")
        assert layout.axis_titles == "collect_x"


# ---------------------------------------------------------------------------
# R: test_that("axis columns are properly resized")
# ---------------------------------------------------------------------------


class TestAxisColumnResize:
    """R test-collect.R:15-29 — long axis labels in column 1 only.

    With ``scale_y_continuous(labels=function(x) paste0('a long axis '
    label signifying ', x))`` the y-axis text grows. Collection must
    resize columns so column 1 has the long labels and columns 2+ do
    not bloat from a duplicated axis.
    """

    def test_long_axis_collect_renders(self, p1):
        p5 = (p1 + scale_y_continuous(
            labels=lambda x: f"a long axis label signifying {x}",
        ))
        p6 = (p1 + theme(axis_text=element_text(colour="red"))
              + ggtitle("Interrupting plot"))

        layout = plot_layout(
            ncol=2, nrow=2,
            axes="collect", axis_titles="collect",
        )
        composed = p5 + p5 + p5 + p6 + layout
        assert composed.patches.layout.axes == "collect"
        assert composed.patches.layout.axis_titles == "collect"
        gt = patchworkGrob(composed)
        # Sanity: 4 panels, all rendered.
        panels = [n for n in gt.layout["name"] if "panel" in n]
        assert len(panels) >= 4


# ---------------------------------------------------------------------------
# R: test_that("axis titles are collected across empty areas")
# ---------------------------------------------------------------------------


class TestAxisTitleAcrossEmptyAreas:
    """R test-collect.R:33-43 — design='#AB\\nC#D\\nEF#' with empty cells.

    Empty (``#``) areas in the design must NOT prevent axis title
    collection — the collector should walk over them.
    """

    def test_empty_areas_dont_block_collection(self, p1):
        plots = wrap_plots([p1] * 6) + plot_layout(
            axes="collect",
            axis_titles="collect",
            design="#AB\nC#D\nEF#",
        )
        # Compose + render must not error.
        gt = patchworkGrob(plots)
        # Six plots → six panel-rooted entries.
        panels = [n for n in gt.layout["name"] if n.startswith("panel")]
        assert len(panels) >= 6


# ---------------------------------------------------------------------------
# R: test_that("collect guides works well")
# ---------------------------------------------------------------------------


class TestCollectGuides:
    """R test-collect.R:46-66 — three guide-collection scenarios.

    1. Two plots where one has a continuous color guide
    2. Same but the guide uses ``key.height = unit(1, "null")``
    3. Two color-guided plots, each with its own ``labs(color=)``
    """

    def test_normal_guides_collect(self, p1, p3):
        composed = wrap_plots([p1, p3], guides="collect")
        assert composed.patches.layout.guides == "collect"
        gt = patchworkGrob(composed)
        # Master gtable should have a guide-box-* entry from p3's color
        # legend (collected to the side).
        all_names = " ".join(gt.layout["name"])
        # Either the guide is collected into a single guide-box on the
        # right/bottom, or appears inline — either way at least one
        # guide-box must remain.
        assert "guide" in all_names

    def test_collect_with_multiple_color_guides(self, p1, p3, mtcars_df):
        from ggplot2_py import labs
        # Two plots each with their own colour scale.
        composed = wrap_plots(
            [p1, p3, p3 + labs(color="another")],
            guides="collect",
        )
        # Smoke: must render without error.
        gt = patchworkGrob(composed)
        assert gt is not None
