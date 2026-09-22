# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The package's central result record (`Probe`) and the shared verdict
vocabulary around it. Stdlib-only, no dependency on anything else in the
package, so every layer (adjudication, CLI, spec serialization, reason
codes) can build and classify results the same way without import
cycles.

A verdict is an open string: one of the base families below, optionally
refined with a colon subroute (`"skipped:misspecified"`). The full
vocabulary:

- `"proven"`: settled symbolically over the whole declared domain.
- `"holds"`: supported empirically; every sampled trial agreed.
- `"unknown"`: the state every claim starts in until verified, and
  the outcome when an adjudication ran but decided nothing either way
  (a derive attempt that came back undecided/unliftable, a family that
  declined). `meta` says why, when an attempt was actually made.
- `"documented"` / `"declared"`: intent-level evidence rungs, not
  full claim verdicts: a deliberate statement (an `Intent:` block, an
  `intent:` field in the declared spec) is `documented`; one inferred
  from a bare summary is `declared`, the lowest rung.
- `"falsified"`: refuted, by counterexample or symbolic disproof.
  Knowledge, not failure; the diagnose/accept workflow decides whether
  it is a bug or a genuine discovery.
- `"skipped"`: blocked, with an identifiable reason (a misspecified
  claim, an unknown route/relation, no evaluable inputs, an
  unavailable resource); reason codes attach here.
- `"invalidated"`: a regression, an error state: the claim was
  `proven`/`holds` in the recorded history and a later adjudication
  could no longer establish it. Written only by the record layer
  (`spec.record()`), which is what holds the history; `meta` carries
  `mathema.previous_verdict` and `mathema.regressed_to`.

`proven` and `holds` support a claim (`SUPPORTED_VERDICTS`). Colon
subroutes (`derive:extensive`, `probe:semi_analytical`) describe HOW a
verdict was reached and are excluded from evidence aggregation,
`classify_verdict` strips them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .routes import examine_predicates


@dataclass
class Probe:
    name: str
    statement: str
    verdict: str           # "proven" | "holds" | "falsified" | "skipped"
    n: int = 0
    counterexample: str | None = None
    note: str | None = None
    sketch: str | None = None       # derive route: the algebraic derivation
    condition: str | None = None    # derive route: a domain condition the proof relies on
    route: str | None = None
    # record-schema.md's own `route` field: an open string, not a fixed
    # enum ("Open for extension" in record-schema.md). "probe"/"derive"
    # for the ordinary cases; a tool is expected to state a real
    # subroute with a colon when its own technique differs from the
    # documented ordinary case, e.g. "derive:extensive" (proven only
    # via the case-split fallback's widened search) or
    # "probe:semi_analytical" (sampling informed by an analytically
    # discovered critical point, not blind). Always the mechanism that
    # actually adjudicated: never the input-side "best" (which only
    # tells the verifier to try the strongest route first and fall
    # back), and `None` when no mechanism engaged at all (a claim
    # skipped at validation, before any route ran).
    meta: dict = field(default_factory=dict)
    # namespaced extension data (record-schema.md's `meta` field); e.g. a
    # probe-route Probe carries {"mathema.sampling": {...}}, how it actually
    # sampled, in a shape that's expected to change as the sampling engine
    # does, not a stable dataclass field.
    # The claim's own declared shape, carried so the verified row can
    # state it structurally beside the canonical statement: the two are
    # equivalent projections of one claim (the statement re-parses to
    # these fields; the fields re-render to the statement). Machines
    # read the fields, people read the text.
    domain: dict | None = None      # JSON-shaped, domain_bound_to_json
    grammar: str | None = None
    tolerance: float | None = None
    # The claim's second stratum, stated only where evidence exists
    # (None otherwise, which is most falsifications). The verdict is
    # about the ARTIFACT and never softens; this field says which
    # stratum a falsification indicts, where that is determinable:
    #   blame: "implementation" | "claim"
    #   mathematics: "sound" | "unsound"  (only where determinable:
    #     "sound" when an exact-arithmetic proof of the same claim
    #     coexists with the executed falsification, "unsound" when a
    #     symbolic disproof was corroborated by a reproduced witness)
    #   cause: an "implementation:*" reason code, iff blame is
    #     "implementation" (reason_codes group 5)
    #   representation: the carrier the evidence holds under ("f64",
    #     "bigint"; representations.py)
    #   witness: short text naming the fragile point or failure
    # Persisted as meta["mathema.stratum"] (spec.to_spec folds it), so
    # the on-disk shape needs no schema change at CDD spec v0.2.0.
    stratum: dict | None = None


