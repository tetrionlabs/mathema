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

from dataclasses import dataclass, field


@dataclass
class SyncReport:
    """One docsync pass: what was materialized, every conflict, and
    the docstring drift, the CLI renders this and the verify sweep
    treats conflicts as gate problems. `index_error` is the error that
    stopped the index being written, as `<type>: <message>`, and None
    when it was written."""
    materialized: list = field(default_factory=list)   # keys written
    conflicts: list = field(default_factory=list)      # {key, claim, docstring, declared}
    drift: list = field(default_factory=list)          # {key, kind, names}
    docstrings_written: list = field(default_factory=list)
    index_path: str | None = None
    index_error: str | None = None
    unreadable: list = field(default_factory=list)     # {key, claim, where, error}
    stale_records: list = field(default_factory=list)  # {key, claim, verified}
    defects: list = field(default_factory=list)        # {key, claim, message}


def _completed(cj, fn):
    """The conjecture with its own bindings completed from `fn`'s
    annotations, the form its record states."""
    if fn is None:
        return cj
    from dataclasses import replace

    from .conjecture import _complete_missing
    completed = _complete_missing(cj, fn)[0]
    return replace(cj, domain=completed) if completed else cj


def _identity(statement: str, domain: "dict | None" = None,
              fn=None) -> "tuple | None":
    """Intent:
        A claim's identity: the `fingerprint_text` of the claim this
        text states, any side `domain` dict merged the same way
        `entry_claims` merges one, its bindings completed from `fn`'s
        annotations when `fn` is given. Every spelling of one claim (an
        inline quantifier, a split-out domain field, a verified row's
        canonical statement) lands on the same string.

    Raises:
        InvalidConjecture: the text does not parse. Identity that
        cannot be computed is an error to surface, never a comparison
        to silently skip; the old fingerprint returned None here, and
        a conflict on an unparseable claim simply vanished.
    """
    from ._annotation_text import complex_parameters
    from .grammar import complex_in_view
    from .spec import _declared_conjecture, fingerprint_text
    with complex_in_view(complex_parameters(fn) if fn is not None else ()):
        return (fingerprint_text(_completed(_declared_conjecture(
            {"statement": statement, "domain": domain}), fn)),)


def _claim_identity(c: dict, fn=None) -> "tuple | None":
    statement = c.get("statement") or c.get("law") or ""
    if not statement:
        return None
    return _identity(statement, c.get("domain"), fn)


def _row_identity(row: dict, fn=None) -> "tuple | None":
    """A verified row's identity: its statement is the canonical text,
    self-contained, so it reads exactly like a declared claim's."""
    return _claim_identity(as_recorded(row), fn)


def _without_constant_holes(bound):
    """Intent:
        A `let` constant's domain without the hole class, and without
        the real type stated beside it, or None when the domain admits
        no hole.
    """
    from dataclasses import replace

    from .domain import _as_domain
    dom = _as_domain(bound)

    def hole(v):
        return getattr(v, "kind", None) == "missing"

    if not any(isinstance(p, frozenset) and any(hole(v) for v in p)
               for p in dom.pieces):
        return None
    pieces = tuple(frozenset(v for v in p if not hole(v))
                   if isinstance(p, frozenset) else p for p in dom.pieces)
    pieces = tuple(p for p in pieces if not (isinstance(p, frozenset) and not p))
    stated = dom.base_type != "R"
    return replace(dom, pieces=pieces, explicit_type=stated,
                   clause=stated or dom.absent, policy=None)


def as_recorded(row: dict) -> dict:
    """Intent:
        A verified row as the claim it records. A row written by an
        earlier release spells a `let` constant with its type and the
        hole class (`let rho be [0.01, 0.99]:float|missing`): the
        type's missing-value default, rendered beside a constant that
        has no hole. That row reads as the constant alone (`let rho be
        [0.01, 0.99]`), its statement the canonical text this release
        writes. Every other row reads as written.
    """
    from dataclasses import replace

    from .spec import _declared_conjecture, canonical_claim_text
    if not row.get("statement") or not _written_by_an_earlier_release(row):
        return row
    try:
        cj = _declared_conjecture({"statement": row["statement"],
                                   "domain": row.get("domain")})
    except Exception:
        return row
    domain = dict(cj.domain)
    for name in cj.free_vars:
        if name in domain:
            bare = _without_constant_holes(domain[name])
            if bare is not None:
                domain[name] = bare
    if domain == cj.domain:
        return row
    return {**row, "statement": canonical_claim_text(replace(cj, domain=domain))}


