# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The MCP tool functions: SDK-free wrappers over the library surface,
exercised directly against the relpkg fixture (no `mcp` install
needed); the server-construction smoke runs only where the optional
extra is present. The bounded-surface rules are pinned: no accept
tool, no verdict parameter anywhere."""
import inspect
import os

import pytest

from mathema.interfaces.mcp import tools

DATA = os.path.join(os.path.dirname(__file__), "data")


def test_resolve_target_tool():
    out = tools.resolve_target("relpkg.geometry", root=DATA)
    keys = {f["key"] for f in out["functions"]}
    assert "relpkg.geometry.doubled" in keys
    assert out["kind"] == "module"


def test_adjudicate_target_tool_adjudicates_a_claim():
    out = tools.adjudicate_target("relpkg.geometry:doubled",
                               claims=["for x in [-10, 10], f(x) == 2*x"],
                               root=DATA)
    assert out["key"] == "relpkg.geometry.doubled"
    assert out["passed"], out["problems"]
    law = next(c for c in out["claims"] if "2*x" in c["statement"])
    assert law["verdict"] in ("holds", "proven")


def test_verify_project_tool_on_an_empty_root(tmp_path):
    out = tools.verify_project(root=str(tmp_path))
    assert out["nothing_declared"] is True


def test_audit_targets_tool_carries_blocked_codes(tmp_path):
    pkg = tmp_path / "audpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "def branchy(x: float) -> float:\n"
        "    if x < 0:\n"
        "        return -x\n"
        "    return x\n")
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        out = tools.audit_targets(["audpkg"], root=str(tmp_path),
                                  cols=["key", "span", "blocker",
                                        "blocker_params", "constructs",
                                        "derivable"])
    finally:
        sys.path.remove(str(tmp_path))
    # compact shape: cols echoed, key prefix factored, raw values
    assert out["cols"] == ["key", "span", "blocker", "blocker_params",
                           "constructs", "derivable"]
    row = next(dict(zip(out["cols"], r)) for r in out["rows"]
               if (out["prefix"] + r[0]).endswith("branchy"))
    assert row["blocker"] == "branch:needs-domain"
    assert row["blocker_params"] == ["x"]
    assert row["constructs"] and row["constructs"][0]["code"].startswith("branch:")
    assert row["span"].endswith("p")


def test_reason_code_lookup_tool():
    one = tools.reason_code("loop:non-affine-update")
    entry = one["codes"]["loop:non-affine-update"]
    assert entry["derive_unlock"] == "limitation"
    assert entry["id"] == "2.18"
    # numeric ids and whole groups filter selectively
    by_id = tools.reason_code("2.18")
    assert "loop:non-affine-update" in by_id["codes"]
    group = tools.reason_code("branch")
    assert all(k.startswith("branch:") for k in group["codes"])
    several = tools.reason_code("1.1, loop:no-loop")
    assert set(several["codes"]) == {"stateful", "loop:no-loop"}
    # no argument: the compact index only, never the whole table
    table = tools.reason_code()
    assert table["cols"] == ["id", "code", "derive_unlock"]
    assert ["2.18", "loop:non-affine-update", "limitation"] \
        in table["rows"]
    assert "meaning" not in str(table["cols"])
    missing = tools.reason_code("no-such-code")
    assert "error" in missing


def test_claim_grammar_tool():
    out = tools.claim_grammar()
    assert isinstance(out["lexicon"], dict) and out["lexicon"]


def test_no_accept_tool_and_no_verdict_parameter():
    # the wall, and it must cover EVERYTHING the server registers,
    # not just TOOLS. A resource or prompt added outside that tuple
    # would otherwise escape the one invariant that matters most here.
    from mathema.interfaces.mcp import resources

    registered = (list(tools.TOOLS)
                  + [fn for fn, _mime in resources.RESOURCES.values()]
                  + list(resources.PROMPTS.values()))
    names = {fn.__name__ for fn in registered}
    # the human-only verbs, by name. "unlock" is checked as its own
    # token because lock_target is deliberately agent-callable and a
    # bare "lock" substring would ban both directions at once.
    for banned_name in ("accept", "unlock", "pin"):
        assert not any(banned_name in n for n in names), (banned_name, names)
    for fn in registered:
        params = inspect.signature(fn).parameters
        for banned in ("verdict", "accepted", "stance", "gates",
                       "pin", "verified_by"):
            assert not any(banned in p for p in params), \
                f"{fn.__name__} takes a {banned} parameter"

    # the served PROSE carries the wall too. Checking for the word
    # "accept" is useless; the grammar reference says "every
    # spelling mathema accepts", so assert the substantive thing:
    # wherever the material discusses acceptance, it says whose job it
    # is, and no prompt ever tells an agent to record one.
    def flat(text):        # the prose is hard-wrapped; match on words
        return " ".join(text.lower().split())

    verdicts = flat(resources.verdict_reference())
    assert "human act" in verdicts and "no tool here will do it" in verdicts
    for name, builder in resources.PROMPTS.items():
        text = (builder("pkg.fn", "claim")
                if name == "diagnose_falsification"
                else builder("mathema.identity:sig_hash"))
        low = flat(text)
        if "accept" in low:
            assert ("human" in low and
                    ("cli" in low or "no accept tool" in low
                     or "no tool" in low)), name


def test_every_resource_and_prompt_actually_renders():
    from mathema.interfaces.mcp import resources

    for uri, (builder, mime) in resources.RESOURCES.items():
        body = builder()
        assert isinstance(body, str) and body.strip(), uri
        assert mime == "text/markdown"
    # prompts bind to a real target and resolve its live state
    text = resources.PROMPTS["claim_this_function"]("mathema.identity:sig_hash",
                                                    root=".")
    assert "sig_hash" in text and "parse_claim" in text
    assert resources.PROMPTS["triage_repository"]("mypkg")
    assert resources.PROMPTS["diagnose_falsification"]("pkg.fn", "nonneg")


def test_the_reference_material_is_generated_not_transcribed():
    # generated from what core already owns, so it cannot drift from
    # the code it describes, and no prose crosses a licence boundary
    from mathema.lexicon import LEXICON
    from mathema.reason_codes import CODE_TABLE
    from mathema.interfaces.mcp import resources

    grammar = resources.grammar_reference()
    assert all(name in grammar for name in list(LEXICON)[:5])
    codes = resources.reason_code_reference()
    assert all(code in codes for code in list(CODE_TABLE)[:5])


def test_server_construction_smoke():
    pytest.importorskip("mcp")
    from mathema.interfaces.mcp.server import build_server
    server = build_server()
    assert server is not None


def test_mcp_serve_without_the_extra_is_a_clean_exit_2(tmp_path):
    import subprocess
    import sys as _sys
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONPATH=repo)
    r = subprocess.run(
        [_sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         "sys.exit(main(['mcp', 'serve']))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    try:
        import mcp  # noqa: F401
    except ImportError:
        assert r.returncode == 2
        assert "pip install mathema[mcp]" in r.stderr
        assert "Traceback" not in r.stderr


def test_parse_claim_lints_without_adjudicating():
    ok = tools.parse_claim("for x in [0,5], f(x) >= 0")
    assert ok["ok"] is True
    assert ok["statement"] == "f(x) >= 0"
    assert ok["domain"] == {"x": "[0.0, 5.0]"}
    assert ok["route"] == "best"
    # claim() defers deep validation; the linter must not
    assert tools.parse_claim("f(x) === 0")["ok"] is False
    bad = tools.parse_claim("for x in bogus, f(x) >= 0")
    assert bad["ok"] is False and "bogus" in bad["error"]


def test_suggest_claims_tool_declares_never_verifies(tmp_path):
    import sys
    import textwrap
    pkg = tmp_path / "sgpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent("""
        def double(x: float) -> float:
            return 2.0 * x
    """))
    sys.path.insert(0, str(tmp_path))
    try:
        out = tools.suggest_claims("sgpkg.mod:double", root=str(tmp_path))
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("sgpkg")]:
            del sys.modules[m]
    # the column set gained `declared` and `aspect` so the tool and
    # `mathema claims --suggest --format json` agree exactly
    assert out["cols"] == ["name", "statement", "route", "declared",
                           "aspect"]
    assert out["rows"], "a plain scalar function earns suggestions"
    assert all(len(row) == 5 for row in out["rows"])
    # the aspect column groups the same-question suggestions: the shape
    # members (affine/convex/concave in x) all share one label, so a
    # caller reads them as one bending question, not three claims.
    by_name = {row[0]: row[4] for row in out["rows"]}
    shape = {by_name.get(n) for n in ("affine[x]", "convex[x]", "concave[x]")}
    assert shape == {"shape[x]"}
    assert by_name.get("monotonic_increasing[x]") == "monotonicity[x]"
    assert by_name.get("is_deterministic") == ""     # its own aspect
    # no verdicts anywhere: this tool declares, never adjudicates
    assert "verdict" not in str(out)


def test_pending_decisions_reads_the_stores(tmp_path):
    from mathema.spec import write_yaml
    vdir = tmp_path / ".mathema" / "verified"
    vdir.mkdir(parents=True)
    write_yaml(str(vdir / "p.mod.f.yaml"), {"p.mod.f": {
        "name": "f",
        "intent_accepted": {"by": "church", "stale": True},
        "claims": [
            {"name": "gap", "verdict": "unknown"},
            {"name": "broken", "verdict": "falsified"},
            {"name": "owned", "verdict": "skipped",
             "accepted": {"as": "risk", "note": "monitored"}},
        ]}})
    out = tools.pending_decisions(root=str(tmp_path))
    kinds = {row[2] for row in out["rows"]}
    assert kinds == {"intent-acceptance-stale", "unknown-gating",
                     "accepted-risk", "falsified-gating"}
    # the falsification awaiting a decision is in the queue, by name
    falsified = [r for r in out["rows"] if r[2] == "falsified-gating"]
    assert falsified and falsified[0][1] == "broken"


def test_audit_docs_dims_reachable_as_compact_columns():
    out = tools.audit_targets(
        ["mathema.identity"],
        cols=["key", "docsync", "intent", "domain_declared",
              "raises_declared", "callees_docsync", "quality"])
    assert out["cols"][1] == "docsync"
    for row in out["rows"]:
        assert row[1] is not None, "docsync must be computed when selected"
        assert isinstance(row[1], int)


def test_verify_project_tool_carries_structured_keys(tmp_path):
    # R002: the MCP sweep gained the same per-key structure the CLI's
    # --format json emits, so an agent never parses `lines`
    out = tools.verify_project(root=str(tmp_path))
    assert "keys" in out and isinstance(out["keys"], list)


def test_suggest_claims_tool_and_cli_agree_on_columns(tmp_path):
    # one vocabulary: the MCP tool gained the CLI's two extra facts
    # rather than the two surfaces drifting apart
    import json
    import subprocess
    import sys
    import textwrap
    pkg = tmp_path / "agpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent("""
        def scale(x: float) -> float:
            return 3.0 * x
    """))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
         str(tmp_path)])
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['claims', 'agpkg.mod.scale', '--suggest', "
              f"'--root', {str(tmp_path)!r}, '--format', 'json']))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    cli = json.loads(r.stdout)

    sys.path.insert(0, str(tmp_path))
    try:
        mcp = tools.suggest_claims("agpkg.mod:scale", root=str(tmp_path))
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("agpkg")]:
            del sys.modules[m]
    assert cli["cols"] == mcp["cols"] == [
        "name", "statement", "route", "declared", "aspect"]
    assert cli["rows"] == mcp["rows"]
    # computed-empty, never null, per the documented null policy
    assert all(row[4] == "" or isinstance(row[4], str) for row in cli["rows"])


def _demo_pkg(tmp_path, body):
    import textwrap
    pkg = tmp_path / "ckpkg"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(body))
    return tmp_path


def _with_path(tmp_path, fn):
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        return fn()
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("ckpkg")]:
            del sys.modules[m]


def test_adjudicate_target_include_selects_the_row_set(tmp_path):
    # the default is `declared`: what the authoring surfaces actually
    # state, which is what a re-check after editing a claim asks about
    root = _demo_pkg(tmp_path, '''
        def scale(x: float) -> float:
            """Claims:
                doubles: f(x) == 2.0 * x
            """
            return 2.0 * x
    ''')
    def run(**kw):
        return tools.adjudicate_target("ckpkg.mod:scale", root=str(root), **kw)

    declared = _with_path(root, lambda: run())
    suggested = _with_path(root, lambda: run(include="suggested"))
    every = _with_path(root, lambda: run(include="all"))

    assert {r["source"] for r in declared["claims"]} == {"docstring"}
    assert {r["source"] for r in suggested["claims"]} == {"suggested"}
    assert len(every["claims"]) == len(declared["claims"]) + len(suggested["claims"])
    # the default is strictly cheaper than what it replaced
    import json
    assert len(json.dumps(declared)) < len(json.dumps(every))
    bad = _with_path(root, lambda: run(include="nonsense"))
    assert bad["ok"] is False and "include" in bad["error"]


def test_adjudicate_target_empty_claims_no_longer_collapses(tmp_path):
    # `[]` means "declared surfaces only" in check()'s documented
    # three-way contract; a falsiness test made it collapse to None
    # (the suggestion battery), so the middle mode was unreachable
    root = _demo_pkg(tmp_path, '''
        def scale(x: float) -> float:
            """Claims:
                doubles: f(x) == 2.0 * x
            """
            return 2.0 * x
    ''')
    explicit = _with_path(root, lambda: tools.adjudicate_target(
        "ckpkg.mod:scale", claims=[], root=str(root), include="all"))
    battery = _with_path(root, lambda: tools.adjudicate_target(
        "ckpkg.mod:scale", claims=None, root=str(root), include="all"))
    assert len(explicit["claims"]) < len(battery["claims"])
    assert not any(r["source"] == "suggested" for r in explicit["claims"])


def test_adjudicate_target_lints_before_adjudicating(tmp_path):
    # the loop skipped the separate lint step ~10 times out of 11, so
    # it happens inside the call the agent was already making
    root = _demo_pkg(tmp_path, '''
        def scale(x: float) -> float:
            return 2.0 * x
    ''')
    out = _with_path(root, lambda: tools.adjudicate_target(
        "ckpkg.mod:scale", claims=["monotone[x]"], root=str(root)))
    assert out["passed"] is None          # adjudicated nothing
    assert out["claims"] == []
    assert out["lint"]["ok"] is False and out["lint"]["error"]


def test_adjudicate_target_hints_when_nothing_is_declared(tmp_path):
    # explicit, never a silent switch to the suggestion set
    root = _demo_pkg(tmp_path, '''
        def bare(x: float) -> float:
            return x + 1.0
    ''')
    out = _with_path(root, lambda: tools.adjudicate_target(
        "ckpkg.mod:bare", root=str(root)))
    assert out["claims"] == []
    assert "include='suggested'" in out["hint"]


def test_adjudicate_targets_batches_without_changing_the_verdicts(tmp_path):
    # a claims pass over a module in one round trip: same adjudication
    # as N single calls, one shared envelope, and the store read once
    root = _demo_pkg(tmp_path, '''
        def scale(x: float) -> float:
            """Claims:
                doubles: f(x) == 2.0 * x
            """
            return 2.0 * x

        def shift(x: float) -> float:
            """Claims:
                adds_one: f(x) == x + 1.0
            """
            return x + 1.0
    ''')
    targets = ["ckpkg.mod:scale", "ckpkg.mod:shift"]

    def run():
        singles = [tools.adjudicate_target(t, root=str(root)) for t in targets]
        batch = tools.adjudicate_targets(targets, root=str(root))
        return singles, batch
    singles, batch = _with_path(root, run)

    assert batch["cols"] == ["key", "claim", "stance", "verdict", "route",
                             "source", "gates"]
    assert batch["prefix"] == "ckpkg.mod."
    # every claim from the single calls appears once in the batch, with
    # the same stance; batching changes cost, never the verdict
    single_rows = {(s["key"].split(".")[-1], r["claim"]): r["stance"]
                   for s in singles for r in s["claims"]}
    batch_rows = {(row[0], row[1]): row[2] for row in batch["rows"]}
    assert single_rows == batch_rows
    assert batch["passed"] == all(s["passed"] for s in singles)

    # one bad name never costs the batch
    def run_bad():
        return tools.adjudicate_targets(targets + ["ckpkg.mod:nope"],
                                     root=str(root))
    out = _with_path(root, run_bad)
    assert len(out["failed"]) == 1 and "nope" in out["failed"][0][0]
    assert out["rows"], "the resolvable targets still adjudicated"


def test_parse_claim_checks_the_real_signature_when_given_a_target(tmp_path):
    # naming a parameter the function does not have is the commonest
    # authoring mistake on unfamiliar code; without this it survives
    # the linter and costs a full adjudication to surface as an opaque
    # gating `unknown`
    root = _demo_pkg(tmp_path, '''
        def doubled(x: float) -> float:
            return 2.0 * x
    ''')
    def lint(stmt):
        return _with_path(root, lambda: tools.parse_claim(
            stmt, target="ckpkg.mod:doubled", root=str(root)))

    assert lint("for x in [0,5], f(x) >= 0")["ok"] is True
    wrong_arity = lint("f(x, y) == 2*x")
    assert wrong_arity["ok"] is False and "1 parameter" in wrong_arity["error"]
    unknown_arg = lint("f(q) >= 0")
    assert unknown_arg["ok"] is False and "'q'" in unknown_arg["error"]
    bad_quant = lint("for mi in [0,10], f(mi) >= 0")
    assert bad_quant["ok"] is False and "'mi'" in bad_quant["error"]
    # a `let` binding is deliberately not a parameter, so it is exempt
    assert lint("let c be [-1,1], f(x) >= c")["ok"] is True
    # and with no target the linter is grammar-only, as before
    assert tools.parse_claim("f(x, y) == 2*x")["ok"] is True


def test_adjudicate_target_rejects_a_wrong_arity_claim_before_adjudicating(tmp_path):
    root = _demo_pkg(tmp_path, '''
        def doubled(x: float) -> float:
            return 2.0 * x
    ''')
    out = _with_path(root, lambda: tools.adjudicate_target(
        "ckpkg.mod:doubled", claims=["f(x, y) == 2*x"], root=str(root)))
    assert out["passed"] is None and out["claims"] == []
    assert "1 parameter" in out["lint"]["error"]


def test_the_wire_payload_is_compact_and_not_duplicated():
    # the SDK serializes a returned dict with indent=2 hardcoded, which
    # roughly doubles exactly the row-oriented payloads that were
    # hand-compacted to avoid repeating key names. The tools still
    # return dicts (so they stay directly callable, and the CLI
    # cross-surface pin keeps working); the server compacts at the
    # boundary.
    pytest.importorskip("mcp")
    import asyncio
    import json

    from mathema.interfaces.mcp.server import build_server
    server = build_server()

    async def call(name, args):
        return await server.call_tool(name, args)

    result = asyncio.run(call("audit_targets", {"targets": ["mathema.identity"]}))
    text = "".join(b.text for b in result.content)
    payload = json.loads(text)              # it is still valid JSON
    assert payload["cols"][1] == "span"
    # compact: no indentation, no space after separators
    assert "\n  " not in text and '", "' not in text
    assert len(text) < len(json.dumps(payload, indent=2))
    # structured_output=False, so the payload is NOT also duplicated
    # into a structured block (a bare `-> str` would have done that)
    assert result.structured_content is None


def test_implementation_coverage_tool_reports_sources_and_staleness(tmp_path):
    import json
    import os
    import sys
    import textwrap
    import time

    (tmp_path / "icp").mkdir()
    (tmp_path / "icp" / "__init__.py").write_text("")
    modp = tmp_path / "icp" / "mod.py"
    modp.write_text(textwrap.dedent('''
        def clamp01(x: float) -> float:
            """Clamp."""
            if x < 0.0:
                return 0.0
            return x
    '''))
    # a coverage report OLDER than the source: the test source is stale.
    (tmp_path / "coverage.json").write_text(json.dumps(
        {"files": {os.path.abspath(str(modp)): {"executed_lines": [2, 3, 4, 5]}}}))
    time.sleep(0.01)
    os.utime(str(modp), None)

    sys.path.insert(0, str(tmp_path))
    try:
        out = tools.implementation_coverage(["icp.mod"], root=str(tmp_path))
    finally:
        sys.path.remove(str(tmp_path))
    assert out["cols"] == ["key", "percent", "potential", "sources",
                           "test_stale", "traced", "remedy"]
    (row,) = out["rows"]
    key, percent, potential, sources, test_stale, traced, rem = row
    assert key == "icp.mod.clamp01"
    assert 0 <= percent <= 100
    assert "probe" in sources and "derive" in sources   # no test suite run needed
    assert test_stale is True                           # test source is stale
    assert out["test_report_stale"] is True
    assert "potential" in out                           # what a re-run could reach
    assert isinstance(rem, str)                         # the how-to-increase field


def test_badges_tool_reports_three_scores_and_the_triangle(tmp_path):
    import sys
    pkg = tmp_path / "btpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "def add(a: float, b: float) -> float:\n"
        "    '''Sum.'''\n"
        "    return a + b\n")
    sys.path.insert(0, str(tmp_path))
    try:
        out = tools.badges(["btpkg"], root=str(tmp_path))
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("btpkg")]:
            del sys.modules[m]
    assert set(("implementation", "intent", "clarity", "overall")) <= set(out)
    assert out["cols"] == ["key", "implementation", "intent", "clarity"]
    assert any(r[0] == "btpkg.mod.add" for r in out["rows"])
    assert "IMPL" in out["ascii"]
    # no verified store: clarity sits at the structural floor (nothing
    # verified, only what the code visibly shows), a low number not a 0
    assert out["clarity"] < 25
