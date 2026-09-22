# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The strict "mathema docstring": a second, opinionated docstring
convention (alongside the loose best-practice checklist
`inventory.docstring_quality()` scores) where a function's own docstring
becomes the complete authoring surface for intent, domain, and claims,
no separate YAML file or decorator required.

    def ema(x: list, alpha: float) -> float:
        # Exponentially weighted moving average.
        #
        # Intent:
        #     Blends each new value with the running mean.
        #
        # Domain:
        #     alpha: (0, 1]
        #
        # Claims:
        #     bounded: for x in [0, 1], f(x) <= 1
        ...

`Claims:` is unchanged, see `authoring.parse_docstring_claims()`. Scalar
and shape typing lives in the signature's `Annotated` hints; see
`types.py`; `domain_from_signature()` already
merges it into `check()`'s domain resolution, so it needs no separate
wiring here. `Domain:` is for a bound that isn't one of the established
markers, most commonly a fold's own accumulator/item name, which is
never a signature parameter at all (see `symbolic.try_prove_fold()`'s use
of it).

Symbol coverage (every real parameter and every loop/comprehension bind
target named somewhere in the docstring) exists to feed the derive route,
not primarily for human readability: a name with no declared range gives
`try_prove_fold()` nothing to work with when sympy needs a sign/range
assumption to resolve an otherwise-ambiguous simplification. Ordinary
scratch locals (a running total's initial value, an indexing-only loop
counter) are exempt, only names whose range could plausibly matter to a
proof are required.
"""
from __future__ import annotations

import ast
import inspect
import os
import re
from dataclasses import dataclass, field

from .analysis import _parse_notes, _read_block
from .authoring import parse_docstring_claims

_INTENT_HEADER = "intent:"
_CLAIMS_HEADER = "claims:"

_DOMAIN_LINE = re.compile(r"^\s*(?P<name>[A-Za-z_]\w*)\s*:\s*(?P<expr>.+?)\s*$")


def _parse_intent(doc: str) -> tuple[str | None, list[str]]:
    """The `Intent:` block's prose, joined into one string, or `None` if
    there's no such block at all. A block present but empty is a real
    authoring mistake (an error), distinct from the block simply being
    absent (not an error, just a missed criterion)."""
    lines = _read_block(doc, _INTENT_HEADER)
    if lines is None:
        return None, []
    text = " ".join(line.strip() for line in lines).strip()
    if not text:
        return None, ["Intent: header present but empty"]
    return text, []


def _bound_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        out: set[str] = set()
        for elt in target.elts:
            out |= _bound_names(elt)
        return out
    return set()


def _required_symbols(facts) -> set[str]:
    """Every real parameter plus every `for`/comprehension bind target;
    the names whose *range* could plausibly matter to a proof (see the
    module docstring). A `while` loop's test expression binds nothing new,
    so it contributes no names; ordinary local assignments are never
    included, only loop/comprehension targets."""
    required = {p for p in facts.params if p not in ("self", "cls")}
    if facts.tree is None:
        return required
    for node in ast.walk(facts.tree):
        if isinstance(node, ast.For):
            required |= _bound_names(node.target)
        elif isinstance(node, ast.comprehension):
            required |= _bound_names(node.target)
    return required


@dataclass
class MathemaDocstring:
    """The result of parsing a function's docstring against the strict
    mathema-docstring schema. `domain` is the `Domain:` block's own
    contribution only (established `Types:` markers are a separate
    concern, see `types.py`, already merged into
    `domain_from_signature()`). `score`/`applicable` follow the same
    "N/M" pattern `inventory.docstring_quality()` uses. `conforms` is
    `True` only when there are zero structural `errors` and every
    applicable criterion is met; a low score with no errors just means
    "incomplete," while any error means something written doesn't parse
    at all. `notes` (from an optional `Notes:` block, limitations or
    design rationale) is carried through but never scored: absence is
    fine, unlike `intent`'s absence."""
    intent: str | None
    claims: list[dict]
    symbols_required: set
    symbols_documented: set
    score: int
    applicable: int
    conforms: bool
    errors: list[str] = field(default_factory=list)
    notes: str | None = None


def _claim_stated_domain(parsed) -> dict:
    """Every bound the docstring's own claims quantify over, the
    canonical place a domain is stated, so "did this declare its
    domain?" is answered from the claims rather than from a parallel
    block that nothing adjudicates."""
    from .conjecture import claim as _claim

    merged: dict = {}
    for row in (parsed.claims or []):
        law = row.get("statement") or row.get("law") if isinstance(row, dict) else row
        if not law:
            continue
        try:
            cj = _claim(law)
        except Exception:
            continue
        for name, bound in (cj.domain or {}).items():
            merged.setdefault(name, bound)
    return merged

