"""Guide (legend) collection, deduplication, and attachment.

Ports ``R/guides.R``. The most subtle piece is ``unname_grob`` which
canonicalises a grob tree so two visually identical legends compare
equal via structural ``==``.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from ggplot2_py import (
    calc_element,
    element_render,
    find_panel,
    margin,
    theme_get,
)
from grid_py import (
    Unit,
    Viewport,
    absolute_size,
    edit_grob,
    height_details,
    is_unit,
    unit_c,
    valid_just,
    width_details,
)
from gtable_py import (
    Gtable,
    gtable_add_cols,
    gtable_add_grob,
    gtable_add_rows,
    gtable_height,
    gtable_width,
    is_gtable,
)

from ._gtable_state import copy_state, get_attr, set_attr
from ._utils import canonicalize_colour, get_grob

__all__ = [
    "unname_grob",
    "collapse_guides",
    "guides_build",
    "complete_guide_theme",
    "assemble_guides",
    "attach_guides",
    "set_border_sizes",
]


# -----------------------------------------------------------------------------
# unname + grob canonicalisation
# -----------------------------------------------------------------------------


def _canon_units_on(obj: Any) -> Any:
    """Walk the attributes of *obj* and convert any Unit to an absolute-size version."""
    for attr in list(vars(obj).keys() if hasattr(obj, "__dict__") else []):
        v = getattr(obj, attr, None)
        if is_unit(v):
            try:
                setattr(obj, attr, absolute_size(v))
            except AttributeError:
                pass
    return obj


def unname_grob(x: Any) -> Any:
    """Strip identifying names from a grob / gtable tree and canonicalize style.

    Mirrors R's ``unname_grob`` (R/guides.R:21-49). R's ``x$name <- ''``
    semantics work on a local copy because R passes by value; Python
    needs an explicit ``copy.deepcopy`` so the upstream ``collapse_guides``
    list keeps the originals intact (``collapse_guides`` reads
    ``unnamed[i]`` only for structural equality, not as a replacement).
    Without the copy, the *original* legend gtables get their ``name``
    field zeroed, which then breaks downstream draw-time viewport setup.
    """
    if x is None:
        return x
    import copy as _copy
    x = _copy.deepcopy(x)

    if is_gtable(x):
        try:
            x.name = ""
            x.rownames = None
        except AttributeError:
            pass
        if x.vp is not None:
            x.vp = _unname_vp(x.vp)
        new_grobs = []
        for child in x.grobs:
            new_grobs.append(unname_grob(child))
        x.grobs = new_grobs
        _canon_units_on(x)
        _canon_gp(x)
        return x
    # Plain grob
    try:
        x.name = ""
    except AttributeError:
        pass
    try:
        x.vp = _unname_vp(x.vp) if x.vp is not None else None
    except AttributeError:
        pass
    children = getattr(x, "children", None)
    if children is not None:
        try:
            x.children = [unname_grob(c) for c in children]
        except (AttributeError, TypeError):
            pass
    _canon_units_on(x)
    _canon_gp(x)
    return x


def _unname_vp(x: Any) -> Any:
    if x is None:
        return x
    if hasattr(x, "parent"):
        try:
            x.parent = _unname_vp(x.parent)
        except AttributeError:
            pass
    if hasattr(x, "children") and getattr(x, "children", None):
        try:
            x.children = [_unname_vp(c) for c in x.children]
        except (AttributeError, TypeError):
            pass
    try:
        x.name = ""
    except AttributeError:
        pass
    return x


_LINETYPE_NUMERIC = {
    0: "blank",
    1: "solid",
    2: "dashed",
    3: "dotted",
    4: "dotdash",
    5: "longdash",
    6: "twodash",
}
_LINETYPE_HEX_MAP = {
    "44": "dashed",
    "13": "dotted",
    "1343": "dotdash",
    "73": "longdash",
    "2262": "twodash",
}


def _canon_gp(grob: Any) -> None:
    gp = getattr(grob, "gp", None)
    if gp is None:
        return
    col = getattr(gp, "col", None)
    if isinstance(col, str):
        gp.col = canonicalize_colour(col)
    fill = getattr(gp, "fill", None)
    if isinstance(fill, str):
        gp.fill = canonicalize_colour(fill)
    lty = getattr(gp, "lty", None)
    if isinstance(lty, (int, float)):
        gp.lty = _LINETYPE_NUMERIC.get(int(lty) + 1, "solid")
    elif isinstance(lty, str):
        gp.lty = _LINETYPE_HEX_MAP.get(lty, lty)


def collapse_guides(guides: Sequence[Any]) -> list[Any]:
    """Remove duplicates from *guides* by structural equality after ``unname_grob``."""
    guides = list(guides)
    unnamed: list[Any] = [unname_grob(g) for g in guides]
    # Walk pairs; drop a guide if an earlier guide is structurally equal.
    to_keep = [True] * len(guides)
    for i in range(len(unnamed) - 1, -1, -1):
        for j in range(i):
            if not to_keep[j]:
                continue
            if _struct_eq(unnamed[i], unnamed[j]):
                to_keep[i] = False
                break
    return [g for g, keep in zip(guides, to_keep) if keep]


def _struct_eq(a: Any, b: Any) -> bool:
    """Structural equality: compares publicly-visible attrs recursively."""
    if a is b:
        return True
    if type(a) is not type(b):
        return False
    a_dict = getattr(a, "__dict__", None)
    b_dict = getattr(b, "__dict__", None)
    if a_dict is None and b_dict is None:
        return a == b
    if a_dict is None or b_dict is None:
        return False
    keys = set(a_dict) | set(b_dict)
    for k in keys:
        if k.startswith("_"):
            continue
        if not _struct_eq(a_dict.get(k), b_dict.get(k)):
            return False
    return True


# -----------------------------------------------------------------------------
# Assemble the guide box
# -----------------------------------------------------------------------------


def guides_build(guides: Sequence[Any], theme) -> Gtable:
    """Build a guide-box gtable from a sequence of guide grobs.

    Ports ``R/guides.R::guides_build``.
    """
    legend_spacing_y = calc_element("legend.spacing.y", theme) or Unit([0], ["mm"])
    legend_spacing_x = calc_element("legend.spacing.x", theme) or Unit([0], ["mm"])
    legend_box_margin = calc_element("legend.box.margin", theme) or margin()

    widths = _unit_c(*(gtable_width(g) for g in guides))
    heights = _unit_c(*(gtable_height(g) for g in guides))

    # R: ``Guides$package_box`` (guides-.R:603-607) defaults
    # ``legend.box.just`` based on direction when the theme element is
    # missing. ``vertical`` → ``c("left", "top")``;
    # ``horizontal`` → ``c("center", "top")``.
    box_layout = calc_element("legend.box", theme)
    vert = box_layout == "horizontal"
    box_just_raw = calc_element("legend.box.just", theme)
    if box_just_raw is None:
        box_just_raw = ("center", "top") if vert else ("left", "top")
    just = valid_just(box_just_raw)
    xjust = just[0]
    yjust = just[1]

    new_guides = []
    for g in guides:
        vp = Viewport(
            x=xjust,
            y=yjust,
            just=(xjust, yjust),
            height=height_details(g) if vert else Unit([1], ["npc"]),
            width=width_details(g) if not vert else Unit([1], ["npc"]),
        )
        new_guides.append(edit_grob(g, vp=vp))

    n = len(new_guides)
    if n == 0:
        return Gtable(widths=Unit([0], ["mm"]), heights=Unit([0], ["mm"]), name="guide-box")

    if vert:
        heights = _unit_max(heights)
        if len(widths.values) != 1:
            widths = _interleave_widths(widths, legend_spacing_x)
    else:
        widths = _unit_max(widths)
        if len(heights.values) != 1:
            heights = _interleave_heights(heights, legend_spacing_y)

    widths = _unit_c(_margin_side(legend_box_margin, 3), widths, _margin_side(legend_box_margin, 1))
    heights = _unit_c(_margin_side(legend_box_margin, 0), heights, _margin_side(legend_box_margin, 2))

    box = Gtable(widths=widths, heights=heights, name="guide-box")
    if vert:
        t_positions = [2] * n
        l_positions = [1 + 2 * i + 1 for i in range(n)]
    else:
        t_positions = [1 + 2 * i + 1 for i in range(n)]
        l_positions = [2] * n
    box = gtable_add_grob(
        box,
        new_guides,
        t=t_positions,
        l=l_positions,
        name="guides",
    )

    bg = element_render(theme, "legend.box.background")
    if bg is not None:
        box = gtable_add_grob(
            box,
            bg,
            t=1,
            l=1,
            b=len(box.heights.values),
            r=len(box.widths.values),
            z=float("-inf"),
            clip="off",
            name="legend.box.background",
        )
    return box


def _unit_c(*parts: Unit) -> Unit:
    parts = [p for p in parts if p is not None]
    if not parts:
        return Unit([0], ["mm"])
    return unit_c(*parts)


def _unit_max(u: Unit) -> Unit:
    """Return a 1-element Unit that is the pmax of *u*.

    Max is an aggregation over raw numeric values, which is only
    meaningful for absolute same-kind units; R's ``unit.pmax`` enforces
    this. For the mixed-unit fallback we return the first entry via
    native ``u[0:1]`` so its grob reference in ``data`` is preserved.
    """
    if len(u.values) <= 1:
        return u
    uniq_units = set(u.units_list)
    if len(uniq_units) == 1:
        return Unit([max(u.values)], [u.units_list[0]])
    return u[0:1]


def _interleave_widths(widths: Unit, sep: Unit) -> Unit:
    """R: interleave a widths vector with a separator at every other slot.

    Built via native :func:`grid_py.unit_c`, which carries each input's
    ``data`` through the concatenation. Equivalent to R's
    ``unit.c(rbind(widths, sep)[, -ncol])``.
    """
    if len(widths) == 0:
        return widths
    parts: list[Unit] = [widths[0:1]]
    for i in range(1, len(widths)):
        parts.append(sep)
        parts.append(widths[i:i + 1])
    return unit_c(*parts)


def _interleave_heights(heights: Unit, sep: Unit) -> Unit:
    return _interleave_widths(heights, sep)


def _margin_side(m: Any, index: int) -> Unit:
    """Extract a Unit out of a ``margin()`` object by index (0=top, 1=right, 2=bottom, 3=left)."""
    order = ["t", "r", "b", "l"]
    key = order[index]
    v = getattr(m, key, None)
    if v is None:
        v = m[index] if isinstance(m, (list, tuple)) else 0
    if is_unit(v):
        return v
    return Unit([float(v)], ["pt"])


def complete_guide_theme(guide_pos: str, theme):
    """Fill in sensible defaults on *theme* for a given guide position."""
    import ggplot2_py as _gg

    if guide_pos in ("top", "bottom"):
        box = getattr(theme, "legend.box", None) or "horizontal"
        direction = getattr(theme, "legend.direction", None) or "horizontal"
        just = getattr(theme, "legend.box.just", None) or ("center", "top")
    else:
        box = getattr(theme, "legend.box", None) or "vertical"
        direction = getattr(theme, "legend.direction", None) or "vertical"
        just = getattr(theme, "legend.box.just", None) or ("left", "top")

    try:
        setattr(theme, "legend.box", box)
        setattr(theme, "legend.direction", direction)
        setattr(theme, "legend.box.just", just)
    except AttributeError:
        pass
    return theme


def assemble_guides(guides: Sequence[Any], position: str, theme) -> Gtable:
    """Produce a single ``guide-box`` gtable at *position*."""
    theme = complete_guide_theme(position, theme)
    box = guides_build(guides, theme)
    just = valid_just(calc_element("legend.justification", theme))
    vp = Viewport(x=just[0], y=just[1], just=(just[0], just[1]))
    box = edit_grob(box, vp=vp)
    box = gtable_add_rows(box, Unit([just[1]], ["null"]))
    box = gtable_add_rows(box, Unit([1 - just[1]], ["null"]), 0)
    box = gtable_add_cols(box, Unit([just[0]], ["null"]), 0)
    box = gtable_add_cols(box, Unit([1 - just[0]], ["null"]))
    return box


def attach_guides(
    table: Gtable, guides: Gtable, position: str, theme
) -> Gtable:
    """Insert *guides* into *table* at *position* ('left','right','top','bottom')."""
    guide_areas = [
        i for i, n in enumerate(table.layout["name"]) if "panel-guide_area" in n
    ]
    if guide_areas:
        area_ind = guide_areas[0]
        table.grobs[area_ind] = guides
        return table
    p_loc = find_panel(table)
    spacing = calc_element("legend.box.spacing", theme) or Unit([0.2], ["cm"])
    legend_width = gtable_width(guides)
    legend_height = gtable_height(guides)

    if position == "left":
        table = gtable_add_grob(
            table, guides, clip="off", t=p_loc["t"], l=p_loc["l"] - 5,
            b=p_loc["b"], name="guide-box",
        )
        new_left = unit_c(
            _slice_unit(table.widths, range(p_loc["l"] - 6)), legend_width, spacing
        )
        table = set_border_sizes(table, l=new_left)
    elif position == "right":
        table = gtable_add_grob(
            table, guides, clip="off", t=p_loc["t"], l=p_loc["r"] + 5,
            b=p_loc["b"], name="guide-box",
        )
        new_right = unit_c(
            spacing, legend_width,
            _slice_unit(table.widths, range(p_loc["r"] + 5, len(table.widths.values))),
        )
        table = set_border_sizes(table, r=new_right)
    elif position == "bottom":
        table = gtable_add_grob(
            table, guides, clip="off", t=p_loc["b"] + 5, l=p_loc["l"],
            r=p_loc["r"], name="guide-box",
        )
        new_bottom = unit_c(
            spacing, legend_height,
            _slice_unit(table.heights, range(p_loc["b"] + 5, len(table.heights.values))),
        )
        table = set_border_sizes(table, b=new_bottom)
    elif position == "top":
        table = gtable_add_grob(
            table, guides, clip="off", t=p_loc["t"] - 5, l=p_loc["l"],
            r=p_loc["r"], name="guide-box",
        )
        new_top = unit_c(
            _slice_unit(table.heights, range(p_loc["t"] - 6)), legend_height, spacing
        )
        table = set_border_sizes(table, t=new_top)
    return table


def _slice_unit(u: Unit, idx_range) -> Unit:
    """R: ``u[indices]`` — index a Unit with a list of 0-based positions.

    Native :py:meth:`grid_py.Unit.__getitem__` preserves the per-entry
    ``data`` array (the grob references that lazy ``grobwidth`` /
    ``grobheight`` / compound ``sum`` units rely on at draw time).
    Building a fresh ``Unit(values, units)`` from list-of-values would
    drop those references and silently collapse the entry to 0 mm.
    """
    indices = list(idx_range)
    if not indices:
        return Unit([0], ["mm"])
    return u[indices]


def set_border_sizes(
    gt: Gtable,
    l: Optional[Unit] = None,
    r: Optional[Unit] = None,
    t: Optional[Unit] = None,
    b: Optional[Unit] = None,
) -> Gtable:
    """Overwrite border widths/heights of a gtable tree.

    Port of R's ``set_border_sizes``. R writes ``gt$widths[1:n] <- new``
    via ``[<-.unit`` (unit.R:454) which preserves the right-hand side
    Unit's ``data`` (grob refs for lazy units).  Mirror that by
    delegating to :py:meth:`grid_py.Unit.__setitem__` instead of
    rebuilding the full Unit from a values/units list (which would drop
    ``data`` entries).
    """
    if l is None and r is None and t is None and b is None:
        return gt
    from ._gtable_state import has_class

    widths = gt.widths.copy()
    if l is not None:
        for i in range(len(l)):
            widths[i] = l[i:i + 1]
    if r is not None:
        offset = len(widths) - len(r)
        for i in range(len(r)):
            widths[offset + i] = r[i:i + 1]
    gt.widths = widths

    heights = gt.heights.copy()
    if t is not None:
        for i in range(len(t)):
            heights[i] = t[i:i + 1]
    if b is not None:
        offset = len(heights) - len(b)
        for i in range(len(b)):
            heights[offset + i] = b[i:i + 1]
    gt.heights = heights

    # Recurse into nested patchwork gtables.
    for i, grob in enumerate(gt.grobs):
        if not is_gtable(grob):
            continue
        if not has_class(grob, "gtable_patchwork"):
            continue
        gt.grobs[i] = set_border_sizes(
            grob,
            l=l if gt.layout["l"][i] == 1 else None,
            r=r if gt.layout["r"][i] == len(gt.widths.values) else None,
            t=t if gt.layout["t"][i] == 1 else None,
            b=b if gt.layout["b"][i] == len(gt.heights.values) else None,
        )
    return gt
