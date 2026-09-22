# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Simple OOP methods on the derive route: a read-only method's self
expands into composite field symbols (the dict-param precedent), field
reads and sibling-method calls derive, field domains quantify like any
scalar (`for self.rate in [0,1]`), and the probe route synthesizes
instances (dataclasses construct normally; a plain class builds
field-by-field, the declared field domains being the validity
contract). Stateful means a genuine WRITE to instance state, or self
escaping the field-read/sibling-call vocabulary, never mere use."""
import textwrap

from mathema.conjecture import check_conjectures, claim


def _mod(tmp_path, body, name):
    import importlib
    import sys
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body))
    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module(name)
        importlib.reload(mod)
    finally:
        sys.path.remove(str(tmp_path))
    return mod


_BODY = """
from dataclasses import dataclass


@dataclass
class Bond:
    face: float
    rate: float

    def simple_interest(self, n: int) -> float:
        return self.face * self.rate * n

    def discount(self, n: int) -> float:
        return 1.0 / (1.0 + self.rate) ** n

    def present_value(self, n: int) -> float:
        return self.face * self.discount(n)

    @staticmethod
    def par_ratio(x: float) -> float:
        return x / 100.0

    def scaled(self, x: float) -> float:
        return self.par_ratio(x) * self.face

    def bump(self, amount: float) -> None:
        self.rate = self.rate + amount

    def escaped(self, x: float) -> float:
        return helper(self) * x


def helper(bond) -> float:
    return bond.rate


class Plain:
    def __init__(self, factor: float, offset: float):
        self.factor = factor
        self.offset = offset

    def scaled(self, x: float) -> float:
        return self.factor * x + self.offset
"""


def _run(fn, law, **kw):
    (p,) = check_conjectures(fn, [claim(law, **kw)])
    return p


def test_read_only_dataclass_method_proves(tmp_path):
    mod = _mod(tmp_path, _BODY, "ml_a")
    p = _run(mod.Bond.simple_interest,
             "f(self, n) == self.face * self.rate * n", route="derive")
    assert p.verdict == "proven", (p.verdict, p.note)


def test_field_domains_quantify_like_scalars(tmp_path):
    mod = _mod(tmp_path, _BODY, "ml_b")
    p = _run(mod.Bond.simple_interest,
             "for self.rate in [0.01,0.2], self.face in [50,100], "
             "n in [1,10] subset Z, f(self, n) >= 0", route="derive")
    assert p.verdict == "proven", (p.verdict, p.note)


def test_sibling_method_calls_inline(tmp_path):
    mod = _mod(tmp_path, _BODY, "ml_c")
    # an instance sibling: the callee's fields join the symbol table
    # even though the caller never reads self.rate itself
    p = _run(mod.Bond.present_value,
             "for self.rate in [0.01,0.2], self.face in [50,100], "
             "n in [1,10] subset Z, "
             "f(self, n) == self.face / (1 + self.rate)**n", route="derive")
    assert p.verdict == "proven", (p.verdict, p.note)
    # a staticmethod sibling
    p = _run(mod.Bond.scaled,
             "for self.face in [50,100], x in [0,10], "
             "f(self, x) == x * self.face / 100", route="derive")
    assert p.verdict == "proven", (p.verdict, p.note)


def test_plain_class_method_proves(tmp_path):
    mod = _mod(tmp_path, _BODY, "ml_d")
    p = _run(mod.Plain.scaled,
             "f(self, x) == self.factor * x + self.offset", route="derive")
    assert p.verdict == "proven", (p.verdict, p.note)


def test_probe_synthesizes_instances(tmp_path):
    mod = _mod(tmp_path, _BODY, "ml_e")
    p = _run(mod.Bond.simple_interest,
             "for self.rate in [0.01,0.2], self.face in [50,100], "
             "n in [1,10] subset Z, "
             "f(self, n) == self.face * self.rate * n", route="probe")
    assert p.verdict == "holds", (p.verdict, p.note)
    assert p.n and p.n > 20
    p = _run(mod.Plain.scaled,
             "for self.factor in [1,5], self.offset in [0,2], x in [1,10], "
             "f(self, x) < 0", route="probe")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_mutating_method_stays_stateful(tmp_path):
    from mathema.inventory import is_pure_enough, purity_reason
    mod = _mod(tmp_path, _BODY, "ml_f")
    assert is_pure_enough(mod.Bond.bump) is False
    assert "stateful" in (purity_reason(mod.Bond.bump) or "")
    p = _run(mod.Bond.bump, "f(self, amount) >= 0", route="derive")
    assert p.verdict != "proven"


def test_self_escaping_stays_stateful(tmp_path):
    from mathema.inventory import is_pure_enough
    mod = _mod(tmp_path, _BODY, "ml_g")
    assert is_pure_enough(mod.Bond.escaped) is False
