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

## Documentation

Tutorials are mirrored to `docs/tutorials/` and rendered via mkdocs:

```bash
pip install -e ".[docs]"
mkdocs serve
```