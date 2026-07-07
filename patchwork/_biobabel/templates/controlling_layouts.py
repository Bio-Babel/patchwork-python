"""Layout control, from tutorials/layout.ipynb ("Controlling Layouts").

Demonstrates a text design string (letters + '#' for empty cells), a
plot_spacer() placeholder, and free() to stop one plot's long axis label
from bleeding whitespace into its neighbor. Uses only the tiny bundled
mtcars dataset — no network, no GUI, no files written.
"""

from __future__ import annotations

import patchwork as pw
from ggplot2_py import aes, geom_point, ggplot, ggtitle, labs
from patchwork._datasets import mtcars


def main() -> None:
    df = mtcars().reset_index()

    p1 = ggplot(df) + geom_point(aes(x="mpg", y="disp")) + ggtitle("Plot 1")
    p2 = ggplot(df) + geom_point(aes(x="mpg", y="hp")) + ggtitle("Plot 2")
    p3 = ggplot(df) + geom_point(aes(x="mpg", y="wt")) + ggtitle("Plot 3")
    p4 = ggplot(df) + geom_point(aes(x="mpg", y="qsec")) + ggtitle("Plot 4")

    design = """
    ##BBBB
    AACCDD
    ##CCDD
    """
    with_design = p1 + p2 + p3 + p4 + pw.plot_layout(design=design)

    with_spacer = p1 + pw.plot_spacer() + p2

    p2_long_label = p2 + labs(
        x="This is such a long\nand important label that\nit has to span many lines"
    )
    fixed = pw.free(p1) | p2_long_label

    for name, composed in (
        ("design string", with_design),
        ("spacer", with_spacer),
        ("free()", fixed),
    ):
        gt = pw.patchworkGrob(composed)
        print(f"{name}: rendered gtable with {len(gt.grobs)} grobs")


if __name__ == "__main__":
    main()
