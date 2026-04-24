"""``plot_spacer()`` — empty transparent placeholder patch."""

from __future__ import annotations

from ._gtable_state import add_class
from ._patch import Patch, make_patch

__all__ = ["plot_spacer", "is_spacer", "Spacer"]


class Spacer(Patch):
    """A ``Patch`` tagged so ``has_tag`` returns ``False`` for it."""


def plot_spacer() -> Spacer:
    """Add a completely blank area between other patches.

    Returns
    -------
    Spacer
        A transparent empty patch object. When added to a patchwork it
        behaves like any other patch but draws nothing and takes no tag.
    """
    base = make_patch()
    spacer = Spacer(plot=base.plot, table=base.table)
    add_class(spacer.table, "spacer")
    return spacer


def is_spacer(x: object) -> bool:
    """Return ``True`` if *x* is a :class:`Spacer`."""
    return isinstance(x, Spacer)
