"""Regression tests for ``annotate_table`` row-height resolution.

Context
-------
R's ``annotate_table`` prepends three rows whose heights are lazy
``grobheight`` units keyed off the internal annotation grob. In
``grid_py.Unit``, a lazy unit carries its grob reference in the
``data`` field; rebuilding a Unit from ``values`` + ``units_list`` only
silently loses the reference and the lazy height resolves to 0 at
render time — collapsing title / subtitle / caption onto the same
zero-height row. This is exactly the bug the user reported where all
three annotations overlapped at the top of the composed patchwork.

Each test here asserts the row that a given annotation lives on has a
*positive* resolved height. We don't assert exact millimetres (that
drifts with font-rendering backend) — the invariant being guarded is
simply "the row is not 0 mm".
"""
from __future__ import annotations

import pandas as pd
import pytest
from ggplot2_py import aes, geom_bar, geom_boxplot, geom_point, ggplot, ggtitle
from grid_py import convert_height

from patchwork import patchworkGrob, plot_annotation


def _df():
    return pd.DataFrame({
        "mpg":  [15, 20, 25, 30],
        "disp": [300, 250, 200, 150],
        "gear": [3, 4, 5, 3],
    })


def _assert_row_has_height(gt, name: str) -> None:
    heights_mm = list(convert_height(gt.heights, "mm").values)
    indices = [
        i for i, n in enumerate(gt.layout["name"]) if n == name
    ]
    assert indices, f"{name!r} layout row missing from gtable"
    for i in indices:
        t = gt.layout["t"][i]
        row_h = heights_mm[t - 1]
        assert row_h > 0.1, (
            f"{name!r} landed on row {t} with resolved height "
            f"{row_h:.3f} mm — lazy grobheight unit did not carry its "
            f"data reference through annotate_table"
        )


def test_title_subtitle_caption_have_nonzero_heights():
    """Reproducer for the notebook bug where all three annotations overlapped."""
    df = _df()
    p1 = ggplot(df) + geom_point(aes(x="mpg", y="disp"))
    p2 = ggplot(df) + geom_boxplot(aes(x="gear", y="disp", group="gear"))
    p3 = ggplot(df) + geom_bar(aes(x="gear"))
    pw = (p1 + p2) / p3 + plot_annotation(
        title="The surprising truth about mtcars",
        subtitle="These 3 plots reveal yet-untold secrets",
        caption="Disclaimer: None of these plots are insightful",
    )
    gt = patchworkGrob(pw)
    _assert_row_has_height(gt, "title")
    _assert_row_has_height(gt, "subtitle")
    _assert_row_has_height(gt, "caption")


def test_title_only_has_nonzero_height():
    """The title path still resolves when subtitle / caption are absent."""
    df = _df()
    p = ggplot(df) + geom_point(aes(x="mpg", y="disp"))
    pw = (p + p) + plot_annotation(title="Only title")
    gt = patchworkGrob(pw)
    _assert_row_has_height(gt, "title")


def test_caption_only_has_nonzero_height():
    """The caption path exercises the tail-Unit rebuild; regression-guard that too."""
    df = _df()
    p = ggplot(df) + geom_point(aes(x="mpg", y="disp"))
    pw = (p + p) + plot_annotation(caption="Caption only")
    gt = patchworkGrob(pw)
    _assert_row_has_height(gt, "caption")


def _assert_nested_row_has_height(gt, nested_name: str, inner_name: str) -> None:
    """Drill into a ``patchwork-table-<N>`` compound grob and check that
    *inner_name*'s row has a positive resolved height. Exercises the
    nested-composition path where the inner grob is the flattened
    (p1+p2) layout embedded inside the outer (... / p3) table.
    """
    import re
    match = next(
        (i for i, n in enumerate(gt.layout["name"])
         if re.fullmatch(nested_name + r"-\d+", n)),
        None,
    )
    assert match is not None, (
        f"expected a {nested_name}-<N> compound grob in the outer layout"
    )
    inner = gt.grobs[match]
    assert hasattr(inner, "heights"), (
        f"{gt.layout['name'][match]} grob is not a Gtable"
    )
    inner_h_mm = list(convert_height(inner.heights, "mm").values)
    indices = [
        j for j, n in enumerate(inner.layout["name"])
        if n.startswith(inner_name + "-") or n == inner_name
    ]
    assert indices, (
        f"{inner_name!r} layout row missing from the nested "
        f"{gt.layout['name'][match]} compound"
    )
    for j in indices:
        t = inner.layout["t"][j]
        h = inner_h_mm[t - 1]
        assert h > 0.1, (
            f"nested {inner.layout['name'][j]!r} landed on row {t} "
            f"with resolved height {h:.3f} mm — lazy grobheight unit "
            f"lost its data reference inside the nested compound"
        )


def test_nested_compound_title_and_xlab_have_nonzero_heights():
    """Reproducer for the tag-overlap notebook bug where adding
    ``labs(tag=...)`` to each patch (via ``plot_annotation(tag_levels=)``)
    stripped the ``grobheight.data`` in
    ``ggplot2_py._table_add_tag``'s tail/head Unit rebuilds, collapsing
    the nested compound's title / xlab rows to 0 mm.
    """
    df = _df()
    p1 = ggplot(df) + geom_point(aes(x="mpg", y="disp")) + ggtitle("Plot 1")
    p2 = ggplot(df) + geom_boxplot(aes(x="gear", y="disp", group="gear")) + ggtitle("Plot 2")
    p3 = ggplot(df) + geom_point(aes(x="mpg", y="disp")) + ggtitle("Plot 3")
    pw = (p1 + p2) / p3 + plot_annotation(tag_levels="A")
    gt = patchworkGrob(pw)
    _assert_nested_row_has_height(gt, "patchwork-table", "title")
    _assert_nested_row_has_height(gt, "patchwork-table", "xlab-b")
    _assert_nested_row_has_height(gt, "patchwork-table", "tag")
