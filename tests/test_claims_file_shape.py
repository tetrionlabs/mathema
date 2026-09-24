# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claims file whose shape is wrong is an authoring error: exit 2
with one clean line naming the file and the key, never a traceback and
never silently ignored. The shapes covered are the ones a hand-written
file gets wrong: a statement that is not text or is missing, `claims`
that is not a list, an entry that is not a mapping, a bare string where
a claim mapping belongs, a domain or tolerance that does not read, one
name used twice under one key, and a misspelled field."""
import pytest

from mathema.cli import main

_SOURCE = "def sq(x):\n    return x * x\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "shapefix.py").write_text(_SOURCE)
    monkeypatch.syspath_prepend(str(tmp_path))
    return tmp_path


def _claim(body):
    return ("shapefix.sq:\n  claims:\n    - name: a\n"
            + "".join(f"      {line}\n" for line in body))


_OK = 'statement: "for x in [0, 1], sq(x) >= 0"'

_BAD = [
    ("statement-not-text", _claim(["statement: 42"]), "statement"),
    ("statement-missing", _claim(["route: probe"]), "statement"),
    ("claims-not-a-list", "shapefix.sq:\n  claims: 5\n", "claims"),
    ("bare-string-claim",
     'shapefix.sq:\n  claims:\n    - "for x in [0, 1], sq(x) >= 0"\n',
     "mapping"),
    ("domain-word", _claim([_OK, "domain: {x: banana}"]), "domain"),
    ("domain-half", _claim([_OK, "domain: {x: {lo: 0}}"]), "domain"),
    ("domain-inverted", _claim([_OK, "domain: {x: [1, 0]}"]), "domain"),
    ("domain-nan", _claim([_OK, "domain: {x: [.nan, 1]}"]), "domain"),
    ("domain-not-a-mapping", _claim([_OK, "domain: [0, 1]"]), "domain"),
    ("tolerance-word", _claim([_OK, "tolerance: abc"]), "tolerance"),
    ("tolerance-negative", _claim([_OK, "tolerance: -1"]), "tolerance"),
    ("top-level-list", "- shapefix.sq\n", "mapping"),
    ("entry-not-a-mapping", "shapefix.sq: 5\n", "mapping"),
    ("duplicate-name",
     "shapefix.sq:\n  claims:\n"
     '    - name: a\n      statement: "for x in [0, 1], sq(x) >= 0"\n'
     '    - name: a\n      statement: "for x in [0, 1], sq(x) >= -1"\n',
     "twice"),
    ("misspelled-field", _claim([_OK, "tolerence: 0.1"]), "tolerance"),
    ("misspelled-claims",
     'shapefix.sq:\n  cliams:\n    - name: a\n      ' + _OK + "\n",
     "claims"),
]


@pytest.mark.parametrize("label,text,word", _BAD, ids=[b[0] for b in _BAD])
@pytest.mark.parametrize("verb", ["verify", "check"])
def test_a_malformed_claims_file_exits_2_naming_file_and_key(
        project, capsys, label, text, word, verb):
    (project / "shapefix.claims.yaml").write_text(text)
    argv = (["verify", "--root", str(project)] if verb == "verify"
            else ["check", "shapefix.sq", "--root", str(project)])
    rc = main(argv)
    err = capsys.readouterr().err
    assert rc == 2, err
    lines = err.strip().splitlines()
    assert len(lines) == 1, err
    assert lines[0].startswith("mathema: ")
    assert "shapefix.claims.yaml" in lines[0]
    if label != "top-level-list":
        assert "shapefix.sq" in lines[0]
    assert word in lines[0], lines[0]


def test_a_well_formed_file_still_verifies(project, capsys):
    (project / "shapefix.claims.yaml").write_text(
        _claim([_OK, "route: probe", "tolerance: 1e-6",
                "domain: {x: [0, 1]}"]))
    assert main(["verify", "--root", str(project)]) == 0, \
        capsys.readouterr()


def _refused(project, capsys, text):
    (project / "shapefix.claims.yaml").write_text(text)
    rc = main(["verify", "--root", str(project)])
    err = capsys.readouterr().err
    assert rc == 2, err
    lines = err.strip().splitlines()
    assert len(lines) == 1, err
    assert "shapefix.claims.yaml" in lines[0] and "shapefix.sq" in lines[0]
    return lines[0]


def test_an_unknown_claim_field_is_refused_naming_the_annotation_fields(
        project, capsys):
    # a field mathema does not read would be silently dropped by the
    # next rewrite; the refusal points at the fields that persist
    line = _refused(project, capsys, _claim([_OK, "ticket: MATH-12"]))
    assert "claim 'a'" in line and "'ticket'" in line
    for field in ("`note:`", "`meta:`", "`references:`", "concepts"):
        assert field in line, line
    assert "did you mean" not in line


def test_an_unknown_entry_field_is_refused_naming_the_annotation_fields(
        project, capsys):
    line = _refused(project, capsys,
                    "shapefix.sq:\n  owner: turing\n  claims:\n"
                    "    - name: a\n      " + _OK + "\n")
    assert "'owner'" in line
    for field in ("`meta:`", "`references:`", "`note:`", "concepts"):
        assert field in line, line


def test_the_annotation_fields_are_accepted(project, capsys):
    (project / "shapefix.claims.yaml").write_text(
        "shapefix.sq:\n"
        "  meta: {concepts: [square], owner: turing}\n"
        "  references: [{title: Squares, url: 'https://example.org'}]\n"
        "  claims:\n"
        "    - name: a\n      " + _OK + "\n"
        "      note: from ticket MATH-12\n"
        "      meta: {ticket: MATH-12}\n")
    assert main(["verify", "--root", str(project)]) == 0, \
        capsys.readouterr()


def test_the_same_name_in_two_files_still_merges(project, capsys):
    (project / "shapefix.claims.yaml").write_text(_claim([_OK]))
    claims = project / "claims"
    claims.mkdir()
    (claims / "more.yaml").write_text(
        _claim(['statement: "for x in [0, 2], sq(x) >= 0"']))
    assert main(["verify", "--root", str(project)]) == 0, \
        capsys.readouterr()


def test_the_materialized_view_says_edits_to_it_are_not_read(project):
    # `.mathema/declared/` is regenerated and never read back, so its
    # header points at the surfaces that are
    from mathema.sync import materialize_entry
    (project / "shapefix.claims.yaml").write_text(_claim([_OK]))
    import shapefix
    materialize_entry(shapefix.sq, "shapefix.sq", root=str(project))
    text = (project / ".mathema" / "declared"
            / "shapefix.sq.yaml").read_text()
    header = "".join(ln for ln in text.splitlines(True)
                     if ln.startswith("#"))
    assert "are read" not in header
    assert "overwritten" in header
