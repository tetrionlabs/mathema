# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Concepts (tags) and references (links): declared markers in
docstrings and declared files, mechanism-derived concepts from
adjudication evidence, the spec-conformant meta shapes (flat
meta.concepts union + un-flattened mathema.concept_sources), role-
labeled reference links (reference/analysis/evidence/policy), and the
audit/index/describe surfaces."""
import os
import subprocess
import sys
import textwrap

from mathema.concepts import (Concept, concepts_for, flat_union,
                              mechanism_concepts, normalize_concept,
                              parse_concepts)


def _mod(tmp_path, body, name):
    import importlib
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body))
    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module(name)
        importlib.reload(mod)
    finally:
        sys.path.remove(str(tmp_path))
    return mod


def test_parse_and_normalize():
    assert normalize_concept("  Great Circle ") == "great-circle"
    assert parse_concepts("metric-space, Great Circle\n- haversine") == [
        "metric-space", "great-circle", "haversine"]


def test_docstring_markers_both_spellings(tmp_path):
    mod = _mod(tmp_path, '''
        def a(x: float) -> float:
            """S.

            Concepts:
                metric-space, Great Circle
            """
            return x

        def b(x: float) -> float:
            """S.

            Tags: scaling, linear ops
            """
            return x
        ''', "conc_a")
    from mathema import analyze
    assert analyze(mod.a).doc_concepts == ["metric-space", "great-circle"]
    assert analyze(mod.b).doc_concepts == ["scaling", "linear-ops"]


def test_reference_sections_carry_roles(tmp_path):
    mod = _mod(tmp_path, '''
        def f(x: float) -> float:
            """Vol assumption.

            Analysis:
                - Assumption notebook: https://nb.example.com/a.ipynb

            Policy:
                - Model risk policy: https://policy.example.com/mr-101
            """
            return x
        ''', "conc_b")
    from mathema import analyze
    refs = analyze(mod.f).doc_refs
    assert ("Assumption notebook", "https://nb.example.com/a.ipynb",
            "analysis") in refs
    assert ("Model risk policy", "https://policy.example.com/mr-101",
            "policy") in refs


def test_summary_stops_at_the_new_sections(tmp_path):
    mod = _mod(tmp_path, '''
        def f(x: float) -> float:
            """Doubles.

            Concepts:
                scaling
            """
            return 2 * x
        ''', "conc_c")
    from mathema import analyze
    assert analyze(mod.f).doc_intent == "Doubles."


def test_mechanism_harvest(tmp_path):
    mod = _mod(tmp_path, '''
        def sum_positives(values: list) -> float:
            total = 0.0
            for v in values:
                if v > 0:
                    total += v
            return total
        ''', "conc_d")
    from mathema import analyze, check
    rec = check(mod.sum_positives, claims=["f(values) >= 0"])
    names = mechanism_concepts(analyze(mod.sum_positives), rec.probes)
    assert "summation" in names and "folded-sum" in names
    # provenance split intact, union flat
    sources = rec.meta["mathema.concept_sources"]
    assert "mechanism" in sources
    assert rec.meta["concepts"] == flat_union(sources)


def test_statement_atoms_map_to_concepts():
    class P:
        meta: dict = {}
        statement = "lim(f(n)/(4**n), n, oo) == 1"
        sketch = ""
        verdict = "unknown"
        name = "x"
    assert "limits" in mechanism_concepts(None, [P()])


def test_record_reasoning_renders_instantiates(tmp_path):
    mod = _mod(tmp_path, '''
        def g(x: float) -> float:
            """S.

            Concepts:
                scaling
            """
            return 2 * x
        ''', "conc_e")
    from mathema import check
    from mathema.spec import to_spec
    spec = to_spec(check(mod.g, claims=[]))
    situating = [c for c in spec["reasoning"] if c["step"] == "situating"]
    assert situating and "scaling" in situating[0]["claim"]
    assert spec["concepts"] == ["scaling"]


def test_declared_file_and_per_claim_round_trip(tmp_path):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pkg = tmp_path / "cpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        'def double(x: float) -> float:\n'
        '    """Doubles.\n\n    Concepts:\n        scaling\n    """\n'
        '    return 2.0 * x\n')
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "c.claims.yaml").write_text(textwrap.dedent("""
        cpkg.mod.double:
          meta:
            concepts: [linear-maps]
          references:
            - title: Assumption notebook
              url: https://nb.example.com/s.ipynb
              via: analysis
          claims:
            - name: doubles
              statement: 'for x in [0,5], f(x) == 2*x'
              route: derive
              meta:
                concepts: [proportionality]
        """))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([repo, str(tmp_path)]))
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}]))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    body = (tmp_path / ".mathema" / "verified"
            / "cpkg.mod.double.yaml").read_text()
    assert '"linear-maps"' in body and '"scaling"' in body
    assert '"proportionality"' in body          # per-claim pass-through
    assert "analysis:" in body                  # references nested by role
    assert '"Assumption notebook"' in body
    assert "mathema.concept_sources" in body    # provenance kept


def test_concepts_for_never_flattens():
    class F:
        doc_concepts = ["a"]
        doc_hints = ["Monotonicity"]
        loops = []
        recursion = False
    sources = concepts_for(F(), [])
    assert sources == {"declared": ["a"], "mechanism": [],
                       "keyword": ["monotonicity"]}
    assert flat_union(sources) == ["a", "monotonicity"]
    assert Concept("a", "declared").name == "a"


def test_docs_score_ignores_the_concepts_section(tmp_path):
    mod = _mod(tmp_path, '''
        def bare(x: float) -> float:
            """Does a thing with x."""
            return x

        def tagged(x: float) -> float:
            """Does a thing with x.

            Concepts:
                scaling
            """
            return x
        ''', "conc_f")
    from mathema.inventory import docstring_quality
    a, b = docstring_quality(mod.bare), docstring_quality(mod.tagged)
    assert (a["score"], a["applicable"]) == (b["score"], b["applicable"])


def test_docstring_claims_reach_the_verified_layer_and_concept_edits_heal(tmp_path):
    # The freshness question, pinned end to end: form_hash ignores
    # docstrings BY DESIGN, but the claims fingerprint covers the
    # merged set, so a new docstring claim re-adjudicates (labeled
    # "claims changed", not "form changed"); and a concepts-only edit,
    # which changes neither, HEALS the fresh record in place.
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pkg = tmp_path / "hpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")

    def write(concepts, extra_claim=""):
        import shutil
        shutil.rmtree(pkg / "__pycache__", ignore_errors=True)
        (pkg / "mod.py").write_text(
            'def double(x: float) -> float:\n'
            f'    """Doubles.\n\n    Concepts:\n        {concepts}\n\n'
            f'    Claims:\n        base: for x in [0,5], f(x) >= 0\n'
            f'{extra_claim}    """\n'
            '    return 2.0 * x\n')

    env = dict(os.environ, PYTHONPATH=os.pathsep.join([repo, str(tmp_path)]))

    def run():
        return subprocess.run(
            [sys.executable, "-c",
             "import sys; from mathema.cli import main; "
             f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}]))"],
            cwd=str(tmp_path), capture_output=True, text=True, env=env)

    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        "hpkg.mod.double:\n  claims: []\n")
    write("scaling")
    r = run()
    assert "no baseline record" in r.stdout

    # a new docstring claim: body unchanged, fingerprint moved
    write("scaling", "        bounded: for x in [0,5], f(x) <= 10\n")
    r = run()
    assert "claims changed" in r.stdout, r.stdout
    body = (tmp_path / ".mathema" / "verified" / "hpkg.mod.double.yaml").read_text()
    assert "bounded" in body

    # a concepts-only edit: fresh, healed in place
    write("scaling, dilation", "        bounded: for x in [0,5], f(x) <= 10\n")
    r = run()
    assert "fresh" in r.stdout.splitlines()[0]
    body = (tmp_path / ".mathema" / "verified" / "hpkg.mod.double.yaml").read_text()
    assert "dilation" in body
