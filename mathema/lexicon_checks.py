# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every check a lexicon is held to, as functions over a
`lexicon.LexiconSource`, so mathema's own lexicon and a package's
registered one are held to the same checks by the same code. Each
`check_*` returns a list of problems, empty when the lexicon passes;
`lexicon_problems` runs them all and returns the ones with problems.
A row with an example function is rendered and round-tripped as that
function completes it (`for n in N` against `n: int` stays `N`), the
form its record states; a row without one renders the unannotated
default.

The checks: every row parses (`parses`) and renders in both forms
(`renders`); both rendered forms match a golden snapshot
(`golden`); render, parse, render is a fixed point in both display
modes and reparses to the same canonical claim (`fixed_point`); the
canonical text is itself a fixed point (`stable_canonical`); the
canonical form reaches the same verdict as the row against its
example function (`same_verdict`); a row survives the declared store
(`declared_store`) and a record row rebuilt from its verdict
adjudicates the same (`verified_record`); a rendered domain other than a finite set of
listed members states its missing-value policy (`missing_policy`); the sections partition the
rows (`sections`); the tags name only real rows (`tags`) and search
finds each tagged row by one of its tags (`search`); every row has an
example function and adjudicates against it (`examples`); and every
row lands on its pinned verdict, and witness where falsified
(`verdicts`)."""
from __future__ import annotations

import json
import os

from .lexicon import LexiconSource


def _example_for(src: LexiconSource, key: str):
    """The first example function demonstrating `key`, or None."""
    for fn, keys in src.example_functions.values():
        if key in keys:
            return fn
    return None


def _as_checked(cj, fn):
    """Intent:
        `cj` with its bindings completed from `fn`'s annotations
        (`conjecture._complete_missing`), the form its record states;
        `cj` itself when there is no function.
    """
    if fn is None:
        return cj
    from dataclasses import replace

    from .conjecture import _complete_missing
    completed = _complete_missing(cj, fn)[0]
    return replace(cj, domain=completed) if completed else cj


def rendered(src: LexiconSource) -> dict:
    """Intent:
        `{key: {"input", "unicode", "ascii"}}` for every row, the shape
        of a golden snapshot.
    """
    from .conjecture import claim
    from .spec import render_claim_text
    out = {}
    for key, law in src.rows.items():
        cj = _as_checked(claim(law), _example_for(src, key))
        out[key] = {"input": law, "unicode": render_claim_text(cj, unicode=True),
                    "ascii": render_claim_text(cj, unicode=False)}
    return out


def write_golden(src: LexiconSource, path: str) -> None:
    """Write `rendered(src)` to `path`, the golden snapshot `check_golden`
    compares against; review the diff before committing it."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rendered(src), fh, ensure_ascii=False, indent=1)


#: `write_golden` under the name the extension surface carries
write_lexicon_golden = write_golden


def check_parses(src: LexiconSource) -> list:
    from .conjecture import claim
    out = []
    for key, law in src.rows.items():
        try:
            claim(law)
        except Exception as exc:
            out.append(f"{key}: does not parse ({type(exc).__name__}: {exc})")
    return out


def check_renders(src: LexiconSource) -> list:
    from .conjecture import claim
    from .spec import render_claim_text
    out = []
    for key, law in src.rows.items():
        try:
            cj = _as_checked(claim(law), _example_for(src, key))
            render_claim_text(cj, unicode=True)
            render_claim_text(cj, unicode=False)
        except Exception as exc:
            out.append(f"{key}: does not render ({type(exc).__name__}: {exc})")
    return out


def check_golden(src: LexiconSource, path: str) -> list:
    if not os.path.exists(path):
        return [f"no golden snapshot at {path}; write one with write_golden"]
    with open(path, encoding="utf-8") as fh:
        golden = json.load(fh)
    now = rendered(src)
    out = [f"{key}: not in the golden snapshot" for key in now if key not in golden]
    out += [f"{key}: in the golden snapshot but not the lexicon" for key in golden if key not in now]
    for key in now:
        if key in golden and now[key] != golden[key]:
            out.append(f"{key}: {golden[key]} -> {now[key]}")
    return out


