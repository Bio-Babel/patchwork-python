"""``guide_area()`` — placeholder cell reserved for collected legends."""

from __future__ import annotations

from gtable_py import Gtable, gtable_add_grob

from ._constants import PANEL_COL, PANEL_ROW
from ._gtable_state import add_class, copy_state
from ._patch import Patch, make_patch, patch_grob
from ._utils import zero_grob

__all__ = ["guide_area", "is_guide_area", "GuideArea"]


class GuideArea(Patch):
    """A ``Patch`` that becomes a home for collected guides.

    If no guides are collected at render time the cell behaves as a
    :class:`~patchwork.spacer.Spacer` — matching R semantics.
    """


def guide_area() -> GuideArea:
    """Add an area to hold collected guides.

    Returns
    -------
    GuideArea
        A patch object that, when placed in a layout and ``plot_layout()``
        has ``guides="collect"``, will host the collected legends.
    """
    base = make_patch()
    ga = GuideArea(plot=base.plot, table=base.table)
    add_class(ga.table, "guide_area")
    return ga


def is_guide_area(x: object) -> bool:
    """Return ``True`` if *x* is a :class:`GuideArea`."""
    return isinstance(x, GuideArea)


@patch_grob.register(GuideArea)
def _(x: GuideArea, guides: str = "auto") -> Gtable:
    """Build a gtable whose panel cell is marked as a guide-area slot."""
    from ._patch import patch_table  # local import to avoid a cycle

    table = patch_table(x)
    out = gtable_add_grob(
        table,
        zero_grob(),
        t=PANEL_ROW,
        l=PANEL_COL,
        name="panel-guide_area",
    )
    copy_state(table, out)
    add_class(out, "guide_area")
    return out
