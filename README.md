# patchwork-python

[![PyPI](https://img.shields.io/pypi/v/patchwork-python)](https://pypi.org/project/patchwork-python/)

Python port of the R [`patchwork`](https://patchwork.data-imaginist.com/) package.

`patchwork` lets you compose multiple `ggplot` figures into a single layout
using arithmetic-style operators — same idea here, same operators, on top of
[`ggplot2-python`](https://github.com/Bio-Babel/ggplot2-python):

```python
import patchwork  # installs the | / + - dunders on GGPlot
from ggplot2_py import ggplot, aes, geom_point

p1 = ggplot(df) + geom_point(aes("x", "y"))
p2 = ggplot(df) + geom_point(aes("x", "z"))

p1 | p2          # side-by-side
p1 / p2          # stacked
(p1 | p2) / p3   # nested
```

## Where it fits in the Bio-Babel R-port stack

```
patchwork-python    <-- this repo: composing ggplots
        |
        +-- ggplot2-python      grammar of graphics
        +-- rgrid-python        viewport / unit / Cairo backend
        +-- gtable-python       layout-aware grob tables
        +-- scales-python       scale transformations
        +-- great_tables        (optional) backend for wrap_table()
```

## Install

```bash
pip install patchwork-python
pip install "patchwork-python[tables]"   # adds great_tables for wrap_table()
```

## Figure size

Jupyter's `_repr_png_` has no current graphics device, so render size lives on
the plot object. Defaults are `7.0 × 5.0 in @ 150 dpi`
(`patchwork/_display.py`).

```python
pw = p1 | p2
pw.fig_width = 12
pw.fig_height = 8
pw.fig_dpi = 200
pw   # renders at 12×8 @ 200 dpi
```

`Patchwork._repr_png_` resolves hints in this order: `self` → `self.plot` →
defaults. So `p.fig_width = 12; p | q` propagates without re-setting on the
wrapper. A bare `Patch` reads from its inner plot only (`Patch.__slots__`
blocks per-instance attrs).

> R contrast: none. R routes size through the active graphics device
> (`png()`, `knitr` chunk options, RStudio plot pane). The `fig_*` protocol
> is a Python-only carry-over from `ggplot2_py.GGPlot`.

## Documentation

Tutorials are mirrored to `docs/tutorials/` and rendered via mkdocs:

```bash
pip install -e ".[docs]"
mkdocs serve
```