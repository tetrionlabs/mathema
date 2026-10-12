# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function with no retrievable source (defined through `exec` or
`python -c`) is drawn from its parameters' types as a sourced one is:
a `list[float]` parameter is a sequence and meets the sequence corners,
the same-sign pair at the largest double among them, so a claim
falsified on the sourced function is falsified on the sourceless one
with the same kind of witness."""
import mathema

# the claim binds no domain: the parameter's type says what xs is
CLAIM = "assuming len(xs) >= 1, min(xs) <= f(xs) <= max(xs)"

SOURCE = '''
def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


class Box:
    def __init__(self, shape):
        self.shape = shape


def area(b: Box) -> float:
    return b.shape[0] * b.shape[1]
'''


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _sourceless(name):
    ns: dict = {"__name__": "sourceless_module"}
    exec(compile(SOURCE, "<sourceless>", "exec"), ns)
    return ns[name]


def _falsified_at_the_limit(fn):
    rows = mathema.check(fn, claims=[CLAIM]).probes
    hit = [p for p in rows if p.verdict == "falsified"
           and "e+308" in (p.counterexample or "")]
    assert hit, [(p.name, p.verdict, p.counterexample) for p in rows]
    return hit


def test_a_sourceless_function_reads_its_parameter_kinds_from_the_signature():
    facts = mathema.analyze(_sourceless("mean"))
    assert facts.tier == 0
    assert facts.param_kinds == {"xs": "sequence"}, facts.param_kinds


def test_the_sourced_function_meets_the_float_limit():
    _falsified_at_the_limit(mean)


def test_the_sourceless_function_meets_the_float_limit_alike():
    _falsified_at_the_limit(_sourceless("mean"))


def test_a_sourceless_class_parameter_is_not_drawn():
    facts = mathema.analyze(_sourceless("area"))
    assert facts.undrawable == {"b": "Box"}, facts.undrawable
    (row,) = [p for p in mathema.check(_sourceless("area"),
                                       claims=["f(b) >= 0"]).probes
              if p.name == "f_b_ge_0"]
    assert row.verdict == "skipped", (row.verdict, row.counterexample, row.note)
    assert "no evaluable inputs" in row.note, row.note
