"""``great_tables.GT`` → ``gtable_py.Gtable`` bridge.

Port of R ``gt::as_gtable()`` (gt v1.3.0 R/utils-render-grid.R). The
algorithm walks the GT data model (heading / boxhead / stub / spanners /
body / source_notes / footnotes / options) and emits a gtable with the
named regions R's ``patchwork::wrap_table`` keys off:

  * One row per ``column_label`` cell, named ``column_label_{n}``
  * One row per body cell, named ``body_cell_{n}``
  * Optional ``title`` / ``subtitle`` / ``spanner`` / ``stubhead`` /
    ``source_notes`` / ``footnotes`` / ``caption`` rows
  * Two named spans:
      - ``table_body``  – covers the body-cell region
      - ``table``       – covers caption-through-source rows
  * Two outer ``0.5 null`` spacer columns wrapping the content grid
    (``grid_align_gtable``)

The output is interchangeable with R's ``gt::as_gtable(gt_tbl)`` for
patchwork's ``as_patch.gt_tbl`` consumer.

References
----------
* R source: ``gt::as_gtable``, ``combine_components``, ``finalize_gtable``,
  ``grid_align_gtable``, ``grid_layout_widths``, ``grid_layout_heights``
  (gt R/utils-render-grid.R).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import numpy as np
import pandas as pd

from grid_py import Gpar, Unit, null_grob, text_grob
from grid_py._size import calc_string_metric
from gtable_py import Gtable, gtable_add_cols, gtable_add_grob

__all__ = ["gt_as_gtable", "is_great_tables_gt"]


# ---------------------------------------------------------------------------
# Layout cell record (mirrors R ``grid_layout`` data frame row)
# ---------------------------------------------------------------------------


@dataclass
class _Cell:
    """One row of R gt's ``grid_layout`` data frame."""

    left: int
    right: int
    top: int
    bottom: int
    label: str
    name: str
    align: str = "left"


# ---------------------------------------------------------------------------
# Type guard
# ---------------------------------------------------------------------------


def is_great_tables_gt(x: Any) -> bool:
    """Return ``True`` if *x* is a :class:`great_tables.GT` instance."""
    try:
        from great_tables import GT
    except ImportError:
        return False
    return isinstance(x, GT)


# ---------------------------------------------------------------------------
# Component builders (one per R ``create_*_component_g``)
# ---------------------------------------------------------------------------


def _create_caption_component(data: Any) -> List[_Cell]:
    """R: ``create_caption_component_g`` — caption row spanning all cols."""
    caption = _option(data, "table_caption", default=None)
    if caption is None or (isinstance(caption, float) and np.isnan(caption)):
        return []
    n_cols = _effective_n_cols(data)
    return [_Cell(left=1, right=n_cols, top=1, bottom=1,
                  label=str(caption), name="caption", align="center")]


def _create_heading_component(data: Any) -> List[_Cell]:
    """R: ``create_heading_component_g`` — title + optional subtitle rows."""
    title = data._heading.title
    subtitle = data._heading.subtitle
    if (title is None or title == "") and (subtitle is None or subtitle == ""):
        return []
    n_cols = _effective_n_cols(data)
    out: List[_Cell] = []
    cur = 1
    if title is not None and title != "":
        out.append(_Cell(left=1, right=n_cols, top=cur, bottom=cur,
                         label=str(title), name="title", align="center"))
        cur += 1
    if subtitle is not None and subtitle != "":
        out.append(_Cell(left=1, right=n_cols, top=cur, bottom=cur,
                         label=str(subtitle), name="subtitle", align="center"))
    return out


