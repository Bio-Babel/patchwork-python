"""patchwork-python — Python port of the R patchwork package.

Top-level public API mirrors R's exports exactly: ``plot_layout``,
``plot_annotation``, ``plot_spacer``, ``guide_area``, ``area``, ``free``,
``inset_element``, ``wrap_elements``, ``wrap_ggplot_grob``, ``wrap_table``,
``wrap_plots``, ``patchGrob`` / ``patch_grob``, ``patchworkGrob`` /
``patchwork_grob``, ``get_dim``, ``set_dim``, ``get_max_dim``,
``align_patches``, ``align_plots``.

Importing this module also installs the operator dunders on
:class:`ggplot2_py.GGPlot` so ``p1 | p2``, ``p1 - p2``, ``p1 / p2`` etc.
work as in R.
"""

from __future__ import annotations

__version__ = "1.3.2.9000"
__r_commit__ = "6b1d88c"

# 1. Load all submodules so their ``@singledispatch.register`` decorators run.
from . import _constants  # noqa: F401
from . import _utils  # noqa: F401
from . import _datasets  # noqa: F401
from . import _patch  # noqa: F401
from . import spacer  # noqa: F401
from . import guide_area  # noqa: F401
from . import layout  # noqa: F401
from . import annotation  # noqa: F401
from . import wrap_elements  # noqa: F401
from . import wrap_ggplot_grob  # noqa: F401
from . import wrap_table  # noqa: F401
from . import add_plot  # noqa: F401
from . import arithmetic  # noqa: F401
from . import merge as _merge_module  # noqa: F401
from . import free as _free_module  # noqa: F401
from . import inset  # noqa: F401
from . import wrap_plots  # noqa: F401
from . import guides  # noqa: F401
from . import collect_axes  # noqa: F401
from . import core  # noqa: F401
from . import multipage  # noqa: F401

# 2. Install runtime plumbing.
arithmetic.install_ggplot_operators()
annotation._register_has_tag_defaults()
add_plot._register_update_ggplot()
core._register_plot_table_patchwork()


def _register_patchwork_cross_module_dispatch() -> None:
    """Register singledispatch handlers that span module boundaries.

    These can't live in their own modules without import cycles, so we
    install them here once all modules have been imported.
    """
    from .add_plot import Patchwork, PlotFiller, is_empty
    from .annotation import has_tag
    from .core import as_gtable, patchworkGrob
    from .wrap_elements import as_patch

    @as_patch.register(Patchwork)
    def _(x: Patchwork, **kwargs):
        """R ``as_patch.patchwork`` → ``patchworkGrob(x)``."""
        return patchworkGrob(x)

    @has_tag.register(PlotFiller)
    def _(x: PlotFiller) -> bool:  # noqa: F811
        """R ``has_tag.plot_filler`` → FALSE."""
        return False

    @has_tag.register(Patchwork)
    def _(x: Patchwork) -> bool:  # noqa: F811
        """R parity: ``has_tag`` on a patchwork falls through to
        ``has_tag.ggplot`` (since patchwork inherits 'ggplot' class),
        which returns ``!is_empty(x)`` (patch.R:80). In Python the
        dataclass doesn't carry ggplot inheritance, so register
        explicitly — the active plot (``x.plot``) is what
        ``recurse_tags`` will try to tag via ``x + labs(tag=...)``."""
        return not is_empty(x)

    @as_gtable.register(Patchwork)
    def _(x: Patchwork):  # noqa: F811
        """R ``as.gtable.patchwork`` → ``patchworkGrob(x)`` (one-line
        method in plot_patchwork.R)."""
        return patchworkGrob(x)


_register_patchwork_cross_module_dispatch()

# 3. Re-export public names.
from ._patch import patch_grob, patchGrob  # noqa: E402
from .add_plot import Patchwork  # noqa: E402
from .annotation import plot_annotation  # noqa: E402
from .core import (  # noqa: E402
    as_gtable,
    patchwork_grob,
    patchworkGrob,
    plot_table,
    simplify_gt,
    build_patchwork,
)
from .free import free  # noqa: E402
from .guide_area import guide_area  # noqa: E402
from .inset import inset_element  # noqa: E402
from .layout import area, plot_layout  # noqa: E402
from .merge import merge  # noqa: E402
from .multipage import (  # noqa: E402
    align_patches,
    align_plots,
    get_dim,
    get_max_dim,
    set_dim,
)
from .spacer import plot_spacer  # noqa: E402
from .wrap_elements import (  # noqa: E402
    as_patch,
    as_patch_formula,
    as_patch_gt_tbl,
    wrap_elements,
)
from .wrap_ggplot_grob import wrap_ggplot_grob  # noqa: E402
from .wrap_plots import wrap_plots  # noqa: E402
from .wrap_table import wrap_table  # noqa: E402

__all__ = [
    "__version__",
    "Patchwork",
    "align_patches",
    "align_plots",
    "area",
    "as_gtable",
    "as_patch",
    "as_patch_formula",
    "as_patch_gt_tbl",
    "build_patchwork",
    "free",
    "get_dim",
    "get_max_dim",
    "guide_area",
    "inset_element",
    "merge",
    "patchGrob",
    "patch_grob",
    "patchworkGrob",
    "patchwork_grob",
    "plot_annotation",
    "plot_layout",
    "plot_spacer",
    "plot_table",
    "set_dim",
    "simplify_gt",
    "wrap_elements",
    "wrap_ggplot_grob",
    "wrap_plots",
    "wrap_table",
]
