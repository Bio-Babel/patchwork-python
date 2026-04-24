"""Axis and axis-title collection.

Ports ``R/collect_axes.R``. The three key helpers are:

- :func:`rle_2d` — 2-D run-length encoding, the core of the matcher.
- :func:`grob_id` — structural hashing for grob dedup across cells.
- :func:`collect_axes` / :func:`collect_axis_titles` — the public entry points.
"""

from __future__ import annotations

import hashlib
from typing import Any, List, Optional, Sequence

import numpy as np
from ggplot2_py import max_height, max_width
from grid_py import Unit
from gtable_py import Gtable

from ._utils import ave_max, ave_min, zero_grob
from .guides import unname_grob

__all__ = [
    "collect_axes",
    "collect_axis_titles",
    "rle_2d",
    "grob_id",
    "grob_layout",
    "retrofit_rows",
    "retrofit_cols",
    "delete_grobs",
    "is_zero",
]


def is_zero(x: Any) -> bool:
    """Return ``True`` if *x* is a zeroGrob / null grob / None.

    Works both on a single grob and on a list of grobs (vector-style).
    """
    if isinstance(x, list):
        return [_is_zero_single(v) for v in x]  # type: ignore[return-value]
    return _is_zero_single(x)


def _is_zero_single(x: Any) -> bool:
    if x is None:
        return True
    # null_grob from grid_py — detect by class name to stay loosely coupled.
    if type(x).__name__ in {"NullGrob", "ZeroGrob"}:
        return True
    # An empty GTree with no children is effectively a zero grob.
    children = getattr(x, "children", None)
    if children is not None and len(children) == 0:
        return True
    return False


def _hash_grob(x: Any) -> str:
    """Structural hash for comparing grobs after :func:`unname_grob`."""
    try:
        rep = repr(unname_grob(x))
    except Exception:
        rep = repr(x)
    return hashlib.md5(rep.encode("utf-8", errors="replace")).hexdigest()


def grob_id(
    grobs: Sequence[Any],
    layout: np.ndarray,
    byrow: bool = True,
    merge: bool = False,
    unpack: bool = False,
) -> np.ndarray:
    """Produce an integer-labelled array where equal grobs share a label.

    Parameters
    ----------
    grobs : sequence of grobs
        All grobs in the gtable.
    layout : ndarray
        Integer indices into *grobs* (0-based); ``-1`` denotes NA.
    byrow : bool
        If ``True``, extra multi-cell identifier spans columns.
    merge : bool
        If ``True``, treat same-hash grobs as one even when they occupy
        different cells.
    unpack : bool
        If ``True``, gtables with a single child are unpacked before hashing.
    """
    layout = np.asarray(layout, dtype=object)
    valid = layout != -1
    idx = [int(v) for v in layout[valid].tolist()]
    hashes: list[str] = []
    for i in idx:
        g = grobs[i]
        if unpack:
            try:
                from gtable_py import Gtable as _Gt

                if isinstance(g, _Gt) and len(g.grobs) == 1:
                    g = g.grobs[0]
            except Exception:
                pass
        hashes.append(_hash_grob(g))

    if not merge:
        if byrow:
            nrow, ncol = layout.shape
            col_matrix = np.tile(np.arange(1, ncol + 1), (nrow, 1))
            index = col_matrix
        else:
            nrow, ncol = layout.shape
            row_matrix = np.tile(np.arange(1, nrow + 1).reshape(-1, 1), (1, ncol))
            index = row_matrix
        flat_layout = layout.flatten()
        flat_valid = flat_layout != -1
        flat_valid_idx = np.arange(len(flat_layout))[flat_valid]
        flat_layout_valid = flat_layout[flat_valid].astype(int)
        flat_index = index.flatten()[flat_valid]

        min_per = ave_min(list(flat_index), list(flat_layout_valid))
        max_per = ave_max(list(flat_index), list(flat_layout_valid))
        for i_pos, base_hash in enumerate(hashes):
            hashes[i_pos] = f"{base_hash};{min_per[i_pos]};{max_per[i_pos]}"

    unique_hashes = list(dict.fromkeys(hashes))
    label_map = {h: i + 1 for i, h in enumerate(unique_hashes)}
    labels = [label_map[h] for h in hashes]

    out = np.full(layout.shape, -1, dtype=int)
    out_flat = out.flatten()
    idx_positions = np.where(layout.flatten() != -1)[0]
    for pos, label in zip(idx_positions, labels):
        out_flat[pos] = label
    return out_flat.reshape(layout.shape)