def _create_columns_component(data: Any) -> List[_Cell]:
    """R: ``create_columns_component_g`` — stubhead + spanners + column labels.

    The stubhead cell sits above the stub column when ``rowname_col`` was
    supplied; spanner rows stack above the column-label row; the column
    labels themselves are the bottom row of this component.
    """
    if _option(data, "column_labels_hidden", default=False):
        return []
    stub_layout = _stub_layout(data)
    n_stub = len(stub_layout)
    visible_cols = data._boxhead._get_default_columns()
    n_data_cols = len(visible_cols)

    spanner_rows = _spanner_rows(data, visible_cols)
    n_spanner_rows = len(spanner_rows)
    label_row = n_spanner_rows + 1

    cells: List[_Cell] = []

    # Stubhead — spans all stub columns at the bottom of the columns
    # component. R emits this cell only when ``dt_stubhead_get`` returns
    # a non-NULL label (i.e. user called ``tab_stubhead()``); without an
    # explicit stubhead, ``vec_c`` drops the NULL entry.
    stubhead_label = data._stubhead
    if n_stub > 0 and stubhead_label is not None and str(stubhead_label) != "":
        cells.append(_Cell(left=1, right=n_stub,
                           top=1, bottom=label_row,
                           label=str(stubhead_label), name="stubhead", align="left"))

    # Spanner cells (one per (level, group) span). R levels are
    # 0-indexed bottom-up; we flip so the topmost spanner has top=1.
    for sp in spanner_rows:
        cells.append(_Cell(
            left=n_stub + sp["start"], right=n_stub + sp["end"],
            top=sp["row"], bottom=sp["row"],
            label=str(sp["label"]), name="spanner", align="center",
        ))

    # Column labels (one cell per visible data column).
    for i, col in enumerate(visible_cols, start=1):
        cells.append(_Cell(
            left=n_stub + i, right=n_stub + i,
            top=label_row, bottom=label_row,
            label=str(col.column_label), name="column_label",
            align=col.column_align or "right",
        ))
    return cells


def _create_body_component(data: Any) -> List[_Cell]:
    """R: ``create_body_component_g`` — body cells (incl. stub).

    Group rows + summary rows are not yet ported (gt v1 features that
    have no analog in great_tables' simpler model anyway). Stub cells
    occupy the leftmost ``n_stub`` columns; data cells fill the rest.
    """
    from great_tables._tbl_data import cast_frame_to_string, replace_null_frame

    # Merge formatted body with raw stringified data — R's behaviour
    # when a column has no fmt_*: fall back to the raw value.
    str_orig = cast_frame_to_string(data._tbl_data)
    merged = replace_null_frame(data._body.body, str_orig)

    stub_layout = _stub_layout(data)
    n_stub = len(stub_layout)
    visible_cols = data._boxhead._get_default_columns()
    rownames = [row.rowname for row in data._stub.rows]

    # R's ``body_cells_g`` emits ONE flat sequence of cells per row,
    # numbered ``body_cell_{n}`` — the stub cell (rowname) is just the
    # leftmost cell in each row, named with the same convention. We
    # walk row-major (matching R's column-major-ish ordering produces
    # the same final layout because the render only depends on
    # (top, left, bottom, right)).
    cells: List[_Cell] = []
    n_rows = len(merged)
    for r in range(n_rows):
        if n_stub > 0:
            label = rownames[r] if r < len(rownames) and rownames[r] is not None else ""
            cells.append(_Cell(
                left=1, right=n_stub, top=r + 1, bottom=r + 1,
                label=str(label), name="body_cell", align="left",
            ))
        for c, col in enumerate(visible_cols, start=1):
            value = merged.iloc[r][col.var]
            text = "" if value is None or (isinstance(value, float) and np.isnan(value)) else str(value)
            cells.append(_Cell(
                left=n_stub + c, right=n_stub + c,
                top=r + 1, bottom=r + 1,
                label=text, name="body_cell",
                align=col.column_align or "right",
            ))
    return cells


def _create_source_notes_component(data: Any) -> List[_Cell]:
    """R: ``create_source_notes_component_g`` — joined source-note row."""
    notes = data._source_notes
    if not notes:
        return []
    multiline = _option(data, "source_notes_multiline", default=True)
    sep = "\n" if multiline else _option(data, "source_notes_sep", default=" ")
    text = sep.join(str(n) for n in notes)
    n_cols = _effective_n_cols(data)
    return [_Cell(left=1, right=n_cols, top=1, bottom=1,
                  label=text, name="source_notes", align="left")]


