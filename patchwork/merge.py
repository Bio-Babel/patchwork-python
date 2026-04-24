"""``merge()`` — flatten a nested patchwork to a single level.

Ports ``R/merge.R``. ``merge.ggplot`` is the identity; ``merge.patchwork``
wraps the current patchwork as a single child under a :class:`PlotFiller`.
"""

from __future__ import annotations

from functools import singledispatch
from typing import Any

from ggplot2_py import GGPlot

from .add_plot import Patchwork, add_patches, new_patchwork, plot_filler

__all__ = ["merge"]


@singledispatch
def merge(x: Any, *args: Any, **kwargs: Any) -> Any:
    """Flatten (or identity-return) a plot object.

    The default dispatch returns *x* unchanged so that user-facing calls
    never crash; registered handlers do the real work.

    Parameters
    ----------
    x : object
        Dispatch key. Registered types: ``ggplot2_py.GGPlot`` (identity)
        and :class:`patchwork.Patchwork` (demote to single child under a
        filler).
    *args, **kwargs
        Unused by the default; some handlers may accept additional
        arguments.

    Returns
    -------
    object
        Default: *x* unchanged.
    """
    return x


@merge.register(GGPlot)
def _(x: GGPlot, *args: Any, **kwargs: Any) -> GGPlot:
    """``merge.ggplot`` — identity (R defines it but it has no effect)."""
    return x


@merge.register(Patchwork)
def _(x: Patchwork, *args: Any, **kwargs: Any) -> Patchwork:
    """``merge.patchwork`` — demote *x* to a single child under a filler."""
    patches = new_patchwork()
    patches.plots = [x]
    return add_patches(plot_filler(), patches)
