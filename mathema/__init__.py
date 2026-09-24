# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema: Claim-Driven Development, turning software intent into
verifiable evidence.

    import mathema
    r = mathema.check(my_function, claims=["f(-x) == -f(x)"])
    print(r)
    mathema.write_spec(my_function, claims=[...])   # also writes the record

State a claim, verify it against the real function, keep the record. Every
claim is adjudicated on one of two evidence routes: **derive** lifts the
function's body to a sympy expression and decides the claim algebraically
(`proven` is exact, not sampled, see `symbolic.py`), or **probe** calls the
real function on sampled/seeded inputs and checks the claim numerically
(`holds (n=...)`/`falsified`, see `probing.py`). A function that can't be
lifted (a loop, a non-scalar parameter, ...) still gets probe-route
coverage; derive is strictly stronger evidence where it applies, not a
replacement for probe. Every claim binds to the function's identity hashes
so a later change is caught, not silently inherited.

A bare string claim (as above) defaults to the probe route. To ask for a
symbolic proof instead, build the claim with `route="derive"` and pass it
in the same `claims=` list, `mathema.check()` accepts a pre-built claim
object exactly as it accepts a string, so nothing else about the call
changes:

    r = mathema.check(my_function,
                      claims=[mathema.claims.claim("f(-x) == -f(x)", route="derive")])

A `proven`/`falsified` verdict on that entry means the derive route
actually decided it (never sampled); `unknown` means it could not,
covering both a genuinely unliftable function and one it could lift but
the claim itself stayed undecided. `Probe.meta["mathema.derive_status"]`
on the returned entry ("unliftable" vs. "undecided") tells the two
apart programmatically,
see authoring.md's own claim-grammar section for the full grammar
(`d(...)`/`lim(...)`/`integrate(...)`/`Sum(...)`, domain quantifiers,
`raises(...)`) `route="derive"` understands. `mathema.claims` is this same
`claim()`/`check_conjectures()` pair exposed directly, for calling the
derive route standalone without `check()`'s own built-in-law probing:

    results = mathema.claims.check_conjectures(
        my_function, [mathema.claims.claim("f(-x) == -f(x)", route="derive")])

This package implements the Claim-Driven Development spec: see the sibling
`claim-driven-development` repo's `v0.2.0/` for the workflow definition and
the record schema this package reads and writes (`SPEC_VERSION` below
states which version).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .analysis import Facts, SourceUnavailable, _parse_notes, analyze_source
# aliased on import: the bare name `claims` is already the conjecture-module
# alias below (`mathema.claims.check(...)`, load-bearing in README/tests), so
# the claims()-decorator is exposed as `claims_decorator` at this level,
# still directly importable as `from mathema.authoring import claims`.
from .authoring import (DomainError, claims as claims_decorator,
                        declared_from_function, enforce_dimensions, enforce_domain,
                        enforce_structure,
                        materialize_declared, parse_docstring_claims,
                        reject_missing, resolve_declared, retrieve)
from .claim_families import _register_builtin_claim_families
from .conjecture import Conjecture, check_conjectures, claim
from .diagnostics import critical_points
from .compiled import CompiledForm, compile_form, numeric_check
from .forms import (Form, SubstitutedForm, Substitution, closed_forms,
                    executable_forms, register_substitution,
                    substituted_forms)
from .identity import form_hash
from .grammar import get_unicode_output, set_unicode_output
from .probing import Probe, probe
from .reason_codes import Category, ClaimReasonCode, ReasonCode, issue
from .spec import SPEC_VERSION
from .targets import Target, TargetError, resolve, resolve_function
from .verify import GateReport, VerifyResult, gate, verify_project
from .suggest import suggest_claims
# exposed for direct, notebook-style exploration of what a function
# lifts to; `mathema.lift_symbolic`, not bare `lift`, since `lift` is
# too generic a name to claim at this module's own top level. See
# docs/authoring.md's "Exploring a function symbolically" section.
from .symbolic import lift as lift_symbolic
from .symbolic._dot import _register_dot_family
from .symbolic._fold import _register_fold_family
from .symbolic._sum import _register_sum_family

