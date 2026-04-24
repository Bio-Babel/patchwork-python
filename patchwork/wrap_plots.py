"""``wrap_plots()`` — programmatic composition of many plots.

Ports ``R/wrap_plots.R``. Accepts both positional plots and a single list
argument; when *design* is a string and every plot has a name that matches
an area letter, plots are matched by name.
"""

from __future__ import annotations

from typing import Any, List, Optional

from ggplot2_py import is_ggplot
from grid_py import is_grob

from .add_plot import Patchwork, plot_filler
from .layout import plot_layout
from .spacer import plot_spacer
from ._utils import WAIVER

__all__ = ["wrap_plots"]


def _is_valid_plot(x: Any) -> bool:
    """A plot is a ggplot or a grob (or a patchwork, handled by ``+``)."""
    return is_ggplot(x) or is_grob(x) or isinstance(x, Patchwork)


def wrap_plots(
    *plots: Any,
    ncol: Any = None,
    nrow: Any = None,
    byrow: Any = None,
    widths: Any = None,
    heights: Any = None,
    guides: Any = None,
    tag_level: Any = None,
    design: Any = None,
    axes: Any = None,
    axis_titles: Any = WAIVER,
) -> Patchwork:
    """Compose plots into a patchwork programmatically.

    Parameters
    ----------
    *plots
        Individual plots or a single iterable. Named kwargs are forwarded
        to :func:`plot_layout`.

    Returns
    -------
    Patchwork
    """
    if axis_titles is WAIVER:
        axis_titles = axes

    if len(plots) == 0:
        raise ValueError("`wrap_plots` needs at least one plot")

    first = plots[0]
    if _is_valid_plot(first):
        plot_list: List[Any] = list(plots)
        plot_names: Optional[dict[int, str]] = None
    elif isinstance(first, (list, tuple)) or (
        isinstance(first, dict) and len(plots) == 1
    ):
        if isinstance(first, dict):
            plot_list = list(first.values())
            plot_names = {i: k for i, k in enumerate(first.keys())}
        else:
            plot_list = list(first)
            plot_names = None
    else:
        raise TypeError(
            "Can only wrap <ggplot> and/or <grob> objects or a list of them"
        )

    if not all(_is_valid_plot(p) for p in plot_list):
        raise TypeError("Only know how to add <ggplot> and/or <grob> objects")

    if plot_names is not None and isinstance(design, str):
        area_chars = set(c for c in design if not c.isspace())
        area_chars.discard("#")
        if set(plot_names.values()) <= area_chars:
            ordered_chars = sorted(area_chars)
            name_to_plot = {plot_names[i]: p for i, p in enumerate(plot_list)}
            plot_list = [name_to_plot.get(ch, plot_spacer()) for ch in ordered_chars]

    result: Any = plot_filler()
    for p in plot_list:
        result = result + p
    result = result + plot_layout(
        ncol=ncol,
        nrow=nrow,
        byrow=byrow,
        widths=widths,
        heights=heights,
        guides=guides,
        tag_level=tag_level,
        design=design,
        axes=axes,
        axis_titles=axis_titles,
    )
    return result
