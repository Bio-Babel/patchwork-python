"""``Patchwork`` container and the ``+`` / ``update_ggplot`` registration.

Ports ``R/add_plot.R``. In R, ``Patchwork`` is a ggplot with
``class(x) <- c("patchwork", class(x))``. Here we use *composition* instead
of inheritance (essentials §2.1): a ``Patchwork`` wraps a ``GGPlot`` plus a
``Patches`` container.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import singledispatch
from typing import Any, List, Optional

from ggplot2_py import GGPlot, ggplot, is_ggplot
from ggplot2_py.plot import update_ggplot
from grid_py import Grob, is_grob  # noqa: F401 — referenced in Patchwork.__add__
from gtable_py import Gtable, is_gtable

from .layout import PlotLayout, plot_layout

__all__ = [
    "Patchwork",
    "Patches",
    "PlotFiller",
    "plot_filler",
    "new_patchwork",
    "is_patchwork",
    "as_patchwork",
    "add_patches",
    "get_patches",
    "should_autowrap",
    "is_empty",
]


@dataclass
class Patches:
    """The content of a patchwork: plots, layout, annotation."""

    plots: List[Any] = field(default_factory=list)
    layout: PlotLayout = field(default_factory=lambda: new_patchwork_layout())
    annotation: Any = None

    def __post_init__(self):
        if self.annotation is None:
            # Late import because annotation.py imports from us.
            from .annotation import plot_annotation

            self.annotation = plot_annotation(
                title=None,
                subtitle=None,
                caption=None,
                tag_levels=None,
                tag_prefix=None,
                tag_suffix=None,
                tag_sep=None,
                theme=None,
            )


def new_patchwork_layout() -> PlotLayout:
    """The layout passed into a freshly constructed :class:`Patches`."""
    return plot_layout(
        ncol=None,
        nrow=None,
        byrow=None,
        widths=None,
        heights=None,
        guides=None,
        tag_level=None,
        design=None,
        axes=None,
        axis_titles=None,
    )


def new_patchwork() -> Patches:
    """Build a default :class:`Patches` holder (mirrors ``R/add_plot.R::new_patchwork``)."""
    return Patches()


class PlotFiller:
    """Sentinel patch representing "no plot yet" (R's ``plot_filler``).

    ``PlotFiller + x`` routes through :func:`add_patches` so that seeding a
    reduction with ``plot_filler()`` and folding over a list of plots
    produces a :class:`Patchwork` without the first plot ever becoming the
    "active" one.
    """

    def __repr__(self) -> str:  # pragma: no cover — cosmetic
        return "<patchwork.PlotFiller>"

    def _repr_png_(self):
        """Sentinel — no pixels to draw."""
        return None

    def __add__(self, other: Any) -> Any:
        if other is None:
            return self
        if is_ggplot(other) or isinstance(other, Patchwork):
            return update_ggplot(other, self)
        # Defer to the registered update_ggplot handler for *other*'s type.
        try:
            return update_ggplot(other, self)
        except Exception:
            from .wrap_elements import wrap_elements

            return update_ggplot(wrap_elements(full=other), self)

    def __radd__(self, other: Any) -> Any:  # pragma: no cover — defensive
        return self.__add__(other)


def plot_filler() -> PlotFiller:
    """Return a :class:`PlotFiller` sentinel used when a composition is still empty."""
    return PlotFiller()


def is_empty(x: Any) -> bool:
    """Return ``True`` if *x* is a :class:`PlotFiller`."""
    return isinstance(x, PlotFiller)


class Patchwork:
    """A composed plot: a ggplot plus a :class:`Patches` container.

    Unlike R's class-tag mechanism, ``Patchwork`` is a plain composition.
    It exposes operator dunders (``+``, ``-``, ``/``, ``|``, ``*``, ``&``)
    and proxies a handful of common ggplot calls to ``self.plot`` so that
    expressions like ``pw + labs(...)`` still work on the inner plot.
    """

    def __init__(self, plot: GGPlot, patches: Optional[Patches] = None) -> None:
        self.plot = plot
        self.patches = patches if patches is not None else new_patchwork()

    # ---- Indexing / iteration -------------------------------------------
    def __len__(self) -> int:
        return len(self.patches.plots) + (0 if is_empty(self.plot) else 1)

    def __getitem__(self, idx):
        # 0-based half-open, matching Python convention.
        if isinstance(idx, tuple):
            first = idx[0]
            rest = idx[1:]
            sub = self.__getitem__(first)
            if not rest:
                return sub
            if not isinstance(sub, Patchwork):
                raise IndexError("Can only do nested indexing into patchworks")
            return sub.__getitem__(rest if len(rest) > 1 else rest[0])

        n = len(self.patches.plots)
        if not is_empty(self.plot) and idx == n:
            return self.plot
        if idx < 0 or idx >= n:
            raise IndexError("Index out of bounds")
        return self.patches.plots[idx]

    def __setitem__(self, idx, value) -> None:
        if not is_ggplot(value) and not isinstance(value, Patchwork):
            from .wrap_elements import wrap_elements

            value = wrap_elements(value)

        if isinstance(idx, tuple):
            first = idx[0]
            rest = idx[1:]
            target = self.patches.plots[first]
            if not isinstance(target, Patchwork):
                raise IndexError("Can only do nested indexing into patchworks")
            target[rest if len(rest) > 1 else rest[0]] = value
            return

        n = len(self.patches.plots)
        if not is_empty(self.plot) and idx == n:
            # Replace active plot → promote value to root.
            result = add_patches(value, self.patches)
            self.plot = result.plot
            self.patches = result.patches
            return
        self.patches.plots[idx] = value

    def names(self) -> None:
        """R's ``names(pw)`` — patchwork doesn't carry names."""
        return None

    def to_list(self) -> List[Any]:
        """R's ``as.list(pw)``: all sub-plots including the active one."""
        return list(get_patches(self).plots)

    def to_gtable(self) -> Gtable:
        """Shorthand for :func:`~patchwork.core.patchworkGrob`."""
        from .core import patchworkGrob

        return patchworkGrob(self)

    def __repr__(self) -> str:
        n = len(self)
        tagged = (
            "on" if self.patches.annotation.tag_levels not in (None, []) else "off"
        )
        guides = self.patches.layout.guides
        g = "collected" if guides == "collect" else "kept"
        return (
            f"A patchwork composed of {n} patches\n"
            f"- Autotagging is turned {tagged}\n"
            f"- Guides are {g}"
        )

    def _repr_png_(self):
        """Port of R's ``print.patchwork`` for Jupyter displayhooks."""
        from ._display import safe_repr_png
        from .core import patchworkGrob

        return safe_repr_png(lambda: patchworkGrob(self))

    # ---- Operator overloads --------------------------------------------
    def __add__(self, other: Any) -> "Patchwork":
        # Patchwork-specific RHS types — registered on ``update_ggplot`` —
        # always return a Patchwork. GGPlot on the RHS also goes through
        # ``update_ggplot`` because that handler is where patchwork
        # extends itself (see R's ``ggplot_add.ggplot``).
        from .annotation import PlotAnnotation
        from ._patch import Patch as _Patch
        from .layout import PlotLayout

        if isinstance(other, (Patchwork, PlotLayout, PlotAnnotation, _Patch, GGPlot)):
            return update_ggplot(other, self)
        if isinstance(other, Grob):
            from .wrap_elements import wrap_elements

            return update_ggplot(wrap_elements(full=other), self)
        import numpy as np

        if isinstance(other, np.ndarray):
            from .wrap_elements import wrap_elements

            return update_ggplot(wrap_elements(full=other), self)
        # Theme / Labels / Layer / Scale / …: modify the inner plot in place.
        self.plot = self.plot + other
        return self

    def __radd__(self, other: Any) -> "Patchwork":  # pragma: no cover — defensive
        return update_ggplot(other, self)

    def __sub__(self, other: Any) -> "Patchwork":
        from .arithmetic import sub_impl

        return sub_impl(self, other)

    def __truediv__(self, other: Any) -> "Patchwork":
        from .arithmetic import truediv_impl

        return truediv_impl(self, other)

    def __or__(self, other: Any) -> "Patchwork":
        from .arithmetic import or_impl

        return or_impl(self, other)

    def __mul__(self, other: Any) -> "Patchwork":
        from .arithmetic import mul_impl

        return mul_impl(self, other)

    def __and__(self, other: Any) -> "Patchwork":
        from .arithmetic import and_impl

        return and_impl(self, other)


def is_patchwork(x: Any) -> bool:
    """Return ``True`` if *x* is a :class:`Patchwork`."""
    return isinstance(x, Patchwork)


@singledispatch
def as_patchwork(x: Any) -> Patchwork:
    """Coerce *x* to a :class:`Patchwork`.

    Registered for ``GGPlot`` and ``Patchwork``; the default raises.
    """
    raise TypeError(
        f"Don't know how to convert an object of type {type(x).__name__} to a patchwork"
    )


@as_patchwork.register(GGPlot)
def _(x: GGPlot) -> Patchwork:
    return Patchwork(plot=x, patches=new_patchwork())


@as_patchwork.register(Patchwork)
def _(x: Patchwork) -> Patchwork:
    return x


@singledispatch
def add_patches(plot: Any, patches: Patches) -> Patchwork:
    """Attach *patches* to *plot* (dispatch on *plot* type)."""
    raise TypeError(f"Cannot add patches to object of type {type(plot).__name__}")


@add_patches.register(GGPlot)
def _(plot: GGPlot, patches: Patches) -> Patchwork:
    pw = as_patchwork(plot)
    pw.patches = patches
    return pw


@add_patches.register(Patchwork)
def _(plot: Patchwork, patches: Patches) -> Patchwork:
    patches.plots = list(patches.plots) + [plot]
    return add_patches(plot_filler(), patches)


@add_patches.register(PlotFiller)
def _(plot: PlotFiller, patches: Patches) -> Patchwork:
    pw = Patchwork(plot=plot, patches=patches)  # type: ignore[arg-type]
    return pw


def get_patches(plot: Any) -> Patches:
    """Pull the :class:`Patches` out of *plot*, appending the active plot to the list.

    Mirrors R's ``get_patches`` (``R/add_plot.R:36-55``) in semantics,
    with one deliberate divergence: R *mutates* its input — after
    ``get_patches(plot)`` runs, ``plot$patches`` is ``NULL`` and the
    ``'patchwork'`` class is stripped off ``plot``. Python returns a
    fresh :class:`Patches` and leaves the input untouched, so callers
    can reuse ``plot`` without surprise. Every in-package caller relies
    only on the return value, so this is safe; external callers should
    assume the input is unchanged.
    """
    if is_patchwork(plot):
        patches = plot.patches
        # Clone so the caller can mutate without aliasing.
        plots = list(patches.plots)
        from .free import is_free_plot

        active = plot.plot
        if not is_empty(active):
            if is_free_plot(active):
                # Strip patchwork_free_settings on the way out.
                plots = plots + [active]
            else:
                plots = plots + [active]
        return Patches(plots=plots, layout=patches.layout, annotation=patches.annotation)

    result = Patches()
    if not is_empty(plot):
        result.plots.append(plot)
    return result


def should_autowrap(x: Any) -> bool:
    """Return ``True`` if *x* is a grob/raster-like object that must be wrapped.

    Port of R's ``should_autowrap`` (add_plot.R:30-32):

        is.grob(x) || inherits(x, 'formula') || is.raster(x) ||
        inherits(x, 'nativeRaster')

    The R side recognises four types; the Python side covers the two
    with native counterparts:

    - ``is_grob(x)`` — grid_py grobs; covers R's ``is.grob``.
    - ``isinstance(x, numpy.ndarray)`` — covers both R's ``raster``
      (matrix with raster class) and ``nativeRaster`` (integer matrix
      backed by ``.Internal(nativeRaster)``). Both are dense arrays in
      Python's universe.

    ``formula`` intentionally has no Python analogue — R formulas
    describe base-R plotting expressions (``~plot(x, y)``) which aren't
    representable in Python. See :func:`~patchwork.wrap_elements.as_patch_formula`.
    """
    import numpy as np

    if is_grob(x):
        return True
    if isinstance(x, np.ndarray):
        return True
    return False


# -----------------------------------------------------------------------------
# update_ggplot registrations
# -----------------------------------------------------------------------------
#
# These give ggplot2_py the knowledge of how to interpret objects on the RHS of
# ``ggplot + x`` where *x* is patchwork-specific. Registration happens when
# this module is imported.


def _register_update_ggplot() -> None:
    """Register patchwork-specific RHS types on ``update_ggplot``."""
    # Local imports to avoid import cycles.
    from .annotation import PlotAnnotation
    from ._patch import Patch
    from .layout import PlotLayout

    @update_ggplot.register(GGPlot)
    def _(obj: GGPlot, plot: Any, object_name: str = "") -> Patchwork:
        patches = get_patches(plot)
        return add_patches(obj, patches)

    @update_ggplot.register(PlotLayout)
    def _(obj: PlotLayout, plot: Any, object_name: str = "") -> Patchwork:  # noqa: F811
        pw = as_patchwork(plot)
        do_change = {k: v for k, v in obj.items() if not _is_waiver_value(v)}
        for key, value in do_change.items():
            setattr(pw.patches.layout, key, value)
        return pw

    @update_ggplot.register(PlotAnnotation)
    def _(obj: PlotAnnotation, plot: Any, object_name: str = "") -> Patchwork:  # noqa: F811
        pw = as_patchwork(plot)
        if obj.theme is None:
            pw.patches.annotation.theme = None
        elif not _is_waiver_value(obj.theme):
            current = pw.patches.annotation.theme
            if current is None:
                pw.patches.annotation.theme = obj.theme
            else:
                pw.patches.annotation.theme = current + obj.theme

        for key, value in obj.items():
            if key == "theme":
                continue
            if _is_waiver_value(value):
                continue
            setattr(pw.patches.annotation, key, value)
        return pw

    @update_ggplot.register(Patchwork)
    def _(obj: Patchwork, plot: Any, object_name: str = "") -> Patchwork:  # noqa: F811
        patches = get_patches(plot)
        patches.plots = list(patches.plots) + [obj]
        return add_patches(plot_filler(), patches)

    @update_ggplot.register(Patch)
    def _(obj: Patch, plot: Any, object_name: str = "") -> Patchwork:  # noqa: F811
        patches = get_patches(plot)
        patches.plots = list(patches.plots) + [obj]
        return add_patches(plot_filler(), patches)

    @update_ggplot.register(Grob)
    def _(obj: Grob, plot: Any, object_name: str = "") -> Patchwork:  # noqa: F811
        from .wrap_elements import wrap_elements

        return plot + wrap_elements(full=obj)

    import numpy as np

    @update_ggplot.register(np.ndarray)
    def _(obj: np.ndarray, plot: Any, object_name: str = "") -> Patchwork:  # noqa: F811
        from .wrap_elements import wrap_elements

        return plot + wrap_elements(full=obj)

    if is_gtable:  # true; guard against partial import
        @update_ggplot.register(Gtable)
        def _(obj: Gtable, plot: Any, object_name: str = "") -> Patchwork:  # noqa: F811
            from .wrap_elements import wrap_elements

            return plot + wrap_elements(full=obj)


def _is_waiver_value(v: Any) -> bool:
    """Helper that avoids an import cycle for the per-dict waiver check."""
    from ggplot2_py import is_waiver

    return is_waiver(v)