from . import conjecture as claims
from . import spec as registry

import sys as _sys
for _alias, _mod in (("claims", claims), ("registry", registry)):
    _sys.modules[f"{__name__}.{_alias}"] = _mod

# The built-in claim families register here, explicitly, once per
# process, not as an import side effect of the modules that define
# them. Any `mathema.*` import runs this package __init__ first, so the
# registry is always populated before check_conjectures() or try_prove()
# can look a family up.
_register_builtin_claim_families()
_register_dot_family()
_register_fold_family()
_register_sum_family()

__version__ = "0.6.0"
__all__ = ["claim", "check", "write_spec", "retrieve", "analyze",
           "status", "track_claims",
           "tagged", "Record", "claims", "registry", "SPEC_VERSION",
           "__version__", "claims_decorator", "declared_from_function",
           "resolve_declared", "materialize_declared",
           "parse_docstring_claims", "enforce_domain", "enforce_dimensions", "enforce_structure", "reject_missing",
           "DomainError", "docstring_report", "DocstringReport", "lift_symbolic",
           "critical_points", "suggest_claims", "Conjecture",
           "issue", "ReasonCode", "Category", "ClaimReasonCode",
           "get_unicode_output", "set_unicode_output",
           "Form", "SubstitutedForm", "Substitution", "closed_forms",
           "substituted_forms", "register_substitution",
           "resolve", "resolve_function", "Target", "TargetError",
           "gate", "verify_project", "GateReport", "VerifyResult",
           "executable_forms", "CompiledForm", "compile_form",
           "numeric_check", "form_hash"]


@dataclass
class Record:
    """The result of checking a function's claims: the facts read off it,
    and one Probe per claim adjudicated (built-in laws plus any claims
    passed in). See the claim-driven-development repo's
    v0.2.0/record-schema.md for the YAML shape this turns into via
    to_spec()/save_spec()."""
    facts: Facts
    probes: list[Probe]
    spec_path: str | None = None
    # `lifted` holds the derive route's own symbolic-lift result
    # (symbolic.Lifted) when the body lifts to a closed form, None
    # otherwise; every reader treats None as a valid value. `concepts`
    # is reserved for a future understanding/Mathemata layer and is
    # always empty.
    lifted: object | None = field(default=None, repr=False)
    concepts: list = field(default_factory=list, repr=False)
    dependencies: list = field(default_factory=list, repr=False)
    # one-deep callee records (inventory.function_dependencies): every
    # sibling function/class/module this function references, with key,
    # file, line, and (for functions) the form hash freshness checks
    # compare against, written into the verified spec as its own
    # section, annotated with per-dependency freshness at record time.
    # namespaced extension data, the same role Probe.meta already plays
    # for one claim; this is the function-level counterpart, for data
    # that isn't a stable, always-computed field (diagnostics.
    # diagnostic_report(), opted into per function, is the first real
    # user: "mathema.diagnostic_report" -> its own dict). Never
    # populated automatically by check()/write_spec(), a caller sets it
    # explicitly when it wants the extra work done.
    meta: dict = field(default_factory=dict, repr=False)

    def __repr__(self) -> str:
        from .analysis import tier_word
        lines = [f"mathema.Record({self.facts.name}) · {tier_word(self.facts.tier)} "
                f"· form {self.facts.form}"]
        for p in self.probes:
            mark = {"holds": "holds  ", "falsified": "FALSIFY", "proven": "proven ",
                    "skipped": "skip   ", "unknown": "unknown",
                    "invalidated": "INVALID"}.get(p.verdict.split(":", 1)[0], p.verdict)
            if p.verdict == "proven":
                # a proof has no trial count the way a probe does, the
                # statement itself gets prettified into ordinary math
                # notation, and the quantifier (who it holds for) stands
                # in place of "(n=...)", on its own line since it's
                # often longer than the statement it qualifies.
                stmt = p.statement.replace("==", "=").replace("<=", "≤").replace(">=", "≥")
                line = f"  {mark} {p.name}: {stmt}"
                if p.condition:
                    line += f"\n           {p.condition}"
            else:
                line = f"  {mark} {p.name}: {p.statement}"
                if p.verdict == "holds" and p.n:
                    line += f" (n={p.n})"
            if p.counterexample:
                line += f"\n           counterexample {p.counterexample}"
            stratum = getattr(p, "stratum", None)
            if stratum:
                # which stratum the falsification indicts, one line:
                # the verdict above is unchanged, this only classifies
                parts = []
                if stratum.get("mathematics"):
                    parts.append(f"mathematics {stratum['mathematics']}")
                if stratum.get("cause"):
                    parts.append(stratum["cause"])
                elif stratum.get("blame"):
                    parts.append(f"blame {stratum['blame']}")
                if parts:
                    line += f"\n           [{', '.join(parts)}]"
            lines.append(line)
        return "\n".join(lines)

    def to_spec(self) -> dict:
        from .spec import to_spec
        return to_spec(self)

    def save_spec(self, path: str) -> str:
        """Write the decoupled spec: intent, identity, claims, references,
        and the reasoning chain, as standalone YAML bound to the identity
        hashes."""
        from .spec import save_spec
        return save_spec(self, path)


