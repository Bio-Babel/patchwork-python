"""Low-level patch primitives used across the rendering pipeline.

Ports ``R/patch.R``. The R source uses S3 class tags (``patch``, ``patchgrob``)
that layer onto a ggplot object and a gtable. Here we introduce small Python
classes ``Patch`` and ``Patchgrob`` and keep the patchwork-specific state on
them as regular attributes — no inheritance from ``GGPlot`` is necessary
because patch objects never flow back to a plain ggplot user path.
"""

from __future__ import annotations

from functools import singledispatch
from typing import Any, Optional

from ggplot2_py import ggplot, ggplotGrob
from grid_py import Unit
from gtable_py import Gtable, gtable_add_grob

from ._constants import PANEL_COL, PANEL_ROW, TABLE_COLS, TABLE_ROWS
from ._gtable_state import add_class, copy_state, set_attr
from ._utils import zero_grob

__all__ = [
    "Patch",
    "Patchgrob",
    "make_patch",
    "patch_table",
    "is_patch",
    "patch_grob",
    "patchGrob",
    "print_patch",
]


class Patch:
    """A resolvable patchwork fragment holding a ggplot-shaped placeholder and a gtable.

    Ports R's ``class(x) <- c("patch", "gg", ...)`` plus the ``attr(x, "table")``
    pattern. ``Patch`` stores the underlying bare ggplot (used only for label
    harvesting — titles, tags, captions) and the backing gtable.
    """

    __slots__ = ("plot", "table", "theme", "labels", "_attrs")

    def __init__(self, plot=None, table: Optional[Gtable] = None) -> None:
        self.plot = plot if plot is not None else ggplot()
        self.table = table
        self.theme = getattr(self.plot, "theme", None)
        self.labels = getattr(self.plot, "labels", {})
        self._attrs: dict[str, Any] = {}

    def set_attr(self, key: str, value: Any) -> "Patch":
        """Attach patchwork-side metadata (e.g. ``free_settings``)."""
        self._attrs[key] = value
        return self

    def get_attr(self, key: str, default: Any = None) -> Any:
        """Read patchwork-side metadata."""
        return self._attrs.get(key, default)

    def __repr__(self) -> str:  # pragma: no cover — cosmetic
        return f"<patchwork.Patch {id(self):x}>"

    def __add__(self, other):
        """Place *self* first, then *other*.

        R's ``plot_spacer() + x`` dispatches through ``+.gg`` →
        ``ggplot_add.ggplot`` → ``add_patches``, which results in
        ``plot_spacer`` ending up in ``patches$plots`` (first) and *other*
        becoming the active plot. Python needs an explicit ``__add__`` on
        :class:`Patch` to preserve that ordering — relying on the RHS's
        ``__radd__`` would lose the "LHS is first" information.
        """
        if other is None:
            return self
        from .add_plot import (
            Patches,
            Patchwork,
            add_patches,
            as_patchwork,
            new_patchwork,
            plot_filler,
        )
        from ggplot2_py import GGPlot, is_ggplot

        if isinstance(other, Patchwork):
            patches = new_patchwork()
            patches.plots = [self]
            return add_patches(other, patches)
        if is_ggplot(other) or isinstance(other, GGPlot):
            patches = new_patchwork()
            patches.plots = [self]
            return add_patches(other, patches)
        if isinstance(other, Patch):
            patches = new_patchwork()
            patches.plots = [self, other]
            return add_patches(plot_filler(), patches)
        return NotImplemented


def make_patch() -> Patch:
    """Build the base ``Patch``: an 18×15 gtable with a panel placeholder.

    R reference: ``R/patch.R::make_patch``. The grid is sized so that the
    only "live" cell is the panel slot. All other cells are 0-mm so they
    collapse when rendered unless we later add content.
    """
    widths_values = [0.0] * TABLE_COLS
    widths_units = ["mm"] * TABLE_COLS
    widths_values[PANEL_COL - 1] = 1.0
    widths_units[PANEL_COL - 1] = "null"

    heights_values = [0.0] * TABLE_ROWS
    heights_units = ["mm"] * TABLE_ROWS
    heights_values[PANEL_ROW - 1] = 1.0
    heights_units[PANEL_ROW - 1] = "null"

    widths = Unit(widths_values, widths_units)
    heights = Unit(heights_values, heights_units)

    table = Gtable(widths=widths, heights=heights)
    table = gtable_add_grob(
        table,
        zero_grob(),
        t=PANEL_ROW,
        l=PANEL_COL,
        z=float("-inf"),
        name="panel_patch",
    )
    add_class(table, "patchgrob")

    return Patch(plot=ggplot(), table=table)


