"""Cross-plot dimension alignment.

Ports ``R/plot_multipage.R``. ``get_dim`` / ``set_dim`` / ``align_patches``
work on bare ggplots; ``get_dim`` on a patchwork raises (matching R).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from functools import singledispatch
from typing import Any, Iterable, List, Sequence

from ggplot2_py import GGPlot, find_panel
from grid_py import Unit, convert_height, convert_width

from .add_plot import Patchwork

__all__ = [
    "PlotDimension",
    "GGPlotDimension",
    "get_dim",
    "set_dim",
    "get_max_dim",
    "align_patches",
    "align_plots",
]


@dataclass
class PlotDimension:
    """A snapshot of a plot's outer margins in mm.

    Four attributes (``l``, ``r``, ``t``, ``b``) each a list of mm values.
    """

    l: List[float]
    r: List[float]
    t: List[float]
    b: List[float]


class GGPlotDimension(PlotDimension):
    """A :class:`PlotDimension` produced from a bare ggplot."""


@singledispatch
def get_dim(plot: Any) -> PlotDimension:
    """Extract outer-margin dimensions from *plot*.

    Parameters
    ----------
    plot : GGPlot or Patchwork
        The plot to measure. Bare ``ggplot2_py.GGPlot`` is supported;
        a ``Patchwork`` raises (matching R's ``get_dim.patchwork``).

    Returns
    -------
    PlotDimension
        Four lists (``l``, ``r``, ``t``, ``b``) of outer-margin widths
        and heights in mm.

    Raises
    ------
    TypeError
        If *plot* is neither a GGPlot nor a supported dispatch type.
    RuntimeError
        If *plot* is a Patchwork (R parity).
    """
    raise TypeError(f"Cannot get dimensions from {type(plot).__name__}")


@get_dim.register(GGPlot)
def _(plot: GGPlot) -> GGPlotDimension:
    from .core import plot_table

    table = plot_table(plot, "auto")
    panel_pos = find_panel(table)
    widths_mm = convert_width(table.widths, "mm").values
    heights_mm = convert_height(table.heights, "mm").values
    dims = GGPlotDimension(
        l=list(widths_mm[: panel_pos["l"] - 1]),
        r=list(widths_mm[panel_pos["r"]:]),
        t=list(heights_mm[: panel_pos["t"] - 1]),
        b=list(heights_mm[panel_pos["b"]:]),
    )
    return dims


@get_dim.register(Patchwork)
def _(plot: Patchwork) -> PlotDimension:  # noqa: F811
    raise RuntimeError("Getting dimensions on patchworks is currently unsupported")


@singledispatch
def set_dim(plot: Any, dim: PlotDimension) -> Any:
    """Apply a captured :class:`PlotDimension` to *plot*.

    Parameters
    ----------
    plot : GGPlot or Patchwork
        The plot to be aligned.
    dim : PlotDimension
        Dimensions previously captured with :func:`get_dim` or
        :func:`get_max_dim`.

    Returns
    -------
    GGPlot
        The same plot tagged with ``fixed_dimensions`` so rendering
        uses the captured outer margins.

    Raises
    ------
    RuntimeError
        If *plot* is a Patchwork (R parity).
    """
    raise TypeError(f"Cannot set dimensions on {type(plot).__name__}")


@set_dim.register(GGPlot)
def _(plot: GGPlot, dim: PlotDimension) -> GGPlot:
    if not isinstance(dim, PlotDimension):
        raise TypeError("`dim` must be a PlotDimension from `get_dim`")
    from ._ggplot_attrs import safe_set

    safe_set(plot, "fixed_dimensions", dim)
    safe_set(plot, "_ptw_fixed_dim", True)
    return plot


@set_dim.register(Patchwork)
def _(plot: Patchwork, dim: PlotDimension) -> Patchwork:  # noqa: F811
    raise RuntimeError("Setting dimensions on patchworks is currently unsupported")


def _collect_plots(args: Sequence[Any]) -> List[Any]:
    """Accept either many plots or a single iterable of plots, R-style."""
    if len(args) == 1 and isinstance(args[0], (list, tuple)):
        return list(args[0])
    return list(args)


def get_max_dim(*plots: Any) -> PlotDimension:
    """Compute the element-wise max of :func:`get_dim` across plots.

    Parameters
    ----------
    *plots : GGPlot
        Plots to measure. Accepts a single iterable or multiple
        positional arguments (R-style).

    Returns
    -------
    PlotDimension
        A :class:`PlotDimension` whose ``l`` / ``r`` / ``t`` / ``b``
        lists hold the max of each corresponding component across *plots*.
    """
    all_plots = _collect_plots(plots)
    dims = [get_dim(p) for p in all_plots]
    return PlotDimension(
        l=list(_parallel_max(*[d.l for d in dims])),
        r=list(_parallel_max(*[d.r for d in dims])),
        t=list(_parallel_max(*[d.t for d in dims])),
        b=list(_parallel_max(*[d.b for d in dims])),
    )


def align_patches(*plots: Any) -> List[Any]:
    """Apply the element-wise max dimensions to every plot.

    Parameters
    ----------
    *plots : GGPlot
        Plots to align. Accepts a single iterable or multiple positional
        arguments (R-style).

    Returns
    -------
    list of GGPlot
        The plots, each tagged with the shared max dimensions.
    """
    all_plots = _collect_plots(plots)
    max_dims = get_max_dim(all_plots)
    return [set_dim(p, max_dims) for p in all_plots]


def align_plots(*plots: Any) -> List[Any]:
    """Deprecated alias for :func:`align_patches` (kept for R API parity).

    Parameters
    ----------
    *plots : GGPlot
        Plots to align.

    Returns
    -------
    list of GGPlot
        Forwarded from :func:`align_patches`.

    Warns
    -----
    DeprecationWarning
        Every call emits this; use :func:`align_patches` instead.
    """
    warnings.warn(
        "`align_plots` is deprecated; use `align_patches` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return align_patches(*plots)


def _parallel_max(*vectors: Sequence[float]) -> list[float]:
    if not vectors:
        return []
    length = max(len(v) for v in vectors)
    result: list[float] = []
    for i in range(length):
        vals = [v[i] for v in vectors if i < len(v)]
        result.append(max(vals) if vals else 0.0)
    return result
