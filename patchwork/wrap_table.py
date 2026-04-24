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

from typing import Any, Literal, Sequence, Tuple, Union

import pandas as pd
from grid_py import Unit, Viewport, convert_height, convert_width, unit_c
from gtable_py import Gtable, is_gtable

from ._constants import PANEL_COL, PANEL_ROW
from ._gtable_state import add_class
from ._patch import patch_grob
from ._utils import arg_match, is_abs_unit
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
    from grid_py import Unit, grob_height, grob_width, null_grob
    from gtable_py import gtable_add_grob

    nrows, ncols = df.shape
    widths = Unit([1.0] * (ncols + 1), ["null"] * (ncols + 1))
    heights = Unit([1.0] * (nrows + 1), ["null"] * (nrows + 1))
    gt = Gtable(widths=widths, heights=heights, name="table")
    gt = gtable_add_grob(gt, null_grob(), t=1, l=1, b=1, r=ncols + 1, name="table_body")
    # Mirror R's ``as_patch.gt_tbl`` (wrap_table.R:149-156):
    #   grob$vp <- viewport(x = 0, y = 1,
    #                       width  = grobWidth(grob),
    #                       height = grobHeight(grob),
    #                       default.units = "npc", just = c(0, 1))
    # Width / height come from the actual grob dimensions, not a 1-npc
    # fallback.
    gt.vp = Viewport(
        x=Unit([0.0], ["npc"]),
        y=Unit([1.0], ["npc"]),
        width=grob_width(gt),
        height=grob_height(gt),
        just=[0, 1],
    )
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


def _set_unit_scalar(u: Unit, i: int, new: Unit) -> Unit:
    """R: ``u[i] <- new`` — 1-based scalar replacement.

    Delegates to :py:meth:`grid_py.Unit.__setitem__` on a copy so
    callers get a fresh Unit (the idiom here always immediately
    reassigns to ``gt.widths`` / ``gt.heights``, so we don't mutate
    the caller's original object). ``Unit.__setitem__`` correctly
    preserves ``data`` for every position it isn't overwriting.
    """
    out = u.copy()
    out[i - 1] = new
    return out


def _unit_slice(u: Unit, start: int, end: int) -> Unit:
    """R: ``u[start:end]`` — 1-based inclusive slice; preserves ``data``."""
    return u[start - 1:end]


def _unit_drop_range(u: Unit, start: int, end: int) -> Unit:
    """R: ``u[-seq(start, end)]`` — drop 1-based inclusive range.

    Concatenates the prefix and suffix via :func:`grid_py.unit_c`;
    both sides preserve ``data`` through native subscript.
    """
    prefix = u[:start - 1]
    suffix = u[end:]
    if len(prefix) == 0:
        return suffix
    if len(suffix) == 0:
        return prefix
    return unit_c(prefix, suffix)


def _unit_reduce_sum(u: Unit) -> Unit:
    """Sum a ``Unit`` into a scalar Unit.

    Mirrors R's ``if (inherits(u, 'simpleUnit')) sum(u) else Reduce('+', u)``:
    when every component shares a single unit-type we can add
    numerically; otherwise we fall back to the grid ``+`` operator,
    which yields a compound ``'sum'`` unit.

    Both branches now build intermediate Units via native
    :py:meth:`grid_py.Unit.__getitem__` (``u[i:i+1]``) so per-entry
    ``data`` (grob refs for lazy ``grobheight``/``grobwidth``) stays
    attached across the reduction.
    """
    n = len(u)
    if n == 0:
        return Unit([0.0], ["mm"])
    # Fast path only when every entry is an absolute unit (no lazy
    # grobheight/grobwidth — summing raw values would throw away the
    # ``data`` grob reference). Otherwise fall through to pairwise +,
    # which grid_py resolves correctly against the entries' data.
    if is_abs_unit(u) and len(set(u.units_list)) == 1:
        return Unit([float(sum(u.values))], [u.units_list[0]])
    acc = u[0:1]
    for i in range(1, n):
        acc = acc + u[i:i + 1]
    return acc


