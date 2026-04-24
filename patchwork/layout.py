"""``plot_layout()``, ``area()``, and the design-string parser.

Ports ``R/plot_layout.R``. Design-string parsing is the same as R:

```
"1##
 123
 ##3"
```

becomes three rectangular ``PatchArea`` cells addressing rows 1–3 and
columns 1–3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence, Union

from ._utils import WAIVER, arg_match, is_waiver

__all__ = [
    "PatchArea",
    "area",
    "as_areas",
    "plot_layout",
    "PlotLayout",
    "default_layout",
    "create_design",
]


@dataclass
class PatchArea:
    """One or many rectangular layout cells.

    The four coordinate lists (``t``, ``l``, ``b``, ``r``) have the same length
    ``n``; each index picks out a single cell. Empty ``PatchArea`` (``n == 0``)
    is the result of ``area()`` with no arguments.
    """

    t: list[int] = field(default_factory=list)
    l: list[int] = field(default_factory=list)
    b: list[int] = field(default_factory=list)
    r: list[int] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.t)

    def __add__(self, other: "PatchArea") -> "PatchArea":
        """Concatenate two ``PatchArea`` objects (like R's ``c.patch_area``)."""
        if not isinstance(other, PatchArea):
            return NotImplemented
        return PatchArea(
            t=list(self.t) + list(other.t),
            l=list(self.l) + list(other.l),
            b=list(self.b) + list(other.b),
            r=list(self.r) + list(other.r),
        )

    def __repr__(self) -> str:
        if len(self) == 0:
            return "PatchArea(<empty>)"
        lines = [
            f"{len(self)} patch areas, spanning {max(self.r)} columns and {max(self.b)} rows",
        ]
        for i, (t, l, b, r) in enumerate(zip(self.t, self.l, self.b, self.r), start=1):
            lines.append(f"  {i}: t={t} l={l} b={b} r={r}")
        return "\n".join(lines)

    def as_records(self) -> list[dict[str, int]]:
        """Return the area as a list of ``{t, l, b, r}`` dicts."""
        return [
            {"t": t, "l": l, "b": b, "r": r}
            for t, l, b, r in zip(self.t, self.l, self.b, self.r)
        ]


def _rep_len_int(x: Any, length: int) -> list[int]:
    if not isinstance(x, (list, tuple)):
        x = [x]
    if len(x) == 0:
        raise ValueError("empty input to `rep_len`")
    out: list[int] = [int(v) for v in x]
    while len(out) < length:
        out.append(out[len(out) % len(x)])
    return out[:length]


def area(
    t: Union[int, Sequence[int], None] = None,
    l: Union[int, Sequence[int], None] = None,
    b: Union[int, Sequence[int], None] = None,
    r: Union[int, Sequence[int], None] = None,
) -> PatchArea:
    """Specify one or more rectangular plotting areas.

    Parameters
    ----------
    t, l : int or sequence of int
        Top and left bounds (1-based, inclusive). If both are ``None``,
        an empty ``PatchArea`` is returned.
    b, r : int or sequence of int, optional
        Bottom and right bounds. Default to *t* and *l* respectively
        (single-cell).

    Returns
    -------
    PatchArea
        Layout specification.

    Raises
    ------
    ValueError
        If any ``t > b`` or ``l > r``.
    """
    if t is None or l is None:
        return PatchArea()

    if b is None:
        b = t
    if r is None:
        r = l

    t_list = t if isinstance(t, (list, tuple)) else [t]
    l_list = l if isinstance(l, (list, tuple)) else [l]
    b_list = b if isinstance(b, (list, tuple)) else [b]
    r_list = r if isinstance(r, (list, tuple)) else [r]
    length = max(len(t_list), len(l_list), len(b_list), len(r_list))

    t_vals = _rep_len_int(t_list, length)
    l_vals = _rep_len_int(l_list, length)
    b_vals = _rep_len_int(b_list, length)
    r_vals = _rep_len_int(r_list, length)

    if any(ti > bi for ti, bi in zip(t_vals, b_vals)):
        raise ValueError("`t` must be less than or equal to `b`")
    if any(li > ri for li, ri in zip(l_vals, r_vals)):
        raise ValueError("`l` must be less than or equal to `r`")

    return PatchArea(t=t_vals, l=l_vals, b=b_vals, r=r_vals)


def _area_from_string(x: str) -> PatchArea:
    """Parse a multi-line design string into a ``PatchArea``.

    Accepts R-style:

    ```
    "A##\nA#B\n##B"
    ```

    Rules: rows are split on ``\\n``, leading / trailing blank rows dropped,
    each row stripped of surrounding whitespace, every non-whitespace
    character is one cell, ``#`` (or any symbol that maps to ``NA``) is a
    hole. Each unique symbol's covered cells must form a rectangle.
    """
    lines = x.split("\n")
    lines = [ln.strip() for ln in lines]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return PatchArea()
    widths = {len(ln) for ln in lines}
    if len(widths) != 1:
        raise ValueError("design string must be rectangular")
    n_cols = widths.pop()

    cells: list[tuple[int, int, str]] = []
    for row_idx, ln in enumerate(lines, start=1):
        for col_idx, ch in enumerate(ln, start=1):
            cells.append((row_idx, col_idx, ch))

    by_symbol: dict[str, list[tuple[int, int]]] = {}
    for r, c, sym in cells:
        if sym == "#":
            continue
        by_symbol.setdefault(sym, []).append((r, c))

    areas: list[PatchArea] = []
    for sym in sorted(by_symbol.keys()):
        cells_for_sym = by_symbol[sym]
        rows = [rc[0] for rc in cells_for_sym]
        cols = [rc[1] for rc in cells_for_sym]
        t_min, t_max = min(rows), max(rows)
        l_min, l_max = min(cols), max(cols)
        expected = {(rr, cc) for rr in range(t_min, t_max + 1) for cc in range(l_min, l_max + 1)}
        actual = set(cells_for_sym)
        if actual != expected:
            raise ValueError("patch areas must be rectangular")
        areas.append(area(t=t_min, l=l_min, b=t_max, r=l_max))

    if not areas:
        return PatchArea()
    result = areas[0]
    for a in areas[1:]:
        result = result + a
    return result


def as_areas(x: Any) -> Optional[PatchArea]:
    """Coerce *x* to a ``PatchArea``, accepting strings, existing areas, or None."""
    if x is None:
        return None
    if isinstance(x, PatchArea):
        return x
    if isinstance(x, str):
        return _area_from_string(x)
    raise TypeError(f"cannot convert {type(x).__name__} to a patch area")


@dataclass
class PlotLayout:
    """Structured return type of :func:`plot_layout`."""

    ncol: Any = field(default=WAIVER)
    nrow: Any = field(default=WAIVER)
    byrow: Any = field(default=WAIVER)
    widths: Any = field(default=WAIVER)
    heights: Any = field(default=WAIVER)
    guides: Any = field(default=WAIVER)
    tag_level: Any = field(default=WAIVER)
    design: Any = field(default=WAIVER)
    axes: Any = field(default=WAIVER)
    axis_titles: Any = field(default=WAIVER)

    def items(self):  # pragma: no cover — iter helper
        return [
            (k, getattr(self, k))
            for k in (
                "ncol",
                "nrow",
                "byrow",
                "widths",
                "heights",
                "guides",
                "tag_level",
                "axes",
                "axis_titles",
                "design",
            )
        ]


def plot_layout(
    ncol: Any = WAIVER,
    nrow: Any = WAIVER,
    byrow: Any = WAIVER,
    widths: Any = WAIVER,
    heights: Any = WAIVER,
    guides: Any = WAIVER,
    tag_level: Any = WAIVER,
    design: Any = WAIVER,
    axes: Any = WAIVER,
    axis_titles: Any = WAIVER,
) -> PlotLayout:
    """Define the grid to compose plots in.

    Parameters
    ----------
    ncol, nrow : int, optional
        Grid dimensions. If both ``None``, ``wrap_dims`` picks a default.
    byrow : bool, optional
        If ``False``, fill column-major instead of row-major.
    widths, heights : sequence of float, optional
        Relative cell widths/heights, recycled to fit the grid.
    guides : {'auto', 'collect', 'keep'}, optional
        How guides should be gathered across the current level.
    tag_level : {'keep', 'new'}, optional
        Whether nested patches continue the parent's tag sequence or
        start a fresh level.
    design : str or PatchArea, optional
        Custom layout specification, either as a multi-line string or a
        concatenation of :func:`area` calls.
    axes : {'keep', 'collect', 'collect_x', 'collect_y'}, optional
        Whether duplicated axes are removed within rows/columns.
    axis_titles : {'keep', 'collect', 'collect_x', 'collect_y'}, optional
        Same but for axis titles. Defaults to ``axes``.

    Returns
    -------
    PlotLayout
        A layout specification to be added to a patchwork via ``+``.
    """
    if guides is not None and not is_waiver(guides):
        guides = arg_match(guides, ("auto", "collect", "keep"), arg="guides")
    if tag_level is not None and not is_waiver(tag_level):
        tag_level = arg_match(tag_level, ("keep", "new"), arg="tag_level")
    if axes is not None and not is_waiver(axes):
        axes = arg_match(axes, ("keep", "collect", "collect_x", "collect_y"), arg="axes")
    if axis_titles is not None and not is_waiver(axis_titles):
        axis_titles = arg_match(
            axis_titles,
            ("keep", "collect", "collect_x", "collect_y"),
            arg="axis_titles",
        )
    parsed_design = design if is_waiver(design) else as_areas(design)

    return PlotLayout(
        ncol=ncol,
        nrow=nrow,
        byrow=byrow,
        widths=widths,
        heights=heights,
        guides=guides,
        tag_level=tag_level,
        axes=axes,
        axis_titles=axis_titles,
        design=parsed_design,
    )


#: Default layout used when the user never touches ``plot_layout()``.
default_layout = PlotLayout(
    ncol=None,
    nrow=None,
    byrow=True,
    widths=float("nan"),
    heights=float("nan"),
    guides="auto",
    tag_level="keep",
    design=None,
    axes="keep",
    axis_titles="keep",
)


def create_design(width: int, height: int, byrow: bool) -> PatchArea:
    """Build a row-/column-major grid of single-cell areas.

    Mirrors R's ``create_design``: fills a ``height × width`` matrix with
    1..n (row-major iff *byrow*) and emits one ``area()`` call per integer
    covering the cell that holds it.
    """
    n = width * height
    if byrow:
        matrix = [[r * width + c + 1 for c in range(width)] for r in range(height)]
    else:
        matrix = [
            [c * height + r + 1 for c in range(width)] for r in range(height)
        ]

    positions: dict[int, tuple[int, int]] = {}
    for r in range(height):
        for c in range(width):
            positions[matrix[r][c]] = (r + 1, c + 1)

    t_list = [positions[i][0] for i in range(1, n + 1)]
    l_list = [positions[i][1] for i in range(1, n + 1)]
    return area(t=t_list, l=l_list)