def patch_table(x: Patch, grob: Optional[Gtable] = None) -> Gtable:
    """Produce a gtable copy of ``x.table`` with the outer frame from *grob*.

    Mirrors R's ``patch_table``. If *grob* is ``None`` the function builds
    one via ``ggplotGrob(x.plot)`` so that outer margins, background and
    width/height for the outer cells match what a bare ggplot would produce.
    """
    table = x.table
    if grob is None:
        grob = ggplotGrob(x.plot)

    widths_list = list(table.widths.values)
    widths_units = list(table.widths.units_list)
    widths_list[0] = grob.widths.values[0]
    widths_units[0] = grob.widths.units_list[0]
    widths_list[-1] = grob.widths.values[-1]
    widths_units[-1] = grob.widths.units_list[-1]
    new_widths = Unit(widths_list, widths_units)

    heights_list = list(table.heights.values)
    heights_units = list(table.heights.units_list)
    heights_list[0] = grob.heights.values[0]
    heights_units[0] = grob.heights.units_list[0]
    heights_list[-1] = grob.heights.values[-1]
    heights_units[-1] = grob.heights.units_list[-1]
    new_heights = Unit(heights_list, heights_units)

    from gtable_py import Gtable as _Gtable  # local alias to keep typing clean

    out = _Gtable(widths=new_widths, heights=new_heights, respect=table.respect)

    for idx, name in enumerate(table.layout["name"]):
        out = gtable_add_grob(
            out,
            table.grobs[idx],
            t=table.layout["t"][idx],
            l=table.layout["l"][idx],
            b=table.layout["b"][idx],
            r=table.layout["r"][idx],
            z=table.layout["z"][idx],
            clip=table.layout["clip"][idx],
            name=name,
        )
    copy_state(table, out)

    bg_indices = [
        i for i, n in enumerate(grob.layout["name"]) if "background" in n
    ]
    if bg_indices:
        bg_grob = grob.grobs[bg_indices[0]]
        out = gtable_add_grob(
            out,
            bg_grob,
            t=1,
            l=1,
            b=len(out.heights.values),
            r=len(out.widths.values),
            z=-100,
            clip="on",
            name="background",
        )
        copy_state(table, out)
    return out


class Patchgrob:
    """Marker class for gtables tagged ``"patchgrob"`` in R.

    In R, any gtable with ``class(x)[[1]] == "patchgrob"`` is opaque to
    ``simplify_gt``. Here that's handled by the patchwork class-tag set —
    ``Patchgrob`` is included only for documentation.
    """


def is_patch(x: Any) -> bool:
    """Return ``True`` if *x* is a ``Patch`` instance."""
    return isinstance(x, Patch)


@singledispatch
def patch_grob(x: Any, guides: str = "auto") -> Gtable:
    """S3-style singledispatch equivalent of R's ``patchGrob``.

    Parameters
    ----------
    x : object
        Dispatch key. Registered types: :class:`Patch`, :class:`GuideArea`,
        :class:`WrappedPatch`, :class:`TablePatch`, :class:`WrappedTable`.
    guides : {'auto', 'collect', 'keep'}, default 'auto'
        Whether the handler should collect or keep guides internally.

    Returns
    -------
    gtable_py.Gtable
        A gtable representing the rendered patch.

    Raises
    ------
    TypeError
        If *x* has no registered handler.
    """
    raise TypeError(
        f"No `patch_grob` method for object of type {type(x).__name__}"
    )


@patch_grob.register(Patch)
def _(x: Patch, guides: str = "auto") -> Gtable:
    """Default: return ``patch_table(x)`` unchanged."""
    return patch_table(x)


#: R-compatible alias.
patchGrob = patch_grob


def print_patch(x: Patch):
    """Render a bare :class:`Patch` as a gtable — port of R's ``print.patch``.

    R's ``print.patch`` calls ``patchGrob(x)`` and hands the gtable to
    ``grid.draw``. Here we just return the gtable, letting the caller
    decide whether to draw or introspect it.
    """
    return patch_grob(x)
