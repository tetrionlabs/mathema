# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Two more claim-authoring surfaces, per declared-schema.md's "this YAML is
the interchange shape, not the only way to author a claim": a decorator, and
a structured block inside a function's own docstring. Both are declared
claims (asserted before anything runs), so both funnel through the same
`spec.declare()` shape a hand-written `claims.yaml` already produces,
nothing downstream (merge-by-name, `claims_fingerprint()`, `entry_claims()`)
needs to know which surface a claim came from.

`load_declared()` only ever sees files on disk; it has no way to see claims
living on a function object. `declared_from_function()` reads the two
in-process surfaces and merges them; `resolve_declared()` folds that
function-level layer underneath whatever `load_declared()` finds on disk,
file wins per claim name, so a claims.yaml entry can always override a
decorator or docstring claim without editing code.
"""
from __future__ import annotations

import inspect
import re

from .analysis import _read_block
from .conjecture import claim as _claim
from .spec import declare as _declare


def _fn_key(fn) -> str:
    """The dotted key claims are filed under: module.qualname, or bare
    qualname for functions defined at the top level of a script/notebook
    (module in ("", "__main__")), the same convention `write_spec()` and
    `track_claims()` already use, so a decorator/docstring claim files
    under the same key a file-declared entry or a verified record would."""
    mod = getattr(fn, "__module__", "") or ""
    qual = getattr(fn, "__qualname__", getattr(fn, "__name__", "callable"))
    return qual if mod in ("", "__main__") else f"{mod}.{qual}"


def _authored_tag(fn, surface: str) -> str:
    """`module.qualname:decorator:L<lineno>` (or `:docstring:...`), the
    origin-reference string a claim's `authored.ref` carries (the
    verified-shape schema's worked example). `co_firstlineno` is used rather
    than `inspect.getsourcelines()` because it needs no source file to be
    readable (a doc-only/compiled callable would raise there) and, unlike
    `getsourcelines`, resolves to the `def` line consistently regardless of
    how many decorators sit above it."""
    lineno = getattr(getattr(fn, "__code__", None), "co_firstlineno", None)
    key = _fn_key(fn)
    return f"{key}:{surface}:L{lineno}" if lineno else f"{key}:{surface}"


def _authored_entry(fn, surface: str, *, ref_surface: str | None = None) -> dict:
    """A declared claim's `authored` object: the authoring-surface kind
    plus the origin reference that traces the claim to its definition
    site. Only `surface` is required by the record schema; `ref` is the
    line-level attribution this tool can always compute for code-borne
    surfaces. A tool-extracted claim (enforce_domain's rejection claim,
    say) keeps `surface: decorator` and names its mechanism in the ref."""
    return {"surface": surface,
            "ref": _authored_tag(fn, ref_surface or surface)}


def claims(*items, source: str = "decorator"):
    """Stamp claims directly onto a function, as declared-dict data (not a
    wrapper): the function object is returned unchanged, same zero-overhead
    precedent as `track_claims`.

        @claims("f(-x) == -f(x)", "f(x) >= 0")
        def my_fn(x): ...

        @claims(claim("f(x) == g(x)", route="derive"))
        def my_fn2(x): ...

    Each item is either a law string (parsed via `conjecture.claim()`,
    exactly like `entry_claims()`/`check_conjectures()` already accept
    mixed string/Conjecture input elsewhere) or an already-built
    `Conjecture`. Every item normalizes to a Conjecture, then to
    declared-schema.md's dict shape via `spec.declare()`, with an
    `authored` provenance field added. Stacking `@claims` more than once
    on the same function merges by claim name; the decorator closest to
    `def` (applied first) loses ties, since the outer decorator's claims
    are what a reader sees applied last, right above the signature.
    """
    def decorator(fn):
        from .types import matrix_param_names
        tag = _authored_entry(fn, "decorator")
        mats = matrix_param_names(fn)
        declared = []
        for item in items:
            cj = (_claim(item, source=source, matrix_names=mats)
                  if isinstance(item, str) else item)
            d = _declare(cj)
            d["authored"] = tag
            declared.append(d)
        existing = list(getattr(fn, "__mathema_claims__", []) or [])
        by_name = {c.get("name"): c for c in existing}
        by_name.update({c.get("name"): c for c in declared})
        fn.__mathema_claims__ = list(by_name.values())
        return fn
    return decorator


# ---------------------------------------------------------------------------
# The docstring surface
#
# Syntax: a "Claims:" block, Google/Napoleon-style (one header line
# ending in `:`) rather than intent.py's numpydoc dash-underline
# sections; a claims block is list-like, one claim per line, not
# prose, so the dash-underline's second line of typing buys nothing;
# `Claims:` also stays invisible to intent.py's own section parser
# (which only looks for dash-underlined headers), so the two coexist
# in the same docstring without either misreading the other's block.
# One claim per line, flush-indented under the header,
# `name [route]: statement`. `route` is optional (defaults to "best": derive when it can, probe otherwise).
# `statement` is handed to conjecture.claim() unchanged, so it accepts the
# full existing law grammar including an inline domain quantifier:
#
#     def my_fn(x: float) -> float:
#         """One-line summary.
#
#         Claims:
#             odd: f(-x) == -f(x)
#             nonneg [derive]: f(x) >= 0
#             exact [derive:math_only]: f(x) - f(x) == 0
#             bounded: for x in [0, 1], f(x) <= 1
#         """
# ---------------------------------------------------------------------------