def analyze(fn) -> Facts:
    """Machine-derived facts about a function: parameters, purity, guards,
    structural shape. Pure `ast`, no probing, no claim verification.

    Falls back to a documentation-only record (tier 0) for callables with no
    retrievable Python source (builtins, C extensions): the docstring states
    the intent, and probing still runs against the live callable."""
    injected = getattr(fn, "__mathema_facts__", None)
    if isinstance(injected, Facts):
        # a resolver-built proxy carries the facts its frontend could
        # honestly state (a namespaced form hash, real param kinds,
        # tree=None); they are richer than the doc-only fallback the
        # source-less path below would produce, so they win outright
        return injected
    try:
        facts = analyze_source(fn)
    except SourceUnavailable:
        return _doc_only_facts(fn)
    facts.tier = 3 if not facts.is_pure else 2
    return facts


def _doc_only_facts(fn) -> Facts:
    """A documentation-only record (tier 0) for callables without Python
    source. Intent is the author's documented claim: a real but weak
    evidence class, and the only one available for compiled code."""
    import hashlib
    import inspect

    from .intent import parse_doc

    doc = inspect.getdoc(fn) or ""
    parsed = parse_doc(doc)
    name = getattr(fn, "__name__", "callable")
    try:
        sig = inspect.signature(fn)
        params = [n for n, p in sig.parameters.items()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                  and p.default is p.empty]
        sig_str = str(sig)
    except (ValueError, TypeError):
        params, sig_str = [], "(…)"
        for arity in (1, 2, 3):
            try:
                fn(*[0.5] * arity)
            except TypeError:
                continue
            except Exception:
                pass  # domain error still confirms the arity
            params = [f"x{i}" for i in range(arity)] if arity > 1 else ["x"]
            sig_str = "(" + ", ".join(params) + ")"
            break
    return Facts(
        name=name,
        signature=sig_str,
        params=params,
        param_kinds={p: "unknown" for p in params},
        returns_kind="unknown",
        docstring=doc or None,
        source="<no Python source; documentation-only record>",
        effects=[],
        # purity cannot be established without source: null, per the
        # record schema (and the general rule: a tool never reports a
        # stronger epistemic state than it has a basis for). Probes
        # still check determinism empirically either way.
        is_pure=None,
        loops=[], comprehensions=[], recursion=False, branch_count=0,
        call_groups={"math": [], "builtin": [], "external": []},
        max_loop_depth=0, lines=0,
        form="doc:" + hashlib.sha256((doc or name).encode()).hexdigest()[:8],
        sigh=hashlib.sha256(sig_str.encode()).hexdigest()[:12],
        tier=0, tree=None,
        doc_intent=parsed.summary or None,
        doc_refs=parsed.refs,
        doc_hints=parsed.concept_hints,
        doc_notes=_parse_notes(doc),
    )


