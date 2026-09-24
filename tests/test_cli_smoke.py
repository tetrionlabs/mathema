# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Comprehensive smoke coverage of the `mathema` CLI: every subcommand and
documented argument, checking that what comes out (exit codes, help text,
report formats) actually matches what cli.py's docstrings and argparse
help promise, and that the spec-facing fields (`--format json`'s
`tool`/`version`/`CDD_spec_version`/`functions`/`totals`) match the field
names claim-driven-development's record schema and cli.py's own
_format_check use.

Each scenario shells out to a real subprocess, one process per `mathema`
invocation, the same pattern tests/test_cli_verify.py uses and for the
same reason: inspect.getsource() resolves against the currently loaded
module's cached line numbers, so mutating a fixture file and re-importing
it in the same interpreter can read back stale, misaligned source. A
subprocess per call sidesteps that regardless of what a given test does.
"""
import json
import subprocess
import sys
import xml.etree.ElementTree as ET


def _write_funcs(path):
    path.write_text(
        "def add(a: float, b: float) -> float:\n"
        "    return a + b\n\n\n"
        "def neg(x: float) -> float:\n"
        "    return -x\n"
    )


def _write_no_functions(path):
    path.write_text("x = 1\ny = 2\n")


def _run(*argv, cwd):
    script = ("import sys; from mathema.cli import main; "
             f"sys.exit(main({list(argv)!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(cwd),
                          capture_output=True, text=True)


def _run_module_help(*argv):
    return subprocess.run([sys.executable, "-m", "mathema.cli", *argv],
                          capture_output=True, text=True)


# ---------------------------------------------------------------------------
# check: target parsing (file.py vs file.py:function)
# ---------------------------------------------------------------------------

def test_check_all_top_level_functions(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    r = _run("check", "funcs.py", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "add" in r.stdout and "neg" in r.stdout
    assert "Traceback" not in r.stderr


def test_check_single_function_target(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    r = _run("check", "funcs.py:add", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "add" in r.stdout
    assert "neg" not in r.stdout


def test_check_unknown_function_fails_cleanly(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    r = _run("check", "funcs.py:bogus", cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    assert "bogus" in r.stdout + r.stderr


def test_check_no_top_level_functions_fails_cleanly(tmp_path):
    empty = tmp_path / "empty.py"
    _write_no_functions(empty)
    r = _run("check", "empty.py", cwd=tmp_path)
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert "no functions found" in r.stdout + r.stderr


# ---------------------------------------------------------------------------
# check: --claim, --domain, --strict
# ---------------------------------------------------------------------------

def test_check_ad_hoc_claim_repeatable(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    r = _run("check", "funcs.py:add", "--claim", "f(a, b) == f(b, a)",
             "--claim", "f(a, 0.0) == a", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "add" in r.stdout


def test_check_bad_domain_syntax_fails_cleanly(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    r = _run("check", "funcs.py:add", "--domain", "not-a-domain", cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    assert "bad --domain" in r.stdout + r.stderr


def test_check_domain_name_lo_hi_syntax_accepted(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    r = _run("check", "funcs.py:add", "--domain", "a=0:1", "--domain", "b=-1:1",
             "--claim", "excluded_outside_domain(a)",
             "--claim", "excluded_outside_domain(b)",
             "--format", "json", cwd=tmp_path)
    # the parsed domain must actually reach the adjudicator, not just
    # parse: the declared exclusion claims trial values outside each
    # bound and report the acceptance per parameter
    assert r.returncode == 1, r.stdout + r.stderr
    assert "excluded_outside_domain[a]" in r.stdout
    assert "excluded_outside_domain[b]" in r.stdout
    assert "asserted, not enforced" in r.stdout


def test_check_fails_on_a_declared_but_unenforced_exclusion(tmp_path):
    # add() never rejects any input. A bare --domain reports nothing
    # about enforcement (no mode any more); DECLARING the exclusion
    # makes the unenforced domain a falsified claim, a failure in
    # every mode, with the accepted value as witness.
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    bare = _run("check", "funcs.py:add", "--domain", "a=0:1", cwd=tmp_path)
    assert bare.returncode == 0, bare.stdout
    assert "excluded_outside_domain" not in bare.stdout

    declared = _run("check", "funcs.py:add", "--domain", "a=0:1",
                    "--claim", "excluded_outside_domain(a)", cwd=tmp_path)
    assert declared.returncode == 1, declared.stdout
    assert "falsified" in declared.stdout


def test_check_strict_fails_on_unverifiable_claims(tmp_path):
    # a function that raises unconditionally, regardless of input, is a
    # robust way to force a real "no evaluable inputs" verdict on every
    # probe-route claim (checked==0 on every trial, for any probe
    # technique), a guarded-but-otherwise-trivial function isn't a
    # reliable fixture for this any more, now that route="best" claims
    # have a real probe:algorithmic/derive fallback for cases that used
    # to have no evaluable path at all.
    guarded = tmp_path / "guarded.py"
    guarded.write_text(
        "def always_raises(x: float) -> float:\n"
        "    raise ValueError('always fails')\n"
    )
    lenient = _run("check", "guarded.py:always_raises", cwd=tmp_path)
    assert lenient.returncode == 0, lenient.stdout
    assert "1 skipped" in lenient.stdout

    strict = _run("check", "guarded.py:always_raises", "--strict", cwd=tmp_path)
    assert strict.returncode == 1, strict.stdout
    assert "1 skipped claim(s)" in strict.stdout


# ---------------------------------------------------------------------------
# check: --format for all 5 choices
# ---------------------------------------------------------------------------

def test_check_format_text_is_default(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    default = _run("check", "funcs.py", cwd=tmp_path)
    explicit = _run("check", "funcs.py", "--format", "text", cwd=tmp_path)
    assert default.stdout == explicit.stdout
    assert default.returncode == explicit.returncode == 0


def test_check_format_json_shape(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    r = _run("check", "funcs.py", "--format", "json", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads(r.stdout)
    assert set(doc.keys()) == {"tool", "version", "CDD_spec_version", "functions",
                               "totals"}
    assert doc["tool"] == "mathema"
    assert doc["CDD_spec_version"] == "0.2.0"
    names = {f["name"] for f in doc["functions"]}
    assert names == {"funcs.add", "funcs.neg"}
    for f in doc["functions"]:
        assert {"name", "tier", "identity", "holds", "refuted", "unverifiable",
                "verified", "total", "coverage", "claims", "problems"} <= set(f)
        assert set(f["identity"]) == {"form", "sig"}
    totals = doc["totals"]
    assert set(totals) == {"functions", "verified", "total", "failed"}
    assert totals["functions"] == 2
    assert totals["failed"] == 0


def test_check_counts_proven_claims_in_coverage(tmp_path):
    """A claim settled symbolically (verdict "proven", the strongest
    evidence on the ladder) counts in verified/total coverage and is
    reported under its own `proven` field; it used to fall out of both
    counts, so `mathema check` under-reported exactly the claims it had
    the most evidence for. `add`'s suggested claims (route "auto")
    reliably include several the derive route settles outright."""
    funcs = tmp_path / "funcs.py"
    funcs.write_text(
        "from mathema import claim, claims_decorator\n\n\n"
        "@claims_decorator(claim('f(a, b) == f(b, a)', route='derive'))\n"
        "def add(a: float, b: float) -> float:\n"
        "    return a + b\n")
    r = _run("check", "funcs.py:add", "--format", "json", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads(r.stdout)
    (row,) = doc["functions"]
    proven_claims = [c for c in row["claims"] if c["verdict"] == "proven"]
    assert proven_claims, "expected the declared derive claim to prove"
    assert row["proven"] == len(proven_claims)
    assert row["total"] == len(row["claims"])
    assert row["verified"] == row["proven"] + row["holds"] + row["refuted"]

    text = _run("check", "funcs.py:add", cwd=tmp_path)
    assert f'{row["proven"]} proven' in text.stdout


def test_check_format_junit_is_well_formed_xml(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    r = _run("check", "funcs.py", "--format", "junit", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    root = ET.fromstring(r.stdout)
    assert root.tag == "testsuite"
    assert root.get("tests") == "2"
    assert root.get("failures") == "0"
    cases = root.findall("testcase")
    assert len(cases) == 2
    assert {c.get("classname") for c in cases} == {"mathema.claims"}


def test_check_format_junit_escapes_failures(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    r = _run("check", "funcs.py:add", "--domain", "a=0:1",
             "--claim", "excluded_outside_domain(a)",
             "--format", "junit", cwd=tmp_path)
    assert r.returncode == 1, r.stdout
    root = ET.fromstring(r.stdout)  # raises if malformed / unescaped
    failure = root.find("testcase/failure")
    assert failure is not None
    assert "falsified" in failure.get("message")


def test_check_format_github_has_annotations(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    ok = _run("check", "funcs.py:add", "--format", "github", cwd=tmp_path)
    assert ok.returncode == 0, ok.stdout
    assert "::notice title=mathema claim check::funcs.add" in ok.stdout

    fail = _run("check", "funcs.py:add", "--domain", "a=0:1",
               "--claim", "excluded_outside_domain(a)",
               "--format", "github", cwd=tmp_path)
    assert fail.returncode == 1, fail.stdout
    assert "::error title=mathema claim check::funcs.add" in fail.stdout


def test_check_format_md_is_a_table(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    r = _run("check", "funcs.py", "--format", "md", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = r.stdout.splitlines()
    assert lines[0].startswith("| function |")
    assert lines[1].startswith("|---|")
    assert any("`funcs.add`" in ln for ln in lines)
    assert any("`funcs.neg`" in ln for ln in lines)
    assert "cdd spec v0.2.0" in r.stdout


# ---------------------------------------------------------------------------
# check: --output
# ---------------------------------------------------------------------------

def test_check_output_writes_file_instead_of_stdout(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    out = tmp_path / "report.txt"
    r = _run("check", "funcs.py", "--output", "report.txt", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == ""
    assert out.exists()
    assert "add" in out.read_text() and "neg" in out.read_text()


# ---------------------------------------------------------------------------
# verify: --root, --target, --all, --lenient, exit codes
# ---------------------------------------------------------------------------

def _seed(tmp_path, funcs_path):
    script = f"""