_CLAIMS_HEADER = "claims:"
_CLAIM_LINE = re.compile(
    r"^\s*(?P<name>[A-Za-z_]\w*)"
    r"(?:\s*\[\s*(?P<route>derive:math_only|derive|probe)\s*\])?"
    r"\s*:\s*(?P<statement>.+?)\s*$"
)


def parse_docstring_claims(doc: str,
                           matrix_names: frozenset = frozenset()) -> list[dict]:
    """Parse a `Claims:` block out of a docstring into declared-dict shape
    (the same shape `spec.declare()` produces). No `Claims:` section, or an
    empty/missing docstring, returns `[]`, never an error; most docstrings
    have no claims in them at all. `matrix_names` are the function's
    matrix parameters (from its signature), so a docstring claim reads
    the matrix sugar (`A^T`, `|A|`) the right way, exactly as
    `check_conjectures` resolves it at adjudication time."""
    lines = _read_block(doc, _CLAIMS_HEADER)
    if lines is None:
        return []
    out: list[dict] = []
    for line in lines:
        m = _CLAIM_LINE.match(line)
        if m is None:
            continue   # not a recognizable claim line; skip, don't error
        cj = _claim(m.group("statement"), name=m.group("name"),
                   route=m.group("route") or "best", source="docstring",
                   matrix_names=matrix_names)
        out.append(_declare(cj))
    return out


# ---------------------------------------------------------------------------
# Merge: function-level (decorator + docstring) → combined with the file
# layer, at the precedence load_declared() already implements for files.
# ---------------------------------------------------------------------------

def declared_from_function(fn) -> list[dict]:
    """Every claim declared directly on a live function object: decorator
    claims (`fn.__mathema_claims__`) plus docstring claims (parsed from
    `inspect.getdoc(fn)`), merged by claim name.

    Precedence: **decorator wins over docstring** on a name collision. The
    decorator is structured data, parsed once at decoration time, the same
    moment a syntax error in a law string would surface as an exception
    right at import; while the docstring block is prose a reader can edit
    without re-running anything. Structured-and-eagerly-checked beats
    freeform-and-silently-stale, so the decorator's version of a claim with
    the same name is treated as the more deliberate statement of the two.
    Docstring-only claims (no decorator claim of that name) still pass
    through untouched.

    A claim's `authored` field is filled in with a `:docstring:` provenance
    tag for entries that don't already carry one from `claims()` (i.e.
    docstring-only claims); decorator claims keep the tag `claims()` set at
    decoration time.
    """

    from .types import matrix_param_names
    doc_claims = parse_docstring_claims(inspect.getdoc(fn) or "",
                                        matrix_param_names(fn))
    decorator_claims = list(getattr(fn, "__mathema_claims__", []) or [])
    tag = _authored_entry(fn, "docstring")
    for c in doc_claims:
        c.setdefault("authored", dict(tag))

    by_name = {c.get("name"): c for c in doc_claims}
    by_name.update({c.get("name"): c for c in decorator_claims})
    return list(by_name.values())