# exception names a raises(...) claim may assert; resolving arbitrary names
# through builtins would widen the eval sandbox for no benefit
_EXC_TYPES = {
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "ZeroDivisionError": ZeroDivisionError, "ArithmeticError": ArithmeticError,
    "OverflowError": OverflowError, "KeyError": KeyError,
    "IndexError": IndexError, "AssertionError": AssertionError,
    "NotImplementedError": NotImplementedError,
}

# The two verdict families that support a claim, strongest first. A
# coverage count treats either as adjudicated-in-favor; they differ only
# in evidence strength (symbolic proof vs. sampled agreement).
SUPPORTED_VERDICTS = ("proven", "holds")


def classify_verdict(verdict: str) -> str:
    """The base family of a verdict string: the part before any colon
    subroute, so `"skipped:misspecified"` classifies as `"skipped"` and a bare
    `"proven"`/`"holds"`/`"falsified"`/`"skipped"` classifies as itself.
    An unrecognized string comes back unchanged (minus any subroute)
    rather than raising; the verdict vocabulary is open."""
    return verdict.split(":", 1)[0]


def stance(verdict: str) -> str:
    """The four-value reading of a verdict an agent can branch on:
    `supported` (proven/holds), `refuted` (falsified/invalidated/
    disproven), `blocked` (skipped/unliftable; adjudication could not
    engage), `undecided` (everything else, unknown included). The
    verdict vocabulary itself stays open (subroutes and all); this is
    the closed fold of it, beside which the verbatim verdict always
    rides for fidelity."""
    kind = classify_verdict(verdict)
    if kind in ("proven", "holds"):
        return "supported"
    if kind in ("falsified", "invalidated", "disproven"):
        return "refuted"
    if kind in ("skipped", "unliftable", "blocked"):
        return "blocked"
    return "undecided"


# the historical claim-source sentinels, folded to the closed authoring-
# surface vocabulary output rows carry. The sentinels themselves are
# load-bearing in adjudication ("user" gates, "mathema" never does) and
# stay as they are; this is the one place they translate.
_SOURCE_VOCAB = {"mathema": "suggested", "docstring": "docstring",
                 "decorator": "decorator", "declared": "declared",
                 # the pre-rename spellings, still read from older stores
                 "author": "decorator", "the author": "declared",
                 "builtin": "builtin", "types": "types",
                 # the Conjecture default: a claim passed at the call
                 # site, mapped deliberately rather than falling through
                 "user": "ad_hoc",
                 # a compendium row materialised into the store
                 "compendium": "compendium"}


def row_source(meta: dict | None, note: str = "") -> str:
    """Which authoring surface a claim row came from: `declared` (a
    hand-written claims file), `docstring`, `decorator`, `types`,
    `suggested` (mathema volunteered it), `builtin` (the structural
    battery), or `ad_hoc` (passed at the call site). A row whose
    recorded source is missing or unrecognized answers `unknown`,
    loudly: provenance a reader cannot trace is a fact worth stating,
    never silently filed under the call-site bucket."""
    source = (meta or {}).get("mathema.surface")
    if source is None and str(note or "").startswith("conjectured by mathema"):
        return "suggested"
    if source in _SOURCE_VOCAB:
        return _SOURCE_VOCAB[source]
    import warnings
    warnings.warn(f"mathema: claim row carries "
                  f"{'no' if source is None else 'unrecognized'} "
                  f"surface{'' if source is None else f' {source!r}'}")
    return "unknown"


def _claim_reason(verdict: str, meta: dict, note: str) -> "str | None":
    """The `ClaimReasonCode` for a row, or None when the verdict carries
    no reason. Works from the same three fields whether the row arrived
    as a live `Probe` or a stored dict, so a record read back from disk
    groups the same way as one just adjudicated."""
    from types import SimpleNamespace

    from .reason_codes import claim_reason_code
    try:
        return claim_reason_code(SimpleNamespace(
            verdict=verdict, meta=meta, note=note))
    except Exception:
        return None

