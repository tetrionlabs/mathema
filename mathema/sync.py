# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The sync engine behind `mathema docsync`: authoring surfaces flow
into the DECLARED layer, the declared layer flows into verification,
and the verified layer's memory flows back.

One pass per function key:

- gather every authoring surface (docstring Claims:/Intent: blocks,
  decorator claims, claims files) plus the verified record's
  membership;
- detect CONFLICTS: the same claim name authored with a genuinely
  different statement on two surfaces (the docstring is the human's
  hand, so resolution offers the docstring version over the declared
  file's);
- materialize the merged entry to `.mathema/declared/<key>.yaml`,
  the one intermediary, regenerated here and never read back (edit
  the docstring or a claims file instead);
- report docstring drift: claim names in the block missing from
  declared/verified and verified names missing from the block
  (writing those INTO the docstring is the explicit opt-in,
  `--write-docstrings`; an implicit generated edit would author by
  accident);

Intent rule: a docstring's intent wins over a declared file's and the
materialized entry carries it; the declared file's intent is the
skeleton only when the function has no docstring at all.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class SyncReport:
    """One docsync pass: what was materialized, every conflict, and
    the docstring drift, the CLI renders this and the verify sweep
    treats conflicts as gate problems."""
    materialized: list = field(default_factory=list)   # keys written
    conflicts: list = field(default_factory=list)      # {key, claim, docstring, declared}
    drift: list = field(default_factory=list)          # {key, kind, names}
    docstrings_written: list = field(default_factory=list)
    index_path: str | None = None


def _identity(statement: str, domain: "dict | None" = None) -> "tuple | None":
    """Intent:
        A claim's identity: the `fingerprint_text` of the claim this
        text states, any side `domain` dict merged the same way
        `entry_claims` merges one. Every spelling of one claim (an
        inline quantifier, a split-out domain field, a verified row's
        canonical statement) lands on the same string.

    Raises:
        InvalidConjecture: the text does not parse. Identity that
        cannot be computed is an error to surface, never a comparison
        to silently skip; the old fingerprint returned None here, and
        a conflict on an unparseable claim simply vanished.
    """
    from .spec import _declared_conjecture, fingerprint_text
    return (fingerprint_text(_declared_conjecture(
        {"statement": statement, "domain": domain})),)


def _claim_identity(c: dict) -> "tuple | None":
    statement = c.get("statement") or c.get("law") or ""
    if not statement:
        return None
    return _identity(statement, c.get("domain"))


def _row_identity(row: dict) -> "tuple | None":
    """A verified row's identity: its statement is the canonical text,
    self-contained, so it reads exactly like a declared claim's."""
    return _claim_identity(row)


def _checked_differently(c: dict, row: dict) -> bool:
    """Intent:
        Whether an authored claim asks to be checked differently from
        its verified row, with the same statement: another tolerance,
        or another route. A row that records its authored route is
        compared with it directly; a row that does not (written before
        the authored route was kept) differs only when the claim names
        an explicit route its evidence route does not match, since a
        default-route claim may have been decided by either route.
    """
    from .spec import base_route

    def _tolerance(v):
        try:
            return None if v is None else float(v)
        except (TypeError, ValueError):
            return v

    if _tolerance(c.get("tolerance")) != _tolerance(row.get("tolerance")):
        return True
    want = base_route(c.get("route"))
    stated = (row.get("authored") or {}).get("route") \
        if isinstance(row.get("authored"), dict) else None
    if stated:
        return want != base_route(stated)
    return want != "best" and want != base_route(row.get("route"))


def _display_claim(c: dict) -> str:
    """The one canonical spelling of a declared claim dict, for a
    conflict report; text that does not parse displays verbatim (the
    report shows the reader what was written; comparison, which must
    not tolerate unparseable text, happens in `_claim_identity`)."""
    from .spec import _declared_conjecture, canonical_claim_text
    try:
        return canonical_claim_text(_declared_conjecture(c))
    except Exception:
        return c.get("statement") or c.get("law") or ""




def claim_conflicts(fn, file_entry: dict,
                    verified_entry: "dict | None" = None) -> list:
    """Intent:
        The layered conflict report, two kinds:

        - kind "authoring": the same claim NAME on the docstring and
          the declared file with different statements/regions, and the
          name NOT yet verified, resolvable by choosing a surface.
        - kind "supersession": an authored surface differs from the
          VERIFIED row. The verified layer is the record and wins
          (materialization adjudicates its version); changing a
          verified claim is a deliberate act, `mathema accept <key>
          <claim> --as superseded`.
    """
    import inspect

    from .authoring import parse_docstring_claims
    doc_claims = {c.get("name"): c
                  for c in parse_docstring_claims(inspect.getdoc(fn) or "")}
    verified_rows = {}
    for row in (verified_entry or {}).get("claims") or []:
        meta = row.get("meta") or {}
        if meta.get("mathema.surface") in ("mathema", "builtin",
                                                "types"):
            continue
        if meta.get("mathema.companion_of"):
            # spawned by its parent's proof, never authored
            continue
        if row.get("name") and row.get("name") != "dependencies_current":
            verified_rows[row["name"]] = row
    out = []
    seen = set()
    for surface, claims_list in (("docstring", list(doc_claims.values())),
                                 ("declared", file_entry.get("claims") or [])):
        for c in claims_list:
            name = c.get("name")
            v = verified_rows.get(name)
            if v is None or (name, "supersession") in seen:
                continue
            fp_a, fp_v = _claim_identity(c), _row_identity(v)
            if fp_a and fp_v and (fp_a != fp_v
                                  or _checked_differently(c, v)):
                seen.add((name, "supersession"))
                out.append({"kind": "supersession", "claim": name,
                            "surface": surface,
                            "authored": _display_claim(c),
                            "authored_raw": c,
                            "verified": v.get("statement")})
    for c in file_entry.get("claims") or []:
        name = c.get("name")
        if name in verified_rows:
            continue          # verified names are the supersession tier
        d = doc_claims.get(name)
        if d is None:
            continue
        if (_claim_identity(d) and _claim_identity(c)
                and _claim_identity(d) != _claim_identity(c)):
            out.append({"kind": "authoring", "claim": name,
                        "docstring": _display_claim(d),
                        "docstring_raw": d,
                        "declared": _display_claim(c),
                        "declared_raw": c})
    return out



def apply_verified_wins(claims: list, conflicts: list,
                        v_entry: dict) -> list:
    """Intent:
        The verified layer is the record: for every un-accepted
        supersession conflict, the authored claim is replaced in the
        adjudication set by the VERIFIED version (region recovered
        from its rendered condition), the authored text riding along
        as pending-supersession meta. Shared by materialization and
        the verify sweep, so the record never gets silently rewritten
        by a re-authored claim.
    """
    pending = {c["claim"] for c in conflicts
               if c.get("kind") == "supersession"}
    if not pending:
        return claims
    v_rows = {r.get("name"): r for r in v_entry.get("claims") or []}
    kept = []
    for c in claims:
        name = c.get("name")
        row = v_rows.get(name)
        if name in pending and row:
            # the row's statement is the canonical text, self-
            # contained; the structured fields ride beside it, so
            # nothing here re-parses a rendered condition
            from .spec import authored_route
            rebuilt = {"name": name, "statement": row.get("statement"),
                       "route": authored_route(row)}
            for field_name in ("domain", "grammar", "tolerance"):
                if row.get(field_name) is not None:
                    rebuilt[field_name] = row[field_name]
            rebuilt["meta"] = {"mathema.pending_supersession":
                               _display_claim(c)}
            kept.append(rebuilt)
        else:
            kept.append(c)
    return kept

def materialize_entry(fn, key: str, root: str = ".") -> dict:
    """Intent:
        The full declared entry for one function, every authoring
        surface merged at the documented precedence, verified
        membership unioned back in, the docstring's intent winning,
        written to `.mathema/declared/<key>.yaml` and returned.

    Notes:
        The written file is a MATERIALIZED VIEW: canonical output for
        people and agents, regenerated on every sync, and never read
        back by the engine (`load_declared` skips `.mathema/` by
        design). The authoring surfaces stay the one source of truth;
        this file is what they resolve to, spelled canonically.
    """
    from .authoring import retrieve
    from .spec import load_verified, write_yaml
    from .verify import _union_verified_membership

    entry = dict(retrieve(fn, root))
    verified = load_verified(root).get(key)
    v_entry = (verified or {}).get("entry") or {}
    # the verified layer is the record: where an authored surface
    # differs from a verified claim WITHOUT an accepted supersession,
    # the verified version is what keeps adjudicating, the authored
    # change waits for `accept --as superseded`
    entry["claims"] = apply_verified_wins(
        entry.get("claims") or [],
        claim_conflicts(fn, entry, v_entry), v_entry)
    entry["claims"] = _union_verified_membership(
        entry.get("claims") or [], v_entry)

    from .analysis import quiet_facts
    facts = quiet_facts(fn)
    doc_intent = getattr(facts, "doc_intent", None) if facts else None
    if doc_intent:
        entry["intent"] = doc_intent          # the docstring's hand wins
    # a declared-file intent already in `entry` stands as the skeleton
    # when there is no docstring intent at all

    path = os.path.join(root, ".mathema", "declared", f"{key}.yaml")
    write_yaml(path, {key: entry},
               header="materialized declared layer, regenerated by "
                      "mathema docsync and never read back: edits here are "
                      "overwritten; edit the docstring or a claims file")
    return entry


def docstring_drift(fn, entry: dict, verified_entry: dict | None) -> list:
    """Intent:
        The Claims:-block drift for one function: names in the block
        unknown to declared∪verified (likely typos or removals), and
        verified names absent from the block (candidates for
        --write-docstrings). Only reported when the docstring carries
        a Claims: marker at all.
    """
    import inspect
    import re

    from .authoring import parse_docstring_claims
    doc = inspect.getdoc(fn) or ""
    if not re.search(r"^\s*claims:\s*$", doc, re.I | re.M):
        return []
    doc_names = {c.get("name") for c in parse_docstring_claims(doc)}
    declared_names = {c.get("name") for c in entry.get("claims") or []}
    verified_names = {c.get("name")
                      for c in (verified_entry or {}).get("claims") or []
                      if (c.get("meta") or {}).get("mathema.surface")
                      not in ("mathema", "builtin", "types")
                      and c.get("name") != "dependencies_current"}
    out = []
    unknown = sorted(n for n in doc_names
                     if n and n not in declared_names | verified_names)
    missing = sorted(n for n in verified_names | declared_names
                     if n and n not in doc_names)
    if unknown:
        out.append({"kind": "unknown-in-docstring", "names": unknown})
    if missing:
        out.append({"kind": "missing-from-docstring", "names": missing})
    return out


def write_claims_into_docstring(fn, names_with_statements: list) -> bool:
    """Intent:
        The explicit `--write-docstrings` edit: append the given
        (name, canonical statement) pairs as new lines at the end of
        an EXISTING Claims: block in the function's source docstring.
        Returns False without touching the file when there is no
        block, the source can't be located, or nothing is missing,
        never creates a block, never rewrites a human's prose.
    """
    import inspect
    import re
    if not names_with_statements:
        return False
    try:
        src_file = inspect.getsourcefile(fn)
        lines, start = inspect.getsourcelines(fn)
    except (OSError, TypeError):
        return False
    header_idx = None
    header_indent = ""
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)claims:\s*$", line, re.I)
        if m:
            header_idx = i
            header_indent = m.group(1)
            break
    if header_idx is None or src_file is None:
        return False
    item_indent = header_indent + "    "
    # the block ends at the first line NOT deeper-indented than the header
    end = header_idx + 1
    while end < len(lines):
        stripped = lines[end].strip()
        if stripped and not lines[end].startswith(item_indent):
            break
        if stripped:
            item_indent_seen = lines[end][:len(lines[end])
                                          - len(lines[end].lstrip())]
            item_indent = item_indent_seen
        end += 1
    additions = [f"{item_indent}{name}: {statement}\n"
                 for name, statement in names_with_statements]
    with open(src_file) as fh:
        all_lines = fh.readlines()
    insert_at = start - 1 + end
    all_lines[insert_at:insert_at] = additions
    with open(src_file, "w") as fh:
        fh.writelines(all_lines)
    return True


