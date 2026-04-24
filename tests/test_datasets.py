"""Unit tests for embedded datasets (Slice 0)."""

from __future__ import annotations

import pandas as pd

from patchwork._datasets import iris, mtcars


def test_mtcars_shape():
    df = mtcars()
    assert df.shape == (32, 11)


def test_mtcars_columns():
    df = mtcars()
    # The R dataset columns in order, minus the row names column.
    expected = {"mpg", "cyl", "disp", "hp", "drat", "wt", "qsec", "vs", "am", "gear", "carb"}
    assert set(df.columns) == expected


def test_iris_shape():
    df = iris()
    assert df.shape == (150, 5)


def test_iris_species_values():
    df = iris()
    assert set(df["Species"].unique()) == {"setosa", "versicolor", "virginica"}


def test_returns_a_copy():
    a = mtcars()
    a["mpg"] = 0.0
    b = mtcars()
    assert (b["mpg"] > 0).all()