def apply_wrapped_table_adjustment(
    x: Gtable,
    panel: str,
    row_head: int,
    space: Tuple[bool, bool],
) -> Gtable:
    """Port of R's ``patchGrob.wrapped_table`` adjustment block.

    Mirrors ``R/wrap_table.R:89-140`` verbatim. *x* is the outer gtable
    produced by the inherited ``WrappedPatch`` resolver; its ``panel``
    cell must already contain the inner table as a ``Gtable`` with a
    ``vp`` anchor. Returns the mutated outer gtable.
    """
    names = list(x.layout["name"])
    try:
        table_loc = names.index("panel")
    except ValueError:
        return x
    inner = x.grobs[table_loc]

    table_width = inner.widths
    if is_abs_unit(table_width):
        table_width = convert_width(table_width, "mm")
    table_height = inner.heights
    if is_abs_unit(table_height):
        table_height = convert_height(table_height, "mm")

    if panel in ("body", "cols"):
        table_body_idx = [
            i for i, n in enumerate(inner.layout["name"]) if n == "table_body"
        ]
        if table_body_idx:
            bp = table_body_idx[0]
            col_head = inner.layout["t"][bp] - 1
            col_tail = inner.layout["b"][bp] + 1
            n_inner_rows = len(inner.heights.values)
            if not space[1] and col_tail <= n_inner_rows:
                height = _unit_reduce_sum(
                    _unit_slice(inner.heights, col_tail, n_inner_rows)
                )
                x.heights = _set_unit_scalar(x.heights, PANEL_ROW + 2, height)
                table_height = _unit_drop_range(table_height, col_tail, n_inner_rows)
            if col_head > 0:
                height = _unit_reduce_sum(_unit_slice(inner.heights, 1, col_head))
                inner.vp = Viewport(
                    x=inner.vp.x,
                    y=inner.vp.y + height,
                    width=inner.vp.width,
                    height=inner.vp.height,
                    just=inner.vp.just,
                )
                x.heights = _set_unit_scalar(x.heights, PANEL_ROW - 2, height)
                table_height = _unit_drop_range(table_height, 1, col_head)

    if panel in ("body", "rows") and row_head > 0:
        width = _unit_reduce_sum(_unit_slice(inner.widths, 1, row_head))
        inner.vp = Viewport(
            x=inner.vp.x - width,
            y=inner.vp.y,
            width=inner.vp.width,
            height=inner.vp.height,
            just=inner.vp.just,
        )
        x.widths = _set_unit_scalar(x.widths, PANEL_COL - 2, width)
        table_width = _unit_drop_range(table_width, 1, row_head)

    if not space[0]:
        w = _unit_reduce_sum(table_width)
        x.widths = _set_unit_scalar(x.widths, PANEL_COL, w)
    if not space[1]:
        h = _unit_reduce_sum(table_height)
        x.heights = _set_unit_scalar(x.heights, PANEL_ROW, h)

    return x


@patch_grob.register(WrappedTable)
def _(x: WrappedTable, guides: str = "auto") -> Gtable:
    """Resolve a :class:`WrappedTable` to a gtable.

    Calls the inherited :class:`WrappedPatch` resolver to build the outer
    patchwork-compliant gtable, then applies the table-specific
    width/height adjustments from :func:`apply_wrapped_table_adjustment`
    (port of ``R/wrap_table.R:89-140``).
    """
    from ._patch import patch_grob as _patch_grob

    base_result = _patch_grob.dispatch(WrappedPatch)(x, guides)

    settings = x.get_attr("patch_settings", {})
    panel = settings.get("panel", "body")
    row_head = int(settings.get("n_row_headers", 0))
    space = settings.get("space", (True, True))
    return apply_wrapped_table_adjustment(base_result, panel, row_head, space)
