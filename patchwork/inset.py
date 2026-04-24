"""``inset_element()`` — place a plot on top of another.

Ports ``R/inset_element.R``. The settings live on an ``inset_settings``
attribute of the returned object (ggplot or wrapped-patch) matching the
R implementation.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from ggplot2_py import GGPlot, is_ggplot
from grid_py import Unit, is_unit

from ._utils import arg_match

__all__ = ["inset_element", "is_inset_patch", "print_inset_patch"]


AlignTo = Literal["panel", "plot", "full"]


def _ensure_unit(x: Any) -> Unit:
    if is_unit(x):
        return x
    return Unit([float(x)], ["npc"])


def inset_element(
    p: Any,
    left: Union[float, Unit],
    bottom: Union[float, Unit],
    right: Union[float, Unit],
    top: Union[float, Unit],
    align_to: AlignTo = "panel",
    on_top: bool = True,
    clip: bool = True,
    ignore_tag: bool = False,
) -> Any:
    """Wrap *p* as an inset with an explicit position.

    Parameters
    ----------
    p : GGPlot, Patchwork, Grob, raster, or anything :func:`wrap_elements` accepts
    left, bottom, right, top : float or grid_py.Unit
        Numeric values are treated as ``npc``.
    align_to : {'panel', 'plot', 'full'}, default 'panel'
    on_top : bool, default ``True``
    clip : bool, default ``True``
    ignore_tag : bool, default ``False``

    Returns
    -------
    GGPlot or WrappedPatch
        The input object tagged with ``inset_settings`` and
        ``_ptw_inset_patch`` markers.
    """
    align_to = arg_match(align_to, ("panel", "plot", "full"), arg="align_to")

    left = _ensure_unit(left)
    bottom = _ensure_unit(bottom)
    right = _ensure_unit(right)
    top = _ensure_unit(top)

    if not is_ggplot(p):
        from .wrap_elements import wrap_elements

        p = wrap_elements(full=p, clip=False)
    else:
        # R's copy-on-modify guarantees each ``inset_element`` call returns
        # a fresh object; Python is reference-semantic, so clone ``p`` here
        # to avoid mutating the caller's plot or cross-contaminating two
        # sibling inset views of the same plot.
        import copy

        p = copy.copy(p)

    clip_str = "on" if clip else "off"
    settings = {
        "left": left,
        "bottom": bottom,
        "right": right,
        "top": top,
        "align_to": align_to,
        "on_top": on_top,
        "clip": clip_str,
        "ignore_tag": ignore_tag,
    }
    from ._ggplot_attrs import safe_set

    safe_set(p, "inset_settings", settings)
    safe_set(p, "_ptw_inset_patch", True)
    return p


def is_inset_patch(x: Any) -> bool:
    """Return ``True`` if *x* was produced by :func:`inset_element`."""
    from ._ggplot_attrs import safe_get

    return bool(safe_get(x, "_ptw_inset_patch", False))


def print_inset_patch(x: Any):
    """Render a bare inset as if it were placed over an empty spacer.

    Ports R's ``print.inset_patch``: ``print(plot_spacer() + x)``. Useful
    when a user has an inset in hand and wants to preview it without
    composing it onto a host plot first.
    """
    from .spacer import plot_spacer
    from .core import patchworkGrob

    return patchworkGrob(plot_spacer() + x)