def resolve_declared(fn, key: str | None = None, root: str = ".", *,
                     file_entry: dict | None = None) -> dict:
    """The full declared entry for `fn`, at the correct three-surface
    precedence: file-declared claims (`load_declared()`, from
    `*.claims.yaml`/`claims/*.yaml`/`claimspec.yaml` on disk) win per claim
    name over decorator/docstring claims declared directly on the function.
    Function-level authorship is the lowest-precedence declared source,
    exactly mirroring `load_declared()`'s own shallow-file-loses-to-
    deep-file rule, just one layer further out: a hand-written claims file
    is the most deliberate, most reviewable place to override a claim, so
    it always gets the last word.

    Returns a `{"claims": [...]}`-shaped entry, ready for
    `spec.entry_claims()`. Reuses `spec.merge_entries()` (claims-merge-by-
    name, already correct) rather than reimplementing that merge here.
    A caller that already holds the file-side entry (a sweep that loaded
    the whole declared store once, or an explicit claim list standing in
    for one) passes it as `file_entry` instead of `key`/`root`, the
    same merge at the same precedence, without a per-function store
    re-read. This is the ONE place function-declared claims merge with
    an overlay; the pattern used to be open-coded at six call sites.
    """
    from .spec import merge_entries, load_declared

    func_entry = {"claims": declared_from_function(fn)}
    if file_entry is None:
        file_entry = load_declared(root).get(key, {}).get("entry", {})
    return merge_entries(func_entry, file_entry)


def retrieve(fn_or_key, root: str = ".", *, store: dict | None = None) -> dict:
    """The one read entry point for the declared layer: the full declared
    entry for a function, with the file store joined in.

        retrieve(my_fn)                      # cwd project store
        retrieve(my_fn, root=repo_root)
        retrieve("pkg.mod.fn", root=repo_root)

    Accepts the live function object or its dotted key (a key is
    resolved to the function through `targets`, so decorator/docstring
    surfaces still contribute). The result is `resolve_declared()`'s
    merge at the documented precedence; file-declared claims win per
    name over decorator/docstring claims, shaped `{"claims": [...]}`
    and ready for `check(declared=...)` or `spec.entry_claims()`.

    `check()` itself never reads the filesystem; this function is the
    IO boundary, and every caller that wants the file surface joins it
    explicitly through here. A sweep that already loaded the whole
    declared store once passes it as `store` (the mapping
    `spec.load_declared()` returns) to skip the per-function re-read.
    The store layout under `root` is this function's implementation
    detail, so a different storage location later changes only here.
    """
    if callable(fn_or_key):
        fn, key = fn_or_key, _fn_key(fn_or_key)
    else:
        from .targets import resolve_function
        key, fn = resolve_function(str(fn_or_key), root)
    if store is None:
        from .spec import load_declared
        store = load_declared(root)
    file_entry = (store.get(key) or {}).get("entry", {})
    entry = resolve_declared(fn, file_entry=file_entry)
    from .concepts import dismissed_concepts
    dismissed = dismissed_concepts(root, key)
    if dismissed:
        # curation from .mathema/meta rides the declared entry's meta
        entry = dict(entry)
        meta = dict(entry.get("meta") or {})
        meta.setdefault("mathema.concepts_dismissed", dismissed)
        entry["meta"] = meta
    return entry


def materialize_declared(fn, key: str, root: str = ".") -> str:
    """Write `fn`'s decorator/docstring-derived declared claims, NOT the
    file-merged result of resolve_declared(), just what lives on the live
    function object, to `.mathema/declared/<key>.yaml`, mirroring how
    `spec.record()` writes the machine-verified layer under
    `.mathema/verified/<key>.yaml`.

    This file exists for cross-tool/cross-language interchange and human
    inspection (a decorator or a docstring block is Python-only; the YAML
    it produces is the portable shape any conformant tool can read). It is
    not consulted by `resolve_declared()` or `declared_from_function()`,
    which read the live function directly, regenerate this file as often
    as convenient, and never hand-edit it.
    """
    import os

    from .spec import write_yaml

    entry = {"claims": declared_from_function(fn)}
    path = os.path.join(root, ".mathema", "declared", f"{key}.yaml")
    return write_yaml(path, {key: entry},
                      header=f"machine-generated from decorator/docstring claims "
                             f"on {key}; regenerated on every "
                             f"materialize_declared() call, not meant for "
                             f"hand-editing")


