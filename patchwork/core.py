"""Rendering core — ``patchworkGrob``, ``plot_table``, ``simplify_gt``,
``build_patchwork``, and all their helpers.

Ports ``R/plot_patchwork.R``. This is the largest module; functions are
grouped top-down (entrypoints first, helpers last) matching the R source
as closely as we can.
"""

from __future__ import annotations

from functools import singledispatch
from typing import Any, List, Optional, Sequence

from ggplot2_py import (
    GGPlot,
    find_panel,
    ggplotGrob,
    is_ggplot,
    is_theme,
    set_last_plot,
    theme_get,
    wrap_dims,
)
from grid_py import Unit, Viewport, convert_height, convert_width, is_unit, unit_c
from gtable_py import (
    Gtable,
    gtable_add_cols,
    gtable_add_grob,
    gtable_add_rows,
    is_gtable,
)

from ._constants import (
    PANEL_COL,
    PANEL_ROW,
    PLOT_BOTTOM,
    PLOT_LEFT,
    PLOT_RIGHT,
    PLOT_TOP,
    TABLE_COLS,
    TABLE_ROWS,
)
from ._gtable_state import (
    add_class,
    copy_state,
    get_attr,
    has_class,
    remove_class,
    set_attr,
)
from ._patch import Patch, patch_grob, patch_table
from ._utils import is_abs_unit, is_waiver, modify_list, zero_grob

__all__ = [
    "plot_table",
    "simplify_gt",
    "build_patchwork",
    "patchworkGrob",
    "patchwork_grob",
    "add_strips",
    "add_guides",
    "add_insets",
    "set_panel_dimensions",
    "table_dims",
    "set_grob_sizes",
    "set_border_sizes",
    "create_design",
]


# --- lazy re-exports to break cycles ---------------------------------------


def _collect_axes(*args, **kwargs):
    from .collect_axes import collect_axes

    return collect_axes(*args, **kwargs)


def _collect_axis_titles(*args, **kwargs):
    from .collect_axes import collect_axis_titles

    return collect_axis_titles(*args, **kwargs)


def _create_design(*args, **kwargs):
    from .layout import create_design

    return create_design(*args, **kwargs)


def _default_layout():
    from .layout import default_layout

    return default_layout


# -----------------------------------------------------------------------------
# plot_table singledispatch
# -----------------------------------------------------------------------------


@singledispatch
def plot_table(x: Any, guides: str = "auto") -> Gtable:
    """Convert *x* to a gtable with patchwork-friendly border slots.

    Parameters
    ----------
    x : object
        Dispatch key. Registered types: ``ggplot2_py.GGPlot`` (with
        special-case routing for inset-marked and free-plot-marked
        plots), :class:`Patch`, :class:`Patchwork`.
    guides : {'auto', 'collect', 'keep'}, default 'auto'
        Passed down to the dispatched handler.

    Returns
    -------
    gtable_py.Gtable
        A padded, strip/guide-annotated gtable ready for composition.

    Raises
    ------
    TypeError
        If *x* has no registered handler.
    """
    raise TypeError(f"No `plot_table` method for object of type {type(x).__name__}")


def _apply_fixed_dim_margins(gt: Gtable, plot: GGPlot) -> Gtable:
    """Override outer margins of *gt* with *plot*'s stored fixed dimensions.

    Port of R's ``ggplot_gtable.fixed_dim_build`` side effect
    (plot_multipage.R:116-127). When ``set_dim`` has tagged *plot* with
    a ``PlotDimension``, replace the widths left of and right of the
    panel column and the heights above and below the panel row with the
    captured mm values. Acts as a no-op when *plot* carries no such tag,
    which is the common case.
    """
    from ._ggplot_attrs import safe_get

    if not safe_get(plot, "_ptw_fixed_dim", False):
        return gt
    dim = safe_get(plot, "fixed_dimensions", None)
    if dim is None:
        return gt

    panel_pos = find_panel(gt)
    n_w = len(gt.widths.values)
    n_h = len(gt.heights.values)
    widths_vals = list(gt.widths.values)
    widths_units = list(gt.widths.units_list)
    heights_vals = list(gt.heights.values)
    heights_units = list(gt.heights.units_list)
    for i in range(panel_pos["l"] - 1):
        if i < len(dim.l):
            widths_vals[i] = float(dim.l[i])
            widths_units[i] = "mm"
    for k, i in enumerate(range(panel_pos["r"], n_w)):
        if k < len(dim.r):
            widths_vals[i] = float(dim.r[k])
            widths_units[i] = "mm"
    for i in range(panel_pos["t"] - 1):
        if i < len(dim.t):
            heights_vals[i] = float(dim.t[i])
            heights_units[i] = "mm"
    for k, i in enumerate(range(panel_pos["b"], n_h)):
        if k < len(dim.b):
            heights_vals[i] = float(dim.b[k])
            heights_units[i] = "mm"
    gt.widths = Unit(widths_vals, widths_units)
    gt.heights = Unit(heights_vals, heights_units)
    return gt


@plot_table.register(GGPlot)
def _(x: GGPlot, guides: str = "auto") -> Gtable:
    gt = ggplotGrob(x)
    gt = add_strips(gt)
    gt = add_guides(gt, collect=(guides == "collect"))
    gt = _pad_to_canonical(gt)
    gt = _apply_fixed_dim_margins(gt, x)
    return gt


@plot_table.register(Patch)
def _(x: Patch, guides: str = "auto") -> Gtable:  # noqa: F811
    # R's ``plot_table.inset_patch`` takes precedence over ``plot_table.patch``
    # via S3's class-vector dispatch. In Python we simulate it by checking
    # for the inset marker on any Patch input and routing accordingly.
    from .inset import is_inset_patch

    if is_inset_patch(x):
        return plot_table_inset_patch(x, guides)
    return patch_grob(x, guides)


def _register_plot_table_patchwork() -> None:
    """Register patchwork-specific ``plot_table`` handlers."""
    from .add_plot import Patchwork, get_patches
    from .free import is_free_plot
    from .inset import is_inset_patch

    @plot_table.register(Patchwork)
    def _(x: Patchwork, guides: str = "auto") -> Gtable:  # noqa: F811
        if is_free_plot(x.plot) or getattr(x, "_ptw_free_plot", False):
            return plot_table_free_plot(x, guides)
        return build_patchwork(get_patches(x), guides)

    # Inset and free handling operate on a ggplot carrying marker attrs.
    @plot_table.register(GGPlot)
    def _(x: GGPlot, guides: str = "auto") -> Gtable:  # noqa: F811
        if is_inset_patch(x):
            return plot_table_inset_patch(x, guides)
        if is_free_plot(x):
            return plot_table_free_plot(x, guides)
        gt = ggplotGrob(x)
        gt = add_strips(gt)
        gt = add_guides(gt, collect=(guides == "collect"))
        gt = _pad_to_canonical(gt)
        gt = _apply_fixed_dim_margins(gt, x)
        return gt


def plot_table_inset_patch(x: GGPlot, guides: str = "auto") -> Gtable:
    """Render a ggplot carrying inset settings."""
    from ._ggplot_attrs import safe_delete, safe_get, safe_set

    settings = safe_get(x, "inset_settings", {})
    left = settings["left"]
    bottom = settings["bottom"]
    right = settings["right"]
    top = settings["top"]
    # Strip markers so the regular plot_table branch handles rendering.
    safe_delete(x, "_ptw_inset_patch")
    gt = plot_table(x, guides)
    safe_set(x, "_ptw_inset_patch", True)
    width = Unit([right.values[0] - left.values[0]], [right.units_list[0]])
    height = Unit([top.values[0] - bottom.values[0]], [top.units_list[0]])
    gt.vp = Viewport(x=left, y=bottom, width=width, height=height, just=(0, 0))
    set_attr(gt, "inset_settings", settings)
    add_class(gt, "inset_table")
    return gt


def plot_table_free_plot(x: Any, guides: str = "auto") -> Gtable:
    """Render a free plot (ggplot or patchwork carrying ``free_settings``)."""
    from .add_plot import Patchwork, get_patches

    from ._ggplot_attrs import safe_get, safe_set

    if isinstance(x, Patchwork):
        settings = safe_get(x, "patchwork_free_settings", {})
        table = build_patchwork(get_patches(x), guides)
    else:
        settings = safe_get(x, "free_settings", {})
        safe_set(x, "_ptw_free_plot", False)
        table = plot_table(x, guides)
    set_attr(table, "free_settings", settings)
    add_class(table, "free_table")
    return table


# -----------------------------------------------------------------------------
# simplify_gt singledispatch
# -----------------------------------------------------------------------------


@singledispatch
def simplify_gt(gt: Any) -> Gtable:
    """Compact a gtable into a form appropriate for composition.

    Parameters
    ----------
    gt : object
        Dispatch key. Registered for ``gtable_py.Gtable``; branches on the
        private ``_ptw_class`` tag to handle the R-side specialisations
        (``gtable_patchwork``, ``gtable_patchwork_simple``, ``patchgrob``,
        ``inset_table``, ``free_table``).

    Returns
    -------
    gtable_py.Gtable
        A gtable where panels have been collapsed into single cells
        (or left intact for opaque/inset/free cases).

    Raises
    ------
    TypeError
        If *gt* has no registered handler.
    """
    raise TypeError(f"No `simplify_gt` method for object of type {type(gt).__name__}")


@simplify_gt.register(Gtable)
def _(gt: Gtable) -> Gtable:
    # Dispatch on our private class-tag set.
    if has_class(gt, "gtable_patchwork"):
        return _simplify_gtable_patchwork(gt)
    if has_class(gt, "patchgrob"):
        return gt
    if has_class(gt, "inset_table"):
        return gt
    if has_class(gt, "free_table"):
        return _simplify_free_table(gt)
    return _simplify_plain_gtable(gt)


