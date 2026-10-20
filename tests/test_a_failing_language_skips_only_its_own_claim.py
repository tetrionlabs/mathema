# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A language package whose hook raises (`hazards()`, `sample()`,
`contains()`, ...) does not end the check: the claim that ranges over
that language is skipped, its note naming the language, the hook and
the exception, and every other claim is adjudicated as it would be
without it."""
import pytest

import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.languages import StringLanguage, register_language, unregister_language


class _Broken(StringLanguage):
    """Letters, with one hook that raises."""

    def __init__(self, hook):
        super().__init__("broken", char_ok=str.isalpha, pool="abc",
                         outside_pool="1 ")
        self.hook = hook

    def hazards(self):
        if self.hook == "hazards":
            raise RuntimeError("hazards table missing")
        return super().hazards()

    def sample(self, rng):
        if self.hook == "sample":
            raise KeyError("pool")
        return super().sample(rng)

    def contains(self, value):
        if self.hook == "contains":
            raise ValueError("contains broke")
        return super().contains(value)


def size(s: str) -> int:
    return len(s)


@pytest.fixture
def broken(request):
    register_language("broken", _Broken(request.param))
    yield request.param
    unregister_language("broken")


OVER_IT = ["for s in L[broken], f(s) >= 0",
           "for s in L[broken], is_language_defined(s)"]


@pytest.mark.parametrize("broken", ["hazards", "sample", "contains"], indirect=True)
@pytest.mark.parametrize("text", OVER_IT)
def test_the_claim_over_a_failing_language_is_skipped_with_the_reason(broken, text):
    rows = {p.name: p for p in check_conjectures(size, [claim(text),
                                                       claim("f('ab') == 2")])}
    assert rows["f_ab_eq_2"].verdict == "proven"
    (row,) = [p for n, p in rows.items() if n != "f_ab_eq_2"]
    assert row.verdict == "skipped", (row.verdict, row.note)
    if broken != "sample" or "is_language_defined" in text:
        assert "L[broken] raised" in row.note, row.note
    assert row.counterexample is None


@pytest.mark.parametrize("broken", ["hazards"], indirect=True)
def test_the_reason_names_the_language_hook_and_exception(broken):
    (row, _other) = sorted(check_conjectures(size, [claim(OVER_IT[0]),
                                                    claim("f('ab') == 2")]),
                           key=lambda p: p.name != "f_s_ge_0")
    assert row.name == "f_s_ge_0"
    assert "L[broken]" in row.note and "hazards()" in row.note, row.note
    assert "RuntimeError" in row.note and "hazards table missing" in row.note


@pytest.mark.parametrize("broken", ["hazards"], indirect=True)
def test_mathema_check_completes_and_records_the_other_claims(broken):
    rows = {p.name: p for p in mathema.check(
        size, claims=[OVER_IT[0], "f('ab') == 2"]).probes}
    assert rows["f_ab_eq_2"].verdict == "proven"
    assert rows["f_s_ge_0"].verdict == "skipped"


def test_an_engine_error_outside_any_language_hook_still_raises(monkeypatch):
    import mathema.conjecture as conjecture

    def broken_run(*_a, **_k):
        raise RuntimeError("engine defect")

    monkeypatch.setattr(conjecture, "_check_conjectures", broken_run)
    with pytest.raises(RuntimeError, match="engine defect"):
        check_conjectures(size, [claim("f('ab') == 2")])