def _expand_claim_keywords(claims: list, fn, facts, merged_domain: dict,
                           extensive: bool) -> list:
    """Intent:
        Replace battery keywords inside a claims list with the hazard
        claims they name: `defined` / `excluding` / `stable` /
        `stateless` (and their long/spaced spellings) each expand to
        the RELEVANT members, the same structural gates
        suggest_claims applies decide relevance, so a keyword asks a
        question, never forces an irrelevant claim. Everything else
        (law strings, Conjectures) passes through untouched, and the
        expanded claims carry source "user": a keyword is adoption,
        so its claims gate like any hand-written one.

    Notes:
        A string that is neither a keyword nor parseable as a law,
        but is closely spelled to a keyword, raises with the whole
        keyword vocabulary and its meanings, a near-miss teaches
        the battery rather than failing as a grammar error. Keyword
        claims never carry a route: the safety members are examine
        by construction.
    """
    from dataclasses import replace as _replace

    from .conjecture import InvalidConjecture, claim
    from .families import close_keyword, expand_keyword, keyword_help
    from .suggest import suggest_claims

    out: list = []
    suggested = None
    for item in claims:
        if isinstance(item, dict):
            # the claims-file row shape, accepted at the call site the
            # same way a claims.yaml row is: one shared construction
            # (spec._declared_conjecture), so the two spellings can
            # never parse differently. A row with no `source` of its
            # own is a call-site claim, exactly like a law string here
            from .spec import _declared_conjecture
            row = dict(item)
            row.setdefault("source", "user")
            out.append(_declared_conjecture(row))
            continue
        if not isinstance(item, str):
            out.append(item)
            continue
        member_names = expand_keyword(item)
        if member_names is None:
            try:
                claim(item)
            except InvalidConjecture:
                near = close_keyword(item)
                if near is not None:
                    raise InvalidConjecture(
                        f"unknown claim {item!r}; did you mean the "
                        f"battery keyword {near!r}? keywords: "
                        f"{keyword_help()}") from None
                raise
            out.append(item)
            continue
        if suggested is None:
            suggested = suggest_claims(fn, facts=facts,
                                       extensive=extensive)
        for cj in suggested:
            if cj.name.split("[", 1)[0] in member_names:
                out.append(_replace(cj, source="user"))
        if "excluded_outside_domain" in member_names:
            # never battery-suggested: generated here per parameter
            # with a declared bound (there is no outside otherwise)
            for p in sorted(merged_domain):
                if p in facts.params:
                    out.append(claim(f"excluded_outside_domain({p})"))
    return out


def _refuse_name_collisions(entries: list) -> list:
    """Intent:
        The claims a check adjudicates, keyed by name: an exact
        duplicate (same name, statement and domain) is one claim, and
        two distinct claims under one name are refused.

    Raises:
        InvalidConjecture: when two distinct claims take the same name
            (four domain variants of one law all auto-name `f_mi_ge_0`,
            say), since a name keys the claim's pins, locks and
            verified row and cannot stand for two claims.
    """
    import json

    from .conjecture import InvalidConjecture

    def _stmt(c):
        return c.get("statement") or c.get("law")

    def _identity(c):
        # the full identity, statement and domain: a domain lives in its
        # own field, not the (domain-stripped) statement
        return (c.get("name"), _stmt(c),
                json.dumps(c.get("domain") or {}, sort_keys=True,
                           default=str))

    seen: dict = {}
    for c in entries:
        seen.setdefault(_identity(c), c)
    by_name: dict = {}
    for c in seen.values():
        prior = by_name.setdefault(c.get("name"), c)
        if prior is not c:
            raise InvalidConjecture(
                f"two claims take the name {c.get('name')!r} "
                f"({_stmt(prior)!r} and {_stmt(c)!r}); give each an "
                f"explicit name (claim(..., name=...), or `name:` in a "
                f"claims file)")
    return list(seen.values())