# ---------------------------------------------------------------------------
# Enforcement, not declaration
#
# Every surface above stamps a *claim* onto a function without touching how
# it runs; claims() famously returns fn unchanged. enforce_domain() is a
# different kind of thing on purpose: audit --deriv-report and the
# domain_enforced[...] probe (strict=True) both exist to *find* a function
# that silently accepts an out-of-domain parameter instead of guarding
# against it, but neither one fixes that gap, only reports it. This is the
# fix: a real wrapper that turns a declared domain into a runtime check,
# without editing the function body to add it by hand.
# ---------------------------------------------------------------------------

class DomainError(ValueError):
    """A parameter's actual value, or a domain declaration itself,
    conflicts with a function's own declared domain, raised by
    `enforce_domain()`, both at decoration time (two declared claims,
    or an explicit `domain=` and a declared claim, disagree about the
    same parameter's interval) and at call time (a real argument value
    falls outside it). One specific, catchable type for both, rather
    than a generic ValueError a caller can't distinguish from an
    unrelated one, still a ValueError underneath, so existing
    `except ValueError` handling keeps working unchanged."""


def _domain_from_declared_claims(fn, key: str | None, root: str) -> dict:
    """Every `for p in [lo, hi]: ...`-quantified interval already declared
    on `fn`'s own claims (decorator, docstring, and; if `key` is given,
    a claims.yaml file too, via `resolve_declared()`), collapsed to a
    single `{param: (lo, hi)}` dict. This is `enforce_domain()`'s real
    source of truth: a claim's own stated domain and the runtime guard
    both come from here, never two independently-typed numbers. Only an
    unambiguous interval bound is picked up, either `declare()`'s
    current `{"lo", "hi", ...}` dict encoding, or the legacy `[lo, hi]`
    list shape a claim declared before this encoding changed may still
    carry, a `"Z"`/`"N"`/discrete-set claim domain isn't auto-derived
    this way (`enforce_domain()`'s own runtime guard only ever checks
    numeric-range containment; picking those up here would need new
    guard logic this function doesn't add). Raises immediately if two
    declared claims disagree on the same parameter's interval; that
    disagreement is exactly the kind of divergence this function exists
    to catch before it reaches a runtime guard."""
    from .grammar import Interval

    entries = declared_from_function(fn)
    if key is not None:
        from .spec import merge_entries, load_declared
        file_entry = load_declared(root).get(key, {}).get("entry", {})
        entries = merge_entries({"claims": declared_from_function(fn)},
                                 file_entry)["claims"]
    out: dict = {}
    for c in entries:
        for p, bounds in (c.get("domain") or {}).items():
            if isinstance(bounds, list) and len(bounds) == 2 \
                    and all(isinstance(v, (int, float)) for v in bounds):
                interval = tuple(bounds)
            elif isinstance(bounds, dict) and "lo" in bounds and "hi" in bounds:
                interval = Interval(bounds["lo"], bounds["hi"],
                                    closed_lo=bounds.get("closed_lo", True),
                                    closed_hi=bounds.get("closed_hi", True))
            else:
                continue
            if p in out and out[p] != interval:
                raise DomainError(
                    f"enforce_domain(): declared claims on {fn.__name__!r} "
                    f"disagree on {p!r}'s domain ({out[p]} vs {interval})")
            out[p] = interval
    return out


