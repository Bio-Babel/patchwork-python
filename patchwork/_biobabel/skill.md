---
name: use-patchwork
description: Reach for patchwork when several ggplot2_py figures need to be composed into one multi-panel layout, tagged, annotated, or aligned across pages — not for building a single figure's grammar-of-graphics content.
---

# patchwork

Python port of R's `patchwork`. It composes `ggplot2_py.GGPlot` objects into a
single figure using arithmetic-style operators, and its own `+`-composable
config objects (`plot_layout`, `plot_annotation`) refine that composition.

`import patchwork` has a required side effect: it installs `|`, `/`, `-`,
`*`, `&` (and, via the `Patchwork` wrapper, `+`) onto `GGPlot`. Every
operator-based pattern below requires this import to have already run, even
if no `patchwork.*` name is called directly.

**Core mental model:**
- `p1 + p2` appends `p2` to a growing `Patchwork`; the most recently added
  plot is the "active" plot, so further `+ <ggplot-modifier>` (e.g.
  `+ theme_bw()`) targets *it*, not the whole composition.
- `|` (pack, side-by-side) and `/` (stack, vertical) are shortcuts for `+`
  followed by `plot_layout(nrow=1)` / `plot_layout(ncol=1)`. `-` keeps both
  sides at the *same* nesting level instead of nesting the LHS under the RHS.
- `plot_layout(...)` and `plot_annotation(...)` are themselves ordinary
  objects added with `+`; they mutate the growing `Patchwork`'s
  `.patches.layout` / `.patches.annotation` field-by-field, skipping any
  field left at its `WAIVER` default — so unspecified fields never clobber
  what a previous `plot_layout`/`plot_annotation` call already set.
- `pw * x` applies `x` to every plot at the *current* nesting level only;
  `pw & x` recurses into nested sub-patchworks too.
- **Python operator-precedence footgun** (no R equivalent): Python's `/` and
  `*` bind *tighter* than `|` and `&`, the opposite of R. `p1 | p2 / p3`
  parses as `p1 | (p2 / p3)` in Python but `(p1 | p2) / p3` in R. Always
  parenthesize when mixing operators.
- Non-ggplot content (grobs, `numpy` rasters, `pandas.DataFrame`/tables) must
  go through `wrap_elements()` / `wrap_table()` before composition; plain
  `+` auto-wraps when the non-ggplot object is on the *right*-hand side only.

## Quick reference

```python
import patchwork as pw
from ggplot2_py import ggplot, aes, geom_point

p1 = ggplot(df) + geom_point(aes("x", "y"))
p2 = ggplot(df) + geom_point(aes("x", "z"))

(p1 | p2) + pw.plot_annotation(title="Overview", tag_levels="A")
```

For more: `biobabel.describe_package(import_name="patchwork")`.