def check_fixed_point(src: LexiconSource) -> list:
    from .conjecture import InvalidConjecture, claim
    from .spec import canonical_claim_text, render_claim_text
    drifted = []
    for name, law in src.rows.items():
        fn = _example_for(src, name)
        conjecture = _as_checked(claim(law), fn)
        canonical = canonical_claim_text(conjecture)
        for unicode_mode in (True, False):
            once = render_claim_text(conjecture, unicode=unicode_mode)
            try:
                reparsed = _as_checked(claim(once), fn)
            except InvalidConjecture as exc:
                drifted.append(f"{name}: rendered text will not reparse ({exc}): {once}")
                continue
            twice = render_claim_text(reparsed, unicode=unicode_mode)
            if once != twice:
                drifted.append(f"{name}:\n    {once}\n    {twice}")
            if canonical_claim_text(reparsed) != canonical:
                drifted.append(f"{name}: display reparses to another claim"
                               f"\n    {canonical}\n    {canonical_claim_text(reparsed)}")
    return drifted


def check_stable_canonical(src: LexiconSource) -> list:
    from .conjecture import InvalidConjecture, claim
    from .spec import canonical_claim_text
    drifted = []
    for name, law in src.rows.items():
        fn = _example_for(src, name)
        once = canonical_claim_text(_as_checked(claim(law), fn))
        try:
            twice = canonical_claim_text(_as_checked(claim(once), fn))
        except InvalidConjecture as exc:
            drifted.append(f"{name}: canonical text will not reparse "
                           f"({type(exc).__name__}): {once}")
            continue
        if once != twice:
            drifted.append(f"{name}:\n    {once}\n    {twice}")
    return drifted


def check_same_verdict(src: LexiconSource) -> list:
    from .conjecture import check_conjectures, claim
    from .spec import canonical_claim_text
    diverged = []
    for fn, keys in src.example_functions.values():
        for key in keys:
            law = src.rows[key]
            try:
                original = claim(law, route="probe")
                canonical = canonical_claim_text(_as_checked(original, fn))
                restored = claim(canonical, route="probe")
            except Exception as exc:
                diverged.append(f"{key}: canonical form will not reparse ({type(exc).__name__})")
                continue
            (before,) = check_conjectures(fn, [original], extensive=False)
            (after,) = check_conjectures(fn, [restored], extensive=False)
            if before.verdict != after.verdict:
                diverged.append(f"{key}: {before.verdict} -> {after.verdict}\n    {law}"
                                f"\n    {canonical}")
    return diverged


def check_declared_store(src: LexiconSource) -> list:
    from .conjecture import claim
    from .spec import canonical_claim_text, declare, entry_claims
    lost = []
    for name, law in src.rows.items():
        original = claim(law)
        try:
            restored = entry_claims({"claims": [declare(original)]})[0]
        except Exception as exc:
            lost.append(f"{name}: will not reparse ({type(exc).__name__}: {exc})")
            continue
        for what, before, after in (
            ("statement", (original.lhs, original.relation, original.rhs),
                          (restored.lhs, restored.relation, restored.rhs)),
            ("links", original.links, restored.links),
            ("free_vars", set(original.free_vars), set(restored.free_vars)),
            ("funcs", set(original.funcs), set(restored.funcs)),
            ("assuming", original.assuming, restored.assuming),
            ("tolerance", original.tolerance, restored.tolerance),
            ("canonical text", canonical_claim_text(original), canonical_claim_text(restored)),
        ):
            if before != after:
                lost.append(f"{name}: {what} {before!r} -> {after!r}")
    return lost