def _domains_from_claims(claims) -> dict:
    """Intent:
        The parameter domains declared by the `for` quantifiers of the
        claims being checked, so the built-in battery samples inside the
        region their author actually declared.

    Notes:
        A claim that will not parse is ignored here and reported by the
        ordinary path instead, so this never changes which errors a
        caller sees. Where two claims bound the same parameter, the
        first stands: the battery only needs one legal region to
        synthesise a call in, and each claim is still adjudicated
        against its own domain regardless.
    """
    from .conjecture import claim as _claim

    out: dict = {}
    for c in claims or ():
        try:
            parsed = _claim(c) if isinstance(c, str) else c
        except Exception:
            continue
        for name, bound in (getattr(parsed, "domain", None) or {}).items():
            out.setdefault(name, bound)
    return out


def check(fn, claims: list | None = None, domain: dict | None = None,
         trials: int | None = None,
         trials_scale: float = 1.0, extensive: bool = False,
         declared: dict | None = None,
         known_premises: dict | None = None) -> Record:
    """Verify a function's claims, each adjudicated against the real
    function.

        mathema.check(ema)                                    # + suggested claims
        mathema.check(ema, claims=["f(x, 1.0) == x[-1]"])      # add a claim
        mathema.check(ema, claims=[])                          # declared surfaces only
        mathema.check(ema, domain={"alpha": (0, 1)})
        mathema.check(ema, declared=mathema.retrieve(ema))     # + file claims

    check is IO-free: it reads only what travels with the function
    object (decorator, docstring, type markers) and never touches the
    filesystem. The file-declared layer, the highest-precedence
    authoring surface, therefore reaches it only through `declared=`,
    a retrieved entry from `mathema.retrieve(fn, root)`. Call-site
    `claims=` still wins per claim name over everything retrieved.
    `write_spec()`, the CLI, and the MCP tools do this join for you;
    a bare `check(fn)` adjudicates the function-attached surfaces only.

    `claims` omitted (`None`) defaults to `suggest_claims(fn)`'s
    own proposals, monotonicity/affine-ness/convexity, symmetry,
    idempotence, commutativity/associativity, raises(...) guards, each
    adjudicated at the best evidence level actually available (a proof
    when the function lifts, probing otherwise, see suggest_claims()'s
    own docstring). `claims=[]` (an explicit empty list, not merely
    omitted) means declared surfaces only: no suggested claims are
    added, while the built-in structural probes and the function's own
    decorator/docstring/type-marker claims still run, and so does a
    `declared=` entry when one is passed. Any other explicit `claims=[...]` is
    checked as given, unioned with whatever the function's own decorator
    or docstring declares.

    `domain` declares parameter limits: algebraic probes sample inside
    the declared domain. Whether the code REJECTS out-of-domain input
    is its own declared claim, `excluded_outside_domain(p)`, state it
    explicitly, opt in with the `excluding` keyword, or get it
    auto-declared by @enforce_domain (the decorator that makes it
    true). There is no adjudication mode: a declared exclusion that
    trials find unenforced is falsified with the accepted value as
    witness; an undeclared one reports nothing. See
    claim-driven-development's v0.2.0/claim-anatomy.md, "Domain:
    declared vs enforced".

    `known_premises` is caller-supplied context for `assuming <name>
    holds` references that resolve nowhere in the batch: a mapping of
    claim name to a human line (usually from
    `compendium.external_premises`) that the missing-prerequisite note
    then includes. Data only; it never satisfies a premise, and
    check() itself stays IO-free.

    `extensive` reaches every route this call touches: `probe()`'s own
    critical-point sampling hints and `domain_safe[...]` probe, and a
    `route="derive"` claim's case-split fallback. Default `False`
    everywhere; real, opt-in cost when set.

    A parameter or return type hinted with a mathema type marker
    (`Annotated[float, Probability]`, `Annotated[list, Shape("m", "n")]`,
    see types.py) contributes its own claims automatically: a domain
    marker merges into `domain` (an explicitly passed bound for the same
    parameter wins), and a `Shape` marker adds a structural probe. Purely
    additive, a function with no markers behaves exactly as before. The
    docstring's own `Types:` block (see types.py) desugars to the same
    markers and merges the same way; a docstring `Domain:` block (see
    docstring.py, for a bound that isn't one of the established markers,
    most commonly a fold's own accumulator/item name) is a third domain
    source, between the two: signature markers, then the docstring's
    `Domain:` block, then an explicitly passed `domain=` still wins on a
    name collision, the most deliberate of the three.

    A `@claims_decorator(...)`-tagged function, or a docstring `Claims:`
    block (see authoring.py), also contributes its claims automatically,
    same as the type markers above; `claims=` passed here is unioned
    with those, winning per claim name on a collision (an explicit call-
    site claim is the most deliberate of the three; see
    authoring.declared_from_function's own decorator-over-docstring rule
    for the same reasoning one layer in).
    """
    from .probing import _RISK, _SPECIALS
    from .spec import declare, entry_claims
    from .types import _TYPE_PROBE_TRIALS, domain_from_signature, type_probes

    facts = analyze(fn)
    # a claim's own quantifier is where a domain is stated; the
    # signature markers are the only other source, and an explicit
    # domain= wins over both. The quantifier has to reach the built-in
    # battery too, not only the claim it was written on: sampling a
    # parameter outside the region the author declared and then
    # reporting that the function raised there manufactures a gap that
    # is an artefact of the battery rather than a fact about the code.
    merged_domain = {**domain_from_signature(fn),
                     **_domains_from_claims(claims),
                     **(domain or {})}

    from .inventory import function_dependencies
    deps = function_dependencies(fn, facts)

    def _stamp_surface(ps, surface):
        # the authoring-surface provenance output rows fold into their
        # `source` field (records.row_source); claim-route probes carry
        # theirs from the conjecture instead
        for p in ps:
            meta = dict(p.meta or {})
            meta.setdefault("mathema.surface", surface)
            p.meta = meta
        return ps

    probes = _stamp_surface(
        probe(fn, facts, domain=merged_domain or None,
              trials=trials, trials_scale=trials_scale, extensive=extensive),
        "builtin")

    type_trials = trials or _TYPE_PROBE_TRIALS
    scale = min(1.0, trials_scale)
    if scale < 1.0:
        type_trials = max(_RISK.min_trials_floor_when_scaled, len(_SPECIALS),
                          round(type_trials * scale))
    probes = probes + _stamp_surface(type_probes(fn, trials=type_trials),
                                     "types")

    # whether this list is the caller's or mathema's own matters for
    # precedence below: a call-site claim is the MOST deliberate
    # surface, a suggestion the least
    suggested = claims is None
    if suggested:
        claims = suggest_claims(fn, facts=facts, extensive=extensive)
    claims = _expand_claim_keywords(claims, fn, facts, merged_domain,
                                    extensive)
    built = [claim(c) if isinstance(c, str) else c for c in claims]
    explicit = []
    for cj in built:
        entry = declare(cj)
        # declare()'s serialized form keeps only importable dotted
        # refs; the caller's actual callables ride beside it under an
        # in-memory-only key (never written to any store), re-attached
        # when the merged entry is rebuilt into claims
        live = {k: v for k, v in (getattr(cj, "funcs", None) or {}).items()
                if callable(v)}
        if live:
            entry["__live_funcs__"] = live
        explicit.append(entry)
    # distinct claims that name alike (four domain variants of one law)
    # cannot share the name-keyed merge below
    explicit = _refuse_name_collisions(explicit)
    from .spec import merge_entries
    # a retrieved entry already carries the function surfaces merged
    # with the file store at the documented precedence; without one,
    # the function's own surfaces stand in (read off the object, so
    # check() stays IO-free)
    authored = (dict(declared) if declared is not None
                else {"claims": declared_from_function(fn)})
    if suggested:
        # a suggestion must never outrank a same-named authored claim.
        # It used to: the suggestion won the merge, so a human's
        # declared claim came back source "suggested", gates false,
        # and its verdict silently stopped counting toward the gate.
        merged_entry = merge_entries({"claims": explicit}, authored,
                                     on_conflict="silent")
    else:
        # a call-site claim overlays, winning per name: documented
        # precedence, the caller is expressing intent now
        merged_entry = merge_entries(authored, {"claims": explicit},
                                     on_conflict="silent")
    all_claims = entry_claims(merged_entry)
    if all_claims:
        probes = probes + check_conjectures(fn, all_claims, domain=merged_domain or None,
                                            trials=trials, trials_scale=trials_scale,
                                            facts=facts, extensive=extensive,
                                            known_premises=known_premises)
    from .concepts import Concept, concepts_for, flat_union
    sources = concepts_for(facts, probes)
    dismissed = set(((declared or {}).get("meta") or {}).get(
        "mathema.concepts_dismissed") or [])
    if dismissed:
        # a curated dismissal silences the suggestion, permanently;
        # keyword hints are inferences and never re-offer a tag a
        # person has already said no to
        sources = {k: [c for c in v if c not in dismissed]
                   for k, v in sources.items()}
    # keyword hints are inferences, not assertions: they ride the
    # provenance split, clearly labeled, but never the interop union
    # or the record's own concepts field
    asserted = {k: v for k, v in sources.items()
                if k in ("declared", "mechanism") and v}
    concept_objs = [Concept(name, src)
                    for src, names in asserted.items() for name in names]
    meta = {}
    if asserted or sources.get("keyword"):
        # the spec's own interop shape (a flat list under
        # meta.concepts) plus the un-flattened provenance beside it
        meta = {"mathema.concept_sources": {k: v for k, v in sources.items()
                                            if v}}
        if asserted:
            meta["concepts"] = flat_union(asserted)
    # the derive route's closed form, kept on the record so the math
    # section can state it (a proof's subject, rendered and exact).
    # Guarded: an unliftable body simply leaves the field None, which
    # every reader already treats as a valid value.
    try:
        lifted = lift_symbolic(fn, facts)
    except Exception:
        lifted = None
    return Record(facts=facts, probes=probes, dependencies=deps,
                  concepts=concept_objs, meta=meta, lifted=lifted)


