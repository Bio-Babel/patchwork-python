"""Unit tests for ``collect_axes`` helpers (Slice 5)."""

from __future__ import annotations

import numpy as np

from patchwork.collect_axes import rle_2d


class TestRle2d:
    def test_all_same(self):
        m = np.array([[1, 1], [1, 1]])
        runs = rle_2d(m)
        assert len(runs) == 1
        assert runs[0]["value"] == 1
        assert runs[0]["row_start"] == 1 and runs[0]["row_end"] == 2
        assert runs[0]["col_start"] == 1 and runs[0]["col_end"] == 2

    def test_docstring_example(self):
        # The docstring example from R:
        # m = [[1, 1, 3],
        #      [1, 1, 3],
        #      [2, 2, 1]]
        m = np.array([[1, 1, 3], [1, 1, 3], [2, 2, 1]])
        runs = rle_2d(m)
        values = sorted([(r["row_start"], r["col_start"], r["value"]) for r in runs])
        assert (1, 1, 1) in values
        assert (3, 1, 2) in values
        assert (1, 3, 3) in values
        assert (3, 3, 1) in values

    def test_empty(self):
        m = np.zeros((0, 0), dtype=int)
        assert rle_2d(m) == []

    def test_all_unique(self):
        m = np.array([[1, 2], [3, 4]])
        runs = rle_2d(m)
        assert len(runs) == 4