def verified_record_verdicts(src: LexiconSource) -> dict:
    """Intent:
        `{key: (verdict, rebuilt verdict or an exception text, rebuilt
        probe or None)}`: each example row adjudicated, its record row
        rebuilt the way `verify` repopulates a declared claim, and
        adjudicated again.
    """
    from .conjecture import check_conjectures, claim
    from .spec import entry_claims
    out = {}
    for fn, keys in src.example_functions.values():
        laws = [claim(src.rows[k], name=k) for k in keys]
        # a function's record rows are repopulated together, as `verify`
        # does, so a gate reads the stated rows beside it
        first, rebuilt_all = {}, []
        for p in check_conjectures(fn, laws):
            row = {"name": p.name, "statement": p.statement,
                   "route": (p.route or "best").split(":", 1)[0]}
            if row["route"] not in ("derive", "probe"):
                row["route"] = "best"
            for field_name in ("domain", "grammar", "tolerance"):
                if getattr(p, field_name, None) is not None:
                    row[field_name] = getattr(p, field_name)
            try:
                (rebuilt,) = entry_claims({"claims": [row]})
            except Exception as exc:
                out[p.name] = (p.verdict, f"will not reconstruct ({type(exc).__name__}: {exc})",
                               None, p.statement)
                continue
            first[p.name] = p
            rebuilt_all.append(rebuilt)
        again = {p2.name: p2 for p2 in check_conjectures(fn, rebuilt_all)} \
            if rebuilt_all else {}
        for name, p in first.items():
            p2 = again.get(name)
            out[name] = (p.verdict, p2.verdict if p2 is not None else "not adjudicated",
                         p2, p.statement)
    return out


def check_verified_record(src: LexiconSource, *, skip=()) -> list:
    drift = []
    for key, (before, after, _p2, statement) in verified_record_verdicts(src).items():
        if key in skip:
            continue
        if before != after:
            drift.append(f"{key}: {before} -> {after} (statement {statement!r})")
    return drift


def check_missing_policy(src: LexiconSource) -> list:
    from .conjecture import claim
    from .domain import stated
    from .spec import canonical_claim_text, render_claim_text
    out = []
    for key, law in src.rows.items():
        fn = _example_for(src, key)
        cj = _as_checked(claim(law), fn)
        if not cj.domain or all(isinstance(b, frozenset) for b in cj.domain.values()):
            continue
        # a binding that does not state its missing-value policy renders
        # the default it resolves to; a stated one renders what it lists
        # a claim's own constant (`let c be [0, 1]`) admits nothing
        # missing and says nothing about it
        unstated = any(not stated(b) for p, b in cj.domain.items()
                       if p.isidentifier() and p not in (cj.free_vars or ()))
        for unicode_mode in (True, False):
            shown = render_claim_text(cj, unicode=unicode_mode)
            if unstated and not any(word in shown for word in
                                    ("absent", "None", "missing", "∅")):
                out.append(f"{key}: the rendered domain states no missing policy: {shown}")
            if canonical_claim_text(_as_checked(claim(shown), fn)) != canonical_claim_text(cj):
                out.append(f"{key}: the rendered missing policy reparses to another claim")
    return out


def check_sections(src: LexiconSource) -> list:
    seen: list = []
    for keys in src.sections.values():
        seen.extend(keys)
    out = [f"{key}: in more than one section" for key in sorted({k for k in seen if seen.count(k) > 1})]
    out += [f"{key}: in no section" for key in sorted(set(src.rows) - set(seen))]
    out += [f"{key}: in a section but not a row" for key in sorted(set(seen) - set(src.rows))]
    return out


def check_tags(src: LexiconSource) -> list:
    return [f"{key}: tagged but not a row" for key in sorted(set(src.tags) - set(src.rows))]


def check_search(src: LexiconSource, *, limit: int = 8) -> list:
    from .lexicon import search
    out = []
    for key, tags in src.tags.items():
        if tags and not any(key in [k for k, _law in search(tag, limit=limit)] for tag in tags):
            out.append(f"{key}: no search for one of its tags {list(tags)} finds it")
    return out