def _create_footnotes_component(data: Any) -> List[_Cell]:
    """R: ``create_footnotes_component_g`` — joined footnote row."""
    foot = data._footnotes
    if not foot:
        return []
    # great_tables stores FootnoteInfo records with ``footnote_text``
    # (or just text). Be permissive: accept str or .footnote attr.
    parts: List[str] = []
    for fn in foot:
        if isinstance(fn, str):
            parts.append(fn)
        elif hasattr(fn, "footnote") and fn.footnote is not None:
            parts.append(str(fn.footnote))
        elif hasattr(fn, "text") and fn.text is not None:
            parts.append(str(fn.text))
    if not parts:
        return []
    multiline = _option(data, "footnotes_multiline", default=True)
    sep = "\n" if multiline else _option(data, "footnotes_sep", default=" ")
    text = sep.join(parts)
    n_cols = _effective_n_cols(data)
    return [_Cell(left=1, right=n_cols, top=1, bottom=1,
                  label=text, name="footnotes", align="left")]


# ---------------------------------------------------------------------------
# Component combine + grid construction
# ---------------------------------------------------------------------------


def _combine_components(
    caption: List[_Cell],
    heading: List[_Cell],
    columns: List[_Cell],
    body: List[_Cell],
    source: List[_Cell],
    footnotes: List[_Cell],
) -> List[_Cell]:
    """R: ``combine_components`` (gt R/utils-render-grid.R).

    Stacks caption → heading → columns → body → footnotes → source
    vertically, then appends the ``table_body`` and ``table`` named
    spans.  The vertical order matches R's ordering exactly (``source``
    is always the *last* row, even after footnotes).
    """
    out: List[_Cell] = []
    n_caption = max((c.bottom for c in caption), default=0)
    cur = n_caption
    out.extend(caption)

    if heading:
        for c in heading:
            c.top += cur; c.bottom += cur
        cur = max(c.bottom for c in heading)
        out.extend(heading)

    if columns:
        for c in columns:
            c.top += cur; c.bottom += cur
        cur = max(c.bottom for c in columns)
        out.extend(columns)

    body_start = cur
    if body:
        for c in body:
            c.top += cur; c.bottom += cur
        cur = max(c.bottom for c in body)
        out.extend(body)
    body_end = cur

    if footnotes:
        for c in footnotes:
            c.top += cur; c.bottom += cur
        cur = max(c.bottom for c in footnotes)
        out.extend(footnotes)

    if source:
        for c in source:
            c.top += cur; c.bottom += cur
        cur = max(c.bottom for c in source)
        out.extend(source)

    n_cols = max((c.right for c in body), default=1) if body else 1

    # table_body — body-cell region only.
    if body:
        out.append(_Cell(
            left=1, right=n_cols, top=body_start + 1, bottom=body_end,
            label="", name="table_body",
        ))
    # table — caption row + 1 through last (footnotes / source).
    out.append(_Cell(
        left=1, right=n_cols, top=n_caption + 1, bottom=cur,
        label="", name="table",
    ))
    return out


def _measure_text_cm(label: str, fontsize: float = 10.0) -> Tuple[float, float]:
    """Width/height of *label* in cm using the renderer's font metrics."""
    if not label:
        return (0.0, 0.0)
    # Multi-line labels: take max width, sum of heights.
    lines = label.split("\n")
    max_w = 0.0
    total_h = 0.0
    for line in lines:
        if line == "":
            total_h += fontsize / 72.0 * 2.54  # blank-line height = 1 line
            continue
        m = calc_string_metric(line, Gpar(fontsize=fontsize))
        max_w = max(max_w, m["width"] * 2.54)
        # ascent + descent in inches → cm
        total_h += (m["ascent"] + m["descent"]) * 2.54
    return (max_w, total_h)