def parse_mathema_docstring(fn) -> MathemaDocstring:
    """Parse `fn`'s docstring against the strict mathema-docstring schema:
    `Intent:`, `Domain:`, `Claims:`, plus symbol coverage. Never raises,
    an unparseable docstring just scores low and lists why in `errors`."""
    import warnings

    from .analysis import SourceUnavailable, analyze_source

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            facts = analyze_source(fn)
        except SourceUnavailable:
            facts = None

    doc = (facts.docstring if facts is not None else inspect.getdoc(fn)) or ""

    intent, intent_errors = _parse_intent(doc)
    from .types import matrix_param_names
    claims = parse_docstring_claims(
        doc, matrix_param_names(fn) if fn is not None else frozenset())
    notes = _parse_notes(doc)

    claim_errors = []
    has_claims_header = bool(re.search(r"^\s*claims:\s*$", doc, re.I | re.M))
    if has_claims_header and not claims:
        claim_errors.append("Claims: header present but nothing valid parsed")

    required = _required_symbols(facts) if facts is not None else set()
    documented = {name for name in required if re.search(rf"\b{re.escape(name)}\b", doc)}
    missing = required - documented
    coverage_errors = [f"{name!r} used but not documented" for name in sorted(missing)]

    errors = intent_errors + claim_errors + coverage_errors

    score, applicable = 0, 0
    applicable += 1
    score += int(bool(intent))
    applicable += 1
    score += int(bool(claims))
    if required:
        applicable += 1
        score += int(not missing)

    conforms = not errors and score == applicable

    return MathemaDocstring(intent=intent, claims=claims,
                            symbols_required=required, symbols_documented=documented,
                            score=score, applicable=applicable, conforms=conforms,
                            errors=errors, notes=notes)


@dataclass
class DocstringSync:
    """How well a function's docstring stays in sync with its own code
    structure and its verified spec record, distinct from the loose
    `docs` checklist (which only checks the docstring against itself)
    and from `parse_mathema_docstring()`'s own bare structural parse
    (which this wraps as `.parsed` and extends). `score`/`applicable`
    start from `parsed.score`/`.applicable` (Intent/Claims/symbol
    coverage) and add one numerator/denominator pair per dimension
    below that's actually applicable to this function, same
    per-item granularity as `inventory.docstring_quality()`'s own
    params/raises scoring, not an all-or-nothing point each.

    `claims_floor`/`claims_actual`/`claims_expected` are deliberately
    NOT part of `score`/`applicable`. The floor is the least this
    function's shape gives you to state (`inventory.claim_floor`), the
    actual is the larger of the docstring's own claim count and the
    verified record's, and the expected, how many a function of this
    shape typically carries; needs a corpus and is None until one
    exists. Reported so a real coverage gap is visible without being
    enforced as a requirement a legitimately simple function would
    fail."""
    parsed: MathemaDocstring
    raises_covered: int
    raises_total: int
    domain_declared: int
    domain_declarable: int
    domain_enforced: bool | None       # None: nothing declared, not applicable
    params_typed: int
    params_typeable: int
    return_typed: bool | None          # None: no meaningful return, not applicable
    # the callee dimension, split: quality (the callee documents
    # itself; docstring plus a documented return) and docsync (the
    # mean of the callees' own shallow sync percentages, shallow =
    # computed without THEIR callee dims, so a call cycle can't loop
    # and a hop only ever counts once)
    callee_funcs_documented: int
    callee_sync_percent: int | None
    callee_funcs_total: int
    claims_floor: int                  # informational only, see above
    claims_actual: int                 # informational only, see above
    claims_expected: int | None = None # None until a corpus predicts it
    intent_concise: bool | None = None
    # the sync dimensions: the docstring against the OTHER layers,
    # claims_in_sync (block names known, zero surface conflicts),
    # intent_in_sync (declared file agrees with the docstring, which
    # wins by design), record_stale (the verified record's form no
    # longer matches the live code; its contribution here is dated).
    # None = not applicable, per the same convention as every field.
    claims_in_sync: bool | None = None
    intent_in_sync: bool | None = None
    record_stale: bool | None = None
    # None: no intent stated, not applicable. Scored: an overlong
    # intent (> 40 words) costs the point; concise intent is the
    # convention's whole value at this level.
    intent_context: dict = field(default_factory=dict)
    # informational only, never scored: the intent hierarchy around
    # this function ({"function", "module", "readme"} -> str | None,
    # see intent_context()); context is reported, never inherited,
    # so a function missing its own Intent: still shows as a gap even
    # when its module or README states one.
    # 0-100: how much of what the function actually does is surfaced
    # as context a developer can read (intent at every level, domains,
    # raise conditions, types, the immediate call surface);
    # deliberately not proveability, which is the claim floor flag's
    # own job; renormalized over whichever components apply
    percent: int = 0
    score: int = 0
    applicable: int = 0
    conforms: bool = False
    errors: list[str] = field(default_factory=list)




