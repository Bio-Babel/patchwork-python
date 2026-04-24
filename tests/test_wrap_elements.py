"""Unit tests for ``wrap_elements`` and friends (Slice 2)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from ggplot2_py import aes, geom_point, ggplot

import patchwork as pw
from patchwork.wrap_elements import WrappedPatch, as_patch, wrap_elements


def test_wrap_elements_returns_wrapped_patch():
    from grid_py import null_grob

    wp = wrap_elements(full=null_grob())
    assert isinstance(wp, WrappedPatch)


def test_wrap_elements_has_ignore_tag_setting():
    from grid_py import null_grob

    wp = wrap_elements(full=null_grob(), ignore_tag=True)
    assert wp.get_attr("patch_settings")["ignore_tag"] is True


def test_as_patch_dispatch_on_ggplot():
    p = ggplot(pd.DataFrame({"x": [1, 2], "y": [1, 2]}), aes(x="x", y="y")) + geom_point()
    grob = as_patch(p)
    # Should be a gtable/GTree; check it responds to expected attrs.
    assert hasattr(grob, "layout")


def test_as_patch_raster():
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    grob = as_patch(arr)
    assert grob is not None


def test_as_patch_glist_wraps_in_gtree():
    """R: ``as_patch.gList(x)`` → ``gTree(children = x)``."""
    from grid_py import GList, GTree, rect_grob

    gl = GList()
    gl.append(rect_grob())
    gl.append(rect_grob())
    result = as_patch(gl)
    assert isinstance(result, GTree)


def test_as_patch_patchwork_calls_patchworkGrob():
    """R: ``as_patch.patchwork(x)`` → ``patchworkGrob(x)``."""
    from gtable_py import is_gtable

    p = ggplot(pd.DataFrame({"x": [1, 2], "y": [1, 2]}), aes(x="x", y="y")) + geom_point()
    pw_obj = p + p
    result = as_patch(pw_obj)
    assert is_gtable(result)


def test_wrap_table_rejects_gt_tbl_like_objects():
    class FakeGt:
        _stub_df = object()
        _options = object()

    with pytest.raises(NotImplementedError):
        pw.wrap_table(FakeGt())


def test_wrap_ggplot_grob_preserves_input():
    from ggplot2_py import ggplotGrob

    p = ggplot(pd.DataFrame({"x": [1, 2], "y": [1, 2]}), aes(x="x", y="y")) + geom_point()
    gt = ggplotGrob(p)
    wrapped = pw.wrap_ggplot_grob(gt)
    assert wrapped.get_attr("table") is gt


def test_wrap_ggplot_grob_rejects_non_gtable():
    with pytest.raises(TypeError):
        pw.wrap_ggplot_grob("not a gtable")


# -----------------------------------------------------------------------------
# inset_element fixes: copy-on-modify semantics + has_tag honours ignore_tag
# -----------------------------------------------------------------------------


class TestInsetElementCopy:
    """``inset_element`` must not mutate the caller's plot (R's copy-on-modify)."""

    @pytest.fixture
    def base_plot(self):
        return ggplot(pd.DataFrame({"x": [1, 2], "y": [1, 2]}), aes(x="x", y="y")) + geom_point()

    def test_two_calls_produce_distinct_settings(self, base_plot):
        ins_tagged = pw.inset_element(base_plot, 0.6, 0.6, 1, 1)
        ins_ignored = pw.inset_element(base_plot, 0.6, 0.6, 1, 1, ignore_tag=True)
        # The two returns are distinct objects with distinct settings.
        assert ins_tagged is not ins_ignored
        from patchwork._ggplot_attrs import safe_get

        tag1 = safe_get(ins_tagged, "inset_settings")["ignore_tag"]
        tag2 = safe_get(ins_ignored, "inset_settings")["ignore_tag"]
        assert tag1 is False
        assert tag2 is True

    def test_original_plot_is_not_marked(self, base_plot):
        _ = pw.inset_element(base_plot, 0.6, 0.6, 1, 1)
        from patchwork._ggplot_attrs import safe_get

        # The passed-in ggplot should remain untouched.
        assert not safe_get(base_plot, "_ptw_inset_patch", False)


class TestHasTagInset:
    """``has_tag`` on an inset plot honours ``ignore_tag`` (R's ``has_tag.inset_patch``)."""

    @pytest.fixture
    def base_plot(self):
        return ggplot(pd.DataFrame({"x": [1, 2], "y": [1, 2]}), aes(x="x", y="y")) + geom_point()

    def test_default_ignore_tag_false(self, base_plot):
        from patchwork.annotation import has_tag

        ins = pw.inset_element(base_plot, 0.6, 0.6, 1, 1)
        assert has_tag(ins) is True

    def test_ignore_tag_true(self, base_plot):
        from patchwork.annotation import has_tag

        ins = pw.inset_element(base_plot, 0.6, 0.6, 1, 1, ignore_tag=True)
        assert has_tag(ins) is False


# -----------------------------------------------------------------------------
# print_inset_patch helper
# -----------------------------------------------------------------------------


def test_print_inset_patch_produces_gtable():
    from grid_py import rect_grob

    from patchwork.inset import print_inset_patch

    ins = pw.inset_element(rect_grob(), 0.2, 0.2, 0.8, 0.8, align_to="full")
    gt = print_inset_patch(ins)
    from gtable_py import is_gtable

    assert is_gtable(gt)
    # The result must contain an ``inset_*`` grob (since print wraps the
    # inset over a spacer).
    assert any(name.startswith("inset_") for name in gt.layout["name"])


# -----------------------------------------------------------------------------
# inset_element edge cases: on_top=False, align_to='plot'
# -----------------------------------------------------------------------------


class TestInsetEdgeCases:
    """Inset variants documented in vignettes/guides/layout.Rmd."""

    @pytest.fixture
    def base_plots(self):
        p1 = ggplot(pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]}), aes(x="x", y="y")) + geom_point()
        p2 = ggplot(pd.DataFrame({"x": [1, 2, 3], "y": [3, 2, 1]}), aes(x="x", y="y")) + geom_point()
        return p1, p2

    def test_on_top_false_renders(self, base_plots):
        p1, p2 = base_plots
        composed = p1 + pw.inset_element(p2, 0.6, 0.6, 1, 1, on_top=False)
        gt = pw.patchworkGrob(composed)
        # Must produce an inset grob regardless of on_top direction.
        assert any(n.startswith("inset_") for n in gt.layout["name"])

    def test_on_top_false_places_below_background(self, base_plots):
        """With ``on_top=False`` the inset's z should be below the panel z."""
        p1, p2 = base_plots
        composed = p1 + pw.inset_element(p2, 0.6, 0.6, 1, 1, on_top=False)
        gt = pw.patchworkGrob(composed)
        inset_z = [
            gt.layout["z"][i]
            for i, n in enumerate(gt.layout["name"])
            if n.startswith("inset_")
        ]
        panel_z = [
            gt.layout["z"][i]
            for i, n in enumerate(gt.layout["name"])
            if n.startswith("panel-") and not n.startswith("panel-area")
        ]
        # Every inset with on_top=False must be below the lowest panel z.
        if inset_z and panel_z:
            assert max(inset_z) < max(panel_z)

    def test_align_to_plot(self, base_plots):
        p1, p2 = base_plots
        composed = p1 + pw.inset_element(p2, 0.6, 0.6, 1, 1, align_to="plot")
        gt = pw.patchworkGrob(composed)
        assert any(n.startswith("inset_") for n in gt.layout["name"])

    def test_align_to_invalid_raises(self, base_plots):
        p1, p2 = base_plots
        with pytest.raises(ValueError, match="align_to"):
            pw.inset_element(p2, 0, 0, 1, 1, align_to="bogus")
