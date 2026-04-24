"""Operator-level plot arithmetic.

Ports ``R/arithmetic.R``. The public dunders live on :class:`Patchwork`;
this module exposes the implementation functions that those dunders
delegate to (``sub_impl``, ``truediv_impl``, ``or_impl``, ``mul_impl``,
``and_impl``). They are also the bodies of the patchwork-side handlers
installed on :class:`ggplot2_py.GGPlot` below so that ``p1 - p2``,
``p1 | p2``, ``p1 / p2`` work when the LHS is still a bare ggplot.

Python's operator precedence differs from R's (essentials §2.3):

- ``p1 | p2 / p3`` reparses in Python; always parenthesize.
- ``p1 + p2 * theme_bw()`` reparses; always parenthesize.
"""

from __future__ import annotations

from typing import Any

from ggplot2_py import GGPlot, is_ggplot, is_theme

from .add_plot import (
    Patchwork,
    add_patches,
    as_patchwork,
    get_patches,
    is_patchwork,
    new_patchwork,
    plot_filler,
    should_autowrap,
)

__all__ = [
    "sub_impl",
    "truediv_impl",
    "or_impl",
    "mul_impl",
    "and_impl",
    "install_ggplot_operators",
]


def _autowrap(e2: Any) -> Any:
    if should_autowrap(e2):
        from .wrap_elements import wrap_elements

        return wrap_elements(full=e2)
    return e2


def sub_impl(e1: Any, e2: Any) -> Any:
    """Implements ``e1 - e2`` (beside, same nesting level)."""
    if e2 is None:
        return e1
    if e1 is None:
        return e2
    e2 = _autowrap(e2)
    if not (is_ggplot(e2) or is_patchwork(e2)):
        raise TypeError("Only knows how to fold ggplot/patchwork objects together")
    patches = new_patchwork()
    if is_patchwork(e2):
        plot = plot_filler()
        patches.plots = [e1, e2]
    else:
        plot = e2
        patches.plots = [e1]
    return add_patches(plot, patches)


def truediv_impl(e1: Any, e2: Any) -> Any:
    """Implements ``e1 / e2`` (stack vertical)."""
    from .layout import plot_layout

    if e2 is None:
        return e1
    if e1 is None:
        return e2
    e2 = _autowrap(e2)
    if not is_patchwork(e1):
        return e1 + e2 + plot_layout(ncol=1)
    if e1.patches.layout.ncol is not None and e1.patches.layout.ncol == 1:
        return e1 + e2
    return sub_impl(e1, e2) + plot_layout(ncol=1)


def or_impl(e1: Any, e2: Any) -> Any:
    """Implements ``e1 | e2`` (stack horizontal)."""
    from .layout import plot_layout

    if e2 is None:
        return e1
    if e1 is None:
        return e2
    e2 = _autowrap(e2)
    if not is_patchwork(e1):
        return e1 + e2 + plot_layout(nrow=1)
    if e1.patches.layout.nrow is not None and e1.patches.layout.nrow == 1:
        return e1 + e2
    return sub_impl(e1, e2) + plot_layout(nrow=1)


def mul_impl(e1: Any, e2: Any) -> Any:
    """Implements ``e1 * e2`` (add to current level only)."""
    if e2 is None:
        return e1
    if is_patchwork(e1):
        new_plots = []
        for p in e1.patches.plots:
            if not is_patchwork(p):
                p = p + e2
            new_plots.append(p)
        e1.patches.plots = new_plots
    return e1 + e2


def and_impl(e1: Any, e2: Any) -> Any:
    """Implements ``e1 & e2`` (recurse into nested)."""
    if e2 is None:
        return e1
    if is_patchwork(e1):
        if is_theme(e2):
            current = e1.patches.annotation.theme
            e1.patches.annotation.theme = (
                e2 if current is None else current + e2
            )
        new_plots = []
        for p in e1.patches.plots:
            if is_patchwork(p):
                p = and_impl(p, e2)
            else:
                p = p + e2
            new_plots.append(p)
        e1.patches.plots = new_plots
    return e1 + e2


# -----------------------------------------------------------------------------
# Install operators on GGPlot so that `p1 | p2` works when neither side is a
# patchwork yet. R-side S3 dispatch registered ``-.ggplot``, ``/.ggplot``, etc.
# Python-side, we attach these dunders to ``ggplot2_py.GGPlot`` at import time.
# -----------------------------------------------------------------------------


def install_ggplot_operators() -> None:
    """Attach ``-``, ``|``, ``/``, ``*``, ``&`` dunders to :class:`GGPlot`."""
    GGPlot.__sub__ = lambda self, other: sub_impl(self, other)
    GGPlot.__or__ = lambda self, other: or_impl(self, other)
    GGPlot.__truediv__ = lambda self, other: truediv_impl(self, other)
    # The "*" and "&" are documented as "gg" operators that only matter when
    # at least one side is already a patchwork; registering them on GGPlot
    # lets users write ``(p1 + p2) * theme_bw()`` without the LHS needing
    # prior promotion.
    GGPlot.__mul__ = lambda self, other: mul_impl(self, other)
    GGPlot.__and__ = lambda self, other: and_impl(self, other)
