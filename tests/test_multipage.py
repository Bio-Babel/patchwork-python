"""Unit tests for ``multipage`` (Slice 6)."""

from __future__ import annotations

import pandas as pd
import pytest
from ggplot2_py import aes, geom_point, ggplot

import patchwork as pw
from patchwork.multipage import (
    GGPlotDimension,
    PlotDimension,
    align_patches,
    align_plots,
    get_dim,
    get_max_dim,
    set_dim,
)


@pytest.fixture
def plots():
    df = pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]})
    return [
        ggplot(df, aes(x="x", y="y")) + geom_point() for _ in range(3)
    ]


def test_get_dim_on_ggplot_returns_dimension(plots):
    dim = get_dim(plots[0])
    assert isinstance(dim, GGPlotDimension)
    assert len(dim.l) > 0
    assert len(dim.t) > 0


def test_get_dim_on_patchwork_raises(plots):
    pw_obj = plots[0] + plots[1]
    with pytest.raises(RuntimeError):
        get_dim(pw_obj)


def test_get_max_dim_returns_plot_dimension(plots):
    dim = get_max_dim(plots)
    assert isinstance(dim, PlotDimension)


def test_set_dim_round_trip(plots):
    dim = get_dim(plots[0])
    out = set_dim(plots[1], dim)
    assert getattr(out, "_ptw_fixed_dim", False)


def test_align_patches(plots):
    aligned = align_patches(plots)
    assert len(aligned) == 3
    assert all(getattr(p, "_ptw_fixed_dim", False) for p in aligned)


def test_align_plots_emits_deprecation(plots):
    with pytest.warns(DeprecationWarning):
        aligned = align_plots(*plots)
    assert len(aligned) == 3