def _simplify_plain_gtable(gt: Gtable) -> Gtable:
    guides = get_attr(gt, "collected_guides", None)
    try:
        delattr(gt, "collected_guides")
    except AttributeError:
        pass

    panel_pos = find_panel(gt)
    rows = (panel_pos["t"], panel_pos["b"])
    cols = (panel_pos["l"], panel_pos["r"])
    if (
        not gt.respect
        and rows[0] == rows[1]
        and cols[0] == cols[1]
        and not any(n.startswith("strip-") for n in gt.layout["name"])
    ):
        gt.widths = convert_width(gt.widths, "mm")
        gt.heights = convert_height(gt.heights, "mm")
        set_attr(gt, "collected_guides", guides)
        return gt

    p_rows = list(range(rows[0], rows[1] + 1))
    p_cols = list(range(cols[0], cols[1] + 1))
    # ``Gtable.__getitem__`` slices with Python's 0-based / half-open
    # convention, but ``p_rows`` / ``p_cols`` carry R's 1-based positions
    # (panel_pos comes from ``find_panel`` which mirrors R layout$t etc.).
    # Convert: 1-based inclusive [start..end] → 0-based half-open
    # [start-1, end). For p4 (facet_wrap, panel cols 7..15) the prior
    # off-by-one made ``panels`` slice cols 8..16 (and miss row 10),
    # producing an empty inner gtable that erased every facet panel
    # when ``_simplify_free`` re-added it as the merged ``panel; ...``
    # cell.
    panels = gt[p_rows[0] - 1:p_rows[-1], p_cols[0] - 1:p_cols[-1]]
    keep_rows = [r for r in range(1, len(gt.heights.values) + 1) if r not in p_rows]
    keep_cols = [c for c in range(1, len(gt.widths.values) + 1) if c not in p_cols]

    gt_new = _slice_gtable(gt, keep_rows, keep_cols)
    gt_new.widths = convert_width(
        _unit_at(gt.widths, [i - 1 for i in keep_cols]), "mm"
    )
    new_width = _collapse_dim(gt.widths, p_cols, "width")
    gt_new.heights = convert_height(
        _unit_at(gt.heights, [i - 1 for i in keep_rows]), "mm"
    )
    new_height = _collapse_dim(gt.heights, p_rows, "height")

    gt_new = gtable_add_rows(gt_new, new_height, rows[0] - 1)
    gt_new = gtable_add_cols(gt_new, new_width, cols[0] - 1)
    if gt.respect:
        gt_new = _simplify_fixed(gt, gt_new, panels, rows, cols)
    else:
        gt_new = _simplify_free(gt, gt_new, panels, rows, cols)
    set_attr(gt_new, "collected_guides", guides)
    return gt_new


def _simplify_gtable_patchwork(gt: Gtable) -> Gtable:
    """Compact a nested patchwork gtable into a 'simple' wrapper."""
    guides = get_attr(gt, "collected_guides", None)
    try:
        delattr(gt, "collected_guides")
    except AttributeError:
        pass

    panel_pos = find_panel(gt)
    p_cols = range(panel_pos["l"], panel_pos["r"] + 1)
    p_rows = range(panel_pos["t"], panel_pos["b"] + 1)
    widths_range = _unit_at(gt.widths, [i - 1 for i in p_cols])
    heights_range = _unit_at(gt.heights, [i - 1 for i in p_rows])

    if is_abs_unit(widths_range):
        new_width = _sum_unit(convert_width(widths_range, "mm"))
    else:
        new_width = Unit([1], ["null"])
    if is_abs_unit(heights_range):
        new_height = _sum_unit(convert_height(heights_range, "mm"))
    else:
        new_height = Unit([1], ["null"])

    prefix_w = _unit_at(gt.widths, list(range(panel_pos["l"] - 1)))
    suffix_w = _unit_at(gt.widths, list(range(panel_pos["r"], len(gt.widths.values))))
    widths = _concat_unit(prefix_w, new_width, suffix_w)

    prefix_h = _unit_at(gt.heights, list(range(panel_pos["t"] - 1)))
    suffix_h = _unit_at(gt.heights, list(range(panel_pos["b"], len(gt.heights.values))))
    heights = _concat_unit(prefix_h, new_height, suffix_h)

    gt_new = Gtable(widths=widths, heights=heights)
    gt_new = gtable_add_grob(
        gt_new, zero_grob(),
        t=PANEL_ROW, l=PANEL_COL, name="panel-nested-patchwork",
    )
    gt_new = gtable_add_grob(
        gt_new, gt,
        t=1, l=1, b=len(gt_new.heights.values), r=len(gt_new.widths.values),
        clip="off", name="patchwork-table",
    )
    add_class(gt_new, "gtable_patchwork_simple")
    set_attr(gt_new, "collected_guides", guides)
    return gt_new


def _simplify_free_table(gt: Gtable) -> Gtable:
    """Apply free-plot side adjustments on top of the plain ``simplify_gt`` result."""
    settings = get_attr(gt, "free_settings", {}) or {}
    # Strip class tag so the next call uses the plain gtable path.
    remove_class(gt, "free_table")
    gt_new = _simplify_plain_gtable(gt)
    split: dict[str, list[str]] = {}
    for side, mode in settings.items():
        split.setdefault(mode, []).append(side)

    if "label" in split:
        mask = [s in split["label"] for s in "trbl"]
        gt_new = _free_label(gt_new, mask)
    if "space" in split:
        mask = [s in split["space"] for s in "trbl"]
        gt_new = _free_space(gt_new, mask)
    if "panel" in split:
        mask = [s in split["panel"] for s in "trbl"]
        gt_new = _free_panel(gt_new, mask)
    return gt_new


# -----------------------------------------------------------------------------
# build_patchwork
# -----------------------------------------------------------------------------


def build_patchwork(x: Any, guides: str = "auto") -> Gtable:
    """Top-level render: convert a :class:`Patches` holder to a composed gtable.

    Parameters
    ----------
    x : Patches
        The patchwork content (plots + layout + annotation) to render.
    guides : {'auto', 'collect', 'keep'}, default 'auto'
        Governs whether guides propagate up to this composition level.

    Returns
    -------
    gtable_py.Gtable
        Composed gtable (tagged ``gtable_patchwork``) ready for the
        outer :func:`patchworkGrob` to annotate with titles / caption /
        background.
    """
    layout = modify_list(
        {k: getattr(_default_layout(), k) for k in vars(_default_layout())},
        {k: v for k, v in vars(x.layout).items() if v is not None},
    )
    # Compose a PlotLayout from the merged dict (dataclass assignment).
    for k, v in layout.items():
        setattr(x.layout, k, v)

    computed_guides = (
        "collect"
        if guides == "collect" and x.layout.guides != "keep"
        else x.layout.guides
    )
    gt_list: List[Gtable] = []
    guide_grobs: List[Any] = []
    for plot in x.plots:
        gt = plot_table(plot, computed_guides)
        gt_list.append(gt)
        extra_guides = get_attr(gt, "collected_guides", None)
        if extra_guides:
            guide_grobs.extend(extra_guides)

    gt_list = [simplify_gt(g) for g in gt_list]
    gt_list = add_insets(gt_list)
    fixed_asp = [bool(g.respect) if not isinstance(g.respect, bool) or g.respect is True else False for g in gt_list]

    if x.layout.design is None:
        ncol = x.layout.ncol
        nrow = x.layout.nrow
        if ncol is None and x.layout.widths is not None and hasattr(x.layout.widths, "__len__"):
            if len(x.layout.widths) > 1:
                ncol = len(x.layout.widths)
        if nrow is None and x.layout.heights is not None and hasattr(x.layout.heights, "__len__"):
            if len(x.layout.heights) > 1:
                nrow = len(x.layout.heights)
        dims = wrap_dims(len(gt_list), nrow=nrow, ncol=ncol)
        x.layout.design = _create_design(dims[1], dims[0], bool(x.layout.byrow))
    else:
        dims = (max(x.layout.design.b), max(x.layout.design.r))

    nrow_cells = dims[0]
    ncol_cells = dims[1]

    gt_new = Gtable(
        widths=Unit([0.0] * (TABLE_COLS * ncol_cells), ["null"] * (TABLE_COLS * ncol_cells)),
        heights=Unit([0.0] * (TABLE_ROWS * nrow_cells), ["null"] * (TABLE_ROWS * nrow_cells)),
    )

    design_records = x.layout.design.as_records()
    if len(design_records) < len(gt_list):
        import warnings

        warnings.warn("Too few patch areas to hold all plots. Dropping plots", stacklevel=2)
        gt_list = gt_list[: len(design_records)]
        fixed_asp = fixed_asp[: len(design_records)]
    else:
        design_records = design_records[: len(gt_list)]

    for rec in design_records:
        if rec["t"] < 1:
            rec["t"] = 1
        if rec["l"] < 1:
            rec["l"] = 1
        if rec["b"] > dims[0]:
            rec["b"] = dims[0]
        if rec["r"] > dims[1]:
            rec["r"] = dims[1]

    max_z_per_gt = [max(g.layout["z"]) if g.layout["z"] else 0 for g in gt_list]
    cumulative = [0]
    for mz in max_z_per_gt:
        cumulative.append(cumulative[-1] + mz)

    new_layout_accum = {k: [] for k in ("t", "l", "b", "r", "z", "clip", "name")}
    for i, (gt, rec) in enumerate(zip(gt_list, design_records)):
        lay = gt.layout
        for k in new_layout_accum:
            new_layout_accum[k].extend(list(lay[k]))
        # Shift z by cumulative offset, except for the background row.
        length = len(lay["name"])
        for j in range(length):
            idx_j = len(new_layout_accum["z"]) - length + j
            if lay["name"][j] != "background":
                new_layout_accum["z"][idx_j] = lay["z"][j] + cumulative[i]
            new_layout_accum["t"][idx_j] = lay["t"][j] + (
                (rec["t"] - 1) * TABLE_ROWS if lay["t"][j] <= PANEL_ROW else (rec["b"] - 1) * TABLE_ROWS
            )
            new_layout_accum["l"][idx_j] = lay["l"][j] + (
                (rec["l"] - 1) * TABLE_COLS if lay["l"][j] <= PANEL_COL else (rec["r"] - 1) * TABLE_COLS
            )
            new_layout_accum["b"][idx_j] = lay["b"][j] + (
                (rec["t"] - 1) * TABLE_ROWS if lay["b"][j] < PANEL_ROW else (rec["b"] - 1) * TABLE_ROWS
            )
            new_layout_accum["r"][idx_j] = lay["r"][j] + (
                (rec["l"] - 1) * TABLE_COLS if lay["r"][j] < PANEL_COL else (rec["r"] - 1) * TABLE_COLS
            )
            new_layout_accum["name"][idx_j] = f"{lay['name'][j]}-{i + 1}"

    gt_new.layout = new_layout_accum
    gt_new.grobs = [g for gt in gt_list for g in gt.grobs]

    tdims = table_dims(
        [g.widths for g in gt_list],
        [g.heights for g in gt_list],
        design_records,
        ncol_cells,
        nrow_cells,
    )
    gt_new.widths = tdims["widths"]
    gt_new.heights = tdims["heights"]

    layout_widths = x.layout.widths
    layout_heights = x.layout.heights
    from ._utils import rep_len as _rep_len

    if layout_widths is not None and not is_waiver(layout_widths):
        widths = _rep_len(_as_sequence(layout_widths), ncol_cells)
    else:
        widths = [float("nan")] * ncol_cells
    if layout_heights is not None and not is_waiver(layout_heights):
        heights = _rep_len(_as_sequence(layout_heights), nrow_cells)
    else:
        heights = [float("nan")] * nrow_cells

    gt_new = set_panel_dimensions(gt_new, gt_list, widths, heights, fixed_asp, design_records)

    if x.layout.guides == "collect":
        from .guides import (
            attach_guides,
            assemble_guides,
            collapse_guides,
        )

        collapsed = collapse_guides(guide_grobs)
        if collapsed:
            theme = x.annotation.theme
            complete = bool(getattr(theme, "complete", False)) if theme is not None else False
            if not complete:
                base = theme_get()
                theme = base + theme if theme is not None else base
            position = getattr(theme, "legend.position", None) or "right"
            if isinstance(position, (list, tuple)) and len(position) == 2:
                import warnings

                warnings.warn(
                    "Manual legend position not possible for collected guides. Defaulting to 'right'",
                    stacklevel=2,
                )
                position = "right"
            guide_grobs = assemble_guides(collapsed, position, theme)
            gt_new = attach_guides(gt_new, guide_grobs, position, theme)
    else:
        set_attr(gt_new, "collected_guides", guide_grobs)

    axes = x.layout.axes or _default_layout().axes
    if axes in ("collect", "collect_x"):
        gt_new = _collect_axes(gt_new, "x")
    if axes in ("collect", "collect_y"):
        gt_new = _collect_axes(gt_new, "y")

    titles = x.layout.axis_titles or _default_layout().axis_titles
    if titles in ("collect", "collect_x"):
        gt_new = _collect_axis_titles(gt_new, "x", merge=True)
    if titles in ("collect", "collect_y"):
        gt_new = _collect_axis_titles(gt_new, "y", merge=True)

    gt_new = gtable_add_grob(
        gt_new,
        zero_grob(),
        t=PANEL_ROW,
        l=PANEL_COL,
        b=PANEL_ROW + TABLE_ROWS * (nrow_cells - 1),
        r=PANEL_COL + TABLE_COLS * (ncol_cells - 1),
        z=-1,
        name="panel-area",
    )
    add_class(gt_new, "gtable_patchwork")
    return gt_new


