# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The three badges: implementation, intent, clarity.

Three orthogonal measures of a codebase, each 0-100:

- IMPLEMENTATION (code layer): the raw line ratio of `impl_coverage`,
  how many statements a test, a probe, or a derive proof exercised. A
  physical ratio, so it is neither averaged nor centrality-weighted.
- INTENT (spec layer): `docstring.docstring_sync`, how much of what each
  function's docstring states is actually claimed and verified.
- CLARITY (behaviour layer): how much is KNOWN about a
  function's behaviour, an information score, not a pass-rate. A
  falsified claim COUNTS (you now know it fails there); correctness is a
  separate question, surfaced by the falsification list.

The two per-function-quality scores (intent, clarity) roll up to the
repo by a CENTRALITY-WEIGHTED mean (`centrality.centrality_weights`): a
function the rest of the codebase depends on counts for more than a leaf.
The overall/health number is the AREA of the radar triangle the three
scores span.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The clarity ALGORITHM is versioned like a route: an open string, so a
# score is only ever compared against one computed the same way. A
# calibration change (the constants below) bumps the minor (@1.1); a
# structural change (a dimension added or removed, an entailment changed)
# bumps the major (@2). ci_snapshot records it beside the score.
CLARITY_ALGO = "entropy-dimensions@1"

# The @1 constants, one labelled set so a recalibration is a new set plus a
# version bump and past scores stay reproducible. Every number is the a-
# priori ENTROPY (nominal bits) of one source, or a fraction of a source a
# mechanism eliminates. These are principled placeholders; calibration
# against real repositories is future work.
_BITS: dict[str, float] = {
    # identity: the map, plus one region's worth per branch it splits into
    "graph": 1.0, "region": 0.4,
    # form: the relational shape (the output envelope is _EXTENT_BITS)
    "shape_branched": 1.0, "shape_flat": 0.4,
    # domain: what each parameter accepts; a guarded parameter has a real,
    # implementation-specific boundary, an unguarded one barely any
    "domain_guarded": 1.0, "domain_soft": 0.3,
    # safety families, scaled to whether the hazard can actually occur
    "safety_pure": 0.15, "safety_impure": 0.8,
    "safety_numeric": 0.2, "safety_numeric_loop": 0.4,
    "safety_seq": 0.4, "safety_str": 1.0,
    # failure: a raise site, a covered hazard call (reducible), an
    # uncovered one (a black box: irreducible, it has no reducer at all)
    "raise": 0.5, "hazard_covered": 0.5, "hazard_uncovered": 2.0,
    # structural (examine-route) facts the code exhibits without a declared
    # claim: visible purity, an unguarded signature. Weaker than a verified
    # examine, so they lift the floor without reaching a claim's credit.
    "base_pure": 0.60, "base_impure": 0.10, "base_domain_soft": 0.30,
    "base_safety": 0.30, "base_arbitrary_input": 0.20,
}
# form: the output envelope, by return kind
_EXTENT_BITS: dict[str, float] = {
    "none": 0.0, "scalar": 1.0, "sequence": 1.5, "matrix": 2.0,
    "mapping": 1.5, "bool": 0.5}
# how much of a source a verdict eliminates. proven is whole-domain; a holds
# is graded by MECHANISM (a structured probe leaves less unsampled surface,
# so less residual entropy, than random sampling); a WITNESSED falsification
# is knowledge (an uncorroborated disproof is already `unknown`, scoring 0)
_PROVEN_STRENGTH = 1.0
_FALSIFIED_STRENGTH = 0.85
_HOLDS_STRENGTH: dict[str, float] = {
    "examine": 0.90, "derive": 0.90, "probe:semi_analytical": 0.85,
    "probe:algorithmic": 0.80, "probe:minimal_example": 0.78, "probe": 0.60}
_HOLDS_DEFAULT = 0.60

_IDENTITY_KINDS = frozenset({"value_identity", "equivalence", "closed_form",
                             "roundtrip"})

# the realization families the clarity metric models, mapped to the source
# each reduces. Some are checked under names not in routes.SAFETY_PREDICATES
# (is_numerically_stable), and several near-siblings collapse onto one
# source (extremity is a representation hazard, empty is a missing one).
_SAFETY_SOURCE = {
    "is_state_safe": "is_state_safe",
    "is_deterministic": "is_deterministic",
    "is_reproducible": "is_deterministic",
    "is_numerically_stable": "is_numerically_stable",
    "is_representation_safe": "is_representation_safe",
    "is_extremity_safe": "is_representation_safe",
    "is_pole_safe": "is_representation_safe",
    "is_missing_safe": "is_missing_safe",
    "is_empty_safe": "is_missing_safe",
    "is_arbitrary_input_safe": "is_arbitrary_input_safe",
    "is_compendium_safe": "is_compendium_safe",
}


