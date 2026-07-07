"""Cross-page alignment, from tutorials/multipage.ipynb
("Alignment Across Multiple Pages").

Aligns several independently-rendered plots (never composed into one
Patchwork) so their outer margins match when shown one after another, e.g.
across slides or PDF pages. Uses only the tiny bundled mtcars dataset — no
network, no GUI, no files written.
"""

from __future__ import annotations

import patchwork as pw
from ggplot2_py import aes, geom_point, ggplot, ggtitle, labs
from patchwork._datasets import mtcars


def main() -> None:
    df = mtcars().reset_index()

    p1 = ggplot(df) + geom_point(aes(x="mpg", y="disp")) + ggtitle("Plot 1")
    p2 = ggplot(df) + geom_point(aes(x="mpg", y="hp")) + ggtitle("Plot 2")
    # p3 has an extra colour-mapped legend that p1/p2 lack, so its panel
    # would otherwise render narrower than p1/p2's.
    p3 = (
        ggplot(df)
        + geom_point(aes(x="mpg", y="wt", color="cyl"))
        + ggtitle("Plot 3")
        + labs(color="Cylinders")
    )

    max_dims = pw.get_max_dim(p1, p2, p3)
    p1_aligned = pw.set_dim(p1, max_dims)
    p2_aligned = pw.set_dim(p2, max_dims)
    p3_aligned = pw.set_dim(p3, max_dims)
    print("pairwise alignment: tagged", sum(
        getattr(p, "_ptw_fixed_dim", False) for p in (p1_aligned, p2_aligned, p3_aligned)
    ), "of 3 plots")

    plots_aligned = pw.align_patches(p1, p2, p3)
    print("one-shot alignment: tagged", sum(
        getattr(p, "_ptw_fixed_dim", False) for p in plots_aligned
    ), "of 3 plots")


if __name__ == "__main__":
    main()