def grob_layout(gt: Gtable, idx: Sequence[int]) -> np.ndarray:
    """Build an integer layout matrix addressing grobs listed in *idx*.

    Returns a matrix ``new`` such that ``new[r, c]`` is the index into
    ``gt.grobs`` of the grob at cell ``(r, c)`` in the subset, or ``-1``
    when no grob covers that cell.
    """
    layout = gt.layout
    sub_t = [layout["t"][i] for i in idx]
    sub_l = [layout["l"][i] for i in idx]
    sub_b = [layout["b"][i] for i in idx]
    sub_r = [layout["r"][i] for i in idx]

    top = sorted(set(sub_t) | set(sub_b))
    left = sorted(set(sub_l) | set(sub_r))

    matrix = np.full((len(top), len(left)), -1, dtype=int)
    for k, (t, l, b, r) in enumerate(zip(sub_t, sub_l, sub_b, sub_r)):
        t_ii = top.index(t)
        b_ii = top.index(b)
        l_ii = left.index(l)
        r_ii = left.index(r)
        for rr in range(t_ii, b_ii + 1):
            for cc in range(l_ii, r_ii + 1):
                matrix[rr, cc] = idx[k]
    return matrix


def rle_2d(
    m: np.ndarray, byrow: bool = False, ignore_na: bool = False
) -> list[dict[str, int]]:
    """2-D run-length encoding: locate maximal same-valued rectangles in *m*.

    Returns a list of dicts with keys ``row_start``, ``row_end``,
    ``col_start``, ``col_end``, ``value``.
    """
    m = np.asarray(m)
    nrow, ncol = m.shape
    n = nrow * ncol
    if n == 0:
        return []

    if byrow:
        m_use = m.T
    else:
        m_use = m

    levels = list(dict.fromkeys(m_use.flatten().tolist()))
    if (ignore_na and sum(1 for lv in levels if lv != -1 and lv is not None) == 1) or len(levels) == 1:
        val = next((lv for lv in levels if lv != -1 and lv is not None), levels[0])
        row_start, row_end = 1, m.shape[0]
        col_start, col_end = 1, m.shape[1]
        return [
            {
                "row_start": row_start, "row_end": row_end,
                "col_start": col_start, "col_end": col_end, "value": val,
            }
        ]

    if len(levels) == n:
        out = []
        for rr in range(m.shape[0]):
            for cc in range(m.shape[1]):
                val = m[rr, cc]
                out.append(
                    {
                        "row_start": rr + 1, "row_end": rr + 1,
                        "col_start": cc + 1, "col_end": cc + 1, "value": val,
                    }
                )
        return out

    # General case: scan column-by-column (or row-by-row when byrow=True).
    d0, d1 = m_use.shape  # rows, cols in the "use" orientation
    runs: list[dict[str, Any]] = []
    for c in range(d1):
        i = 0
        while i < d0:
            v = m_use[i, c]
            j = i
            while j + 1 < d0 and m_use[j + 1, c] == v:
                j += 1
            # Try to merge with a run in the previous column.
            merged = False
            if c > 0:
                for run in runs:
                    if (run["col_end"] == c and run["row_start"] - 1 == i and run["row_end"] - 1 == j and run["value"] == v):
                        run["col_end"] = c + 1
                        merged = True
                        break
            if not merged:
                runs.append({"row_start": i + 1, "row_end": j + 1, "col_start": c + 1, "col_end": c + 1, "value": v})
            i = j + 1

    if byrow:
        runs = [
            {
                "row_start": r["col_start"], "row_end": r["col_end"],
                "col_start": r["row_start"], "col_end": r["row_end"],
                "value": r["value"],
            }
            for r in runs
        ]
    return runs