def _strength(verdict: str, route: str) -> float:
    """How much of a source's entropy this verdict, reached by this
    mechanism, eliminates. See the @1 constants above."""
    from .records import classify_verdict
    v = classify_verdict(verdict or "")
    if v == "proven":
        return _PROVEN_STRENGTH
    if v == "falsified":
        return _FALSIFIED_STRENGTH
    if v == "holds":
        return _HOLDS_STRENGTH.get(route or "probe", _HOLDS_DEFAULT)
    return 0.0


def _claim_kind(name: str, statement: str) -> str:
    """Classify a claim into a behavioural KIND, from its name aspect
    first, then its statement shape. Cheap: string inspection only, no
    lift, so the badge stays CI-fast."""
    from .families import claim_aspect
    from .matrices import PROPERTIES as _MATRIX
    stmt = statement or ""
    if stmt.startswith("raises(") or " raises(" in stmt:
        return "partiality"
    base = (name or "").split("[", 1)[0]
    aspect = claim_aspect(name or "")[0]
    if aspect in ("monotonicity", "shape", "symmetry"):
        return aspect
    if base in _MATRIX:
        return "structure"
    if base in ("is_sorted_output", "output_never_none", "preserves_length",
                "preserves_type", "is_permutation_of_input"):
        return "invariant"
    if base in ("returns_in_range", "bounded_lower", "bounded_upper"):
        return "bound"
    if base == "equivalent_to_core":
        return "equivalence"
    if base == "roundtrips_with":
        return "roundtrip"
    if base == "closed_form":
        return "closed_form"
    if base == "idempotent":
        return "idempotent"
    if base in ("is_defined", "excluded_outside_domain"):
        return "definedness"
    if "=:=" in stmt or " equiv " in stmt:
        return "equivalence"
    has_ineq = any(op in stmt for op in ("<=", ">=", "<", ">"))
    if "==" in stmt and not has_ineq:
        return "value_identity"
    if has_ineq:
        return "bound"
    return "relation"


def _verified_claims_for(fn, root: str) -> list:
    """The verified-store claim rows for one function (`name`/`verdict`/
    `route` each), or `[]` when it has no verified record. This is the
    COMMITTED knowledge, what `mathema verify` adjudicated and wrote, not
    a live re-derivation: a function nobody has claimed and verified has
    an empty behavioural record on purpose."""
    from .spec import load_verified
    key = f"{getattr(fn, '__module__', '')}.{getattr(fn, '__qualname__', '')}"
    entry = (load_verified(root).get(key) or {}).get("entry") or {}
    return entry.get("claims") or []


@dataclass(frozen=True)
class _Profile:
    """The structural + hazard surface behind a function's clarity, all
    from `analyze_source` and the compendium hazard scan (no lift)."""
    params: tuple = ()            # kinds: scalar / sequence / matrix / string
    guarded: int = 0             # parameters with a real accept/reject boundary
    cx: int = 0                  # decision points (the branch surface)
    output: str = "scalar"
    numeric: bool = False
    loops: int = 0
    pure: bool = True
    str_params: int = 0
    n_raises: int = 0
    covered_calls: int = 0
    uncovered_calls: int = 0


def _clarity_profile(fn, facts=None, root: str = ".") -> _Profile | None:
    """Assemble a function's `_Profile`, or None when its source is
    unavailable (a builtin, a C extension): nothing to characterise
    structurally, so it leaves the clarity roll-up rather than scoring 0."""
    import ast
    import warnings
    if fn is None:
        return None
    try:
        if facts is None:
            from .analysis import analyze_source
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                facts = analyze_source(fn)
    except Exception:
        return None
    tree = getattr(facts, "tree", None)
    if tree is None:
        return None
    cx = n_raises = 0
    numeric = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            n_raises += 1
        elif isinstance(node, (ast.If, ast.IfExp, ast.For, ast.AsyncFor,
                               ast.While, ast.ExceptHandler)):
            cx += 1
        elif isinstance(node, ast.comprehension):
            cx += len(node.ifs)
        elif isinstance(node, ast.BoolOp):
            cx += len(node.values) - 1
        elif isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
                          ast.Mod, ast.Pow, ast.MatMult)):
            numeric = True
    params = [p for p in getattr(facts, "params", []) if p not in ("self", "cls")]
    kinds = getattr(facts, "param_kinds", {}) or {}
    guards = getattr(facts, "guards", {}) or {}
    try:
        from .hazards import _string_input_params
        str_params = set(_string_input_params(facts))
    except Exception:
        str_params = set()
    param_kinds = tuple("string" if p in str_params else kinds.get(p, "scalar")
                        for p in params)
    guarded = sum(1 for p in params if guards.get(p) not in (None, "none"))
    cov = unc = 0
    try:
        from .compendium import hazard_call_sites
        cov, unc = hazard_call_sites(fn, facts, root)
    except Exception:
        pass
    return _Profile(
        params=param_kinds, guarded=guarded, cx=cx,
        output=getattr(facts, "returns_kind", "scalar") or "none",
        numeric=numeric, loops=len(getattr(facts, "loops", []) or []),
        pure=bool(getattr(facts, "is_pure", True)),
        str_params=len(str_params), n_raises=n_raises,
        covered_calls=cov, uncovered_calls=unc)