def _as_sequence(x):
    """Normalise ``x`` for length-based recycling.

    Mirrors R's implicit treatment of ``unit`` vectors as element-iterable
    sequences. A bare :class:`grid_py.Unit` is exploded into a list of
    single-entry Units so :func:`rep_len` can recycle entries individually
    (matching R's ``rep_len(unit(...))`` which preserves per-entry units).
    """
    if isinstance(x, Unit):
        return [x[i:i + 1] for i in range(len(x))]
    if isinstance(x, (list, tuple)):
        return list(x)
    return [x]


# -----------------------------------------------------------------------------
# public entrypoints
# -----------------------------------------------------------------------------


def patchworkGrob(x: Any) -> Gtable:
    """Assemble the composed gtable (the Python analogue of R's ``patchworkGrob``).

    Parameters
    ----------
    x : Patchwork

    Returns
    -------
    gtable_py.Gtable
        The final, annotated gtable ready to draw.
    """
    from .add_plot import get_patches
    from .annotation import annotate_table, default_annotation, recurse_tags

    annotation_dict = {
        k: v for k, v in vars(x.patches.annotation).items() if v is not None
    }
    annotation = modify_list(vars(default_annotation), annotation_dict)
    # Rebuild a PlotAnnotation dataclass instance.
    from .annotation import PlotAnnotation

    annotation_obj = PlotAnnotation(**annotation)

    tagged = recurse_tags(
        x,
        annotation_obj.tag_levels or [],
        annotation_obj.tag_prefix or "",
        annotation_obj.tag_suffix or "",
        annotation_obj.tag_sep or "",
    )["patches"]
    patches = get_patches(tagged)
    table = build_patchwork(patches)
    table = annotate_table(table, annotation_obj)
    remove_class(table, "gtable_patchwork")
    return table


#: R-compatible alias.
patchwork_grob = patchworkGrob


# -----------------------------------------------------------------------------
# add_strips / add_guides (ports of the corresponding R helpers)
# -----------------------------------------------------------------------------


def add_strips(gt: Gtable) -> Gtable:
    """Ensure the gtable has strip rows/columns for patchwork alignment.

    If ggplot already introduced strips and placed them "outside", we merge
    the strip-gap into the adjacent axis and delete the gap row/column —
    matching R's ``add_strips``.
    """
    panel_loc = find_panel(gt)
    strip_pos = 0 if _find_strip_pos(gt) == "inside" else 2

    if not any("strip-b" in n for n in gt.layout["name"]):
        gt = gtable_add_rows(gt, Unit([0], ["mm"]), panel_loc["b"] + strip_pos)
    elif strip_pos == 2 and all(b != panel_loc["b"] + 2 for b in gt.layout["b"]):
        idx = panel_loc["b"] + 1
        merged = gt.heights.values[idx - 1] + gt.heights.values[idx]
        gt.heights = _set_unit_value(gt.heights, idx - 1, merged, gt.heights.units_list[idx - 1])
        gt = _drop_row(gt, panel_loc["b"] + 2)

    if not any("strip-t" in n for n in gt.layout["name"]):
        gt = gtable_add_rows(gt, Unit([0], ["mm"]), panel_loc["t"] - 1 - strip_pos)
    elif strip_pos == 2 and all(t != panel_loc["t"] - 2 for t in gt.layout["t"]):
        idx = panel_loc["t"] - 1
        merged = gt.heights.values[idx - 1] + gt.heights.values[idx]
        gt.heights = _set_unit_value(gt.heights, idx - 1, merged, gt.heights.units_list[idx - 1])
        gt = _drop_row(gt, panel_loc["t"] - 2)

    if not any("strip-r" in n for n in gt.layout["name"]):
        gt = gtable_add_cols(gt, Unit([0], ["mm"]), panel_loc["r"] + strip_pos)
    elif strip_pos == 2 and all(r != panel_loc["r"] + 2 for r in gt.layout["r"]):
        idx = panel_loc["r"] + 1
        merged = gt.widths.values[idx - 1] + gt.widths.values[idx]
        gt.widths = _set_unit_value(gt.widths, idx - 1, merged, gt.widths.units_list[idx - 1])
        gt = _drop_col(gt, panel_loc["r"] + 2)

    if not any("strip-l" in n for n in gt.layout["name"]):
        gt = gtable_add_cols(gt, Unit([0], ["mm"]), panel_loc["l"] - 1 - strip_pos)
    elif strip_pos == 2 and all(l != panel_loc["l"] - 2 for l in gt.layout["l"]):
        idx = panel_loc["l"] - 1
        merged = gt.widths.values[idx - 1] + gt.widths.values[idx]
        gt.widths = _set_unit_value(gt.widths, idx - 1, merged, gt.widths.units_list[idx - 1])
        gt = _drop_col(gt, panel_loc["l"] - 2)
    return gt


def _pad_to_canonical(gt: Gtable) -> Gtable:
    """Insert zero-sized rows/cols so the panel sits at (PANEL_ROW, PANEL_COL).

    .. note::

       This function has no counterpart in R. It exists to bridge an
       **upstream** gap: ``ggplot2_py.ggplotGrob`` currently emits a
       leaner gtable than R's ``ggplot2::ggplotGrob`` — specifically,
       it omits the zero-height/width padding rows/cols that R adds
       around the panel (subtitle-gap, caption-gap, guide-gap cells
       etc.). Patchwork's layout constants (``PANEL_ROW=10``,
       ``PANEL_COL=8`` etc. from ``_constants.py``) assume R's 18×15
       shape. Without this pad the canonical indices in ``add_guides``,
       ``add_strips``, ``_simplify_free`` / ``_simplify_fixed`` point
       at the wrong cells.

       The *correct* long-term fix is in **ggplot2_py** — make its
       ``ggplotGrob`` emit the same 18×15 layout that R does. Once
       that's done, every ``_pad_to_canonical(gt)`` call in this file
       becomes a no-op and can be removed. Until then, removing it
       here would silently break every composed plot.
    """
    panel = find_panel(gt)
    # Pad rows above the panel so panel row reaches PANEL_ROW.
    top_pad = PANEL_ROW - panel["t"]
    for _ in range(max(0, top_pad)):
        gt = gtable_add_rows(gt, Unit([0], ["mm"]), 0)

    # Pad rows below the panel so total rows reach TABLE_ROWS.
    bottom_pad = TABLE_ROWS - len(gt.heights.values)
    for _ in range(max(0, bottom_pad)):
        gt = gtable_add_rows(gt, Unit([0], ["mm"]))

    # Pad cols left of the panel so panel col reaches PANEL_COL.
    panel = find_panel(gt)
    left_pad = PANEL_COL - panel["l"]
    for _ in range(max(0, left_pad)):
        gt = gtable_add_cols(gt, Unit([0], ["mm"]), 0)

    # Pad cols right of the panel so total cols reach TABLE_COLS.
    right_pad = TABLE_COLS - len(gt.widths.values)
    for _ in range(max(0, right_pad)):
        gt = gtable_add_cols(gt, Unit([0], ["mm"]))
    return gt


def _find_strip_pos(gt: Gtable) -> str:
    panel_loc = find_panel(gt)
    names = gt.layout["name"]
    for side, cmp in (
        ("strip-t", lambda i: panel_loc["t"] - gt.layout["t"][i] != 1),
        ("strip-r", lambda i: gt.layout["r"][i] - panel_loc["r"] != 1),
        ("strip-b", lambda i: gt.layout["b"][i] - panel_loc["b"] != 1),
        ("strip-l", lambda i: panel_loc["l"] - gt.layout["l"][i] != 1),
    ):
        ind = [i for i, n in enumerate(names) if n.startswith(side)]
        if ind and any(cmp(i) for i in ind):
            return "outside"
    return "inside"


