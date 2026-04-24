"""Layout constants used throughout the composed gtable.

Mirrors ``R/aaa.R``. All indices are 1-based to match R and ``gtable_py``'s
1-based indexing convention.
"""

from __future__ import annotations

__all__ = [
    "TABLE_ROWS",
    "TABLE_COLS",
    "PANEL_ROW",
    "PANEL_COL",
    "PLOT_TOP",
    "PLOT_BOTTOM",
    "PLOT_LEFT",
    "PLOT_RIGHT",
    "TITLE_ROW",
    "SUBTITLE_ROW",
    "CAPTION_ROW",
    "GUIDE_RIGHT",
    "GUIDE_LEFT",
    "GUIDE_TOP",
    "GUIDE_BOTTOM",
]

TABLE_ROWS: int = 18
TABLE_COLS: int = 15
PANEL_ROW: int = 10
PANEL_COL: int = 8
PLOT_TOP: int = 7
PLOT_BOTTOM: int = 13
PLOT_LEFT: int = 5
PLOT_RIGHT: int = 11
TITLE_ROW: int = 3
SUBTITLE_ROW: int = 4
CAPTION_ROW: int = 16

GUIDE_RIGHT: int = 13
GUIDE_LEFT: int = 3
GUIDE_TOP: int = 5
GUIDE_BOTTOM: int = 15