#: the release whose canonical text first states what a domain admits
IDENTITY_RELEASE = "0.6.1"


def _without_missing_policy(c: dict) -> "str | None":
    """Intent:
        A claim's canonical text with every missing-value statement left
        out (no sentinel in any binding, none rendered), so two
        spellings that differ only in what they say about missing
        values read alike.
    """
    from dataclasses import replace

    from .domain import Domain, _as_domain, is_sentinel
    from .spec import _declared_conjecture, render_claim_text
    statement = c.get("statement") or c.get("law") or ""
    if not statement:
        return None

    def strip(bound):
        if bound is None or isinstance(bound, str):
            return bound
        dom = _as_domain(bound)
        pieces = tuple(frozenset(v for v in p if not is_sentinel(v))
                       if isinstance(p, frozenset) else p for p in dom.pieces)
        pieces = tuple(p for p in pieces if not (isinstance(p, frozenset) and not p))
        return Domain(base_type=dom.base_type, pieces=pieces,
                      excluded=frozenset(v for v in dom.excluded
                                         if not is_sentinel(v)),
                      explicit_type=dom.explicit_type, dims=dom.dims)

    cj = _declared_conjecture({"statement": statement, "domain": c.get("domain")})
    cj = replace(cj, domain={p: strip(b) for p, b in cj.domain.items()})
    return render_claim_text(cj, unicode=False, canonical=True,
                             show_missing=False)


def _written_by_an_earlier_release(row: dict) -> bool:
    """Whether a verified row's statement is not the canonical text this
    release writes for it: a row recorded before the canonical domain
    spelling moved."""
    from .spec import _declared_conjecture, canonical_claim_text
    statement = row.get("statement") or ""
    try:
        return canonical_claim_text(_declared_conjecture(
            {"statement": statement, "domain": row.get("domain")})) != statement
    except Exception:
        return False


def release_moved(c: dict, row: dict) -> bool:
    """Intent:
        Whether an authored claim and its verified row differ only
        because the canonical text moved in `IDENTITY_RELEASE`: the row
        was written by an earlier release, and the two read alike once
        every missing-value statement is left out.
    """
    try:
        return (_written_by_an_earlier_release(row)
                and _without_missing_policy(c) == _without_missing_policy(row))
    except Exception:
        return False


def _legacy_renderings() -> dict:
    """Intent:
        `{move name: context manager}` for each earlier rendering of
        stored claim text this release can reproduce.
    """
    from ._scan import (legacy_domain_escapes, legacy_not_parentheses,
                        legacy_quoting)
    return {"literal-quoting": legacy_quoting,
            "not-parentheses": legacy_not_parentheses,
            "domain-escapes": legacy_domain_escapes}


def _set_strings(domain: dict) -> dict:
    """Intent:
        `{name: sorted string members}` of each domain binding that has a
        string member in a discrete set.
    """
    from .domain import _as_domain
    out = {}
    for name, bound in (domain or {}).items():
        try:
            pieces = _as_domain(bound).pieces
        except Exception:
            continue
        found = sorted(v for p in pieces if isinstance(p, frozenset)
                       for v in p if isinstance(v, str))
        if found:
            out[name] = found
    return out


def text_rules_of(verified_entry: "dict | None") -> "str | None":
    """Intent:
        The release whose statement text rules a verified record's rows
        were written under (`lineage.statement_text`), or None for a
        record written by a release before `spec.STATEMENT_TEXT_RELEASE`,
        which states none.
    """
    lineage = (verified_entry or {}).get("lineage")
    rules = lineage.get("statement_text") if isinstance(lineage, dict) else None
    return rules if isinstance(rules, str) else None


def written_under_earlier_text(verified_entry: "dict | None") -> bool:
    """Intent:
        Whether a verified record was written before the statement text
        rules of `spec.STATEMENT_TEXT_RELEASE`: it states no rules, or
        the rules of an earlier release.
    """
    from .spec import STATEMENT_TEXT_RELEASE

    def parts(v):
        return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))

    rules = text_rules_of(verified_entry)
    return rules is None or parts(rules) < parts(STATEMENT_TEXT_RELEASE)