def collect_axis_titles(gt: Gtable, dir: str = "x", merge: bool = True) -> Gtable:
    """Merge duplicated axis titles along *dir* (either ``"x"`` or ``"y"``)."""
    if dir == "x":
        names = ["xlab-t", "xlab-b"]
    else:
        names = ["ylab-l", "ylab-r"]

    delete: list[int] = []
    for name in names:
        idx = [i for i, n in enumerate(gt.layout["name"]) if n.startswith(name)]
        if len(idx) < 2:
            continue
        if all(_is_zero_single(gt.grobs[i]) for i in idx):
            continue
        patch_index = [
            i for i, n in enumerate(gt.layout["name"]) if "panel-nested-patchwork" in n
        ]
        layout = grob_layout(gt, idx + patch_index)
        # Mark nested patchwork positions as NA.
        if patch_index:
            nested_mask = np.isin(layout, patch_index)
            layout[nested_mask] = -1

        structure = grob_id(
            gt.grobs, layout, byrow=(dir == "x"), merge=merge, unpack=True,
        )
        flat_struct = structure.flatten()
        present = flat_struct[flat_struct != -1]
        if len(set(present.tolist())) == len(present):
            continue

        runs = rle_2d(structure, byrow=(dir == "y"), ignore_na=True)
        # Mirror R collect_axes.R:42 — the `!= 0` gate is intentional and
        # asymmetric with collect_axes (R:127): here we also skipped the
        # nested patchwork cells by setting their structure value to 0
        # above, so runs of value 0 must be excluded. Do not "simplify"
        # this to match collect_axes.
        runs = [r for r in runs if r["value"] != -1 and r["value"] != 0]

        panels_list = []
        title_grob = []
        for run in runs:
            rs, re = run["row_start"] - 1, run["row_end"] - 1
            cs, ce = run["col_start"] - 1, run["col_end"] - 1
            if name == "xlab-t":
                first_row = layout[rs, cs:ce + 1]
            elif name == "xlab-b":
                first_row = layout[re, cs:ce + 1]
            elif name == "ylab-l":
                first_row = layout[rs:re + 1, cs]
            else:
                first_row = layout[rs:re + 1, ce]
            first_valid = next((int(v) for v in first_row.tolist() if v != -1), None)
            if first_valid is None:
                continue
            panels_in_run = layout[rs:re + 1, cs:ce + 1].flatten().tolist()
            panels_in_run = [int(p) for p in panels_in_run if p != -1]
            panels_list.append([first_valid] + [p for p in panels_in_run if p != first_valid])
            title_grob.append(first_valid)

        for i in idx:
            if i not in title_grob:
                delete.append(i)

        if (dir == "x" and all(r["col_start"] == r["col_end"] for r in runs)) or (
            dir == "y" and all(r["row_start"] == r["row_end"] for r in runs)
        ):
            continue

        for tg, panels in zip(title_grob, panels_list):
            if dir == "y":
                gt.layout["t"][tg] = min(gt.layout["t"][i] for i in panels)
                gt.layout["b"][tg] = max(gt.layout["b"][i] for i in panels)
                gt.layout["z"][tg] = max(gt.layout["z"][i] for i in idx)
            else:
                gt.layout["l"][tg] = min(gt.layout["l"][i] for i in panels)
                gt.layout["r"][tg] = max(gt.layout["r"][i] for i in panels)
                gt.layout["z"][tg] = max(gt.layout["z"][i] for i in idx)

    return delete_grobs(gt, delete)


def collect_axes(gt: Gtable, dir: str = "x") -> Gtable:
    """Remove duplicated axes along *dir*, then resize bare axis rows/columns."""
    if dir == "x":
        names = ["axis-b", "axis-t"]
    else:
        names = ["axis-l", "axis-r"]

    delete: list[int] = []
    for name in names:
        idx = [i for i, n in enumerate(gt.layout["name"]) if n.startswith(name)]
        if len(idx) < 2:
            continue
        if all(_is_zero_single(gt.grobs[i]) for i in idx):
            continue
        patch_index = [
            i for i, n in enumerate(gt.layout["name"]) if "panel-nested-patchwork" in n
        ]
        layout = grob_layout(gt, idx + patch_index)
        if patch_index:
            nested_mask = np.isin(layout, patch_index)
            layout[nested_mask] = -1

        structure = grob_id(gt.grobs, layout, byrow=(dir == "x"), merge=False)
        flat_struct = structure.flatten()
        present = flat_struct[flat_struct != -1]
        if len(set(present.tolist())) == len(present):
            continue

        runs = rle_2d(structure, byrow=(dir == "y"))
        # Mirror R collect_axes.R:127 — no `!= 0` gate here; only NA
        # (represented as -1) is filtered out. The 0-gate belongs to
        # collect_axis_titles (R:42) which sets nested-patchwork cells
        # to 0 via an explicit write; this function never performs
        # that write, so there is nothing to filter.
        runs = [r for r in runs if r["value"] != -1]

        # Collect the "keeper" grob index for every run — R computes
        # start_idx <- layout[as.matrix(runs[, start_runs])] in one shot
        # (collect_axes.R:133), then does a single setdiff(idx, start_idx)
        # per axis name. Doing it per-run the way the previous code did
        # marks every run's own keeper for deletion under every other
        # run's iteration, collapsing all axes away.
        start_idx: list[int] = []
        for r in runs:
            rs = (r["row_end"] if name == "axis-b" else r["row_start"]) - 1
            cs = (r["col_end"] if name == "axis-r" else r["col_start"]) - 1
            v = int(layout[rs, cs])
            if v != -1:
                start_idx.append(v)

        start_set = set(start_idx)
        delete.extend(i for i in idx if i not in start_set)

    deleted_rows = sorted(set(
        gt.layout["t"][i] for i in delete
    ) | set(gt.layout["b"][i] for i in delete))
    deleted_cols = sorted(set(
        gt.layout["l"][i] for i in delete
    ) | set(gt.layout["r"][i] for i in delete))

    new = delete_grobs(gt, delete)
    new = retrofit_rows(new, deleted_rows, pattern="axis")
    new = retrofit_cols(new, deleted_cols, pattern="axis")
    return new


