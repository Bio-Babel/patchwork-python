"""``plot_annotation()``, tag recursion, and title/caption placement.

Ports ``R/plot_annotation.R``. Automatic tagging is done by walking the
patchwork tree depth-first and assigning labels based on the
``tag_levels`` list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import singledispatch
from typing import Any, Optional, Sequence

from ggplot2_py import (
    ggplot,
    ggplotGrob,
    labs,
    theme,
    waiver,
)
from grid_py import Unit
from gtable_py import Gtable, gtable_add_cols, gtable_add_grob, gtable_add_rows

from ._constants import CAPTION_ROW, SUBTITLE_ROW, TITLE_ROW
from ._utils import WAIVER, as_roman, get_grob, is_waiver, tail

__all__ = [
    "PlotAnnotation",
    "plot_annotation",
    "default_annotation",
    "has_tag",
    "recurse_tags",
    "annotate_table",
    "get_level",
]


@dataclass
class PlotAnnotation:
    """Structured return type of :func:`plot_annotation`."""

    title: Any = field(default=WAIVER)
    subtitle: Any = field(default=WAIVER)
    caption: Any = field(default=WAIVER)
    tag_levels: Any = field(default=WAIVER)
    tag_prefix: Any = field(default=WAIVER)
    tag_suffix: Any = field(default=WAIVER)
    tag_sep: Any = field(default=WAIVER)
    theme: Any = field(default=WAIVER)

    def items(self):  # pragma: no cover — iter helper
        return [
            (k, getattr(self, k))
            for k in (
                "title",
                "subtitle",
                "caption",
                "tag_levels",
                "tag_prefix",
                "tag_suffix",
                "tag_sep",
                "theme",
            )
        ]


def plot_annotation(
    title: Any = WAIVER,
    subtitle: Any = WAIVER,
    caption: Any = WAIVER,
    tag_levels: Any = WAIVER,
    tag_prefix: Any = WAIVER,
    tag_suffix: Any = WAIVER,
    tag_sep: Any = WAIVER,
    theme: Any = WAIVER,
) -> PlotAnnotation:
    """Annotate the final patchwork with title, subtitle, caption, and tags.

    Parameters
    ----------
    title, subtitle, caption : str, optional
        Text strings to use for the respective annotations.
    tag_levels : sequence of str or list, optional
        Enumeration format. Each element is one of ``'a'``, ``'A'``,
        ``'1'``, ``'i'``, ``'I'`` (predefined sequences) or a list of
        custom tag values.
    tag_prefix, tag_suffix, tag_sep : str, optional
        Strings surrounding and separating tag components.
    theme : ggplot2_py.Theme, optional
        Theme applied to the overall composed plot. Only title, margin
        and background elements have an effect.

    Returns
    -------
    PlotAnnotation
        A specification object to be ``+``ed onto a patchwork.
    """
    # Mirror R plot_annotation.R:77 — ``th <- if (is.null(theme)) ggplot2::theme() else theme``.
    from ggplot2_py import theme as _empty_theme

    resolved_theme = _empty_theme() if theme is None else theme

    return PlotAnnotation(
        title=title,
        subtitle=subtitle,
        caption=caption,
        tag_levels=tag_levels,
        tag_prefix=tag_prefix,
        tag_suffix=tag_suffix,
        tag_sep=tag_sep,
        theme=resolved_theme,
    )


#: The default annotation: everything ``None`` with empty tag bits.
default_annotation = PlotAnnotation(
    title=None,
    subtitle=None,
    caption=None,
    tag_levels=[],
    tag_prefix="",
    tag_suffix="",
    tag_sep="",
    theme=None,
)


# -----------------------------------------------------------------------------
# has_tag singledispatch
# -----------------------------------------------------------------------------


@singledispatch
def has_tag(x: Any) -> bool:
    """Return whether *x* should receive a tag during autotagging.

    Default dispatch returns ``False``; concrete types override.
    """
    return False


def _register_has_tag_defaults() -> None:
    """Register default ``has_tag`` implementations.

    Imported lazily via ``patchwork.__init__`` at import time.
    """
    # Local imports because this module is imported early.
    from ggplot2_py import GGPlot
    from ._patch import Patch
    from .guide_area import GuideArea
    from .spacer import Spacer

    @has_tag.register(GGPlot)
    def _(x: GGPlot) -> bool:
        # R: has_tag.inset_patch — an inset plot honours its ``ignore_tag``
        # setting. Inset plots are bare ``GGPlot`` with a ``_ptw_inset_patch``
        # marker (composition over subclassing, §2.1 of the essentials).
        from ._ggplot_attrs import safe_get

        if safe_get(x, "_ptw_inset_patch", False):
            settings = safe_get(x, "inset_settings", {}) or {}
            return not settings.get("ignore_tag", False)
        return True

    @has_tag.register(Spacer)
    def _(x: Spacer) -> bool:  # noqa: F811
        return False

    @has_tag.register(GuideArea)
    def _(x: GuideArea) -> bool:  # noqa: F811
        return False

    from .wrap_elements import WrappedPatch

    @has_tag.register(WrappedPatch)
    def _(x: WrappedPatch) -> bool:  # noqa: F811
        settings = x.get_attr("patch_settings", {})
        return not settings.get("ignore_tag", False)


# -----------------------------------------------------------------------------
# Tag recursion
# -----------------------------------------------------------------------------


def get_level(x: Any) -> Sequence[str]:
    """Expand a ``tag_levels`` element into a concrete sequence of tags.

    Mirrors R's ``get_level``.
    """
    if isinstance(x, list):
        if len(x) == 1 and x[0] in ("a", "A", "1", "i", "I"):
            x = x[0]
        else:
            return list(x[0])
    letters = "abcdefghijklmnopqrstuvwxyz"
    upper = letters.upper()
    mapping = {
        "a": list(letters),
        "A": list(upper),
        "1": [str(n) for n in range(1, 101)],
        "i": [as_roman(n).lower() for n in range(1, 101)],
        "I": [as_roman(n) for n in range(1, 101)],
    }
    if x in mapping:
        return mapping[x]
    raise ValueError(f"Unknown tag type: {x!r}")


def recurse_tags(
    x,
    levels: Sequence,
    prefix: str,
    suffix: str,
    sep: str,
    offset: int = 1,
) -> dict:
    """Walk a patchwork tree and attach ``labs(tag=...)`` calls.

    Returns a ``{"patches": <patchwork>, "tag_ind": <int>}`` dict mirroring R.
    """
    from .add_plot import is_patchwork

    if len(levels) == 0:
        return {"patches": x, "tag_ind": offset}

    level = get_level(levels[0])
    tag_ind = offset
    patches = list(x.patches.plots)

    for i, child in enumerate(patches):
        this_level = "" if len(level) < tag_ind else level[tag_ind - 1]
        if is_patchwork(child):
            from .inset import is_inset_patch

            if is_inset_patch(child) and not has_tag(child):
                continue
            from .layout import default_layout

            child_tag_level = child.patches.layout.tag_level
            if child_tag_level is None:
                child_tag_level = default_layout.tag_level
            if is_waiver(child_tag_level):
                child_tag_level = default_layout.tag_level
            if child_tag_level == "keep":
                new_plots = recurse_tags(child, levels, prefix, suffix, sep, tag_ind)
                patches[i] = new_plots["patches"]
                tag_ind = new_plots["tag_ind"]
            elif len(levels) > 1:
                patches[i] = recurse_tags(
                    child,
                    list(levels[1:]),
                    prefix=f"{prefix}{this_level}{sep}",
                    suffix=suffix,
                    sep=sep,
                )["patches"]
                tag_ind += 1
        elif has_tag(child):
            patches[i] = child + labs(tag=f"{prefix}{this_level}{suffix}")
            tag_ind += 1

    x.patches.plots = patches
    if has_tag(x):
        this_level = "" if len(level) < tag_ind else level[tag_ind - 1]
        x = x + labs(tag=f"{prefix}{this_level}{suffix}")
        tag_ind += 1
    return {"patches": x, "tag_ind": tag_ind}


# -----------------------------------------------------------------------------
# Annotate an assembled gtable
# -----------------------------------------------------------------------------


def annotate_table(table: Gtable, annotation: PlotAnnotation) -> Gtable:
    """Decorate *table* with title / subtitle / caption / background.

    Mirrors R's ``annotate_table``.
    """
    import ggplot2_py as _gg

    # Compose a temporary ggplot whose grob gives us the title heights / style.
    th = annotation.theme if annotation.theme is not None else _gg.theme()
    p = _gg.ggplot() + th + labs(
        title=_resolve(annotation.title),
        subtitle=_resolve(annotation.subtitle),
        caption=_resolve(annotation.caption),
    )
    grob = ggplotGrob(p)
    max_z = max(table.layout["z"])

    # R: ``fix_respect <- is.matrix(table$respect)`` — when set_panel_dimensions
    # produced a per-cell respect matrix, every gtable_add_rows/cols below
    # must grow the matrix in the same direction so its shape stays in sync
    # with the gtable (plot_annotation.R:166-191).
    import numpy as np

    respect = getattr(table, "_respect", None)
    fix_respect = isinstance(respect, np.ndarray) and respect.ndim == 2

    if annotation.title is not None or annotation.subtitle is not None:
        heights_to_prepend = _heights_at(grob, [1, 3, 4])
        table = gtable_add_rows(table, heights_to_prepend, 0)
        if fix_respect:
            table._respect = np.vstack([
                np.zeros((3, table._respect.shape[1]), dtype=table._respect.dtype),
                table._respect,
            ])

        table = gtable_add_grob(
            table,
            get_grob(grob, "title"),
            t=2,
            l=2,
            r=len(table.widths.values) - 1,
            z=max_z + 3,
            name="title",
            clip="off",
        )
        table = gtable_add_grob(
            table,
            get_grob(grob, "subtitle"),
            t=3,
            l=2,
            r=len(table.widths.values) - 1,
            z=max_z + 2,
            name="subtitle",
            clip="off",
        )
    else:
        table = gtable_add_rows(table, _heights_at(grob, [1]), 0)
        if fix_respect:
            table._respect = np.vstack([
                np.zeros((1, table._respect.shape[1]), dtype=table._respect.dtype),
                table._respect,
            ])

    if annotation.caption is not None:
        # R: ``gtable_add_rows(table, tail(p$heights, 3)[-2])`` — take
        # the last three heights then drop the middle (separator between
        # caption and bottom margin), keeping slots 0 and 2. Native
        # subscript carries ``data`` forward automatically (R parity
        # with ``[.unit``).
        keep = _heights_tail(grob, 3)[[0, 2]]
        table = gtable_add_rows(table, keep)
        if fix_respect:
            table._respect = np.vstack([
                table._respect,
                np.zeros((2, table._respect.shape[1]), dtype=table._respect.dtype),
            ])
        table = gtable_add_grob(
            table,
            get_grob(grob, "caption"),
            t=len(table.heights.values) - 1,
            l=2,
            r=len(table.widths.values) - 1,
            z=max_z + 1,
            name="caption",
            clip="off",
        )
    else:
        table = gtable_add_rows(table, _heights_tail(grob, 1))
        if fix_respect:
            table._respect = np.vstack([
                table._respect,
                np.zeros((1, table._respect.shape[1]), dtype=table._respect.dtype),
            ])

    table = gtable_add_cols(table, _widths_at(grob, [1]), 0)
    table = gtable_add_cols(table, _widths_tail(grob, 1))
    if fix_respect:
        table._respect = np.hstack([
            np.zeros((table._respect.shape[0], 1), dtype=table._respect.dtype),
            table._respect,
            np.zeros((table._respect.shape[0], 1), dtype=table._respect.dtype),
        ])
    table = gtable_add_grob(
        table,
        get_grob(grob, "background"),
        t=1,
        l=1,
        b=len(table.heights.values),
        r=len(table.widths.values),
        z=float("-inf"),
        name="background",
    )
    return table


def _resolve(x: Any) -> Optional[str]:
    """Return *x* if it is a real title/subtitle/caption, else None."""
    if x is None or is_waiver(x):
        return None
    return x


def _heights_at(grob: Gtable, indices: Sequence[int]) -> Unit:
    """R: ``grob$heights[indices]`` — 1-based subset, preserves ``data``."""
    return grob.heights[[i - 1 for i in indices]]


def _widths_at(grob: Gtable, indices: Sequence[int]) -> Unit:
    """R: ``grob$widths[indices]`` — 1-based subset, preserves ``data``."""
    return grob.widths[[i - 1 for i in indices]]


def _heights_tail(grob: Gtable, n: int) -> Unit:
    """R: ``tail(grob$heights, n)`` — last *n* entries, preserves ``data``."""
    return grob.heights[-n:]


def _widths_tail(grob: Gtable, n: int) -> Unit:
    """R: ``tail(grob$widths, n)`` — last *n* entries, preserves ``data``."""
    return grob.widths[-n:]
