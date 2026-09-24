# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The MCP tool functions: thin, JSON-shaped wrappers over mathema's
library surface (`targets.resolve`, `check` + `verify.gate`,
`verify.verify_project`, `audit`, the reason-code registry, the claim
lexicon). Plain functions with no MCP dependency of their own, so they
are directly callable and testable; `server.py` registers them.

Every tool adjudicates through mathema's own machinery, none accepts
a caller-supplied verdict, and acceptance is deliberately absent."""
from __future__ import annotations

import inspect


def resolve_target(target: str, root: str = ".") -> dict:
    """Resolve a target spelling (dotted name, module:function, or file
    path) to its function keys and signatures."""
    from mathema.targets import resolve

    t = resolve(target, root)
    functions = []
    for key, fn in sorted(t.functions.items()):
        try:
            sig = str(inspect.signature(fn))
        except (TypeError, ValueError):
            sig = "(...)"
        functions.append({"key": key, "signature": sig})
    return {"kind": t.kind, "module": t.module_name, "functions": functions,
            "skipped_submodules": [list(x) for x in t.skipped]}


def adjudicate_target(target: str, claims: list | None = None,
                      root: str = ".", strict: bool = False,
                      include: str = "declared") -> dict:
    """Adjudicate one function and gate the outcome, the `mathema
    check` authoring loop as one call. Claim statements are
    adjudicated by mathema; the verdicts are mathema's own.

    Names its input a TARGET (a dotted name, `module:function`, or a
    path) rather than taking a function object, and READS the project
    to resolve it and join the declared layer, but never writes. The
    library `mathema.check()` is the same adjudication over a live
    function object with no filesystem access at all; `verify_project`
    is the one that writes records.

    `include` selects which rows come back: `"declared"` (the default;
    what the authoring surfaces actually state, which is what a
    re-check after editing a claim is asking about), `"suggested"`
    (mathema's own candidate battery), or `"all"`. A function with no
    declared claims returns no rows and a `hint` naming
    `include="suggested"` rather than silently switching sets.

    Statements passed in `claims` are LINTED before anything is
    adjudicated: a statement that does not parse comes back as
    `{"lint": {...}, "passed": null}` at parse cost, with nothing
    run. A rejected statement is information, not an error.

    Reading a claim row: branch on `stance`, the closed four-value
    fold (supported/refuted/undecided/blocked); `verdict` and `route`
    are open strings beside it for fidelity, a colon marking a
    subroute ("derive:extensive", "skipped:unknown_but_accepted").
    `source` says which authoring surface the claim came from
    (declared/docstring/decorator/types/suggested/builtin/ad_hoc), and
    `gates` whether the row counts toward `passed`, so `passed` can
    be true beside a refuted row exactly when that row is a
    SUGGESTION mathema volunteered (`gates` false): a falsified
    suggestion is information, not a failure. Envelope rule:
    `counterexample` present iff refuted, `blocked_by` iff blocked."""
    if include not in ("declared", "suggested", "all"):
        return {"ok": False, "error": f"unknown include={include!r}; "
                                      "choose declared, suggested, or all"}
    # lint first: the check-fix-check loop skips a separate lint step
    # roughly ten times out of eleven, so it happens in here instead
    for statement in (claims or []):
        if not isinstance(statement, str):
            continue
        # target too: a claim naming a parameter the function does not
        # have is the commonest mistake on unfamiliar code, and it is
        # far cheaper to catch here than as an opaque gating `unknown`
        lint = parse_claim(statement, target=target, root=root)
        if not lint.get("ok"):
            return {"key": target, "lint": lint, "claims": [],
                    "passed": None, "problems": [], "counts": {}}

    from mathema import check
    from mathema.authoring import retrieve
    from mathema.spec import load_verified
    from mathema.targets import resolve_function
    from mathema.verify import _accepted_risk, gate

    key, fn = resolve_function(target, root)
    # `is not None`, deliberately: an explicit [] means "the declared
    # surfaces only" and must not collapse to the suggestion battery
    # the way a falsiness test made it
    passed_claims = list(claims) if claims is not None else None
    if passed_claims is None and include == "declared":
        passed_claims = []
    from mathema.compendium import install as _install_compendium
    from mathema.compendium import external_premises as _stub_premise_names
    _install_compendium(root)
    rec = check(fn, claims=passed_claims, declared=retrieve(fn, root),
                known_premises=_stub_premise_names(root))
    accepted = _accepted_risk((load_verified(root).get(key) or {}).get("entry"))
    report = gate(rec.probes, strict=strict, accepted_risk=accepted,
                  unresolved=rec.facts.unresolved)
    from mathema.records import claim_row
    rows = [claim_row(p, accepted_risk=accepted) for p in rec.probes]
    if include == "declared":
        rows = [r for r in rows if r["source"] != "suggested"]
    elif include == "suggested":
        rows = [r for r in rows if r["source"] == "suggested"]
    out = {
        "key": key,
        "problems": report.problems,
        "passed": not report.problems,
        "counts": {"proven": report.proven, "holds": report.holds,
                   "refuted": report.refuted, "unknown": report.unknown,
                   "accepted_risk": report.owned, "skipped": report.skipped},
        "claims": rows,
    }
    if not rows and include == "declared":
        out["hint"] = ("no declared claims for this function; call again "
                       "with include='suggested' to see candidates, or "
                       "pass claims=[...] to adjudicate your own")
    return out


def adjudicate_targets(targets: list[str], root: str = ".",
                       strict: bool = False,
                       include: str = "declared") -> dict:
    """Adjudicate SEVERAL functions in one call, a claims pass over a
    module without one round trip per function. Same adjudication and
    the same gate as `adjudicate_target`, reads the same way and writes
    nothing either, and the same `include` vocabulary; what changes is
    that the store is read once for the whole batch rather than once
    per target, and one envelope is returned instead of N.

    Rows are column-oriented like `audit_targets`:
    `{"prefix", "cols", "rows"}` with the shared dotted key prefix
    factored out. `cols` is
    `[key, claim, stance, verdict, route, source, gates]`; the fuller
    per-claim shape (counterexample, blocked_by, evidence) stays on
    `adjudicate_target`, which is the right call once a specific row
    needs diagnosing. `failed` lists the targets that would not
    resolve, so one bad name never costs the batch."""
    from mathema import check
    from mathema.audit import _common_key_prefix
    from mathema.authoring import retrieve
    from mathema.records import claim_row
    from mathema.spec import load_declared, load_verified
    from mathema.targets import resolve_function
    from mathema.verify import _accepted_risk, gate

    if include not in ("declared", "suggested", "all"):
        return {"ok": False, "error": f"unknown include={include!r}; "
                                      "choose declared, suggested, or all"}
    # the whole point of the batch: one walk of the declared store and
    # one parse of the verified store, shared across every target
    declared_store = load_declared(root)
    verified_store = load_verified(root)

    resolved, failed = [], []
    for target in targets:
        try:
            resolved.append(resolve_function(target, root))
        except Exception as e:
            failed.append([target, f"{type(e).__name__}: {e}"])

    from mathema.compendium import install as _install_compendium
    from mathema.compendium import external_premises as _stub_premise_names
    _install_compendium(root)
    stub_premises = _stub_premise_names(root)
    rows: list = []
    counts: dict = {}
    problems: list = []
    for key, fn in resolved:
        passed_claims: list | None = [] if include == "declared" else None
        rec = check(fn, claims=passed_claims,
                    known_premises=stub_premises,
                    declared=retrieve(fn, root, store=declared_store))
        accepted = _accepted_risk(
            (verified_store.get(key) or {}).get("entry"))
        report = gate(rec.probes, strict=strict, accepted_risk=accepted,
                      unresolved=rec.facts.unresolved)
        problems.extend(f"{key}: {p}" for p in report.problems)
        for r in (claim_row(p, accepted_risk=accepted) for p in rec.probes):
            if include == "declared" and r["source"] == "suggested":
                continue
            if include == "suggested" and r["source"] != "suggested":
                continue
            rows.append([key, r["claim"], r["stance"], r["verdict"],
                         r["route"], r["source"], r["gates"]])
        for name in ("proven", "holds", "refuted", "unknown", "skipped"):
            counts[name] = counts.get(name, 0) + getattr(report, name)

    prefix = _common_key_prefix([k for k, _ in resolved])
    if prefix:
        for row in rows:
            row[0] = row[0][len(prefix):]
    return {"prefix": prefix,
            "cols": ["key", "claim", "stance", "verdict", "route",
                     "source", "gates"],
            "rows": rows, "counts": counts, "problems": problems,
            "passed": not problems, "failed": failed}


def verify_project(root: str = ".", strict: bool = True,
                   all: bool = False) -> dict:
    """The CI sweep (`mathema verify`) as one call: freshness,
    re-adjudication, record refresh, and the gate.

    The one tool here that WRITES: it refreshes `.mathema/verified/`
    as it goes. `adjudicate_target`/`adjudicate_targets` answer the
    same question about a target without touching the store.

    `keys` is the sweep as structured data; one entry per key with
    `why` it was looked at, its gate `counts`, and its `claims` in the
    same row vocabulary `adjudicate_target` emits (stance/verdict/route/
    source/gates, counterexample iff refuted). Read that rather than
    parsing `report`, which is the human rendering of the same facts.
    (`report` is prose; the audit surface's `span` is a sed address.
    They were both called `lines` and were not the same thing.)"""
    from mathema.verify import verify_project as _sweep

    result = _sweep(root, all=all, strict=strict)
    return {"report": result.lines, "problems": result.problems,
            "passed": not result.problems and not result.nothing_declared,
            "fresh": result.fresh, "adjudicated": result.adjudicated,
            "nothing_declared": result.nothing_declared,
            "grammars_seen": sorted(result.grammars_seen),
            "keys": result.keys}


def describe_target(target: str, root: str = ".", depth: int = 3,
                      tier: str | None = None) -> dict:
    """One function's full detail view: signature, identity hashes,
    inferred domains, claims with verdicts, and the tier ladder."""
    from mathema.audit import describe_detail
    from mathema.targets import resolve_function

    key, fn = resolve_function(target, root)
    return {"key": key,
            **describe_detail(key, fn, root=root, depth=depth, tier=tier)}


def audit_targets(targets: list[str], root: str = ".",
                  cols: list | None = None,
                  filter: "str | list | None" = None) -> dict:
    """The population report in the column-oriented agent shape:
    `{"prefix", "cols", "rows"}`, column names once, the shared key
    prefix factored out. `span` is a ready-made `sed -n` range for the
    function (`142:187p`), so reading exactly one function needs no
    search. One null policy: null means the analysis was
    NOT COMPUTED; a computed-but-empty result is its typed empty value
    ([] for lists, 0 for counts, "" for a derivable function's
    blocker). `docsync` is the weighted 0-100 CDD-compliance percent.
    `min_expected_claims` is the claim floor; the triplet's third
    member (how many claims a function of this shape typically
    carries) needs a corpus and has no column yet. `cols`
    selects and orders the columns (the resolved selection is echoed
    back); omitted, the default triage set is returned.

    Two derive columns, deliberately: `derivable` is what the derive
    route can do given the domain the signature, docstring and claims
    declare; the question worth asking; while `unconditional` is
    whether the body lifts with nothing supplied, a fact about the code
    alone. They differ often: a `branch:needs-domain` function is not
    unconditional and is derivable all the same, because a claim's own
    quantifier prunes the branch. Reading `unconditional` as a ceiling
    on provability understates it badly.

    `filter` keeps only matching rows: semantic terms (derive_unlock
    classes "actionable"/"limitation"/"N/A", "claimed"/"unclaimed",
    "derivable"/"underivable", "unconditional"/"needs-context") and
    columnar substring matches
    ("blocker~loop" scopes to one column, "~mutual" matches any
    column). Same-dimension terms OR together ("actionable,limitation"
    keeps either; also how "everything except N/A" is spelled);
    dimensions and columnar terms AND across. A filter's own column
    references are computed even when not selected as output columns,
    so an empty result always means "nothing matched", never "never
    looked". Explicit by design, never a default: right for a lifting
    pass, wrong for a claims pass (probe claims stay viable on every
    limitation row). Unknown columns, unknown filters, and empty match
    text come back as an error naming the vocabulary."""
    from mathema.audit import (COMPACT_DEFAULT_COLS, audit_rows,
                               compact_audit, exclude_for_cols,
                               filter_rows)

    chosen = list(cols) if cols else list(COMPACT_DEFAULT_COLS)
    exclude = exclude_for_cols(chosen, filters=filter)
    skipped: list = []
    rows = audit_rows(list(targets), root=root, skipped=skipped,
                      exclude=exclude)
    try:
        if filter:
            rows = filter_rows(rows, filter)
        compact = compact_audit(rows, chosen)
    except ValueError as e:
        from mathema.audit import AUDIT_FILTERS, COMPACT_COLUMNS
        return {"error": str(e), "known_cols": sorted(COMPACT_COLUMNS),
                "known_filters": sorted(AUDIT_FILTERS)}
    return {**compact,
            "skipped_submodules": [list(x) for x in skipped]}


def reason_code(code: "str | list | None" = None) -> dict:
    """The reason-code lookup, selective by design: `code` takes an
    exact name, a numeric id ("2.18"), a whole group by major ("2") or
    name ("loop"/"branch"/"unsupported"/"structural"), or several of
    those (a list, or comma-separated), fetch exactly the codes a
    report actually used, never the whole table by default. With no
    argument, the compact index only: id/code/derive_unlock rows, details
    fetched selectively from there."""
    from mathema.reason_codes import (CODE_GROUPS, CODE_IDS, CODE_TABLE,
                                      select_codes)

    if code is None:
        return {"groups": CODE_GROUPS,
                "cols": ["id", "code", "derive_unlock"],
                "rows": [[CODE_IDS.get(name), name, entry["derive_unlock"]]
                         for name, entry in CODE_TABLE.items()],
                "hint": "fetch details selectively: pass names, ids "
                        "(2.18), or groups (loop; 2), singly or "
                        "comma-separated"}
    found = select_codes(code)
    if not found:
        return {"error": f"no reason codes match {code!r}",
                "groups": CODE_GROUPS, "known": sorted(CODE_TABLE)}
    return {"codes": found}



def project_index(root: str = ".") -> dict:
    """The generated navigable index (.mathema/index.yaml): system
    intent, module intents (with acceptance status), function keys,
    sed-ready line spans, source/verified/declared file paths,
    concepts. Read-only; run `mathema audit --index` (or
    `mathema docsync <target>`) to (re)generate it."""
    import os

    import yaml
    path = os.path.join(root, ".mathema", "index.yaml")
    if not os.path.exists(path):
        return {"error": "no index at .mathema/index.yaml; run "
                         "`mathema docsync <target>` to generate it"}
    try:
        doc = yaml.safe_load(open(path)) or {}
    except Exception as e:
        return {"error": f"index unreadable: {type(e).__name__}: {e}"}
    return {"index": doc.get("index") or doc}


def claim_grammar() -> dict:
    """The claim-grammar reference: the lexicon of spellings the claim
    language accepts, exactly as the library states it."""
    from mathema.lexicon import LEXICON

    return {"lexicon": dict(LEXICON)}


def parse_claim(statement: str, target: str | None = None,
                root: str = ".") -> dict:
    """Parse and validate one claim statement WITHOUT adjudicating it;
    the authoring-loop linter. Success returns the resolved reading
    rendered back explicitly: `name`, canonical `statement`,
    `relation`, `route`, `negated`, and `domain` with every binding in
    its one canonical rendered form. Failure returns
    `{"ok": false, "error"}` with the grammar's own message. Nothing
    is run, proven, or stored.

    Give `target` and the statement is also checked against that
    function's real signature, by inspection: `f(...)` called with the
    wrong number of arguments, an argument name the function does not
    have, or a `for q in ...` quantifier over a nonexistent parameter.
    Naming a parameter the function does not have is the commonest
    authoring mistake on unfamiliar code, and without this it survives
    the linter and costs a full adjudication to come back as an opaque
    `unknown` that gates. A `let name be ...` binding and any function
    letter bound through `funcs=` are exempt, since neither is meant
    to be a parameter."""
    from mathema.conjecture import claim
    from mathema.domain import render_domain_bound
    from mathema.records import statement_text

    try:
        cj = claim(statement)
        # claim() defers deep validation to adjudication time; a
        # linter must not; each side has to at least parse as an
        # expression ("f(x) === 0" leaves "= 0" on the right)
        import ast
        for side in (cj.lhs, cj.rhs):
            if side:
                ast.parse(str(side).replace("^", "**"), mode="eval")
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if target is not None:
        problem = _signature_mismatch(cj, target, root)
        if problem:
            return {"ok": False, "error": problem}
    text = statement_text(cj.relation, cj.lhs, cj.rhs)
    if cj.negated:
        text = f"not {text.strip()}"
    return {"ok": True, "name": cj.name, "statement": text.strip(),
            "relation": cj.relation, "route": cj.route,
            "negated": cj.negated,
            "domain": {p: render_domain_bound(b)
                       for p, b in (cj.domain or {}).items()}}


def _signature_mismatch(cj, target: str, root: str) -> "str | None":
    """Intent:
        The claim read against the real signature, statically: wrong
        `f(...)` arity, an argument the function has no parameter for,
        or a quantifier over a name that is not a parameter. Returns
        the message, or None when the claim is consistent with the
        signature. Nothing is executed, the module imports (so the
        function object exists to inspect), the function does not run.
    """
    import ast

    from mathema.analysis import analyze_source
    from mathema.targets import resolve_function
    try:
        _key, fn = resolve_function(target, root)
        params = list(analyze_source(fn).params)
    except Exception:
        return None          # unresolvable target is not a lint failure
    # a `let name be ...` binding and any extra function letter are
    # deliberately not parameters
    exempt = set(cj.free_vars or ()) | set((cj.funcs or {}).keys())

    for side in (cj.lhs, cj.rhs):
        if not side:
            continue
        try:
            tree = ast.parse(str(side).replace("^", "**"), mode="eval")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "f"):
                continue
            if len(node.args) != len(params):
                return (f"f takes {len(params)} parameter"
                        f"{'' if len(params) == 1 else 's'} "
                        f"({', '.join(params)}), but the claim calls f "
                        f"with {len(node.args)}")
            for arg in node.args:
                if (isinstance(arg, ast.Name) and arg.id not in params
                        and arg.id not in exempt):
                    return (f"{arg.id!r} is not a parameter of f "
                            f"({', '.join(params)})")
    for name in (cj.domain or {}):
        if name not in params and name not in exempt:
            return (f"the quantifier binds {name!r}, which is not a "
                    f"parameter of f ({', '.join(params)})")
    return None


def suggest_claims(target: str, root: str = ".") -> dict:
    """Candidate claims for one function, what `mathema claims`
    proposes: monotonicity/affine/convexity per scalar parameter,
    symmetry, commutativity, safety predicates, sequence bounds,
    raises(...) per guarded parameter. Declares, never verifies:
    nothing here is run or proven, and a suggestion never gates until
    a human adopts it. Rows are `[name, statement, route, declared,
    aspect]`; `declared` is true when that name is already in the
    declared layer, and `aspect` names the question a suggestion
    competes on (`""` when it answers a question no other suggestion
    does), so a caller reads the whole bending question `shape[x]`
    (affine, convex, concave) as one choice rather than three
    independent claims. Same columns `mathema claims --suggest
    --format json` emits. A `hints` list, when present, carries
    directions to the author (not claims): a structurally bounded but
    unannotated return earns a nudge to annotate it so a bound claim can
    be offered, never a bound guessed from prose."""
    from mathema.families import aspect_label
    from mathema.records import claim_statement
    from mathema.spec import load_declared
    from mathema.suggest import suggest_claims as _suggest
    from mathema.targets import resolve_function

    key, fn = resolve_function(target, root)
    entry = (load_declared(root).get(key) or {}).get("entry", {})
    declared_names = {c.get("name") for c in entry.get("claims") or []}
    rows = []
    for cj in _suggest(fn, key=key, root=root):
        text = claim_statement(cj).strip()
        rows.append([cj.name, text, cj.route, cj.name in declared_names,
                     aspect_label(cj.name)])
    from mathema.suggest import bound_annotation_hint
    out = {"key": key,
           "cols": ["name", "statement", "route", "declared", "aspect"],
           "rows": rows}
    # hints are directions to the author, not claims: an unannotated but
    # structurally bounded return earns a nudge to annotate it (a bound
    # marker), never a bound mathema invents from prose.
    hint = bound_annotation_hint(fn)
    if hint:
        out["hints"] = [hint]
    return out


def pending_decisions(root: str = ".") -> dict:
    """Everything currently awaiting a HUMAN decision, read straight
    off the declared and verified layers, the acceptance queue
    without the accept verb (acceptance itself stays CLI-only). Rows
    are `[key, claim, kind, detail]`, kinds: `supersession-pending`
    (a re-authored verified claim needs `accept --as superseded`),
    `acceptance-stale` (an accepted claim's function changed),
    `intent-acceptance-stale` (signature/raises/intent moved on),
    `accepted-risk` (a standing risk ownership, reviewable), and
    `unknown-gating` (an unaccepted unknown that fails the gate), and
            `falsified-gating` (an unaccepted falsification awaiting a
            fix or `accept --as discovery`), and `locked-changed` (a
            locked function whose body moved: restore it, or a human
            unlocks; unlocking, like acceptance, is CLI-only), and
            `moved` (a record whose key no longer resolves while a
            function with no record has its form hash: a human renames
            the record with `mathema accept NEW --as reconciled --from
            OLD`, named in the detail)."""
    from mathema.spec import load_declared, load_verified

    rows = []
    declared = load_declared(root)
    verified = load_verified(root)
    for key, wrap in sorted(declared.items()):
        for c in (wrap.get("entry") or {}).get("claims") or []:
            pend = (c.get("meta") or {}).get("mathema.pending_supersession")
            if pend:
                rows.append([key, c.get("name"), "supersession-pending",
                             str(pend)])
    from mathema.conjecture import _resolve_func_ref
    from mathema.moved import find_moved, rename_command
    moved = find_moved(root, verified, declared,
                       lambda k: _resolve_func_ref(k, root=root))
    for old_key, new_keys in sorted(moved.items()):
        rows.append([old_key, None, "moved",
                     f"no longer resolves; its form hash matches "
                     f"{', '.join(new_keys)}, which has no record. If it "
                     f"moved, a human runs: "
                     + " (or) ".join(rename_command(n, old_key)
                                     for n in new_keys)])
    for key, wrap in sorted(verified.items()):
        entry = wrap.get("entry") or {}
        ia = entry.get("intent_accepted") or {}
        if ia.get("stale"):
            rows.append([key, None, "intent-acceptance-stale",
                         "re-accept with `mathema accept --intent`"])
        for c in entry.get("claims") or []:
            acc = c.get("accepted") or {}
            if acc.get("stale"):
                rows.append([key, c.get("name"), "acceptance-stale",
                             f"accepted as {acc.get('as')}, function "
                             "changed since"])
            elif acc.get("as") == "risk":
                rows.append([key, c.get("name"), "accepted-risk",
                             acc.get("note") or ""])
            elif (c.get("verdict") == "unknown" and not acc):
                rows.append([key, c.get("name"), "unknown-gating",
                             "accept as risk, or strengthen the claim"])
            elif (c.get("verdict") == "falsified" and not acc):
                # a falsification is the decision the whole accept flow
                # is built around: fix the code, or diagnose it as a
                # discovered claim (`accept --as discovery`). It gates
                # exactly like an unknown, so it belongs in this queue.
                rows.append([key, c.get("name"), "falsified-gating",
                             "fix the code, or diagnose with "
                             "`accept --as discovery`"])
    from mathema.locks import load_locks
    from mathema.targets import resolve_function
    for key, lk in sorted(load_locks(root).items()):
        try:
            _, fn = resolve_function(key, root)
            from mathema import analyze
            current = analyze(fn).form
        except Exception:
            current = None
        if current is not None and current != lk.get("form"):
            rows.append([key, None, "locked-changed",
                         f"locked at {lk.get('form')}, code is now "
                         f"{current}; restore the body, or a human runs "
                         f"`mathema unlock {key}`"])
    return {"cols": ["key", "claim", "kind", "detail"], "rows": rows}


def lock_target(target: str, note: str = "", root: str = ".") -> dict:
    """Pin a function's form hash: `verify` fails, and refuses to
    re-adjudicate, if the body changes, until a HUMAN runs `mathema
    unlock` in the CLI. Locking is the safe direction, so agents may do
    it (a settled implementation is worth protecting from later loop
    iterations); there is deliberately no unlock tool here. Docstring
    edits never trip a lock."""
    from mathema import analyze
    from mathema.locks import LockError, lock
    from mathema.targets import resolve_function
    key, fn = resolve_function(target, root)
    form = analyze(fn).form
    try:
        entry = lock(root, key, form, by="agent", note=note or None)
    except LockError as e:
        return {"key": key, "locked": False, "error": str(e)}
    return {"key": key, "locked": True, "form": entry["form"],
            "note": entry.get("note"),
            "hint": f"a human releases it with `mathema unlock {key}`"}


def implementation_coverage(targets: list[str], root: str = ".",
                            run_tests: bool = False) -> dict:
    """Per-function implementation coverage WITHOUT running the test
    suite: mathema's own probing and proofs supply the `probe` and
    `derive` sources on the spot, so an agent reads coverage directly
    here instead of invoking pytest and parsing a coverage report. Rows
    are `[key, percent, potential, sources, test_stale, traced, remedy]`.
    `percent` is the score, the line-weighted share of the function's
    statements backed by CURRENT evidence (a stale test report is
    excluded). `potential` is the score a test re-run could reach,
    folding in the stale-test lines. `sources` is which of
    test/probe/derive covered it. `test_stale` is true when the external
    report predates the source. `traced` is false only when the source
    could not be traced at all (a builtin/C function). `remedy` is the
    single most useful action to RAISE this function's score, the field
    to act on: re-run tests (reclaim a stale report), declare a claim (a
    derivable body derives), or cover the named lines. Top level:
    `implementation_coverage` (the repo score), `potential` (after a
    test re-run), and `test_report_stale`. Pass `run_tests=true` to
    actually re-run the suite under coverage first and RECLAIM the stale
    lines into the score (slow and side-effecting: it runs the tests, so
    an agent opts in deliberately, typically after seeing a `re-run
    tests` remedy)."""
    from mathema.impl_coverage import project_coverage, remedy

    pc = project_coverage(list(targets), root=root, run_tests=run_tests)
    rows = [[fc.key, fc.percent, fc.potential_percent,
             "+".join(k for k in ("test", "probe", "derive")
                      if k in fc.by_source) or "-",
             fc.test_stale, fc.traced, remedy(fc)]
            for fc in pc.functions]
    return {"cols": ["key", "percent", "potential", "sources",
                     "test_stale", "traced", "remedy"],
            "rows": rows,
            "implementation_coverage": pc.percent,
            "potential": pc.potential_percent,
            "test_report_stale": any(fc.test_stale for fc in pc.functions)}


def badges(targets: list[str], root: str = ".") -> dict:
    """The three badges over a target set (or rootwide when empty):
    `implementation` (code coverage, a raw line ratio), `intent`
    (docsync), and `clarity` (how much is KNOWN about the behaviour,
    scored from VERIFIED claims, NOT a pass-rate; a falsified claim still
    counts as knowledge). Intent and clarity roll up to
    the repo CENTRALITY-weighted (a core function the rest depends on
    counts more than a leaf); implementation is the raw ratio. `overall`
    is the area of the radar triangle the three span, the single health
    number to diff across commits. Per-function rows are `[key,
    implementation, intent, clarity]`; a null clarity means the source
    is unavailable. `ascii` is the git-diffable triangle. Reads the
    verified store, so clarity reflects only declared-and-verified
    claims, the CDD loop it rewards."""
    from mathema.badges import render_triangle, repo_badges

    scores = repo_badges(list(targets) or None, root=root)
    rows = [[key, v["implementation"], v["intent"], v["clarity"]]
            for key, v in scores.per_function.items()]
    return {"implementation": scores.implementation,
            "intent": scores.intent,
            "clarity": scores.clarity,
            "overall": scores.overall,
            "cols": ["key", "implementation", "intent", "clarity"],
            "rows": rows,
            "ascii": render_triangle(scores.implementation, scores.intent,
                                     scores.clarity)}


# every tool the server registers, in one place; server.py reads this
# and the no-accept test pins it
TOOLS = (resolve_target, adjudicate_target, adjudicate_targets, verify_project,
         describe_target,
         audit_targets, reason_code, claim_grammar, project_index,
         parse_claim, suggest_claims, pending_decisions, lock_target,
         implementation_coverage, badges)