def write_spec(fn, claims: list | None = None, root: str = ".",
               key: str | None = None, **kwargs) -> Record:
    """The one-call IO workflow: retrieve the declared layer from the
    project store, check the function's claims against it, write the
    record into the store (.mathema/verified/), and return the Record.

        mathema.write_spec(my_fn, claims=[...])
        mathema.write_spec(my_fn, domain={"a": (0, 1)}, strict=True)

    This is `retrieve` + `check` + `spec.record` composed; `check`
    itself stays IO-free.
    """
    from .authoring import retrieve
    from .spec import declare, merge_entries, record

    declared = retrieve(fn, root)
    from .compendium import external_premises as _external_premises
    from .compendium import install as _install_compendium
    _install_compendium(root)
    kwargs.setdefault("known_premises", _external_premises(root))
    rec = check(fn, claims=claims, declared=declared, **kwargs)
    if key is None:
        from .authoring import _fn_key
        key = _fn_key(fn)
    # The written claims_fingerprint must reflect everything check() just
    # evaluated, the retrieved file-declared claims and the function's
    # own decorator/docstring claims, not only the explicit `claims=`
    # argument here. A fingerprint computed from a subset of what was
    # actually checked would make `mathema verify` see a false "form
    # changed" on the very next run (the claim set it merges independently
    # wouldn't match this record's stamped fingerprint).
    explicit = [declare(claim(c) if isinstance(c, str) else c) for c in (claims or [])]
    merged = merge_entries(dict(declared), {"claims": explicit},
                           on_conflict="silent")
    rec.spec_path = record(rec, key=key, root=root, claims=merged["claims"])
    return rec


