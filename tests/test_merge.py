"""Smoke tests for :func:`patchwork.merge`.

Ports R's ``R/merge.R``. Verifies the single-dispatch behaviour:

- ``merge(ggplot)`` is the identity (R's ``merge.ggplot``).
- ``merge(patchwork)`` wraps the composition as a single child under a
  filler, creating a 1-level deep patchwork (R's ``merge.patchwork``).

R behaviour for reference::

    > p <- ggplot(mtcars) + geom_point(aes(mpg, disp))
    > identical(merge(p), p)
    [1] TRUE
    > pw <- p + p
    > length(merge(pw)$patches$plots)
    [1] 1  # the inner patchwork is now a single child
"""
from __future__ import annotations

import pandas as pd
from ggplot2_py import aes, geom_point, ggplot

from patchwork import merge, wrap_plots
from patchwork.add_plot import Patchwork


def _mkdf() -> pd.DataFrame:
    return pd.DataFrame({"x": [1, 2, 3, 4], "y": [1, 2, 3, 4]})


def test_merge_ggplot_is_identity():
    """``merge.ggplot(p)`` returns *p* unchanged (R's merge.R:11-13)."""
    p = ggplot(_mkdf()) + geom_point(aes(x="x", y="y"))
    result = merge(p)
    assert result is p


def test_merge_patchwork_demotes_to_single_child():
    """``merge.patchwork(pw)`` returns a fresh Patchwork with ``pw`` as
    its only entry in ``patches.plots`` (R's merge.R:3-8)."""
    p1 = ggplot(_mkdf()) + geom_point(aes(x="x", y="y"))
    p2 = ggplot(_mkdf()) + geom_point(aes(x="x", y="y"))
    pw = wrap_plots([p1, p2])
    result = merge(pw)

    assert isinstance(result, Patchwork)
    assert len(result.patches.plots) == 1
    assert result.patches.plots[0] is pw


def test_merge_dispatch_default_is_identity():
    """Unknown types fall through the default dispatch unchanged."""
    sentinel = object()
    assert merge(sentinel) is sentinel
