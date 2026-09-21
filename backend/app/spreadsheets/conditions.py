"""
The register's condition language, evaluated on the server for imports.

The form engine (src/lib/spec/conditions.ts) decides on screen whether a field
is visible and whether a Conditional field is required. An import has no
screen, so the same rules are applied here — otherwise a spreadsheet could
store what the form would have refused.

Only what the importable fields actually use is supported, and anything else
is REPORTED as not understood rather than guessed:

    field == 'Label'      field != 'Label'      field includes 'KEY'
    a && b                a || b                ( ... )

Literals compare slug-normalised against the stored key AND its picklist label,
exactly as the frontend's picklist_comparison convention says, so
`deal_source == 'Partner-sourced'` holds for the key PARTNER_SOURCED.
"""

from __future__ import annotations

import re
from typing import Any, Callable

_TOKEN = re.compile(r"\s*(?:(\(|\)|&&|\|\||==|!=)|('(?:[^']*)'|\"(?:[^\"]*)\")|(includes\b)|([A-Za-z_][\w—]*))")


class ConditionError(ValueError):
    """An expression this evaluator does not understand."""


def slug(value: Any) -> str:
    return re.sub(r"[\s_\-/]+", "", str(value if value is not None else "")).lower()


def _tokens(expr: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    expr = expr.strip()
    while pos < len(expr):
        match = _TOKEN.match(expr, pos)
        if not match or match.end() == pos:
            raise ConditionError(f"cannot read {expr[pos:]!r}")
        op, literal, includes, ident = match.groups()
        if op:
            out.append(("op", op))
        elif literal is not None:
            out.append(("str", literal[1:-1]))
        elif includes:
            out.append(("op", "includes"))
        else:
            out.append(("id", ident))
        pos = match.end()
    return out


def evaluate(expr: str, value_of: Callable[[str], Any], label_of: Callable[[str, Any], str | None]) -> bool:
    """
    `value_of(api_name)` returns the stored value (a key, or a list of keys).
    `label_of(api_name, key)` returns that key's picklist label, or None.
    """
    tokens = _tokens(expr)
    pos = 0

    def peek() -> tuple[str, str] | None:
        return tokens[pos] if pos < len(tokens) else None

    def take() -> tuple[str, str]:
        nonlocal pos
        if pos >= len(tokens):
            raise ConditionError(f"unexpected end of {expr!r}")
        pos += 1
        return tokens[pos - 1]

    def same(name: str, stored: Any, literal: str) -> bool:
        want = slug(literal)
        if stored is None or stored == "":
            return want == ""
        return slug(stored) == want or slug(label_of(name, stored) or "") == want

    def comparison() -> bool:
        token = take()
        if token == ("op", "("):
            result = disjunction()
            if take() != ("op", ")"):
                raise ConditionError(f"unbalanced brackets in {expr!r}")
            return result
        if token[0] != "id":
            raise ConditionError(f"expected a field name in {expr!r}")
        name = token[1]
        op = take()
        literal = take()
        if op[0] != "op" or literal[0] != "str":
            raise ConditionError(f"expected field OP 'value' in {expr!r}")
        stored = value_of(name)
        if op[1] == "includes":
            items = stored if isinstance(stored, list) else ([] if stored in (None, "") else [stored])
            return any(same(name, item, literal[1]) for item in items)
        if op[1] == "==":
            return same(name, stored, literal[1])
        if op[1] == "!=":
            return not same(name, stored, literal[1])
        raise ConditionError(f"unsupported operator {op[1]!r} in {expr!r}")

    def conjunction() -> bool:
        result = comparison()
        while peek() == ("op", "&&"):
            take()
            right = comparison()
            result = result and right
        return result

    def disjunction() -> bool:
        result = conjunction()
        while peek() == ("op", "||"):
            take()
            right = conjunction()
            result = result or right
        return result

    result = disjunction()
    if pos != len(tokens):
        raise ConditionError(f"unexpected {tokens[pos][1]!r} in {expr!r}")
    return result
