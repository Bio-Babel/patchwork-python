"""``wrap_table()`` — compose a ``great_tables.GT`` table into a patchwork.

R reference: ``patchwork::wrap_table`` + ``as_patch.gt_tbl`` +
``patchGrob.wrapped_table`` (R/wrap_table.R). The R API requires a
``gt_tbl``; we mirror that contract exactly with ``great_tables.GT``.
A pandas ``DataFrame`` is accepted as a one-liner sugar that
auto-promotes via ``GT(df)`` — same shape as R's
``gt::gt(as.data.frame(table))`` fallback.
"""

from __future__ import annotations

from typing import Any, Literal, Tuple, Union

import pandas as pd

from grid_py import Unit, Viewport, convert_height, convert_width, unit_c
from gtable_py import Gtable

from ._constants import PANEL_COL, PANEL_ROW
from ._gt_bridge import gt_as_gtable, is_great_tables_gt
from ._gtable_state import add_class
from ._patch import patch_grob
from ._utils import arg_match, is_abs_unit
from .wrap_elements import WrappedPatch, as_patch, wrap_elements

__all__ = ["WrappedTable", "wrap_table"]

PanelChoice = Literal["body", "full", "rows", "cols"]
SpaceChoice = Literal["free", "free_x", "free_y", "fixed"]


class WrappedTable(WrappedPatch):
    """A wrapped-table patch built from a ``great_tables.GT`` instance."""


def _coerce_to_gt(table: Any) -> Any:
    """Promote *table* to ``great_tables.GT`` mirroring R's fallback.

    R: ``if (!inherits(table, "gt_tbl")) table <- gt::gt(as.data.frame(table))``
    (R/wrap_table.R:64-69). Python accepts ``GT`` directly or any object
    coercible to ``pandas.DataFrame``.
    """
    if is_great_tables_gt(table):
        return table
    try:
        from great_tables import GT
    except ImportError as exc:
        raise ImportError(
            "wrap_table requires the great_tables package "
            "(``pip install great_tables``)."
        ) from exc
    if isinstance(table, pd.DataFrame):
        return GT(table)
    try:
        df = pd.DataFrame(table)
    except Exception as exc:
        raise TypeError(
            f"Unable to convert input table (type {type(table).__name__}) "
            "to great_tables.GT — supply a GT or DataFrame-like object."
        ) from exc
    return GT(df)


def _gt_n_row_headers(gt_obj: Any) -> int:
    """Number of stub columns (row-header columns) in a GT.

    R: ``n_row_headers <- (!all(is.na(table[["_stub_df"]]$row_id))) +
                          (!all(is.na(table[["_stub_df"]]$group_id)))``
    R/wrap_table.R:71-74.

    great_tables exposes the same information via
    ``Stub._get_stub_layout`` which returns a subset of
    ``{"group_label", "rowname"}``. ``len(stub_layout)`` is exactly the
    R count modulo the ``row_group_as_column`` option's de-duplication.
    """
    data = gt_obj._build_data(context="html")
    stub_layout = data._stub._get_stub_layout(
        has_summary_rows=False, options=data._options,
    )
    n = len(stub_layout)
    # R collapses the count to 1 when row_group_as_column is FALSE
    # (R/wrap_table.R:75-77).
    row_group_as_col = getattr(data._options, "row_group_as_column", None)
    if (n == 2 and row_group_as_col is not None and
            getattr(row_group_as_col, "value", row_group_as_col) is False):
        n = 1
    return n


def wrap_table(
    table: Any,
    panel: PanelChoice = "body",
    space: SpaceChoice = "free",
    ignore_tag: bool = False,
) -> WrappedTable:
    """Wrap a ``great_tables.GT`` (or DataFrame) into a patchwork-compliant patch.

    Parameters
    ----------
    table : great_tables.GT or pandas.DataFrame (or DataFrame-coercible)
        The table to embed. R's ``wrap_table`` accepts a ``gt_tbl``;
        the Python contract requires :class:`great_tables.GT` for
        feature parity (formatters, spanners, source notes, footnotes).
        A bare DataFrame is auto-promoted via ``GT(df)`` — the same
        sugar R's ``gt::gt(as.data.frame(table))`` provides.
    panel : {'body', 'full', 'rows', 'cols'}, default ``'body'``
        Which portion of the table aligns with the panel region.
    space : {'free', 'free_x', 'free_y', 'fixed'}, default ``'free'``
        Whether the table's fixed dimensions influence layout.
    ignore_tag : bool, default ``False``
        Skip auto-tagging for this patch.

    Returns
    -------
    WrappedTable

    Notes
    -----
    The full R panel-partition algorithm is ported in
    :func:`apply_wrapped_table_adjustment`; it relies on the
    ``table_body`` and ``table`` named regions emitted by
    :func:`patchwork._gt_bridge.gt_as_gtable`.
    """
    gt_obj = _coerce_to_gt(table)
    n_row_headers = _gt_n_row_headers(gt_obj)

    panel_value = arg_match(panel, ("body", "full", "rows", "cols"), arg="panel")
    space_value = arg_match(space, ("free", "free_x", "free_y", "fixed"), arg="space")

    wp = wrap_elements(full=gt_obj, ignore_tag=ignore_tag)
    settings = wp.get_attr("patch_settings", {"clip": "on", "ignore_tag": ignore_tag})
    settings["panel"] = panel_value
    settings["n_row_headers"] = n_row_headers
    settings["space"] = (
        space_value in ("free", "free_x"),
        space_value in ("free", "free_y"),
    )
    wp.set_attr("patch_settings", settings)

    wt = WrappedTable(plot=wp.plot, table=wp.table)
    wt._attrs = wp._attrs  # carry private attrs dict
    add_class(wt.table, "wrapped_table")
    return wt


