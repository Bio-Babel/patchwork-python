# patchwork-python

**patchwork-python** is a Python port of the R
[`patchwork`](https://patchwork.data-imaginist.com/) package by Thomas Lin
Pedersen. It extends `ggplot2_py` so that multiple plots can be composed
into a single figure using arithmetic operators:

| Operator | Meaning                                                      |
|---       |---                                                           |
| `p1 + p2` | Append `p2` to the patchwork; `p2` becomes the active plot. |
| `p1 - p2` | Place `p1` and `p2` side-by-side at the same nesting level. |
| `p1 \| p2` | Stack horizontally (shortcut for `+ plot_layout(nrow=1)`). |
| `p1 / p2` | Stack vertically (shortcut for `+ plot_layout(ncol=1)`).    |
| `pw * x`  | Add `x` to every plot in the current nesting level.         |
| `pw & x`  | Add `x` to every plot recursively (including nested).        |

## Installation

```bash
pip install -e .
```

The package depends on editable installs of `ggplot2_py`, `gtable_py`,
`grid_py`, and `scales` (a.k.a. `scales_py`). Those are expected to be
available in the same environment.

## Quick start

```python
from ggplot2_py import aes, geom_point, ggplot, ggtitle
import patchwork as pw
from patchwork._datasets import mtcars

df = mtcars().reset_index()
p1 = ggplot(df) + geom_point(aes(x="mpg", y="disp")) + ggtitle("Plot 1")
p2 = ggplot(df) + geom_point(aes(x="wt", y="hp")) + ggtitle("Plot 2")

# Compose
(p1 | p2) + pw.plot_annotation(title="mtcars overview", tag_levels="A")
```

## Operator precedence caveat

Python's `/` and `*` bind tighter than `|` and `&`, so two R expressions
reparse differently in Python:

| Expression             | R parses as             | Python parses as           | Status       |
|---                     |---                      |---                         |---           |
| `p1 + p2 - p3`         | `(p1 + p2) - p3`        | `(p1 + p2) - p3`           | same         |
| `p1 + p2 \| p3`        | `(p1 + p2) \| p3`       | `(p1 + p2) \| p3`          | same         |
| `p1 \| p2 / p3`        | `(p1 \| p2) / p3`       | `p1 \| (p2 / p3)`          | **diverges** |
| `p1 + p2 * theme_bw()` | `(p1 + p2) * theme_bw()`| `p1 + (p2 * theme_bw())`   | **diverges** |

**Always parenthesize when mixing operators.**

## Deviations from R patchwork

A handful of features have an intentional divergence from the R behaviour
because the supporting R-only ecosystem has no Python analogue. Each is
documented in
[`port_reports/patchwork/08_validation.md`](https://github.com/...)
with a rationale.

- `wrap_table()` accepts `pandas.DataFrame` / `gtable_py.Gtable` instead
  of `gt_tbl`. Any `gt_tbl`-shaped object raises `NotImplementedError`.
- `as_patch.formula` / `ggplot_add.formula` (R's base-graphics bridge)
  raises `NotImplementedError`. Use `ggplot2_py` directly instead.
- The `recordGraphics` RStudio session lock has been removed.

## Tutorials

- [Getting Started](tutorials/patchwork.ipynb)
- [Plot Assembly](tutorials/assembly.ipynb)
- [Controlling Layouts](tutorials/layout.ipynb)
- [Adding Annotation and Style](tutorials/annotation.ipynb)
- [Alignment Across Multiple Pages](tutorials/multipage.ipynb)

## API reference

See the [API Reference](api.md) page for every public name and signature.