def _guard_raise_names(facts, merged_domain: dict) -> set:
    """Intent:
        Exception names raised by a parameter's own domain guard, an
        `if <param compares literal>: raise X(...)` whose parameter has
        a DECLARED domain. The declaration plus the boundary check is a
        formal statement of when the function raises, so the raises
        dimension counts it as covered.
    """
    import ast as _ast
    if facts is None or facts.tree is None or not merged_domain:
        return set()
    out: set = set()
    for node in _ast.walk(facts.tree):
        if not isinstance(node, _ast.If):
            continue
        names = {n.id for n in _ast.walk(node.test)
                 if isinstance(n, _ast.Name)}
        if not names or not names <= set(merged_domain):
            continue
        for stmt in node.body:
            if isinstance(stmt, _ast.Raise) and stmt.exc is not None:
                exc = stmt.exc
                if isinstance(exc, _ast.Call):
                    exc = exc.func
                if isinstance(exc, _ast.Name):
                    out.add(exc.id)
    return out

def docstring_sync(fn, root: str = ".", *, declared: dict | None = None,
                   verified: dict | None = None,
                   claims_floor: int | None = None,
                   sync_cache: dict | None = None,
                   _shallow: bool = False) -> DocstringSync:
    """`fn`'s docstring measured against its own code structure and
    verified spec record, not just against itself. Callee resolution
    (`callee_funcs_*`) covers DIRECT callees only: an undocumented
    central helper already dings every caller's own row, so a deeper
    walk mostly double-counts a per-function sweep, and its extra
    signal is invisible in a single report anyway (run the report on
    the callee to see its closure). Never raises.

    `declared`/`verified` accept the stores preloaded (load_declared/
    load_verified) so a population sweep parses the YAML once, not
    once per function."""
    import warnings

    from .analysis import SourceUnavailable, analyze_source
    from .authoring import _fn_key
    from .grammar import parse_raises
    from .inventory import _raised_exception_names, docstring_quality
    from .spec import load_verified
    from .types import domain_from_signature

    parsed = parse_mathema_docstring(fn)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            facts = analyze_source(fn)
        except SourceUnavailable:
            facts = None

    doc = (facts.docstring if facts is not None else inspect.getdoc(fn)) or ""
    real_params = [p for p in (facts.params if facts is not None else [])
                   if p not in ("self", "cls")]

    try:
        sig = inspect.signature(fn)
        annotated_params = {n for n, p in sig.parameters.items()
                            if p.annotation is not inspect.Parameter.empty}
        return_annotated = sig.return_annotation is not inspect.Signature.empty
    except (ValueError, TypeError):
        annotated_params, return_annotated = set(), False

    score, applicable = parsed.score, parsed.applicable

    # --- intent conciseness: a concise intent is the useful kind -------
    # (it stays readable in a record, and doubles as agent context),
    # scored only when an intent exists at all; the threshold is a
    # judgment call, wide enough that two ordinary sentences pass.
    intent_concise = None
    if parsed.intent:
        intent_concise = len(parsed.intent.split()) <= 40
        applicable += 1
        score += int(intent_concise)

    # Where a domain is actually stated: a claim's own quantifier. The
    # docstring `Domain:` block used to sit here too and was removed;
    # measured at 0 real uses across a 313-file corpus, against 96% of
    # claims carrying an inline quantifier, and it was a second,
    # never-adjudicated declaration that could silently disagree with
    # the claims beneath it. The signature markers remain, though they
    # are only three sentinels (Probability/Positive/Nonnegative) with
    # fixed intervals.
    merged_domain = {**domain_from_signature(fn), **_claim_stated_domain(parsed)}

    # --- raises: claim-first (raises(f(x), ExcType)), prose fallback,
    # and a guard raise ENFORCING a declared domain counts too, the
    # declaration plus its own boundary check states the raise
    # condition as formally as prose would --------------------------------
    raised = _raised_exception_names(facts.tree) if facts is not None and facts.tree is not None else []
    claimed_raises = set()
    for c in parsed.claims:
        result = parse_raises(c.get("statement", ""))
        if result is not None and result[1]:
            claimed_raises.add(result[1])
    guard_raised = (_guard_raise_names(facts, merged_domain)
                    if facts is not None else set())
    raises_covered = sum(1 for name in raised if name in claimed_raises
                         or re.search(rf"\b{re.escape(name)}\b", doc)
                         or name in guard_raised)
    raises_total = len(raised)
    if raises_total:
        applicable += raises_total
        score += raises_covered

    # --- domain: declared (signature markers ∪ docstring Domain:) and,
    # only when something is, actually enforced at runtime -----------------
    scalar_params = [p for p in real_params
                     if facts is not None and facts.param_kinds.get(p) in ("scalar", "int")]
    domain_declarable = len(scalar_params)
    domain_declared = sum(1 for p in scalar_params if p in merged_domain)
    if domain_declarable:
        applicable += domain_declarable
        score += domain_declared
    domain_enforced = None
    if domain_declared:
        domain_enforced = hasattr(fn, "__mathema_enforced_domain__")
        applicable += 1
        score += int(domain_enforced)

    # --- type coverage: real parameters, internal loop/comprehension
    # variables, and the return value ---------------------------------------
    def _has_type_info(name: str) -> bool:
        return name in merged_domain or name in annotated_params

    params_typeable = len(real_params)
    params_typed = sum(1 for p in real_params if _has_type_info(p))
    if params_typeable:
        applicable += params_typeable
        score += params_typed

    return_typed = None
    if facts is not None and facts.returns_kind not in ("none", "unknown"):
        return_typed = return_annotated
        applicable += 1
        score += int(return_typed)

    # --- callees: do the functions this one DIRECTLY calls document
    # themselves; the one-hop closure; deeper hops belong to the
    # callees' own rows -----------------------------------------------
    callees: list = []
    if facts is not None:
        seen_ids = {id(fn)}
        g = getattr(fn, "__globals__", {})
        for name in facts.global_funcs:
            obj = g.get(name)
            if obj is None or not inspect.isfunction(obj) \
                    or id(obj) in seen_ids:
                continue
            seen_ids.add(id(obj))
            callees.append(obj)
    callee_funcs_total = len(callees)
    if verified is None:
        verified = load_verified(root)
    if declared is None:
        from .spec import load_declared
        declared = load_declared(root)
    callee_funcs_documented = 0
    callee_sync_percent = None
    if _shallow:
        callees = []
        callee_funcs_total = 0
    if callees:
        from .authoring import _fn_key as _key_of
        sync_cache = sync_cache if sync_cache is not None else {}
        percents = []
        for c in callees:
            sq = docstring_quality(c)
            if sq["has_docstring"] and sq["documents_return"] is not False:
                callee_funcs_documented += 1
            ck = _key_of(c)
            cached = sync_cache.get(ck)
            if cached is None:
                cached = docstring_sync(c, root, declared=declared,
                                        verified=verified,
                                        sync_cache=sync_cache,
                                        _shallow=True)
                sync_cache[ck] = cached
            percents.append(cached.percent)
        callee_sync_percent = round(sum(percents) / len(percents))
        applicable += callee_funcs_total
        score += callee_funcs_documented

    # --- the SYNC dimensions: the docstring measured against the
    # other layers, not just against itself ---------------------------
    key = _fn_key(fn)
    rec = verified.get(key)
    verified_entry = (rec or {}).get("entry") or {}
    file_entry = (declared.get(key) or {}).get("entry", {})

    claims_in_sync = None
    if re.search(r"^\s*claims:\s*$", doc, re.I | re.M):
        from .sync import claim_conflicts, docstring_drift
        conflicts = claim_conflicts(fn, file_entry)
        from .authoring import retrieve
        merged = retrieve(fn, root)
        drift = docstring_drift(fn, merged, verified_entry)
        unknown = any(d["kind"] == "unknown-in-docstring" for d in drift)
        claims_in_sync = not conflicts and not unknown
        applicable += 1
        score += int(claims_in_sync)

    intent_in_sync = None
    file_intent = (file_entry.get("intent") or "").strip()
    if parsed.intent and file_intent:
        # the docstring wins by design; a differing declared-file
        # intent is drift a docsync run resolves
        intent_in_sync = " ".join(parsed.intent.split()) == \
            " ".join(file_intent.split())
        applicable += 1
        score += int(intent_in_sync)

    # the record contribution's freshness: a stale record (form
    # mismatch) is flagged, never silently used as truth
    record_stale = None
    if verified_entry:
        recorded_form = (verified_entry.get("identity") or {}).get("form")
        live_form = getattr(facts, "form", None) if facts is not None \
            else None
        if recorded_form and live_form:
            record_stale = recorded_form != live_form

    # --- the claim triplet: informational only, never scored --------------
    if claims_floor is None:
        from .inventory import claim_floor as _claim_floor
        floor_report = _claim_floor(fn, facts)
        claims_floor = floor_report["floor"] if floor_report else 0
    verified_claim_count = len(verified_entry.get("claims") or [])
    try:
        from .authoring import retrieve as _retrieve
        declared_claim_count = len(_retrieve(fn, root).get("claims") or [])
    except Exception:
        declared_claim_count = 0
    claims_actual = max(len(parsed.claims), verified_claim_count,
                        declared_claim_count)

    conforms = not parsed.errors and score == applicable

    # the weighted 0-100 measure: (weight, value-in-[0,1], applicable),
    # renormalized over whichever components this function has at all.
    # What it measures: how much of what the function actually does is
    # surfaced as context a developer can read, intent at every
    # level, domains, raise conditions, types, and the same for the
    # immediate call surface. Deliberately NOT proveability: whether
    # the claims themselves are enough is the claim floor's own flag
    # (rendered beside the triplet, never folded in here), and domain
    # ENFORCEMENT already shows up through the raise-coverage rule (a
    # guard enforcing a declared domain covers its exception), so
    # neither is a separate component.
    ctx = intent_context(fn, root=root)
    intent_words = len(parsed.intent.split()) if parsed.intent else 0
    # conciseness as a ramp, not a cliff: full credit through 40
    # words, fading linearly to zero by 80
    concise_value = (1.0 if intent_words <= 40
                     else max(0.0, 1.0 - (intent_words - 40) / 40.0))
    components = [
        (12, float(bool(claims_in_sync)), claims_in_sync is not None),
        (16, float(bool(parsed.intent)), True),
        (5, concise_value, parsed.intent is not None),
        (5, float(bool(intent_in_sync)), intent_in_sync is not None),
        (5, float(bool((ctx.get("module") or {}).get("text"))), True),
        (3, float(bool((ctx.get("readme") or {}).get("text"))), True),
        (15, (domain_declared / domain_declarable
              if domain_declarable else 0.0), domain_declarable > 0),
        (12, (raises_covered / raises_total if raises_total else 0.0),
         raises_total > 0),
        (10, (params_typed / params_typeable if params_typeable else 0.0),
         params_typeable > 0),
        (4, float(bool(return_typed)), return_typed is not None),
        (5, (callee_funcs_documented / callee_funcs_total
             if callee_funcs_total else 0.0), callee_funcs_total > 0),
        (8, ((callee_sync_percent or 0) / 100.0),
         callee_sync_percent is not None),
    ]
    live = [(w, v) for w, v, applies in components if applies]
    total_w = sum(w for w, _v in live)
    percent = round(100 * sum(w * v for w, v in live) / total_w)         if total_w else 0

    return DocstringSync(
        parsed=parsed, raises_covered=raises_covered, raises_total=raises_total,
        domain_declared=domain_declared, domain_declarable=domain_declarable,
        domain_enforced=domain_enforced, params_typed=params_typed,
        params_typeable=params_typeable, return_typed=return_typed,
        callee_funcs_documented=callee_funcs_documented,
        callee_sync_percent=callee_sync_percent,
        callee_funcs_total=callee_funcs_total,
        claims_floor=claims_floor,
        claims_actual=claims_actual,
        claims_in_sync=claims_in_sync,
        intent_in_sync=intent_in_sync,
        record_stale=record_stale,
        intent_concise=intent_concise,
        intent_context=ctx,
        percent=percent,
        score=score, applicable=applicable, conforms=conforms, errors=parsed.errors,
    )


