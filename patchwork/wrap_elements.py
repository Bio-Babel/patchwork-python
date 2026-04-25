"""``wrap_elements()`` and the ``as_patch`` singledispatch registry.

Ports ``R/wrap_elements.R``. The R source uses S3 dispatch on many input
types; here we use ``functools.singledispatch`` keyed on Python type.

Scope deviations from R — the following R S3 methods have no Python
counterpart because the underlying types do not exist in Python:

- ``as_patch.formula`` (R: ``gridGraphics::echoGrob`` of a base-R plot
  expression). Calling :func:`as_patch_formula` raises
  ``NotImplementedError``.
- ``as_patch.gt_tbl`` (R: ``gt::as_gtable`` of a ``gt`` table). Use
  :func:`~patchwork.wrap_table.wrap_table` with a ``pandas.DataFrame``
  or ``gtable_py.Gtable``. Calling :func:`as_patch_gt_tbl` raises
  ``NotImplementedError``.

Unknown types dispatched through :func:`as_patch` fall through to the
default, which raises ``TypeError``.
"""

from __future__ import annotations

from functools import singledispatch
from typing import Any, Optional

import numpy as np
from ggplot2_py import (
    GGPlot,
    calc_element,
    ggplotGrob,
    is_ggplot,
    theme_get,
)
from grid_py import GList, GTree, Grob, convert_height, grob_height, is_grob, raster_grob
from gtable_py import Gtable, gtable_add_grob

from ._constants import (
    CAPTION_ROW,
    PANEL_COL,
    PANEL_ROW,
    PLOT_BOTTOM,
    PLOT_LEFT,
    PLOT_RIGHT,
    PLOT_TOP,
    SUBTITLE_ROW,
    TITLE_ROW,
)
from ._gtable_state import add_class, copy_state
from ._patch import Patch, make_patch, patch_grob, patch_table
from ._utils import get_grob, zero_grob

__all__ = [
    "WrappedPatch",
    "wrap_elements",
    "as_patch",
    "as_patch_formula",
    "as_patch_gt_tbl",
    "is_wrapped_patch",
]


class WrappedPatch(Patch):
    """A :class:`Patch` wrapping arbitrary graphics in patchwork-compliant form."""


def wrap_elements(
    panel: Any = None,
    plot: Any = None,
    full: Any = None,
    clip: bool = True,
    ignore_tag: bool = False,
) -> WrappedPatch:
    """Wrap graphics so they can be added to a patchwork.

    Parameters
    ----------
    panel, plot, full : object, optional
        A grob, ggplot, patchwork, raster, or ``numpy`` native-raster to
        place in the corresponding area.
    clip : bool, default ``True``
        Whether to clip grobs that expand beyond their area.
    ignore_tag : bool, default ``False``
        If ``True``, automatic tagging skips this patch.

    Returns
    -------
    WrappedPatch
        A composable patch.
    """
    clip_str = "on" if clip else "off"
    base = make_patch()
    wp = WrappedPatch(plot=base.plot, table=base.table)
    wp.set_attr("grobs", {"panel": panel, "plot": plot, "full": full})
    wp.set_attr("patch_settings", {"clip": clip_str, "ignore_tag": ignore_tag})
    add_class(wp.table, "wrapped_patch")
    return wp


def is_wrapped_patch(x: Any) -> bool:
    """Return ``True`` if *x* is a :class:`WrappedPatch`."""
    return isinstance(x, WrappedPatch)


@singledispatch
def as_patch(x: Any, **kwargs: Any) -> Grob:
    """Convert *x* to a grob suitable for placement inside a patch slot.

    This is a :func:`functools.singledispatch` generic — register new
    handlers with ``as_patch.register(SomeType)``.

    Parameters
    ----------
    x : object
        Input to convert. Registered types: ``grid_py.Grob``, ``grid_py.GTree``,
        ``grid_py.GList``, ``ggplot2_py.GGPlot``, ``numpy.ndarray``
        (raster/nativeRaster), and :class:`patchwork.Patchwork`. Unsupported
        types raise ``TypeError``.
    **kwargs
        Forwarded to the concrete handler (unused by the default).

    Returns
    -------
    grid_py.Grob
        A grob ready to be placed into a gtable cell.

    Raises
    ------
    TypeError
        If *x* has no registered handler.
    """
    raise TypeError(
        f"Don't know how to convert an object of type {type(x).__name__} to a patch"
    )