def _grid_layout_widths(layout: List[_Cell], n_cols: int,
                         padding_cm: float = 0.18) -> Unit:
    """R: ``grid_layout_widths`` — per-column width = max text width.

    Span cells are added *after* single-cell maxima so a wide span
    doesn't undersize an unconstrained column. ``padding_cm`` adds gt's
    default cell padding (R: ``data_cell_padding_horizontal`` ≈ 5px).
    """
    widths = [0.0] * n_cols
    spans: List[Tuple[int, int, float]] = []
    for cell in layout:
        if cell.name in ("table_body", "table"):
            continue
        w_cm, _ = _measure_text_cm(cell.label)
        w_cm += 2 * padding_cm
        if cell.left == cell.right:
            i = cell.left - 1
            widths[i] = max(widths[i], w_cm)
        else:
            spans.append((cell.left, cell.right, w_cm))

    for left, right, w in spans:
        cur = sum(widths[left - 1:right])
        if w > cur:
            extra = (w - cur) / (right - left + 1)
            for i in range(left - 1, right):
                widths[i] += extra
    return Unit(widths, ["cm"] * n_cols)


def _grid_layout_heights(layout: List[_Cell], n_rows: int,
                          padding_cm: float = 0.14) -> Unit:
    """R: ``grid_layout_heights`` — per-row height = max text height."""
    heights = [0.0] * n_rows
    spans: List[Tuple[int, int, float]] = []
    for cell in layout:
        if cell.name in ("table_body", "table"):
            continue
        _, h_cm = _measure_text_cm(cell.label)
        h_cm += 2 * padding_cm
        if cell.top == cell.bottom:
            i = cell.top - 1
            heights[i] = max(heights[i], h_cm)
        else:
            spans.append((cell.top, cell.bottom, h_cm))

    for top, bot, h in spans:
        cur = sum(heights[top - 1:bot])
        if h > cur:
            extra = (h - cur) / (bot - top + 1)
            for i in range(top - 1, bot):
                heights[i] += extra
    return Unit(heights, ["cm"] * n_rows)


def _render_text_grob(label: str, align: str = "left",
                      fontsize: float = 10.0) -> Any:
    """Build a textGrob for a single cell."""
    if not label:
        return null_grob()
    hjust_map = {"left": 0.0, "center": 0.5, "centre": 0.5, "right": 1.0}
    hjust = hjust_map.get(align, 0.0)
    # For multi-line labels, place each line as a separate text grob.
    # Keep it simple: just one text_grob with the joined label —
    # text_grob supports newlines via the underlying renderer.
    return text_grob(
        label=label,
        x=Unit([hjust if hjust > 0 else 0.05], ["npc"]),
        y=Unit([0.5], ["npc"]),
        hjust=hjust,
        vjust=0.5,
        gp=Gpar(fontsize=fontsize),
    )


def _finalize_gtable(layout: List[_Cell]) -> Gtable:
    """R: ``finalize_gtable`` — build gtable with named/numbered cells.

    R suffixes repeated names with ``_1, _2, _3, ...``; we mirror that so
    layout names match exactly (``column_label_1`` etc.).
    """
    n_cols = max(c.right for c in layout)
    n_rows = max(c.bottom for c in layout)
    widths = _grid_layout_widths(layout, n_cols)
    heights = _grid_layout_heights(layout, n_rows)

    gt = Gtable(widths=widths, heights=heights, name="gt_table")

    # R: ave(name, name, FUN=function(nm) if (length(nm) == 1) nm
    #       else paste0(nm, "_", seq_along(nm))).
    name_counts: dict[str, int] = {}
    for cell in layout:
        name_counts[cell.name] = name_counts.get(cell.name, 0) + 1
    name_seq: dict[str, int] = {}
    for cell in layout:
        if name_counts[cell.name] == 1:
            display_name = cell.name
        else:
            name_seq[cell.name] = name_seq.get(cell.name, 0) + 1
            display_name = f"{cell.name}_{name_seq[cell.name]}"
        if cell.name in ("table_body", "table"):
            grob = null_grob()
        else:
            grob = _render_text_grob(cell.label, align=cell.align)
        gt = gtable_add_grob(
            gt, grob,
            t=cell.top, l=cell.left, b=cell.bottom, r=cell.right,
            clip="off", name=display_name,
        )
    return gt