def check_examples(src: LexiconSource, *, every_row: bool = True) -> list:
    from .conjecture import check_conjectures, claim
    covered = {key for _fn, keys in src.example_functions.values() for key in keys}
    out = ([f"{key}: no example function" for key in sorted(set(src.rows) - covered)]
           if every_row else [])
    for fn, keys in src.example_functions.values():
        for key in keys:
            try:
                check_conjectures(fn, [claim(src.rows[key], route="probe")], extensive=False)
            except Exception as exc:
                out.append(f"{key}: adjudicating against {getattr(fn, '__name__', fn)} "
                           f"raised {type(exc).__name__}: {exc}")
    return out


def check_verdicts(src: LexiconSource, expected: dict) -> list:
    """Every row against its example function lands on `expected[key]`,
    a verdict or `(verdict, text the witness contains)`; a row two
    example functions demonstrate to different ends pins one of those
    per function, `{function name: verdict or (verdict, text)}`. A row
    is adjudicated in one batch with the claims declared on its example
    function, as `verify` does, so a premise naming a sibling claim
    resolves to it."""
    from .authoring import declared_from_function
    from .conjecture import check_conjectures, claim
    from .spec import entry_claims
    out = [f"{key}: no pinned verdict" for key in sorted(set(src.rows) - set(expected))]
    for fn, keys in src.example_functions.values():
        for key in keys:
            want = expected.get(key)
            if isinstance(want, dict):
                want = want.get(getattr(fn, "__name__", ""))
            if want is None:
                continue
            verdict, witness = (want, None) if isinstance(want, str) else want
            row = claim(src.rows[key])
            siblings = [c for c in entry_claims(
                {"claims": declared_from_function(fn)}) if c.name != row.name]
            (p,) = [q for q in check_conjectures(fn, [row, *siblings])
                    if q.name == row.name]
            if p.verdict != verdict:
                out.append(f"{key}: {p.verdict}, pinned {verdict} ({p.note})")
            elif witness is not None and witness not in str(p.counterexample):
                out.append(f"{key}: the witness {p.counterexample!r} does not contain {witness!r}")
    return out


def lexicon_problems(src: LexiconSource, *, golden: str | None = None,
                     expected: dict | None = None, skip_record: tuple = ()) -> dict:
    """Intent:
        `{check: [problem, ...]}` for every check with a problem, empty
        when the lexicon passes them all. `golden` is the snapshot path
        (the golden check runs only with one), `expected` the pinned
        verdicts (the verdict check runs only with them), and
        `skip_record` rows the verified-record check leaves out. A row
        with an example function is rendered and round-tripped as that
        function completes it.
    """
    checks = {
        "parses": lambda: check_parses(src),
        "renders": lambda: check_renders(src),
        "fixed_point": lambda: check_fixed_point(src),
        "stable_canonical": lambda: check_stable_canonical(src),
        "same_verdict": lambda: check_same_verdict(src),
        "declared_store": lambda: check_declared_store(src),
        "verified_record": lambda: check_verified_record(src, skip=skip_record),
        "missing_policy": lambda: check_missing_policy(src),
        "sections": lambda: check_sections(src),
        "tags": lambda: check_tags(src),
        "search": lambda: check_search(src),
        "examples": lambda: check_examples(src),
    }
    if golden is not None:
        checks["golden"] = lambda: check_golden(src, golden)
    if expected is not None:
        checks["verdicts"] = lambda: check_verdicts(src, expected)
    found = {name: run() for name, run in checks.items()}
    return {name: problems for name, problems in found.items() if problems}


__all__ = ["check_declared_store", "check_examples", "check_fixed_point", "check_golden",
           "check_missing_policy", "check_parses", "check_renders", "check_same_verdict",
           "check_search", "check_sections", "check_stable_canonical", "check_tags",
           "check_verdicts", "check_verified_record", "lexicon_problems", "rendered",
           "verified_record_verdicts", "write_golden", "write_lexicon_golden"]
