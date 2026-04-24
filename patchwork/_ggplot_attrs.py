"""Helpers to attach patchwork-private attributes to ``ggplot2_py.GGPlot``.

``GGPlot`` overrides ``__setattr__`` to whitelist only its own fields, so
direct ``setattr`` silently fails for patchwork metadata. We bypass the
guard via ``__dict__`` assignment, which is the interpreter-level path.
"""

from __future__ import annotations

from typing import Any

__all__ = ["safe_set", "safe_get", "safe_delete"]


def safe_set(obj: Any, name: str, value: Any) -> Any:
    """Set ``obj.<name> = value`` bypassing any ``__setattr__`` guard."""
    try:
        obj.__dict__[name] = value
    except (AttributeError, TypeError):
        # Final fallback: raw ``object`` descriptor.
        object.__setattr__(obj, name, value)
    return obj


def safe_get(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``obj.<name>`` if present, else *default*."""
    if hasattr(obj, "__dict__"):
        return obj.__dict__.get(name, default)
    return getattr(obj, name, default)


def safe_delete(obj: Any, name: str) -> None:
    """Delete ``obj.<name>`` if present; silent no-op otherwise."""
    if hasattr(obj, "__dict__"):
        obj.__dict__.pop(name, None)