def mathema_docstring_checklist(parsed: MathemaDocstring) -> list[str]:
    """`parse_mathema_docstring()`'s result as checkbox-style lines
    (✓/✗ for scored criteria, `!` for a structural error), the Mode B
    counterpart to `inventory.docs_checklist()`, same style, used by
    `mathema audit --docs-only --mathema-docs`. No leading indentation;
    callers indent as their own context needs."""
    def mark(ok):
        return "✓" if ok else "✗"

    lines = [f"{mark(bool(parsed.intent))} Intent: present"]
    lines.append(f"{mark(bool(parsed.claims))} Claims: present "
                 f"({len(parsed.claims)} parsed)")
    if parsed.symbols_required:
        n_doc, n_req = len(parsed.symbols_documented), len(parsed.symbols_required)
        lines.append(f"{mark(n_doc == n_req)} symbol coverage ({n_doc}/{n_req} documented)")
    for e in parsed.errors:
        lines.append(f"! {e}")
    return lines


def claims_triplet(floor, actual, expected) -> str:
    """Intent:
        The claim triplet as one cell: `{floor | actual | expected}`,
        with `-` for anything not yet known. Read left to right as the
        least this shape gives you to state, what it states, and what
        a function of this shape typically carries.
    """
    def cell(value):
        return "-" if value is None else str(value)
    return f"{{{cell(floor)} | {cell(actual)} | {cell(expected)}}}"