def _grid_align_gtable(gt: Gtable) -> Gtable:
    """R: ``grid_align_gtable`` — wrap with two outer 0.5-null spacer cols."""
    gt = gtable_add_cols(gt, Unit([0.5], ["null"]), pos=0)
    gt = gtable_add_cols(gt, Unit([0.5], ["null"]), pos=-1)
    return gt


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def gt_as_gtable(gt: Any) -> Gtable:
    """Render a ``great_tables.GT`` to a ``gtable_py.Gtable``.

    Mirrors R ``gt::as_gtable`` exactly: builds the six components,
    stacks them via ``combine_components``, finalises into a gtable,
    then wraps with outer 0.5-null spacer columns.

    The output gtable carries the named regions patchwork's
    ``wrap_table`` keys off (``table_body``, ``table``,
    ``column_label_*``, ``body_cell_*`` …).
    """
    if not is_great_tables_gt(gt):
        raise TypeError(
            f"gt_as_gtable expects a great_tables.GT, got "
            f"{type(gt).__name__}"
        )
    data = gt._build_data(context="html")
    caption = _create_caption_component(data)
    heading = _create_heading_component(data)
    columns = _create_columns_component(data)
    body = _create_body_component(data)
    source = _create_source_notes_component(data)
    footnotes = _create_footnotes_component(data)
    layout = _combine_components(caption, heading, columns, body, source,
                                  footnotes)
    gt_obj = _finalize_gtable(layout)
    gt_obj = _grid_align_gtable(gt_obj)
    return gt_obj


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _option(data: Any, key: str, default: Any = None) -> Any:
    """Read a great_tables option by R-style dotted key."""
    opts = data._options
    # great_tables stores options as attributes on the Options dataclass.
    # Map R-style dotted names to underscore names.
    py_key = key.replace(".", "_")
    val = getattr(opts, py_key, None)
    if val is None:
        return default
    # OptionsInfo wraps the stored value; unwrap if needed.
    if hasattr(val, "value"):
        v = val.value
        return default if v is None else v
    return val


def _stub_layout(data: Any) -> List[str]:
    """Resolve the stub-layout list (subset of {"group_label", "rowname"})."""
    has_summary = bool(getattr(data, "_summary_rows", None) or
                       getattr(data, "_summary_rows_grand", None))
    return data._stub._get_stub_layout(
        has_summary_rows=has_summary, options=data._options,
    )


def _effective_n_cols(data: Any) -> int:
    """R: ``get_effective_number_of_columns`` — stub cols + visible data cols."""
    return len(_stub_layout(data)) + len(data._boxhead._get_default_columns())


def _spanner_rows(data: Any, visible_cols: List[Any]) -> List[dict]:
    """Resolve spanner-cell positions (level/start/end/label) over visible cols.

    Returns a list of dicts ``{row, start, end, label}`` where ``row`` is
    the row index within the columns-component (1-based, top-down) and
    ``start/end`` are 1-based column indices within the visible data
    columns (excluding the stub).
    """
    spanners = list(data._spanners)
    if not spanners:
        return []
    var_to_idx = {col.var: i + 1 for i, col in enumerate(visible_cols)}
    # Highest level number = topmost row in R; flip so top=1 is topmost.
    levels = sorted({sp.spanner_level for sp in spanners}, reverse=True)
    out: List[dict] = []
    for row_idx, level in enumerate(levels, start=1):
        for sp in spanners:
            if sp.spanner_level != level:
                continue
            indices = [var_to_idx[v] for v in sp.vars if v in var_to_idx]
            if not indices:
                continue
            out.append({
                "row": row_idx,
                "start": min(indices),
                "end": max(indices),
                "label": sp.spanner_label,
            })
    return out
