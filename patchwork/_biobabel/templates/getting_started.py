"""End-to-end composition, from tutorials/patchwork.ipynb ("Getting Started").

Builds four small ggplot2_py plots from the bundled mtcars dataset, composes
them with the |/ operators (parenthesized to avoid the Python-vs-R operator
precedence divergence), and annotates the result with a title and
auto-generated tags. Uses only the tiny bundled dataset — no network, no
GUI, no files written.
"""

from __future__ import annotations

import patchwork as pw
from ggplot2_py import aes, geom_point, ggplot, ggtitle
from patchwork._datasets import mtcars


def main() -> None:
    df = mtcars().reset_index()

    p1 = ggplot(df) + geom_point(aes(x="mpg", y="disp")) + ggtitle("Plot 1")
    p2 = ggplot(df) + geom_point(aes(x="mpg", y="hp")) + ggtitle("Plot 2")
    p3 = ggplot(df) + geom_point(aes(x="mpg", y="wt")) + ggtitle("Plot 3")

    # Python's `/` binds tighter than `|` (opposite of R) — parenthesize.
    composed = (p1 | (p2 / p3)) + pw.plot_annotation(
        title="The surprising story about mtcars",
        tag_levels="I",
    )

    # Exercise one real render path without producing pixel output.
    gt = pw.patchworkGrob(composed)
    print(f"composed {len(composed)} plots into a gtable with {len(gt.grobs)} grobs")


if __name__ == "__main__":
    main()