def load_ipython_extension(ip):
    """`%load_ext mathema` then:

        %%mathema
        def my_fn(x: list, alpha: float) -> float:
            ...

    runs the cell, then for every function it defines: writes its spec
    (check + record to .mathema/verified/) and displays the result inline.
    """
    import ast as _ast

    from IPython.display import display

    def mathema_cell(line, cell):
        ip.run_cell(cell)
        for node in _ast.parse(cell).body:
            if isinstance(node, _ast.FunctionDef):
                fn = ip.user_ns.get(node.name)
                if callable(fn):
                    display(write_spec(fn))

    ip.register_magic_function(mathema_cell, magic_kind="cell", magic_name="mathema")


_REGISTRY: dict = {}


def track_claims(fn):
    """Optional bare tag: track this function's claims over time.

    Entirely optional. Without it, everything still works: check, write_spec,
    claims.check, and the CLI operate on any function. What an untracked
    function loses is visibility in mathema.status(), the fresh-versus-stale
    sweep, because status can only report on functions it knows exist. Tag
    the functions whose claims you want watched; leave the rest alone.

    Mechanics, precisely:
      - runs once, at decoration time; the function object is returned
        unchanged (no wrapper, zero call overhead, stack traces untouched)
      - stamps ``fn.__mathema__ = {"key": ...}`` so tools and readers can see
        the tag by introspection
      - registers the function under its dotted key (module.qualname) in a
        weak registry, so `mathema.tagged()` and `mathema.status()` can find
        it; redefining the function in a notebook simply re-registers the key
    The tag carries no spec content: intent and claims live in the sidecar
    spec store (see `mathema.spec`), keeping code untouched by design.
    """
    import weakref

    from .authoring import _fn_key
    key = _fn_key(fn)
    fn.__mathema__ = {"key": key}
    _REGISTRY[key] = weakref.ref(fn)
    return fn


