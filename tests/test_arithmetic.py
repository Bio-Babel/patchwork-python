"""Unit tests for plot arithmetic operators (Slice 4)."""

from __future__ import annotations

import pandas as pd
import pytest
from ggplot2_py import aes, geom_point, ggplot, theme_bw

import patchwork as pw
from patchwork import Patchwork


@pytest.fixture
def p1():
    df = pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]})
    return ggplot(df, aes(x="x", y="y")) + geom_point()


@pytest.fixture
def p2():
    df = pd.DataFrame({"x": [4, 5, 6], "y": [4, 5, 6]})
    return ggplot(df, aes(x="x", y="y")) + geom_point()


class TestAddition:
    def test_ggplot_plus_ggplot(self, p1, p2):
        result = p1 + p2
        assert isinstance(result, Patchwork)
        assert len(result) == 2

    def test_add_plot_layout(self, p1, p2):
        result = (p1 + p2) + pw.plot_layout(ncol=2)
        assert result.patches.layout.ncol == 2

    def test_add_plot_annotation(self, p1, p2):
        result = (p1 + p2) + pw.plot_annotation(title="Hi")
        assert result.patches.annotation.title == "Hi"


class TestMinus:
    def test_ggplot_minus_ggplot(self, p1, p2):
        result = p1 - p2
        assert isinstance(result, Patchwork)
        assert len(result) == 2

    def test_none_identity_left(self, p1):
        result = p1 - None
        assert result is p1


class TestOr:
    def test_or_sets_nrow(self, p1, p2):
        result = p1 | p2
        assert isinstance(result, Patchwork)
        assert result.patches.layout.nrow == 1


class TestTruediv:
    def test_div_sets_ncol(self, p1, p2):
        result = p1 / p2
        assert isinstance(result, Patchwork)
        assert result.patches.layout.ncol == 1


class TestMulAnd:
    def test_and_wraps_into_patchwork(self, p1, p2):
        result = (p1 + p2) & theme_bw()
        assert isinstance(result, Patchwork)

    def test_mul_wraps_into_patchwork(self, p1, p2):
        result = (p1 + p2) * theme_bw()
        assert isinstance(result, Patchwork)
