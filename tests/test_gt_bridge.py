"""GT→Gtable bridge tests against R-generated gold-standard layouts.

The bridge ports R ``gt::as_gtable()`` faithfully (6 components:
caption / heading / columns / body / source_notes / footnotes plus
combine + finalize + grid_align). For every fixture we verify the
Python output matches the R-generated TSV byte-for-byte at the
``(t, l, b, r, name)`` layout level — same coordinates, same names,
same count.

R gold dumps live under ``validation/_fixtures/gt_gold/`` (generated
by ``validation/_gen_gold_gt_as_gtable.R`` under R env ggrepel-dev).
Skip the test if the gold file isn't present (allows the package to
work in installs that don't include the validation/ directory — gold
files are dev-only).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

GOLD_DIR = Path(__file__).resolve().parent.parent / "validation" / "_fixtures" / "gt_gold"

great_tables = pytest.importorskip("great_tables")
GT = great_tables.GT


@pytest.fixture(scope="module")
def df():
    return pd.DataFrame({
        "month": ["May", "June", "July", "August", "September"],
        "mean":  [60.5, 70.1, 75.3, 73.0, 67.0],
        "max":   [80, 90, 95, 93, 87],
    })


def _read_gold(tag: str):
    """Return the R-derived gold layout DataFrame, or skip if missing."""
    p = GOLD_DIR / f"{tag}_layout.tsv"
    if not p.exists():
        pytest.skip(f"gold file missing: {p} (run validation/_gen_gold_gt_as_gtable.R)")
    return pd.read_csv(p, sep="\t")


def _bridge_layout(gt_obj):
    """Return the Python bridge's layout as a normalized DataFrame."""
    from patchwork._gt_bridge import gt_as_gtable
    g = gt_as_gtable(gt_obj)
    return pd.DataFrame({
        "t": g.layout["t"],
        "l": g.layout["l"],
        "b": g.layout["b"],
        "r": g.layout["r"],
        "name": g.layout["name"],
    })


def _assert_layouts_equal(py_df, r_df, tag):
    """Compare R vs Python layouts, ignoring row order."""
    # Sort both by (t, l, b, r, name) so the comparison is order-invariant.
    sort_cols = ["t", "l", "b", "r", "name"]
    py_sorted = py_df.sort_values(sort_cols).reset_index(drop=True)
    r_sorted = r_df.sort_values(sort_cols).reset_index(drop=True)
    pd.testing.assert_frame_equal(
        py_sorted, r_sorted,
        check_dtype=False,
        obj=f"{tag} layout (Python vs R)",
    )


class TestGtBridgeRParity:
    """Each test mirrors one case in validation/_gen_gold_gt_as_gtable.R."""

    def test_stub_only(self, df):
        gt_obj = GT(df, rowname_col="month")
        py_df = _bridge_layout(gt_obj)
        r_df = _read_gold("stub_only")
        _assert_layouts_equal(py_df, r_df, "stub_only")

    def test_no_stub(self, df):
        gt_obj = GT(df)
        py_df = _bridge_layout(gt_obj)
        r_df = _read_gold("no_stub")
        _assert_layouts_equal(py_df, r_df, "no_stub")

    def test_with_heading(self, df):
        gt_obj = GT(df, rowname_col="month").tab_header(
            title="Title", subtitle="Sub",
        )
        py_df = _bridge_layout(gt_obj)
        r_df = _read_gold("with_heading")
        _assert_layouts_equal(py_df, r_df, "with_heading")

    def test_with_source(self, df):
        gt_obj = GT(df, rowname_col="month").tab_source_note("Source note")
        py_df = _bridge_layout(gt_obj)
        r_df = _read_gold("with_source")
        _assert_layouts_equal(py_df, r_df, "with_source")

    def test_with_spanner(self, df):
        gt_obj = GT(df, rowname_col="month").tab_spanner(
            label="Stats", columns=["mean", "max"],
        )
        py_df = _bridge_layout(gt_obj)
        r_df = _read_gold("with_spanner")
        _assert_layouts_equal(py_df, r_df, "with_spanner")

    def test_everything(self, df):
        gt_obj = (GT(df, rowname_col="month")
                  .tab_header(title="Title", subtitle="Sub")
                  .tab_spanner(label="Stats", columns=["mean", "max"])
                  .tab_source_note("S1")
                  .tab_source_note("S2"))
        py_df = _bridge_layout(gt_obj)
        r_df = _read_gold("everything")
        _assert_layouts_equal(py_df, r_df, "everything")
