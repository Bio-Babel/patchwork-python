"""Jupyter/IPython display integration for patchwork classes.

R's ``print.patchwork`` / ``print.patch`` / ``print.inset_patch`` hand a
gtable to ``grid.draw`` on the current graphics device; the resulting
raster is what the user sees in RStudio / a knitted document. The Python
analogue is to implement ``_repr_png_`` so Jupyter's displayhook shows
the composed figure when a :class:`~patchwork.Patchwork` / :class:`Patch` /
:class:`WrappedPatch` is a cell's last expression.

This module owns the shared rendering path so every patchwork-level
class can call one helper and differ only in how it produces its gtable.
"""

from __future__ import annotations

from typing import Callable, Optional

from ggplot2_py._compat import cli_warn
from gtable_py import Gtable

# Defaults match ``ggplot2_py.GGPlot.fig_*`` so a bare patch renders at
# the same size a standalone ggplot would.
FIG_WIDTH = 7.0
FIG_HEIGHT = 5.0
FIG_DPI = 150


def gtable_to_png(
    gt: Gtable,
    width: float | None = None,
    height: float | None = None,
    dpi: float | None = None,
) -> Optional[bytes]:
    """Render *gt* on a fresh grid page and return its PNG bytes."""
    from grid_py import get_state, grid_draw, grid_newpage

    width = FIG_WIDTH if width is None else float(width)
    height = FIG_HEIGHT if height is None else float(height)
    dpi = float(FIG_DPI) if dpi is None else float(dpi)
    grid_newpage(width=width, height=height, dpi=dpi)
    grid_draw(gt)
    renderer = get_state().get_renderer()
    if renderer is not None:
        return renderer.to_png_bytes()
    return None


def safe_repr_png(
    build_gtable: Callable[[], Optional[Gtable]],
    *,
    width: float | None = None,
    height: float | None = None,
    dpi: float | None = None,
) -> Optional[bytes]:
    """Shared ``_repr_png_`` body used by every patchwork-level class.

    Mirrors ``ggplot2_py.GGPlot._repr_png_``'s error-handling contract:
    Jupyter display hooks must not raise, so any exception during gtable
    construction or rendering is surfaced via :func:`cli_warn` and
    ``None`` is returned.
    """
    try:
        gt = build_gtable()
        if gt is None:
            return None
        return gtable_to_png(gt, width=width, height=height, dpi=dpi)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:  # noqa: BLE001 — Jupyter _repr_* must not raise
        import traceback as _tb

        cli_warn(
            "Failed to render patchwork via _repr_png_: "
            f"{type(exc).__name__}: {exc}\n{_tb.format_exc()}"
        )
        return None
