# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A runtime's missing values are stated in a claims file as definition
rows under a key's `defines:`, `missing := {null, nan}`: taken at face
value (verdict `trusted`, route `axiom`), never adjudicated, and applied
in layers (the adapter's built-ins, the bundled compendium, a project's
compendium, a project's claims file). A plain set replaces what the key
had, the class word inside the set extends it, and a spelling the key's
runtime type cannot realise fails at load. `:=` is never a claim.

A runtime that is not Python is the same construct: a registered
adapter whose definition rows spell absence `Option::None` and the hole
`NaN` renders its parameter `|None|missing`, states the resolution, and
names its own spelling in a witness."""
import math
import textwrap

import pytest

import mathema
from mathema import compendium
from mathema import runtime_types as rt
from mathema.conjecture import InvalidConjecture, claim
from mathema.grammar import InvalidDefinition, parse_definition
from mathema.runtime_types import Detection, NotMine
from mathema.spec import ClaimsFileError


def write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(textwrap.dedent(text))
    return path


def test_a_definition_row_reads_its_word_and_members():
    assert parse_definition("missing := {null, nan}") == ("missing", ("null", "nan"), False)
    assert parse_definition("missing := {missing, NaT}") == ("missing", ("NaT",), True)
    assert parse_definition("None := {Option::None}") == ("None", ("Option::None",), False)
    assert parse_definition("absent := {Option::None}") == ("None", ("Option::None",), False)
    assert parse_definition("absent := {absent, undefined}") == ("None", ("undefined",), True)
    with pytest.raises(InvalidDefinition):
        parse_definition("x := {nan}")
    with pytest.raises(InvalidDefinition):
        parse_definition("missing = {nan}")


def test_the_bundled_definitions_apply():
    compendium.ensure_bundled()
    assert rt.resolve_missing("pandas.Series") == ("nan", "null", "NA", "NaT")
    assert rt.resolve_missing("polars.Series") == ("null", "nan")
    assert rt.resolve_missing("numpy.ndarray") == ("nan",)


def test_a_project_row_loads_as_an_axiom_and_composes(tmp_path):
    write(tmp_path, "project.claims.yaml", """
        polars.Series:
          defines:
            - "missing := {null}"
        pandas.Series:
          defines:
            - "missing := {missing, NA}"
    """)
    compendium.install(str(tmp_path))
    try:
        assert rt.resolve_missing("polars.Series") == ("null",)
        assert rt.resolve_missing("pandas.Series") == ("nan", "null", "NA", "NaT")
        records = {r["key"]: r for r in compendium.definition_records(
            rt.definitions(("claims",)))}
        assert records["polars.Series"] == {
            "key": "polars.Series", "definition": "missing := {null}",
            "verdict": "trusted", "route": "axiom",
            "source": "claims file project.claims.yaml", "members": ["null"]}
    finally:
        compendium.uninstall()
        compendium.ensure_bundled()


def test_a_spelling_the_runtime_cannot_realise_fails_at_load(tmp_path):
    path = write(tmp_path, "project.claims.yaml", """
        numpy.ndarray:
          defines:
            - "missing := {missing, NA}"
    """)
    from mathema.spec import read_claims_file
    with pytest.raises(ClaimsFileError, match="numpy.ndarray has no spelling 'NA'"):
        read_claims_file(str(path), "project.claims.yaml")


def test_a_definition_is_refused_in_a_statement():
    with pytest.raises(InvalidConjecture, match="defines:"):
        claim("missing := {null, nan}")


def test_a_definition_is_refused_in_a_binding():
    with pytest.raises(InvalidConjecture, match=":="):
        claim("for x in {nan} := missing, f(x) >= 0")


def test_verify_lists_definitions_outside_the_verdict_counts(tmp_path, capsys,
                                                             monkeypatch):
    write(tmp_path, "defmod.py", """
        # SPDX-License-Identifier: BUSL-1.1
        # Copyright 2026 Tetrion Ltd
        def double(x: float) -> float:
            return 2 * x
    """)
    write(tmp_path, "project.claims.yaml", """
        polars.Series:
          defines:
            - "missing := {null, nan}"
        defmod.double:
          claims:
            - name: grows
              statement: "for x in [0, 1], f(x) >= x"
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    from mathema.cli import main
    try:
        main(["verify", "--root", str(tmp_path)])
    except SystemExit:
        pass
    finally:
        compendium.uninstall()
        compendium.ensure_bundled()
    out = capsys.readouterr().out
    assert "definitions (trusted):" in out
    assert "polars.Series: missing := {null, nan}" in out
    assert "1 fresh" not in out and "polars.Series: " not in out.split(
        "definitions (trusted):")[0]


# --- a runtime that is not Python -----------------------------------------

class OptionNone:
    """The toy runtime's absent value."""

    def __repr__(self) -> str:
        return "Option::None"


class ToyF64:
    """A toy foreign runtime: its values are plain Python floats, it
    spells a hole `NaN` and the absence of a value `Option::None`."""
    name = "toy.f64"
    kinds = frozenset({"scalar"})
    requires: tuple = ()
    SPELLINGS = {"NaN": (lambda: math.nan, lambda v: isinstance(v, float) and v != v),
                 "Option::None": (OptionNone, lambda v: isinstance(v, OptionNone))}
    MISSING_MEMBERS: tuple = ()
    ABSENCE: tuple = ()

    def detect(self, annotation):
        if annotation == "toy.f64":
            return Detection(self.name, "scalar", "annotation text: toy.f64")
        return None

    def realise(self, abstract, options):
        return abstract

    def observe(self, obj):
        return NotMine


class _EntryPoint:
    name = "toy"
    value = "tests:ToyF64"

    def load(self):
        return ToyF64


@pytest.fixture
def toy_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(rt, "entry_points", lambda **_: [_EntryPoint()])
    rt._discovered.cache_clear()
    write(tmp_path, "toy.claims.yaml", """
        toy.f64:
          defines:
            - "None := {Option::None}"
            - "missing := {NaN}"
    """)
    compendium.install(str(tmp_path))
    yield
    compendium.uninstall()
    compendium.ensure_bundled()
    rt._discovered.cache_clear()


def toy_sqrt(x) -> float:
    if isinstance(x, OptionNone):
        raise ValueError("no value")
    return math.sqrt(x)


# the parameter's annotation names the toy runtime's type by its text,
# as a foreign runtime's own type is named
toy_sqrt.__annotations__["x"] = "toy.f64"


def test_a_foreign_runtime_renders_both_kinds_and_states_its_members(toy_runtime):
    report = mathema.check(toy_sqrt, claims=[mathema.claim("for x in [0, 1], f(x) >= 0",
                                                           name="c")])
    probe = next(p for p in report.probes if p.name == "c")
    assert probe.statement == "for x in [0.0, 1.0] : float|None|missing, f(x) >= 0"
    assert probe.meta["mathema.missing"]["admitted"]["x"]["holes"] == ["NaN"]


def test_a_foreign_runtime_records_its_own_spelling(toy_runtime):
    report = mathema.check(toy_sqrt, claims=[mathema.claim("for x in {0.25, None}, f(x) >= 0",
                                                           name="c")])
    probe = next(p for p in report.probes if p.name == "c")
    assert probe.verdict == "proven", (probe.verdict, probe.note)
    assert probe.meta["mathema.missing"]["executed"] == {
        "x": {"Option::None": "raised ValueError"}}


def test_one_value_may_be_both_absence_and_a_hole_member(tmp_path):
    path = write(tmp_path, "project.claims.yaml", """
        polars.Series:
          defines:
            - "absent := {None}"
            - "missing := {null, nan}"
    """)
    from mathema.spec import read_claims_file
    assert read_claims_file(str(path), "project.claims.yaml")
    from mathema._missing_policy import no_value_slots
    assert [(s.kind, s.member) for s in no_value_slots(None).slots] == [("absent", "None")]
    assert [(s.kind, s.member) for s in no_value_slots([1.0, None]).slots] == \
        [("missing", "null")]


class ClashVec:
    """A toy runtime whose two hole spellings are one value."""
    name = "toy.clash"
    kinds = frozenset({"vec"})
    requires: tuple = ()
    SPELLINGS = {"null": (lambda: None, lambda v: v is None),
                 "none": (lambda: None, lambda v: v is None)}
    MISSING_MEMBERS: tuple = ()
    ABSENCE: tuple = ()

    def detect(self, annotation):
        return None

    def realise(self, abstract, options):
        return abstract

    def observe(self, obj):
        return NotMine


class _ClashEntryPoint:
    name = "clash"
    value = "tests:ClashVec"

    def load(self):
        return ClashVec


def test_one_value_as_two_hole_members_is_refused_at_load(tmp_path, monkeypatch):
    from mathema.spec import read_claims_file
    monkeypatch.setattr(rt, "entry_points", lambda **_: [_ClashEntryPoint()])
    rt._discovered.cache_clear()
    clash = write(tmp_path, "clash.claims.yaml", """
        toy.clash:
          defines:
            - "missing := {null, none}"
    """)
    try:
        with pytest.raises(ClaimsFileError, match="names one value, None, as two hole "
                                                  "members, null and none"):
            read_claims_file(str(clash), "clash.claims.yaml")
    finally:
        monkeypatch.undo()
        rt._discovered.cache_clear()
