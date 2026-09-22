# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""spec.py's domain (de)serialization: declare()/entry_claims() must be
lossless for every domain-bound shape split_quantifier() can produce (an
open or closed Interval, "Z"/"N", a discrete frozenset), round-trip
through a real YAML dump/load, stay backward-compatible with the
pre-existing plain [lo, hi] list files every earlier mathema release
wrote, and feed claims_fingerprint() a value that actually changes when
a domain boundary's open/closed-ness changes.
"""
import yaml

from mathema.authoring import claims as claims_decorator
from mathema.authoring import _domain_from_declared_claims
from mathema.conjecture import claim
from mathema.grammar import Domain
from mathema.spec import claims_fingerprint, declare, entry_claims


def _yaml_round_trip(obj):
    return yaml.safe_load(yaml.dump(obj))


def test_declare_entry_claims_round_trip_an_open_interval():
    cj = claim("for x in (0, 1], f(x) <= 1")
    stored = _yaml_round_trip({"claims": [declare(cj)]})
    reparsed = entry_claims(stored)
    bound = reparsed[0].domain["x"]
    assert bound == (0.0, 1.0)
    assert bound.closed_lo is False
    assert bound.closed_hi is True


def test_declare_entry_claims_round_trip_an_integer_domain():
    # a bare named-set spelling ("Z") is a deliberate, stated type
    # choice (`explicit_type=True`), round-tripped through JSON/YAML,
    # see grammar.py's parse_binding().
    cj = claim("for x in Z, f(x) >= 0")
    stored = _yaml_round_trip({"claims": [declare(cj)]})
    reparsed = entry_claims(stored)
    assert reparsed[0].domain["x"] == Domain(base_type="Z", explicit_type=True)


def test_declare_entry_claims_round_trip_a_discrete_set():
    cj = claim("for x in {0, 1}, f(x) >= 0")
    stored = _yaml_round_trip({"claims": [declare(cj)]})
    reparsed = entry_claims(stored)
    bound = reparsed[0].domain["x"]
    assert isinstance(bound, frozenset)
    assert bound == frozenset({0.0, 1.0})


def test_entry_claims_still_reads_the_legacy_plain_list_shape():
    # every domain bound written by mathema before declare() started
    # emitting a self-describing dict, must keep loading unchanged,
    # forever, with no migration step.
    legacy = {"claims": [{"name": "bounded", "statement": "f(x) <= 1",
                          "domain": {"x": [0.0, 1.0]}}]}
    reparsed = entry_claims(legacy)
    bound = reparsed[0].domain["x"]
    assert bound == (0.0, 1.0)
    assert bound.closed_lo is True
    assert bound.closed_hi is True


def test_entry_claims_source_reads_as_a_real_sentence_when_no_family():
    # entry_claims()'s own source fallback used to be the bare word
    # "authored", making check_conjectures()'s "conjectured by {source}"
    # note read as "conjectured by authored", not a real sentence.
    stored = {"claims": [{"name": "bounded", "statement": "f(x) <= 1"}]}
    reparsed = entry_claims(stored)
    assert reparsed[0].source == "declared"


def test_claims_fingerprint_changes_when_a_boundary_opens():
    closed = declare(claim("for x in [0, 1], f(x) <= 1", name="bounded"))
    open_lo = declare(claim("for x in (0, 1], f(x) <= 1", name="bounded"))
    assert claims_fingerprint([closed]) != claims_fingerprint([open_lo])


def test_claims_fingerprint_is_stable_for_the_same_domain():
    a = declare(claim("for x in (0, 1], f(x) <= 1", name="bounded"))
    b = declare(claim("for x in (0, 1], f(x) <= 1", name="bounded"))
    assert claims_fingerprint([a]) == claims_fingerprint([b])


def test_claims_fingerprint_handles_the_legacy_list_shape_too():
    legacy = {"name": "bounded", "statement": "f(x) <= 1", "domain": {"x": [0.0, 1.0]}}
    # must not raise, and must match the equivalent closed-interval new shape
    new_shape = declare(claim("for x in [0, 1], f(x) <= 1", name="bounded"))
    assert claims_fingerprint([legacy]) == claims_fingerprint([new_shape])


def test_decorator_declared_interval_domain_still_enforced(tmp_path):
    # guards the silent-regression risk: _domain_from_declared_claims()
    # reads declare()'s own output shape directly, and must keep
    # recognizing an interval domain now that declare() emits a dict
    # instead of a [lo, hi] list.
    @claims_decorator(claim("for x in [0, 2], f(x) >= 0"))
    def guarded(x: float) -> float:
        return x

    domain = _domain_from_declared_claims(guarded, key=None, root=str(tmp_path))
    assert domain == {"x": (0.0, 2.0)}
