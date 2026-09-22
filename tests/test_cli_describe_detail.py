# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema describe <key>`: the single-function deep-dive view,
signature/identity hashes, inferred domains, claims, and the five-tier
ladder (source/normalized/structural sharing one plain indented
rendering, lifted/canonical a separate rendering of the real lift
result). A richer, box-drawing diagram rendering, callee inlining, a
`Legend:` for long names, can register a `"describe_diagram"`
capability to replace this wholesale (see `mathema/_tier_text.py`,
`mathema/_providers.py`); that renderer's own tests live wherever it
does, not here; these tests cover only mathema's own zero-install
default. Real subprocess per invocation, same reasoning as
test_cli_describe.py's own docstring.
"""
import subprocess
import sys


def _repo_root():
    import os
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_with_repo_on_path(pkg_root):
    import os
    env = dict(os.environ)
    parts = [_repo_root(), str(pkg_root)]
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _write_pkg(tmp_path, body):
    pkg = tmp_path / "trialpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(body)
    return tmp_path


def _run(root, *args):
    script = ("import sys; from mathema.cli import main; "
             f"sys.exit(main({list(args)!r} + ['--root', {str(root)!r}]))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True,
                          env=_env_with_repo_on_path(root))


_BODY = '''
def branchy(r: float, scale: str = "info") -> float:
    if scale == "info":
        return r ** 2
    return 1.0 - r


def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def dot_product(a: list, b: list) -> float:
    total = 0.0
    for i in range(len(a)):
        total += a[i] * b[i]
    return total


def helper(x: float, scale: float) -> float:
    return x / scale


def pipeline(x: list, scale: float, alpha: float) -> float:
    a = helper(x[0], scale)
    b = ema(x, alpha)
    return a + b


def unliftable(x: float) -> float:
    while x > 0:
        x -= 1
    return x
'''


def test_describe_single_function_shows_signature_and_hashes(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg.mod.ema")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "trialpkg.mod.ema(x: list, alpha: float) -> float" in r.stdout
    assert "sig_hash:" in r.stdout
    assert "form_hash:" in r.stdout


def test_describe_shows_all_five_tiers_by_default(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg.mod.ema")
    assert r.returncode == 0, r.stdout + r.stderr
    for tier in ("source", "normalized", "structural", "lifted", "canonical"):
        assert f"--- {tier}" in r.stdout, r.stdout


def test_describe_tier_flag_narrows_to_one_section(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg.mod.ema", "--tier", "canonical")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "--- canonical" in r.stdout
    assert "--- source" not in r.stdout
    assert "--- structural" not in r.stdout


def test_describe_tier_flag_accepts_a_1_to_5_ladder_position(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    by_name = _run(root, "describe", "trialpkg.mod.ema", "--tier", "canonical")
    by_number = _run(root, "describe", "trialpkg.mod.ema", "--tier", "5")
    assert by_number.returncode == 0, by_number.stdout + by_number.stderr
    assert "--- canonical" in by_number.stdout
    assert "--- source" not in by_number.stdout
    assert by_number.stdout == by_name.stdout

    source_by_number = _run(root, "describe", "trialpkg.mod.ema", "--tier", "1")
    assert "--- source" in source_by_number.stdout
    assert "--- canonical" not in source_by_number.stdout


def test_describe_multiline_statement_renders_every_line(tmp_path):
    # a compound statement the derive route doesn't specially dispatch
    # (try/except here) unparses to *several* physical lines, plain
    # indented text has no 2D alignment to violate, but every line must
    # still show up, in order, none silently dropped or merged into a
    # neighboring statement.
    body = '''
def guarded() -> str:
    try:
        import json
    except ImportError as exc:
        raise ImportError("nope") from exc
    return "ok"
'''
    root = _write_pkg(tmp_path, body)
    r = _run(root, "describe", "trialpkg.mod.guarded", "--tier", "source")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = r.stdout.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("--- source"))
    diagram_lines = []
    for ln in lines[start + 1:]:
        if not ln.strip():
            break
        diagram_lines.append(ln)
    # ast.unparse() normalizes string-literal quoting to single quotes
    assert diagram_lines[-1].strip() == "return 'ok'"
    assert "raise ImportError" in diagram_lines[-2]
    assert "return" not in diagram_lines[-2]


def test_describe_fold_lifts_to_a_real_closed_form(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg.mod.ema", "--tier", "canonical")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "not available" not in r.stdout
    # the fold's own closed form always has a base case at L == 1
    assert "L = 1" in r.stdout


def test_describe_sum_loop_reports_as_sum_loop_structurally(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg.mod.dot_product", "--tier", "structural")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "sum-loop" in r.stdout


def test_describe_branch_shows_the_real_condition_at_source_tier(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg.mod.branchy", "--tier", "source")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "scale == 'info'" in r.stdout
    # structural tier must not leak the same condition text
    r2 = _run(root, "describe", "trialpkg.mod.branchy", "--tier", "structural")
    assert "scale ==" not in r2.stdout


def test_describe_unliftable_function_states_a_real_reason_not_a_silent_gap(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg.mod.unliftable", "--tier", "lifted")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "not available" in r.stdout
    # a real, specific reason follows the section header, not blank
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    idx = next(i for i, ln in enumerate(lines) if ln.startswith("--- lifted"))
    assert lines[idx + 1].strip()


def test_describe_plain_default_never_inlines_a_callee_regardless_of_depth(tmp_path):
    # callee inlining is a describe_diagram capability, not part of
    # mathema's own zero-install rendering, a whole-statement call to
    # a local function always shows as an ordinary call, at any --depth,
    # unless a "describe_diagram" provider is registered.
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg.mod.pipeline", "--tier", "source", "--depth", "2")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "inlined" not in r.stdout
    assert "a = helper(x[0], scale)" in r.stdout


def test_describe_colon_bare_name_shorthand_resolves_uniquely(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg:ema")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "trialpkg.mod.ema" in r.stdout


def test_describe_unresolvable_target_reports_cleanly_and_exits_nonzero(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg:does_not_exist")
    assert r.returncode == 2
    assert "no function named" in r.stderr


def test_describe_ambiguous_bare_name_lists_candidates_rather_than_guessing(tmp_path):
    # two functions across different modules sharing the same bare name;
    # the colon shorthand must list both candidates and refuse to
    # pick one, never silently resolve to whichever discover() happens
    # to find first.
    pkg = tmp_path / "trialpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(_BODY)
    (pkg / "other.py").write_text("def ema(y):\n    return y\n")
    r = _run(tmp_path, "describe", "trialpkg:ema")
    assert r.returncode == 2
    assert "ambiguous" in r.stderr
    assert "trialpkg.mod.ema" in r.stderr
    assert "trialpkg.other.ema" in r.stderr


def test_describe_is_deterministic_across_two_runs(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r1 = _run(root, "describe", "trialpkg.mod.ema")
    r2 = _run(root, "describe", "trialpkg.mod.ema")
    assert r1.returncode == 0 == r2.returncode
    assert r1.stdout == r2.stdout


def test_describe_plain_rendering_nests_loop_body_one_level_deeper(tmp_path):
    # the plain renderer's own real invariant, in place of the
    # box-drawing renderer's equal-row-width one (covered at the unit
    # level, for that renderer specifically, by test_describe_diagram.py):
    # a loop's body is indented one level deeper than its own header.
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg.mod.ema", "--tier", "source")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = r.stdout.splitlines()
    header_idx = next(i for i, ln in enumerate(lines) if ln.strip().startswith("for v in"))
    assert lines[header_idx + 1].startswith("    ")
    assert not lines[header_idx].startswith(" ")


def test_describe_renders_a_literal_finite_domain_as_a_discrete_set(tmp_path):
    # typing_info()'s own finite_domains is a plain list, not part of the
    # Interval/"Z"/"N"/frozenset domain vocabulary every other domain
    # source produces, describe_detail() wraps it in a frozenset so
    # render_domain_bound() (which only knows that vocabulary) can
    # render it without guessing at an arbitrary-length list's shape.
    body = '''
from typing import Literal

def scaled(x: float, mode: Literal["a", "b", "c"] = "a") -> float:
    return x
'''
    root = _write_pkg(tmp_path, body)
    r = _run(root, "describe", "trialpkg.mod.scaled")
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'mode: {"a", "b", "c"}' in r.stdout
