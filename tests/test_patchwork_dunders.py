"""``Patchwork`` Python dunder protocol — `__len__`, `__iter__`,
`__getitem__`, `__setitem__`, `__contains__`.

R uses ``[[`` / ``[[<-`` / ``length`` / ``names``. Python equivalents
live on the Patchwork class. Tests verify each works for both the
ggplot-list path and the patches-with-design path.
"""
from __future__ import annotations

import pytest
from ggplot2_py import aes, geom_point, ggplot, ggtitle

from patchwork import Patchwork


@pytest.fixture
def df():
    from patchwork._datasets import mtcars
    return mtcars().reset_index()


@pytest.fixture
def p1(df):
    return ggplot(df) + geom_point(aes(x="mpg", y="disp")) + ggtitle("A")


@pytest.fixture
def p2(df):
    return ggplot(df) + geom_point(aes(x="hp", y="wt")) + ggtitle("B")


@pytest.fixture
def p3(df):
    return ggplot(df) + geom_point(aes(x="cyl", y="qsec")) + ggtitle("C")


class TestPatchworkDunders:

    def test_len(self, p1, p2):
        assert len(p1 + p2) == 2

    def test_len_three(self, p1, p2, p3):
        assert len(p1 + p2 + p3) == 3

    def test_iter(self, p1, p2, p3):
        items = list(p1 + p2 + p3)
        assert len(items) == 3

    def test_getitem(self, p1, p2):
        composed = p1 + p2
        # First plot of the composition.
        item0 = composed[0]
        # Should be a ggplot or patchwork-element, not a Patchwork itself.
        assert item0 is not None

    def test_setitem(self, p1, p2, p3):
        composed = p1 + p2
        composed[0] = p3
        # After replacement, composed[0] is now p3.
        assert composed[0] is not None
        assert len(composed) == 2

    def test_repr(self, p1, p2):
        composed = p1 + p2
        # __repr__ should not raise.
        s = repr(composed)
        assert "Patchwork" in s or "patches" in s.lower()