def retrofit_rows(gt: Gtable, rows: Sequence[int], pattern: str = "axis") -> Gtable:
    """Resize rows whose remaining grobs all match *pattern*."""
    if not rows:
        return gt
    for row in rows:
        grobs_in_row = [
            gt.grobs[i] for i, (t, b) in enumerate(zip(gt.layout["t"], gt.layout["b"]))
            if (t == row or b == row) and not _is_zero_single(gt.grobs[i])
        ]
        names_in_row = [
            gt.layout["name"][i] for i, (t, b) in enumerate(zip(gt.layout["t"], gt.layout["b"]))
            if (t == row or b == row) and not _is_zero_single(gt.grobs[i])
        ]
        if not grobs_in_row:
            continue
        if all(pattern in n for n in names_in_row):
            try:
                size = max_height(grobs_in_row)
            except Exception:
                continue
            values = list(gt.heights.values)
            units = list(gt.heights.units_list)
            if isinstance(size, Unit):
                values[row - 1] = size.values[0]
                units[row - 1] = size.units_list[0]
            gt.heights = Unit(values, units)
    return gt


def retrofit_cols(gt: Gtable, cols: Sequence[int], pattern: str = "axis") -> Gtable:
    """Resize columns whose remaining grobs all match *pattern*."""
    if not cols:
        return gt
    for col in cols:
        grobs_in_col = [
            gt.grobs[i] for i, (l, r) in enumerate(zip(gt.layout["l"], gt.layout["r"]))
            if (l == col or r == col) and not _is_zero_single(gt.grobs[i])
        ]
        names_in_col = [
            gt.layout["name"][i] for i, (l, r) in enumerate(zip(gt.layout["l"], gt.layout["r"]))
            if (l == col or r == col) and not _is_zero_single(gt.grobs[i])
        ]
        if not grobs_in_col:
            continue
        if all(pattern in n for n in names_in_col):
            try:
                size = max_width(grobs_in_col)
            except Exception:
                continue
            values = list(gt.widths.values)
            units = list(gt.widths.units_list)
            if isinstance(size, Unit):
                values[col - 1] = size.values[0]
                units[col - 1] = size.units_list[0]
            gt.widths = Unit(values, units)
    return gt


def delete_grobs(gt: Gtable, idx: Sequence[int], resize: bool = True) -> Gtable:
    """Drop *idx* positions from *gt.layout* and *gt.grobs*.

    Optionally resize rows/columns that become empty after removal.
    """
    if not idx:
        return gt
    keep = [i for i in range(len(gt.grobs)) if i not in idx]
    if resize:
        resize_rows = list({gt.layout["t"][i] for i in idx})
        resize_cols = list({gt.layout["l"][i] for i in idx})

    new_grobs = [gt.grobs[i] for i in keep]
    new_layout = {k: [v[i] for i in keep] for k, v in gt.layout.items()}
    gt.grobs = new_grobs
    gt.layout = new_layout

    if not resize:
        return gt

    zero_mask = [_is_zero_single(g) for g in gt.grobs]
    used_rows = set(
        gt.layout["t"][i] for i in range(len(gt.grobs)) if not zero_mask[i]
    ) | set(
        gt.layout["b"][i] for i in range(len(gt.grobs)) if not zero_mask[i]
    )
    used_cols = set(
        gt.layout["l"][i] for i in range(len(gt.grobs)) if not zero_mask[i]
    ) | set(
        gt.layout["r"][i] for i in range(len(gt.grobs)) if not zero_mask[i]
    )

    rows_to_zero = [r for r in resize_rows if r not in used_rows]
    cols_to_zero = [c for c in resize_cols if c not in used_cols]
    if rows_to_zero:
        values = list(gt.heights.values)
        units = list(gt.heights.units_list)
        for r in rows_to_zero:
            values[r - 1] = 0.0
            units[r - 1] = "pt"
        gt.heights = Unit(values, units)
    if cols_to_zero:
        values = list(gt.widths.values)
        units = list(gt.widths.units_list)
        for c in cols_to_zero:
            values[c - 1] = 0.0
            units[c - 1] = "pt"
        gt.widths = Unit(values, units)
    return gt
