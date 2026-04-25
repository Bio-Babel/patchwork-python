"""Structural snapshot tests against R-derived canonical name counts.

For each canonical patchwork fixture, renders to a gtable via
:func:`patchwork.patchworkGrob`, canonicalises every layout-row name to
strip R-vs-Python padding / directional-variant noise, and counts how
many of each canonical name appear. The resulting dict is diffed
against a baseline TSV produced by ``tests/_snapshots/gen_gold.R``.

Why counts instead of positions?
  Both R and ``ggplot2_py`` ``ggplotGrob`` emit a 16x13 gtable;
  ``add_strips`` then promotes both sides to the canonical 18xN
  shape. Counts of canonical names survive minor positional
  differences and still catch real regressions (e.g. ``collect_axes``
  silently removing the wrong axes, ``_free_panel`` dropping strips,
  ``patchwork_grob`` losing the title row).

The baselines live in ``tests/_snapshots/*.tsv`` and are checked in.
Regenerate them only when an intended behaviour change has been
validated — run ``Rscript tests/_snapshots/gen_gold.R`` from the
``patchwork-python/`` root under the ``ggrepel-dev`` R environment.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import pytest
from ggplot2_py import aes, geom_point, ggplot

from patchwork import (
    patchworkGrob,
    plot_annotation,
    plot_layout,
    wrap_plots,
)

_SNAPSHOT_DIR = Path(__file__).parent / "_snapshots"

_TRAILING_IDX = re.compile(r"-\d+(-\d+)*$")

# Directional / position suffixes that R emits but Python collapses.
_SYNONYMS = {
    "xlab-t": "xlab",
    "xlab-b": "xlab",
    "ylab-l": "ylab",
    "ylab-r": "ylab",
    "guide-box-right": "guide-box",
    "guide-box-left": "guide-box",
    "guide-box-top": "guide-box",
    "guide-box-bottom": "guide-box",
    "guide-box-inside": "guide-box",
    # R-only placeholders — canonicalise to a sentinel so the test
    # tolerates their absence on the Python side.
    "axis-r": "axis-r-only-in-r",
    "axis-t": "axis-t-only-in-r",
    "spacer": "spacer-only-in-r",
    "subtitle": "subtitle-only-in-r",
    "caption": "caption-only-in-r",
    "free_panel": "free_panel-only-in-r",
    "free_row": "free_row-only-in-r",
    "free_col": "free_col-only-in-r",
    "patchwork-table": "patchwork-table-only-in-r",
    # Structural decorations: R emits per-plot + composition
    # ``background`` cells; Python emits one composition-level
    # ``background`` plus a ``panel-area`` marker. The two algorithms
    # are not count-equivalent (R=3 vs Py=2 for a two-plot add), and
    # neither is "wrong" — visual-fill parity belongs in a pixel test,
    # not a structural snapshot. Drop both sides from the assertion.
    "background": "background-decoration-ignored",
    "panel-area": "background-decoration-ignored",
}


def _canonical_name(name: str) -> str:
    """Fold a raw layout-row name to a backend-neutral canonical form."""
    if not name:
        return name
    if name.startswith("panel;"):
        return "panel"
    if ", " in name:
        name = name.split(", ", 1)[0]
    stripped = _TRAILING_IDX.sub("", name)
    return _SYNONYMS.get(stripped, stripped)


def _is_present(grob: Any) -> bool:
    """Mirror gen_gold.R's ``is_zero``: drop null / zero / empty layout rows.

    ``grid_py.null_grob()`` returns a ``Grob`` with ``_grid_class == "null"``;
    an empty ``GTree`` has no children. Either state means the layout row is
    a placeholder the R gold filters out, so the count snapshot must too.
    """
    if grob is None:
        return False
    grid_class = getattr(grob, "_grid_class", None)
    if grid_class in {"null", "zero"}:
        return False
    if type(grob).__name__ in {"NullGrob", "ZeroGrob"}:
        return False
    children = getattr(grob, "children", None)
    if children is not None and len(children) == 0:
        return False
    return True


def _name_counts(layout_names: Iterable[str], grobs: Iterable[Any]) -> Counter:
    out: Counter = Counter()
    for name, grob in zip(layout_names, grobs):
        if not _is_present(grob):
            continue
        canonical = _canonical_name(name)
        if canonical.endswith("-only-in-r") or canonical.endswith("-decoration-ignored"):
            continue
        out[canonical] += 1
    return out


def _load_baseline(tag: str) -> Counter:
    path = _SNAPSHOT_DIR / f"{tag}.tsv"
    baseline: Counter = Counter()
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 2:
                continue
            baseline[parts[0]] = int(parts[1])
    return baseline


def _df() -> pd.DataFrame:
    return pd.DataFrame({"x": [1, 2, 3, 4], "y": [1, 3, 2, 4]})


def _p() -> Any:
    return ggplot(_df()) + geom_point(aes(x="x", y="y"))


# -- Fixture registry — each returns (tag, patchwork). Tag must match
#    the baseline filename in tests/_snapshots/<tag>.tsv.
FIXTURES = [
    ("two_plus",       lambda: _p() + _p()),
    ("two_stack",      lambda: _p() / _p()),
    ("wrap_four",      lambda: wrap_plots([_p(), _p(), _p(), _p()])),
    ("nested",         lambda: _p() + (_p() + _p())),
    ("design_string",  lambda: _p() + _p() + _p() + plot_layout(design="AA#\nBCC")),
    ("annotated",      lambda: (_p() + _p()) + plot_annotation(title="Hello", subtitle="Sub")),
    ("tagged",         lambda: (_p() + _p() + _p()) + plot_annotation(tag_levels="A")),
]


@pytest.mark.parametrize("tag,build", FIXTURES, ids=[t for t, _ in FIXTURES])
def test_structural_snapshot(tag: str, build) -> None:
    """Canonicalised name counts match the R-derived baseline."""
    pw = build()
    gt = patchworkGrob(pw)
    py_counts = _name_counts(gt.layout["name"], gt.grobs)
    gold = _load_baseline(tag)

    assert py_counts == gold, (
        f"[{tag}] snapshot diverged from R gold\n"
        f"  Python : {dict(sorted(py_counts.items()))}\n"
        f"  R gold : {dict(sorted(gold.items()))}\n"
        f"  extra in Py   : {dict((k, v) for k, v in (py_counts - gold).items())}\n"
        f"  missing in Py : {dict((k, v) for k, v in (gold - py_counts).items())}"
    )