def claim_row(c, *, accepted_risk: frozenset = frozenset()) -> dict:
    """One adjudicated claim (a live Probe or a stored claim dict) as
    the agent-facing row shape: `{claim, statement, stance, verdict,
    route, source, gates, evidence}`, with the envelope rule that
    `counterexample` is present iff the row is refuted and `blocked_by`
    iff it is blocked; presence is the signal, so a missing key can
    never be misread the way null or "" can. `gates` says whether the
    row is in the gated population at all (suggestions and foreign-
    grammar claims are not); an accepted-risk unknown stays in the
    population, its verdict itself saying why it passes."""
    if isinstance(c, dict):
        name, verdict = c.get("name") or "", c.get("verdict") or ""
        meta, note = c.get("meta") or {}, str(c.get("note") or "")
        statement, route = c.get("statement") or c.get("law"), c.get("route")
        counterexample, n = c.get("counterexample"), c.get("n")
        stratum = meta.get("mathema.stratum")
    else:
        name, verdict = c.name or "", c.verdict or ""
        meta, note = c.meta or {}, str(c.note or "")
        statement, route = c.statement, c.route
        counterexample, n = c.counterexample, c.n
        stratum = getattr(c, "stratum", None) or meta.get("mathema.stratum")
    source = row_source(meta, note)
    st = stance(verdict)
    # source + verdict + route says what happened; `reason` says why,
    # and without it a rollup cannot tell one `holds` from another,
    # a derive gap the probe route rescued and a claim that was never
    # derivable in principle group identically otherwise. `stance` is a
    # closed fold of `verdict` and adds no grouping dimension of its
    # own; it stays for readers, not for grouping.
    # a live Probe carries the stratum as a field; the stored shape
    # carries it inside meta. One merged meta feeds the reason lookup
    # so both shapes produce the same row.
    reason_meta = ({**meta, "mathema.stratum": stratum} if stratum else meta)
    row = {"claim": name, "statement": statement, "stance": st,
           "verdict": verdict, "route": route, "source": source,
           "reason": _claim_reason(verdict, reason_meta, note),
           "gates": (source != "suggested"
                     and "mathema.foreign_grammar" not in meta),
           "evidence": {"n": n or None}}
    if name in accepted_risk:
        row["accepted"] = "risk"
    if st == "refuted":
        row["counterexample"] = counterexample
        if stratum:
            # the refuted parallel of blocked_by, present iff stratum
            # evidence exists: the implementation cause, or "claim"
            # for a corroborated mathematical disproof. Absence means
            # no stratum was determinable, exactly as a missing
            # blocked_by means an unclassified block.
            row["refuted_by"] = (stratum.get("cause")
                                 if stratum.get("blame") == "implementation"
                                 else stratum.get("blame"))
    if st == "blocked":
        subroute = verdict.split(":", 1)[1] if ":" in verdict else None
        row["blocked_by"] = (meta.get("mathema.blocked_code")
                             or subroute or classify_verdict(verdict))
    return row


def pseudo_infinity_range(value) -> tuple[float, float] | None:
    """The resolved (lo, hi) operational-infinity range for a claim's
    `pseudo_infinity` value: a bare magnitude means the symmetric
    range, a two-element pair states both sides, None stays None. The
    one resolver every consumer (the stability sweep's corners, the
    spec emitter, the statement renderer) reads, so the canonical
    two-sided form is produced identically everywhere."""
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        return float(value[0]), float(value[1])
    return -float(value), float(value)


def statement_text(relation: str, lhs: str, rhs: str | None) -> str:
    """The one raw claim-statement spelling: predicate forms
    (`raises(...)` and the domain-safety trio) render as calls,
    everything else as `lhs relation rhs`. Every producer of a raw
    statement (adjudication's Probe.statement, the declared-layer
    writer) goes through here, so a domain-safety claim can never again
    render as the drifted `"x is_pole_safe "` in one place and
    `"is_pole_safe(x)"` in another."""
    if relation == "raises":
        return f"raises({lhs}, {rhs})" if rhs else f"raises({lhs})"
    if relation in examine_predicates():
        return f"{relation}({lhs})"
    return f"{lhs} {relation} {rhs}"


def claim_statement(cj) -> str:
    """The full statement of a Conjecture, chain-aware and binding-aware:
    a chained comparison (`0 <= f(x) <= 1`) renders every link so it does
    not read as its first link alone; a claim binding an external
    reference (a delegated core) is prefixed with its `let g = pkg.mod.
    core` so the binding is legible, while internal `mathema.*` helper
    bindings (the permutation/scale probes) stay implicit; everything
    else renders through `statement_text`. This is what a suggestion row
    shows, since return-bound and cross-implementation suggestions carry
    a chain or a binding the single-relation spelling would drop."""
    funcs = getattr(cj, "funcs", None) or {}
    prefix = "".join(
        f"let {letter} = {ref}, "
        for letter, ref in funcs.items()
        if isinstance(ref, str) and not ref.startswith("mathema."))
    links = getattr(cj, "links", None)
    if links:
        body = links[0][0]
        for _lhs, rel, rhs in links:
            body += f" {rel} {rhs}"
    else:
        body = statement_text(cj.relation, cj.lhs, cj.rhs)
    return prefix + body
