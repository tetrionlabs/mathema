# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The compact underivability codes: blocked_code() over real
derivability reports, the CODE_TABLE lookup covering every code the
composer can emit, and diagnostic_report carrying the per-construct
detail (codes for machines, hints for humans) plus wraps."""
import math

from mathema import analyze
from mathema.diagnostics import diagnostic_report
from mathema.inventory import derivability_report
from mathema.reason_codes import (BranchReason, CODE_TABLE, LoopReason,
                                  blocked_code, describe_code)


def _mul_fold(xs: list) -> float:
    acc = 1.0
    for x in xs:
        acc = acc * x
    return acc


def _branchy(r: float, scale: str) -> float:
    if scale == "info":
        return math.sqrt(1.0 - r * r)
    return 1.0 - r * r


def _recursive(n: int) -> int:
    if n <= 1:
        return 1
    return n * _recursive(n - 1)


def test_loop_code_composes_from_the_fold_reason():
    code = blocked_code(derivability_report(_mul_fold))
    assert code == "loop:non-affine-update"
    entry = describe_code(code)
    assert entry is not None and entry["derive_unlock"] == "limitation"


def test_branch_needs_domain_names_the_parameters():
    code = blocked_code(derivability_report(_branchy))
    assert code == "branch:needs-domain(scale)"
    entry = describe_code(code)
    assert entry is not None and entry["derive_unlock"] == "actionable"
    assert "declare a domain" in entry["hint"]


def test_liftable_report_has_no_code():
    def clean(x: float) -> float:
        return 2.0 * x
    assert blocked_code(derivability_report(clean)) is None
    assert blocked_code(None) is None


def test_every_enum_value_has_a_table_entry():
    for slug in LoopReason.ALL:
        assert describe_code(f"loop:{slug}") is not None, slug
    for slug in BranchReason.ALL:
        assert describe_code(f"branch:{slug}") is not None, slug
    for code in CODE_TABLE:
        entry = CODE_TABLE[code]
        assert entry["derive_unlock"] in ("actionable", "limitation",
                                    "N/A"), code
        assert entry["meaning"] and entry["hint"], code


def test_describe_code_strips_decorations():
    assert describe_code("branch:needs-domain(scale, mode)") is not None
    assert describe_code("branch:untraceable-local+2") is not None
    # a loop whose own pieces hit an unsupported construct falls back
    # to the matching unsupported entry
    assert describe_code("loop:unsupported-call") is not None


def test_diagnostic_report_carries_constructs_and_wraps():
    facts = analyze(_branchy)
    rd = diagnostic_report(_branchy, facts)
    assert rd["liftable"] is False
    assert rd["blocked"] == "branch:needs-domain(scale)"
    assert rd["wraps"] is None
    constructs = rd["constructs"]
    assert constructs and all("line" in c and "code" in c for c in constructs)
    assert any(c.get("needs_domain_for") == ["scale"] for c in constructs)

    facts = analyze(_mul_fold)
    rd = diagnostic_report(_mul_fold, facts)
    assert rd["blocked"] == "loop:non-affine-update"
    c = rd["constructs"][0]
    # the interpolated human hint survives here (the CLI prints codes)
    assert "linear combination" in c["hint"]
    assert c["derive_unlock"] == "limitation"


def test_wraps_reported_on_the_liftable_side_too():
    def thin(x: float) -> float:
        return math.sqrt(x)
    rd = diagnostic_report(thin, analyze(thin))
    assert rd["liftable"] is True
    assert rd["wraps"] == "math.sqrt"


def test_docs_reason_code_page_covers_every_code():
    # docs/reason-codes.md is the human twin of CODE_TABLE, the two
    # stay together by construction
    import os
    page = open(os.path.join(os.path.dirname(__file__), "..", "docs",
                             "reason-codes.md")).read()
    for code in CODE_TABLE:
        assert f"`{code}`" in page, code


def test_reason_code_ids_are_stable_and_complete():
    # every code carries a major.minor id; ids are unique, cover the
    # table, and (like the codes themselves) are additive only.
    # The anchors below are released ids: renumbering any of them is
    # a public-interface break, not a cleanup.
    from mathema.reason_codes import CODE_GROUPS, CODE_IDS, CODE_TABLE
    assert set(CODE_IDS) == set(CODE_TABLE)
    assert len(set(CODE_IDS.values())) == len(CODE_IDS)
    assert CODE_IDS["stateful"] == "1.1"
    assert CODE_IDS["loop:no-loop"] == "2.1"
    assert CODE_IDS["loop:non-affine-update"] == "2.18"
    assert CODE_IDS["branch:needs-domain"] == "3.1"
    assert CODE_IDS["unsupported:unsupported-syntax"] == "4.1"
    assert CODE_IDS["implementation:overflow"] == "5.1"
    assert CODE_GROUPS == {"1": "structural", "2": "loop",
                           "3": "branch", "4": "unsupported",
                           "5": "implementation"}
    for name, cid in CODE_IDS.items():
        major = cid.split(".", 1)[0]
        expected = ("2" if name.startswith("loop:") else
                    "3" if name.startswith("branch:") else
                    "4" if name.startswith("unsupported:") else
                    "5" if name.startswith("implementation:") else "1")
        assert major == expected, (name, cid)


def test_select_codes_filters_by_name_id_and_group():
    from mathema.reason_codes import select_codes
    assert list(select_codes("2.18")) == ["loop:non-affine-update"]
    assert all(k.startswith("branch:") for k in select_codes("branch"))
    assert set(select_codes("1.1, loop:no-loop")) == \
        {"stateful", "loop:no-loop"}
    assert select_codes("no-such") == {}


def test_every_emitted_category_is_a_code_table_key():
    # the stability contract from the other direction: every
    # "category" literal the symbolic reader can emit must resolve
    # through describe_code(), so an agent never loses the remedy,
    # unsupported-statement went unlisted for a while and the only
    # symptom was a silent None
    import ast
    import os

    import mathema
    from mathema.reason_codes import CODE_TABLE

    pkg_dir = os.path.dirname(mathema.__file__)
    emitted = set()
    for dirpath, _dirs, files in os.walk(pkg_dir):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            with open(path) as fh:
                tree = ast.parse(fh.read(), filename=path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                for k, v in zip(node.keys, node.values):
                    if (isinstance(k, ast.Constant) and k.value == "category"
                            and isinstance(v, ast.Constant)
                            and isinstance(v.value, str)):
                        emitted.add(v.value)
    assert emitted, "the scan found no category literals at all"
    missing = {c for c in emitted
               if f"unsupported:{c}" not in CODE_TABLE}
    assert not missing, (
        f"emitted categories with no CODE_TABLE entry: {sorted(missing)}")


def test_implementation_causes_ride_a_falsified_claims_reason():
    # group 5 attaches to falsified claims through the stratum, the one
    # exception to falsified-carries-no-code; an ordinary falsification
    # still carries none
    from mathema.reason_codes import claim_reason_code
    from mathema.records import Probe

    plain = Probe("k", "s", "falsified", counterexample="x=1: 2 vs 3")
    assert claim_reason_code(plain) is None
    pinned = Probe("k", "s", "falsified", counterexample="x=1e308: raised",
                   meta={"mathema.stratum": {
                       "blame": "implementation",
                       "cause": "implementation:overflow"}})
    assert claim_reason_code(pinned) == "implementation:overflow"
    # an unknown cause string is not echoed
    bogus = Probe("k", "s", "falsified",
                  meta={"mathema.stratum": {"cause": "implementation:xyz"}})
    assert claim_reason_code(bogus) is None
