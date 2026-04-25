"""``wrap_table`` panel × space matrix — exercises every branch in
``apply_wrapped_table_adjustment`` (R patchGrob.wrapped_table:89-140).

R's ``wrap_table`` accepts ``panel ∈ {body, full, rows, cols}`` and
``space ∈ {free, free_x, free_y, fixed}``. Each cell of the 4×4
matrix routes through different branches in the post-resolve
adjustment. Single panel='full', space='fixed' was the case that
infinite-looped before this session's grid_py fix; we test all 16
combinations now.
"""
from __future__ import annotations

import pytest
from ggplot2_py import aes, geom_point, ggplot

from patchwork import patchworkGrob, wrap_table


great_tables = pytest.importorskip("great_tables")
GT = great_tables.GT


@pytest.fixture(scope="module")
def df():
    from patchwork._datasets import mtcars
    return mtcars().reset_index().head(5)


@pytest.fixture
def p1(df):
    return ggplot(df) + geom_point(aes(x="mpg", y="disp"))


PANELS = ("body", "full", "rows", "cols")
SPACES = ("free", "free_x", "free_y", "fixed")


@pytest.mark.parametrize("panel", PANELS)
@pytest.mark.parametrize("space", SPACES)
def test_wrap_table_panel_x_space(p1, df, panel, space):
    """Every (panel, space) combination must compose + render fast.

    Pre-fix: ``panel='full', space='fixed'`` infinite-looped because
    the inner GT vp's width = grobWidth(itself) re-entered
    _evaluate_grob_unit and corrupted the parent chain (bypass_pyc
    bug in grid_py state.push_viewport, fixed upstream).
    """
    wt = wrap_table(GT(df), panel=panel, space=space)
    composed = p1 + wt
    gt = patchworkGrob(composed)
    assert gt is not None


def test_wrap_table_dataframe_auto_promotes(p1, df):
    # R: wrap_table(non-gt_tbl) calls gt(as.data.frame(table)).
    # Python: wrap_table(DataFrame) auto-promotes via GT(df).
    wt = wrap_table(df)
    composed = p1 + wt
    gt = patchworkGrob(composed)
    assert gt is not None


def test_wrap_table_ignore_tag(df):
    # R: wrap_table(table, ignore_tag=TRUE) — tag is suppressed.
    wt = wrap_table(GT(df), ignore_tag=True)
    settings = wt.get_attr("patch_settings", {})
    assert settings.get("ignore_tag") is True


def test_wrap_table_invalid_panel_arg_raises(df):
    with pytest.raises(ValueError, match="panel"):
        wrap_table(GT(df), panel="nonsense")


def test_wrap_table_invalid_space_arg_raises(df):
    with pytest.raises(ValueError, match="space"):
        wrap_table(GT(df), space="nonsense")


# ---------------------------------------------------------------------------
# Stub (rowname_col) tests — exercise apply_wrapped_table_adjustment's
# ``row_head > 0`` and ``col_head > 0`` branches that R's
# patchGrob.wrapped_table covers (R/wrap_table.R:102-126).
# ---------------------------------------------------------------------------


@pytest.fixture
def df_stub(df):
    # GT with a stub (rowname_col) → n_row_headers = 1 → exercises
    # the row_head > 0 branch (panel='body' or 'rows' subtracts the
    # stub column from the panel-area's width).
    return GT(df, rowname_col="mpg")


@pytest.fixture
def p_simple(df):
    return ggplot(df) + geom_point(aes(x="mpg", y="disp"))


@pytest.mark.parametrize("panel", ("body", "rows"))
def test_wrap_table_with_stub_panel(p_simple, df_stub, panel):
    """panel='body' or 'rows' with a stub → row_head=1 branch fires."""
    wt = wrap_table(df_stub, panel=panel)
    composed = p_simple + wt
    gt = patchworkGrob(composed)
    assert gt is not None


@pytest.mark.parametrize("panel", ("body", "cols"))
def test_wrap_table_with_heading_col_head(p_simple, df, panel):
    """Tables with column headers above the body exercise the col_head
    branch (apply_wrapped_table_adjustment lines 286-296).
    """
    g = GT(df).tab_header(title="Title", subtitle="Sub")
    wt = wrap_table(g, panel=panel)
    composed = p_simple + wt
    gt = patchworkGrob(composed)
    assert gt is not None
