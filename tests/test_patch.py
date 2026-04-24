"""Unit tests for ``_patch`` and adjacent primitives (Slice 1)."""

from __future__ import annotations

import pandas as pd
import pytest
from ggplot2_py import aes, geom_point, ggplot
from gtable_py import is_gtable

import patchwork as pw
from patchwork._constants import PANEL_COL, PANEL_ROW, TABLE_COLS, TABLE_ROWS
from patchwork._patch import Patch, is_patch, make_patch, print_patch
from patchwork.add_plot import Patchwork, is_patchwork


def test_make_patch_returns_patch():
    p = make_patch()
    assert isinstance(p, Patch)
    assert is_patch(p)


def test_make_patch_table_dimensions():
    p = make_patch()
    assert len(p.table.widths.values) == TABLE_COLS
    assert len(p.table.heights.values) == TABLE_ROWS


def test_panel_cell_is_null_unit():
    p = make_patch()
    assert p.table.widths.values[PANEL_COL - 1] == 1.0
    assert p.table.widths.units_list[PANEL_COL - 1] == "null"
    assert p.table.heights.values[PANEL_ROW - 1] == 1.0
    assert p.table.heights.units_list[PANEL_ROW - 1] == "null"


# -----------------------------------------------------------------------------
# print_patch / plot.patch alias
# -----------------------------------------------------------------------------


def test_print_patch_returns_gtable():
    gt = print_patch(make_patch())
    assert is_gtable(gt)


def test_print_patch_has_panel_patch_grob():
    gt = print_patch(make_patch())
    # The canonical make_patch places a zeroGrob named ``panel_patch`` at
    # (PANEL_ROW, PANEL_COL).
    assert "panel_patch" in gt.layout["name"]


# -----------------------------------------------------------------------------
# Patch.__add__ — LHS-first ordering (added to fix plot_spacer() + inset)
# -----------------------------------------------------------------------------


class TestPatchAdd:
    """Patch + x preserves LHS-first semantics (R's ``+.gg`` via S3)."""

    @pytest.fixture
    def ggplot_obj(self):
        df = pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]})
        return ggplot(df, aes(x="x", y="y")) + geom_point()

    def test_patch_plus_none_returns_self(self):
        sp = pw.plot_spacer()
        assert (sp + None) is sp

    def test_patch_plus_ggplot_puts_patch_first(self, ggplot_obj):
        sp = pw.plot_spacer()
        pw_obj = sp + ggplot_obj
        assert is_patchwork(pw_obj)
        # LHS (spacer) should be in the patches list; RHS becomes active plot
        assert pw_obj.plot is ggplot_obj
        assert any(p is sp for p in pw_obj.patches.plots)

    def test_patch_plus_patch_yields_filler_root(self):
        s1 = pw.plot_spacer()
        s2 = pw.plot_spacer()
        pw_obj = s1 + s2
        assert is_patchwork(pw_obj)
        # Both spacers should end up as children
        assert len(pw_obj.patches.plots) == 2

    def test_patch_plus_patchwork_prepends_patch(self, ggplot_obj):
        sp = pw.plot_spacer()
        root = ggplot_obj + ggplot_obj  # a Patchwork with 2 plots
        composed = sp + root
        assert is_patchwork(composed)
        # The spacer should be included in the final composition somewhere
        from patchwork.add_plot import get_patches

        all_plots = get_patches(composed).plots
        assert any(p is sp for p in all_plots)
