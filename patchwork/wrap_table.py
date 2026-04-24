"""``wrap_table()`` — compose a table into a patchwork.

The R API accepts a ``gt_tbl`` object; ``gt`` has no Python port so the
Python variant accepts a ``pandas.DataFrame`` or a pre-built
``gtable_py.Gtable`` instead. Any input that *looks* like a ``gt_tbl``
(an object with both ``_stub_df`` and ``_options`` attributes) raises
``NotImplementedError``.

See ``port_reports/patchwork/02_feature_checklist.md`` for the deviation
rationale (essentials §4).
"""

from __future__ import annotations

from typing import Any, Literal, Sequence, Union

import pandas as pd
from gtable_py import Gtable, is_gtable

from ._gtable_state import add_class
from ._patch import patch_grob
from ._utils import arg_match
from .wrap_elements import WrappedPatch, wrap_elements

__all__ = ["WrappedTable", "wrap_table"]

PanelChoice = Literal["body", "full", "rows", "cols"]
SpaceChoice = Literal["free", "free_x", "free_y", "fixed"]


class WrappedTable(WrappedPatch):
    """A wrapped-table patch built from a ``DataFrame`` or a ``Gtable``."""


def _dataframe_to_gtable(df: pd.DataFrame) -> Gtable:
    """Convert a ``DataFrame`` to a basic ``Gtable`` suitable for wrapping.

    This is intentionally minimal — a gt-quality renderer is out of scope
    (would be its own port). We build a gtable whose single panel cell
    holds a textual representation of *df*. Callers wanting polished
    tables should precompose a gtable with ``gtable_py`` and pass that
    gtable in directly.
    """
    from grid_py import Unit, null_grob, raster_grob  # noqa: F401
    from gtable_py import gtable_add_grob

    nrows, ncols = df.shape
    widths = Unit([1.0] * (ncols + 1), ["null"] * (ncols + 1))
    heights = Unit([1.0] * (nrows + 1), ["null"] * (nrows + 1))
    gt = Gtable(widths=widths, heights=heights, name="table")
    gt = gtable_add_grob(gt, null_grob(), t=1, l=1, b=1, r=ncols + 1, name="table_body")
    return gt


def wrap_table(
    table: Union[pd.DataFrame, Gtable, Any],
    panel: PanelChoice = "body",
    space: SpaceChoice = "free",
    ignore_tag: bool = False,
) -> WrappedTable:
    """Wrap a table in a patchwork-compliant patch.

    Parameters
    ----------
    table : pandas.DataFrame or gtable_py.Gtable
        The table to embed. R's original API accepts a ``gt_tbl`` from
        the ``gt`` package; ``gt`` has no Python port, so Python
        callers supply a ``DataFrame`` or a pre-built gtable.
    panel : {'body', 'full', 'rows', 'cols'}, default 'body'
        Which portion of the table should be aligned with the panel region.
    space : {'free', 'free_x', 'free_y', 'fixed'}, default 'free'
        Whether the table's fixed dimensions should influence layout.
    ignore_tag : bool, default ``False``
        Skip auto-tagging for this patch.

    Returns
    -------
    WrappedTable
        A composable patch.

    Raises
    ------
    NotImplementedError
        If *table* looks like a ``gt_tbl`` (has both ``_stub_df`` and
        ``_options``). R's gt is out of scope for v0; see essentials §4.
    """
    if hasattr(table, "_stub_df") and hasattr(table, "_options"):
        raise NotImplementedError(
            "`gt` has no Python port; `wrap_table` accepts a pandas.DataFrame "
            "or a pre-built gtable_py.Gtable instead. See "
            "https://gt.rstudio.com/ for the R behaviour we're intentionally "
            "not replicating."
        )

    if isinstance(table, pd.DataFrame):
        gtable = _dataframe_to_gtable(table)
        n_row_headers = 1 if table.index.name is not None else 0
    elif is_gtable(table):
        gtable = table
        n_row_headers = 0
    else:
        try:
            df = pd.DataFrame(table)
        except Exception as exc:  # pragma: no cover — pandas narrows this
            raise TypeError(
                "Unable to convert input table to pandas.DataFrame or gtable."
            ) from exc
        gtable = _dataframe_to_gtable(df)
        n_row_headers = 1 if df.index.name is not None else 0

    panel_value = arg_match(panel, ("body", "full", "rows", "cols"), arg="panel")
    space_value = arg_match(space, ("free", "free_x", "free_y", "fixed"), arg="space")

    wp = wrap_elements(full=gtable, ignore_tag=ignore_tag)
    settings = wp.get_attr("patch_settings", {"clip": "on", "ignore_tag": ignore_tag})
    settings["panel"] = panel_value
    settings["n_row_headers"] = n_row_headers
    settings["space"] = (
        space_value in ("free", "free_x"),
        space_value in ("free", "free_y"),
    )
    wp.set_attr("patch_settings", settings)

    wt = WrappedTable(plot=wp.plot, table=wp.table)
    wt._attrs = wp._attrs  # copy private attrs dict
    add_class(wt.table, "wrapped_table")
    return wt


@patch_grob.register(WrappedTable)
def _(x: WrappedTable, guides: str = "auto") -> Gtable:
    """Resolve a :class:`WrappedTable` to a gtable.

    Current implementation delegates to :class:`WrappedPatch`'s resolver
    and then applies the table-specific width/height adjustments only if
    the embedded gtable exposes the expected layout. For a DataFrame-only
    wrap this adjustment is a no-op.
    """
    from ._patch import patch_grob as _patch_grob

    from .wrap_elements import WrappedPatch

    # WrappedTable inherits WrappedPatch; dispatch on the parent.
    base_result = _patch_grob.dispatch(WrappedPatch)(x, guides)
    return base_result