def docstring_sync_checklist(sync: DocstringSync) -> list[str]:
    """`docstring_sync()`'s result as checkbox-style lines, grouped:
    Intent/Notes, Claims (plus the expected-claims-floor hint, marked
    non-scored), Domain (declared/enforced), Raises, Typing (params/
    return), Callees (quality/docsync). No leading indentation, callers indent
    as their own context needs."""
    def mark(ok):
        return "✓" if ok else "✗"

    def ratio(ok_count, total, label):
        return f"{mark(ok_count == total)} {label} ({ok_count}/{total})"

    p = sync.parsed
    lines = [f"{mark(bool(p.intent))} Intent: present"]
    if sync.intent_concise is not None:
        n_words = len(p.intent.split())
        lines.append(f"{mark(sync.intent_concise)} intent concise ({n_words} words)")
    if sync.intent_in_sync is not None:
        lines.append(f"{mark(sync.intent_in_sync)} intent in sync with the "
                     f"declared layer")
    if sync.claims_in_sync is not None:
        lines.append(f"{mark(sync.claims_in_sync)} Claims: block in sync "
                     f"(names known, no surface conflicts)")
    if sync.record_stale:
        lines.append("! verified record is stale (form changed since it "
                     "was written); its contribution here is dated "
                     "(not scored)")
    ctx = sync.intent_context or {}
    if ctx.get("module") or ctx.get("readme"):
        parts = []
        for level in ("function", "module", "readme"):
            entry = ctx.get(level)
            parts.append(f"{level} ✓ {entry['evidence']}" if entry else f"{level} ✗")
        lines.append("· intent context: " + ", ".join(parts) + " (not scored)")
    if p.notes:
        lines.append("· Notes: present")
    lines.append(f"{mark(bool(p.claims))} Claims: present ({len(p.claims)} parsed)")
    lines.append(f"· claims {claims_triplet(sync.claims_floor, sync.claims_actual, sync.claims_expected)} "
                 f"floor | actual | expected (not scored)")
    if sync.domain_declarable:
        lines.append(ratio(sync.domain_declared, sync.domain_declarable, "domain declared"))
    if sync.domain_declared:
        lines.append(f"{mark(bool(sync.domain_enforced))} domain enforced")
    if sync.raises_total:
        lines.append(ratio(sync.raises_covered, sync.raises_total, "raises covered"))
    if p.symbols_required:
        n_doc, n_req = len(p.symbols_documented), len(p.symbols_required)
        lines.append(ratio(n_doc, n_req, "symbol coverage"))
    if sync.params_typeable:
        lines.append(ratio(sync.params_typed, sync.params_typeable, "params typed"))
    if sync.return_typed is not None:
        lines.append(f"{mark(sync.return_typed)} return typed")
    if sync.callee_funcs_total:
        lines.append(ratio(sync.callee_funcs_documented, sync.callee_funcs_total,
                           "callees documented"))
        lines.append(f"  callees docsync (mean of their own shallow "
                     f"percentages): {sync.callee_sync_percent}%")
    lines.append(f"docsync {sync.percent}% (how much of what the "
                 f"function does is surfaced as context)")
    for e in sync.errors:
        lines.append(f"! {e}")
    return lines


