# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The three badges: implementation (raw line ratio), intent (docsync),
clarity (known-about-behaviour from VERIFIED claims, a
falsified claim counts). Repo roll-up weights intent + clarity by
centrality; the overall number is the radar-triangle area. Plus the
git-diffable render and the four emitters."""
import json
import re

from mathema.badges import (_SVG_PALETTE, BadgeScores, clarity_score,
                            render_svg, ci_snapshot, render_triangle,
                            repo_badges, shields_payloads, triangle_area,
                            write_badges)


def _load(tmp_path, name, source):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(source)
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- the area / overall number ----------------------------------------

def test_triangle_area_is_full_at_100_and_shrinks_with_imbalance():
    assert triangle_area(100, 100, 100) == 100
    assert triangle_area(0, 0, 0) == 0
    assert triangle_area(100, 100, 0) < 40          # a spike has little area
    assert triangle_area(60, 60, 60) < triangle_area(80, 80, 80)


# --- clarity ----------------------------------------------

def test_clarity_scores_verified_claims_only(tmp_path):
    mod = _load(tmp_path, "bc_fixture",
                "def double(x: float) -> float:\n"
                "    '''Twice.'''\n"
                "    return 2.0 * x\n")

    # no verified claims: near-total uncertainty, only the structural floor
    # (a visibly pure, total, hazard-free helper is nearly transparent even
    # unclaimed), so a low number, not a hard 0
    assert clarity_score(mod.double, verified_claims=[]) < 25
    # knowing what it computes AND that it runs safely -> full clarity: a
    # proven identity settles the map, its output envelope, and its shape
    # (entailment), and the safety families settle how it runs
    full = [{"name": "doubles", "statement": "f(x) == 2*x",
             "verdict": "proven", "route": "derive"},
            {"name": "is_state_safe", "statement": "f(x) = f(x)",
             "verdict": "proven", "route": "examine"},
            {"name": "is_deterministic", "statement": "f(x) = f(x)",
             "verdict": "proven", "route": "examine"},
            {"name": "is_numerically_stable", "statement": "g(f, x) = 1",
             "verdict": "proven", "route": "probe"},
            {"name": "is_representation_safe", "statement": "no overflow",
             "verdict": "proven", "route": "derive"}]
    assert clarity_score(mod.double, verified_claims=full) == 100
    # a witnessed falsification COUNTS as knowledge (raises clarity)
    one_fals = [{"name": "doubles", "statement": "f(x) == 2*x",
                 "verdict": "falsified"}]
    base = clarity_score(mod.double, verified_claims=[])
    assert clarity_score(mod.double, verified_claims=one_fals) > base


def test_clarity_grades_a_holds_by_mechanism(tmp_path):
    # a structured probe leaves less unsampled surface than random sampling,
    # so it eliminates more of the same source's entropy
    mod = _load(tmp_path, "bcroute_fixture",
                "def double(x: float) -> float:\n"
                "    '''Twice.'''\n"
                "    return 2.0 * x\n")

    def held(route):
        return clarity_score(mod.double, verified_claims=[
            {"name": "doubles", "statement": "f(x) == 2*x",
             "verdict": "holds", "route": route}])

    assert held("probe") < held("probe:algorithmic") \
        < held("probe:semi_analytical") < clarity_score(
            mod.double, verified_claims=[{"name": "doubles",
            "statement": "f(x) == 2*x", "verdict": "proven"}])


def test_clarity_is_none_when_source_unavailable():
    # a builtin has no readable source, so nothing can be characterised
    # structurally: None (excluded from the roll-up), never a misleading 0
    assert clarity_score(len) is None


# --- the render -------------------------------------------------------

def test_triangle_render_is_deterministic_and_hides_degenerate():
    a = render_triangle(88, 71, 52)
    assert a == render_triangle(88, 71, 52)          # byte-stable
    assert "IMPL 88" in a and "overall" in a
    # dotted frame with ◆ corners, dot-filled score triangle, ● vertices
    assert "·" in a and "●" in a and "◆" in a and "░" not in a
    # at 100/100/100 the score vertices reach the corners, so ◆ is gone
    full = render_triangle(100, 100, 100)
    assert "·" in full and "●" in full
    degen = render_triangle(90, 3, 40)
    # a sub-5% dimension draws no shape at all, only the numbers
    assert "◆" not in degen and "●" not in degen and "below 5%" in degen


# --- the emitters -----------------------------------------------------

def test_shields_payloads_are_four_distinct_badges():
    sc = BadgeScores(88, 71, 52, 48)
    sp = shields_payloads(sc)
    assert set(sp) == {"implementation", "intent", "clarity"}
    assert sp["implementation"]["color"] == "#0E7A47"
    assert all(p["labelColor"] == "#1A1714" for p in sp.values())
    assert sp["clarity"]["label"] == "clarity"
    assert all(p["schemaVersion"] == 1 for p in sp.values())


def test_svg_and_snapshot_and_file_emission(tmp_path):
    sc = BadgeScores(88, 71, 52, 48,
                     per_function={"pkg.f": {"implementation": 100,
                                             "intent": 71, "clarity": 52}})
    svg = render_svg(sc)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "#3ECF8E" in svg and 'fill="#1A1714"' in svg
    # every colour in the card comes from the Tetrion Labs palette
    assert set(re.findall(r"#[0-9A-Fa-f]{6}", svg)) <= _SVG_PALETTE
    assert ">48%</text>" in svg
    snap = ci_snapshot(sc)
    assert snap["overall"] == 48 and "pkg.f" in snap["per_function"]
    written, pruned = write_badges(sc, str(tmp_path / "out"))
    assert pruned == []                 # a fresh directory prunes nothing
    names = {p.rsplit("/", 1)[-1] for p in written}
    assert {"triangle.txt", "triangle.svg", "snapshot.json",
            "implementation.json", "clarity.json"} <= names
    doc = json.loads((tmp_path / "out" / "snapshot.json").read_text())
    assert doc["implementation"] == 88


# --- the weighted repo roll-up ----------------------------------------

def test_repo_badges_implementation_is_a_raw_ratio_not_centrality(tmp_path):
    import sys
    pkg = tmp_path / "rbpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "def core(a: float, b: float) -> float:\n"
        "    '''Sum.'''\n"
        "    return a + b\n"
        "def wrap(a: float, b: float) -> float:\n"
        "    '''Delegates.'''\n"
        "    return core(a, b)\n")
    sys.path.insert(0, str(tmp_path))
    try:
        scores = repo_badges(["rbpkg"], root=str(tmp_path))
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("rbpkg")]:
            del sys.modules[m]
    assert 0 <= scores.implementation <= 100
    assert 0 <= scores.overall <= 100
    assert set(scores.per_function) == {"rbpkg.mod.core", "rbpkg.mod.wrap"}
    # no verified store here, so clarity sits at the structural floor
    # (nothing verified, only what the code visibly shows), a low number
    assert scores.clarity < 25
    assert scores.algo == "entropy-dimensions@1"


def test_repo_badges_gives_no_implementation_credit_from_a_stale_report(tmp_path):
    # the report fully covers `load`, but its source changed since it was
    # measured; those lines no longer describe the code, so they do not
    # count, even though the report alone would say 100%
    import sys

    from mathema.inventory import stamp_coverage_sources
    pkg = tmp_path / "stalepkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    mod = pkg / "mod.py"
    mod.write_text(
        "def load(path):\n"
        "    with open(path) as fh:\n"
        "        return fh.read()\n")
    (tmp_path / "coverage.json").write_text(json.dumps(
        {"files": {"stalepkg/mod.py": {"executed_lines": [2, 3]}}}))
    stamp_coverage_sources(str(tmp_path))
    with open(mod, "a") as fh:
        fh.write("# edited after the report\n")
    sys.path.insert(0, str(tmp_path))
    try:
        scores = repo_badges(["stalepkg"], root=str(tmp_path))
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("stalepkg")]:
            del sys.modules[m]
    assert scores.per_function["stalepkg.mod.load"]["implementation"] < 100


def test_write_badges_owns_its_directory(tmp_path):
    # the behavioural->clarity rename left behavioural.json and the
    # unpublished overall.json on disk, committed and served, frozen at
    # their last values; the diff-based CI guard is structurally blind
    # to a file nothing writes any more. write_badges now owns the
    # directory: any badge-artifact extension it did not write this
    # run is pruned, and the prune is a visible git deletion
    out = tmp_path / "out"
    out.mkdir()
    (out / "behavioural.json").write_text('{"message": "21%"}')
    (out / "overall.json").write_text('{"message": "17%"}')
    (out / "stale-readme.md").write_text("old snippet")
    (out / "keep.rst").write_text("not a badge artifact")
    (out / "sub").mkdir()
    (out / "sub" / "anything.json").write_text("{}")
    sc = BadgeScores(88, 71, 52, 48, per_function={})
    written, pruned = write_badges(sc, str(out))
    names = {p.rsplit("/", 1)[-1] for p in written}
    assert {"triangle.txt", "triangle.svg", "snapshot.json",
            "implementation.json", "intent.json", "clarity.json",
            "readme-snippet.md"} <= names
    pruned_names = sorted(p.rsplit("/", 1)[-1] for p in pruned)
    assert pruned_names == ["behavioural.json", "overall.json",
                            "stale-readme.md"]
    assert not (out / "behavioural.json").exists()
    assert not (out / "overall.json").exists()
    assert (out / "keep.rst").exists()          # not an owned extension
    assert (out / "sub" / "anything.json").exists()   # never recurses


def test_readme_snippet_states_the_meanings_and_links(tmp_path):
    sc = BadgeScores(88, 71, 52, 48, per_function={})
    write_badges(sc, str(tmp_path / "out"))
    text = (tmp_path / "out" / "readme-snippet.md").read_text()
    assert "reached by a test, a probe or a derive proof" in text
    assert "explicitly specified" in text
    assert "pinned down" in text
    assert "the area the three span" in text
    assert "know what your code actually does" in text
    # links resolve on the public docs site, never a private repository
    assert "https://mathema.tetrionlabs.com/modes/badges/#the-three-badges" in text
    assert "github.com/tetrionlabs/mathema/blob" not in text
    assert ".mathema/badges/triangle.svg" in text
    assert "OWNER/REPO" in text                 # the paste-and-substitute hint