def add_guides(gt: Gtable, collect: bool = False) -> Gtable:
    """Allocate rows/columns for the guide-box (and optionally collect guides).

    Port of R's ``add_guides`` (``R/plot_patchwork.R:979-1061``). Two
    branches mirror the two ggplot2 ABIs:

    - ``len(guide_ind) == 5``: ggplot2 ≥ 3.5 shipped one cell per
      position (left/right/top/bottom/inside). Zero the gap cells on
      every collected side and pull the inner ``guides`` grobs out.
    - ``len(guide_ind) <= 1``: ggplot2 < 3.5 shipped a single guide
      box. Detect its position from its layout row vs the panel's,
      then insert the canonical +/-2 gap rows/cols so the canonical
      layout indices line up with :data:`PANEL_ROW` / :data:`PANEL_COL`.
    """
    panel_loc = find_panel(gt)
    guide_ind = [i for i, n in enumerate(gt.layout["name"]) if "guide-box" in n]

    # ------------------------------------------------ ggplot2 ≥ 3.5 path
    if len(guide_ind) == 5:
        # R plot_patchwork.R:983-988: without collection the guide cells
        # already live in the right layout spots; nothing to do.
        if not collect:
            return gt
        # R:991 — strip the "guide-box-" prefix to get the side name.
        guide_positions = [
            gt.layout["name"][i].replace("guide-box-", "") for i in guide_ind
        ]
        for idx, pos in zip(guide_ind, guide_positions):
            # R:994 — space_pos is +1 for left/top (gap cell is one
            # column/row *after* the guide) and -1 for right/bottom (gap
            # cell is one *before* the guide).
            if pos in ("left", "right"):
                col = gt.layout["l"][idx]
                col_mod = 1 if pos == "left" else -1
                gt.widths = _set_unit_value(gt.widths, col - 1, 0, "mm")
                gt.widths = _set_unit_value(gt.widths, col - 1 + col_mod, 0, "mm")
            elif pos in ("top", "bottom"):
                row = gt.layout["t"][idx]
                row_mod = 1 if pos == "top" else -1
                gt.heights = _set_unit_value(gt.heights, row - 1, 0, "mm")
                gt.heights = _set_unit_value(gt.heights, row - 1 + row_mod, 0, "mm")

        # R:1003-1007 — collect the inner "guides" grobs across all
        # guide-box cells.
        collection = []
        for idx in guide_ind:
            box = gt.grobs[idx]
            if hasattr(box, "grobs") and hasattr(box, "layout"):
                for j, n in enumerate(box.layout.get("name", [])):
                    if "guides" in n:
                        collection.append(box.grobs[j])
        set_attr(gt, "collected_guides", collection)
        gt = _drop_indices(gt, guide_ind)
        return gt

    # ------------------------------------------------ ggplot2 < 3.5 path
    # R plot_patchwork.R:1016-1034 — derive guide_pos from the one guide
    # box's position relative to the panel.
    if not guide_ind:
        guide_pos = "none"
    else:
        idx = guide_ind[0]
        g = gt.layout
        if (
            g["t"][idx] == panel_loc["t"]
            and g["b"][idx] == panel_loc["b"]
            and g["l"][idx] == panel_loc["l"]
            and g["r"][idx] == panel_loc["r"]
        ):
            guide_pos = "inside"
        elif g["t"][idx] == panel_loc["t"]:
            guide_pos = "left" if panel_loc["l"] > g["l"][idx] else "right"
        else:
            guide_pos = "top" if panel_loc["t"] > g["t"][idx] else "bottom"

    # R:1035-1046 — insert two zero-sized cells on every side the guide
    # is NOT occupying, so every ggplot has the canonical 18×15 shape.
    if guide_pos != "right":
        gt = gtable_add_cols(gt, Unit([0, 0], ["mm", "mm"]), panel_loc["r"] + 3)
    if guide_pos != "left":
        gt = gtable_add_cols(gt, Unit([0, 0], ["mm", "mm"]), panel_loc["l"] - 4)
    if guide_pos != "bottom":
        gt = gtable_add_rows(gt, Unit([0, 0], ["mm", "mm"]), panel_loc["b"] + 5)
    if guide_pos != "top":
        gt = gtable_add_rows(gt, Unit([0, 0], ["mm", "mm"]), panel_loc["t"] - 4)

    # R:1047-1059 — when collecting, extract the guide grob then zero
    # its two surrounding gap cells. Re-read guide_loc from gt.layout
    # since the gtable_add_rows/cols above can shift indices.
    if collect and guide_pos != "none":
        idx = guide_ind[0]
        grob = gt.grobs[idx]
        guide_loc = {k: gt.layout[k][idx] for k in ("t", "l", "b", "r")}
        space_pos = 1 if guide_pos in ("left", "top") else -1
        if guide_pos in ("right", "left"):
            gt.widths = _set_unit_value(gt.widths, guide_loc["l"] - 1, 0, "mm")
            gt.widths = _set_unit_value(gt.widths, guide_loc["l"] - 1 + space_pos, 0, "mm")
        elif guide_pos in ("bottom", "top"):
            gt.heights = _set_unit_value(gt.heights, guide_loc["t"] - 1, 0, "mm")
            gt.heights = _set_unit_value(gt.heights, guide_loc["t"] - 1 + space_pos, 0, "mm")

        collected = []
        if hasattr(grob, "grobs") and hasattr(grob, "layout"):
            for j, n in enumerate(grob.layout.get("name", [])):
                if "guides" in n:
                    collected.append(grob.grobs[j])
        set_attr(gt, "collected_guides", collected)
        gt = _drop_indices(gt, guide_ind)
    return gt


# -----------------------------------------------------------------------------
# add_insets
# -----------------------------------------------------------------------------


def add_insets(gt_list: Sequence[Gtable]) -> list[Gtable]:
    """Merge ``inset_table``-class gtables onto preceding canvases."""
    from ._gtable_state import has_class, remove_class

    flags = [has_class(g, "inset_table") for g in gt_list]
    if not any(flags):
        return list(gt_list)

    canvases = []
    running = 0
    for flag in flags:
        running += 0 if flag else 1
        canvases.append(running)

    if flags[0]:
        raise ValueError("insets cannot be the first plot in a patchwork")

    out = list(gt_list)
    for i, is_inset in enumerate(flags):
        if not is_inset:
            continue
        ins = out[i]
        canvas_idx = canvases[i] - 1
        can = out[canvas_idx]
        settings = get_attr(ins, "inset_settings")
        if settings.get("on_top", True):
            z = max(can.layout["z"]) + 1
        else:
            bg = [j for j, n in enumerate(can.layout["name"]) if "background" in n]
            z = can.layout["z"][bg[0]] if bg else min(can.layout["z"]) - 1
        align_to = settings.get("align_to", "panel")
        if align_to == "panel":
            can = gtable_add_grob(
                can, [ins],
                t=PANEL_ROW, l=PANEL_COL,
                z=z, clip=settings["clip"], name=f"inset_{i + 1}",
            )
        elif align_to == "plot":
            can = gtable_add_grob(
                can, [ins],
                t=PLOT_TOP, l=PLOT_LEFT,
                b=PLOT_BOTTOM, r=PLOT_RIGHT,
                z=z, clip=settings["clip"], name=f"inset_{i + 1}",
            )
        elif align_to == "full":
            can = gtable_add_grob(
                can, [ins],
                t=1, l=1,
                b=len(can.heights.values), r=len(can.widths.values),
                z=z, clip=settings["clip"], name=f"inset_{i + 1}",
            )
        else:
            raise ValueError(f"Unknown alignment setting: {align_to!r}")
        out[canvas_idx] = can

    return [g for g, f in zip(out, flags) if not f]


# -----------------------------------------------------------------------------
# simplify_free / simplify_fixed
# -----------------------------------------------------------------------------


def _name_suffix_match(name: str, suffix: str) -> bool:
    """Mirror R's ``grep('-<sfx>(-|$)', name)`` — the axis/strip marker test."""
    marker = "-" + suffix
    if marker not in name:
        return False
    idx = name.rfind(marker)
    end = idx + len(marker)
    return end == len(name) or name[end] == "-"


def _subset_grob_list(gt: Gtable, indices: Sequence[int]) -> list:
    """Return [gt.grobs[i] for i in indices] using 0-based *indices*."""
    return [gt.grobs[i] for i in indices]


def _paste_layout_names(table: Gtable, sep: str = ", ") -> str:
    """R ``paste(table$layout$name, collapse = sep)``."""
    return sep.join(table.layout.get("name", []))


def _max_layout_z(table: Gtable, default: int = 0) -> int:
    z = table.layout.get("z", [])
    return max(z) if z else default


def _apply_vp_to_gtable_grobs(
    gt: Gtable, pattern: str, vp_builder,
) -> None:
    """For every layout row whose name starts with *pattern*, mutate the
    associated grob's ``vp`` via *vp_builder(grob)*.

    Mirrors R's ``gt$grobs[strips] <- lapply(gt$grobs[strips], ...)``.
    """
    names = gt.layout.get("name", [])
    for i, nm in enumerate(names):
        if nm.startswith(pattern):
            g = gt.grobs[i]
            if isinstance(g, Gtable):
                g.vp = vp_builder(g)
                gt.grobs[i] = g


def _simplify_free(gt: Gtable, gt_new: Gtable, panels: Gtable, rows, cols) -> Gtable:
    """Port of R's ``simplify_free`` (plot_patchwork.R:443-551).

    Routes axis / strip / label grobs around the panel block while
    shifting indices into the ``gt_new`` coordinate system.
    """
    p_cols = list(range(cols[0], cols[1] + 1))
    p_rows = list(range(rows[0], rows[1] + 1))
    layout = gt.layout
    n_cells = len(layout.get("name", []))
    z_list = layout.get("z", [])

    # ------------------------- columnar axis/strip handling -------------
    if len(p_cols) == 1:
        p_col = p_cols[0]
        top_idx = [
            i for i in range(n_cells)
            if layout["l"][i] == p_col and layout["r"][i] == p_col
            and layout["b"][i] < rows[0]
        ]
        if top_idx:
            gt_new = gtable_add_grob(
                gt_new,
                _subset_grob_list(gt, top_idx),
                t=[layout["t"][i] for i in top_idx],
                l=p_col,
                b=[layout["b"][i] for i in top_idx],
                z=[z_list[i] for i in top_idx] if z_list else None,
                clip=[layout["clip"][i] for i in top_idx],
                name=[layout["name"][i] for i in top_idx],
            )
        bottom_idx = [
            i for i in range(n_cells)
            if layout["l"][i] == p_col and layout["r"][i] == p_col
            and layout["t"][i] > rows[1]
        ]
        if bottom_idx:
            b_mod = rows[1] - rows[0]
            gt_new = gtable_add_grob(
                gt_new,
                _subset_grob_list(gt, bottom_idx),
                t=[layout["t"][i] - b_mod for i in bottom_idx],
                l=p_col,
                b=[layout["b"][i] - b_mod for i in bottom_idx],
                z=[z_list[i] for i in bottom_idx] if z_list else None,
                clip=[layout["clip"][i] for i in bottom_idx],
                name=[layout["name"][i] for i in bottom_idx],
            )
        # NB: R uses ``sum(g$heights)`` which preserves unit type
        # (simpleUnit sum for same-kind, compound 'sum' for mixed).
        # The Python shortcut below collapses raw values into ``mm``
        # which is correct iff every strip row is already absolute —
        # the overwhelmingly common case for strip grobs, which carry
        # strip-text rows + rect padding (all absolute). A lazy
        # ``grobheight`` entry would be numerically wrong here; no
        # known fixture exercises that path, but the reduction below
        # should switch to ``_unit_reduce_sum``-style if it ever does.
        _apply_vp_to_gtable_grobs(
            gt_new, "strip-t-",
            lambda g: Viewport(
                y=Unit([0.0], ["npc"]),
                height=Unit([float(sum(g.heights.values))], ["mm"]),
                just=["centre", "bottom"],
            ),
        )
        _apply_vp_to_gtable_grobs(
            gt_new, "strip-b-",
            lambda g: Viewport(
                y=Unit([1.0], ["npc"]),
                height=Unit([float(sum(g.heights.values))], ["mm"]),
                just=["centre", "top"],
            ),
        )
    else:
        # R: ``simplify_free`` else-branch (plot_patchwork.R:466-489).
        # R wraps each above/below row's panel-area grobs into a single
        # gtable WITH a viewport so the inner content auto-sizes to its
        # natural height. The Python rendering pipeline pre-resolves
        # viewport heights before the inner gtable's grobs are in scope,
        # which collapses lazy ``grobheight`` units to 0 and erases the
        # title/strips/axis labels. Skipping the wrapper viewport keeps
        # the layout-name structure R-faithful (one combined cell per
        # row, named via paste0(layout$name, collapse=", ")) while
        # letting the inner gtable's own widths/heights resolve normally
        # against the parent cell — which is what we visually need.
        for i in range(1, len(gt.heights.values) + 1):
            if i >= rows[0]:
                if i <= rows[1]:
                    continue
                ii = i - (rows[1] - rows[0])
            else:
                ii = i
            table = gt[i - 1:i, p_cols[0] - 1:p_cols[-1]]
            if table.grobs:
                grobname = _paste_layout_names(table)
                gt_new = gtable_add_grob(
                    gt_new, table,
                    t=ii, l=cols[0], clip="off",
                    name=grobname,
                    z=_max_layout_z(table),
                )

    # ------------------------- rowwise axis/strip handling -------------
    if len(p_rows) == 1:
        p_row = p_rows[0]
        left_idx = [
            i for i in range(n_cells)
            if layout["t"][i] == p_row and layout["b"][i] == p_row
            and layout["r"][i] < cols[0]
        ]
        if left_idx:
            gt_new = gtable_add_grob(
                gt_new,
                _subset_grob_list(gt, left_idx),
                t=p_row,
                l=[layout["l"][i] for i in left_idx],
                b=p_row,
                r=[layout["r"][i] for i in left_idx],
                z=[z_list[i] for i in left_idx] if z_list else None,
                clip=[layout["clip"][i] for i in left_idx],
                name=[layout["name"][i] for i in left_idx],
            )
        right_idx = [
            i for i in range(n_cells)
            if layout["t"][i] == p_row and layout["b"][i] == p_row
            and layout["l"][i] > cols[1]
        ]
        if right_idx:
            r_mod = cols[1] - cols[0]
            gt_new = gtable_add_grob(
                gt_new,
                _subset_grob_list(gt, right_idx),
                t=p_row,
                l=[layout["l"][i] - r_mod for i in right_idx],
                b=p_row,
                r=[layout["r"][i] - r_mod for i in right_idx],
                z=[z_list[i] for i in right_idx] if z_list else None,
                clip=[layout["clip"][i] for i in right_idx],
                name=[layout["name"][i] for i in right_idx],
            )
        _apply_vp_to_gtable_grobs(
            gt_new, "strip-l-",
            lambda g: Viewport(
                x=Unit([1.0], ["npc"]),
                width=Unit([float(sum(g.widths.values))], ["mm"]),
                just=["right", "centre"],
            ),
        )
        _apply_vp_to_gtable_grobs(
            gt_new, "strip-r-",
            lambda g: Viewport(
                x=Unit([0.0], ["npc"]),
                width=Unit([float(sum(g.widths.values))], ["mm"]),
                just=["left", "centre"],
            ),
        )
    else:
        for i in range(1, len(gt.widths.values) + 1):
            if i >= cols[0]:
                if i <= cols[1]:
                    continue
                ii = i - (cols[1] - cols[0])
                pos = "right"
            else:
                ii = i
                pos = "left"
            table = gt[p_rows[0] - 1:p_rows[-1], i - 1:i]
            if table.grobs:
                grobname = _paste_layout_names(table)
                if pos == "left":
                    table.vp = Viewport(
                        x=Unit([1.0], ["npc"]),
                        width=table.widths,
                        just=["right", "centre"],
                    )
                else:
                    table.vp = Viewport(
                        x=Unit([0.0], ["npc"]),
                        width=table.widths,
                        just=["left", "centre"],
                    )
                gt_new = gtable_add_grob(
                    gt_new, table,
                    t=rows[0], l=ii, clip="off",
                    name=grobname,
                    z=_max_layout_z(table),
                )

    panel_name = "panel; " + _paste_layout_names(panels)
    return gtable_add_grob(
        gt_new, panels,
        t=rows[0], l=cols[0],
        clip="off", name=panel_name, z=1,
    )


