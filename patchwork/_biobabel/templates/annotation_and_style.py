"""Titles, tags, and styling, from tutorials/annotation.ipynb
("Adding Annotation and Style").

Builds a publication-style figure: title/subtitle/caption on the whole
composition via plot_annotation(), auto-generated panel tags, and tag
styling applied recursively with `&`. Uses only the tiny bundled mtcars
dataset — no network, no GUI, no files written.
"""

from __future__ import annotations

import patchwork as pw
from ggplot2_py import aes, element_text, geom_point, ggplot, ggtitle, theme
from patchwork._datasets import mtcars


def main() -> None:
    df = mtcars().reset_index()

    p1 = ggplot(df) + geom_point(aes(x="mpg", y="disp")) + ggtitle("Plot 1")
    p2 = ggplot(df) + geom_point(aes(x="mpg", y="hp")) + ggtitle("Plot 2")
    p3 = ggplot(df) + geom_point(aes(x="mpg", y="wt")) + ggtitle("Plot 3")

    patchwork_obj = (p1 + p2) / p3
    annotated = patchwork_obj + pw.plot_annotation(
        title="The surprising truth about mtcars",
        subtitle="These 3 plots reveal yet-untold secrets about our beloved dataset",
        caption="Disclaimer: None of these plots are insightful",
        tag_levels="A",
    )
    styled = annotated & theme(plot_tag=element_text(size=8))

    gt = pw.patchworkGrob(styled)
    print(f"rendered annotated+tagged gtable with {len(gt.grobs)} grobs")


if __name__ == "__main__":
    main()