def enforce_domain(domain: dict | None = None, key: str | None = None,
                   root: str = "."):
    """Decorator: wrap a function so a call with an out-of-domain
    parameter value raises `ValueError` before the real function ever
    runs, instead of silently proceeding on data its own declared
    domain says it should not accept, the gap `domain_enforced[...]`
    (`mathema.check(fn, domain=..., strict=True)`) finds and reports,
    turned into an actual guard, with no change to the function body.

        @enforce_domain()   # picks up "for alpha in [0, 1], ..." automatically
        @claims_decorator("for alpha in [0, 1], f(x, alpha) <= max(x)")
        def ema(x: list, alpha: float) -> float:
            ...

        ema([1.0, 2.0], 1.5)   # raises ValueError: alpha=1.5 is outside [0, 1]

    The enforced domain is never a second, independently-typed copy of
    what a claim already states: every parameter interval declared on
    `fn`'s own claims (decorator, docstring, and a claims.yaml file too
    if `key`/`root` are given) is picked up automatically (see
    `_domain_from_declared_claims()`), merged with whatever
    `types.domain_from_signature()` infers from `Probability`/
    `Positive`/`Nonnegative` markers. An explicit `domain=` bound is
    only ever a convenience for a parameter with no declared-claim
    domain of its own; for one that already has one, it must match
    exactly, or this raises at decoration time rather than silently
    picking a value and letting the two drift apart. Every domain shape
    `check()` accepts is enforced here too: an `(lo, hi)` interval,
    `"Z"`/`"N"` (integer / non-negative integer), and an explicit
    discrete set (only reachable via an explicit `domain=`, since a
    declared claim's own set-shaped domain isn't auto-derived, see
    `_domain_from_declared_claims()`). A parameter no source says
    anything about is left unchecked; this only ever narrows what a
    function accepts, never widens it, so composing it with the
    function's own existing guards (if any) is always safe."""
    def decorator(fn):
        import functools
        import inspect

        from .grammar import is_missing, domain_contains, render_domain
        from .types import domain_from_signature

        declared_domain = _domain_from_declared_claims(fn, key, root)
        explicit = domain or {}
        for p, bounds in explicit.items():
            if p in declared_domain and declared_domain[p] != tuple(bounds):
                raise DomainError(
                    f"enforce_domain(): explicit domain for {p!r} {tuple(bounds)} "
                    f"conflicts with the declared claim domain "
                    f"{declared_domain[p]} on {fn.__name__!r}; these must "
                    "not diverge")
        merged_domain = {**domain_from_signature(fn), **declared_domain, **explicit}
        sig = inspect.signature(fn)

        def _check_scalar(value, bounds) -> bool:
            """`True` when `value` is a candidate this `bounds` shape
            could ever be violated by, an `Interval`/`"Z"`/`"N"`/a
            `Domain` with no discrete-set piece can only ever be
            satisfied or violated by a number, so a non-numeric value
            (a string, say) was always silently exempt rather than
            flagged, and stays that way; a discrete-set-shaped bound
            (a bare `frozenset`, or a `Domain` with at least one) has
            no such restriction, `domain_contains()` itself already
            knows how to test membership for any hashable value.
            Missingness is checked *before* any of that, unconditionally;
            it's an orthogonal axis from "is this bound shape
            numeric", not a special case of "not a number", so the
            numeric-only exemption above must never also silently
            exempt a missing value from a domain that explicitly
            excludes it."""
            if is_missing(value):
                return domain_contains(value, bounds)
            numeric_only = (isinstance(bounds, (str, tuple))
                            or (hasattr(bounds, "pieces")
                                and not any(isinstance(p, frozenset) for p in bounds.pieces)))
            if numeric_only and isinstance(value, complex) \
                    and not isinstance(value, (int, float)):
                # a complex value IS a candidate against a numeric
                # bound: domain_contains reads a zero-imaginary complex
                # as the real number it equals and rejects a genuinely
                # imaginary one, never silently exempt.
                return domain_contains(value, bounds)
            if numeric_only and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                return True   # not a candidate, exempt, not a violation
            return domain_contains(value, bounds)

        def _violation(name: str, value) -> str | None:
            bounds = merged_domain.get(name)
            if bounds is None:
                return None
            # A sequence-valued argument (list/tuple/array/Series, any
            # real iterable that isn't itself a string/bytes/mapping) is
            # checked element by element against the same domain a
            # scalar parameter of that name would be, previously
            # unconditionally skipped ("not a numeric value") for every
            # non-numeric value, so a list/array-typed parameter had no
            # domain enforcement at all, missing values or otherwise.
            # `domain_contains()` itself decides whether a
            # missing element is exempt (allowed unless the domain
            # explicitly excludes it); this loop doesn't special-case
            # missingness at all, it's just one more value to check.
            if isinstance(value, (list, tuple)) or (
                    hasattr(value, "__iter__") and not isinstance(value, (str, bytes, dict))):
                for i, el in enumerate(value):
                    if not _check_scalar(el, bounds):
                        return (f"has element {i} ({el!r}) outside its declared "
                                f"domain {render_domain(bounds, show_missing=True)}")
                return None
            if not _check_scalar(value, bounds):
                return f"outside its declared domain {render_domain(bounds, show_missing=True)}"
            return None

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            for name, value in bound.arguments.items():
                problem = _violation(name, value)
                if problem is not None:
                    raise DomainError(f"{fn.__name__}(): {name}={value!r} {problem}")
            return fn(*args, **kwargs)

        wrapper.__mathema_enforced_domain__ = merged_domain
        # the decorator that MAKES out-of-domain rejection true also
        # DECLARES it: one excluded_outside_domain claim per enforced
        # parameter joins the decorator claims surface, so check()
        # adjudicates the enforcement like any other declared claim
        # (proven structurally, rejection by construction)
        auto_declared = []
        for p in sorted(merged_domain):
            d = _declare(_claim(f"excluded_outside_domain({p})"))
            d["authored"] = _authored_entry(fn, "decorator",
                                            ref_surface="enforce_domain")
            auto_declared.append(d)
        existing = list(getattr(wrapper, "__mathema_claims__", []) or [])
        by_name = {c.get("name"): c for c in existing}
        by_name.update({c.get("name"): c for c in auto_declared})
        wrapper.__mathema_claims__ = list(by_name.values())
        return wrapper
    return decorator