def _strip_block(text: str, header: str) -> str:
    """Remove an existing `<header>` docstring block (header line, body,
    and any immediately-trailing blank line) from `text`, collapsing any
    resulting run of blank lines down to one. `text` unchanged if the
    header isn't present at all."""
    lines = text.splitlines()
    target = header.strip().lower()
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == target:
            start = i
            break
    if start is None:
        return text
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end][:1].isspace()):
        end += 1
    kept = lines[:start] + lines[end:]
    collapsed: list[str] = []
    for line in kept:
        if line.strip() == "" and collapsed and collapsed[-1].strip() == "":
            continue
        collapsed.append(line)
    return "\n".join(collapsed).strip("\n")


def render_docstring(fn, root: str = ".") -> str:
    """The proposed new docstring text for `fn`, with `Claims:` (and
    `Intent:`, if the docstring doesn't already state one) regenerated
    from its verified spec record (`.mathema/verified/<key>.yaml`), only
    claims that actually `held`/were `proven` are written back, each
    tagged `[derive]` when the verdict came from the derive route.
    `Domain:` is left untouched: it's an authoring input mathema reads,
    never an adjudicated output the verified record stores, so there's
    nothing to write back for it. Returns text only, never writes to
    the `.py` file; raises `ValueError` if no verified record exists yet
    (run `mathema.write_spec(fn)` first)."""
    from .authoring import _fn_key
    from .spec import load_verified

    key = _fn_key(fn)
    verified = load_verified(root)
    rec = verified.get(key)
    if rec is None:
        raise ValueError(f"no verified record for {key!r} under root {root!r} "
                         "-- run mathema.write_spec(fn) first")
    entry = rec["entry"]
    claims = entry.get("claims") or []

    doc = inspect.getdoc(fn) or ""
    text = _strip_block(doc, "Claims:")

    claim_lines = [f"    {c['name']}{' [derive]' if c.get('verdict') == 'proven' else ''}"
                  f": {c['statement']}"
                  for c in claims if c.get("verdict") in ("proven", "holds")]

    blocks = []
    if _read_block(doc, _INTENT_HEADER) is None and entry.get("intent"):
        blocks.append(f"Intent:\n    {entry['intent']}")
    if claim_lines:
        blocks.append("\n".join(["Claims:"] + claim_lines))

    if not blocks:
        return text
    prefix = text.rstrip()
    return (prefix + "\n\n" if prefix else "") + "\n\n".join(blocks)


