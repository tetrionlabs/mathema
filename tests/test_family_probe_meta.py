# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A registered family's probe may say what it resolved: a mapping as
the last element of its result, after `(verdict, checked, cx)` or the
four-element form with an established sketch, is merged into the
resulting `Probe.meta`. The three- and four-element forms without one
keep working unchanged. The mapping reaches the record whichever
report stands: when derive's `unknown` is kept over a probe that
skipped, the probe's meta is merged in under its own keys, derive's
keys winning on a clash. A mapping under `mathema.language` merges per
key with the language description core writes for every `L[...]`
binding, so a family's `return` entry sits beside the parameters."""
import pytest

from mathema import families
from mathema.claim_families import OutputPredicateFamily, SafetyFamily
from mathema.claims import check_conjectures, claim
from mathema.languages import StringLanguage, register_language, unregister_language

LETTERS = StringLanguage("letters", char_ok=str.isalpha, pool="abcXYZ")


def _echo(s):
    return s


class _Scripted(OutputPredicateFamily):
    """An output predicate whose probe answers a fixed result."""

    def __init__(self, name, result):
        super().__init__(name, lambda out: None)
        self._result = result

    def routes(self):
        return {"probe:algorithmic": lambda *args: self._result}


@pytest.fixture
def letters():
    register_language("letters", LETTERS)
    try:
        yield
    finally:
        unregister_language("letters")


@pytest.fixture
def scripted():
    added = []

    def install(result, name="output_is_scripted"):
        families.register(name, _Scripted(name, result))
        added.append(name)
        return name

    try:
        yield install
    finally:
        for name in added:
            families._REGISTRY.pop(name, None)


def _check(name, domain='{"a", "b"}'):
    (p,) = check_conjectures(_echo, [claim(f"for s in {domain}, {name}(f(s))")])
    return p


@pytest.mark.parametrize("result, verdict", [
    (("holds", 7, None, {"acme.target": "slug"}), "holds"),
    (("falsified", 3, "s='!'", {"acme.target": "slug"}), "falsified"),
])
def test_a_trailing_mapping_lands_in_the_record_meta(scripted, result, verdict):
    p = _check(scripted(result))
    assert p.verdict == verdict, (p.verdict, p.note)
    assert p.meta["acme.target"] == "slug"


def test_the_four_element_form_carries_a_mapping_too(scripted):
    p = _check(scripted(("holds", 5, None, None, {"acme.target": "slug"})))
    assert p.verdict == "holds" and p.meta["acme.target"] == "slug"


@pytest.mark.parametrize("result", [
    ("holds", 5, None),
    ("holds", 5, None, None),
])
def test_the_forms_without_a_mapping_are_unchanged(scripted, result):
    p = _check(scripted(result))
    assert p.verdict == "holds" and p.n == 5
    assert "acme.target" not in (p.meta or {})


def test_a_proven_examination_carries_its_mapping():
    def probe(fn, facts, cj, domain, rng, trials):
        return ("proven", 2, None, "every case of the class observed",
                {"acme.coverage": "exhaustive"})

    family = SafetyFamily("is_scripted_safe", derive=lambda *a, **k: None, probe=probe)
    families.register("is_scripted_safe", family)
    try:
        (p,) = check_conjectures(_echo, [claim('for s in {"a"}, is_scripted_safe(s)')])
    finally:
        families._REGISTRY.pop("is_scripted_safe", None)
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.meta["acme.coverage"] == "exhaustive"


def test_the_mapping_is_copied_not_shared(scripted):
    extra = {"acme.target": {"name": "slug"}}
    p = _check(scripted(("holds", 1, None, extra)))
    p.meta["acme.target"]["name"] = "changed"
    assert extra["acme.target"]["name"] == "slug"


def test_a_language_entry_merges_per_key_with_the_bindings(letters, scripted):
    returned = {"mathema.language": {"return": [{"name": "letters", "from": "s"}]}}
    p = _check(scripted(("holds", 4, None, returned)), domain="L[letters]")
    assert p.verdict == "holds", (p.verdict, p.note)
    described = p.meta["mathema.language"]
    assert described["return"] == [{"name": "letters", "from": "s"}]
    assert described["s"][0]["name"] == "letters"


def test_without_a_family_entry_the_bindings_stand_alone(letters, scripted):
    p = _check(scripted(("holds", 4, None)), domain="L[letters]")
    assert set(p.meta["mathema.language"]) == {"s"}


def test_a_mapping_in_any_other_position_is_not_meta(scripted):
    p = _check(scripted(("holds", 5, {"acme.target": "slug"})))
    assert "acme.target" not in (p.meta or {})


@pytest.mark.parametrize("result", [("holds", 1), ("holds", 1, None, None, None, {})])
def test_any_other_shape_is_refused(result):
    from mathema.claim_families import split_probe_result
    with pytest.raises(ValueError):
        split_probe_result(result)


def test_a_skipped_probe_still_puts_its_mapping_on_the_record(scripted):
    p = _check(scripted(("skipped", 0, "nothing to call",
                         {"acme.target": "slug",
                          "mathema.probe_gap": "string-domain-missing"})))
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert p.meta["acme.target"] == "slug"
    assert p.meta["mathema.probe_gap"] == "string-domain-missing"
    assert p.meta["mathema.derive_status"]


def test_derive_keys_win_over_a_skipped_probe(scripted):
    p = _check(scripted(("skipped", 0, "nothing to call",
                         {"mathema.derive_status": "from the probe"})))
    assert p.verdict == "unknown"
    assert p.meta["mathema.derive_status"] != "from the probe"


def test_a_skipped_probe_language_entry_merges_per_key(letters, scripted):
    returned = {"mathema.language": {"return": [{"name": "letters", "from": "s"}]}}
    p = _check(scripted(("skipped", 0, "nothing to call", returned)), domain="L[letters]")
    assert p.verdict == "unknown", (p.verdict, p.note)
    described = p.meta["mathema.language"]
    assert described["return"] == [{"name": "letters", "from": "s"}]
    assert described["s"][0]["name"] == "letters"
