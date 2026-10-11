# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A frontend registered under the `mathema.frontends` entry-point group
is asked for a callable's body before the Python frontend: the KOINE
document it writes is the body the claims are proved from, the record's
provenance names it, and when the Python frontend can read the callable
too the hash of each frontend's body is kept on the facts. A frontend
that declines costs nothing, and one that fails is skipped with a
warning."""
import inspect
import textwrap
import warnings

import pytest

import mathema
from mathema import identity
from mathema.analysis import analyze_source, get_tree
from mathema.koine import Document, koine_hash
from mathema.koine import frontends
from mathema.koine._render import materialise, render
from mathema.spec import to_spec
from tests._koine_docs import golden_text

GROWTH = "for r in [-1, 5], for x in [-10, 10], f(x, r) == x * (1 + r)"

#: the sample frontend: writes the body of any callable named `growth`
#: from `growth.koi` beside it, under its own lifter line, and of no
#: other callable
FRONTEND = '''
import pathlib

_TEXT = (pathlib.Path(__file__).parent / "growth.koi").read_text()


def write(fn):
    if getattr(fn, "__name__", None) != "growth":
        return None
    return _TEXT


def broken(fn):
    raise RuntimeError("cannot read this callable")
'''

TARGETS = '''
def growth(x: float, r: float) -> float:
    if r < -1:
        raise ValueError("rate below -1")
    g = 1 + r
    return x * g


def other(x: float) -> float:
    return 2 * x
'''


def _install(tmp_path, monkeypatch, entries: str, distribution: str = "sample_frontend"):
    """A throwaway distribution on the path: its metadata, its entry
    points under `mathema.frontends`, and the module they name."""
    text = golden_text("growth_py").replace('name: "mathema", version: "0"',
                                            'name: "sample", version: "3.1"')
    (tmp_path / "growth.koi").write_text(text)
    (tmp_path / "sample_frontend.py").write_text(FRONTEND)
    (tmp_path / "sample_targets.py").write_text(TARGETS)
    info = tmp_path / f"{distribution}-3.1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {distribution}\nVersion: 3.1\n")
    (info / "entry_points.txt").write_text(
        "[mathema.frontends]\n" + textwrap.dedent(entries))
    monkeypatch.syspath_prepend(str(tmp_path))
    frontends._reset_discovery()
    return Document.parse(text)


@pytest.fixture(autouse=True)
def _forget_frontends():
    frontends._reset_discovery()
    yield
    frontends._reset_discovery()


def _targets():
    import importlib
    import sys
    sys.modules.pop("sample_targets", None)
    return importlib.import_module("sample_targets")


def _stand_in(d: Document):
    """A callable named `growth` with no source to read: the Python
    frontend cannot write its body."""
    impl = materialise(render(d))
    scope = {"impl": impl}
    exec("def growth(x, r):\n    return impl(x, r)\n", scope)
    fn = scope["growth"]
    fn.__signature__ = inspect.signature(impl)
    return fn


def test_a_registered_frontend_body_proves_a_claim_and_the_record_names_it(
        tmp_path, monkeypatch):
    d = _install(tmp_path, monkeypatch, "sample = sample_frontend:write\n")
    fn = _stand_in(d)
    rec = mathema.check(fn, claims=[GROWTH])
    rows = [(p.verdict, p.route) for p in rec.probes
            if not p.name.endswith("[float]") and p.name != "purity"
            and (p.meta or {}).get("mathema.surface") != "mathema"]
    assert rows == [("proven", "derive")], rows
    assert rec.facts.koine == d
    spec = to_spec(rec)
    assert spec["meta"]["mathema.provenance"] == {
        "frontend": {"name": "sample", "distribution": "sample_frontend",
                     "version": "3.1", "language": "py"},
        "koine_hash": koine_hash(d),
    }


def test_when_both_frontends_write_the_body_both_hashes_are_kept(tmp_path, monkeypatch):
    d = _install(tmp_path, monkeypatch, "sample = sample_frontend:write\n")
    growth = _targets().growth
    facts = analyze_source(growth)
    python_form = identity.form_hash(get_tree(growth)[1])
    assert facts.koine == d
    assert facts.body_hashes == {"sample": koine_hash(d), "python": python_form}
    assert facts.signature == identity.signature_string(growth)
    spec = to_spec(mathema.check(growth, claims=[GROWTH]))
    assert spec["meta"]["mathema.provenance"]["body_hashes"] == facts.body_hashes


def test_a_callable_no_frontend_claims_is_read_by_the_python_frontend(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "sample = sample_frontend:write\n")
    other = _targets().other
    facts = analyze_source(other)
    assert facts.koine is None and facts.provenance is None and facts.body_hashes == {}
    assert facts.form_is_computed()
    assert "mathema.provenance" not in (to_spec(mathema.check(other, claims=[])).get("meta")
                                        or {})


def test_a_frontend_that_fails_is_skipped_with_a_warning(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "broken = sample_frontend:broken\n")
    growth = _targets().growth
    with pytest.warns(UserWarning, match="broken"):
        facts = analyze_source(growth)
    assert facts.koine is None and facts.form_is_computed()


def test_a_failing_frontend_does_not_stop_the_next_one(tmp_path, monkeypatch):
    d = _install(tmp_path, monkeypatch,
                 "sample = sample_frontend:write\nbroken = sample_frontend:broken\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        facts = analyze_source(_targets().growth)
    assert facts.koine == d
    assert facts.provenance["frontend"]["name"] == "sample"


def test_the_names_a_registered_body_reads_resolve_without_the_callable_importing_them(
        tmp_path, monkeypatch):
    from tests._koine_docs import at, koi
    square_sum = ("operator::binary::addition(operator::binary::multiplication(x, x), "
                  "operator::binary::multiplication(r, r))")
    text = koi(f"statement::return(function::root::square({square_sum}), {at(2)})",
               name="growth", lifter="sample")
    _install(tmp_path, monkeypatch, "sample = sample_frontend:write\n")
    (tmp_path / "growth.koi").write_text(text)
    fn = _stand_in(Document.parse(text))
    assert "math" not in fn.__globals__
    rec = mathema.check(fn, claims=["for x in [-10, 10], for r in [-10, 10], "
                                    "f(x, r) >= 0"])
    rows = [(p.verdict, p.route) for p in rec.probes
            if not p.name.endswith("[float]") and p.name != "purity"
            and (p.meta or {}).get("mathema.surface") != "mathema"]
    assert rows == [("proven", "derive")], rows


@pytest.mark.needs_full_proof_budget
def test_a_python_body_that_moves_under_the_same_registered_body_makes_the_record_stale(
        tmp_path, monkeypatch):
    import sys

    from mathema.verify import verify_project
    _install(tmp_path, monkeypatch, "sample = sample_frontend:write\n")
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "sample_targets.claims.yaml").write_text(
        f"sample_targets.growth:\n  claims:\n    - name: growth\n"
        f"      statement: '{GROWTH}'\n")

    def sweep():
        monkeypatch.delitem(sys.modules, "sample_targets", raising=False)
        return {r["key"]: r for r in verify_project(str(tmp_path)).keys}

    sweep()
    assert sweep()["sample_targets.growth"]["why"] == "fresh"
    (tmp_path / "sample_targets.py").write_text(TARGETS.replace("g = 1 + r", "g = r + 1"))
    assert sweep()["sample_targets.growth"]["why"] == "body changed"


def test_an_entry_named_python_is_refused_so_it_never_stands_for_the_python_frontend(
        tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "python = sample_frontend:write\n")
    growth = _targets().growth
    with pytest.warns(UserWarning, match="python"):
        facts = analyze_source(growth)
    assert facts.koine is None and facts.body_hashes == {}
    assert facts.form_is_computed()
