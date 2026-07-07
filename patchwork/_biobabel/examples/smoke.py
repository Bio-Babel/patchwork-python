"""Smoke test for patchwork._biobabel.

Imports patchwork and exercises one real path: composing two tiny plots
from the bundled mtcars dataset and rendering the composition to a gtable
(no pixel output, no GUI, no network, no files written).
"""

from __future__ import annotations


def main() -> None:
    import patchwork as pw
    from ggplot2_py import aes, geom_point, ggplot
    from patchwork._datasets import mtcars

    df = mtcars().reset_index()
    p1 = ggplot(df) + geom_point(aes(x="mpg", y="disp"))
    p2 = ggplot(df) + geom_point(aes(x="mpg", y="hp"))

    composed = p1 | p2
    gt = pw.patchworkGrob(composed)
    print(f"imported patchwork successfully; rendered gtable with {len(gt.grobs)} grobs")


if __name__ == "__main__":
    main()