def _recorded_set_strings(row: dict) -> "dict | None":
    """Intent:
        `_set_strings` of a verified row's recorded `domain`, or None
        when the row records no domain or one that does not read.
    """
    from .grammar import domain_bound_from_json
    domain = row.get("domain")
    if not isinstance(domain, dict):
        return None
    try:
        return _set_strings({n: domain_bound_from_json(b)
                             for n, b in domain.items()})
    except Exception:
        return None


def _renders_as(cj, statement: str, names: tuple) -> "tuple | None":
    """Intent:
        The smallest set of the earlier renderings `names` (none at
        all, then each alone, then together) under which `cj`'s
        canonical text is `statement`, or None when none gives it.
    """
    import contextlib
    import itertools

    from .spec import canonical_claim_text
    renderings = _legacy_renderings()
    for size in range(0, len(names) + 1):
        for chosen in itertools.combinations(sorted(names), size):
            with contextlib.ExitStack() as stack:
                for name in chosen:
                    stack.enter_context(renderings[name]())
                if canonical_claim_text(cj) == statement:
                    return chosen
    return None


def _domain_escapes_move(c: dict, row: dict, fn=None) -> "list | None":
    """Intent:
        The domain values whose reading changed, as `(written, value
        now)` pairs, when the verified `row` records the authored claim
        `c` as releases up to 0.6.6.1 read it: `c` has a domain set
        string member whose backslash escape those releases read as its
        characters undecoded, the row's statement is `c`'s text under
        that reading (with any other earlier rendering of the text), and
        the row's recorded `domain` does not hold the values read now
        (it holds the old values, or is absent or does not read). None
        otherwise, so any other difference between `c` and the row is
        left to the supersession check. `written` is the member as the
        author wrote it. The caller applies this only to a row of a
        record written under earlier text rules.
    """
    from ._annotation_text import complex_parameters
    from ._scan import legacy_domain_escapes
    from .domain import _string_member
    from .grammar import complex_in_view
    from .spec import _declared_conjecture
    statement = c.get("statement") or c.get("law") or ""
    stored = row.get("statement") or ""
    if "\\" not in statement or not stored:
        return None
    try:
        with complex_in_view(complex_parameters(fn) if fn is not None else ()):
            now = _set_strings(_declared_conjecture(c).domain)
            with legacy_domain_escapes():
                old = _completed(_declared_conjecture(c), fn)
                before = _set_strings(old.domain)
                if now == before:
                    return None
                if _renders_as(old, stored, ("literal-quoting",
                                             "not-parentheses")) is None:
                    return None
    except Exception:
        return None
    changed = [n for n in before if before[n] != now.get(n)]
    recorded = _recorded_set_strings(row)
    if recorded is not None and all(recorded.get(n) == now.get(n) for n in changed):
        return None
    pairs = []
    for name in sorted(before):
        for value in sorted(set(before[name]) - set(now.get(name) or [])):
            written = f'"{value}"'
            try:
                pairs.append((written, _string_member(written)))
            except ValueError:
                continue
    return pairs or None


def _legacy_move(c: dict, row: dict, fn=None) -> "tuple | None":
    """Intent:
        The earlier renderings, by move name, under which releases up to
        0.6.6.1 wrote a verified row's statement for the authored claim
        `c`, or None when the row's statement is the canonical text
        written now or no earlier rendering (alone or together) gives
        it. A row a move names records `c`, whether or not its old text
        reads back as `c`. The caller applies this only to a row of a
        record written under earlier text rules.
    """
    from ._annotation_text import complex_parameters
    from .grammar import complex_in_view
    from .spec import _declared_conjecture
    statement = row.get("statement") or ""
    if not statement or ("'" not in statement and '"' not in statement
                         and "not" not in statement):
        return None
    try:
        with complex_in_view(complex_parameters(fn) if fn is not None else ()):
            cj = _completed(_declared_conjecture(c), fn)
            moved = _renders_as(cj, statement, tuple(sorted(_legacy_renderings())))
    except Exception:
        return None
    return moved or None


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