def tagged() -> dict:
    """Currently-alive @track_claims-tagged functions, keyed by dotted name."""
    out = {}
    for key, ref in list(_REGISTRY.items()):
        fn = ref()
        if fn is None:
            del _REGISTRY[key]
        else:
            out[key] = fn
    return out


def status(root: str = ".") -> str:
    """One line per tagged function: does a verified record exist, and is
    it fresh (its recorded form hash matches the code as it is now)?
    Freshness reads only the verified layer (.mathema/verified/), a declared
    claims file never carries an identity hash, so it can't answer this."""
    from .spec import load_verified

    verified = load_verified(root)
    lines = []
    for key, fn in sorted(tagged().items()):
        try:
            current = analyze_source(fn).form
        except SourceUnavailable:
            current = None
        rec = verified.get(key) or verified.get(fn.__name__)
        if rec is None:
            lines.append(f"  ∅ {key}: no verified record")
            continue
        stored = (rec["entry"].get("identity") or {}).get("form")
        state = ("fresh" if stored and stored == current
                 else "STALE (code changed since spec)" if stored else "no hash")
        lines.append(f"  {'✓' if state == 'fresh' else '✗'} {key}: {state} "
                     f"[{rec['source']}]")
    return "mathema status\n" + ("\n".join(lines) if lines else
                                 "  (no @track_claims-tagged functions alive)")


@dataclass
class DocstringReport:
    """The result of `docstring_report()`: the same loose best-practice
    checklist `mathema audit`'s `docs` column already scores
    (`inventory.docstring_quality()`), returned as a single object so it
    can be inspected or printed on its own for one function, e.g. in a
    notebook, without running the full `audit` CLI over a package."""
    name: str
    quality: dict

    def __repr__(self) -> str:
        from .inventory import docs_checklist

        q = self.quality
        header = (f"mathema.DocstringReport({self.name}) · "
                 f"{q['score']}/{q['applicable']} criteria met")
        return "\n".join([header] + [f"  {line}" for line in docs_checklist(q)])


def docstring_report(fn) -> DocstringReport:
    """Run the same loose docstring best-practice checklist `mathema
    audit`'s `docs` column scores, against just this one function,
    interactive/notebook-friendly, no package import or CLI needed.

        mathema.docstring_report(my_fn)
    """
    from .inventory import docstring_quality

    return DocstringReport(name=getattr(fn, "__name__", "callable"),
                           quality=docstring_quality(fn))