@as_patch.register(Grob)
def _(x: Grob, **kwargs: Any) -> Grob:
    return x


@as_patch.register(GTree)
def _(x: GTree, **kwargs: Any) -> Grob:
    return x


@as_patch.register(GList)
def _(x: GList, **kwargs: Any) -> Grob:
    """R ``as_patch.gList(x)`` → ``gTree(children = x)`` — wrap the list in a GTree."""
    return GTree(children=x)


@as_patch.register(GGPlot)
def _(x: GGPlot, **kwargs: Any) -> Grob:
    return ggplotGrob(x)


@as_patch.register(np.ndarray)
def _(x: np.ndarray, **kwargs: Any) -> Grob:
    """Raster / nativeRaster path: 2-D or 3-D ndarray → ``raster_grob``."""
    return raster_grob(x)


# R's ``as_patch.formula`` and ``as_patch.gt_tbl`` have no Python
# dispatch target — neither type exists. Expose them as explicit helpers
# so users hit a clear NotImplementedError rather than a confusing
# TypeError from singledispatch.


def as_patch_formula(x: Any, **kwargs: Any) -> Grob:
    """R ``as_patch.formula`` has no Python equivalent.

    In R the formula form wraps a base-R plotting expression via
    ``gridGraphics::echoGrob``. Python has no formula-typed plotting
    expression, so this is intentionally unimplemented.
    """
    raise NotImplementedError(
        "as_patch.formula has no Python counterpart: base-R graphics "
        "expressions (e.g. ~plot(x, y)) are not representable in Python. "
        "Wrap an equivalent grob directly via wrap_elements(full=<grob>)."
    )


def as_patch_gt_tbl(x: Any, **kwargs: Any) -> Grob:
    """R ``as_patch.gt_tbl`` has no Python equivalent.

    The ``gt`` R package has no Python port; patchwork-python routes
    tabular content through :func:`~patchwork.wrap_table.wrap_table`
    with a ``pandas.DataFrame`` or ``gtable_py.Gtable`` instead.
    """
    raise NotImplementedError(
        "as_patch.gt_tbl has no Python counterpart: the R 'gt' package "
        "has no Python port. Use wrap_table(<pandas.DataFrame>) or pass "
        "a gtable_py.Gtable to wrap_elements(full=...) instead."
    )


