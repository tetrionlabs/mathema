# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Conformance against the CDD v0.2 spec's normative core
(github.com/aaronbyrnephd/claim-driven-development, `record-schema.md`,
"What this document requires, and what it leaves alone").

v0.2 pins a deliberately small core: two tools must agree on `claims`
(each with `name`, `statement`, `verdict`, `route` once adjudicated,
and `authored` with at least `authored.surface`), `grammar`, `identity`
(`form` and `sig`) and `lineage` (`CDD_spec_version`). Everything else
in the spec is a recommended spelling, not a conformance requirement,
so this file splits in two: the CORE section is what conformance
means, and the RECOMMENDED section checks the optional facts mathema
chooses to record against the spellings the spec names for them,
as quality pins rather than conformance.

One real, nontrivial function walks the full pipeline: docstring
claims on both routes, a declared and enforced domain,
`mathema.check()`, `spec.to_spec()`.
"""

import pytest
import yaml

import mathema
from mathema.authoring import materialize_declared
from mathema.spec import to_spec

_SOURCE = '''\
def shrink(x: float, alpha: float) -> float:
    """Blend x toward zero by alpha.

    Intent:
        A simple weighted shrinkage toward zero.

    Claims:
        shrinks [probe]: for alpha in [0, 1], abs(f(x, alpha)) <= abs(x)
        affine_in_x [derive]: for alpha in [0, 1], d(f(x, alpha), x, x) == 0
    """
    if alpha < 0 or alpha > 1:
        raise ValueError("alpha out of range")
    return (1.0 - alpha) * x
'''


@pytest.fixture
def shrink_module(tmp_path):
    fixture = tmp_path / "shrink_fixture.py"
    fixture.write_text(_SOURCE)
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        mod = __import__("shrink_fixture")
    finally:
        sys.path.remove(str(tmp_path))
    return mod


@pytest.fixture
def verified_spec(shrink_module):
    r = mathema.check(shrink_module.shrink, domain={"alpha": (0.0, 1.0)},
                      claims=["excluded_outside_domain(alpha)"])
    return to_spec(r)


@pytest.fixture
def declared_yaml(shrink_module, tmp_path):
    path = materialize_declared(shrink_module.shrink, key="shrink", root=str(tmp_path))
    return yaml.safe_load(open(path))["shrink"]


# --- sanity: the pipeline itself actually produces the mixed evidence ------
# --- this suite needs to say anything meaningful about -----------------

def test_fixture_pipeline_produces_a_real_mix_of_evidence(verified_spec):
    verdicts = {c["name"]: c["verdict"] for c in verified_spec["claims"]}
    assert verdicts["shrinks"] == "holds"                 # real probe evidence
    assert verdicts["affine_in_x"] == "proven"             # real derive evidence
    # real enforcement evidence: the DECLARED exclusion, held by the
    # fixture's own raising alpha guard through the examine trials
    assert verdicts["excluded_outside_domain[alpha]"] == "holds"


# --- THE NORMATIVE CORE (record-schema.md, v0.2) ----------------------------
# a conformance suite tests this, and nothing beyond it

def test_core_every_claim_has_name_statement_verdict(verified_spec):
    for c in verified_spec["claims"]:
        assert c.get("name"), c
        assert c.get("statement"), c
        assert c.get("verdict"), c


def test_core_route_names_the_mechanism_once_adjudicated(verified_spec):
    # route is null until something decided; every claim in this
    # fixture was adjudicated, so every row names its real mechanism,
    # and never a cascade value (auto/best are input-side only)
    for c in verified_spec["claims"]:
        assert c.get("route"), c
        assert c["route"].split(":", 1)[0] not in ("auto", "best"), c


def test_core_authored_is_an_object_with_a_surface(verified_spec):
    # authored.surface is the one always-known fact and the interop
    # minimum; the record schema requires nothing richer
    for c in verified_spec["claims"]:
        authored = c.get("authored")
        assert isinstance(authored, dict), c
        assert authored.get("surface"), c


def test_core_grammar_is_stated(verified_spec):
    assert verified_spec["grammar"] == "mathema"


def test_core_identity_has_form_and_sig(verified_spec):
    identity = verified_spec["identity"]
    assert identity["form"]
    assert identity["sig"]


def test_core_lineage_states_the_spec_version(verified_spec):
    # the spelled-out key, adopted by the spec from this implementation
    assert verified_spec["lineage"]["CDD_spec_version"] == mathema.SPEC_VERSION


def test_schema_version_is_a_top_level_dispatch_key(verified_spec):
    # a consumer dispatches on this before reading anything else, so it
    # sits at the top level, not inside lineage; the two state the same
    # version by construction
    assert verified_spec["schema_version"] == mathema.SPEC_VERSION
    assert (verified_spec["schema_version"]
            == verified_spec["lineage"]["CDD_spec_version"])


# --- RECOMMENDED SPELLINGS (quality pins, not conformance) ------------------
# mathema records these optional facts; when it does, the spec names
# the spelling other tools will expect, and these tests hold it there

def test_top_level_has_name_signature_intent(verified_spec):
    assert verified_spec["name"] == "shrink"
    assert "float" in verified_spec["signature"]
    assert verified_spec["intent"]


def test_identity_source_available_is_emitted_and_true_with_real_source(verified_spec):
    # "nothing proved" and "nothing to read" are different facts
    assert verified_spec["identity"]["source_available"] is True


def test_identity_pure_is_true_for_a_genuinely_pure_function(verified_spec):
    assert verified_spec["identity"]["pure"] is True


def test_doc_only_record_reports_null_purity_not_true():
    # "Say what you know, and no more": purity cannot be established
    # without source, so it is null, never a confident value
    facts = mathema.analyze(abs)   # a real builtin, no retrievable source
    assert facts.is_pure is None


def test_doc_only_identity_says_source_was_unavailable():
    r = mathema.check(abs)
    spec = to_spec(r)
    assert spec["identity"]["source_available"] is False
    assert spec["identity"]["pure"] is None


def test_verified_claims_carry_reasoning_and_lineage(verified_spec):
    assert verified_spec["reasoning"]
    assert verified_spec["lineage"]["generated_by"].startswith("mathema")


def test_authored_carries_the_origin_reference_when_known(verified_spec):
    # the docstring surface's line-level ref is computable, so it is
    # recorded: surface for interop, ref for the human chasing a
    # falsification back to its definition site
    claim = next(c for c in verified_spec["claims"] if c["name"] == "shrinks")
    assert claim["authored"]["surface"] == "docstring"
    assert ":docstring:" in claim["authored"]["ref"]


def test_route_reflects_how_it_was_actually_checked(verified_spec):
    probe_claim = next(c for c in verified_spec["claims"] if c["name"] == "shrinks")
    derive_claim = next(c for c in verified_spec["claims"] if c["name"] == "affine_in_x")
    assert probe_claim["route"] == "probe"
    assert derive_claim["route"] == "derive"


def test_claim_carries_domain_and_grammar_forward(verified_spec):
    # the self-contained-record principle: everything needed to read
    # and re-check a claim rides the verified row
    claim = next(c for c in verified_spec["claims"] if c["name"] == "shrinks")
    assert claim.get("domain")
    # grammar rides the record: a row states its own only when it differs
    # from the record-level grammar, so it is resolvable from either
    assert claim.get("grammar") or verified_spec.get("grammar")


def test_claim_meta_is_carried_when_present(verified_spec):
    # check_conjectures()'s own probe route attaches sampling/confidence
    # meta to every probe-route claim; "shrinks" is [probe]-tagged and
    # carries it, "affine_in_x" is [derive]-tagged and correctly
    # carries none of the sampling keys
    shrinks = next(c for c in verified_spec["claims"] if c["name"] == "shrinks")
    assert "mathema.sampling" in shrinks["meta"]
    affine = next(c for c in verified_spec["claims"] if c["name"] == "affine_in_x")
    assert affine["meta"]["mathema.surface"] == "docstring"
    # the region the evidence covered rides as the rendered condition
    assert affine.get("condition")


# --- declared shape ---------------------------------------------------------

def test_declared_claim_has_the_documented_fields(declared_yaml):
    claim = next(c for c in declared_yaml["claims"] if c["name"] == "shrinks")
    for field in ("name", "statement", "route", "domain"):
        assert field in claim, f"declared claim missing documented field {field!r}"


def test_declared_authored_object_reaches_the_verified_row(declared_yaml):
    # v0.2 sanctions a declared authored object (what the author knows,
    # carried forward by the checker); mathema's docstring surface
    # writes {surface, ref} there
    claim = next(c for c in declared_yaml["claims"] if c["name"] == "shrinks")
    assert isinstance(claim["authored"], dict)
    assert claim["authored"]["surface"] == "docstring"


def test_v01_bare_string_authored_reads_as_ref(tmp_path, shrink_module):
    # a v0.1.0-era record spelled authored as a bare string; a v0.2
    # reader treats it as {ref: <string>}
    import os
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    (claims_dir / "legacy.claims.yaml").write_text(
        "shrink_fixture.shrink:\n"
        "  claims:\n"
        "    - name: legacy_bound\n"
        '      statement: "for alpha in [0, 1], f(1.0, alpha) <= 1.0"\n'
        "      route: probe\n"
        '      authored: "geo/symspec.yaml"\n')
    cwd = os.getcwd()
    entry = mathema.retrieve(shrink_module.shrink, root=str(tmp_path))
    assert os.getcwd() == cwd
    r = mathema.check(shrink_module.shrink, declared=entry)
    spec = to_spec(r)
    row = next(c for c in spec["claims"] if c["name"] == "legacy_bound")
    assert row["authored"]["ref"] == "geo/symspec.yaml"
    assert row["authored"]["surface"] == "claims-file"


# --- acceptance: the verified_by stamp shape --------------------------------

def test_accepted_block_carries_who_when_and_the_form_binding(tmp_path, shrink_module):
    # the spec's acceptance principle: who decided, when, bound to the
    # code version it was about. mathema's object form records all
    # three; verified_by joins it only when a PIN is configured, which
    # tests/test_auth.py covers with a temp credential.
    import mathema as m
    m.write_spec(shrink_module.shrink, root=str(tmp_path))
    from mathema.acceptance import plan_acceptance
    plan = plan_acceptance(str(tmp_path), "shrink_fixture.shrink",
                           "shrinks", "evidence", by="tester")
    accepted = plan["accepted"]
    assert accepted["as"] == "evidence"
    assert accepted["at"]
    assert accepted["form"]
    assert accepted["by"] == "tester"
