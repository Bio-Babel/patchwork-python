"""``free()`` — release a plot from some alignment constraints.

Ports ``R/free.R``. The R implementation uses ``class(x) <- c("free_plot", ...)``
and stores options in an attribute. Python-side we use a dict attribute
``_free_settings`` on the wrapped object.
"""

from __future__ import annotations

import warnings
from typing import Any, Literal, Union

from ggplot2_py import GGPlot, is_ggplot

from .add_plot import Patchwork, is_patchwork
from .merge import merge
from ._utils import arg_match

__all__ = [
    "free",
    "is_free_plot",
    "FreePlot",
]


FreeType = Literal["panel", "label", "space"]


class FreePlot:
    """Marker: either a ggplot or a patchwork tagged "free".

    Python uses composition rather than inheritance to avoid collisions
    with ggplot2_py's ``__add__`` chain (essentials §2.1).
    """


def _settings_attr(x: Any) -> str:
    return "patchwork_free_settings" if is_patchwork(x) else "free_settings"


def _current_settings(x: Any) -> dict[str, str]:
    from ._ggplot_attrs import safe_get

    return dict(safe_get(x, _settings_attr(x), {}) or {})


def free(
    x: Union[GGPlot, Patchwork],
    type: FreeType = "panel",
    side: str = "trbl",
) -> Union[GGPlot, Patchwork]:
    """Free a plot from some alignment constraints.

    Parameters
    ----------
    x : GGPlot or Patchwork
        The plot to free.
    type : {'panel', 'label', 'space'}, default 'panel'
        Which alignment to release:

        - ``'panel'``: let the panel expand freely without matching others.
        - ``'label'``: keep axis labels glued to the axis instead of aligned.
        - ``'space'``: do not reserve axis-label space at all.
    side : str, default ``'trbl'``
        Subset of ``{t, r, b, l}`` denoting which sides to free.

    Returns
    -------
    GGPlot or Patchwork
        The same object with a ``_ptw_class`` tag and settings attached.
    """
    if not (is_ggplot(x) or is_patchwork(x)):
        raise TypeError("`x` must be a <ggplot> or <patchwork> object")
    type = arg_match(type, ("panel", "label", "space"), arg="type")
    side_low = side.lower()
    if any(ch not in "trbl" for ch in side_low):
        raise ValueError("`side` can only contain the t, r, b, and l characters")
    sides = list(side_low)
    new_settings = {s: type for s in sides}

    # R's copy-on-modify semantics: ``free()`` must return a fresh object
    # without mutating the caller's plot. In Python we must explicitly copy
    # to mirror this — otherwise repeated ``free(p)`` calls on the same
    # variable would accumulate state across calls.
    import copy

    x = copy.copy(x)

    attr = _settings_attr(x)
    old_settings = _current_settings(x)
    overlap = set(old_settings) & set(new_settings)
    if overlap:
        warnings.warn(
            f"Overwriting free settings for {sorted(overlap)}",
            UserWarning,
            stacklevel=2,
        )
        for k in overlap:
            del old_settings[k]
    combined = {**new_settings, **old_settings}
    from ._ggplot_attrs import safe_set

    safe_set(x, attr, combined)
    safe_set(x, "_ptw_free_plot", True)
    result = merge(x)
    safe_set(result, attr, combined)
    safe_set(result, "_ptw_free_plot", True)
    return result


def is_free_plot(x: Any) -> bool:
    """Return ``True`` if *x* was produced by :func:`free`."""
    from ._ggplot_attrs import safe_get

    return bool(safe_get(x, "_ptw_free_plot", False))