def _simplify_fixed(gt: Gtable, gt_new: Gtable, panels: Gtable, rows, cols) -> Gtable:
    """Port of R's ``simplify_fixed`` (plot_patchwork.R:554-653).

    Merges axis / strip grobs *into* the panel block (with viewports
    positioned relative to the panel) rather than routing them around
    the panel. This keeps fixed-aspect panels aligned to their axis
    labels across the whole composition.
    """
    p_rows = list(range(rows[0], rows[1] + 1))
    p_cols = list(range(cols[0], cols[1] + 1))
    layout = gt.layout
    names = layout.get("name", [])

    left_ls = [layout["l"][i] for i, n in enumerate(names)
               if _name_suffix_match(n, "l")]
    right_rs = [layout["r"][i] for i, n in enumerate(names)
                if _name_suffix_match(n, "r")]
    top_ts = [layout["t"][i] for i, n in enumerate(names)
              if _name_suffix_match(n, "t")]
    bottom_bs = [layout["b"][i] for i, n in enumerate(names)
                 if _name_suffix_match(n, "b")]

    n_pan_rows = len(panels.heights.values)
    n_pan_cols = len(panels.widths.values)

    def _convert_widths_mm(g: Gtable) -> list[float]:
        return list(convert_width(g.widths, "mm").values)

    def _convert_heights_mm(g: Gtable) -> list[float]:
        return list(convert_height(g.heights, "mm").values)

    if left_ls and min(left_ls) < cols[0]:
        left_grob = gt[p_rows[0] - 1:p_rows[-1], min(left_ls) - 1:cols[0] - 1]
        half = sum(_convert_widths_mm(left_grob)) / 2.0
        left_grob.vp = Viewport(
            x=Unit([0.0], ["npc"]) - Unit([half], ["mm"]),
        )
        panels = gtable_add_grob(
            panels, left_grob,
            t=1, l=1, b=n_pan_rows, r=n_pan_cols,
            z=float("inf"), clip="off", name="left-l",
        )
    if right_rs and max(right_rs) > cols[1]:
        right_grob = gt[p_rows[0] - 1:p_rows[-1], cols[1]:max(right_rs)]
        half = sum(_convert_widths_mm(right_grob)) / 2.0
        right_grob.vp = Viewport(
            x=Unit([1.0], ["npc"]) + Unit([half], ["mm"]),
        )
        panels = gtable_add_grob(
            panels, right_grob,
            t=1, l=1, b=n_pan_rows, r=n_pan_cols,
            z=float("inf"), clip="off", name="right-r",
        )
    if top_ts and min(top_ts) < rows[0]:
        top_grob = gt[min(top_ts) - 1:rows[0] - 1, p_cols[0] - 1:p_cols[-1]]
        half = sum(_convert_heights_mm(top_grob)) / 2.0
        top_grob.vp = Viewport(
            y=Unit([1.0], ["npc"]) + Unit([half], ["mm"]),
        )
        panels = gtable_add_grob(
            panels, top_grob,
            t=1, l=1, b=n_pan_rows, r=n_pan_cols,
            z=float("inf"), clip="off", name="top-t",
        )
    if bottom_bs and max(bottom_bs) > rows[1]:
        bottom_grob = gt[rows[1]:max(bottom_bs), p_cols[0] - 1:p_cols[-1]]
        half = sum(_convert_heights_mm(bottom_grob)) / 2.0
        bottom_grob.vp = Viewport(
            y=Unit([0.0], ["npc"]) - Unit([half], ["mm"]),
        )
        panels = gtable_add_grob(
            panels, bottom_grob,
            t=1, l=1, b=n_pan_rows, r=n_pan_cols,
            z=float("inf"), clip="off", name="bottom-b",
        )

    # --- Add remaining grobs that sit outside the axis/strip region ---
    left_boundary = min(left_ls) if left_ls else cols[0]
    for i in range(1, left_boundary):
        table = gt[p_rows[0] - 1:p_rows[-1], i - 1:i]
        if table.grobs:
            grob, grobname = _single_or_wrap(table)
            gt_new = gtable_add_grob(
                gt_new, grob,
                t=rows[0], l=i, clip="off",
                name=grobname, z=_max_layout_z(table),
            )
    right_boundary = max(right_rs) if right_rs else cols[1]
    for k in range(1, len(gt.widths.values) - right_boundary + 1):
        table = gt[p_rows[0] - 1:p_rows[-1], k + right_boundary - 1:k + right_boundary]
        if table.grobs:
            grob, grobname = _single_or_wrap(table)
            gt_new = gtable_add_grob(
                gt_new, grob,
                t=rows[0], l=k + cols[0] + right_boundary - cols[1],
                clip="off", name=grobname, z=_max_layout_z(table),
            )
    top_boundary = min(top_ts) if top_ts else rows[0]
    for i in range(1, top_boundary):
        table = gt[i - 1:i, p_cols[0] - 1:p_cols[-1]]
        if table.grobs:
            grob, grobname = _single_or_wrap(table)
            gt_new = gtable_add_grob(
                gt_new, grob,
                t=i, l=cols[0], clip="off",
                name=grobname, z=_max_layout_z(table),
            )
    bottom_boundary = max(bottom_bs) if bottom_bs else rows[1]
    for k in range(1, len(gt.heights.values) - bottom_boundary + 1):
        table = gt[k + bottom_boundary - 1:k + bottom_boundary,
                   p_cols[0] - 1:p_cols[-1]]
        if table.grobs:
            grob, grobname = _single_or_wrap(table)
            gt_new = gtable_add_grob(
                gt_new, grob,
                t=k + rows[0] + bottom_boundary - rows[1],
                l=cols[0], clip="off",
                name=grobname, z=_max_layout_z(table),
            )

    panel_name = "panel; " + _paste_layout_names(panels)
    return gtable_add_grob(
        gt_new, panels,
        t=rows[0], l=cols[0],
        clip="off", name=panel_name, z=1,
    )


def _single_or_wrap(table: Gtable):
    """R's idiom: if the slice has one grob, use it directly; else wrap."""
    grobs = table.grobs
    names = table.layout.get("name", [])
    if len(grobs) == 1:
        return grobs[0], names[0]
    return table, _paste_layout_names(table)


# -----------------------------------------------------------------------------
# free_panel / free_label / free_space (simplified ports)
# -----------------------------------------------------------------------------


def _grob_in_rect(gt: Gtable, top: int, right: int, bottom: int, left: int) -> list[int]:
    """Return indices of layout rows whose cell is fully inside ``[top, bottom] × [left, right]``.

    Mirrors R's ``grob_in_rect`` (all four bounds are 1-based, inclusive).
    """
    lay = gt.layout
    return [
        i
        for i in range(len(lay["name"]))
        if lay["l"][i] >= left
        and lay["t"][i] >= top
        and lay["r"][i] <= right
        and lay["b"][i] <= bottom
    ]


def _liberate_area(
    gt: Gtable,
    top: int,
    right: int,
    bottom: int,
    left: int,
    name: Optional[str] = None,
    vp: Optional[Viewport] = None,
) -> Gtable:
    """Extract ``gt[top:bottom, left:right]`` as a single compound grob.

    Mirrors R's ``liberate_area``: slice the sub-gtable, remove every grob
    whose layout lies within the rectangle, then add the slice back as
    one grob named *name* (or the concatenation of captured names).
    """
    if top > bottom or left > right:
        return gt
    liberated = gt[top:bottom + 1, left:right + 1]
    remove = _grob_in_rect(gt, top, right, bottom, left)
    if not remove:
        return gt

    if vp is not None:
        liberated.vp = vp
    if name is None:
        captured = [gt.layout["name"][i] for i in remove]
        name = "; ".join(captured)

    # Remove liberated grobs from the source gtable.
    keep_mask = [i not in set(remove) for i in range(len(gt.grobs))]
    gt.grobs = [g for g, k in zip(gt.grobs, keep_mask) if k]
    gt.layout = {
        key: [v for v, k in zip(values, keep_mask) if k]
        for key, values in gt.layout.items()
    }

    z_vals = [liberated.layout["z"][i] for i in range(len(liberated.layout["z"]))]
    z = max(z_vals) if z_vals else 1
    return gtable_add_grob(
        gt,
        liberated,
        t=top,
        l=left,
        b=bottom,
        r=right,
        z=z,
        clip="inherit",
        name=name,
    )


