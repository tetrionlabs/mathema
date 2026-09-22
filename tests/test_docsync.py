# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The docstring sync loop: `# note:` comment harvesting (all notes,
any capitalisation, structured provenance, deduped), docstring
generation from the declared/verified layers (creation only), the
source-file write-back, and the function/module/README intent
hierarchy (reported, never inherited)."""
import importlib.util
import subprocess
import sys
import textwrap

import pytest

import mathema
from mathema.analysis import analyze_source
from mathema.docstring import (generate_docstring, intent_context,
                               parse_mathema_docstring, write_docstring)


def _load_module(tmp_path, name, source):
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(source))
    spec = importlib.util.spec_from_file_location(name, path)
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


# --- comment-note harvesting ----------------------------------------------

def test_every_note_comment_is_harvested_any_capitalisation(tmp_path):
    mod = _load_module(tmp_path, "notes_fixture", '''\
    def scale(x: float) -> float:
        # NOTE: clamps nothing; caller owns range checks.
        y = 2.0 * x
        # note: precision loss above 1e15.
        # (float64 mantissa limit.)
        return y
    ''')
    facts = analyze_source(mod.scale)
    assert [n["text"] for n in facts.comment_notes] == [
        "clamps nothing; caller owns range checks.",
        "precision loss above 1e15. (float64 mantissa limit.)"]
    assert facts.doc_notes == ("clamps nothing; caller owns range checks. "
                               "precision loss above 1e15. (float64 mantissa limit.)")
    # provenance is file line numbers, in order
    lines = [n["line"] for n in facts.comment_notes]
    assert lines == sorted(lines) and all(line > 1 for line in lines)


def test_comment_note_duplicating_the_docstring_notes_is_deduped(tmp_path):
    mod = _load_module(tmp_path, "dedupe_fixture", '''\
    def half(x: float) -> float:
        """Halves x.

        Notes:
            Only tested for finite inputs.
        """
        # note: Only tested for finite inputs.
        return x / 2
    ''')
    facts = analyze_source(mod.half)
    assert facts.doc_notes == "Only tested for finite inputs."
    assert len(facts.comment_notes) == 1   # still structured, just not re-appended


# --- generation (claims + intent -> docstring, creation only) --------------

def _write_declared(tmp_path, key, intent=None):
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir(exist_ok=True)
    intent_line = f"  intent: {intent}\n" if intent else ""
    (claims_dir / f"{key}.claims.yaml").write_text(
        f"{key}:\n{intent_line}"
        "  claims:\n"
        "    - name: nonneg\n"
        '      statement: "f(x) >= 0"\n'
        "      route: derive\n")


def test_generate_docstring_from_declared_intent_and_claims(tmp_path):
    mod = _load_module(tmp_path, "gen_fixture", '''\
    def square(x: float) -> float:
        return x * x
    ''')
    key = "gen_fixture.square"
    _write_declared(tmp_path, key, intent="Squares its input.")
    text = generate_docstring(mod.square, key=key, root=str(tmp_path))
    assert text.startswith("Squares its input.")
    assert "Intent:\n    Squares its input." in text
    assert "nonneg [derive]: f(x) >= 0" in text


def test_generate_docstring_never_replaces_an_existing_one(tmp_path):
    mod = _load_module(tmp_path, "gen_present_fixture", '''\
    def cube(x: float) -> float:
        """Cubes x."""
        return x ** 3
    ''')
    assert generate_docstring(mod.cube, root=str(tmp_path)) is None


def test_generate_docstring_with_nothing_to_write_from(tmp_path):
    mod = _load_module(tmp_path, "gen_empty_fixture", '''\
    def opaque(x: float) -> float:
        return x
    ''')
    assert generate_docstring(mod.opaque, key="gen_empty_fixture.opaque",
                              root=str(tmp_path)) is None


def test_generated_docstring_round_trips_through_the_parser(tmp_path):
    mod = _load_module(tmp_path, "roundtrip_fixture", '''\
    def double(x: float) -> float:
        return 2 * x
    ''')
    key = "roundtrip_fixture.double"
    _write_declared(tmp_path, key, intent="Doubles its input.")
    text = generate_docstring(mod.double, key=key, root=str(tmp_path))
    path = write_docstring(mod.double, text)
    assert path.endswith("roundtrip_fixture.py")

    # re-import the modified file: the docstring is real source now
    fresh = _load_module(tmp_path, "roundtrip_fixture", open(path).read())
    parsed = parse_mathema_docstring(fresh.double)
    assert parsed.intent == "Doubles its input."
    assert [c["name"] for c in parsed.claims] == ["nonneg"]

    # and the write half only ever creates
    import pytest
    with pytest.raises(ValueError):
        write_docstring(fresh.double, "another")


# --- the intent hierarchy ---------------------------------------------------

def test_intent_context_reports_all_three_levels_without_inheriting(tmp_path):
    (tmp_path / "README.md").write_text(
        "# demo\n\n## Intent\n\nA toy package for exercising the intent "
        "hierarchy.\nSecond line of the same paragraph.\n\nMore prose.\n")
    mod = _load_module(tmp_path, "hierarchy_fixture", '''\
    """Utilities for the hierarchy test.

    Intent:
        Module-level intent statement.
    """

    def documented(x: float) -> float:
        """Documented function.

        Intent:
            Function-level intent statement.
        """
        return x

    def bare(x: float) -> float:
        return x
    ''')
    ctx = intent_context(mod.documented, root=str(tmp_path))
    assert ctx["function"] == {"text": "Function-level intent statement.",
                               "evidence": "explicit"}
    assert ctx["module"] == {"text": "Module-level intent statement.",
                             "evidence": "explicit"}
    assert ctx["readme"]["text"].startswith("A toy package for exercising")
    assert ctx["readme"]["evidence"] == "explicit"

    bare_ctx = intent_context(mod.bare, root=str(tmp_path))
    # context is reported, never inherited: the bare function's own
    # intent stays a gap even though module and README both state one.
    assert bare_ctx["function"] is None
    assert bare_ctx["module"]["text"] == "Module-level intent statement."


def test_docstring_sync_carries_the_intent_context(tmp_path):
    from mathema.docstring import docstring_sync, docstring_sync_checklist
    mod = _load_module(tmp_path, "sync_ctx_fixture", '''\
    """Intent:
        Module intent here.
    """

    def plain(x: float) -> float:
        return x
    ''')
    sync = docstring_sync(mod.plain, root=str(tmp_path))
    assert sync.intent_context["module"] == {"text": "Module intent here.",
                                             "evidence": "explicit"}
    joined = "\n".join(docstring_sync_checklist(sync))
    assert "intent context" in joined and "(not scored)" in joined


# --- the CLI face -----------------------------------------------------------

def test_cli_docsync_reports_and_proposes(tmp_path):
    (tmp_path / "funcs.py").write_text(
        'def documented(x: float) -> float:\n'
        '    """Documented.\n\n    Intent:\n        States itself.\n    """\n'
        '    return x\n\n'
        'def bare(x: float) -> float:\n'
        '    return x\n')
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    (claims_dir / "funcs.bare.claims.yaml").write_text(
        "funcs.bare:\n"
        "  intent: Passes x through unchanged.\n"
        "  claims:\n"
        "    - name: identity\n"
        '      statement: "f(x) == x"\n'
        "      route: derive\n")
    script = ("import sys; from mathema.cli import main; "
             "sys.exit(main(['docsync', 'funcs.py', '--report']))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "documented: docstring present, docsync" in r.stdout
    assert "bare: no docstring, proposed:" in r.stdout
    assert "Passes x through unchanged." in r.stdout
    assert "identity [derive]: f(x) == x" in r.stdout


def test_intent_evidence_rungs_documented_vs_declared(tmp_path):
    mod = _load_module(tmp_path, "rungs_fixture", '''\
    def summary_only(x: float) -> float:
        """Scales x by two."""
        return 2 * x

    def with_block(x: float) -> float:
        """Scales x by three.

        Intent:
            Triples its input.
        """
        return 3 * x
    ''')
    assert intent_context(mod.summary_only)["function"] == {
        "text": "Scales x by two.", "evidence": "implicit"}
    assert intent_context(mod.with_block)["function"] == {
        "text": "Triples its input.", "evidence": "explicit"}

    # the verified record carries the provenance as its own function-
    # level fact (intent is a section of the record, never a claim),
    # only the deliberate "documented" case is tagged; summary-only
    # intent sits at the default lowest rung, read from the tag's
    # absence, so every merely-docstringed function stays meta-free.
    # the RECORD's rung ladder is declared -> documented, and
    # documented is a human acceptance, an explicit Intent: block no
    # longer auto-earns it; every stated intent starts declared
    from mathema.spec import to_spec
    documented = to_spec(mathema.check(mod.with_block, claims=[]))
    assert documented["meta"]["mathema.intent_provenance"] == "declared"
    summary = to_spec(mathema.check(mod.summary_only, claims=[]))
    assert summary["meta"]["mathema.intent_provenance"] == "declared"


# --- the global index record -------------------------------------------------

def test_index_covers_intent_modules_and_function_lines(tmp_path):
    (tmp_path / "README.md").write_text(
        "# demo\n\n## Intent\n\nA toy package for the index test.\n")
    pkg = tmp_path / "idxpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "funcs.py").write_text(
        '"""Utility functions.\n\nIntent:\n    Index-test module intent.\n"""\n\n\n'
        "def one(x: float) -> float:\n"
        "    return x\n\n\n"
        "def two(x: float) -> float:\n"
        "    return 2 * x\n")
    script = (
        "import sys, yaml; sys.path.insert(0, '.')\n"
        "import idxpkg.funcs, mathema\n"
        "mathema.write_spec(idxpkg.funcs.one, root='.', claims=[])\n"
        "from mathema.audit import build_index, write_index\n"
        "idx = build_index(['idxpkg'], root='.')\n"
        "path = write_index(['idxpkg'], root='.')\n"
        "print(yaml.safe_load(open(path))['index'] == idx or 'roundtrip-note')\n"
        "print(idx['intent'])\n"
        "mod = idx['modules'][0]\n"
        "print(mod['name'], '|', mod['file'], '|', mod['intent'])\n"
        "for f in mod['functions']:\n"
        "    print(f['key'], f['line'], f['verified'])\n")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "A toy package for the index test." in out
    assert "'evidence': 'explicit'" in out
    assert "idxpkg.funcs |" in out and "funcs.py" in out
    assert "Index-test module intent." in out
    assert "idxpkg.funcs.one 8 True" in out
    assert "idxpkg.funcs.two 12 False" in out


def test_cli_index_writes_the_record(tmp_path):
    pkg = tmp_path / "clipkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "funcs.py").write_text(
        "def solo(x: float) -> float:\n    return x\n")
    script = ("import sys; from mathema.cli import main; "
             "sys.exit(main(['audit', 'clipkg', '--index']))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 module(s), 1 function(s), 0 verified" in r.stdout
    assert (tmp_path / ".mathema" / "index.yaml").exists()
    body = (tmp_path / ".mathema" / "index.yaml").read_text()
    assert "clipkg.funcs.solo" in body and "line:" in body
    # the grep-free contract: root-relative file, sed-address span,
    # and the record path (null here, nothing verified yet), all
    # denormalized onto every function entry
    assert 'file: "clipkg/funcs.py"' in body
    assert 'span: "1:2p"' in body
    assert "spec:" in body