# ---------------------------------------------------------------------------
# as_patch.GT — analog of R ``as_patch.gt_tbl``
# ---------------------------------------------------------------------------


def _register_gt_as_patch() -> None:
    """Install ``as_patch.GT`` so ``wrap_elements(full=gt)`` resolves."""
    try:
        from great_tables import GT
    except ImportError:
        return  # great_tables not available; wrap_table will error earlier.

    from grid_py import edit_grob, grob_height, grob_width

    @as_patch.register(GT)
    def _(x: GT, **kwargs: Any) -> Gtable:
        """Port of R ``as_patch.gt_tbl`` (R/wrap_table.R:147-160).

        Build the gtable, subset to just the ``table`` named region,
        then set a viewport anchored at the top-left so the table
        flows from there.
        """
        gtable = gt_as_gtable(x)
        # Find the "table" named region's bounds.
        names = list(gtable.layout["name"])
        try:
            idx = names.index("table")
        except ValueError:
            return gtable  # no table region — return as-is
        t = gtable.layout["t"][idx]
        l = gtable.layout["l"][idx]
        b = gtable.layout["b"][idx]
        r = gtable.layout["r"][idx]
        # gtable_py accepts 0-based list indices for slicing.
        sub = gtable[list(range(t - 1, b)), list(range(l - 1, r))]
        # R: viewport(x=0, y=1, width=grobWidth(grob), height=grobHeight(grob),
        #             default.units="npc", just=c(0,1))
        sub.vp = Viewport(
            x=Unit([0.0], ["npc"]),
            y=Unit([1.0], ["npc"]),
            width=grob_width(sub),
            height=grob_height(sub),
            just=[0, 1],
        )
        return sub


_register_gt_as_patch()


# ---------------------------------------------------------------------------
# Unit helpers — R/Python parity for ``gt$widths[i]`` / ``Reduce(`+`, u)``
# ---------------------------------------------------------------------------


def _set_unit_scalar(u: Unit, i: int, new: Unit) -> Unit:
    """R: ``u[i] <- new`` — 1-based scalar replacement preserving ``data``."""
    out = u.copy()
    out[i - 1] = new
    return out


def _unit_slice(u: Unit, start: int, end: int) -> Unit:
    """R: ``u[start:end]`` — 1-based inclusive slice, preserves ``data``."""
    return u[start - 1:end]


def _unit_drop_range(u: Unit, start: int, end: int) -> Unit:
    """R: ``u[-seq(start, end)]`` — drop a 1-based inclusive range."""
    prefix = u[:start - 1]
    suffix = u[end:]
    if len(prefix) == 0:
        return suffix
    if len(suffix) == 0:
        return prefix
    return unit_c(prefix, suffix)


def _unit_reduce_sum(u: Unit) -> Unit:
    """R: ``if (inherits(u, 'simpleUnit')) sum(u) else Reduce('+', u)``."""
    n = len(u)
    if n == 0:
        return Unit([0.0], ["mm"])
    if is_abs_unit(u) and len(set(u.units_list)) == 1:
        return Unit([float(sum(u.values))], [u.units_list[0]])
    acc = u[0:1]
    for i in range(1, n):
        acc = acc + u[i:i + 1]
    return acc


# ---------------------------------------------------------------------------
# Panel-partition algorithm (R: patchGrob.wrapped_table, R/wrap_table.R:89-140)
# ---------------------------------------------------------------------------


def apply_wrapped_table_adjustment(
    x: Gtable,
    panel: str,
    row_head: int,
    space: Tuple[bool, bool],
) -> Gtable:
    """Port of R's ``patchGrob.wrapped_table`` post-resolve adjustment.

    Mirrors ``R/wrap_table.R:89-140`` verbatim. *x* is the outer gtable
    produced by the inherited :class:`WrappedPatch` resolver; its
    ``panel`` cell must contain the inner table as a Gtable with a
    ``vp`` anchor and a ``table_body`` named region. Returns the
    mutated outer gtable.
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
        body_idx = [
            i for i, n in enumerate(inner.layout["name"]) if n == "table_body"
        ]
        if body_idx:
            bp = body_idx[0]
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

    Calls the inherited :class:`WrappedPatch` resolver to build the
    outer patchwork gtable, then applies the table-specific
    width/height adjustments from
    :func:`apply_wrapped_table_adjustment`.
    """
    from ._patch import patch_grob as _patch_grob

    base_result = _patch_grob.dispatch(WrappedPatch)(x, guides)

    settings = x.get_attr("patch_settings", {})
    panel = settings.get("panel", "body")
    row_head = int(settings.get("n_row_headers", 0))
    space = settings.get("space", (True, True))
    return apply_wrapped_table_adjustment(base_result, panel, row_head, space)
