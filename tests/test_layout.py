"""Unit tests for ``layout.py`` (Slice 1)."""

from __future__ import annotations

import pytest

from patchwork.layout import (
    PatchArea,
    area,
    as_areas,
    create_design,
    plot_layout,
)


class TestArea:
    def test_single_cell(self):
        a = area(1, 1)
        assert len(a) == 1
        assert a.t == [1] and a.l == [1] and a.b == [1] and a.r == [1]

    def test_rectangle(self):
        a = area(1, 1, 2, 3)
        assert a.t == [1] and a.l == [1] and a.b == [2] and a.r == [3]

    def test_empty(self):
        assert len(area()) == 0

    def test_concatenation(self):
        a = area(1, 1) + area(2, 2, 3, 3)
        assert len(a) == 2
        assert a.t == [1, 2]
        assert a.b == [1, 3]

    def test_invalid_t_gt_b(self):
        with pytest.raises(ValueError):
            area(3, 1, 1, 2)

    def test_invalid_l_gt_r(self):
        with pytest.raises(ValueError):
            area(1, 3, 2, 2)


class TestAsAreas:
    def test_none(self):
        assert as_areas(None) is None

    def test_identity_on_patch_area(self):
        a = area(1, 1)
        assert as_areas(a) is a

    def test_from_string(self):
        s = as_areas("""
        A##
        A#B
        ##B
        """)
        assert len(s) == 2
        # Areas sort alphabetically; A first (col 1), then B (col 3)
        assert s.t == [1, 2]
        assert s.l == [1, 3]
        assert s.b == [2, 3]
        assert s.r == [1, 3]

    def test_hash_is_hole(self):
        with pytest.raises(ValueError):
            # A spans diagonal — not rectangular → must raise
            as_areas("A#\n#A")

    def test_non_rectangular_raises(self):
        with pytest.raises(ValueError, match="rectangular"):
            as_areas("AA\nA")


class TestPlotLayout:
    def test_default_kwargs_are_waivers(self):
        pl = plot_layout()
        from patchwork._utils import is_waiver

        assert is_waiver(pl.ncol)
        assert is_waiver(pl.guides)

    def test_guides_arg_match(self):
        pl = plot_layout(guides="collect")
        assert pl.guides == "collect"
        with pytest.raises(ValueError, match="guides"):
            plot_layout(guides="bad")

    def test_design_string_parsed(self):
        pl = plot_layout(design="A\nB")
        assert isinstance(pl.design, PatchArea)
        assert len(pl.design) == 2

    def test_axis_titles_inherits_axes_when_omitted(self):
        # Mirrors R's `axis_titles = axes` lazy default-binding
        # (plot_layout.R:113). Calling plot_layout(axes='collect_x')
        # without axis_titles must propagate 'collect_x' onto axis_titles
        # so the downstream `do_change` merge in `update_ggplot(PlotLayout)`
        # writes both fields.
        pl = plot_layout(axes="collect_x")
        assert pl.axes == "collect_x"
        assert pl.axis_titles == "collect_x"

    def test_axis_titles_explicit_overrides_inheritance(self):
        # User passes axis_titles explicitly → no inheritance.
        pl = plot_layout(axes="collect", axis_titles="keep")
        assert pl.axes == "collect"
        assert pl.axis_titles == "keep"

    def test_axis_titles_default_when_neither_passed(self):
        # Both at WAIVER should stay at WAIVER (no merge writes either).
        from patchwork._utils import is_waiver

        pl = plot_layout()
        assert is_waiver(pl.axes)
        assert is_waiver(pl.axis_titles)

    def test_axis_titles_explicit_waiver_opts_out(self):
        # Passing WAIVER explicitly suppresses inheritance — both fields
        # remain WAIVER even though `axes` is set, matching R's
        # behaviour when `axis_titles=waiver()` is passed at the call site.
        from patchwork._utils import WAIVER, is_waiver

        pl = plot_layout(axes="collect_x", axis_titles=WAIVER)
        assert pl.axes == "collect_x"
        assert is_waiver(pl.axis_titles)


class TestCreateDesign:
    def test_byrow_true(self):
        d = create_design(2, 2, byrow=True)
        # 1 2
        # 3 4   → t: 1,1,2,2  l: 1,2,1,2
        assert d.t == [1, 1, 2, 2]
        assert d.l == [1, 2, 1, 2]

    def test_byrow_false(self):
        d = create_design(2, 2, byrow=False)
        # 1 3
        # 2 4   → t: 1,2,1,2  l: 1,1,2,2
        assert d.t == [1, 2, 1, 2]
        assert d.l == [1, 1, 2, 2]