import sys
sys.path.insert(0, {str(funcs_path.parent)!r})
import mathema, funcs
for name in ("add", "neg"):
    mathema.write_spec(getattr(funcs, name), root={str(tmp_path)!r})
"""
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_verify_nothing_declared_is_clean_noop(tmp_path):
    r = _run("verify", "--root", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "nothing declared yet" in r.stdout


def test_verify_root_argument_points_elsewhere(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    funcs = project / "funcs.py"
    _write_funcs(funcs)
    _seed(project, funcs)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    r = _run("verify", "--root", str(project), cwd=elsewhere)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "2 fresh" in r.stdout


def test_verify_all_forces_reverification(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    _seed(tmp_path, funcs)

    r = _run("verify", "--root", str(tmp_path), "--all", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 fresh" in r.stdout
    assert "2 adjudicated" in r.stdout
    assert "forced (--all)" in r.stdout


def test_verify_dotted_keys_resolve_and_bare_names_fail_cleanly(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    specs = tmp_path / ".mathema" / "verified"
    specs.mkdir(parents=True)
    (specs / "funcs.add.yaml").write_text(
        'funcs.add:\n  identity: {form: "deadbeef0000"}\n  claims: []\n')
    (specs / "add.yaml").write_text(
        'add:\n  identity: {form: "deadbeef0000"}\n  claims: []\n')

    r = _run("verify", "--root", str(tmp_path), cwd=tmp_path)
    # the dotted key resolves through the project root; the legacy
    # bare-name key fails as a clear per-key problem, not a traceback
    assert r.returncode == 1, r.stdout + r.stderr
    assert "funcs.add" in r.stdout
    assert "add: cannot resolve" in r.stdout


def test_verify_lenient_downgrades_unverifiable_to_exit_0(tmp_path):
    funcs = tmp_path / "funcs.py"
    funcs.write_text(
        "import math\n\n\n"
        "def add(a: float, b: float) -> float:\n"
        "    return a + b\n\n\n"
        "def neg(x: float) -> float:\n"
        "    return math.lgamma(x)\n"
    )
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    (claims_dir / "neg.claims.yaml").write_text(
        "funcs.neg:\n"
        "  claims:\n"
        "    - name: unliftable\n"
        # digamma's sign stays a genuinely OPEN unknown: sympy cannot
        # settle it, probe cannot read d(), and the lifted-numeric
        # fallback declines (polygamma has no plain-math lambdify
        # mapping), so the accept-as-risk flow exercises a real open
        # gap; the old literal-bound Sum fixture now falsifies with an
        # executed witness instead
        '      statement: "for x in [2, 10], d(f(x), x) >= 0"\n'
        "      route: derive\n"
    )
    _seed(tmp_path, funcs)

    # an open claim fails in EVERY mode until a human owns the risk
    strict = _run("verify", "--root", str(tmp_path), cwd=tmp_path)
    assert strict.returncode == 1, strict.stdout
    assert "unverifiable" in strict.stdout or "unknown" in strict.stdout

    lenient = _run("verify", "--root", str(tmp_path), "--lenient", cwd=tmp_path)
    assert lenient.returncode == 1, lenient.stdout

    # accepting the risk reclassifies it; lenient then proceeds, strict
    # still refuses the accepted skip (visible, never laundered)
    accept = _run("accept", "funcs.neg", "unliftable", "--as", "risk",
                  "--by", "test", "--yes", "--root", str(tmp_path),
                  cwd=tmp_path)
    assert accept.returncode == 0, accept.stdout + accept.stderr
    lenient = _run("verify", "--root", str(tmp_path), "--lenient", "--all",
                   cwd=tmp_path)
    assert lenient.returncode == 0, lenient.stdout
    strict = _run("verify", "--root", str(tmp_path), "--all", cwd=tmp_path)
    assert strict.returncode == 1, strict.stdout


def test_verify_unresolvable_key_reported_not_crashed(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    _seed(tmp_path, funcs)
    specs = tmp_path / ".mathema" / "verified"
    (specs / "funcs.ghost.yaml").write_text(
        'funcs.ghost:\n  identity: {form: "deadbeef0000"}\n  claims: []\n')

    r = _run("verify", "--root", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 1, r.stdout
    assert "cannot resolve to a live function" in r.stdout
    assert "Traceback" not in r.stderr


# ---------------------------------------------------------------------------
# status: with/without target, --root
# ---------------------------------------------------------------------------

def test_status_without_target_reports_nothing_tagged(tmp_path):
    r = _run("verify", "--status", "--root", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "mathema status" in r.stdout
    assert "no @track_claims-tagged functions alive" in r.stdout


def test_status_with_target_registers_and_reports(tmp_path):
    # Was broken: cmd_status called `_load_module(args.target)` and
    # discarded the returned module without binding it to a name; since
    # @track_claims only keeps a weakref in the registry, the module (and
    # the functions it defines) got garbage-collected before status() ran,
    # so a target's tagged functions never showed up. Fixed by keeping a
    # local reference to the loaded module until after status() reads it.
    tracked = tmp_path / "tracked.py"
    tracked.write_text(
        "import mathema\n\n"
        "@mathema.track_claims\n"
        "def add(a: float, b: float) -> float:\n"
        "    return a + b\n"
    )
    r = _run("verify", "--status", "tracked.py", "--root", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no @track_claims-tagged functions alive" not in r.stdout
    # _load_module() imports the target under its real dotted module name
    # (tracked.py under root tmp_path -> "tracked"), not a synthetic one;
    # @track_claims's own key is f"{fn.__module__}.{fn.__qualname__}", and
    # a real name here makes it match the key a verified record written
    # the normal way (write_spec() on a normally-imported function) would use.
    assert "tracked.add" in r.stdout
    assert "no verified record" in r.stdout   # tagged, but never write_spec()'d


def test_status_root_flag_points_at_verified_store(tmp_path):
    # Independent of the target-loading behavior above: --root must
    # still be the directory status() reads .mathema/verified from.
    r = _run("verify", "--status", "--root", str(tmp_path / "nested"), cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "mathema status" in r.stdout


def test_status_with_target_finds_a_verified_record_written_the_normal_way(tmp_path):
    # Was broken: cmd_status tagged a file-target's functions under a
    # synthetic module name ("_mathema_target"), so @track_claims's own
    # key (f"{fn.__module__}.{fn.__qualname__}") never matched a verified
    # record written the normal way, write_spec() on a function imported as
    # part of a real package, even when that record genuinely existed
    # and was fresh. `mathema status` reported "no verified record" for a
    # function that actually had one. Fixed by loading the target under
    # its real dotted module name (_module_name_for) instead.
    pkg = tmp_path / "demo_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "funcs.py").write_text(
        "import mathema\n\n"
        "@mathema.track_claims\n"
        "def square(x: float) -> float:\n"
        "    return x * x\n"
    )
    write_script = (
        "import sys; sys.path.insert(0, '.')\n"
        "import mathema\n"
        "from demo_pkg.funcs import square\n"
        "mathema.write_spec(square, root='.')\n"
    )
    r = subprocess.run([sys.executable, "-c", write_script], cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / ".mathema" / "verified" / "demo_pkg.funcs.square.yaml").exists()

    r = _run("verify", "--status", "demo_pkg/funcs.py", "--root", ".", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "demo_pkg.funcs.square: fresh" in r.stdout
    assert "no verified record" not in r.stdout


# ---------------------------------------------------------------------------
# argument error handling: clean SystemExit, not a traceback dump
# ---------------------------------------------------------------------------

def test_unknown_subcommand_fails_cleanly():
    r = _run_module_help("bogus-command")
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert "invalid choice" in r.stderr


def test_check_missing_target_fails_cleanly():
    r = _run_module_help("check")
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert "required" in r.stderr


def test_check_bad_format_choice_fails_cleanly(tmp_path):
    funcs = tmp_path / "funcs.py"
    _write_funcs(funcs)
    r = subprocess.run([sys.executable, "-m", "mathema.cli", "check", "funcs.py",
                       "--format", "yaml"], cwd=str(tmp_path),
                      capture_output=True, text=True)
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert "invalid choice" in r.stderr


def test_no_subcommand_fails_cleanly():
    r = _run_module_help()
    assert r.returncode == 2
    assert "Traceback" not in r.stderr


# ---------------------------------------------------------------------------
# help text: every subcommand documents its arguments
# ---------------------------------------------------------------------------

def test_top_level_help_lists_all_subcommands():
    r = _run_module_help("--help")
    assert r.returncode == 0
    assert all(cmd in r.stdout for cmd in
               ("check", "verify", "audit", "init", "describe",
                "docsync", "claims", "accept"))
    # the merged verbs are gone from the surface
    for gone in ("status", "index", "issue"):
        assert f" {gone} " not in r.stdout.split("{")[-1]


def test_check_help_documents_all_flags():
    r = _run_module_help("check", "--help")
    assert r.returncode == 0
    for flag in ("--claim", "--domain", "--strict", "--lenient",
                "--format", "--output",
                "--trials-scale"):
        assert flag in r.stdout, flag
    for choice in ("text", "json", "junit", "github", "md"):
        assert choice in r.stdout, choice


def test_verify_help_documents_all_flags():
    r = _run_module_help("verify", "--help")
    assert r.returncode == 0
    for flag in ("--root", "--all", "--lenient", "--trials-scale"):
        assert flag in r.stdout, flag


# ---------------------------------------------------------------------------
# check: --trials-scale
# ---------------------------------------------------------------------------

def _write_unliftable(path):
    # sorts a local copy through list.sort(), structurally impure
    # enough that the derive route declines, so a commutativity claim
    # genuinely SAMPLES (the scale tests need a real n to compare)
    path.write_text(
        "def add(a: float, b: float) -> float:\n"
        "    vals = [a, b]\n"
        "    vals.sort()\n"
        "    return vals[0] + vals[1]\n")


def test_trials_scale_shrinks_the_reported_n(tmp_path):
    # suggestions no longer populate the report: declare a probe claim
    # so the runs have a sampled n to compare
    _write_unliftable(tmp_path / "funcs.py")
    probe_claim = ("--claim", "for a in [-5,5], b in [-5,5], f(a, b) == f(b, a)")
    default = _run("check", "funcs.py:add", "--format", "json", *probe_claim,
                   cwd=tmp_path)
    scaled = _run("check", "funcs.py:add", "--format", "json", *probe_claim,
                  "--trials-scale", "0.25", cwd=tmp_path)
    assert default.returncode == 0 and scaled.returncode == 0
    default_ns = {c["n"] for f in json.loads(default.stdout)["functions"]
                  for c in f["claims"] if c["n"]}
    scaled_ns = {c["n"] for f in json.loads(scaled.stdout)["functions"]
                for c in f["claims"] if c["n"]}
    assert max(scaled_ns) < min(default_ns)


def test_trials_scale_never_drops_below_the_floor(tmp_path):
    _write_unliftable(tmp_path / "funcs.py")
    r = _run("check", "funcs.py:add", "--format", "json",
            "--claim", "for a in [-5,5], b in [-5,5], f(a, b) == f(b, a)",
            "--trials-scale", "0.001", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    ns = {c["n"] for f in json.loads(r.stdout)["functions"]
         for c in f["claims"] if c["n"]}
    assert min(ns) >= 16


def test_trials_scale_above_one_is_harmless_not_an_error(tmp_path):
    # "harmless" means clamped, not amplified: the sampled budgets under
    # scale 4.0 match an unscaled run exactly
    import json as _json
    _write_funcs(tmp_path / "funcs.py")
    base = _run("check", "funcs.py", "--format", "json", cwd=tmp_path)
    r = _run("check", "funcs.py", "--trials-scale", "4.0",
             "--format", "json", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr

    def _ns(out):
        data = _json.loads(out)
        return [c.get("n") for f in data["functions"]
                for c in f.get("claims", []) if c.get("n")]
    assert _ns(r.stdout) == _ns(base.stdout)


def test_trials_scale_zero_or_negative_is_a_clean_error(tmp_path):
    _write_funcs(tmp_path / "funcs.py")
    for bad in ("0", "-0.5"):
        r = _run("check", "funcs.py", "--trials-scale", bad, cwd=tmp_path)
        assert r.returncode == 2, r.stdout + r.stderr
        assert "--trials-scale" in (r.stdout + r.stderr)


def test_verify_status_flag_is_documented():
    r = _run_module_help("verify", "--help")
    assert r.returncode == 0
    assert "--status" in r.stdout