def _foreign_skip(row: dict) -> bool:
    """A verified row that is a claim skipped as written in another
    grammar, which no route here adjudicated."""
    return (row.get("verdict") == "skipped"
            and "mathema.foreign_grammar" in (row.get("meta") or {}))


def claim_conflicts(fn, file_entry: dict,
                    verified_entry: "dict | None" = None) -> list:
    """Intent:
        The layered conflict report, two kinds:

        - kind "authoring": the same claim NAME on the docstring and
          the declared file with different statements/regions, and the
          name NOT yet verified, resolvable by choosing a surface.
        - kind "unreadable-record": the verified row's stored statement
          does not parse, so the row is stale and the authored claim is
          adjudicated as written.
        - kind "canonical-text-defect": mathema cannot write the stored
          text of the authored claim or of its verified row
          (`CanonicalTextError`, under `error`), so the two are not
          compared; the claim is not adjudicated and its row is left as
          it was.
        - kind "release-move": the verified row was written by an
          earlier release and records the authored claim in the text,
          or with the domain reading, that release wrote; the claim is
          adjudicated as written, with no supersession. A move of
          literal quoting, negation parentheses or domain escapes is
          recognised only in a record written under earlier statement
          text rules (`written_under_earlier_text`).
        - kind "supersession": an authored surface differs from the
          VERIFIED row. The verified layer is the record and wins
          (materialization adjudicates its version); changing a
          verified claim is a deliberate act, `mathema accept <key>
          <claim> --as superseded`. A verified row skipped as another
          grammar's claim holds no verdict, so it is never in
          conflict: the authored claim is adjudicated as written.
    """

    from .analysis import docstring_of
    from .authoring import _fn_key, parse_docstring_claims
    from .conjecture import CanonicalTextError, InvalidConjecture
    doc_claims = {c.get("name"): c
                  for c in parse_docstring_claims(docstring_of(fn),
                                                  owner=_fn_key(fn))}
    earlier = written_under_earlier_text(verified_entry)

    def defect(name, surface, error, c, row=None):
        return {"kind": "canonical-text-defect", "claim": name,
                "surface": surface, "error": error,
                "authored": c.get("statement") or c.get("law") or "",
                "verified": (row or {}).get("statement")}
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
            if _foreign_skip(v):
                # a claim skipped as another grammar's established
                # nothing, so there is no verdict for the record to
                # keep: the authored claim is adjudicated as written
                continue
            escapes = _domain_escapes_move(c, v, fn) if earlier else None
            if escapes and not _checked_differently(c, v):
                # the row records the values an earlier release read for
                # this claim's domain: adjudicated on the values it names
                seen.add((name, "supersession"))
                out.append({"kind": "release-move", "claim": name,
                            "moved": ("domain-escapes",),
                            "escapes": escapes,
                            "surface": surface,
                            "authored": _display_claim(c),
                            "verified": v.get("statement")})
                continue
            moved = _legacy_move(c, v, fn) if earlier else None
            if moved and not _checked_differently(c, v):
                # the row records this claim in the text an earlier
                # rendering wrote for it: adjudicated as written, the
                # same way as a release move of the canonical text
                seen.add((name, "supersession"))
                out.append({"kind": "release-move", "claim": name,
                            "moved": moved,
                            "surface": surface,
                            "authored": _display_claim(c),
                            "verified": v.get("statement")})
                continue
            try:
                fp_a = _claim_identity(c, fn)
            except CanonicalTextError as e:
                # mathema cannot write this claim's stored text, so the
                # two cannot be compared: the row is left as it was
                seen.add((name, "supersession"))
                out.append(defect(name, surface, e, c, v))
                continue
            try:
                fp_v = _row_identity(v, fn)
            except CanonicalTextError as e:
                seen.add((name, "supersession"))
                out.append(defect(name, surface, e, c, v))
                continue
            except InvalidConjecture:
                # the stored statement records nothing: the row is stale
                # and the authored claim is adjudicated as written
                seen.add((name, "supersession"))
                out.append({"kind": "unreadable-record", "claim": name,
                            "surface": surface,
                            "authored": _display_claim(c),
                            "verified": v.get("statement")})
                continue
            if fp_a and fp_v and fp_a != fp_v \
                    and not _checked_differently(c, v) and release_moved(c, v):
                # the canonical text moved under the claim, the author
                # changed nothing: adjudicated as written, and reported
                # once for the whole run rather than claim by claim
                seen.add((name, "supersession"))
                out.append({"kind": "release-move", "claim": name,
                            "surface": surface,
                            "authored": _display_claim(c),
                            "verified": v.get("statement")})
                continue
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
        try:
            fp_d, fp_c = _claim_identity(d, fn), _claim_identity(c, fn)
        except CanonicalTextError as e:
            out.append(defect(name, "declared", e, c))
            continue
        if fp_d and fp_c and fp_d != fp_c:
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
            rebuilt = {"name": name, "statement": as_recorded(row).get("statement"),
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

def yaml_has_comments(text: str) -> bool:
    """Intent:
        Whether YAML source carries a `#` comment: a `#` that starts a
        line's content or follows whitespace, outside a quoted scalar.
        A `#` inside quotes, or glued to a plain word (`a#b`), is text.
    """
    for line in text.splitlines():
        quote = None
        prev = " "
        i = 0
        while i < len(line):
            ch = line[i]
            if quote == "'":
                if ch == "'":
                    if line[i + 1:i + 2] == "'":
                        i += 1
                    else:
                        quote = None
            elif quote == '"':
                if ch == "\\":
                    i += 1
                elif ch == '"':
                    quote = None
            elif ch in "'\"" and (prev.isspace() or prev in ":-[{,"):
                quote = ch
            elif ch == "#" and prev.isspace():
                return True
            prev = ch
            i += 1
    return False


def materialize_entry(fn, key: str, root: str = ".", *,
                      declared_store: "dict | None" = None,
                      verified_store: "dict | None" = None) -> dict:
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

        `declared_store` and `verified_store` are the mappings
        `spec.load_declared(root)` and `spec.load_verified(root)`
        return, already loaded; each one not given is loaded here. The
        entry used from a given store is a copy, so the store is left
        as it was.
    """
    import copy

    from .authoring import _fn_key, retrieve
    from .spec import load_verified, write_yaml
    from .verify import _union_verified_membership

    if declared_store is None:
        entry = dict(retrieve(fn, root))
    else:
        own_key = _fn_key(fn)
        held = declared_store.get(own_key)
        entry = dict(retrieve(
            fn, root,
            store={} if held is None else {own_key: copy.deepcopy(held)}))
    if verified_store is None:
        verified = load_verified(root).get(key)
    else:
        verified = copy.deepcopy(verified_store.get(key))
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

    from .spec import declared_dir, record_path
    path = record_path(declared_dir(root), key)
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
    import re

    from .analysis import docstring_of
    from .authoring import _fn_key, parse_docstring_claims
    doc = docstring_of(fn)
    if not re.search(r"^\s*claims:\s*$", doc, re.I | re.M):
        return []
    doc_names = {c.get("name") for c in parse_docstring_claims(
        doc, owner=_fn_key(fn))}
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

    Raises:
        ValueError: `fn` carries injected facts, so its Python source
            is a wrapper's and not the source of the function the facts
            describe.
    """
    import inspect
    import re

    from .analysis import has_injected_facts
    if has_injected_facts(fn):
        name = getattr(fn, "__qualname__", None) or repr(fn)
        raise ValueError(
            f"cannot write claims into the docstring of {name}: it carries "
            f"injected facts, so its Python source is not the source of "
            f"the function they describe; add the claims to that "
            f"function's own docstring or to a claims file")
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
    from ._run_scope import wrote
    wrote(src_file)
    return True


def sync(targets: list, root: str = ".",
         write_docstrings: bool = False) -> SyncReport:
    """Intent:
        The whole docsync pass over resolved targets:
        records, materialize every key's declared entry, collect
        conflicts and drift, optionally perform the explicit
        docstring write-back, and regenerate the index.

    Notes:
        The pass runs in a `_run_scope.run_scope()`, so its reads of
        the stores, the claims files and the curation file are shared
        across the functions it syncs.
    """
    from ._run_scope import run_scope
    with run_scope():
        return _sync(targets, root, write_docstrings)


def _sync(targets: list, root: str, write_docstrings: bool) -> SyncReport:
    """Intent:
        `sync`'s pass, inside its run scope: both stores are loaded
        once and every function's entry is materialized from them.
    """
    from .authoring import _fn_key
    from .conjecture import CanonicalTextError, InvalidConjecture
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

    resolved: dict = {}
    for key, fn in sorted(functions.items()):
        key = _fn_key(fn) if key is None else key
        resolved[key] = fn
        file_entry = (declared_store.get(key) or {}).get("entry", {})
        v_entry = (verified_store.get(key) or {}).get("entry")
        try:
            conflicts = claim_conflicts(fn, file_entry, v_entry)
            entry = materialize_entry(fn, key, root,
                                      declared_store=declared_store,
                                      verified_store=verified_store)
        except CanonicalTextError as e:
            report.defects.append(canonical_text_defect(
                key, getattr(e, "claim_name", None) or "a claim", e,
                declared_store.get(key), root))
            continue
        except InvalidConjecture as e:
            report.unreadable.append(unreadable_claim(
                key, fn, e, declared_store.get(key), verified_store.get(key), root))
            continue
        report.defects.extend(
            canonical_text_defect(key, c["claim"], c["error"],
                                  declared_store.get(key), root)
            for c in conflicts if c.get("kind") == "canonical-text-defect")
        report.conflicts.extend(
            {"key": key, **c} for c in conflicts
            if c.get("kind") not in ("release-move", "unreadable-record",
                                     "canonical-text-defect"))
        report.stale_records.extend(
            {"key": key, **c} for c in conflicts if c.get("kind") == "unreadable-record")
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
        # a named target indexes the functions it resolved to; with no
        # target the index keeps `write_index`'s own discovery
        report.index_path = write_index(list(targets), root=root,
                                        functions=resolved if targets else None)
    except Exception as exc:
        report.index_path = None
        report.index_error = f"{type(exc).__name__}: {exc}"
    return report


def canonical_text_defect(key: str, name: str, error,
                          declared: "dict | None", root: str = ".") -> dict:
    """Intent:
        A claim of function `key` whose stored text mathema cannot write
        (`CanonicalTextError`), as `{key, claim, message}`: `message` is
        the diagnostic `verify.canonical_text_defect_message` gives,
        located in the claims file that states it when that is found.
    """
    from .verify import canonical_text_defect_message, claim_location
    source = (declared or {}).get("source")
    return {"key": key, "claim": name,
            "message": canonical_text_defect_message(
                key, name, source, error,
                claim_location(root, source, key, name), command="docsync")}


def unreadable_claim(key: str, fn, error, declared: "dict | None",
                     verified: "dict | None", root: str = ".") -> dict:
    """Intent:
        The claim of function `key` that docsync could not read, as
        `{key, claim, where, error}`: `where` is `path:line` of its
        statement (a verified record, a claims file, or the function's
        source for a docstring claim), or the path alone when the line
        is not found. Each claim is read on its own to find the one
        that fails; when none does, `claim` is None and `where` names
        the claims file or record.
    """
    import os

    from .conjecture import InvalidConjecture
    from .spec import claim_statement_line, claims_file_paths

    def located(rel, name):
        line = claim_statement_line(os.path.join(root, rel), key, name)
        return f"{rel}:{line}" if line else rel

    def fails(read):
        try:
            read()
        except InvalidConjecture as e:
            return e
        return None

    for row in ((verified or {}).get("entry") or {}).get("claims") or []:
        if row.get("name") and row.get("statement") \
                and fails(lambda: _row_identity(row, fn)):
            return {"key": key, "claim": row["name"], "error": str(error),
                    "where": located((verified or {}).get("source") or "", row["name"])}
    for c in ((declared or {}).get("entry") or {}).get("claims") or []:
        if c.get("name") and fails(lambda: _claim_identity(c, fn)):
            for path in reversed(claims_file_paths(root)):
                rel = os.path.relpath(path, root)
                if claim_statement_line(path, key, c["name"]):
                    return {"key": key, "claim": c["name"], "error": str(error),
                            "where": located(rel, c["name"])}
            return {"key": key, "claim": c["name"], "error": str(error),
                    "where": (declared or {}).get("source") or ""}
    return {"key": key, "claim": None, "error": str(error),
            "where": (verified or declared or {}).get("source") or ""}