def enforce_dimensions(key: str | None = None, root: str = "."):
    """Decorator: wrap a function so a call whose arguments violate a
    declared DIMENSION premise raises `ValueError` before the real
    function runs. The shape analogue of `@enforce_domain`; where that
    guards a parameter's value domain, this guards the relations
    between argument shapes a claim states as its precondition.

        @enforce_dimensions()
        @claims_decorator("assuming len(x) == len(y), f(x, y) == f(y, x)")
        def dot(x: list, y: list) -> float:
            return sum(a * b for a, b in zip(x, y))

        dot([1.0, 2.0], [3.0])   # raises ValueError: dim(x, 0)=2 != dim(y, 0)=1

    Every `assuming dim(<arg>, <axis>) <rel> dim(<arg>, <axis>)` and
    `... <rel> <const>` premise on the function's own claims (decorator,
    docstring, and a claims.yaml file when `key`/`root` are given) is
    enforced. `dim(x, 0)` reads the outer length; a higher axis reads
    into nested sequences and raises the same honest `IndexError` an
    over-indexed axis always does. A premise mentioning anything but a
    plain argument dimension against another or a constant is left to
    adjudication, never guessed at runtime. Purely narrowing: a call
    the premises admit reaches the real function unchanged.

    This never makes a claim true by fiat, exactly as `@enforce_domain`
    does not: it makes the function REJECT inputs the claim was never
    about, so `assuming <premise>, <law>` and a guard for `<premise>`
    are the same precondition stated once."""
    import ast
    import functools
    import inspect

    from .grammar import extract_assuming_clause, normalize

    def _premises(fn) -> list:
        entries = declared_from_function(fn)
        if key is not None:
            from .spec import load_declared, merge_entries
            file_entry = load_declared(root).get(key, {}).get("entry", {})
            entries = merge_entries({"claims": declared_from_function(fn)},
                                    file_entry)["claims"]
        out: list = []
        for c in entries:
            statement = c.get("statement") or c.get("law") or ""
            clause, _ = extract_assuming_clause(normalize(statement))
            if not clause:
                continue
            body = clause[len("assuming "):] if clause.startswith(
                "assuming ") else clause
            for part in body.split(" and "):
                rel = next((r for r in ("==", "!=", ">=", "<=", ">", "<")
                            if r in part), None)
                if rel is None:
                    continue
                lhs, rhs = part.split(rel, 1)
                out.append((lhs.strip(), rel, rhs.strip()))
        return out

    def _dim_ref(text):
        try:
            node = ast.parse(text, mode="eval").body
        except SyntaxError:
            return None
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "dim" and len(node.args) == 2
                and isinstance(node.args[0], ast.Name)
                and isinstance(node.args[1], ast.Constant)):
            return (node.args[0].id, int(node.args[1].value))
        return None

    def _const(text):
        try:
            v = ast.literal_eval(text)
            return v if isinstance(v, (int, float)) else None
        except Exception:
            return None

    def _measure(value, axis):
        v = value
        for _ in range(axis):
            v = v[0]
        return len(v)

    _OPS = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b,
            ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b, "<": lambda a, b: a < b}

    def decorator(fn):
        premises = _premises(fn)
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            av = bound.arguments
            for lhs, rel, rhs in premises:
                left = _dim_ref(lhs)
                if left is None or left[0] not in av:
                    continue
                lval = _measure(av[left[0]], left[1])
                right = _dim_ref(rhs)
                if right is not None and right[0] in av:
                    rval = _measure(av[right[0]], right[1])
                    rdesc = f"dim({right[0]}, {right[1]})={rval}"
                else:
                    rval = _const(rhs)
                    if rval is None:
                        continue
                    rdesc = str(rval)
                if not _OPS[rel](lval, rval):
                    raise ValueError(
                        f"{fn.__name__}: dim({left[0]}, {left[1]})={lval} "
                        f"violates the declared premise "
                        f"dim({left[0]}, {left[1]}) {rel} {rdesc}")
            return fn(*args, **kwargs)
        return wrapper

    return decorator


