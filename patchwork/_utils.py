"""Small helpers that R-side rlang/cli/utils provided.

No rlang re-implementation — every piece is a focused Python-native shim
that preserves the call site semantics the patchwork R source depends on.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Sequence

from ggplot2_py import is_waiver as _gg_is_waiver
from ggplot2_py import waiver as _gg_waiver
from grid_py import Unit, is_unit, null_grob, unit_type
from scales import col2hcl

__all__ = [
    "WAIVER",
    "is_waiver",
    "arg_match",
    "modify_list",
    "rep_len",
    "tail",
    "as_roman",
    "canonicalize_colour",
    "is_abs_unit",
    "unit_type_name",
    "zero_grob",
    "get_grob",
    "ave_min",
    "ave_max",
]

#: Sentinel (a ``ggplot2_py.waiver()`` instance) returned by functions that
#: want to distinguish "not set" from ``None``.
WAIVER = _gg_waiver()


def is_waiver(x: Any) -> bool:
    """Return ``True`` if *x* is a ggplot2 ``waiver()`` sentinel."""
    return _gg_is_waiver(x)


def arg_match(x: str, choices: Sequence[str], arg: str = "arg") -> str:
    """Match *x* against *choices*; raise ``ValueError`` on miss.

    Parameters
    ----------
    x : str
        Value to validate.
    choices : sequence of str
        Allowed values.
    arg : str, default ``"arg"``
        Argument name to reference in the error message.
    """
    if x in choices:
        return x
    raise ValueError(
        f"`{arg}` must be one of {choices!r}; got {x!r}"
    )


def modify_list(default: dict, user: dict) -> dict:
    """Replacement for ``utils::modifyList`` preserving R semantics.

    Keys whose value is ``None`` or ``waiver()`` are dropped before merge
    (matching patchwork's call sites where callers filter these out first).
    """
    filtered = {k: v for k, v in user.items() if v is not None and not is_waiver(v)}
    out = dict(default)
    out.update(filtered)
    return out


def rep_len(x: Any, length: int) -> list:
    """R ``rep_len(x, length)``: recycle or truncate *x* to exactly *length*."""
    if not isinstance(x, (list, tuple)):
        x = [x]
    if len(x) == 0:
        raise ValueError("cannot `rep_len` an empty sequence")
    if length <= 0:
        return []
    out = list(x)
    while len(out) < length:
        out.extend(x)
    return out[:length]


def tail(x: Sequence, n: int = 1) -> list:
    """R ``tail(x, n)``: last *n* elements; if ``n < 0``, drop first ``|n|``."""
    if n < 0:
        return list(x)[-n:]
    if n == 0:
        return []
    return list(x)[-n:]


_ROMAN_PAIRS = [
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
]


def as_roman(i: int) -> str:
    """Integer → uppercase Roman numeral (1 ≤ i ≤ 3999)."""
    if not isinstance(i, int) or i < 1 or i >= 4000:
        raise ValueError(f"`as_roman` only supports integers in [1, 3999]; got {i!r}")
    out: list[str] = []
    remaining = i
    for value, symbol in _ROMAN_PAIRS:
        while remaining >= value:
            out.append(symbol)
            remaining -= value
    return "".join(out)


def canonicalize_colour(col: str | None) -> str | None:
    """Canonicalize a colour string so two visually identical colours compare equal.

    Replaces the farver ``set_channel(x, "r", get_channel(x, "r"))`` trick in
    R's ``guides.R::unname_grob``. We route the colour through
    ``scales.col2hcl`` and back, which normalises named colours (``"red"``),
    short hex (``"#f00"``), and alpha hex (``"#FF0000FF"``) to a single form.
    """
    if col is None:
        return None
    return col2hcl(col)


_ABS_UNITS = {
    "cm",
    "inches",
    "mm",
    "points",
    "picas",
    "bigpts",
    "dida",
    "cicero",
    "scaledpts",
}


def unit_type_name(u: Any) -> list[str]:
    """Return the unit type(s) of a ``grid_py.Unit`` as a list of strings."""
    if not is_unit(u):
        return []
    t = unit_type(u)
    if isinstance(t, list):
        return t
    return [t]


def is_abs_unit(u: Any) -> bool:
    """Return ``True`` iff every component of *u* is an absolute unit."""
    names = unit_type_name(u)
    if not names:
        return False
    return all(n in _ABS_UNITS for n in names)


def zero_grob():
    """R ``zeroGrob()`` equivalent — uses ``grid_py.null_grob()``."""
    return null_grob()


def get_grob(gt, name: str):
    """Find a grob in a gtable by exact-match name; fallback to ``zero_grob()``."""
    names = gt.layout.get("name", [])
    for idx, n in enumerate(names):
        if n == name:
            return gt.grobs[idx]
    return zero_grob()


def _groupby_reduce(values: Sequence[int], keys: Sequence[int], reducer: Callable) -> list[int]:
    """Group *values* by *keys* and reduce within group, returning per-element reduced."""
    group_result: dict[Any, Any] = {}
    for v, k in zip(values, keys):
        if k not in group_result:
            group_result[k] = v
        else:
            group_result[k] = reducer(group_result[k], v)
    return [group_result[k] for k in keys]


def ave_min(values: Sequence[int], keys: Sequence[int]) -> list[int]:
    """R ``ave(values, keys, FUN = min)`` — per-group min broadcast back."""
    return _groupby_reduce(values, keys, min)


def ave_max(values: Sequence[int], keys: Sequence[int]) -> list[int]:
    """R ``ave(values, keys, FUN = max)`` — per-group max broadcast back."""
    return _groupby_reduce(values, keys, max)
