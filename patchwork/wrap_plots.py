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
    **named_plots: Any,
) -> Patchwork:
    """Compose plots into a patchwork programmatically.

    Parameters
    ----------
    *plots
        Individual plots, or a single ``list`` / ``tuple`` / ``dict`` of
        plots. Dict keys are treated as area names.
    **named_plots
        Named plots as keyword arguments (R-style:
        ``wrap_plots(A=p1, B=p2, design="AB")``). Mixed positional and
        named plots are supported.

    Other keyword arguments are forwarded to :func:`plot_layout`.

    Returns
    -------
    Patchwork
    """
    if axis_titles is WAIVER:
        axis_titles = axes

    if len(plots) == 0 and not named_plots:
        raise ValueError("`wrap_plots` needs at least one plot")

    plot_list: List[Any] = []
    plot_names: Optional[dict[int, str]] = None

    if len(plots) == 1 and not named_plots:
        first = plots[0]
        if isinstance(first, dict):
            plot_list = list(first.values())
            plot_names = dict(enumerate(first.keys()))
        elif isinstance(first, (list, tuple)) and not _is_valid_plot(first):
            plot_list = list(first)
        elif _is_valid_plot(first):
            plot_list = [first]
        else:
            raise TypeError(
                "Can only wrap <ggplot> and/or <grob> objects or a list of them"
            )
    else:
        # Mixed positional + named (R-style). Positional plots come first,
        # named plots append after, matching R's list(...) ordering where
        # named entries appear in declaration order.
        plot_list = list(plots) + list(named_plots.values())
        if named_plots:
            offset = len(plots)
            plot_names = {offset + i: k for i, k in enumerate(named_plots.keys())}

    if not all(_is_valid_plot(p) for p in plot_list):
        raise TypeError("Only know how to add <ggplot> and/or <grob> objects")

    # Name-based area placement (R wrap_plots.R:59-69): when a design
    # string is set and every plot name matches an area letter, fill the
    # area slots by name and pad the rest with plot_spacer().
    if plot_names is not None and isinstance(design, str):
        area_chars = set(c for c in design if not c.isspace())
        area_chars.discard("#")
        name_values = set(plot_names.values())
        if name_values and name_values <= area_chars:
            ordered_chars = sorted(area_chars)
            name_to_plot: dict[str, Any] = {}
            for i, p in enumerate(plot_list):
                nm = plot_names.get(i)
                if nm is not None:
                    name_to_plot[nm] = p
            plot_list = [
                name_to_plot.get(ch, plot_spacer()) for ch in ordered_chars
            ]

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