def enforce_structure(key: str | None = None, root: str = "."):
    """Decorator: wrap a function so a call whose matrix argument lacks
    a declared STRUCTURE raises `ValueError` before the real function
    runs. The structure analogue of `@enforce_domain` (value domains)
    and `@enforce_dimensions` (shape relations): here the guard is a
    matrix property (symmetric, positive-definite, finite, ...).

        @enforce_structure()
        def solve(a: Mat("n", "n", PositiveDefinite), b: Vec("n")):
            ...

        solve([[1, 2], [3, 4]], [1, 2])   # ValueError: a is not
                                          # is_positive_definite

    Every structure declared on a parameter is enforced: a signature
    marker (`Mat(..., Symmetric)`) and a `is_<prop>(param)` claim on
    the function (decorator, docstring, and a claims.yaml file when
    `key`/`root` are given), entailment-closed, so a
    `PositiveDefinite` marker also enforces symmetry. A property the
    registry cannot decide for an argument (a spectral check with no
    numpy) is skipped rather than raising, never a false rejection.

    Like `@enforce_domain`, it makes the function REJECT inputs the
    claim was never about and auto-declares the matching
    `is_<prop>(param)` claim, so `is_<prop>(A)` as a precondition and
    the runtime guard are the same statement made once."""
    import functools
    import inspect

    from . import matrices as _mtx
    from .grammar import parse_domain_safety, normalize

    def _declared(fn) -> dict:
        """{param: entailed props} from signature markers and declared
        is_<prop>(param) claims."""
        from .types import structures_from_signature
        out = {p: set(props)
               for p, props in structures_from_signature(fn).items()}
        entries = declared_from_function(fn)
        if key is not None:
            from .spec import load_declared, merge_entries
            file_entry = load_declared(root).get(key, {}).get("entry", {})
            entries = merge_entries({"claims": declared_from_function(fn)},
                                    file_entry)["claims"]
        for c in entries:
            parsed = parse_domain_safety(
                normalize(c.get("statement") or c.get("law") or ""))
            if (parsed is not None and not parsed[0].startswith("not ")
                    and parsed[0] in _mtx.PROPERTIES
                    and parsed[1].isidentifier()):
                out.setdefault(parsed[1], set()).add(parsed[0])
        return {p: _mtx.entailed(props) for p, props in out.items() if props}

    def decorator(fn):
        declared = _declared(fn)
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            for param, props in declared.items():
                if param not in bound.arguments:
                    continue
                value = bound.arguments[param]
                for prop in sorted(props):
                    if _mtx.PROPERTIES[prop].check(value) is False:
                        raise ValueError(
                            f"{fn.__name__}: {param} is not "
                            f"{prop} ({prop[3:].replace('_', ' ')})")
            return fn(*args, **kwargs)

        # auto-declare the matching predicate claims, as enforce_domain
        # declares excluded_outside_domain, so the guard and the claim
        # are one statement
        auto = []
        for param, props in declared.items():
            for prop in sorted(props):
                d = _declare(_claim(f"{prop}({param})"))
                d["authored"] = _authored_entry(
                    fn, "decorator", ref_surface="enforce_structure")
                auto.append(d)
        existing = list(getattr(wrapper, "__mathema_claims__", []) or [])
        by_name = {c.get("name"): c for c in existing}
        by_name.update({c.get("name"): c for c in auto})
        wrapper.__mathema_claims__ = list(by_name.values())
        return wrapper

    return decorator


def reject_missing(*names: str):
    """Intent:
        Reject a missing value in the named parameters. No bounds
        otherwise.

    Notes:
        Composes enforce_domain with an unrestricted, missing-excluded
        domain per name. No new checking logic.
    """
    from .grammar import Domain, MISSING
    return enforce_domain({n: Domain(excluded=frozenset({MISSING})) for n in names})