def _clarity_sources(p: _Profile) -> list:
    """The entropy sources of one function, `(dimension, bits, reducer)`.
    `reducer` names which claim group (or structural baseline) clears it;
    `None` means irreducible (a black-box call). See `_BITS`."""
    C = _BITS
    s: list = [("identity", C["graph"] + C["region"] * p.cx, "identity")]
    s.append(("form", _EXTENT_BITS.get(p.output, 1.0), "extent"))
    s.append(("form", C["shape_branched"] if p.cx else C["shape_flat"], "shape"))
    for i, _kind in enumerate(p.params):
        if i < p.guarded:
            s.append(("domain", C["domain_guarded"], "domain"))
        else:
            s.append(("domain", C["domain_soft"], "domain_soft"))
    pur = C["safety_pure"] if p.pure else C["safety_impure"]
    s.append(("safety", pur, "safety:is_state_safe"))
    s.append(("safety", pur, "safety:is_deterministic"))
    if p.numeric:
        num = C["safety_numeric"] + C["safety_numeric_loop"] * p.loops
        s.append(("safety", num, "safety:is_numerically_stable"))
        s.append(("safety", num, "safety:is_representation_safe"))
    if any(k in ("sequence", "matrix") for k in p.params):
        s.append(("safety", C["safety_seq"], "safety:is_missing_safe"))
    for _ in range(p.str_params):
        s.append(("safety", C["safety_str"], "safety:is_arbitrary_input_safe"))
    for _ in range(p.n_raises):
        s.append(("failure", C["raise"], "raises"))
    for _ in range(p.covered_calls):
        s.append(("failure", C["hazard_covered"], "safety:is_compendium_safe"))
    for _ in range(p.uncovered_calls):
        s.append(("failure", C["hazard_uncovered"], None))
    return s


def _reductions(verified_claims, pure: bool) -> dict:
    """The fraction each reducer group has been established to, from the
    verified claims plus the structural (examine-route) baselines."""
    C = _BITS
    base_purity = C["base_pure"] if pure else C["base_impure"]
    r: dict = {
        "identity": 0.0, "extent": 0.0, "shape": 0.0, "domain": 0.0,
        "domain_soft": C["base_domain_soft"], "raises": 0.0,
        "safety:is_state_safe": base_purity,
        "safety:is_deterministic": base_purity,
        "safety:is_numerically_stable": C["base_safety"],
        "safety:is_representation_safe": C["base_safety"],
        "safety:is_missing_safe": C["base_safety"],
        "safety:is_arbitrary_input_safe": C["base_arbitrary_input"],
        # a covered library call is a hazard until is_compendium_safe is
        # verified: no structural baseline
        "safety:is_compendium_safe": 0.0,
    }

    def bump(key, val):
        if val > r.get(key, 0.0):
            r[key] = val

    for claim in verified_claims:
        name = claim.get("name") or ""
        statement = claim.get("statement") or claim.get("law") or ""
        if not statement or statement == name:       # a freshness pseudo-claim
            continue
        # an uncorroborated disproof is already downgraded to `unknown`
        # (which scores 0 below), so a `falsified` row is always witnessed
        # knowledge; this guards that invariant if it is ever violated
        if (claim.get("meta") or {}).get("mathema.corroboration") == \
                "uncorroborated":
            continue
        st = _strength(claim.get("verdict") or "", claim.get("route") or "")
        if st <= 0:
            continue
        base = name.split("[", 1)[0]
        if base in _SAFETY_SOURCE:
            bump("safety:" + _SAFETY_SOURCE[base], st)
            continue
        kind = _claim_kind(name, statement)
        if kind in _IDENTITY_KINDS:
            bump("identity", st)
        elif kind == "bound":
            bump("extent", st)
        elif kind == "partiality":
            bump("raises", st)
            bump("domain", st)                       # a raising guard IS a boundary
        elif kind == "definedness":
            bump("domain", st)
        else:                                        # the shape / relation group
            bump("shape", st)
    # entailment: knowing the exact map settles the output envelope, the
    # relational shape, and an unguarded parameter's domain
    r["extent"] = max(r["extent"], r["identity"])
    r["shape"] = max(r["shape"], r["identity"])
    r["domain_soft"] = max(r["domain_soft"], r["domain"], r["identity"])
    return r