def _liberate_rows(
    gt: Gtable,
    top: int,
    right: int,
    bottom: int,
    left: int,
    align: float = 0.5,
    name: Optional[str] = None,
) -> Gtable:
    """For each distinct ``(t, b)`` in the rectangle, liberate that row span."""
    idx = _grob_in_rect(gt, top, right, bottom, left)
    seen: set[tuple[int, int]] = set()
    unique_rows: list[tuple[int, int]] = []
    for i in idx:
        key = (gt.layout["t"][i], gt.layout["b"][i])
        if key not in seen:
            seen.add(key)
            unique_rows.append(key)
    for t, b in unique_rows:
        height = Unit(
            [sum(gt.heights.values[t - 1:b])],
            [gt.heights.units_list[t - 1] if gt.heights.units_list else "mm"],
        )
        vp = Viewport(y=align, height=height, just=(0.5, align))
        gt = _liberate_area(gt, t, right, b, left, name, vp)
    return gt


def _liberate_cols(
    gt: Gtable,
    top: int,
    right: int,
    bottom: int,
    left: int,
    align: float = 0.5,
    name: Optional[str] = None,
) -> Gtable:
    """For each distinct ``(l, r)`` in the rectangle, liberate that column span."""
    idx = _grob_in_rect(gt, top, right, bottom, left)
    seen: set[tuple[int, int]] = set()
    unique_cols: list[tuple[int, int]] = []
    for i in idx:
        key = (gt.layout["l"][i], gt.layout["r"][i])
        if key not in seen:
            seen.add(key)
            unique_cols.append(key)
    for l, r in unique_cols:
        width = Unit(
            [sum(gt.widths.values[l - 1:r])],
            [gt.widths.units_list[l - 1] if gt.widths.units_list else "mm"],
        )
        vp = Viewport(x=align, width=width, just=(align, 0.5))
        gt = _liberate_area(gt, top, r, bottom, l, name, vp)
    return gt


def _free_recurse_nested(
    gt: Gtable,
    has_side: Sequence[bool],
    fn,
) -> Gtable:
    """Descend into nested ``patchwork-table`` children.

    Ports the preamble of R's ``free_panel`` / ``free_label`` / ``free_space``
    (plot_patchwork.R:656-662, 770-776, 810-816): for every nested child,
    compute which of its sides touch the outer frame, intersect with the
    outer ``has_side``, and recurse with the narrowed mask.
    """
    names = list(gt.layout["name"])
    n_cols = len(gt.widths.values)
    n_rows = len(gt.heights.values)
    for i, nm in enumerate(names):
        if "patchwork-table" not in nm:
            continue
        t = gt.layout["t"][i]
        r = gt.layout["r"][i]
        b = gt.layout["b"][i]
        l = gt.layout["l"][i]
        child_sides = (
            (t == 1) and has_side[0],
            (r == n_cols) and has_side[1],
            (b == n_rows) and has_side[2],
            (l == 1) and has_side[3],
        )
        if not any(child_sides):
            continue
        gt.grobs[i] = fn(gt.grobs[i], list(child_sides))
    return gt


