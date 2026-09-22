# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""String-annotated parameters: no more floats thrown at a str param.
A bare `str` with no domain declines honestly (named parameter, the
spelling that fixes it, the no-evaluable-inputs reason code); a
`Literal[...]` annotation is a complete finite domain and samples/
adjudicates like a declared one; `set[str]` still reads as a
sequence."""
import math
from typing import Literal

from mathema import analyze, check, claim
from mathema.reason_codes import ClaimReasonCode, claim_reason_code


def _bare_str(r: float, scale: str) -> float:
    if scale == "sqrt":
        return math.sqrt(1.0 - r * r)
    return 1.0 - r * r


def _literal_scale(r: float, scale: Literal["sqrt", "square"]) -> float:
    if scale == "sqrt":
        return math.sqrt(abs(1.0 - r * r))
    return 1.0 - r * r


def test_param_kinds_classify_str_and_literal():
    kinds = analyze(_bare_str).param_kinds
    assert kinds["scale"] == "string"
    kinds = analyze(_literal_scale).param_kinds
    assert kinds["scale"] == "string"


def test_literal_annotation_is_a_finite_domain():
    facts = analyze(_literal_scale)
    assert facts.finite_domains == {"scale": ["sqrt", "square"]}


def test_set_str_annotation_stays_a_sequence():
    def takes_set(xs: "set[str]") -> int:
        return len(xs)
    assert analyze(takes_set).param_kinds["xs"] == "sequence"


def test_bare_str_declines_honestly_not_a_spurious_gap():
    rec = check(_bare_str)
    gap = [p for p in rec.probes
           if (p.meta or {}).get("mathema.probe_gap")]
    assert gap, [p.name for p in rec.probes]
    p = gap[0]
    assert p.verdict == "skipped"
    assert not p.statement          # a gap asserts no law
    assert "'scale' is a string with no declared domain" in (p.note or "")
    assert claim_reason_code(p) == ClaimReasonCode.NO_EVALUABLE_INPUTS
    # the old artefact, a float thrown at the str param and the raise
    # recorded as a synthesis failure, must not appear
    assert not any("could not synthesize valid inputs" in (p.note or "")
                   for p in rec.probes)


def test_literal_param_samples_and_adjudicates():
    rec = check(_literal_scale, claims=[
        claim('for r in [0, 1], scale in {"square"}, '
              "f(r, scale) == 1 - r^2")])
    by_name = {p.name: p for p in rec.probes}
    law = next(p for n, p in by_name.items() if "f_r_scale" in n or
               p.statement.startswith("f(r, scale)"))
    assert law.verdict in ("holds", "proven"), (law.verdict, law.note)
    assert not any("could not synthesize valid inputs" in (p.note or "")
                   for p in rec.probes)


def test_literal_domain_inferred_and_rendered_when_not_declared():
    # the claim leaves `scale` unbound: its Literal annotation supplies
    # the whole value set, the note renders the inference explicitly,
    # and the claim adjudicates over BOTH values, falsified, because
    # the sqrt branch breaks the square law
    rec = check(_literal_scale, claims=[
        claim("for r in [0, 0.9], f(r, scale) == 1 - r^2")])
    law = next(p for p in rec.probes
               if "f(r, scale) = 1 - r^2" in p.statement)
    assert "from its own annotation's stated values" in (law.note or "")
    assert law.verdict == "falsified", (law.verdict, law.note)


def test_input_synthesis_failure_carries_the_reason_code():
    from mathema.records import Probe
    p = Probe("callable", "", "skipped",
              note="could not synthesize valid inputs from the signature "
                   "(TypeError: boom)",
              meta={"mathema.probe_gap": "input-synthesis"})
    assert claim_reason_code(p) == ClaimReasonCode.NO_EVALUABLE_INPUTS


def test_param_kinds_infers_numpy_arraylike_params():
    # an unannotated parameter turned into an array (np.asarray) or read
    # through an array attribute (.shape) is sequence-like, so it is
    # synthesized as a sequence rather than a scalar (static analysis,
    # numpy need not be importable).
    def uses_asarray(values, scale: str = "info"):
        import numpy as np
        n = np.asarray(values).shape[0]
        return n if scale == "info" else 0

    def uses_shape(x):
        return x.shape[0]

    assert analyze(uses_asarray).param_kinds["values"] == "sequence"
    assert analyze(uses_shape).param_kinds["x"] == "sequence"


def test_unannotated_numpy_sequence_param_is_synthesized_as_a_sequence(tmp_path):
    import importlib.util
    import textwrap

    import pytest
    pytest.importorskip("numpy")
    from mathema.conjecture import check_conjectures, claim as _claim

    src = textwrap.dedent('''
        import numpy as np

        def seq_then_string(values, scale: str = "info", frac: float = 0.35):
            n = np.asarray(values).shape[0]
            if scale == "info":
                return n * frac
            raise ValueError(f"unknown scale {scale!r}")

        def needs_seven(x, y, lenient: bool = False) -> float:
            n = len(np.asarray(x, float))
            if not lenient and n <= 6:
                raise ValueError("need more than 6 samples")
            return float(np.sum(np.asarray(x, float)))
    ''')
    p = tmp_path / "npmod.py"
    p.write_text(src)
    spec = importlib.util.spec_from_file_location("npmod", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # L14: values is a sequence, so np.asarray(values).shape[0] works and
    # scale='nope' raises ValueError; the claim holds, no spurious
    # IndexError falsification from a scalar-synthesized `values`.
    (pr,) = check_conjectures(
        mod.seq_then_string,
        [_claim('raises(f(values, "nope", 0.35), ValueError)')])
    assert pr.verdict == "holds", pr.counterexample

    # L15: x is a sequence, so len() works; f(x, y, True) never raises,
    # and `assuming is_defined(f)` runs trials instead of unknown(n=0).
    (pr2,) = check_conjectures(
        mod.needs_seven,
        [_claim("assuming is_defined(f), f(x, y, True) >= -1e9",
                route="probe")])
    assert pr2.verdict == "holds" and pr2.n > 0


def test_string_literal_call_argument_shows_in_the_witness(tmp_path):
    # a literal call argument is passed verbatim, so a falsifying witness
    # shows it (a string "info"), never a synthesized 0 in the literal's
    # slot.
    import importlib.util
    import textwrap

    import pytest
    pytest.importorskip("numpy")
    from mathema.conjecture import check_conjectures, claim as _claim

    src = textwrap.dedent('''
        import numpy as np

        def seq_then_string(values, scale: str = "info", frac: float = 0.35):
            n = np.asarray(values).shape[0]
            if scale == "info":
                return n * frac
            raise ValueError(f"unknown scale {scale!r}")
    ''')
    p = tmp_path / "sm.py"
    p.write_text(src)
    spec = importlib.util.spec_from_file_location("sm", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # scale="info" does not raise, so the ValueError raises claim
    # falsifies, and its witness shows the string literal it was called
    # with, not a synthesized value.
    (pr,) = check_conjectures(
        mod.seq_then_string,
        [_claim('raises(f(values, "info", 0.35), ValueError)')])
    assert pr.verdict == "falsified"
    assert "'info'" in (pr.counterexample or "")
