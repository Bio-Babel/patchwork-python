"""``patchwork._display`` — gtable_to_png smoke + edge cases.

The display helper renders a Gtable to PNG bytes via grid_py's Cairo
backend. Tests exercise the full render pipeline end-to-end and would
catch regressions in (a) backend wiring, (b) PNG mime/header,
(c) device sizing.
"""
from __future__ import annotations

import pytest
from ggplot2_py import aes, geom_point, ggplot

from patchwork import patchworkGrob
from patchwork._display import gtable_to_png


@pytest.fixture
def small_pw():
    from patchwork._datasets import mtcars
    df = mtcars().reset_index().head(8)
    p1 = ggplot(df) + geom_point(aes(x="mpg", y="disp"))
    p2 = ggplot(df) + geom_point(aes(x="hp", y="wt"))
    return p1 | p2


class TestGtableToPng:

    def test_renders_nonempty_png(self, small_pw):
        gt = patchworkGrob(small_pw)
        img = gtable_to_png(gt, width=4, height=3, dpi=72)
        assert isinstance(img, (bytes, bytearray))
        assert len(img) > 1000  # at least 1 KB
        # PNG magic header: \x89PNG\r\n\x1a\n
        assert img[:8] == b"\x89PNG\r\n\x1a\n"

    def test_dpi_changes_byte_size(self, small_pw):
        gt = patchworkGrob(small_pw)
        img_low = gtable_to_png(gt, width=4, height=3, dpi=50)
        img_high = gtable_to_png(gt, width=4, height=3, dpi=150)
        # Higher DPI = more pixels = larger PNG. Allow some slack
        # because PNG is compressed and the relationship isn't linear,
        # but high dpi should be substantially larger than low dpi.
        assert len(img_high) > len(img_low)

    def test_aspect_ratios(self, small_pw):
        gt = patchworkGrob(small_pw)
        # All three sizings must produce a valid PNG.
        for w, h in [(2, 4), (4, 2), (3, 3)]:
            img = gtable_to_png(gt, width=w, height=h, dpi=72)
            assert img[:8] == b"\x89PNG\r\n\x1a\n", f"failed at {w}x{h}"


class TestSafeReprPng:
    """``safe_repr_png`` is the Jupyter ``_repr_png_`` shared body.

    Contract: never raise. Errors surface as cli_warn + return None.
    """

    def test_safe_repr_png_returns_bytes(self, small_pw):
        from patchwork._display import safe_repr_png

        img = safe_repr_png(lambda: patchworkGrob(small_pw))
        assert img is not None
        assert img[:8] == b"\x89PNG\r\n\x1a\n"

    def test_safe_repr_png_returns_none_on_none_gtable(self):
        from patchwork._display import safe_repr_png

        # build_gtable returns None → safe_repr_png returns None.
        assert safe_repr_png(lambda: None) is None

    def test_safe_repr_png_swallows_exceptions(self):
        from patchwork._display import safe_repr_png

        def failing_builder():
            raise RuntimeError("intentional test failure")

        # Must not raise — returns None and logs via cli_warn.
        result = safe_repr_png(failing_builder)
        assert result is None

    def test_safe_repr_png_propagates_keyboard_interrupt(self):
        from patchwork._display import safe_repr_png

        def interrupted():
            raise KeyboardInterrupt()

        # KeyboardInterrupt / SystemExit MUST propagate.
        import pytest as _pt
        with _pt.raises(KeyboardInterrupt):
            safe_repr_png(interrupted)
