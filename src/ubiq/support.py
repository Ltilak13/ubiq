"""Runtime requirements: what a feature needs from the interpreter and its extras.

Support records (`.ubiq/support/*.md`) say which Python versions Ubiq supports.
A feature may need more than the package floor: a newer interpreter, or the pip
extra that brings in its dependency. It declares that need once, as data
(`runtime: {python: ">=3.11"}`, `extra: jsonpath`), and these helpers turn the
declaration into an actionable message instead of an ImportError or SyntaxError.

    from ubiq.support import require
    require(python=">=3.11", extra="jsonpath", module="jsonpath_ng", feature="JSONPath selection")

The module uses only the standard library so it can run on every supported Python.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Mapping
from typing import Any

PACKAGE = "ubiq"

_CLAUSE = re.compile(r"^\s*(>=|<=|==|!=|>|<)\s*([0-9]+(?:\.[0-9]+){0,2})\s*$")


class RuntimeUnmet(ImportError):
    """A feature's declared runtime is not met. An ImportError, so fallbacks keep working."""


def parse_specifier(spec: str) -> list[tuple[str, tuple[int, ...]]]:
    """Comma-separated clauses such as `>=3.11,<3.14`, as (operator, version) pairs."""
    clauses = []
    for part in spec.split(","):
        match = _CLAUSE.match(part)
        if match is None:
            raise ValueError(f"unsupported Python requirement {spec!r}; "
                             "use clauses like '>=3.11' or '>=3.11,<3.14'")
        clauses.append((match.group(1), tuple(int(n) for n in match.group(2).split("."))))
    return clauses


def satisfies(version: tuple[int, ...], spec: str) -> bool:
    """Whether `version` meets every clause of `spec`. `==3.11` also matches 3.11.4."""
    for op, wanted in parse_specifier(spec):
        padded = tuple(version[:3]) + (0,) * (3 - len(version[:3]))
        bound = wanted + (0,) * (3 - len(wanted))
        if op == "==":
            ok = padded[:len(wanted)] == wanted
        elif op == "!=":
            ok = padded[:len(wanted)] != wanted
        else:
            ok = {">=": padded >= bound, "<=": padded <= bound,
                  ">": padded > bound, "<": padded < bound}[op]
        if not ok:
            return False
    return True


def _label(version: tuple[int, ...]) -> str:
    return ".".join(str(n) for n in version[:3])


def unmet(python: str | None = None, extra: str | None = None, module: str | None = None,
          feature: str | None = None, *, version: tuple[int, ...] | None = None) -> str | None:
    """The actionable message for an unmet requirement, or None when all are met.

    `python` is a version specifier. `extra` names the pip extra that brings in
    the feature's dependency, and `module` the import that proves it is installed
    (without `module`, `extra` only improves the message). `version` overrides
    the running interpreter, for tests.
    """
    current = tuple(version) if version is not None else tuple(sys.version_info[:3])
    subject = feature or "this feature"
    hint = f" (install {PACKAGE}[{extra}])" if extra else ""
    if python is not None and not satisfies(current, python):
        return (f"{subject} needs Python {python}{hint}; this is Python {_label(current)}. "
                f"Run it on a newer interpreter, or skip {subject}.")
    if module is not None and importlib.util.find_spec(module.split(".")[0]) is None:
        install = f"pip install '{PACKAGE}[{extra}]'" if extra else f"pip install {module}"
        return f"{subject} needs the {module!r} module; install it with {install}."
    return None


def require(python: str | None = None, extra: str | None = None, module: str | None = None,
            feature: str | None = None, *, version: tuple[int, ...] | None = None) -> None:
    """Raise RuntimeUnmet with an actionable message unless the requirements are met."""
    message = unmet(python, extra, module, feature, version=version)
    if message is not None:
        raise RuntimeUnmet(message)


def declared(runtime: Mapping[str, Any] | None, extra: str | None = None,
             feature: str | None = None, module: str | None = None) -> str | None:
    """`unmet` for a feature record's `runtime` mapping and `extra` fields."""
    return unmet((runtime or {}).get("python"), extra, module, feature)


def skip_reason(*args: Any, **kwargs: Any) -> str | None:
    """The pytest skip reason for a `runtime` marker, or None to run the test.

    `@pytest.mark.runtime(python=">=3.11", extra="jsonpath", module="jsonpath_ng")`
    accepts the same keywords as `unmet`.
    """
    if args:
        raise TypeError("the runtime marker takes keyword arguments only")
    return unmet(**kwargs)
