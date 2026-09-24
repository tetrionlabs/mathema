# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Population sweeps: discover every function under a target, shape one
row per function for `mathema audit`/`mathema audit --docs-only`/
`mathema describe`, roll those rows up by module/package, and scaffold
bare claim stubs for `mathema init`.

Distinct from `inventory.py`, which this module is built *on*: inventory
owns "facts about one function" (is it pure, does its docstring pass a
checklist, is it derivable, ...), independently useful on a single
function, e.g. from `mathema.docstring_report()`. This module owns the
sweep itself: finding the population, calling inventory's per-function
primitives across it, and shaping/aggregating the results into what the
`audit`/`init`/`describe` CLI commands actually print. Nothing here
classifies a function on its own; nothing in inventory.py knows what a
"row" or a "rollup" is.
"""
from __future__ import annotations

import datetime
import importlib
import inspect
import os
import pkgutil
import sys

from .inventory import (coverage_freshness, derivability_report,
                        docstring_quality, is_pure_enough,
                        is_test_covered, mutated_globals, purity_reason,
                        read_test_coverage, scope_dependencies,
                        structural_complexity, typing_info)


def _source_span(fn) -> str | None:
    """Intent:
        The function's own line range in its source file, in the
        sed-address style the audit grid prints (`100:245p`), so a
        reader can jump straight to it. None when the source is
        unavailable.
    """
    try:
        lines, start = inspect.getsourcelines(fn)
    except (OSError, TypeError):
        return None
    return f"{start}:{start + len(lines) - 1}p"


class DiscoveryError(Exception):
    """A target could not be resolved to importable functions at all;
    a filesystem path where a dotted name was expected, or a top-level
    module/package that would not import. Distinct from finding zero
    functions in a module that imported cleanly (that is a legitimate,
    if often surprising, empty result, reported by the caller with
    hints rather than raised)."""


def _looks_like_a_path(target: str) -> bool:
    """Intent:
        A target is a dotted importable name (`pkg.sub`), never a
        filesystem path, `mathema audit` differs from `mathema check`
        here, which does take `file.py:function`. Catch the easy
        confusions (`./pkg`, `src/pkg`, `pkg/`, `mod.py`) so they draw a
        clear message instead of a raw relative-import TypeError.
    Notes:
        The module part is checked before the `:qualname` split is
        applied by the caller, so a bare `mod.py:fn` is caught too.
    """
    mod = target.partition(":")[0]
    return ("/" in mod or os.sep in mod or mod.endswith(".py")
            or mod.startswith(("~", ".")))


def discover(targets: list[str], skipped: list | None = None) -> dict[str, object]:
    """Import each target (a dotted module or package name, the
    target must already be importable, e.g. pip installed editable, the
    same expectation `mathema verify` already has for resolving keys)
    and return every top-level function actually *defined* in it (not
    merely imported into it), keyed `module.qualname`, the same key
    shape the declared/verified store already uses, so results here
    line up with load_declared()/load_verified() directly. A package
    target recurses into every submodule.

    `module.sub:qualname` (a colon, same convention `mathema check`'s
    `file.py:function` already uses) scopes a target down to exactly
    one function or method, only that one module is imported (no
    package walk at all, even if it happens to be one), and only the
    matching key survives. `module.sub` alone (no colon) already scopes
    to a single module on its own, since a plain module target is never
    walked as a package; the colon form is only needed to go one
    level narrower, to a single function within it.

    Also finds methods, keyed `module.ClassName.method`, a class's
    *own* methods only (`vars(cls)`, not inherited ones, the same
    "defined here, not merely visible here" scope module-level
    discovery already applies), `@staticmethod`s unwrapped to their
    plain function (already parameter-complete, no `self` at all) and
    ordinary instance methods included as-is, `self`/`cls` and all;
    is_pure_enough()/purity_reason() are what tell a stateful method
    apart from a stateless one (a method that never actually references
    `self`), not discovery. `@classmethod`/`@property`/anything else is
    skipped: `cls` is murkier than `self` (a "stateless" classmethod can
    still legitimately call `cls()`), not attempted here.

    A single-leading-underscore name (`_helper`) is included, not
    treated as excluded-by-convention, a "private" module-level
    helper is still a real, defined function, and in practice is often
    the more claimable one (a public function frequently just dispatches
    to a private numeric core; hiding the core from audit/init would
    hide the more liftable target, not a noisier one). Only *dunder*
    names (`__init__`, `__repr__`, ...) are excluded; those are
    genuine Python protocol members, not ordinary internal helpers.

    A target that looks like a path, or a top-level module/package that
    will not import, raises `DiscoveryError` (a clear message, not a raw
    traceback). A *submodule* of a walked package that fails to import
    is not fatal; it is skipped, and appended to `skipped` (as
    `(module_name, "ExcType: message")`) when a list is passed, so a
    caller can report which submodules were skipped rather than leave a
    package that looks mysteriously empty."""
    found: dict[str, object] = {}
    for target in targets:
        if _looks_like_a_path(target):
            raise DiscoveryError(
                f"{target!r} looks like a filesystem path, but audit/init/"
                f"describe take an importable dotted name (e.g. `mypkg` or "
                f"`mypkg.submodule`), not a path. `mathema check` is the one "
                f"that takes a `file.py:function` path.")
        mod_name, _, qualname = target.partition(":")
        wanted = f"{mod_name}.{qualname}" if qualname else None
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:
            raise DiscoveryError(
                f"could not import {mod_name!r}: {type(e).__name__}: {e}. The "
                f"target must be importable from the project root. Install "
                f"it (`pip install -e .`) or run from a directory where "
                f"`import {mod_name}` works (audit already adds --root to "
                f"sys.path).") from e
        mods = [mod]
        if not qualname and hasattr(mod, "__path__"):   # a package, not a single module
            for info in pkgutil.walk_packages(mod.__path__, prefix=mod.__name__ + "."):
                try:
                    mods.append(importlib.import_module(info.name))
                except Exception as e:
                    # a submodule that fails to import is skipped, not fatal,
                    # but recorded so the caller can say WHICH, otherwise a
                    # package whose functions all live in an unimportable
                    # submodule looks empty with no explanation
                    if skipped is not None:
                        skipped.append((info.name, f"{type(e).__name__}: {e}"))
                    continue
        for m in mods:
            for name, obj in vars(m).items():
                if _is_dunder(name):
                    continue
                if inspect.isfunction(obj) and obj.__module__ == m.__name__:
                    key = f"{m.__name__}.{name}"
                    if wanted is None or key == wanted:
                        found[key] = obj
                elif inspect.isclass(obj) and obj.__module__ == m.__name__:
                    for mname, member in vars(obj).items():
                        if _is_dunder(mname):
                            continue
                        key = f"{m.__name__}.{name}.{mname}"
                        if wanted is not None and key != wanted:
                            continue
                        if isinstance(member, staticmethod):
                            found[key] = member.__func__
                        elif inspect.isfunction(member):
                            found[key] = member
    return found


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _describe_signature(fn) -> str:
    """A real function's signature, rendered as text, `inspect.
    signature(fn)` (works directly off the live function object, so it
    can never fail with `SourceUnavailable` the way AST-based analysis
    can) as the base, enriched with one small piece of mathema-specific
    value: a parameter with *no* type annotation at all that
    `analyze_source()`'s own AST inference classifies as `"sequence"`-
    kind (subscripted, iterated, `len()`'d, the same inference every
    other derive-route mechanism already relies on) renders as
    `name: sequence (inferred)` instead of a bare, uninformative `name`.
    Built by hand rather than via `inspect.Signature.replace()`/`str()`
    with a synthetic string annotation injected, `inspect.
    formatannotation()` doesn't pass a plain string through unquoted
    (it falls through to `repr()` for anything that isn't a real
    type/typing construct), so that trick renders
    `x: 'sequence (inferred)'`, quotes and all, not the clean
    `x: sequence (inferred)` wanted here.

    Source unavailability for the AST-inference step (a genuine
    possibility independent of whether `inspect.signature()` itself
    succeeded) never breaks the whole signature; it just means no
    enrichment for that one function, the base `inspect.signature()`
    rendering is still returned."""
    import inspect
    import warnings

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return "(...)"
    try:
        from .analysis import SourceUnavailable, analyze_source
        with warnings.catch_warnings():
            # analyze_source() warns on global-scope/unresolved-name
            # capture, real, useful signal on a single function, but a
            # sweep over every function in a package would otherwise
            # print one of these per affected function, drowning out the
            # signature listing itself (same reasoning, same fix, as
            # every population-sweep function in inventory.py already
            # applies around its own analyze_source() call).
            warnings.simplefilter("ignore")
            kinds = analyze_source(fn).param_kinds
    except SourceUnavailable:
        kinds = {}
    parts = []
    for name, p in sig.parameters.items():
        piece = name
        if p.annotation is not inspect.Parameter.empty:
            piece += f": {inspect.formatannotation(p.annotation)}"
        elif kinds.get(name) == "sequence":
            piece += ": sequence (inferred)"
        if p.default is not inspect.Parameter.empty:
            piece += f" = {p.default!r}"
        parts.append(piece)
    ret = ""
    if sig.return_annotation is not inspect.Signature.empty:
        ret = f" -> {inspect.formatannotation(sig.return_annotation)}"
    return f"({', '.join(parts)}){ret}"


def _try_derive_lift(fn, facts, extra_domain: dict | None = None):
    """The same lift-dispatch order `try_prove()` itself tries (`lift()`
    -> `lift_conditioned()` -> `lift_fold()` -> `lift_dot()` ->
    `lift_sum()`), run here *read-only*, with no claim to prove against,
    for `describe`'s own `lifted`/`canonical` tier sections, which
    want to know only "does this function have a closed form at all,"
    not verify anything about it. `lift_conditioned()` is only attempted
    when the function actually branches (mirrors `lift()`'s own
    branch-free precondition) and a domain can be found at all (the
    same two sources `types.domain_from_signature()`/the docstring's own
    `Domain:` block already merge elsewhere), with no domain, a
    branchy function has nothing for `lift_conditioned()` to prune
    against, so trying it would only ever return `None` anyway. Returns
    the bare `sympy.Expr`, or `None` if nothing in the chain resolves."""
    from .symbolic import lift, lift_conditioned, lift_dot, lift_fold, lift_sum
    from .types import domain_from_signature

    result = lift(fn, facts)
    if result is not None:
        return result.expr
    if facts.branch_count:
        domain = dict(domain_from_signature(fn))
        if extra_domain:
            # a caller-supplied domain (a claim's own declared bounds,
            # diagnostic_report' declared_domain) conditions the lift
            # exactly as claim-time adjudication would, without this,
            # a guard-carrying function whose domain lives only in its
            # claims reported liftable: False while its claims proved
            domain.update(extra_domain)
        if domain:
            conditioned = lift_conditioned(fn, facts, domain)
            if conditioned is not None and conditioned.kind == "value":
                return conditioned.expr
    fold = lift_fold(fn, facts)
    if fold is not None:
        return fold.expr
    dot = lift_dot(fn, facts)
    if dot is not None:
        return dot.expr
    total = lift_sum(fn, facts)
    if total is not None:
        return total.expr
    return None


def _claim_domain(entry: dict) -> dict:
    """Every bound the entry's own claims declare, merged, the context
    a claim brings to the derive route, which is exactly what turns a
    `branch:needs-domain` blocker into a proof.

    Parsed, not read off the `domain` key: the spelling the grammar
    teaches puts the quantifier inline in the statement
    (`for theta in [0, 100], f(theta) >= 0`), and only a claim mathema
    itself wrote has the bounds split out into a side field. Reading
    the field alone saw nothing for a hand-authored claim, so the
    common case never supplied any context at all.

    One claim at a time, so a single unparseable statement costs only
    its own bounds rather than the whole entry's.
    """
    from .spec import entry_claims

    merged: dict = {}
    for row in (entry.get("claims") or []):
        if row.get("verdict"):
            continue          # a past adjudication, not a declaration
        try:
            conjecture = entry_claims({"claims": [row],
                                       "grammar": entry.get("grammar")})
        except Exception:
            continue
        for cj in conjecture:
            for name, bound in (cj.domain or {}).items():
                merged.setdefault(name, bound)
    return merged

def _declared_entry(fn, stored: dict | None) -> dict:
    """Intent:
        The claims every authoring surface declares for `fn`: the
        claims-file entry from the loaded store, merged with the
        function's own docstring and decorator claims at the usual
        precedence. The file entry alone when the function's own claims
        cannot be read.
    """
    from .authoring import resolve_declared
    file_entry = (stored or {}).get("entry") or {}
    try:
        return resolve_declared(fn, file_entry=file_entry)
    except Exception:
        return file_entry


def derivable_in_context(fn, facts=None, declared_domain: dict | None = None) -> bool | None:
    """Intent:
        Whether the derive route can work on `fn` given the context it
        actually has, the domain its signature, docstring and claims
        declare, rather than with nothing supplied.

    Notes:
        This is the question a reader asks of an audit table, and it is
        not the one `inventory.is_pure_enough()` answers. That measures
        whether the body lifts unaided, which is a property of the code
        alone; a branchy function reports `False` there and proves its
        claims through the derive route anyway, because the claim's own
        `for x in [...]` quantifier prunes the branch. Two spiral
        functions in a real repository sat at `derivable=False` with
        eleven derive-route proofs between them.

        `None` when the source could not be retrieved, not a verdict
        either way, matching `is_pure_enough()`.
    """
    # quiet_facts, not analyze_source: this is a read-only diagnostic
    # run once per audited row, and the scope warning it would raise has
    # already been emitted by the analysis the row's other columns did
    from .inventory import quiet_facts
    if facts is None:
        facts = quiet_facts(fn)
        if facts is None:
            return None
    try:
        return _try_derive_lift(fn, facts, extra_domain=declared_domain) is not None
    except Exception:
        return None

def describe_detail(key: str, fn, root: str = ".", depth: int = 3,
                    tier: str | None = None) -> dict:
    """Everything mathema itself sees about one already-resolved function
    `fn` (found under `key`, e.g. by `cmd_describe`'s own key-resolution
    step): its signature and identity hashes, every inferred domain
    (types/docstring/finite-value sources, each tagged with which one),
    every claim (file-declared merged with whatever's on the live
    function, plus a verified verdict when one exists), and the tier
    ladder, `source`/`normalized`/`structural` share one plain,
    indented rendering (`_tier_text.render_structure_plain`), `lifted`/
    `canonical` are a second, separate rendering of the real lift
    result's own shape (`_tier_text.render_lifted_plain` /
    `grammar.render_canonical`). A tier that isn't available is never
    silently substituted: `text` carries the real reason and
    `available` says which it is.

    `tier=None` (the default) computes all five tiers; passing one tier
    name narrows the `"tiers"` section to just that one, without paying
    for the other four."""
    from .analysis import quiet_facts
    from .authoring import resolve_declared
    from .grammar import to_latex
    from .identity import local_names
    from .inventory import purity_reason, typing_info
    from .spec import load_declared, load_verified
    from .types import domain_from_signature
    from . import _tier_text
    from . import tiers as tiers_mod

    facts = quiet_facts(fn)

    identity: dict[str, str | None] = (
        {"sig_hash": facts.sigh, "form_hash": facts.form} if facts is not None
        else {"sig_hash": None, "form_hash": None})

    domains = [{"param": name, "domain": bound, "source": "types"}
              for name, bound in domain_from_signature(fn).items()]
    for name, values in (typing_info(fn).get("finite_domains") or {}).items():
        # a plain Python list here (typing_info()'s own return shape) is
        # not part of the Interval/"Z"/"N"/frozenset domain vocabulary
        # every other domain source already produces, wrapped in a
        # frozenset so render_domain_bound() (and any other consumer of
        # this list) sees one consistent domain-bound shape regardless
        # of source, rather than a fourth, list-shaped special case.
        domains.append({"param": name, "domain": frozenset(values), "source": "typing"})

    declared = load_declared(root)
    verified = load_verified(root)
    file_entry = declared.get(key, {}).get("entry", {})
    merged_entry = resolve_declared(fn, file_entry=file_entry)
    verified_claims = (verified.get(key, {}).get("entry", {}) or {}).get("claims") or []
    verified_by_name = {c.get("name"): c for c in verified_claims}
    claims = []
    for c in merged_entry.get("claims") or []:
        statement = c.get("statement") or c.get("law")
        if not statement:
            continue
        try:
            latex = to_latex(statement)
        except Exception as e:
            latex = f"(not available: {e})"
        v = verified_by_name.get(c.get("name"))
        claims.append({"name": c.get("name"), "statement": statement, "latex": latex,
                       "verdict": v.get("verdict") if v else None})

    tier_names = tiers_mod.TIERS if tier is None else (tier,)
    ladder = {}
    name_map = seq_params = None
    if facts is not None and facts.tree is not None:
        name_map = {n: f"v{i}" for i, n in enumerate(local_names(facts.tree))}
        seq_params = frozenset(p for p, k in facts.param_kinds.items() if k == "sequence")

    lift_expr = "not-attempted"   # computed lazily, at most once, only if a tier needs it
    for t in tier_names:
        if t in ("source", "normalized", "structural"):
            if facts is None or facts.tree is None:
                ladder[t] = {"text": "source unavailable for this function", "available": False}
                continue
            text = _tier_text.render_structure_plain(
                facts.tree, t, name_map=name_map, seq_params=seq_params)
            ladder[t] = {"text": text, "available": True}
        elif t in ("lifted", "canonical"):
            if facts is None or facts.tree is None:
                ladder[t] = {"text": "source unavailable for this function", "available": False}
                continue
            if lift_expr == "not-attempted":
                lift_expr = _try_derive_lift(fn, facts)
            if lift_expr is None:
                reason = purity_reason(fn) or "this function doesn't lift to a closed form"
                ladder[t] = {"text": reason, "available": False}
            elif t == "lifted":
                ladder[t] = {"text": _tier_text.render_lifted_plain(lift_expr),
                            "available": True}
            else:
                from .grammar import render_canonical
                ladder[t] = {"text": render_canonical(lift_expr)[0], "available": True}

    from .spec import load_declared as _ld, load_verified as _lv
    concepts = _row_concepts(key, fn, _ld(root), _lv(root))
    references = [{"title": t, "url": u, "via": via}
                  for t, u, via in (getattr(facts, "doc_refs", []) or [])] \
        if facts is not None else []
    return {"key": key, "signature": _describe_signature(fn), "identity": identity,
           "domains": domains, "claims": claims, "tiers": ladder,
           "concepts": concepts, "references": references}


def describe_rows(targets: list[str]) -> list[dict]:
    """One row per discovered function: `key` and its own rendered
    `signature` (see `_describe_signature()`), nothing else. The
    lightest of this module's three row-shaping functions (alongside
    `audit_rows()`/`docs_only_rows()`): no declared-claims lookup, no
    coverage report, no docstring scoring, no derivability computation;
    `mathema describe`'s whole job is discovery plus a signature,
    not a population *analysis* the way `mathema audit` is."""
    functions = discover(targets)
    return [{"key": key, "signature": _describe_signature(fn)}
           for key, fn in sorted(functions.items())]


def _claim_floor_count(fn) -> int | None:
    """The floor as a plain integer for a row, `inventory.claim_floor`
    also reports which aspects produced it, which is detail for
    `describe`, not for one cell of a sweep."""
    from .inventory import claim_floor
    report = claim_floor(fn)
    return report["floor"] if report else None


def claimed_count(key: str, fn, declared: dict, verified: dict | None = None) -> int:
    """How many claims this function already has, from *any* authoring
    surface, file-declared (the `declared` store, already loaded by
    the caller) merged with whatever's on the live function itself
    (decorator/docstring/inferred-type claims), the same merge
    cmd_verify() already does. Deliberately does not count a verified
    record's auto-probed generic properties (determinism, symmetry,
    ...); those exist for every function unconditionally and would
    make "claimed" meaningless as a coverage signal.

    With `verified` supplied, a claim whose recorded verdict is blocked
    (skipped, unliftable) does not count: adjudication never engaged
    with it, so it evidences nothing. A claim that came back unknown or
    falsified does count; both are real adjudications, and a
    falsification is evidence. A claim with no record yet counts, since
    nothing has been adjudicated to exclude it."""
    from .authoring import resolve_declared
    from .records import stance
    from .spec import entry_claims

    file_entry = declared.get(key, {}).get("entry", {})
    merged = resolve_declared(fn, file_entry=file_entry)
    claims = entry_claims(merged)
    if not verified:
        return len(claims)
    rec = verified.get(key)
    if rec is None:
        return len(claims)
    blocked = {row.get("name") for row in (rec["entry"].get("claims") or [])
               if stance(row.get("verdict") or "") == "blocked"}
    return sum(1 for cj in claims if cj.name not in blocked)


def _docsync_score(fn, root: str = ".", declared: dict | None = None,
                   verified: dict | None = None,
                   claims_floor: int | None = None,
                   sync_cache: dict | None = None) -> dict:
    """`docstring.docstring_sync(fn, root)`'s result,
    flattened to a plain dict for `audit`'s row shape (every other row
    field is a dict or scalar, never a dataclass), `percent` (the
    weighted CDD-compliance measure) for the table column,
    `score`/`applicable`/`conforms`/`errors` for anything wanting the
    per-criterion detail. The wide table's single-column summary
    reports the same number `--docs`' own grid does, not a different,
    narrower one."""
    import warnings

    from .docstring import docstring_sync

    with warnings.catch_warnings():
        # the sync's callee walk re-analyzes neighbors; their hygiene
        # warnings belong to their own rows, not this one's sweep
        warnings.simplefilter("ignore")
        sync = docstring_sync(fn, root=root, declared=declared,
                              verified=verified, claims_floor=claims_floor,
                              sync_cache=sync_cache)
    return {"percent": sync.percent,
            "score": sync.score, "applicable": sync.applicable,
            "conforms": sync.conforms, "errors": sync.errors,
            # the per-dim cells the compact columns expose, the
            # --docs grid's own dims, as typed values
            "intent": bool(sync.parsed.intent),
            "domain_declared": [sync.domain_declared,
                                sync.domain_declarable],
            "raises_declared": [sync.raises_covered, sync.raises_total],
            "callees_doc_quality": [sync.callee_funcs_documented,
                                    sync.callee_funcs_total],
            "callees_docsync": [sync.callee_sync_percent or 0,
                                sync.callee_funcs_total]}


AUDIT_ANALYSES = frozenset({"derivable", "complexity", "typing",
                            "scope", "tested", "docs", "docsync"})


def _row_concepts(key: str, fn, declared: dict, verified: dict) -> list:
    """Intent:
        Every concept known for one function across the three
        authoring/derivation surfaces the stores already hold: the
        docstring marker, the declared entry's own meta.concepts, and
        the verified record's meta.concepts union (which folds in the
        mechanism harvest). De-duplicated, first-seen order.
    """
    from .analysis import quiet_facts
    from .concepts import normalize_concept

    out: list = []

    def add(tokens):
        for t in tokens or []:
            t = normalize_concept(str(t))
            if t and t not in out:
                out.append(t)

    facts = quiet_facts(fn)
    if facts is not None:
        add(getattr(facts, "doc_concepts", []))
    entry = (declared.get(key) or {}).get("entry") or {}
    add((entry.get("meta") or {}).get("concepts"))
    ventry = (verified.get(key) or {}).get("entry") or {}
    add((ventry.get("meta") or {}).get("concepts"))
    return out


def audit_rows(targets: list[str], root: str = ".",
               exclude: frozenset | None = None,
               skipped: list | None = None) -> list[dict]:
    """One row per discovered function: whether it's claimed (any
    surface), whether it's liftable for a *derive-route* proof specifically
    (probe-route claims remain viable regardless, see purity_reason()),
    and if not, why not; whether it depends on module-level global
    *variable* state (a real, hidden-dependency risk) as distinct from
    merely referencing a sibling function/class/module (ordinary code
    structure, not a risk, see analysis._is_definitional()), or
    references a name mathema can't resolve at all; and, if a
    coverage report exists, whether the target's own tests exercise it
    at all. `exclude` (see AUDIT_ANALYSES for the accepted names) skips
    the corresponding analysis entirely rather than just hiding it;
    excluded fields come back `None`.

    Every underivable row (`pure is False`) carries its
    derivability_report() as `blocked_report`, the coded per-construct
    detail the audit grid's `blocked` column and detail block render.
    `lines` is the function's own source span, sed-style
    (`{start}:{end}p`), or None when the source is unavailable.

    `mathema_docs` additionally scores every row against the strict
    mathema-docstring schema (docstring.parse_mathema_docstring()),
    opt-in and off by default, unlike every other analysis here, since
    it's a much more opinionated bar than the loose `docs` checklist
    (mathema audit --mathema-docs). """
    from .spec import load_declared

    from .spec import load_verified

    exclude = exclude or frozenset()
    functions = discover(targets, skipped=skipped)
    declared = load_declared(root)
    verified = load_verified(root)
    from .locks import load_locks
    locks = load_locks(root)
    coverage_data = None if "tested" in exclude else read_test_coverage(root)
    freshness = (None if coverage_data is None
                 else coverage_freshness(root))
    # shared across the sweep: each function's shallow sync computed
    # once, then reused when it appears as someone's callee
    sync_cache: dict = {}
    rows = []
    for key, fn in sorted(functions.items()):
        n = claimed_count(key, fn, declared, verified)
        # the floor feeds both the claims triplet and the docsync
        # score: computed once per function, threaded to both
        row_floor = (None if ("derivable" in exclude
                              and "docsync" in exclude)
                     else _claim_floor_count(fn))
        if "scope" in exclude:
            global_vars: list[str] = []
            global_funcs: list[str] = []
            unresolved: list[str] = []
            mutated: list[str] = []
        else:
            scope = scope_dependencies(fn)
            global_vars, global_funcs, unresolved = scope if scope is not None else ([], [], [])
            mutated = mutated_globals(fn) or []
        skip_derive = "derivable" in exclude
        # two different questions, kept apart because collapsing them
        # is what made the column understate: `unconditional` is a
        # property of the body alone, `derivable` is what the derive
        # route can actually do here given the declared context
        unconditional = None if skip_derive else is_pure_enough(fn)
        derivable = (None if skip_derive
                     else derivable_in_context(fn, declared_domain=_claim_domain(
                         _declared_entry(fn, declared.get(key)))))
        rows.append({
            "key": key,
            "_fn": fn,
            # the lock entry when this function's form is pinned: a
            # person's assurance that the body cannot change under a
            # CDD loop until a human unlocks
            "locked": locks.get(key),
            "module": getattr(fn, "__module__", None),
            "claimed": n > 0,
            "n_claims": n,
            "claim_floor": row_floor,
            "unconditional": unconditional,
            "derivable": derivable,
            "pure": unconditional,
            "purity_reason": None if "derivable" in exclude else purity_reason(fn),
            "blocked_report": (derivability_report(fn)
                               if unconditional is False else None),
            "span": _source_span(fn),
            "complexity": None if "complexity" in exclude else structural_complexity(fn),
            "typing": None if "typing" in exclude else typing_info(fn),
            "global_vars": global_vars,
            "mutated_globals": mutated,
            "global_funcs": global_funcs,
            "unresolved": unresolved,
            # tested is a closed enum: "yes"/"no" against a real
            # coverage report, "no-report" when none exists, and
            # "outdated" when the function's source file changed after
            # the report was produced (a stale yes is not evidence).
            # null stays strictly "analysis excluded".
            "test_covered": (None if "tested" in exclude
                             else "no-report" if coverage_data is None
                             else "outdated" if _coverage_outdated(
                                 fn, freshness)
                             else ("yes" if is_test_covered(fn, coverage_data)
                                   else "no")),
            "_scope_excluded": "scope" in exclude,
            "docs": None if "docs" in exclude else docstring_quality(fn),
            "concepts": _row_concepts(key, fn, declared, verified),
            "docsync": (None if "docsync" in exclude
                        else _docsync_score(fn, root, declared, verified,
                                            row_floor, sync_cache)),
        })
    return rows



def _coverage_outdated(fn, freshness) -> bool:
    """Intent:
        Whether the function's source file changed since the coverage
        report measured it (by content hash when the report is stamped,
        else by file time); the report's yes/no then describes code
        that no longer exists, so neither answer is trustworthy and the
        cell says "outdated" instead of either.
    """
    if freshness is None:
        return False
    import inspect as _inspect
    try:
        src = _inspect.getsourcefile(fn)
    except TypeError:
        return False
    return src is not None and freshness.is_stale(src)

# the compact table's column registry: name -> raw value off an
# audit_rows() row. Raw data, not grid strings, a missing/inapplicable
# value is None (JSON null), never "-". The names are the caller-facing
# selection vocabulary, additive-only once released.
# One null policy across every compact cell: null means the analysis
# was NOT COMPUTED (excluded, usually because no chosen column needed
# it); a computed-but-empty result is its typed empty value ([] for
# lists, 0 for counts, "" for the blocker of a derivable function).
# The two used to share null, which made a cell unreadable once
# column selection began deriving exclusions.
COMPACT_COLUMNS = {
    "key": lambda r: r["key"],
    # a ready-made sed address, not a line count: `sed -n 142,187p`
    "span": lambda r: r["span"],
    "claims": lambda r: r["n_claims"],
    "min_expected_claims": lambda r: r["claim_floor"],
    # the two numbers side by side: an aggregate can look healthy while
    # the functions carrying the risk are the unevidenced ones
    "claims_vs_floor": lambda r: (None if r["claim_floor"] is None
                                  else [r["n_claims"], r["claim_floor"]]),
    # what the derive route can do here, given the domain the
    # signature, docstring and claims declare
    "derivable": lambda r: r["derivable"],
    # whether the body lifts with nothing supplied, a property of the
    # code alone, and deliberately not a ceiling on what can be proven
    "unconditional": lambda r: r["unconditional"],
    "blocker": lambda r: _blocker_cell(r, 0),
    "blocker_params": lambda r: _blocker_cell(r, 1),
    "blocker_more": lambda r: _blocker_cell(r, 2),
    # the remedy, in the row the caller is already reading: a separate
    # reason_code lookup to decode a blocker loses the thread, so the
    # hint rides along when asked for (never by default, the compact
    # payload stays compact)
    "blocker_hint": lambda r: _blocker_detail(r, "hint"),
    "blocker_unlock": lambda r: _blocker_detail(r, "derive_unlock"),
    "constructs": lambda r: (None if r["pure"] is None
                             else _compact_constructs(r["blocked_report"])
                             or []),
    "cx": lambda r: (r["complexity"] or {}).get("cyclomatic"),
    "typed": lambda r: _typed_pair(r["typing"]),
    "tested": lambda r: r["test_covered"],
    "doc_quality": lambda r: ([r["docs"]["score"], r["docs"]["applicable"]]
                              if r["docs"] else None),
    "docsync": lambda r: (r["docsync"]["percent"]
                          if r.get("docsync") else None),
    "quality": lambda r: ([r["docs"]["score"], r["docs"]["applicable"]]
                          if r["docs"] else None),
    "intent": lambda r: (r["docsync"]["intent"]
                         if r.get("docsync") else None),
    "domain_declared": lambda r: (r["docsync"]["domain_declared"]
                                  if r.get("docsync") else None),
    "raises_declared": lambda r: (r["docsync"]["raises_declared"]
                                  if r.get("docsync") else None),
    "callees_doc_quality": lambda r: (r["docsync"]["callees_doc_quality"]
                                      if r.get("docsync") else None),
    "callees_docsync": lambda r: (r["docsync"]["callees_docsync"]
                                  if r.get("docsync") else None),
    "concepts": lambda r: len(r["concepts"]),
    # the pinned form hash when locked, "" when not: assurance that
    # the body cannot change until a human runs mathema unlock
    "locked": lambda r: ((r.get("locked") or {}).get("form") or ""),
    "global_vars": lambda r: (None if r.get("_scope_excluded")
                              else r["global_vars"]),
    "mutates": lambda r: (None if r.get("_scope_excluded")
                          else r["mutated_globals"]),
    "unresolved": lambda r: (None if r.get("_scope_excluded")
                             else r["unresolved"]),
}



def _blocker_detail(r, field: str):
    """Intent:
        One field of the reason-code entry for this row's blocker,
        the hint text or the derive_unlock class, looked up from
        CODE_TABLE by the bare code `_blocker_cell` already produces.
        null when the derivable analysis was excluded; "" for a
        derivable function (computed, nothing blocking).
    """
    if r["pure"] is None:
        return None
    from .reason_codes import blocked_code, describe_code
    code = (blocked_code(r["blocked_report"])
            if r["blocked_report"] is not None else None)
    if not code:
        return ""
    entry = describe_code(code)
    return (entry or {}).get(field) or ""

def _blocker_cell(r, part: int):
    """Intent:
        One slot of the split blocked code: bare CODE_TABLE key,
        parameter list, +N count. null when the derivable analysis was
        excluded; ("", [], 0) for a derivable function, computed,
        nothing blocking.
    """
    if r["pure"] is None:
        return None
    from .reason_codes import blocked_code, split_code
    code = (blocked_code(r["blocked_report"])
            if r["blocked_report"] is not None else None)
    bare, params, more = split_code(code)
    return (bare or "", params, more)[part]


# what a caller gets without naming columns: the triage set
COMPACT_DEFAULT_COLS = ("key", "span", "claims", "derivable",
                        "unconditional", "blocker", "typed", "tested")

# which analysis each compact column actually needs, the speed half
# of column selection: an unrequested analysis is never computed at
# all (audit_rows' own exclude mechanism), not merely dropped from
# the payload
_COL_ANALYSES = {
    "derivable": "derivable", "unconditional": "derivable",
    "blocker": "derivable",
    "blocker_params": "derivable", "blocker_more": "derivable",
    "blocker_hint": "derivable", "blocker_unlock": "derivable",
    "claims_vs_floor": "derivable",
    "constructs": "derivable", "min_expected_claims": "derivable",
    "cx": "complexity", "typed": "typing", "tested": "tested",
    "doc_quality": "docs", "quality": "docs", "docsync": "docsync",
    "intent": "docsync", "domain_declared": "docsync",
    "raises_declared": "docsync", "callees_doc_quality": "docsync",
    "callees_docsync": "docsync",
    "global_vars": "scope", "unresolved": "scope", "mutates": "scope",
}


def exclude_for_cols(cols, filters=None) -> frozenset:
    """Intent:
        The audit analyses NOT needed by the selected compact columns
        AND by the filter's own references, in audit_rows' own exclude
        vocabulary, so a triage call computes only what its columns
        show, while a filter never matches against a value that was
        never computed (an empty result must mean "nothing matched",
        never "never looked"). A columnar term pulls in its column's
        analysis; a bare ~text term matches ANY column, so it needs
        everything; the semantic terms all read derivability facts.
    """
    needed = {_COL_ANALYSES[c] for c in cols if c in _COL_ANALYSES}
    for term in _filter_terms(filters):
        if "~" not in term:
            needed.add("derivable")
        else:
            col = term.split("~", 1)[0]
            if not col:
                return frozenset()
            if col in _COL_ANALYSES:
                needed.add(_COL_ANALYSES[col])
    return frozenset(AUDIT_ANALYSES) - needed


def _filter_terms(filters) -> list:
    if not filters:
        return []
    if isinstance(filters, str):
        return [t.strip() for t in filters.split(",") if t.strip()]
    return [t for item in filters
            for t in str(item).split(",") if t.strip()]


def _compact_blocked(report) -> "str | None":
    from .reason_codes import blocked_code
    return blocked_code(report) or None


def _compact_constructs(report) -> "list | None":
    from .diagnostics import _blocking_constructs
    return _blocking_constructs(report) or None


def _typed_pair(typing_info) -> "list | None":
    if not typing_info:
        return None
    typed = typing_info["params_typed"] + bool(typing_info["return_typed"])
    total = typing_info["params_total"] + 1
    return [typed, total]


def _common_key_prefix(keys: list) -> str:
    """Intent:
        The longest shared dotted prefix (cut at a dot boundary) across
        the row keys, factored out of every row; "" when nothing is
        shared.
    """
    import os as _os
    if len(keys) < 2:
        head, dot, _ = (keys[0] if keys else "").rpartition(".")
        return head + dot if dot else ""
    common = _os.path.commonprefix(keys)
    head, dot, _ = common.rpartition(".")
    return head + dot if dot else ""


AUDIT_FILTERS = frozenset({"actionable", "limitation", "N/A",
                           "claimed", "unclaimed", "derivable",
                           "underivable", "unconditional", "needs-context",
                           "underclaimed"})


def filter_rows(rows: list[dict], filters) -> list[dict]:
    """Intent:
        The audit rows a filter keeps. Two kinds of term, freely
        mixed, several ANDing together:

        - semantic terms, evaluated against row FACTS: derive_unlock
          classes ("actionable"/"limitation"/"N/A", read off the
          row's blocked code), claim status ("claimed"/"unclaimed"),
          "derivable"/"underivable" (what the derive route can do given
          the declared domain), "unconditional"/"needs-context" (whether
          the body lifts with nothing supplied), and "underclaimed" (fewer claims
          than the function's own structural floor; the "what have I
          not evidenced" query);
        - columnar matches, substring against a column's rendered
          value: "blocker~loop" scopes to one column,
          "~measures" matches ANY column (see COMPACT_COLUMNS for
          the names).

        Terms from the same semantic dimension OR together
        ("actionable,limitation" keeps either, which is also how
        "everything except N/A" is spelled); dimensions and columnar
        terms AND across. An empty match text ("~", "col~") is an
        error, never a keep-everything no-op.

        An EXPLICIT parameter by design, never a default: the
        semantic terms are right for a lifting pass and wrong for a
        claims pass; probe claims stay viable on every limitation
        row.
    Raises:
        ValueError: an unknown term or column, naming the vocabulary.
    """
    from .reason_codes import blocked_code, describe_code
    terms = _filter_terms(filters)
    matchers = [t for t in terms if "~" in t]
    semantic = [t for t in terms if "~" not in t]
    unknown = [t for t in semantic if t not in AUDIT_FILTERS]
    for m in matchers:
        col, _tilde, text = m.partition("~")
        if col and col not in COMPACT_COLUMNS:
            unknown.append(m)
        elif not text:
            # a bare "~" or "col~" would keep every row, a truncated
            # argument must never read as a successful query
            raise ValueError(
                f"empty match text in filter {m!r}; a columnar term "
                f"is col~text (or ~text for any column)")
    if unknown:
        raise ValueError(
            f"unknown filter(s) {unknown}; choose from "
            f"{sorted(AUDIT_FILTERS)}, or match a column as "
            f"col~text / ~text (columns: {sorted(COMPACT_COLUMNS)})")

    def _cell(r, col) -> str:
        try:
            v = COMPACT_COLUMNS[col](r)
        except Exception:
            return ""
        return "" if v is None else str(v)

    # same-dimension terms OR together, dimensions AND across: an
    # agent writing "actionable,limitation" means either (and that
    # spelling IS "everything except N/A", the claims-pass query),
    # while a pure AND would make every such pair a guaranteed-empty
    # result that reads like a confident answer
    unlock_wanted = {t for t in semantic
                     if t in ("actionable", "limitation", "N/A")}
    claim_wanted = {t for t in semantic if t in ("claimed", "unclaimed")}
    # "what have I not evidenced": the floor is already a structural
    # minimum rather than a target, so carrying fewer claims than it
    # is a real gap and needs no threshold parameter
    want_underclaimed = "underclaimed" in semantic
    deriv_wanted = {t for t in semantic
                    if t in ("derivable", "underivable")}
    uncond_wanted = {t for t in semantic
                     if t in ("unconditional", "needs-context")}

    def keep(r) -> bool:
        code = (blocked_code(r["blocked_report"])
                if r.get("blocked_report") is not None else None)
        unlock = None
        if code:
            entry = describe_code(code)
            unlock = entry["derive_unlock"] if entry else None
        if unlock_wanted and unlock not in unlock_wanted:
            return False
        if claim_wanted:
            status = "claimed" if r.get("claimed") else "unclaimed"
            if status not in claim_wanted:
                return False
        if want_underclaimed:
            floor = r.get("claim_floor")
            if floor is None or r.get("n_claims", 0) >= floor:
                return False
        if deriv_wanted:
            # filters on what the derive route can do here, matching the
            # column of the same name. `unconditional` is its own term:
            # a branch:needs-domain row is derivable and does not lift
            # unconditionally, and an agent hunting either population
            # has to be able to say which.
            status = ("derivable" if r.get("derivable") is True
                      else "underivable" if r.get("derivable") is False
                      else None)
            if status not in deriv_wanted:
                return False
        if uncond_wanted:
            bare = ("unconditional" if r.get("unconditional") is True
                    else "needs-context" if r.get("unconditional") is False
                    else None)
            if bare not in uncond_wanted:
                return False
        for m in matchers:
            col, _tilde, text = m.partition("~")
            if col:
                if text not in _cell(r, col):
                    return False
            elif not any(text in _cell(r, c) for c in COMPACT_COLUMNS):
                return False
        return True
    return [r for r in rows if keep(r)]


def compact_audit(rows: list[dict], cols: list | None = None) -> dict:
    """The population report in the column-oriented agent shape:
    `{"prefix": ..., "cols": [...], "rows": [[...], ...]}`. Column
    names appear once, the shared dotted key prefix is factored out of
    every row, and values are raw data (None for missing, never "-").
    `cols` selects and orders the columns (see COMPACT_COLUMNS for the
    vocabulary); omitted, the default triage set is used, either way
    the resolved selection is rendered back in `cols` explicitly.
    Raises ValueError naming the known columns on an unknown name."""
    chosen = list(cols) if cols else list(COMPACT_DEFAULT_COLS)
    unknown = [c for c in chosen if c not in COMPACT_COLUMNS]
    if unknown:
        raise ValueError(f"unknown column(s) {unknown}; "
                         f"choose from {sorted(COMPACT_COLUMNS)}")
    prefix = _common_key_prefix([r["key"] for r in rows])
    out_rows = []
    for r in rows:
        vals = []
        for c in chosen:
            v = COMPACT_COLUMNS[c](r)
            if c == "key" and prefix and isinstance(v, str):
                v = v[len(prefix):]
            vals.append(v)
        out_rows.append(vals)
    return {"prefix": prefix, "cols": chosen, "rows": out_rows}


def docs_only_rows(targets: list[str], root: str = ".",
                   mathema_docs: bool = False) -> list[dict]:
    """One row per discovered function, docs-only: `key`, the loose
    `docstring_quality()` result, and, if `mathema_docs`, the full
    `docstring.DocstringSync` object (not audit_rows()'s flattened
    `mathema_docs` shape, which only keeps score/applicable/conforms/
    errors; a per-criterion checkbox breakdown needs the real object's
    `.raises_covered`/`.domain_declared`/`.params_typed`/etc. too).
    Backs `mathema audit --docs-only`, a separate, smaller sweep from
    audit_rows() rather than a filtered view of it, since nothing else
    is discovered or computed either. """
    functions = discover(targets)
    from .spec import load_declared, load_verified
    declared = load_declared(root)
    verified = load_verified(root)
    rows = []
    sync_cache: dict = {}
    for key, fn in sorted(functions.items()):
        row = {"key": key, "docs": docstring_quality(fn),
               "concepts": _row_concepts(key, fn, declared, verified)}
        if mathema_docs:
            from .docstring import docstring_sync
            row["sync"] = docstring_sync(fn, root=root, declared=declared,
                                         verified=verified,
                                         sync_cache=sync_cache)
        else:
            row["sync"] = None
        rows.append(row)
    return rows


def rollup_stats(rows: list[dict]) -> dict:
    """The same aggregate counts cmd_audit's grand-total line computes,
    generalized to any subset of rows, so a module- or package-level
    rollup is exactly this called on the rows that belong to it, not a
    second, separately-maintained set of aggregation rules."""
    n = len(rows)
    tested = [r["test_covered"] == "yes" for r in rows
              if r["test_covered"] in ("yes", "no")]
    docs_scored = [r["docs"] for r in rows if r["docs"] and r["docs"]["applicable"]]
    return {
        "n": n,
        "claimed": sum(1 for r in rows if r["claimed"]),
        # the rollup counts what the derive route can actually do here,
        # which is the number a reader is looking for. `unconditional`
        # is reported beside it rather than instead of it: a low count
        # there is a fact about the code, not a ceiling on proof, and
        # reporting only that understated provability badly enough that
        # a real repository read 2/75 while carrying derive proofs.
        "derivable": sum(1 for r in rows if r["derivable"]) if any(
            r["derivable"] is not None for r in rows) else None,
        "unconditional": sum(1 for r in rows if r["unconditional"]) if any(
            r["unconditional"] is not None for r in rows) else None,
        "typed": sum(1 for r in rows if r["typing"] and _row_is_typed(r)) if any(
            r["typing"] for r in rows) else None,
        # global_funcs deliberately excluded, a sibling function/class/
        # module reference isn't the "depends on hidden state" risk
        # global_vars/unresolved actually are; see analysis.py's
        # _is_definitional().
        "scoped": sum(1 for r in rows if r["global_vars"] or r["unresolved"]),
        "tested": (sum(tested), len(tested)) if tested else None,
        "docs": (sum(d["score"] for d in docs_scored),
                sum(d["applicable"] for d in docs_scored)) if docs_scored else None,
    }


def _row_is_typed(r: dict) -> bool:
    ti = r["typing"]
    if ti["params_total"] == 0:
        return bool(ti["return_typed"])
    return ti["params_typed"] == ti["params_total"] and bool(ti["return_typed"])


def rollup_by_module(rows: list[dict]) -> dict[str, dict]:
    """One rollup per module (`row["module"]`), in the same order the
    modules first appear, for arbital-sized packages, the "which
    module needs the most attention" view `audit`'s flat per-function
    table doesn't answer on its own."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["module"], []).append(r)
    return {module: rollup_stats(group_rows) for module, group_rows in groups.items()}


def rollup_by_target(rows: list[dict], targets: list[str]) -> dict[str, dict]:
    """One rollup per originally-requested target (`mathema audit pkg1
    pkg2` rolls up separately per package, not just one combined total)
   ; a row belongs to whichever target is a prefix of its module name,
    the longest one if more than one matches."""
    groups: dict[str, list[dict]] = {t: [] for t in targets}
    for r in rows:
        module = r["module"] or ""
        matches = [t for t in targets if module == t or module.startswith(t + ".")]
        if matches:
            groups[max(matches, key=len)].append(r)
    return {t: rollup_stats(group_rows) for t, group_rows in groups.items() if group_rows}


def write_stubs(targets: list[str], root: str = ".") -> list[str]:
    """For every discovered function with zero claims (any surface),
    add a bare `claims: []` declared entry, an explicit, empty
    placeholder to fill in, not a claim. One file per source module
    (`claims/<module>.claims.yaml`), matching the natural one-file-per-
    module convention. Additive and idempotent: an existing file's
    content is read and only missing keys are appended, a key already
    present (claimed or already stubbed) is never touched, so this is
    safe to re-run as a target package grows. Returns the list of files
    written or updated."""
    import yaml

    from .spec import load_declared, write_yaml

    functions = discover(targets)
    declared = load_declared(root)
    by_module: dict[str, list[str]] = {}
    for key, fn in sorted(functions.items()):
        if claimed_count(key, fn, declared) > 0:
            continue
        by_module.setdefault(fn.__module__, []).append(key)

    written = []
    for module, keys in by_module.items():
        rel_path = os.path.join("claims", f"{module}.claims.yaml")
        path = os.path.join(root, rel_path)
        existing: dict = {}
        if os.path.exists(path):
            existing = yaml.safe_load(open(path)) or {}
            if not isinstance(existing, dict):
                existing = {}
        new_keys = [k for k in keys if k not in existing]
        if not new_keys:
            continue
        for k in new_keys:
            existing[k] = {"claims": []}
        write_yaml(path, existing,
                   header=f"mathema init: bare declared stubs for {module} "
                          "(fill in claims; an empty list means nothing declared yet)")
        written.append(rel_path)
    return written



def _with_scope_status(intent, root: str, key: str):
    """Intent:
        Annotate a module/project intent dict with its acceptance
        status ("documented" when a live scope acceptance matches the
        text, "stale" when the text moved on), shape labels
        (explicit/implicit) describe the SOURCE, this describes the
        rung.
    """
    if not intent:
        return intent
    from .acceptance import scope_intent_status
    status = scope_intent_status(root, key, intent.get("text"))
    if status:
        intent = dict(intent)
        intent["accepted"] = status
    return intent

def build_index(targets: list[str], root: str = ".") -> dict:
    """The global index record: one navigable summary of a codebase for
    the verified layer, the project's own intent (README), every
    module with its module-level intent (docstring `Intent:` block or
    first paragraph, else a README.md beside the module's own file),
    and every discovered function key with its source file and line
    number, marked verified when a record exists. The point is that an
    agent (or a person) can go from "what is this codebase / where is
    that function" to the exact file and line, and to the right
    per-function spec, without grepping around.

    Same discovery scope as `mathema audit` (`discover()`), so the
    index lines up key-for-key with the declared/verified stores."""
    from .docstring import _read_module_intent, _read_readme_intent
    from .spec import load_verified

    verified = load_verified(root)
    root_abs = os.path.abspath(root)

    modules: dict[str, dict] = {}
    for key, fn in sorted(discover(targets).items()):
        module_name = getattr(fn, "__module__", "") or ""
        entry = modules.get(module_name)
        if entry is None:
            mod = sys.modules.get(module_name)
            file_path, src = None, None
            try:
                src = inspect.getsourcefile(mod) if mod else None
            except TypeError:
                src = None
            if src:
                file_path = os.path.relpath(src, root_abs)
            intent = _read_module_intent(mod) if mod else None
            if intent is None and src:
                readme = os.path.join(os.path.dirname(src), "README.md")
                if os.path.exists(readme):
                    with open(readme) as fh:
                        intent = _read_readme_intent(fh.read())
            module_concepts: list = []
            from .analysis import _parse_concepts_marker
            module_concepts = _parse_concepts_marker(
                getattr(mod, "__doc__", None) or "")
            if not module_concepts and src:
                readme = os.path.join(os.path.dirname(src), "README.md")
                if os.path.exists(readme):
                    with open(readme) as fh:
                        module_concepts = _readme_concepts(fh.read())
            entry = modules[module_name] = {
                "name": module_name, "file": file_path,
                "intent": _with_scope_status(intent, root, module_name),
                "concepts": module_concepts,
                "functions": [],
            }
        line = getattr(getattr(fn, "__code__", None), "co_firstlineno", None)
        # everything an agent needs to go straight to the code and the
        # record, no grepping and no joins: the root-relative file
        # repeated per function, the sed-address source span, and the
        # verified record's own path when one exists
        ventry = (verified.get(key) or {}).get("entry") or {}
        entry["functions"].append({
            "key": key, "name": key.rpartition(".")[2], "line": line,
            "file": entry["file"],
            "span": _source_span(fn),
            "verified": key in verified,
            "spec": (os.path.join(".mathema", "verified", f"{key}.yaml")
                     if key in verified else None),
            "declared": (os.path.join(".mathema", "declared",
                                      f"{key}.yaml")
                         if os.path.exists(os.path.join(
                             root_abs, ".mathema", "declared",
                             f"{key}.yaml")) else None),
            "concepts": (list((ventry.get("meta") or {}).get("concepts")
                              or [])
                         or _row_concepts(key, fn, {}, verified)),
        })

    from . import __version__
    from .spec import SPEC_VERSION
    return {
        "intent": _with_scope_status(_read_readme_intent_at(root),
                                     root, "__project__"),
        "modules": [modules[m] for m in sorted(modules)],
        "lineage": {"generated_by": f"mathema {__version__}",
                    "CDD_spec_version": SPEC_VERSION,
                    "date": datetime.date.today().isoformat()},
    }


def _readme_concepts(readme: str) -> list:
    """Intent:
        A module README's declared concepts: a `Concepts:`/`Tags:`
        line or block, or a `# Concepts`-style markdown heading whose
        section body lists the tokens.
    """
    import re as _re

    from .analysis import _parse_concepts_marker
    from .concepts import parse_concepts

    tokens = _parse_concepts_marker(readme)
    if tokens:
        return tokens
    m = _re.search(r"^#+\s*(Concepts|Tags)\s*$\n(.*?)(?=^#|\Z)", readme,
                   _re.IGNORECASE | _re.MULTILINE | _re.DOTALL)
    if m:
        return parse_concepts(m.group(2))
    return []


def _read_readme_intent_at(root: str):
    """The codebase-level intent from `<root>/README.md`, or None."""
    from .docstring import _read_readme_intent
    path = os.path.join(root, "README.md")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return _read_readme_intent(fh.read())


def write_index(targets: list[str], root: str = ".") -> str:
    """Build the global index (`build_index`) and write it to
    `<root>/.mathema/index.yaml`, beside the specs store, not inside
    it, so `load_verified()`'s per-function scan never mistakes the
    index for a function record. Returns the path."""
    from .spec import write_yaml
    path = os.path.join(root, ".mathema", "index.yaml")
    return write_yaml(path, {"index": build_index(targets, root=root)},
                      header="mathema index: codebase intent, modules, and "
                             "function keys with source locations, "
                             "regenerated by `mathema audit --index`, not "
                             "hand-edited")