def sync(targets: list, root: str = ".",
         write_docstrings: bool = False) -> SyncReport:
    """Intent:
        The whole docsync pass over resolved targets:
        records, materialize every key's declared entry, collect
        conflicts and drift, optionally perform the explicit
        docstring write-back, and regenerate the index.
    """
    from .authoring import _fn_key
    from .spec import load_declared, load_verified
    from .targets import resolve

    report = SyncReport()
    declared_store = load_declared(root)
    verified_store = load_verified(root)

    functions: dict = {}
    if targets:
        for target in targets:
            functions.update(resolve(target, root).functions)
    else:
        # rootwide, no explicit target: the docsync analogue of `verify`,
        # every function the declared/verified stores already know,
        # resolved back to its live callable (a key that no longer
        # imports is skipped, same as verify's own sweep).
        from .conjecture import _resolve_func_ref
        for key in sorted(set(declared_store) | set(verified_store)):
            fn = _resolve_func_ref(key)
            if fn is not None:
                functions[key] = fn

    for key, fn in sorted(functions.items()):
        key = _fn_key(fn) if key is None else key
        file_entry = (declared_store.get(key) or {}).get("entry", {})
        v_entry = (verified_store.get(key) or {}).get("entry")
        report.conflicts.extend(
            {"key": key, **c}
            for c in claim_conflicts(fn, file_entry, v_entry))
        entry = materialize_entry(fn, key, root)
        report.materialized.append(key)
        v_entry = (verified_store.get(key) or {}).get("entry")
        for d in docstring_drift(fn, entry, v_entry):
            report.drift.append({"key": key, **d})
            if write_docstrings and d["kind"] == "missing-from-docstring":
                by_name = {c.get("name"): c for c in entry.get("claims") or []}
                pairs = [(n, (by_name.get(n) or {}).get("statement") or "")
                         for n in d["names"]]
                pairs = [(n, st) for n, st in pairs if st]
                if write_claims_into_docstring(fn, pairs):
                    report.docstrings_written.append(key)

    from .audit import write_index
    try:
        report.index_path = write_index(list(targets), root=root)
    except Exception:
        report.index_path = None
    return report