@patch_grob.register(WrappedPatch)
def _(x: WrappedPatch, guides: str = "auto") -> Gtable:
    """Bring wrapped grobs onto a patch table, mirroring R's logic."""
    gt = ggplotGrob(x.plot)
    table = patch_table(x, gt)
    settings = x.get_attr("patch_settings", {"clip": "on", "ignore_tag": False})
    grobs = x.get_attr("grobs", {"panel": None, "plot": None, "full": None})

    if grobs.get("full") is not None:
        grob_full = _resolve(grobs["full"])
        table = gtable_add_grob(
            table,
            grob_full,
            t=1,
            l=1,
            b=len(table.heights.values),
            r=len(table.widths.values),
            clip=settings["clip"],
            name="full",
        )
    if grobs.get("plot") is not None:
        grob_plot = _resolve(grobs["plot"])
        table = gtable_add_grob(
            table,
            grob_plot,
            t=PLOT_TOP,
            l=PLOT_LEFT,
            b=PLOT_BOTTOM,
            r=PLOT_RIGHT,
            clip=settings["clip"],
            name="plot",
        )
    if grobs.get("panel") is not None:
        grob_panel = _resolve(grobs["panel"])
        table = gtable_add_grob(
            table,
            grob_panel,
            t=PANEL_ROW,
            l=PANEL_COL,
            clip=settings["clip"],
            name="panel",
        )

    # Titles from the underlying ggplot
    title = get_grob(gt, "title")
    table = gtable_add_grob(
        table,
        title,
        t=TITLE_ROW,
        l=PANEL_COL,
        clip=settings["clip"],
        name="title",
    )
    _set_height(table, TITLE_ROW, convert_height(grob_height(title), "mm"))

    subtitle = get_grob(gt, "subtitle")
    table = gtable_add_grob(
        table,
        subtitle,
        t=SUBTITLE_ROW,
        l=PANEL_COL,
        clip=settings["clip"],
        name="subtitle",
    )
    _set_height(table, SUBTITLE_ROW, convert_height(grob_height(subtitle), "mm"))

    caption = get_grob(gt, "caption")
    table = gtable_add_grob(
        table,
        caption,
        t=CAPTION_ROW,
        l=PANEL_COL,
        clip=settings["clip"],
        name="caption",
    )
    _set_height(table, CAPTION_ROW, convert_height(grob_height(caption), "mm"))

    if not settings.get("ignore_tag", False):
        _copy_col_width(table, gt, dst_col=2, src_col=2)
        _copy_col_width(
            table,
            gt,
            dst_col=len(table.widths.values) - 1,
            src_col=len(gt.widths.values) - 1,
        )
        _copy_row_height(table, gt, dst_row=2, src_row=2)
        _copy_row_height(
            table,
            gt,
            dst_row=len(table.heights.values) - 1,
            src_row=len(gt.heights.values) - 1,
        )
        tag = get_grob(gt, "tag")
        tag_pos = calc_element("plot.tag.position", x.theme or theme_get())
        if tag_pos is None:
            tag_pos = theme_get().plot.get("tag.position")
        if not isinstance(tag_pos, str):
            tag_pos = "manual"
        table = _place_tag(table, tag, tag_pos)

    copy_state(x.table, table)
    return table


def _resolve(x: Any) -> Grob:
    """Convert an input into a grob via :func:`as_patch`."""
    return as_patch(x)


def _set_height(table: Gtable, row: int, value) -> None:
    """R: ``table$heights[row] <- value`` — single-entry replacement.

    Use :py:meth:`grid_py.Unit.__setitem__` so neighbouring entries keep
    their ``data`` (lazy grobwidth/grobheight grob refs); rebuilding the
    Unit from raw values would silently drop them.
    """
    from grid_py import Unit

    if hasattr(value, "values") and hasattr(value, "units_list"):
        rhs = value[0:1] if len(value) > 0 else value
    else:
        rhs = Unit([float(value)], ["mm"])
    heights = table.heights.copy()
    heights[row - 1] = rhs
    table.heights = heights


def _copy_row_height(dst: Gtable, src: Gtable, dst_row: int, src_row: int) -> None:
    if src_row < 1 or src_row > len(src.heights.values):
        return
    heights = dst.heights.copy()
    heights[dst_row - 1] = src.heights[src_row - 1:src_row]
    dst.heights = heights


def _copy_col_width(dst: Gtable, src: Gtable, dst_col: int, src_col: int) -> None:
    if src_col < 1 or src_col > len(src.widths.values):
        return
    widths = dst.widths.copy()
    widths[dst_col - 1] = src.widths[src_col - 1:src_col]
    dst.widths = widths


def _place_tag(table: Gtable, tag: Grob, tag_pos: str) -> Gtable:
    """Place a tag grob into the gtable according to *tag_pos*."""
    n_rows = len(table.heights.values)
    n_cols = len(table.widths.values)
    placements = {
        "topleft":     dict(t=2, l=2),
        "top":         dict(t=2, l=2, r=n_cols - 1),
        "topright":    dict(t=2, l=n_cols - 1),
        "left":        dict(t=2, b=n_rows - 1, l=2),
        "right":       dict(t=2, b=n_rows - 1, l=n_cols - 1),
        "bottomleft":  dict(t=n_rows - 1, l=2),
        "bottom":      dict(t=n_rows - 1, l=2, r=n_cols - 1),
        "bottomright": dict(t=n_rows - 1, l=n_cols - 1),
        "manual":      dict(t=2, l=2, b=n_rows - 1, r=n_cols - 1),
    }
    spec = placements.get(tag_pos, placements["manual"])
    return gtable_add_grob(table, tag, name="tag", clip="off", **spec)
