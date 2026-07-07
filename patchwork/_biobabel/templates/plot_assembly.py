"""Ways to assemble plots, from tutorials/assembly.ipynb ("Plot Assembly").

Demonstrates nesting a patchwork inside another composition, adding a raw
grid grob via wrap_elements(), building a composition dynamically with
wrap_plots(), and the difference between `&` (recursive) and `*` (current
level only) when restyling. Uses only the tiny bundled mtcars dataset — no
network, no GUI, no files written.
"""

from __future__ import annotations

import patchwork as pw
from ggplot2_py import aes, geom_point, ggplot, ggtitle, theme_minimal
from grid_py import text_grob
from patchwork._datasets import mtcars


def main() -> None:
    df = mtcars().reset_index()

    p1 = ggplot(df) + geom_point(aes(x="mpg", y="disp")) + ggtitle("Plot 1")
    p2 = ggplot(df) + geom_point(aes(x="mpg", y="hp")) + ggtitle("Plot 2")
    p3 = ggplot(df) + geom_point(aes(x="mpg", y="wt")) + ggtitle("Plot 3")
    p4 = ggplot(df) + geom_point(aes(x="mpg", y="qsec")) + ggtitle("Plot 4")

    # Nest an existing patchwork inside a new composition.
    patch = p1 + p2
    nested = p3 + patch

    # A raw grid grob is auto-wrapped when added on the right-hand side.
    with_header = pw.wrap_elements(text_grob("Header")) + p1

    # Dynamic, list-based composition.
    from_list = pw.wrap_plots([p1, p2, p3, p4])

    # Recursive (&) vs shallow (*) restyling of a nested composition.
    grouped = p3 / (p1 | p2)
    everywhere = grouped & theme_minimal()
    top_level_only = grouped * theme_minimal()

    for name, composed in (
        ("nested", nested),
        ("with_header", with_header),
        ("from_list", from_list),
        ("everywhere", everywhere),
        ("top_level_only", top_level_only),
    ):
        gt = pw.patchworkGrob(composed)
        print(f"{name}: rendered gtable with {len(gt.grobs)} grobs")


if __name__ == "__main__":
    main()