def clarity_score(fn=None, verified_claims=None, root: str = ".",
                        facts=None) -> int | None:
    """Intent:
        The clarity score for one function, 0-100: the
        fraction of what is KNOWABLE about its behaviour that its VERIFIED
        claims pin down. It is an entropy measure, `1 - H_remaining / H0`,
        over five dimensions (what it computes, what it accepts, its
        bounds and shape, how safely it runs, where it can go wrong); each
        verified claim eliminates a share of one dimension's a-priori
        uncertainty, scaled by the mechanism that reached it. None when
        the source is unavailable (nothing to characterise); 0 when the
        source is readable but nothing is known.
    Notes:
        A dimension that CANNOT apply (a total function with no failure
        modes) carries zero entropy and drops out of the denominator, it
        is not free score. An UNCOVERED library call is irreducible (no
        compendium models where it fails), so it caps clarity below 100.
        A witnessed falsification of a LIVE claim counts as knowledge;
        a claim retired into the record's discoveries is history, and
        the score follows whatever replaced it. Structural facts the code shows
        (visible purity, an unguarded signature) count as examine-route
        evidence. Reads the COMMITTED verified store, no re-adjudication.
        The algorithm is versioned: `CLARITY_ALGO`.
    """
    if verified_claims is None:
        verified_claims = _verified_claims_for(fn, root) if fn is not None else []
    profile = _clarity_profile(fn, facts, root)
    if profile is None:
        return None
    sources = _clarity_sources(profile)
    reductions = _reductions(verified_claims, profile.pure)
    h0 = h_rem = 0.0
    for _dim, bits, reducer in sources:
        h0 += bits
        h_rem += bits * (1.0 - reductions.get(reducer, 0.0))
    if h0 <= 0:
        return 0
    return round(100 * (1.0 - h_rem / h0))


@dataclass(frozen=True)
class BadgeScores:
    """The four repo numbers plus the per-function rows behind them.
    `implementation`/`intent`/`clarity` are 0-100; `overall` is the
    radar-triangle area (0-100), the single health number CI diffs across
    commits. `per_function` maps each key to its own three scores (a
    clarity None means the function posed no question)."""
    implementation: int | None
    intent: int
    clarity: int
    overall: int | None
    per_function: dict = field(default_factory=dict)
    algo: str = CLARITY_ALGO


def _population(targets, root: str) -> dict:
    """Intent:
        The `{key: fn}` population the badges score over: every function
        defined under `targets`, or, rootwide (no targets), every
        function the declared/verified store knows. One population feeds
        all three scores and the centrality graph, so they line up.
    """
    if targets:
        from .audit import discover
        return dict(discover(list(targets)))
    from .conjecture import _resolve_func_ref
    from .spec import load_declared, load_verified
    keys = sorted(set(load_declared(root)) | set(load_verified(root)))
    out = {}
    for key in keys:
        fn = _resolve_func_ref(key)
        if fn is not None:
            out[key] = fn
    return out


def _weighted_mean(pairs: list[tuple[float, float]]) -> int:
    """A centrality-weighted mean of `(weight, score)` pairs, rounded;
    pairs with a None score are dropped by the caller. 0 when empty."""
    total_w = sum(w for w, _ in pairs)
    if total_w <= 0:
        return 0
    return round(sum(w * s for w, s in pairs) / total_w)


def triangle_area(a: float, b: float, c: float) -> int:
    """Intent:
        The overall/health number, 0-100: the fraction of the frame the
        drawn triangle SHADES, so half the triangle shaded reads 50. With
        clarity (c) the apex height and implementation (a) and intent (b)
        the base, that area is `clarity * (implementation + intent) / 2`
        on the 0-1 fractions: 100 when all three are 100, and 0 whenever
        clarity is 0 (a flat, zero-height shape) or both base scores are.
    """
    fa, fb, fc = a / 100.0, b / 100.0, c / 100.0
    return round(100 * fc * (fa + fb) / 2.0)