def _free_panel(gt: Gtable, has_side: Sequence[bool]) -> Gtable:
    """Port of R's ``free_panel``: pull the panel region into a compound grob.

    *has_side* is a 4-bool mask ``(top, right, bottom, left)``. Each ``True``
    tells patchwork to include that peripheral strip in the freed area.
    """
    gt = _free_recurse_nested(gt, has_side, _free_panel)

    n_cols = len(gt.widths.values)
    n_rows = len(gt.heights.values)

    top = 3 if has_side[0] else PANEL_ROW
    right = n_cols - (2 if has_side[1] else (TABLE_COLS - PANEL_COL))
    bottom = n_rows - (2 if has_side[2] else (TABLE_ROWS - PANEL_ROW))
    left = 3 if has_side[3] else PANEL_COL

    # Panel cell positions along each axis.
    panel_col_pos = [
        PANEL_COL + i * TABLE_COLS for i in range(n_cols // TABLE_COLS)
    ]
    panel_row_pos = [
        PANEL_ROW + i * TABLE_ROWS for i in range(n_rows // TABLE_ROWS)
    ]
    panel_widths = [gt.widths.values[i - 1] for i in panel_col_pos]
    panel_widths_units = [gt.widths.units_list[i - 1] for i in panel_col_pos]
    panel_heights = [gt.heights.values[i - 1] for i in panel_row_pos]
    panel_heights_units = [gt.heights.units_list[i - 1] for i in panel_row_pos]

    # Expand zero-size panel columns/rows to 1 null so liberation doesn't
    # produce a zero-height/-width slice. Use ``[<-.unit``-style native
    # subscript so non-panel cells keep their lazy ``data`` arrays
    # (grobwidth/grobheight references).
    one_null = Unit([1.0], ["null"])
    widths = gt.widths.copy()
    for ci, pcol in enumerate(panel_col_pos):
        if panel_widths[ci] == 0:
            widths[pcol - 1] = one_null
    gt.widths = widths
    heights = gt.heights.copy()
    for ri, prow in enumerate(panel_row_pos):
        if panel_heights[ri] == 0:
            heights[prow - 1] = one_null
    gt.heights = heights

    # Fixed-aspect branch — R:677-698. When the outer gt carries
    # ``respect = TRUE`` (set by ggplot2 for fixed-aspect coords), R
    # does NOT liberate the panel region into a compound grob. Instead
    # it extracts each side's axis/strip child out of the panels grob
    # and re-attaches it as a new row/col on the panels grob itself,
    # growing the panels block to cover the axis area. The outer
    # layout row for the panels grob then points at the expanded
    # (top/right/bottom/left) position.
    if getattr(gt, "respect", False) is True:
        p_idx = next(
            (j for j, n in enumerate(gt.layout["name"])
             if n.startswith("panel;")),
            None,
        )
        if p_idx is not None and isinstance(gt.grobs[p_idx], Gtable):
            panels_grob = gt.grobs[p_idx]
            # Each side: find the child-grob whose layout name matches
            # the side marker (R uses grep("top", ...)), sum its
            # heights/widths in mm, and grow panels_grob by that
            # slice at pos=0 (top / left) or pos=-1 (right / bottom).
            for side_idx, (marker, add_fn, dim_attr, outer_key, outer_val, pos) in enumerate((
                ("top",    gtable_add_rows, "heights", "t", top,    0),
                ("right",  gtable_add_cols, "widths",  "r", right, -1),
                ("bottom", gtable_add_rows, "heights", "b", bottom,-1),
                ("left",   gtable_add_cols, "widths",  "l", left,   0),
            )):
                if not has_side[side_idx]:
                    continue
                child_idx = next(
                    (k for k, cn in enumerate(panels_grob.layout["name"])
                     if marker in cn),
                    None,
                )
                if child_idx is None:
                    continue
                child = panels_grob.grobs[child_idx]
                child_dim = getattr(child, dim_attr, None)
                if child_dim is None:
                    continue
                # R: sum(child$heights) / sum(child$widths) — returns a
                # possibly-compound unit. Collapse to mm via convert_*
                # for a clean absolute value (matches R's resolution at
                # render time for fixed-aspect axes, which are always
                # absolute units).
                if dim_attr == "heights":
                    total_mm = float(sum(convert_height(child_dim, "mm").values))
                else:
                    total_mm = float(sum(convert_width(child_dim, "mm").values))
                panels_grob = add_fn(
                    panels_grob, Unit([total_mm], ["mm"]), pos=pos,
                )
                gt.grobs[p_idx] = panels_grob
                gt.layout[outer_key][p_idx] = outer_val
    else:
        gt = _liberate_area(gt, top, right, bottom, left, "free_panel")

    # After liberation, optionally flatten outer peripheral rows/cols.
    if not has_side[0] and (has_side[1] or has_side[3]):
        gt = _liberate_rows(gt, 3, right, top - 1, left, align=0.0, name="free_row")
    if not has_side[1] and (has_side[0] or has_side[2]):
        gt = _liberate_cols(gt, top, n_cols - 2, bottom, right + 1, align=0.0, name="free_col")
    if not has_side[2] and (has_side[1] or has_side[3]):
        gt = _liberate_rows(gt, bottom + 1, right, n_rows - 2, left, align=1.0, name="free_row")
    if not has_side[3] and (has_side[0] or has_side[2]):
        gt = _liberate_cols(gt, top, left - 1, bottom, 3, align=1.0, name="free_col")

    # Old-free repair (R:716-727). When free_panel is called on a gt
    # that *already* contains previously-freed grobs (``free_panel-*``
    # / ``free_row-*`` / ``free_col-*``) — as happens with chained
    # ``free(free(p, "panel"), "label")`` — those grobs need their
    # bounding boxes re-clipped to the new (top, right, bottom, left)
    # for any side flagged in has_side. Each grob gets cropped to the
    # new rectangle and its layout row updated in place.
    new_bounds = (top, right, bottom, left)
    bounds_keys = ("t", "r", "b", "l")
    prefixes = ("free_panel-", "free_row-", "free_col-")
    names_snapshot = list(gt.layout["name"])
    for i, nm in enumerate(names_snapshot):
        if not any(nm.startswith(pfx) for pfx in prefixes):
            continue
        loc = [gt.layout[k][i] for k in bounds_keys]
        for k in range(4):
            if has_side[k]:
                loc[k] = new_bounds[k]
        new_t, new_r, new_b, new_l = loc
        # Build a single-grob scratch gtable of the same outer shape,
        # holding only this grob at its original bounds; then slice it
        # to (new_t:new_b, new_l:new_r). Mirrors R's:
        #   gt_old <- gt
        #   gt_old$grobs <- gt_old$grobs[i]
        #   gt_old$layout <- gt_old$layout[i, ]
        #   gt$grobs[[i]] <- gt_old[loc[1]:loc[3], loc[4]:loc[2]]
        scratch = Gtable(widths=gt.widths, heights=gt.heights)
        scratch = gtable_add_grob(
            scratch, gt.grobs[i],
            t=gt.layout["t"][i], l=gt.layout["l"][i],
            b=gt.layout["b"][i], r=gt.layout["r"][i],
            name=nm,
        )
        cropped = scratch[new_t - 1:new_b, new_l - 1:new_r]
        gt.grobs[i] = cropped
        gt.layout["t"][i] = new_t
        gt.layout["r"][i] = new_r
        gt.layout["b"][i] = new_b
        gt.layout["l"][i] = new_l

    # Restore panel cell sizes and zero out the rest of the freed span.
    widths_values = list(gt.widths.values)
    widths_units = list(gt.widths.units_list)
    heights_values = list(gt.heights.values)
    heights_units = list(gt.heights.units_list)
    if panel_col_pos:
        inner_cols = set(range(min(panel_col_pos), max(panel_col_pos) + 1))
        for i in range(left, right + 1):
            if i not in inner_cols:
                widths_values[i - 1] = 0.0
                widths_units[i - 1] = "mm"
        for ci, pcol in enumerate(panel_col_pos):
            widths_values[pcol - 1] = panel_widths[ci]
            widths_units[pcol - 1] = panel_widths_units[ci]
    if panel_row_pos:
        inner_rows = set(range(min(panel_row_pos), max(panel_row_pos) + 1))
        for i in range(top, bottom + 1):
            if i not in inner_rows:
                heights_values[i - 1] = 0.0
                heights_units[i - 1] = "mm"
        for ri, prow in enumerate(panel_row_pos):
            heights_values[prow - 1] = panel_heights[ri]
            heights_units[prow - 1] = panel_heights_units[ri]
    gt.widths = Unit(widths_values, widths_units)
    gt.heights = Unit(heights_values, heights_units)
    set_attr(gt, "free_panel_sides", list(has_side))
    return gt


def _free_label(gt: Gtable, has_side: Sequence[bool]) -> Gtable:
    """Port of R's ``free_label``: liberate outer-label strips only."""
    # Fixed-aspect plots already have this behaviour (R:769).
    if getattr(gt, "respect", False) is True:
        return gt

    gt = _free_recurse_nested(gt, has_side, _free_label)

    n_cols = len(gt.widths.values)
    n_rows = len(gt.heights.values)

    top = PANEL_ROW
    right = n_cols - (TABLE_COLS - PANEL_COL)
    bottom = n_rows - (TABLE_ROWS - PANEL_ROW)
    left = PANEL_COL

    if has_side[0] and top - 3 >= 1:
        height = Unit(
            [sum(gt.heights.values[top - 3 - 1:top - 1])],
            [gt.heights.units_list[top - 3 - 1]],
        )
        vp = Viewport(y=0.0, height=height, just=(0.5, 0.0))
        gt = _liberate_area(gt, top - 3, right, top - 1, left, vp=vp)
    if has_side[1] and right + 3 <= n_cols:
        width = Unit(
            [sum(gt.widths.values[right:right + 3])],
            [gt.widths.units_list[right]],
        )
        vp = Viewport(x=0.0, width=width, just=(0.0, 0.5))
        gt = _liberate_area(gt, top, right + 3, bottom, right + 1, vp=vp)
    if has_side[2] and bottom + 3 <= n_rows:
        height = Unit(
            [sum(gt.heights.values[bottom:bottom + 3])],
            [gt.heights.units_list[bottom]],
        )
        vp = Viewport(y=1.0, height=height, just=(0.5, 1.0))
        gt = _liberate_area(gt, bottom + 1, right, bottom + 3, left, vp=vp)
    if has_side[3] and left - 3 >= 1:
        width = Unit(
            [sum(gt.widths.values[left - 3 - 1:left - 1])],
            [gt.widths.units_list[left - 3 - 1]],
        )
        vp = Viewport(x=1.0, width=width, just=(1.0, 0.5))
        gt = _liberate_area(gt, top, left - 1, bottom, left - 3, vp=vp)
    set_attr(gt, "free_label_sides", list(has_side))
    return gt


def _free_space(gt: Gtable, has_side: Sequence[bool]) -> Gtable:
    """Port of R's ``free_space``: liberate + zero the outer strip widths."""
    gt = _free_recurse_nested(gt, has_side, _free_space)

    n_cols = len(gt.widths.values)
    n_rows = len(gt.heights.values)

    top = PANEL_ROW
    right = n_cols - (TABLE_COLS - PANEL_COL)
    bottom = n_rows - (TABLE_ROWS - PANEL_ROW)
    left = PANEL_COL

    if has_side[0] and top - 1 >= 3:
        height = Unit(
            [sum(gt.heights.values[2:top - 1])],
            [gt.heights.units_list[2]],
        )
        vp = Viewport(y=0.0, height=height, just=(0.5, 0.0))
        gt = _liberate_area(gt, 3, right, top - 1, left, vp=vp)
        values = list(gt.heights.values)
        units = list(gt.heights.units_list)
        for i in range(2, top - 1):
            values[i] = 0.0
            units[i] = "mm"
        gt.heights = Unit(values, units)
    if has_side[1] and right + 1 <= n_cols - 2:
        width = Unit(
            [sum(gt.widths.values[right:n_cols - 2])],
            [gt.widths.units_list[right]],
        )
        vp = Viewport(x=0.0, width=width, just=(0.0, 0.5))
        gt = _liberate_area(gt, top, n_cols - 2, bottom, right + 1, vp=vp)
        values = list(gt.widths.values)
        units = list(gt.widths.units_list)
        for i in range(right, n_cols - 2):
            values[i] = 0.0
            units[i] = "mm"
        gt.widths = Unit(values, units)
    if has_side[2] and bottom + 1 <= n_rows - 2:
        height = Unit(
            [sum(gt.heights.values[bottom:n_rows - 2])],
            [gt.heights.units_list[bottom]],
        )
        vp = Viewport(y=1.0, height=height, just=(0.5, 1.0))
        gt = _liberate_area(gt, bottom + 1, right, n_rows - 2, left, vp=vp)
        values = list(gt.heights.values)
        units = list(gt.heights.units_list)
        for i in range(bottom, n_rows - 2):
            values[i] = 0.0
            units[i] = "mm"
        gt.heights = Unit(values, units)
    if has_side[3] and left - 1 >= 3:
        width = Unit(
            [sum(gt.widths.values[2:left - 1])],
            [gt.widths.units_list[2]],
        )
        vp = Viewport(x=1.0, width=width, just=(1.0, 0.5))
        gt = _liberate_area(gt, top, left - 1, bottom, 3, vp=vp)
        values = list(gt.widths.values)
        units = list(gt.widths.units_list)
        for i in range(2, left - 1):
            values[i] = 0.0
            units[i] = "mm"
        gt.widths = Unit(values, units)
    set_attr(gt, "free_space_sides", list(has_side))
    return gt


# -----------------------------------------------------------------------------
# set_panel_dimensions / table_dims / set_grob_sizes
# -----------------------------------------------------------------------------


def set_panel_dimensions(
    gt: Gtable,
    panels: Sequence[Gtable],
    widths: Sequence[float],
    heights: Sequence[float],
    fixed_asp: Sequence[bool],
    design: Sequence[dict],
) -> Gtable:
    """Apply per-row/column widths and heights to the panel lane of the big gtable.

    Ports R's ``set_panel_dimensions``. Handles three things:

    1. **Absolute panel-width/-height promotion**: when a sub-plot's panel
       cell has an absolute unit (e.g. fixed-aspect plots in R with
       ``coord_fixed()``), and the grid-level width/height for that
       column/row is still unset, promote the absolute value into the
       grid width/height.
    2. **Fixed-aspect respect matrix**: when both widths and heights
       contain ``NaN`` placeholders and at least one sub-plot is
       fixed-aspect, build a ``respect`` matrix marking those cells.
    3. **Final write-back**: put the resolved widths/heights into the
       outer gtable's panel lanes.
    """
    import math

    import numpy as np

    width_indices = [PANEL_COL + TABLE_COLS * i - 1 for i in range(len(widths))]
    height_indices = [PANEL_ROW + TABLE_ROWS * i - 1 for i in range(len(heights))]

    # Step 0 — normalise input widths/heights. Mirror R plot_patchwork.R:1086-1095:
    #   if (!is.unit(widths)) { widths[is.na(widths)] <- -1; widths <- unit(widths, 'null') }
    # then ``width_strings <- as.character(widths)`` so the (-1, "null") tuple
    # encodes "grid-level value not set yet". When the user supplied a Unit
    # (potentially split into single-entry Units by :func:`_as_sequence`),
    # preserve the unit types per entry (e.g. ``Unit([5, 1], ['cm','null'])``).
    def _split_dim(dim: Any) -> tuple[list[float], list[str]]:
        if isinstance(dim, Unit):
            entries: list[Any] = [dim[i:i + 1] for i in range(len(dim))]
        else:
            entries = list(dim)
        vals: list[float] = []
        units: list[str] = []
        for entry in entries:
            if isinstance(entry, Unit):
                v = float(entry.values[0])
                u = entry.units_list[0]
            elif isinstance(entry, float) and math.isnan(entry):
                v = -1.0
                u = "null"
            else:
                v = float(entry)
                u = "null"
            if isinstance(v, float) and math.isnan(v):
                v = -1.0
                u = "null"
            vals.append(v)
            units.append(u)
        return vals, units

    widths_values, widths_units = _split_dim(widths)
    heights_values, heights_units = _split_dim(heights)

    def _is_unset_width(ci: int) -> bool:
        return widths_units[ci] == "null" and widths_values[ci] == -1.0

    def _is_unset_height(ri: int) -> bool:
        return heights_units[ri] == "null" and heights_values[ri] == -1.0

    # Step 1 — absolute panel-width/-height promotion.
    panel_widths = []
    panel_widths_units = []
    panel_heights = []
    panel_heights_units = []
    for p in panels:
        pc = PANEL_COL - 1
        pr = PANEL_ROW - 1
        panel_widths.append(p.widths.values[pc] if pc < len(p.widths.values) else 0.0)
        panel_widths_units.append(
            p.widths.units_list[pc] if pc < len(p.widths.units_list) else "null"
        )
        panel_heights.append(p.heights.values[pr] if pr < len(p.heights.values) else 0.0)
        panel_heights_units.append(
            p.heights.units_list[pr] if pr < len(p.heights.units_list) else "null"
        )

    _ABS_UNITS = ("cm", "inches", "mm", "points", "picas", "bigpts", "dida", "cicero", "scaledpts")
    for i, rec in enumerate(design):
        if i >= len(panels):
            break
        # Width promotion: plot spans a single column AND its panel is
        # absolute AND the column is still unset.
        if rec["l"] == rec["r"] and panel_widths_units[i] in _ABS_UNITS and panel_widths[i] != 0:
            col = rec["l"] - 1
            if 0 <= col < len(widths_values) and _is_unset_width(col):
                widths_values[col] = max(widths_values[col], panel_widths[i]) \
                    if widths_values[col] != -1.0 else panel_widths[i]
                widths_units[col] = panel_widths_units[i]
        if rec["t"] == rec["b"] and panel_heights_units[i] in _ABS_UNITS and panel_heights[i] != 0:
            row = rec["t"] - 1
            if 0 <= row < len(heights_values) and _is_unset_height(row):
                heights_values[row] = max(heights_values[row], panel_heights[i]) \
                    if heights_values[row] != -1.0 else panel_heights[i]
                heights_units[row] = panel_heights_units[i]

    # Step 2 — fixed-aspect respect matrix.
    respect_matrix = None
    has_unset_width = any(_is_unset_width(i) for i in range(len(widths_values)))
    has_unset_height = any(_is_unset_height(i) for i in range(len(heights_values)))
    any_fixed = any(bool(f) for f in fixed_asp)

    if has_unset_width and has_unset_height and any_fixed:
        respect_matrix = np.zeros((len(gt.heights.values), len(gt.widths.values)), dtype=int)

        # Build list of candidate fixed areas: single-cell, all-null across
        # rows and cols, from plots with fixed_asp.
        fixed_indices = [i for i, f in enumerate(fixed_asp) if bool(f)]
        candidates: list[tuple[int, list[int], list[int], float, float]] = []
        for i in fixed_indices:
            if i >= len(panels) or i >= len(design):
                continue
            rec = design[i]
            rows = list(range(rec["t"] - 1, rec["b"]))
            cols = list(range(rec["l"] - 1, rec["r"]))
            if len(rows) != 1 or len(cols) != 1:
                continue
            # All the covered rows/cols must still be unset (null).
            if not all(_is_unset_width(c) for c in cols):
                continue
            if not all(_is_unset_height(r) for r in rows):
                continue
            w = panel_widths[i]
            h = panel_heights[i]
            if w == 0 or h == 0:
                continue
            candidates.append((i, rows, cols, w, h))

        # Apply fixed-aspect constraints in a stable order.
        for _, rows, cols, w, h in candidates:
            for c in cols:
                widths_values[c] = w
                widths_units[c] = panel_widths_units[fixed_indices[0]]  # unit doesn't really matter for null
            for r in rows:
                heights_values[r] = h
                heights_units[r] = panel_heights_units[fixed_indices[0]]
            for r in rows:
                for c in cols:
                    respect_matrix[height_indices[r], width_indices[c]] = 1

        if not respect_matrix.any():
            respect_matrix = None

    # Step 3 — finalize: replace sentinels with 1null, write back.
    for i in range(len(widths_values)):
        if _is_unset_width(i):
            widths_values[i] = 1.0
            widths_units[i] = "null"
    for i in range(len(heights_values)):
        if _is_unset_height(i):
            heights_values[i] = 1.0
            heights_units[i] = "null"

    gt_widths_vals = list(gt.widths.values)
    gt_widths_units = list(gt.widths.units_list)
    for idx, (w, u) in zip(width_indices, zip(widths_values, widths_units)):
        gt_widths_vals[idx] = float(w)
        gt_widths_units[idx] = u
    gt.widths = Unit(gt_widths_vals, gt_widths_units)

    gt_heights_vals = list(gt.heights.values)
    gt_heights_units = list(gt.heights.units_list)
    for idx, (h, u) in zip(height_indices, zip(heights_values, heights_units)):
        gt_heights_vals[idx] = float(h)
        gt_heights_units[idx] = u
    gt.heights = Unit(gt_heights_vals, gt_heights_units)

    if respect_matrix is not None:
        gt.respect = respect_matrix
    return gt


def table_dims(
    widths_list: Sequence[Unit],
    heights_list: Sequence[Unit],
    design: Sequence[dict],
    ncol: int,
    nrow: int,
) -> dict[str, Unit]:
    """Compute per-cell max widths/heights over every patch for *design*.

    Simplified: take the max numeric value (in mm) per position across every
    patch whose layout area covers that cell. Returns Units in mm.
    """
    widths_mm = [convert_width(w, "mm").values for w in widths_list]
    heights_mm = [convert_height(h, "mm").values for h in heights_list]

    total_cols = TABLE_COLS * ncol
    total_rows = TABLE_ROWS * nrow

    widths = []
    for i in range(1, total_cols + 1):
        cell = (i - 1) // TABLE_COLS + 1
        col_loc = (i - 1) % TABLE_COLS + 1
        side = "l" if col_loc <= PANEL_COL else "r"
        which = [idx for idx, rec in enumerate(design) if rec[side] == cell]
        if not which:
            widths.append(0.0)
        else:
            widths.append(max(widths_mm[idx][col_loc - 1] for idx in which))

    heights = []
    for i in range(1, total_rows + 1):
        cell = (i - 1) // TABLE_ROWS + 1
        row_loc = (i - 1) % TABLE_ROWS + 1
        side = "t" if row_loc <= PANEL_ROW else "b"
        which = [idx for idx, rec in enumerate(design) if rec[side] == cell]
        if not which:
            heights.append(0.0)
        else:
            heights.append(max(heights_mm[idx][row_loc - 1] for idx in which))

    return {
        "widths": Unit(widths, ["mm"] * len(widths)),
        "heights": Unit(heights, ["mm"] * len(heights)),
    }


def _unit_slice_1based(u: Unit, start: int, end: int) -> Unit:
    """R: ``u[start:end]`` — 1-based inclusive slice; preserves ``data``."""
    return u[start - 1:end]


def set_grob_sizes(
    tables: Sequence[Gtable],
    widths: Unit,
    heights: Unit,
    design: Sequence[dict],
) -> list:
    """Port of R's ``set_grob_sizes`` (plot_patchwork.R:895-914).

    For each table classified as ``gtable_patchwork_simple``, compute
    the slice of the global ``widths`` / ``heights`` corresponding to
    that cell's border zones (outside of ``PANEL_COL`` / ``PANEL_ROW``),
    find the nested ``patchwork-table`` grob inside, and push those
    slices through :func:`set_border_sizes` so nested patchworks
    inherit the outer layout's outer margins. Non-simple tables are
    left untouched and just flattened into the output list.

    Parameters match R's: *design* is a sequence of dicts with keys
    ``t`` / ``l`` / ``b`` / ``r`` — the 1-based cell coordinates of each
    table in the enclosing layout.
    """
    from ._gtable_state import has_class
    from .guides import set_border_sizes as _set_border_sizes

    out: list = []
    for i, gt in enumerate(tables):
        if not has_class(gt, "gtable_patchwork_simple"):
            out.extend(gt.grobs)
            continue

        tl = design[i]
        l_off = (tl["l"] - 1) * TABLE_COLS
        r_off = (tl["r"] - 1) * TABLE_COLS
        t_off = (tl["t"] - 1) * TABLE_ROWS
        b_off = (tl["b"] - 1) * TABLE_ROWS

        l_widths  = _unit_slice_1based(widths,  l_off + 1,               l_off + PANEL_COL - 1)
        r_widths  = _unit_slice_1based(widths,  r_off + PANEL_COL + 1,   r_off + TABLE_COLS)
        t_heights = _unit_slice_1based(heights, t_off + 1,               t_off + PANEL_ROW - 1)
        b_heights = _unit_slice_1based(heights, b_off + PANEL_ROW + 1,   b_off + TABLE_ROWS)

        nested_idx = next(
            (j for j, n in enumerate(gt.layout["name"])
             if "patchwork-table" in n),
            None,
        )
        if nested_idx is not None:
            gt.grobs[nested_idx] = _set_border_sizes(
                gt.grobs[nested_idx],
                l=l_widths,
                r=r_widths,
                t=t_heights,
                b=b_heights,
            )
        out.extend(gt.grobs)
    return out


def set_border_sizes(gt: Gtable, **kwargs):  # pragma: no cover — re-exported for parity
    from .guides import set_border_sizes as _sbs

    return _sbs(gt, **kwargs)


# -----------------------------------------------------------------------------
# small Unit helpers
# -----------------------------------------------------------------------------


def _unit_at(u: Unit, idx: Sequence[int]) -> Unit:
    """R: ``u[idx + 1]`` — 0-based subset wrapper.

    Delegates to :py:meth:`grid_py.Unit.__getitem__`, which is the
    faithful port of R's ``[.unit`` (grid/R/unit.R:454) and preserves
    every per-entry attribute including the ``data`` grob reference
    that lazy ``grobheight`` / ``grobwidth`` units need to resolve.
    Keeping this helper as a named wrapper so call-sites stay
    self-documenting; the empty case returns a concrete zero-mm unit.
    """
    idx = list(idx)
    if not idx:
        return Unit([0], ["mm"])
    return u[idx]


def _collapse_dim(u: Unit, indices: Sequence[int], kind: str) -> Unit:
    sub = _unit_at(u, [i - 1 for i in indices])
    if is_abs_unit(sub):
        if kind == "width":
            mm = convert_width(sub, "mm")
        else:
            mm = convert_height(sub, "mm")
        return Unit([sum(mm.values)], ["mm"])
    return Unit([1.0], ["null"])


def _concat_unit(*parts: Unit) -> Unit:
    """R: ``unit.c(...)`` — thin wrapper over :func:`grid_py.unit_c`."""
    if not parts:
        return Unit([0], ["mm"])
    return unit_c(*parts)


def _sum_unit(u: Unit) -> Unit:
    return Unit([sum(u.values)], [u.units_list[0] if u.units_list else "mm"])


def _slice_gtable(gt: Gtable, rows: Sequence[int], cols: Sequence[int]) -> Gtable:
    """Extract a sub-gtable at the given 1-based row/col lists.

    R equivalent: ``gt[rows, cols]``. The slice must honour R's
    ``gt[-p_rows, -p_cols]`` "exclude" semantic — the caller passes the
    full keep-list (not a contiguous range), and this helper delegates
    to :py:meth:`gtable_py.Gtable.__getitem__` with a list of 0-based
    indices so genuinely excluded rows/cols are dropped (and any grob
    that straddled them is deleted rather than smuggled through).
    """
    if rows and cols:
        return gt[[r - 1 for r in rows], [c - 1 for c in cols]]
    return gt


def _set_unit_value(u: Unit, idx: int, value: float, unit_name: str) -> Unit:
    """R: ``u[idx + 1] <- unit(value, unit_name)``.

    Native :py:meth:`grid_py.Unit.__setitem__` updates one slot in place
    while preserving every OTHER slot's ``data`` (the grob references
    that lazy ``grobwidth`` / ``grobheight`` / ``sum`` units rely on).
    Rebuilding from a flat ``Unit(values, units)`` would silently drop
    every neighbour's data and collapse them to 0 mm at draw time.
    """
    out = u.copy()
    out[idx] = Unit([float(value)], [unit_name])
    return out


def _drop_row(gt: Gtable, row: int) -> Gtable:
    """Drop a single row from *gt* (1-based)."""
    keep = [r for r in range(1, len(gt.heights.values) + 1) if r != row]
    return _slice_gtable(gt, keep, list(range(1, len(gt.widths.values) + 1)))


def _drop_col(gt: Gtable, col: int) -> Gtable:
    keep = [c for c in range(1, len(gt.widths.values) + 1) if c != col]
    return _slice_gtable(gt, list(range(1, len(gt.heights.values) + 1)), keep)


def _drop_indices(gt: Gtable, idx: Sequence[int]) -> Gtable:
    keep = [i for i in range(len(gt.grobs)) if i not in idx]
    gt.grobs = [gt.grobs[i] for i in keep]
    gt.layout = {k: [v[i] for i in keep] for k, v in gt.layout.items()}
    return gt


def create_design(width: int, height: int, byrow: bool):
    """Re-export to preserve R-API parity."""
    return _create_design(width, height, byrow)