def generate_docstring(fn, key: str | None = None, root: str = ".") -> str | None:
    """Propose a complete docstring for a function that has NONE,
    the claims->docstring direction of the sync loop, the inverse of
    `parse_docstring_claims()`. Creation only: a present docstring is
    the human source of truth, so this returns `None` rather than a
    replacement for one, however sparse it is.

    Intent comes from the declared layer first (an `intent:` field on
    the function's own claims entry, the same per-key entry a
    claims.yaml carries, riding through `merge_entries()` like any
    other field), falling back to the verified record's `intent`.
    Claims come from the verified record when one exists (only claims
    that `held`/were `proven`, `[derive]`-tagged the same way
    `render_docstring()` writes them), else from the declared layer
    as-is (`[derive]` when that's the declared route). `None` when
    neither an intent nor any claims exist; there is nothing to
    write a docstring from."""
    from .authoring import _fn_key, resolve_declared
    from .spec import load_verified

    if (inspect.getdoc(fn) or "").strip():
        return None
    key = key or _fn_key(fn)
    declared = resolve_declared(fn, key=key, root=root)
    verified_entry = (load_verified(root).get(key, {}) or {}).get("entry", {})

    intent = declared.get("intent") or verified_entry.get("intent") or None

    claim_lines: list[str] = []
    verified_claims = [c for c in (verified_entry.get("claims") or [])
                      if c.get("verdict") in ("proven", "holds")]
    if verified_claims:
        claim_lines = [f"    {c['name']}"
                      f"{' [derive]' if c.get('verdict') == 'proven' else ''}"
                      f": {c['statement']}" for c in verified_claims]
    else:
        claim_lines = [f"    {c.get('name')}"
                      f"{' [derive]' if c.get('route') == 'derive' else ''}"
                      f": {c.get('statement')}"
                      for c in (declared.get("claims") or [])
                      if c.get("name") and c.get("statement")]

    if not intent and not claim_lines:
        return None
    blocks = []
    if intent:
        blocks.append(intent)
        blocks.append(f"Intent:\n    {intent}")
    if claim_lines:
        blocks.append("\n".join(["Claims:"] + claim_lines))
    return "\n\n".join(blocks)


