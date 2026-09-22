# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The strict mathema-docstring schema: Intent:/Domain:/Claims: parsing,
symbol coverage, and the verified-record write-back helper."""
import importlib.util
import sys

import mathema
from mathema.docstring import (docstring_sync, docstring_sync_checklist,
                               parse_mathema_docstring, render_docstring)
import pytest



def _import_module(tmp_path, name: str, src: str):
    """Write `src` to a real file and import it, docstring_sync()
    (like parse_mathema_docstring()) needs inspect.getsource() to work,
    which a docstring patched onto an inline function after the fact
    can't provide."""
    mod_path = tmp_path / f"{name}.py"
    mod_path.write_text(src)
    spec = importlib.util.spec_from_file_location(name, mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    _LOADED_FIXTURE_MODULES.append(name)
    spec.loader.exec_module(mod)
    return mod


_LOADED_FIXTURE_MODULES: list = []


@pytest.fixture(autouse=True)
def _unload_fixture_modules():
    # fixture modules registered in sys.modules must not outlive their
    # test: inspect.getsource resolves against currently-loaded module
    # state, so a leaked name is cross-test contamination waiting to
    # collide
    yield
    while _LOADED_FIXTURE_MODULES:
        sys.modules.pop(_LOADED_FIXTURE_MODULES.pop(), None)



def well_formed(x: list, alpha: float) -> float:
    """Exponentially weighted moving average.

    Intent:
        Blends each new value v into the running mean.

    Domain:
        alpha: (0, 1]

    Claims:
        bounded: for x in [0, 1], f(x) <= 1
    """
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def missing_intent(x: float) -> float:
    """Claims:
        nonneg: f(x) >= 0
    """
    return x * 2


def uncovered_symbol(rows: list) -> float:
    """Sums every value in a nested sequence.

    Intent:
        Adds up every number across every row.
    """
    t = 0.0
    for row in rows:
        for v in row:   # v is never mentioned below; should be flagged
            t += v
    return t


def malformed_domain(x: float) -> float:
    """A trivial identity.

    Intent:
        Returns x unchanged.

    Domain:
        x: not-an-interval
    """
    return x


def empty_claims_header(x: float) -> float:
    """A trivial identity.

    Intent:
        Returns x unchanged.

    Claims:
        this is not a valid claim line at all
    """
    return x


def test_well_formed_docstring_conforms():
    parsed = parse_mathema_docstring(well_formed)
    assert parsed.intent == "Blends each new value v into the running mean."
    # the domain lives in the claim's own quantifier now, not in a
    # separate `Domain:` block
    assert {c["name"] for c in parsed.claims} == {"bounded"}
    assert parsed.symbols_required == {"x", "alpha", "v"}
    assert parsed.symbols_documented == {"x", "alpha", "v"}
    assert parsed.errors == []
    assert parsed.score == parsed.applicable
    assert parsed.conforms is True


def test_missing_intent_costs_score_but_not_an_error():
    parsed = parse_mathema_docstring(missing_intent)
    assert parsed.intent is None
    assert parsed.errors == []
    assert parsed.score < parsed.applicable
    assert parsed.conforms is False


def test_uncovered_loop_variable_is_an_error():
    parsed = parse_mathema_docstring(uncovered_symbol)
    assert "v" in parsed.symbols_required
    assert "v" not in parsed.symbols_documented
    assert any("'v'" in e for e in parsed.errors)
    assert parsed.conforms is False


def test_claims_header_with_nothing_parsed_is_an_error():
    parsed = parse_mathema_docstring(empty_claims_header)
    assert parsed.claims == []
    assert any("Claims:" in e for e in parsed.errors)


def test_render_docstring_requires_a_verified_record(tmp_path):
    try:
        render_docstring(well_formed, root=str(tmp_path))
    except ValueError as e:
        assert "no verified record" in str(e)
    else:
        raise AssertionError("expected ValueError for an unverified function")


def test_render_docstring_writes_back_held_claims(tmp_path):
    def add(a: float, b: float) -> float:
        """Adds two numbers.

        Claims:
            commutative_extra: f(a, b) == f(b, a)
        """
        return a + b

    mathema.write_spec(add, root=str(tmp_path))
    text = render_docstring(add, root=str(tmp_path))
    assert "Claims:" in text
    assert "commutative_extra" in text
    assert "f(a, b) = f(b, a)" in text


# ---- docstring_sync() -------------------------------------------------

def test_docstring_sync_raises_unions_claim_and_prose_without_double_counting(tmp_path):
    mod = _import_module(tmp_path, "sync_raises_mod", (
        "def f(a, b):\n"
        "    \"\"\"Does a thing.\n"
        "\n"
        "    Raises:\n"
        "        ValueError: on bad a.\n"
        "\n"
        "    Claims:\n"
        "        raises_b: raises(f(a, b), TypeError)\n"
        "    \"\"\"\n"
        "    if a < 0:\n"
        "        raise ValueError('bad a')\n"
        "    if b < 0:\n"
        "        raise TypeError('bad b')\n"
        "    return a + b\n"
    ))
    s = docstring_sync(mod.f, root=str(tmp_path))
    assert s.raises_total == 2
    assert s.raises_covered == 2   # ValueError via prose, TypeError via the claim


def test_docstring_sync_domain_declared_and_enforced(tmp_path):
    mod = _import_module(tmp_path, "sync_domain_mod", (
        "from mathema import enforce_domain\n"
        "\n"
        "\n"
        "from typing import Annotated\n"
        "from mathema.types import Probability\n"
        "\n"
        "\n"
        "@enforce_domain()\n"
        "def enforced(p: Annotated[float, Probability]) -> float:\n"
        "    \"\"\"Uses p directly.\"\"\"\n"
        "    return p\n"
        "\n"
        "\n"
        "def unenforced(p: Annotated[float, Probability]) -> float:\n"
        "    \"\"\"Uses p directly.\"\"\"\n"
        "    return p\n"
    ))
    enforced_sync = docstring_sync(mod.enforced, root=str(tmp_path))
    unenforced_sync = docstring_sync(mod.unenforced, root=str(tmp_path))
    assert enforced_sync.domain_declared == 1
    assert enforced_sync.domain_enforced is True
    assert unenforced_sync.domain_declared == 1
    assert unenforced_sync.domain_enforced is False


def test_docstring_sync_no_domain_declared_is_not_applicable(tmp_path):
    mod = _import_module(tmp_path, "sync_no_domain_mod", (
        "def f(p: float) -> float:\n"
        "    \"\"\"Uses p directly.\"\"\"\n"
        "    return p\n"
    ))
    s = docstring_sync(mod.f, root=str(tmp_path))
    assert s.domain_declared == 0
    assert s.domain_enforced is None


def test_docstring_sync_type_coverage_params_and_return(tmp_path):
    # the typing system is the one place a type belongs: a parameter
    # counts as typed via its annotation (Annotated included) or a
    # Domain: entry; the return via its annotation. There is no
    # docstring Types: block any more, and loop-variable typing is not
    # a scored dimension (a fold accumulator's range enters through
    # Domain:, which symbol coverage already encourages).
    mod = _import_module(tmp_path, "sync_typed_mod", (
        "def f(x: float, y) -> float:\n"
        "    \"\"\"Sums a sequence of values.\n"
        "\n"
        "    Domain:\n"
        "        y: [0, 100]\n"
        "        v: [0, 100]\n"
        "    \"\"\"\n"
        "    total = 0.0\n"
        "    for v in y:\n"
        "        total += v\n"
        "    return total + x\n"
    ))
    s = docstring_sync(mod.f, root=str(tmp_path))
    assert s.params_typeable == 2
    # only the real annotation counts now: a `Domain:` entry used to
    # be credited as typing, and that block is gone; it was a
    # domain statement, never a type
    assert s.params_typed == 1
    assert not hasattr(s, "internal_vars_typeable")
    assert s.return_typed is True


def test_docstring_sync_callees_are_direct_only(tmp_path):
    mod = _import_module(tmp_path, "sync_chain_mod", (
        "def level_c(x):\n"
        "    return x + 1\n"
        "\n"
        "\n"
        "def level_b(x):\n"
        "    return level_c(x) * 2\n"
        "\n"
        "\n"
        "def level_a(x):\n"
        "    \"\"\"Calls level_b.\"\"\"\n"
        "    return level_b(x)\n"
        "\n"
        "\n"
        "def level_0(x):\n"
        "    \"\"\"Calls level_a, three hops from level_c.\"\"\"\n"
        "    return level_a(x)\n"
    ))
    # the dimension covers the immediate call surface: level_c is a
    # transitive callee of level_0 and never counted for it, a
    # central undocumented callee already compounds through each
    # caller's own row
    a_sync = docstring_sync(mod.level_a, root=str(tmp_path))
    root_sync = docstring_sync(mod.level_0, root=str(tmp_path))
    assert a_sync.callee_funcs_total == 1          # level_b only
    assert a_sync.callee_funcs_documented == 0     # no docstring
    assert root_sync.callee_funcs_total == 1       # level_a only
    assert root_sync.callee_funcs_documented == 1  # level_a has one


def test_docstring_sync_claims_floor_is_informational_only(tmp_path):
    mod = _import_module(tmp_path, "sync_floor_mod", (
        "def f(a, b, c):\n"
        "    \"\"\"Undocumented branches, no claims, no domain.\n"
        "\n"
        "    Intent:\n"
        "        Adds three things together with some guards.\n"
        "    \"\"\"\n"
        "    if a < 0:\n"
        "        raise ValueError('bad a')\n"
        "    if b < 0:\n"
        "        raise TypeError('bad b')\n"
        "    return a + b + c\n"
    ))
    s = docstring_sync(mod.f, root=str(tmp_path))
    # one claim per relevant family per target: two definedness
    # conjuncts, the three unconditional battery members, monotonicity
    # and shape for each of a/b/c, and a raises for each guarded param
    assert s.claims_floor == 13
    assert s.claims_actual == 0    # no claims, no verified record
    assert s.claims_expected is None   # needs a corpus, has none
    # never subtracted from score/applicable, a real gap (floor=13,
    # actual=0) must not by itself change conforms/score the way a
    # missing Intent: (a real scored criterion) would.
    assert s.conforms is False   # Claims: is genuinely absent; that
                                 # alone accounts for the gap from full
                                 # marks, not claims_floor


def test_docstring_sync_checklist_renders_the_claim_triplet_unscored(tmp_path):
    mod = _import_module(tmp_path, "sync_checklist_mod", (
        "def half(x: float) -> float:\n"
        "    \"\"\"Halves x.\n"
        "\n"
        "    Intent:\n"
        "        Returns half of x.\n"
        "\n"
        "    Notes:\n"
        "        Only tested for finite inputs.\n"
        "\n"
        "    Claims:\n"
        "        nonneg: f(x) >= 0\n"
        "    \"\"\"\n"
        "    return x / 2\n"
    ))
    s = docstring_sync(mod.half, root=str(tmp_path))
    lines = docstring_sync_checklist(s)
    assert any(line.startswith("✓ Intent:") for line in lines)
    assert any(line.startswith("· Notes:") for line in lines)
    triplet_line = next(line for line in lines if line.startswith("· claims {"))
    assert triplet_line.startswith("·")   # informational marker, not ✓/✗
    assert "not scored" in triplet_line
    assert "| -}" in triplet_line         # expected is unknown, not zero
