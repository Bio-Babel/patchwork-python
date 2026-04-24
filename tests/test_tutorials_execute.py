"""End-to-end execution tests for every tutorial notebook.

Each notebook in ``tutorials/`` must run to completion with the current
package. This guards against silent regressions where a public API
change breaks user-facing examples.
"""

from __future__ import annotations

from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient

TUTORIALS_DIR = Path(__file__).resolve().parent.parent / "tutorials"


def _notebook_paths() -> list[Path]:
    return sorted(TUTORIALS_DIR.glob("*.ipynb"))


@pytest.mark.parametrize("notebook", _notebook_paths(), ids=lambda p: p.name)
def test_notebook_executes(notebook: Path) -> None:
    nb = nbformat.read(str(notebook), as_version=4)
    client = NotebookClient(nb, timeout=120, kernel_name="python3")
    client.execute()  # Raises on any cell failure.
