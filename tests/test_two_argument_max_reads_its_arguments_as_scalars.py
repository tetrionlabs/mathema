# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`max(a, b)` and `min(a, b)` compare their arguments as values, so an
unannotated parameter passed to them is a scalar; only the one-argument
form `max(xs)` reads its argument as a sequence. A true claim over a
real interval on such a function gets the same verdict as the same
function with the parameter annotated `float`."""
import importlib.util
import sys
import textwrap

import pytest

import mathema
from mathema import analyze, claim
from mathema.runtime_types import SEQUENCE_KINDS

_SOURCE = textwrap.dedent("""\
    def capped_loss(change):
        return max(change, -1.0)

    def capped_loss_annotated(change: float) -> float:
        return max(change, -1.0)

    def capped_gain(change):
        return min(change, 1.0)

    def capped_gain_annotated(change: float) -> float:
        return min(change, 1.0)

    def clamp(x, lo, hi):
        return min(max(x, lo), hi)

    def largest(xs):
        return max(xs)

    def smallest_or(xs, fallback):
        return min(xs, default=fallback)

    def capped_total(xs, c):
        return max(sum(xs), c)

    def total_from(xs, start):
        return sum(xs, start)
    """)


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("max_scalars") / "max_scalars_mod.py"
    path.write_text(_SOURCE)
    spec = importlib.util.spec_from_file_location("max_scalars_mod", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name, scalars, sequences", [
    ("capped_loss", ["change"], []),
    ("capped_gain", ["change"], []),
    ("clamp", ["x", "lo", "hi"], []),
    ("largest", [], ["xs"]),
    ("smallest_or", [], ["xs"]),
    ("capped_total", ["c"], ["xs"]),
    ("total_from", [], ["xs"]),
])
def test_only_a_single_argument_reads_as_a_sequence(mod, name, scalars,
                                                    sequences):
    kinds = analyze(getattr(mod, name)).param_kinds
    for p in scalars:
        assert kinds[p] not in SEQUENCE_KINDS, (name, kinds)
    for p in sequences:
        assert kinds[p] in SEQUENCE_KINDS, (name, kinds)


@pytest.mark.parametrize("name, law", [
    ("capped_loss", "for change in [-5, 5], f(change) >= -1"),
    ("capped_gain", "for change in [-5, 5], f(change) <= 1"),
])
def test_a_true_claim_gets_the_annotated_verdict(mod, name, law):
    def claim_row(fn):
        (row,) = [p for p in mathema.check(fn, claims=[claim(law)]).probes
                  if p.name.startswith("f_change") and "[" not in p.name]
        return row
    bare = claim_row(getattr(mod, name))
    annotated = claim_row(getattr(mod, f"{name}_annotated"))
    assert bare.verdict == annotated.verdict, (
        bare.verdict, bare.counterexample, annotated.verdict)
    assert bare.verdict in ("proven", "holds")


@pytest.mark.parametrize("name, law", [
    ("capped_loss", "for change in [-5, 5], f(change) >= -1"),
    ("capped_gain", "for change in [-5, 5], f(change) <= 1"),
])
def test_no_row_is_a_sequence_row_or_draws_a_container(mod, name, law):
    rec = mathema.check(getattr(mod, name), claims=[claim(law)])
    for p in rec.probes:
        assert not p.name.startswith("is_empty_safe"), p.name
        for arg in p.meta.get("mathema.counterexample_args") or []:
            assert not isinstance(arg, (list, tuple)), (p.name, arg)