def repo_badges(targets=None, root: str = ".",
                implementation: bool = True) -> BadgeScores:
    """Intent:
        Compute the badges over the population. Implementation is the raw
        repo line ratio of the test-union-probe-union-derive coverage (no
        averaging, no centrality); intent and clarity are
        centrality-weighted means of their per-function scores. `overall`
        is the triangle area. `implementation=False` SKIPS the coverage
        pass entirely: the implementation score and `overall` come back
        None (nothing is output for them), it does not fall back to a
        cheaper, different number.
    Notes:
        Implementation is the real union of all three sources, so it
        re-runs `check()` (under line tracing) for a function whose lines
        the tests do not already fully cover; a function a FRESH report
        fully covers is short-circuited (its union already equals its
        statement set, so the traced pass is provably redundant and
        skipped), keeping the identical number at lower cost. A stale
        report's lines never count (`inventory.coverage_freshness`).
        Clarity reads the
        committed verified store (no re-adjudication) and is recorded with
        its algorithm version in `algo` (`CLARITY_ALGO`). A clarity
        None (source unavailable) drops out of the clarity roll-up.
    """
    from .centrality import centrality_weights
    from .docstring import docstring_sync
    from .impl_coverage import (_external_lines, _line_range,
                                _statement_lines, function_coverage)
    from .inventory import coverage_freshness, read_test_coverage
    from .spec import load_verified

    functions = _population(targets, root)
    weights = centrality_weights(functions)
    verified = load_verified(root)
    coverage_data = read_test_coverage(root) if implementation else None
    freshness = coverage_freshness(root) if implementation else None

    covered_lines = statement_lines = 0
    intent_pairs: list[tuple[float, float]] = []
    behav_pairs: list[tuple[float, float]] = []
    per_function: dict = {}
    for key, fn in functions.items():
        w = weights.get(key, 1.0)
        impl = None
        if implementation:
            stmts = _statement_lines(fn)
            test_cov = _external_lines(fn, coverage_data) & stmts
            rng = _line_range(fn)
            fresh = rng is not None and not freshness.is_stale(rng[0])
            if stmts and fresh and not (stmts - test_cov):
                covered, statements = stmts, stmts   # fresh tests cover it all
            else:
                fc = function_coverage(fn, root=root,
                                       coverage_data=coverage_data,
                                       freshness=freshness)
                covered = fc.covered & fc.statements
                statements = fc.statements
            covered_lines += len(covered)
            statement_lines += len(statements)
            impl = (round(100 * len(covered) / len(statements))
                    if statements else 100)
        intent = docstring_sync(fn, root=root).percent
        intent_pairs.append((w, intent))
        claims = (verified.get(key) or {}).get("entry", {}).get("claims") or []
        behav = clarity_score(fn, verified_claims=claims, root=root)
        if behav is not None:
            behav_pairs.append((w, behav))
        per_function[key] = {"implementation": impl,
                             "intent": intent, "clarity": behav}

    intent = _weighted_mean(intent_pairs)
    clarity = _weighted_mean(behav_pairs)
    if implementation:
        impl_score = (round(100 * covered_lines / statement_lines)
                      if statement_lines else 100)
        overall = triangle_area(impl_score, intent, clarity)
    else:
        impl_score = overall = None
    return BadgeScores(implementation=impl_score, intent=intent,
                       clarity=clarity, overall=overall,
                       per_function=per_function)


# --- the radar triangle -----------------------------------------------
# A fixed integer canvas so the same scores always render the same bytes
# (clean git diffs). The frame is the sharp full 100/100/100 triangle,
# CLARITY at the top apex, IMPL and INTENT the two bottom nodes, with
# exact 45-degree edges so each side is one dot per row (no doubling).
# Each score grows from the bottom centre (all-zero) out to its corner,
# and the triangle those three dots span is filled with dots: the filled
# area is the state, the gap to the frame the room to grow.
_TRI_SIZE = 14
_ORDER = ("CLARITY", "IMPL", "INTENT")
_DOT, _CORNER, _CENTRE, _MARK = "·", "◆", "+", "●"


def _corner_xy(size: int) -> dict:
    """The three frame corners on a `2*size+1` by `size+1` grid: CLARITY
    at the top apex, IMPL bottom-left, INTENT bottom-right."""
    return {"CLARITY": (size, 0), "IMPL": (0, size), "INTENT": (2 * size, size)}


