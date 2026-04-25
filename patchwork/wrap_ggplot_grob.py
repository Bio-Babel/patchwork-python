"""``wrap_ggplot_grob()`` — wrap an existing ``ggplot``-built gtable.

Ports ``R/wrap_ggplot_grob.R``.
"""

from __future__ import annotations

from typing import Any

from ggplot2_py import ggplotGrob
from gtable_py import Gtable, gtable_add_grob, is_gtable

from ._constants import TABLE_COLS, TABLE_ROWS
from ._gtable_state import add_class
from ._patch import Patch, make_patch, patch_grob

__all__ = ["TablePatch", "wrap_ggplot_grob"]


class TablePatch(Patch):
    """A patch whose rendered form is a pre-built gtable."""


def wrap_ggplot_grob(x: Gtable) -> TablePatch:
    """Make a gtable (produced by ``ggplotGrob``) patchwork-compliant.

    Parameters
    ----------
    x : gtable_py.Gtable
        A gtable, typically the output of ``ggplotGrob``.

    Returns
    -------
    TablePatch
        A composable patch that participates in patchwork alignment.

    Raises
    ------
    TypeError
        If *x* is not a :class:`Gtable`.
    ValueError
        If *x* has more rows/columns than the canonical 18×15 ggplot gtable.
    """
    if not is_gtable(x):
        raise TypeError(f"`x` must be a <gtable>, got {type(x).__name__}")
    if len(x.widths.values) > TABLE_COLS or len(x.heights.values) > TABLE_ROWS:
        raise ValueError("`x` does not appear to be a gtable created from a <ggplot> object")
    base = make_patch()
    patch = TablePatch(plot=base.plot, table=base.table)
    patch.set_attr("table", x)
    add_class(patch.table, "table_patch")
    return patch


@patch_grob.register(TablePatch)
def _(x: TablePatch, guides: str = "auto") -> Gtable:
    """Resolve a :class:`TablePatch` to a gtable with patchwork-friendly extras."""
    # Lazy import to avoid cycles
    from .core import add_guides, add_strips

    gt = x.get_attr("table")
    gt = add_strips(gt)
    gt = add_guides(gt, collect=(guides == "collect"))

    labels = getattr(x.plot, "labels", {}) or {}
    if "tag" in labels:
        # Build a fresh ggplot grob so we know where the tag lives.
        built = add_guides(add_strips(ggplotGrob(x.plot)))
        names = built.layout["name"]
        if "tag" in names:
            tag_idx = names.index("tag")
            gt = gtable_add_grob(
                gt,
                built.grobs[tag_idx],
                t=built.layout["t"][tag_idx],
                l=built.layout["l"][tag_idx],
                b=built.layout["b"][tag_idx],
                r=built.layout["r"][tag_idx],
                z=max(gt.layout["z"]) + 1,
                clip=built.layout["clip"][tag_idx],
                name="tag",
            )
    return gt
