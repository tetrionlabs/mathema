# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A domain guard lets a parameter through, for a `raises` claim, when it
lets through every value the claim's own finite set gives that
parameter. A missing value the set lists stands for the values the
parameter's own resolution realises it as: Python's `None` for absence
on a parameter with no annotation. A spelling of absence some runtime
registered in the same process (`Option::None`) is not a value of that
set, so it changes nothing; and the reading needs no solver."""
import pytest

from mathema import authoring, check_conjectures, claim
from mathema import domain as mathema_domain
from mathema.symbolic import _smt

CLAIM = "for x in [-5, -1], y in {1, None}, raises(f(x, y), KeyError)"


class OptionNone:
    """A foreign runtime's absent value."""

    def __repr__(self) -> str:
        return "Option::None"


@authoring.enforce_domain({"y": "{1, None}"})
def guard_of_the_same_set(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@authoring.enforce_domain({"y": "{1}"})
def guard_that_refuses_none(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@pytest.fixture
def registries(monkeypatch):
    """The spelling registries as copies, so a spelling a test registers
    is gone after it."""
    for name in ("_ABSENCE_VALUES", "_ABSENCE_DETECTORS", "_SPELLING_VALUES"):
        monkeypatch.setattr(mathema_domain, name, dict(getattr(mathema_domain, name)))


def _solver(monkeypatch, hidden: bool) -> None:
    if hidden:
        monkeypatch.setattr(_smt, "available", lambda: False)


def _verdict(fn, text=CLAIM):
    row = check_conjectures(fn, [claim(text, route="derive")])[-1]
    return row.verdict, row.sketch, row.note


@pytest.mark.parametrize("hidden", [True, False], ids=["solver hidden", "solver as installed"])
def test_the_guard_of_the_same_set_is_proven(monkeypatch, registries, hidden):
    _solver(monkeypatch, hidden)
    for y in (1, None):
        with pytest.raises(KeyError):
            guard_of_the_same_set(-5, y)
    verdict = _verdict(guard_of_the_same_set)
    assert verdict[0] == "proven", verdict


@pytest.mark.parametrize("hidden", [True, False], ids=["solver hidden", "solver as installed"])
def test_a_foreign_absence_registered_earlier_changes_nothing(monkeypatch, registries,
                                                               hidden):
    _solver(monkeypatch, hidden)
    mathema_domain.register_absence_spelling(
        "Option::None", OptionNone, lambda v: isinstance(v, OptionNone))
    verdict = _verdict(guard_of_the_same_set)
    assert verdict[0] == "proven", verdict


@pytest.mark.parametrize("hidden", [True, False], ids=["solver hidden", "solver as installed"])
def test_a_guard_that_refuses_a_listed_value_is_never_proven(monkeypatch, registries,
                                                             hidden):
    _solver(monkeypatch, hidden)
    with pytest.raises(authoring.DomainError):
        guard_that_refuses_none(-5, None)
    verdict = _verdict(guard_that_refuses_none)
    assert verdict[0] != "proven", verdict


@pytest.fixture
def toy_runtime(monkeypatch, registries, tmp_path):
    """The toy foreign runtime of the definition tests installed, its
    parameter type `toy.f64` spelling absence `Option::None`."""
    from mathema import compendium
    from mathema import runtime_types as rt
    from test_definitions_are_axioms_not_claims import _EntryPoint
    monkeypatch.setattr(rt, "entry_points", lambda **_: [_EntryPoint()])
    rt._discovered.cache_clear()
    (tmp_path / "toy.claims.yaml").write_text(
        'toy.f64:\n  defines:\n    - "None := {Option::None}"\n')
    compendium.install(str(tmp_path))
    yield
    compendium.uninstall()
    compendium.ensure_bundled()
    rt._discovered.cache_clear()


def _of_the_toy_runtime(x, y):
    if x < 0:
        raise KeyError("n")
    return x


_of_the_toy_runtime.__annotations__["y"] = "toy.f64"
guard_of_a_foreign_parameter = authoring.enforce_domain({"y": "{1, None}"})(_of_the_toy_runtime)


@pytest.mark.parametrize("hidden", [True, False], ids=["solver hidden", "solver as installed"])
def test_a_foreign_parameter_is_judged_at_its_own_absence(monkeypatch, toy_runtime, hidden):
    from test_definitions_are_axioms_not_claims import OptionNone as ToyNone
    _solver(monkeypatch, hidden)
    with pytest.raises(authoring.DomainError):
        guard_of_a_foreign_parameter(-5, ToyNone())
    verdict = _verdict(guard_of_a_foreign_parameter)
    assert verdict[0] != "proven", verdict