def _inside(x: float, y: float, tri) -> bool:
    (ax, ay), (bx, by), (cx, cy) = tri

    def sign(px, py, qx, qy, rx, ry):
        return (px - rx) * (qy - ry) - (qx - rx) * (py - ry)

    d1 = sign(x, y, ax, ay, bx, by)
    d2 = sign(x, y, bx, by, cx, cy)
    d3 = sign(x, y, cx, cy, ax, ay)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def render_triangle(a: int, b: int, c: int) -> str:
    """Intent:
        The radar for scores (implementation a, intent b, clarity c), each
        0-100: the sharp dotted outer triangle is the full 100/100/100
        frame, CLARITY at the apex and IMPL/INTENT the bottom nodes; each
        score is a dot on its spoke from the bottom centre (all-zero) out
        to its corner, and the triangle those three dots span is filled
        with dots, so the filled area is the current state and the gap to
        the frame is the room to grow. The three scores label the corners
        and the overall area sits below. If any score is under 5 the shape
        is degenerate and is not drawn, only the numbers are shown.
    """
    overall = triangle_area(a, b, c)
    scores = {"IMPL": a, "INTENT": b, "CLARITY": c}
    if min(a, b, c) < 5:
        return (f"IMPL {a}   INTENT {b}   CLARITY {c}   overall {overall}\n"
                "(no triangle: a dimension is below 5%)")
    size = _TRI_SIZE
    w, h = 2 * size + 1, size + 1
    grid = [[" "] * w for _ in range(h)]

    def put(x, y, ch, over=False):
        if 0 <= y < h and 0 <= x < w and (over or grid[y][x] == " "):
            grid[y][x] = ch

    corners = _corner_xy(size)
    for y in range(h):                              # the two sharp 45-deg edges
        put(size - y, y, _DOT)
        put(size + y, y, _DOT)
    for x in range(w):                              # the dotted base
        put(x, size, _DOT)
    for name, (x, y) in corners.items():
        put(x, y, _CORNER, over=True)
    origin = (size, size)                           # all-zero sits at the base
    put(origin[0], origin[1], _CENTRE, over=True)
    inner = {}
    for name in _ORDER:
        f = max(0.0, min(1.0, scores[name] / 100.0))
        cx, cy = corners[name]
        inner[name] = (origin[0] + f * (cx - origin[0]),
                       origin[1] + f * (cy - origin[1]))
    tri = [inner[n] for n in _ORDER]
    for y in range(h):                              # fill the score triangle
        for x in range(w):
            if grid[y][x] == " " and _inside(x, y, tri):
                put(x, y, _DOT)
    for name in _ORDER:                             # the score vertices on top
        put(round(inner[name][0]), round(inner[name][1]), _MARK, over=True)
    rows = ["".join(row).rstrip() for row in grid]
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    body = "\n".join(rows)
    return (f"        CLARITY {c}\n{body}\n"
            f"  IMPL {a}{' ' * 11}INTENT {b}\n"
            f"        overall {overall}")


# --- emission ---------------------------------------------------------
# Distinct brand colors, one per layer; the overall badge scales its
# color with the value so a glance reads health.
_BADGE_COLOR = {"implementation": "#1f6feb",     # blue  (code)
                "intent": "#2da44e",             # green (spec)
                "clarity": "#8250df"}            # purple (clarity)
_BADGE_LABEL = {"implementation": "implementation",
                "intent": "intent",
                "clarity": "clarity"}


def _value_color(pct: int) -> str:
    if pct >= 80:
        return "#2da44e"
    if pct >= 60:
        return "#bf8700"
    if pct >= 40:
        return "#d1741f"
    return "#cf222e"


def shields_payloads(scores: BadgeScores) -> dict:
    """The three shields.io endpoint payloads (`schemaVersion`/`label`/
    `message`/`color`), keyed implementation/intent/clarity.
    Each renders as a badge a README references by its raw URL."""
    out = {}
    for dim in ("implementation", "intent", "clarity"):
        out[dim] = {"schemaVersion": 1, "label": _BADGE_LABEL[dim],
                    "message": f"{getattr(scores, dim)}%",
                    "color": _BADGE_COLOR[dim]}
    return out


def _svg_score_point(origin, corner, score):
    """A score's point on its spoke from `origin` (all-zero) out to its
    frame `corner`, the SVG twin of the ASCII spoke placement."""
    f = max(0.0, min(1.0, score / 100.0))
    return (origin[0] + f * (corner[0] - origin[0]),
            origin[1] + f * (corner[1] - origin[1]))