def write_docstring(fn, text: str) -> str:
    """Insert `text` as `fn`'s docstring in its own source file,
    the write half of `generate_docstring()`, kept separate so every
    caller decides for itself when writing is allowed (the CLI prompts;
    nothing in the library writes on its own). Creation only: raises
    `ValueError` if the function already has a docstring, or if its
    definition can't be located in the file. Returns the file path.

    The insertion is positional, not a reformat: the triple-quoted
    string goes on its own lines immediately before the function's
    first statement, at that statement's own indentation, and nothing
    else in the file is touched."""
    path = inspect.getsourcefile(fn)
    if path is None:
        raise ValueError(f"no source file for {fn!r}")
    with open(path) as fh:
        module_src = fh.read()
    tree = ast.parse(module_src)
    target = None
    firstline = getattr(getattr(fn, "__code__", None), "co_firstlineno", None)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == fn.__name__:
            if target is None or (firstline is not None
                                  and abs(node.lineno - firstline)
                                  < abs(target.lineno - firstline)):
                target = node
    if target is None:
        raise ValueError(f"could not locate 'def {fn.__name__}' in {path}")
    if ast.get_docstring(target) is not None:
        raise ValueError(f"{fn.__name__} already has a docstring, "
                         "write_docstring() only ever creates, never replaces")
    first_stmt = target.body[0]
    indent = " " * first_stmt.col_offset
    doc_lines = [f'{indent}"""{text.splitlines()[0]}' if text.strip() else f'{indent}"""']
    for line in text.splitlines()[1:]:
        doc_lines.append(f"{indent}{line}" if line.strip() else "")
    doc_lines.append(f'{indent}"""')
    lines = module_src.splitlines()
    insert_at = first_stmt.lineno - 1
    lines[insert_at:insert_at] = doc_lines
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + ("\n" if module_src.endswith("\n") else ""))
    return path


_README_INTENT_HEADING = re.compile(r"^#{1,4}\s*Intent\s*$", re.IGNORECASE | re.MULTILINE)


def _read_module_intent(module) -> dict | None:
    """A module's own intent: its docstring's `Intent:` block
    (`documented`), else the docstring's first non-empty line
    (`declared`; the first paragraph is assumed to be the most
    important explanation of what the code is). `None` when the module
    has no docstring at all."""
    module_doc = (getattr(module, "__doc__", None) or "")
    if not module_doc.strip():
        return None
    block = _read_block(module_doc, _INTENT_HEADER)
    if block:
        text = " ".join(line.strip() for line in block).strip()
        return {"text": text, "evidence": "explicit"} if text else None
    first = next((line.strip() for line in module_doc.splitlines() if line.strip()), None)
    return {"text": first, "evidence": "implicit"} if first else None


def _read_readme_intent(readme: str) -> dict | None:
    """A README's intent: an `Intent:` Google-style block or the first
    paragraph under an `# Intent`-style heading; either is a marked,
    deliberate section, so both earn `documented`. `None` when neither
    exists."""
    block = _read_block(readme, _INTENT_HEADER)
    text = None
    if block:
        text = " ".join(line.strip() for line in block).strip()
    else:
        m = _README_INTENT_HEADING.search(readme)
        if m is not None:
            rest = readme[m.end():].lstrip("\n")
            text = " ".join(rest.split("\n\n", 1)[0].split())
    return {"text": text, "evidence": "explicit"} if text else None


def intent_context(fn, root: str = ".") -> dict:
    """The intent hierarchy around one function: its own docstring's
    intent (`Intent:` block, falling back to the summary line the same
    way `analyze_source()` reads it), its module docstring's (an
    `Intent:` block there, else the module docstring's own first
    non-empty line), and the codebase's (`<root>/README.md`: an
    `Intent:` Google-style block, or the first paragraph under an
    `# Intent`-style heading). Returns
    `{"function": ..., "module": ..., "readme": ...}`, `None` per level
    where nothing is stated; context is reported, never inherited
    downward: a function with no intent of its own stays a gap for the
    sync checklist to show, whatever its module or README says."""
    from .analysis import quiet_facts

    # the explicit Intent: block is the function-level marker and earns
    # "explicit"; the summary line stands in only when no block is
    # stated, labeled "implicit"; these are docstring-SHAPE facts,
    # deliberately distinct from the acceptance rung ladder
    # (declared -> documented), where documented is a human act. A
    # summary is a bare
    # declaration of intent, not a deliberate intent statement.
    function_intent = None
    try:
        block = parse_mathema_docstring(fn).intent
    except Exception:
        block = None
    if block:
        function_intent = {"text": block, "evidence": "explicit"}
    else:
        facts = quiet_facts(fn)
        if facts is not None and facts.doc_intent:
            function_intent = {"text": facts.doc_intent, "evidence": "implicit"}

    module = inspect.getmodule(fn)
    module_intent = _read_module_intent(module) if module else None

    readme_intent = None
    readme_path = os.path.join(root, "README.md")
    if os.path.exists(readme_path):
        with open(readme_path) as fh:
            readme_intent = _read_readme_intent(fh.read())

    return {"function": function_intent, "module": module_intent,
            "readme": readme_intent}
