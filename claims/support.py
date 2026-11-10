# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Builders the claims in this directory bind with `let`: each turns a
value a claim can quantify over (a string, a number) into the object a
function under claim takes (a parsed function definition, a record
row, a claim)."""
from __future__ import annotations

import ast
import keyword


def _parsed(source: str) -> ast.FunctionDef:
    return ast.parse(source).body[0]


def _identifier(name: str) -> str:
    """`name`, or `name_` where `name` is a Python keyword."""
    return f"{name}_" if keyword.iskeyword(name) else name


def squaring_def(name: str) -> ast.FunctionDef:
    """`def g(<name>): <name>_sq = <name> * <name>; return <name>_sq + 1`,
    one function body whose parameter and local are spelled after
    `name`."""
    p = _identifier(name)
    return _parsed(f"def g({p}):\n    {p}_sq = {p} * {p}\n    return {p}_sq + 1\n")


def documented_def(doc: str) -> ast.FunctionDef:
    """`def g(x): return x + 1` with `doc` as its docstring."""
    return _parsed(f"def g(x):\n    {doc!r}\n    return x + 1\n")


def adding_def(k: int) -> ast.FunctionDef:
    """`def g(x): return x + <k>`."""
    return _parsed(f"def g(x):\n    return x + {int(k)}\n")


def named_def(name: str) -> ast.FunctionDef:
    """`def <name>(x): return x + 1`, one body under any function name."""
    return _parsed(f"def {_identifier(name)}(x):\n    return x + 1\n")


def returning_free_name(name: str) -> ast.FunctionDef:
    """`def g(x): return <name>`, a function returning a name it does not
    bind."""
    return _parsed(f"def g(x):\n    return {_identifier(name)}\n")


def returning_parameter(name: str) -> ast.FunctionDef:
    """`def g(x): return x`, whatever `name` is."""
    return _parsed("def g(x):\n    return x\n")


def calling_def(name: str) -> ast.FunctionDef:
    """`def <name>(x): return f(x)`, a function calling a function `f`."""
    return _parsed(f"def {_identifier(name)}(x):\n    return f(x)\n")


def recursive_def(name: str) -> ast.FunctionDef:
    """`def <name>(x): return <name>(x)`, a function calling itself."""
    n = _identifier(name)
    return _parsed(f"def {n}(x):\n    return {n}(x)\n")


def function_of_arity(n: int):
    """A function of `n` positional parameters `a0 ... a<n-1>`."""
    params = ", ".join(f"a{i}" for i in range(int(n)))
    space: dict = {}
    exec(f"def g({params}):\n    return 0\n", space)
    return space["g"]


def function_with_constant(k: int):
    """`def g(x, y=0): return x + <k>`: one signature, a body that
    varies with `k`."""
    space: dict = {}
    exec(f"def g(x, y=0):\n    return x + {int(k)}\n", space)
    return space["g"]


def surface_meta(source: str) -> dict:
    """A record's `meta` naming `source` as its authoring surface."""
    return {"mathema.surface": source}


def sweep_meta(text: str) -> dict:
    """A record's `meta` holding a float64 sweep of `len(text) + 2`
    points whose largest delta was 2.2e-16."""
    return {"mathema.sweep_precision": {"points": len(text) + 2,
                                        "largest_delta": 2.220446049250313e-16}}


def live_row(verdict: str):
    """A live `Probe` with `verdict`, declared in a claims file, carrying
    a counterexample and a note."""
    from mathema.records import Probe
    return Probe(name="c", statement="f(x) >= 0", verdict=verdict, n=10,
                 counterexample="x = 1", note="a note", route="probe",
                 meta={"mathema.surface": "declared"})


def stored_row(verdict: str) -> dict:
    """The same row as `live_row(verdict)`, in the shape a store holds."""
    return {"name": "c", "statement": "f(x) >= 0", "verdict": verdict,
            "n": 10, "counterexample": "x = 1", "note": "a note",
            "route": "probe", "meta": {"mathema.surface": "declared"}}


def claim_text(text: str):
    """The claim `text` reads as."""
    from mathema.claims import claim
    return claim(text)


def bounded_claim(bound: float):
    """`let |inf| be <bound>, for x in R, f(x) >= 0`."""
    from mathema.claims import claim
    return claim(f"let |inf| be {float(bound)!r}, for x in R, f(x) >= 0")


def pseudo_infinity_of(value: float):
    """A claim-level `PseudoInfinity` of magnitude `value`."""
    from mathema.records import PseudoInfinity
    return PseudoInfinity(float(value), "claim")


def number(text: str) -> float:
    """The number `text` spells."""
    return float(text)


def _row_of(families: tuple, sub: str) -> dict:
    """A stored row whose verdict is one of `families`, picked by the
    length of `sub`, refined with the subroute `sub` when it is not
    empty."""
    family = families[len(sub) % len(families)]
    return stored_row(f"{family}:{sub}" if sub else family)


def refuted_row(sub: str) -> dict:
    """A stored row with a refuting verdict and subroute `sub`."""
    return _row_of(("falsified", "invalidated", "disproven"), sub)


def blocked_row(sub: str) -> dict:
    """A stored row with a blocking verdict and subroute `sub`."""
    return _row_of(("skipped", "unliftable", "blocked"), sub)


def open_row(sub: str) -> dict:
    """A stored row whose verdict neither refutes nor blocks, with
    subroute `sub`."""
    return _row_of(("proven", "holds", "unknown", "declared", "documented"), sub)


def bound_read_back(binding: str):
    """The magnitude the claim grammar reads from `binding`, a
    `let |inf| be <value>` prefix."""
    from mathema.claims import claim
    return claim(f"{binding}, for x in R, f(x) >= 0").pseudo_infinity


def ascii_name(text: str) -> str:
    """An ASCII identifier spelled from `text`: `x` and its UTF-8 bytes
    in hex."""
    return "x" + text.encode("utf-8", "surrogatepass").hex()


def chain_claim(text: str):
    """`for <name> in [0, 1], 0 <= f(<name>) <= 1`, its variable named
    `ascii_name(text)`."""
    from mathema.claims import claim
    n = ascii_name(text)
    return claim(f"for {n} in [0, 1], 0 <= f({n}) <= 1")


def value_of(found):
    """The `value` of a `PseudoInfinity`."""
    return found.value


def source_of(found):
    """The `source` of a `PseudoInfinity`."""
    return found.source