def _blend_fill(intent: int, clarity: int, implementation: int) -> tuple:
    """The inner fill colour is the three scores AS a colour: red is
    intent, green is clarity, blue is implementation, each 0-100 mapped
    onto 0-255. All three high reads near white, all low near black, and
    a lopsided profile takes on the colour of its strongest layer.
    Returns `(hex, text_colour)`, the text picked for contrast by
    luminance so the overall number stays legible on the fill."""
    r = round(255 * max(0, min(100, intent)) / 100)
    g = round(255 * max(0, min(100, clarity)) / 100)
    b = round(255 * max(0, min(100, implementation)) / 100)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return f"#{r:02x}{g:02x}{b:02x}", ("#111111" if lum > 140 else "#ffffff")


def render_svg(scores: BadgeScores) -> str:
    """A colored twin of the ASCII triangle, same layout so the two read
    alike: CLARITY at the apex, IMPL and INTENT the bottom nodes, the full
    100/100/100 triangle as a faint frame, and each score a vertex on its
    spoke from the bottom centre (all-zero) out to its corner, with the
    triangle they span filled. The fill colour encodes the scores: red
    intent, green clarity, blue implementation. For a slicker README embed
    than the ASCII (whose job is the git diff)."""
    w, h = 360, 300
    apex = (180.0, 64.0)          # CLARITY, top
    left = (56.0, 246.0)          # IMPL, bottom-left
    right = (304.0, 246.0)        # INTENT, bottom-right
    origin = (180.0, 246.0)       # all-zero sits at the base centre
    frame = {"CLARITY": apex, "IMPL": left, "INTENT": right}
    dims = (("CLARITY", "clarity", scores.clarity),
            ("IMPL", "implementation", scores.implementation),
            ("INTENT", "intent", scores.intent))
    fill, text_color = _blend_fill(scores.intent, scores.clarity,
                                   scores.implementation)
    ghost = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in (apex, left, right))
    pts = {name: _svg_score_point(origin, frame[name], sc)
           for name, _, sc in dims}
    cur = " ".join(f"{pts[n][0]:.1f},{pts[n][1]:.1f}"
                   for n in ("CLARITY", "IMPL", "INTENT"))
    ctr = (sum(p[0] for p in pts.values()) / 3.0,
           sum(p[1] for p in pts.values()) / 3.0 + 5)
    font = ("system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,"
            "Arial,sans-serif")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{font}">',
        # a self-contained light card, so the badge reads on any README
        # theme without depending on external CSS or fonts
        f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="14" '
        'fill="#ffffff" stroke="#d0d7de"/>',
        # the full 100/100/100 frame: a faint dashed triangle with open
        # corner pips, the room to grow
        f'<polygon points="{ghost}" fill="none" stroke="#afb8c1" '
        'stroke-dasharray="2 5" stroke-width="1.25"/>',
    ]
    for p in (apex, left, right):
        parts.append(f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="3" '
                     'fill="none" stroke="#afb8c1" stroke-width="1.25"/>')
    parts.append(f'<polygon points="{cur}" fill="{fill}" stroke="#57606a" '
                 'stroke-width="1.5" stroke-linejoin="round"/>')
    label_pos = {"CLARITY": (apex[0], apex[1] - 14, "middle"),
                 "IMPL": (left[0] - 10, left[1] + 26, "start"),
                 "INTENT": (right[0] + 10, right[1] + 26, "end")}
    for name, layer, sc in dims:
        vx, vy = pts[name]
        color = _BADGE_COLOR[layer]
        parts.append(f'<line x1="{origin[0]:.0f}" y1="{origin[1]:.0f}" '
                     f'x2="{frame[name][0]:.1f}" y2="{frame[name][1]:.1f}" '
                     f'stroke="{color}" stroke-width="1" opacity="0.3"/>')
        parts.append(f'<circle cx="{vx:.1f}" cy="{vy:.1f}" r="5.5" '
                     f'fill="{color}"/>')
        lx, ly, anchor = label_pos[name]
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" fill="{color}" '
                     f'font-size="14" font-weight="600" '
                     f'text-anchor="{anchor}">{name} {sc}</text>')
    # the overall (shaded-area) number, at the filled triangle's centroid
    # so it always sits on the fill, coloured for contrast against it
    parts.append(f'<text x="{ctr[0]:.1f}" y="{ctr[1]:.1f}" fill="{text_color}" '
                 f'font-size="17" font-weight="700" text-anchor="middle">'
                 f'{scores.overall}%</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def ci_snapshot(scores: BadgeScores) -> dict:
    """A machine-readable snapshot for CI: the four repo numbers plus the
    per-function rows, so a job can compute and comment the area delta
    between two commits. `clarity_algo` records the clarity algorithm
    version, so a diff across a version bump reads as an algorithm change,
    not a regression."""
    return {"implementation": scores.implementation,
            "intent": scores.intent,
            "clarity": scores.clarity,
            "overall": scores.overall,
            "clarity_algo": scores.algo,
            "per_function": scores.per_function}


# The standard, documented home for the written badge artifacts, under
# the tracked `.mathema/` so a README can embed `triangle.svg` by its
# in-repo path. `mathema badges --out` writes here by default.
DEFAULT_BADGE_DIR = ".mathema/badges"


# the extensions mathema's badge directory holds: it OWNS them, so one
# left behind by a rename (behavioural.json outliving the clarity
# rename) is pruned rather than served forever. A git-diff CI guard
# cannot catch a stale badge on its own, because nothing writes the
# file any more; a prune turns it into a visible deletion
_OWNED_BADGE_SUFFIXES = (".json", ".svg", ".txt", ".md")


def write_badges(scores: BadgeScores, out_dir: str) -> "tuple[list, list]":
    """Write the badge artifacts under `out_dir`: `triangle.txt` (the
    ASCII triangle), one shields JSON per badge, `triangle.svg`,
    `snapshot.json`, and `readme-snippet.md` (a paste-ready block for a
    consumer's README).

    mathema OWNS this directory: any badge-shaped file it did not write
    this run is deleted, so a renamed or retired badge cannot go on
    being served from a stale file. Files with other extensions, and
    anything in a subdirectory, are left alone. Returns
    `(written, pruned)` paths, so the removal is never silent.
    """
    import json
    import os
    os.makedirs(out_dir, exist_ok=True)
    written = []

    def _put(name, text):
        path = os.path.join(out_dir, name)
        with open(path, "w") as fh:
            fh.write(text)
        written.append(path)

    _put("triangle.txt", render_triangle(scores.implementation, scores.intent,
                                         scores.clarity) + "\n")
    for dim, payload in shields_payloads(scores).items():
        _put(f"{dim}.json", json.dumps(payload, indent=2) + "\n")
    _put("triangle.svg", render_svg(scores) + "\n")
    _put("snapshot.json", json.dumps(ci_snapshot(scores), indent=2) + "\n")
    _put("readme-snippet.md", readme_snippet())

    keep = {os.path.abspath(p) for p in written}
    pruned = []
    for name in sorted(os.listdir(out_dir)):
        path = os.path.join(out_dir, name)
        if (os.path.isfile(path) and name.endswith(_OWNED_BADGE_SUFFIXES)
                and os.path.abspath(path) not in keep):
            os.remove(path)
            pruned.append(path)
    return written, pruned


_DOCS = "https://github.com/tetrionlabs/mathema/blob/main/docs/modes/badges.md"
_MEANINGS = (
    ("implementation", "how much of the code's behaviour is covered by "
                       "tests, probes, or proofs", "#the-three-badges"),
    ("intent", "how much of what the code is meant to do is explicitly "
               "specified", "#the-three-badges"),
    ("clarity", "how much of the code's knowable behaviour is made "
                "explicit and unambiguous", "#how-clarity-is-scored"),
)


def readme_snippet() -> str:
    """A paste-ready README block: the three shields, the triangle, and
    what each score means, each linking to the section of the badge docs
    that defines it. The shields read the committed JSON by raw URL, so
    the consumer substitutes OWNER/REPO once."""
    raw = ("https://raw.githubusercontent.com/OWNER/REPO/main/"
           ".mathema/badges")
    shields = " ".join(
        f"![{dim}](https://img.shields.io/endpoint?url={raw}/{dim}.json)"
        for dim, _why, _anchor in _MEANINGS)
    rows = "\n".join(f"| [{dim}]({_DOCS}{anchor}) | {why} |"
                      for dim, why, anchor in _MEANINGS)
    return (f"{shields}\n\n"
            "<!-- substitute OWNER/REPO above; the badges read the JSON "
            "committed under .mathema/badges/ -->\n\n"
            "![mathema triangle](.mathema/badges/triangle.svg)\n\n"
            "| score | what it measures |\n|---|---|\n"
            f"{rows}\n\n"
            f"[mathema]({_DOCS}): know what your code actually does\n")
