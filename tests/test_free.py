"""Unit tests for ``free()`` and the R-style liberation helpers (Slice 4/5)."""

from __future__ import annotations

import pandas as pd
import pytest
from ggplot2_py import aes, geom_point, ggplot

import patchwork as pw
from patchwork._ggplot_attrs import safe_get
from patchwork.free import is_free_plot


@pytest.fixture
def p1():
    df = pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]})
    return ggplot(df, aes(x="x", y="y")) + geom_point()


@pytest.fixture
def p2():
    df = pd.DataFrame({"x": [4, 5, 6], "y": [6, 5, 4]})
    return ggplot(df, aes(x="x", y="y")) + geom_point()


class TestFreeCopyOnModify:
    """``free()`` must not mutate its argument (R's copy-on-modify)."""

    def test_original_not_marked(self, p1):
        freed = pw.free(p1)
        assert freed is not p1
        assert not safe_get(p1, "_ptw_free_plot", False)
        assert is_free_plot(freed)

    def test_settings_isolated(self, p1):
        """Two free() calls on the same plot produce independent settings."""
        a = pw.free(p1, side="t")
        b = pw.free(p1, side="b")
        a_settings = safe_get(a, "free_settings") or {}
        b_settings = safe_get(b, "free_settings") or {}
        assert "t" in a_settings
        assert "b" in b_settings
        # Neither should see the other's side.
        assert "b" not in a_settings
        assert "t" not in b_settings


class TestFreeArgValidation:
    def test_invalid_type_raises(self, p1):
        with pytest.raises(ValueError, match="type"):
            pw.free(p1, type="bogus")

    def test_invalid_side_chars_raise(self, p1):
        with pytest.raises(ValueError, match="t, r, b, and l"):
            pw.free(p1, side="x")

    def test_invalid_plot_type_raises(self):
        with pytest.raises(TypeError):
            pw.free("not a plot")


class TestFreePanelLiberation:
    """Full composition must produce ``free_panel`` compound grobs."""

    def test_free_produces_free_panel_grob(self, p1, p2):
        from ggplot2_py import labs

        composed = pw.free(p1) | (p2 + labs(x="long\nlabel\nacross\nlines"))
        gt = pw.patchworkGrob(composed)
        assert any(n.startswith("free_panel") for n in gt.layout["name"])

    def test_free_side_left_only_liberates_left(self, p1, p2):
        composed = p1 / pw.free(p2, side="l")
        gt = pw.patchworkGrob(composed)
        assert any(n.startswith("free_panel") for n in gt.layout["name"])
        # p1 (unfreed) still has a regular panel grob.
        assert any(n.startswith("panel-") and not n.startswith("panel-area") for n in gt.layout["name"])


class TestFreeTypes:
    @pytest.mark.parametrize("free_type", ["panel", "label", "space"])
    def test_all_types_render(self, p1, p2, free_type):
        composed = pw.free(p1, type=free_type) | p2
        gt = pw.patchworkGrob(composed)
        # Every type must at least render successfully; structural specifics
        # vary by type.
        assert gt is not None
        assert len(gt.layout["name"]) > 0
