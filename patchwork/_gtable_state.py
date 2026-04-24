"""Preserve patchwork-specific state across ``gtable_py`` operations.

``gtable_py`` copies the ``Gtable`` on every ``gtable_add_grob`` /
``gtable_add_rows`` / ``gtable_add_cols`` call, but does not carry over
attributes we set from patchwork (``collected_guides``, ``_ptw_class``,
``inset_settings``, ``free_settings``, ``patch_settings``). The helpers
below copy patchwork-private state from a source gtable to a destination
gtable after such operations.
"""

from __future__ import annotations

from typing import Any

from gtable_py import Gtable

__all__ = [
    "STATE_ATTRS",
    "PTW_CLASS",
    "copy_state",
    "get_class",
    "add_class",
    "remove_class",
    "has_class",
    "set_attr",
    "get_attr",
]

#: Patchwork-private attributes we want to carry across gtable operations.
STATE_ATTRS: tuple[str, ...] = (
    "_ptw_class",
    "collected_guides",
    "inset_settings",
    "free_settings",
    "patch_settings",
    "patchwork_free_settings",
    "patchwork_link",
)

PTW_CLASS = "_ptw_class"


def copy_state(src: Any, dst: Any) -> Any:
    """Copy every ``STATE_ATTRS`` value present on *src* onto *dst*."""
    for attr in STATE_ATTRS:
        if hasattr(src, attr):
            try:
                setattr(dst, attr, getattr(src, attr))
            except AttributeError:
                pass
    return dst


def get_class(x: Any) -> set[str]:
    """Return the patchwork class-tag set attached to *x* (empty if none)."""
    return set(getattr(x, PTW_CLASS, set()))


def add_class(x: Any, tag: str | None = None, /, tags: set[str] | None = None) -> Any:
    """Add one or more patchwork class-tags to *x* (mutating, returns *x*)."""
    current = get_class(x)
    if tag is not None:
        current.add(tag)
    if tags is not None:
        current |= tags
    try:
        setattr(x, PTW_CLASS, current)
    except AttributeError:
        pass
    return x


def remove_class(x: Any, tag: str) -> Any:
    """Remove a patchwork class-tag from *x* (mutating, returns *x*)."""
    current = get_class(x)
    current.discard(tag)
    try:
        setattr(x, PTW_CLASS, current)
    except AttributeError:
        pass
    return x


def has_class(x: Any, tag: str) -> bool:
    """Return ``True`` if *x* carries the given patchwork class-tag."""
    return tag in get_class(x)


def set_attr(x: Any, attr: str, value: Any) -> Any:
    """Set a single patchwork-private attribute on *x* (mutating)."""
    try:
        setattr(x, attr, value)
    except AttributeError:
        pass
    return x


def get_attr(x: Any, attr: str, default: Any = None) -> Any:
    """Read a patchwork-private attribute from *x* with a default."""
    return getattr(x, attr, default)


def ensure_gtable(x: Any) -> Any:
    """Assert *x* is a ``Gtable`` and return it (pass-through guard)."""
    if not isinstance(x, Gtable):
        raise TypeError(f"expected a Gtable, got {type(x).__name__}")
    return x
