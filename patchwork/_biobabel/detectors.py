"""AST detectors for patchwork anti_patterns.

Wired into pyproject.toml as `biobabel.detectors` entry points. Each
callable is a pure function of (tree, args) -> list[DetectorMatch]: no tree
mutation, no I/O, no raising on well-formed input.
"""

from __future__ import annotations

import ast

from biobabel.detector_api import DetectorMatch

#: Functions whose R-parity docs explicitly call out that Python must copy
#: the argument (no copy-on-modify) because they never mutate it in place.
_COPY_ON_MODIFY_FUNCS = frozenset({"free", "inset_element", "merge"})


def _called_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def discard_copy_on_modify_result(tree: ast.AST, args: dict) -> list[DetectorMatch]:
    """Flag `free(...)`/`inset_element(...)`/`merge(...)` used as a bare, discarded statement."""
    matches: list[DetectorMatch] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        name = _called_name(call)
        if name in _COPY_ON_MODIFY_FUNCS:
            matches.append(DetectorMatch(line=node.lineno, detail={"call": name}))
    return matches
