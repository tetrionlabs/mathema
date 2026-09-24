# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The decoupled spec: everything mathema knows about a function, as a
standalone YAML record conforming to the claim-driven-development repo's
v0.2.0/record-schema.md; intent, identity, claims with verdicts, references,
and the chain of reasoning that connects them. The `math` and `concepts`
fields are reserved for a future understanding/Mathemata layer and are
always empty in a v0.1 record.

The spec is deliberately independent of the Python implementation: it carries
the identity hashes, so it can outlive the code and be re-verified against a
regeneration.
"""
from __future__ import annotations

import datetime
import os
import re
import unicodedata

from .records import (SUPPORTED_VERDICTS, classify_verdict,
                      pseudo_infinity_range, statement_text)
from .routes import examine_predicates

# The CDD spec version this module's writer/reader conforms to: see the
# sibling claim-driven-development repo's v0.2.0/record-schema.md and
# CHANGELOG.md. Stamped into every record's lineage.CDD_spec_version field.
SPEC_VERSION = "0.2.0"


def reasoning_chain(ex) -> list[dict]:
    """The persistent chain of reasoning: intent → structure → formalization →
    derivation → evidence → situation in the concept graph. Each link states
    its claim and its basis (which evidence class it rests on)."""
    chain: list[dict] = []
    f = ex.facts
    if f.doc_intent:
        chain.append({"step": "intent", "claim": f.doc_intent,
                      "basis": "documented; the author's stated purpose"})
    for loop in f.loops:
        if loop.kind == "fold":
            chain.append({"step": "structure",
                          "claim": f"a left fold over {loop.iter_src} with accumulator '{loop.acc}'",
                          "basis": "read off the AST"})
    if f.comprehensions:
        chain.append({"step": "structure",
                      "claim": f"comprehension pipeline: {', '.join(f.comprehensions)}",
                      "basis": "read off the AST"})
    if ex.lifted is not None:
        chain.append({"step": "formalization", "claim": ex.lifted.unicode,
                      "basis": "symbolic lift of the body"})
        for d in ex.lifted.derived:
            link = {"step": "derivation", "claim": d.statement,
                    "basis": d.sketch or "symbolic derivation"}
            if d.condition:
                link["condition"] = d.condition
            chain.append(link)
    for p in ex.probes:
        if p.verdict == "proven":
            # a proven conjecture (check_conjectures()'s derive route,
            # not ex.lifted.derived's automatic-derivation pass above;
            # the two are different sources of a "derivation" step) has
            # no `n` and no counterexample; its own sketch *is* the
            # basis, the algebraic derivation that settled it.
            chain.append({"step": "derivation", "claim": p.statement,
                          "basis": p.sketch or "symbolic derivation"})
        elif p.verdict == "holds":
            chain.append({"step": "evidence", "claim": p.statement,
                          "basis": f"probed, n={p.n}"})
        elif p.verdict == "falsified":
            # a derive-route disproof carries its reasoning in `sketch`,
            # not `counterexample` (there's no single sampled input to
            # name, the two sides simplify to different expressions
            # over the whole domain); a probe-route falsification is the
            # reverse. Prefer whichever one the verdict actually has.
            basis = (f"counterexample {p.counterexample}" if p.counterexample
                    else p.sketch or "falsified")
            chain.append({"step": "refutation", "claim": f"NOT ({p.statement})",
                          "basis": basis})
        elif classify_verdict(p.verdict) in ("skipped", "unknown"):
            chain.append({"step": "gap", "claim": p.statement,
                          "basis": p.sketch or p.note or "could not be adjudicated"})
    if ex.concepts:
        chain.append({"step": "situating",
                      "claim": "instantiates: " + ", ".join(t.name for t in ex.concepts),
                      "basis": "deterministic concept tagging"})
    return chain


def group_references(triples) -> dict:
    """Intent:
        The record's references section, nested by role: plain
        citations under `reference`, working links under their own
        roles (`analysis`, `evidence`, `policy`). Only roles that
        actually have links appear; the item shape stays
        `{title, url}`.
    """
    grouped: dict = {}
    for t, u, via in triples or []:
        grouped.setdefault(via or "reference", []).append(
            {"title": t, "url": u})
    return grouped


# the record's authored.surface speaks the record schema's well-known
# surface names; row_source's internal tokens translate here, at the one
# write site, so nothing else in the pipeline changes vocabulary
_AUTHORED_SURFACES = {"declared": "claims-file", "types": "annotation",
                      "ad_hoc": "inline"}


def authored_block(meta: dict | None, note: str = "") -> dict:
    """A verified claim row's `authored` object. `surface` is stamped
    from what the pipeline observed (`records.row_source`); every other
    key is carried from the claim's own declared `authored` statement
    (threaded through meta as `mathema.authored`), the author's word on
    who/when/where, which this tool never overwrites. A v0.1.0-era bare
    string reads as `{ref: <string>}`. When no author was stated and the
    surface is one a person or agent authored, `by` falls back to the
    `MATHEMA_CLAIM_SOURCE` environment (the identity that ran the
    verification), so records produced by an agent carry their origin."""
    from .records import row_source
    surface = row_source(meta, note)
    block = {"surface": _AUTHORED_SURFACES.get(surface, surface)}
    carried = (meta or {}).get("mathema.authored")
    if isinstance(carried, str):
        carried = {"ref": carried}
    for k, v in (carried or {}).items():
        if k != "surface" and v is not None:
            block[k] = v
    if "by" not in block and block["surface"] not in (
            "suggested", "builtin", "compendium", "unknown"):
        # optional author identity (the model, harness, or git username
        # that proposed the claim), distinct from the surface it was
        # written on and the route it was checked by. Absent unless a
        # caller states it, on the claim's authored statement or the
        # MATHEMA_CLAIM_SOURCE environment a harness sets.
        author = os.environ.get("MATHEMA_CLAIM_SOURCE")
        if author:
            block["by"] = author
    return block



def _math_section(lifted) -> dict:
    """Intent:
        The record's `math` block for a lifted closed form: both
        rendered projections plus the exact `srepr` when the lift is a
        single sympy expression.
    """
    import sympy
    section = {"unicode": lifted.unicode, "latex": lifted.latex}
    expr = getattr(lifted, "expr", None)
    section["srepr"] = (sympy.srepr(expr)
                        if isinstance(expr, sympy.Basic) else None)
    return section

def to_spec(ex, include_suggestions: bool = False) -> dict:
    """A `mathema.Record` (or anything with the same `.facts`/`.probes`/
    `.lifted` shape) as a plain dict conforming to
    v0.2.0/record-schema.md: name, signature, intent, identity hashes,
    the (currently always-empty in v0.1) `math`/`concepts` fields, and
    the reasoning chain. `dump_yaml()`/`save_spec()` turn this into the
    actual on-disk record. `meta` is record-schema.md's own namespaced
    extension field, merged from two sources: `meta.notes` (from a
    docstring `Notes:` block, see docstring.py) and `Record.meta`
    itself (e.g. `meta["mathema.diagnostic_report"]`, opt-in only,
    see diagnostics.py), included only when at least one of the two
    is actually present, so a record with neither doesn't get a
    `meta: {}` line."""
    from . import __version__
    from .conjecture import DEFAULT_TOLERANCE

    f = ex.facts
    spec: dict = {
        # the dispatch key a consumer reads before anything else; the
        # same version lineage.CDD_spec_version states, hoisted to the
        # top level so dispatching needs no nested read
        "schema_version": SPEC_VERSION,
        "name": f.name,
        "signature": f.signature,
        "intent": f.doc_intent,
        # the grammar every claim statement in this record is written
        # in unless a row states its own (verified-schema.md's own
        # inherit-from-the-tool rule)
        "grammar": "mathema",
        # the closeness default in force for every claim in this record
        # that states no tolerance of its own (a per-claim `tolerance`
        # or an epsilon written into the law overrides it)
        "tolerance": DEFAULT_TOLERANCE,
        "identity": {"form": f.form, "sig": f.sigh,
                     "tier": f.tier,
                     # whether real source was analyzed, as opposed to
                     # a documentation-only record: "nothing proved"
                     # and "nothing to read" are different facts
                     "source_available": f.tree is not None,
                     "pure": f.is_pure},
        # unicode/latex are the human projections; srepr is the exact,
        # re-parseable form (sympy.sympify round-trips it), the one a
        # consumer can compute with. A tuple-valued lift has no single
        # expression, so srepr stays null there.
        "math": (_math_section(ex.lifted) if ex.lifted else None),
        "claims": [],
        "concepts": [t.name for t in ex.concepts] if ex.concepts else [],
        "references": group_references(f.doc_refs),
        "reasoning": reasoning_chain(ex),
        "lineage": {"generated_by": f"mathema {__version__}",
                    "CDD_spec_version": SPEC_VERSION,
                    "date": datetime.date.today().isoformat()},
    }
    deps = list(getattr(ex, "dependencies", None) or [])
    if deps:
        # one-deep callee records (inventory.function_dependencies):
        # written as their own section so freshness checks and agent
        # navigation (file + line, never grepping) read from the
        # record itself. `record()` annotates each with its freshness
        # against the store at write time.
        spec["dependencies"] = deps
    if f.tree is not None:
        from .inventory import _raised_exception_names
        raised = _raised_exception_names(f.tree)
        if raised:
            # the exception surface, persisted: half of what an intent
            # acceptance binds to (signature + raises + the text)
            spec["raises"] = raised
    meta = dict(getattr(ex, "meta", None) or {})   # Record.meta, e.g. "mathema.diagnostic_report", opt-in only
    if f.doc_notes:
        meta["notes"] = f.doc_notes
    if f.doc_intent:
        # intent is its own function-level section of the record, not a
        # claim. The rung ladder is declared -> documented, and
        # "documented" is a HUMAN act (mathema accept --intent), any
        # stated intent, an explicit Intent: block included, sits at
        # "declared" until a person accepts it. record() upgrades the
        # tag when a live (non-stale) intent acceptance stands.
        meta["mathema.intent_provenance"] = "declared"
    if meta:
        spec["meta"] = meta
    if ex.lifted:
        for d in ex.lifted.derived:
            spec["claims"].append({"name": d.concept, "statement": d.statement,
                                   "verdict": "derived", "condition": d.condition,
                                   "sketch": d.sketch})
    record_grammar = spec.get("grammar")
    for p in ex.probes:
        # A row carries only what it actually has. The optional fields
        # below are omitted when null/empty rather than written as
        # placeholders, `condition` is kept only on a derive row (where it
        # is the proof's own quantifier and can differ from the statement),
        # and per-row `grammar` is written only when it differs from the
        # record's, since the text and the record header already carry the
        # rest. `route` (record-schema.md's own field) is an open string, a
        # subroute (e.g. "derive:extensive", "probe:semi_analytical") when
        # the Probe's adjudication states one.
        row = {"name": p.name}
        if p.statement:
            # a machine diagnostic (a probe-gap skip, the dependency
            # freshness fact) asserts no law and carries no statement;
            # its reason rides `note`
            row["statement"] = p.statement
        row["verdict"] = p.verdict
        if p.n:
            row["n"] = p.n
        if p.counterexample is not None:
            row["counterexample"] = p.counterexample
        if p.note:
            row["note"] = p.note
        if p.sketch:
            row["sketch"] = p.sketch
        if p.condition and (p.route or "").split(":", 1)[0] == "derive":
            row["condition"] = p.condition
        row["route"] = p.route
        # where the claim came from: an object whose `surface` names the
        # authoring surface (the one always-known fact) and whose other
        # keys carry whatever origin detail rode the claim's meta
        row["authored"] = authored_block(p.meta, p.note or "")
        # the statement's own structured projection: machines read this, the
        # text re-parses to it
        if p.domain:
            row["domain"] = p.domain
        if p.grammar and p.grammar != record_grammar:
            row["grammar"] = p.grammar
        if p.tolerance is not None:
            row["tolerance"] = p.tolerance
        # the stratum rides meta on disk (a namespaced key needs no
        # schema change at spec v0.2.0; promotion to a row field is a
        # v0.3 matter), so the live field folds in here and claim_row
        # reads either shape identically
        row_meta = ({**(p.meta or {}), "mathema.stratum": p.stratum}
                    if getattr(p, "stratum", None) else (p.meta or None))
        if row_meta:
            row["meta"] = row_meta
        source = (p.meta or {}).get("mathema.surface")
        if not include_suggestions and (
                source == "mathema"
                or str(p.note or "").startswith("conjectured by mathema")):
            # a suggestion mathema volunteered is an AUTHORING-surface
            # helper, not a record of fact: it never enters the
            # verified layer at all. Adoption (mathema claims --adopt)
            # writes it into the declared spec, where it becomes an
            # ordinary claim adjudicated and gated like any other.
            continue
        spec["claims"].append(row)
    return spec


def _dump(value, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return pad + "{}\n"
        out = ""
        for k, v in value.items():
            if isinstance(v, (dict, list)) and v:
                out += f"{pad}{k}:\n" + _dump(v, indent + 1)
            elif isinstance(v, list):      # empty list: inline [], not the
                out += f"{pad}{k}: []\n"   # *string* "[]" _scalar() would emit
            elif isinstance(v, dict):
                out += f"{pad}{k}: {{}}\n"
            else:
                out += f"{pad}{k}: {_scalar(v)}\n"
        return out
    if isinstance(value, list):
        if not value:
            return pad + "[]\n"
        out = ""
        for item in value:
            if isinstance(item, (dict, list)) and item:
                body = _dump(item, indent + 1)
                first, _, rest = body.partition("\n")
                out += f"{pad}- {first.strip()}\n" + (rest if rest.strip() else "")
            else:
                out += f"{pad}- {_scalar(item)}\n"
        return out
    return pad + _scalar(value) + "\n"


def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        r = repr(v)
        if r in ("inf", "-inf", "nan"):
            return {"inf": ".inf", "-inf": "-.inf", "nan": ".nan"}[r]
        if "e" in r and "." not in r.split("e", 1)[0]:
            # yaml's float form needs a dot in the mantissa: repr's
            # dotless "1e-09" reads back as a string, not a number
            mantissa, exponent = r.split("e", 1)
            r = f"{mantissa}.0e{exponent}"
        return r
    if isinstance(v, int):
        return repr(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def dump_yaml(spec: dict) -> str:
    """Render a spec dict (from `to_spec()`) as YAML text, ready to
    write to disk."""
    return _dump(spec)


def write_yaml(path: str, data: dict, header: str | None = None) -> str:
    """Write one YAML document with an optional leading `#` comment
    block (one `# ` line per header line, so a multi-line header stays
    a comment), creating the parent directory first, the one shared
    spelling of every store write (specs, machine records, declared
    stubs, suggested claims). Returns `path`.

    The write is atomic (see `atomic_write_text`): an interrupted or
    failed write leaves the previous file exactly as it was."""
    text = ""
    if header:
        text = "".join(f"# {line}\n" if line else "#\n"
                       for line in header.splitlines())
    return atomic_write_text(path, text + dump_yaml(data))


def atomic_write_text(path: str, text: str) -> str:
    """Intent:
        Replace the file at `path` with `text` all at once, creating
        the parent directory first. The text goes to a temporary file
        in the same directory, is flushed to disk, and is renamed over
        `path`; a rename within one filesystem is atomic, so a reader
        (or an interrupted run) sees either the old file or the new
        one, never a truncated one. An existing file's permission
        bits carry over. Returns `path`.
    """
    import tempfile
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d or ".",
                               prefix=f".{os.path.basename(path)}.",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if os.path.exists(path):
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def save_spec(ex, path: str) -> str:
    """Write `ex`'s spec (`to_spec(ex)`) to `path` as YAML, keyed by
    the function's own name, with a header comment naming the identity
    hash it binds to. Returns `path`."""
    return write_yaml(path, {ex.facts.name: to_spec(ex)},
                      header=f"mathema spec: decoupled from implementation; "
                             f"binds to form {ex.facts.form}")


# ---------------------------------------------------------------------------
# The spec store: two shapes, two file sets, kept genuinely separate
#
# This mirrors claim-driven-development's own split between
# declared-schema.md and verified-schema.md, which are deliberately two
# different shapes, not two layers of one merged blob: a declared entry is
# what's written *before anything runs* (intent, claims, no identity, a
# hash is a fact about checked code, not a thing a human declares), and a
# verified entry is what a checking tool writes *after* adjudication
# (identity.form/sig, per-claim verdicts). Conflating them one merged-blob
# key at a time is a trap: a declared file that only ever states `claims`
# would silently blot out the verified layer's `identity.form` for that
# key, breaking the one thing (`mathema verify`'s freshness diff) that
# depends on that hash surviving. So:
#
#   load_declared(), *.claims.yaml, claims/*.yaml, claimspec.yaml, anywhere
#                      in the tree, any number of files, even several for
#                      the same function in different grammars: claims
#                      merge by claim name across files (deeper file wins
#                      per claim), a file-level `grammar` field sets that
#                      file's default dialect. Never carries `identity`.
#   load_verified() , .mathema/verified/<key>.yaml, one machine-written file
#                       per function (what `record()` produces). This, and
#                       only this, is the freshness baseline.
#   load_specs()    ; a read-only, display-only merge of the two, for
#                       `mathema status` and human introspection. Anything
#                       that decides what to adjudicate or whether code has
#                       changed must call load_declared()/load_verified()
#                       directly, never this merged view.
#
# Keys are dotted names (module.qualname) so many files share one namespace.
# ---------------------------------------------------------------------------

def claims_fingerprint(raw_claims: list, grammar: str = "mathema") -> str:
    """A stable hash of a declared claim set's portable identity. For
    each claim, its `fingerprint_text` (the canonical ascii rendering
    of the parsed claim, advisory `-->` regions stripped) beside the
    small metadata that changes how it is checked (`name`, `route`,
    `tolerance`), under a `grammar=` header.

    The portability contract is the GRAMMAR, not a field encoding: two
    conformant tools, whatever language they are written in, compute
    the same fingerprint by parsing any accepted spelling of a claim
    and emitting the one canonical ascii form. Where the quantifier
    was written (inline `for ...` text, or a split-out `domain` field),
    which glyphs spelled it, and which internal shape a bound landed in
    are all spelling, and spelling never changes identity. A statement
    in a foreign grammar (a per-claim or per-set `grammar` other than
    "mathema") cannot be parsed here and is hashed as its verbatim
    bytes instead: opaque, but stable.

    A mathema-grammar statement that does not parse cannot be
    fingerprinted: that raises, loudly, at the caller. A claim set
    whose identity cannot be computed must never be silently treated
    as unchanged (or as changed).

    `mathema verify` uses this alongside the form hash: unchanged code
    plus an unchanged claim set is what "fresh" actually means."""
    import hashlib

    def sort_key(c):
        return c.get("name") or c.get("statement") or c.get("law") or ""

    parts = [f"grammar={grammar}"]
    for c in sorted(raw_claims or [], key=sort_key):
        cgrammar = c.get("grammar", grammar)
        statement = (c.get("statement") or c.get("law") or "").strip()
        if cgrammar == "mathema":
            statement = fingerprint_text(_declared_conjecture(c, grammar))
        parts.append(f"{c.get('name', '')}|{statement}|{c.get('route', 'best')}"
                     f"|{cgrammar}|{c.get('tolerance')}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:12]


def _declared_conjecture(c: dict, default_grammar: str = "mathema"):
    """Intent:
        One declared claim dict as the Conjecture it states, the one
        construction `entry_claims()` and `claims_fingerprint()` both
        go through, so loading and identity can never parse the same
        row two different ways. The statement text wins where it and
        the side fields overlap (`setdefault` on each domain key).
    """
    from .conjecture import claim as _claim
    from .grammar import domain_bound_from_json

    meta = c.get("meta")
    authored = c.get("authored")
    if authored is not None:
        # the declared layer's statement of origin rides the claim's
        # meta into adjudication, so the verified row can carry it
        # (a bare string is the v0.1.0 spelling of `ref`)
        meta = dict(meta or {})
        meta.setdefault("mathema.authored",
                        {"ref": authored} if isinstance(authored, str)
                        else authored)
    cj = _claim(c.get("statement") or c.get("law"), name=c.get("name"),
                source=c.get("source", c.get("family", "declared")),
                route=c.get("route", "best"),
                grammar=c.get("grammar", default_grammar),
                funcs=c.get("funcs"),
                tolerance=c.get("tolerance"),
                pseudo_infinity=c.get("pseudo_infinity"),
                meta=meta)
    for param, b in (c.get("domain") or {}).items():
        cj.domain.setdefault(param, domain_bound_from_json(b))
    # a call-site claim's in-hand callables (check() carries them under
    # this in-memory-only key; a loaded YAML row never has it) beat the
    # serialized dotted refs, which are only their fallback spelling
    for name, target in (c.get("__live_funcs__") or {}).items():
        cj.funcs[name] = target
    return cj


def _git_commit(root: str) -> "str | None":
    """Intent:
        The repository's HEAD commit at record time, best-effort,
        None outside a git repo or when git is unavailable. Stamped
        into lineage so a historical claim can point at the code
        state its last valid adjudication saw.
    """
    import subprocess
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root or ".",
                             capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and len(sha) == 40 else None


def integrity_checksum(entry: dict) -> str:
    """Intent:
        The tamper-evidence checksum over a verified entry's key
        fields: sorted (claim name, verdict, acceptance) triples plus
        the form hash and any lock stamp. Acceptance is summarized as
        (as, verified_by key, staleness), so a hand-forged or
        hand-stripped sign-off trips the mismatch the same way an
        edited verdict does. Deliberately narrow otherwise;
        notes/sketches/meta are free to be reformatted. Advisory: a
        mismatch warns and points at the fix, it does not block.
    """
    import hashlib
    def _acc(c: dict) -> str:
        accepted = c.get("accepted")
        if not isinstance(accepted, dict):
            return ""
        vb = accepted.get("verified_by") or {}
        return (f"{accepted.get('as', '')}:{vb.get('key', '')}"
                f":{1 if accepted.get('stale') else 0}")

    rows = sorted((c.get("name") or "", c.get("verdict") or "", _acc(c))
                  for c in entry.get("claims") or [])
    basis = "|".join(f"{n}={v};{a}" for n, v, a in rows)
    basis += f"#form={(entry.get('identity') or {}).get('form', '')}"
    locked = entry.get("locked")
    if isinstance(locked, dict):
        basis += f"#locked={locked.get('form', '')}"
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def pin_summary(entry: dict) -> "dict | str":
    """Intent:
        A record-level statement of whether a HUMAN pin backs any of its
        acceptances, so the absence of one is stated (`"none"`) rather
        than left to be inferred from a missing field. A machine-verified
        record with no human sign-off is perfectly valid; this just makes
        that visible to a reviewer at a glance. When one or more
        acceptances carry a `verified_by`, the summary names the methods
        and key ids seen; the per-acceptance stamps remain authoritative.
    """
    methods: set = set()
    keys: set = set()

    def scan(acc):
        vb = (acc or {}).get("verified_by")
        if isinstance(vb, dict):
            if vb.get("method"):
                methods.add(vb["method"])
            if vb.get("key"):
                keys.add(vb["key"])

    for c in entry.get("claims") or []:
        scan(c.get("accepted"))
    scan((entry.get("identity") or {}).get("reconciled"))
    if not methods and not keys:
        return "none"
    return {"methods": sorted(methods), "keys": sorted(keys)}


def anchor_reachable(commit: "str | None", root: str = ".") -> "bool | None":
    """Intent:
        Whether a record's anchor commit (its `lineage.commit`, the HEAD
        it was stamped at) is still reachable from the current HEAD.
        True: it is an ancestor, the history is intact. False: it is not
        an ancestor or no longer exists at all, so the branch was rebased,
        force-updated, or the repository re-initialised since. None: it
        cannot be told (no anchor was stamped, or this is not a git repo).
    Notes:
        Git is a Merkle chain, so a rewritten or dropped commit changes
        every descendant's hash; an orphaned anchor is exactly that trace.
    """
    if not commit:
        return None
    import subprocess
    try:
        r = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=root or ".", capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if r.returncode == 0:
        return True
    # 1: exists but not an ancestor; 128: the commit is gone entirely.
    # Both mean the anchor is not in this history line.
    return False if r.returncode in (1, 128) else None


def integrity_diagnosis(key: str, entry: dict, root: str = ".") -> str:
    """Intent:
        The advisory warning line when a verified record's contents no
        longer match its stored integrity checksum. It reads the record's
        anchor to name the LIKELY cause accurately (never accusing the
        author of hand-editing) and points at the fix that actually
        re-checks: a targeted re-verify, which re-adjudicates the key
        against the live code and re-stamps it. Reconciliation vouches
        for contents without checking them, so it stays documented
        under `mathema accept` for the deliberate, already-reviewed
        case rather than offered here as a peer of re-adjudication.
    """
    commit = (entry.get("lineage") or {}).get("commit")
    if anchor_reachable(commit, root) is False:
        cause = ("its provenance anchor is not in this history (the branch "
                 "was rebased, force-updated, or the repo re-initialised)")
    else:
        cause = ("its contents changed since mathema last stamped it (a "
                 "merge, a rebase, a stash, or an edited declared claim)")
    return (f"WARN {key}: the verified record's checksum no longer matches "
            f"its contents, {cause}. Re-run `mathema verify {key}` to "
            f"re-adjudicate and re-stamp it.")


def _relative_file(path: str, root_abs: str) -> "str | None":
    """A source path as a record states it: root-relative when the file
    lives under the project root (the same spelling index.yaml uses),
    and None when it does not. A path into site-packages or the
    interpreter is machine-specific; the dotted `key` beside it is the
    portable identity, so an out-of-root location is omitted rather
    than written as a `../../..` walk that no other checkout can
    follow."""
    ap = os.path.abspath(path)
    if ap == root_abs or ap.startswith(root_abs + os.sep):
        return os.path.relpath(ap, root_abs)
    return None


def _relativize_record_paths(spec: dict, root: str) -> None:
    """Intent:
        Every filesystem path a record carries, made portable at the
        one persist boundary that knows the root: `dependencies[].file`
        and the diagnostic report's motif/hazard `file` fields. Live
        in-process callers (`function_dependencies`, `diagnostics`)
        keep returning absolute paths; only what is written moves.
    """
    root_abs = os.path.abspath(root)

    def fix(row: dict) -> None:
        if row.get("file"):
            rel = _relative_file(row["file"], root_abs)
            if rel is None:
                row.pop("file", None)
            else:
                row["file"] = rel

    for dep in spec.get("dependencies") or []:
        fix(dep)
    diag = (spec.get("meta") or {}).get("mathema.diagnostic_report") or {}
    for section in ("motifs", "domain_hazards"):
        for row in diag.get(section) or []:
            fix(row)


def record(ex, key: str | None = None, root: str = ".",
          claims: list | None = None, declared_intent: str | None = None) -> str:
    """Write this explanation into the machine layer of the project store:
    one file per function under .mathema/verified/. `claims` (the declared
    entry's raw claim dicts this record was checked against, if any) gets
    folded into `identity.claims_fingerprint` via claims_fingerprint()
    above, so a later `mathema verify` can detect a claim being added or
    edited even when the code itself hasn't changed. Pass the raw declared
    dicts (as loaded from YAML), not Conjecture objects, the fingerprint
    must stay comparable across implementations, and Conjecture is a
    Python-only parse of that same declared shape.

    `declared_intent` (an `intent:` field on the declared entry this
    record was checked against, when one exists) fills the record's
    own `intent` when the docstring provided none, and stamps
    `meta["mathema.intent_provenance"]: declared`. Every stated intent
    starts on the `declared` rung; `documented` is the human act of
    accepting it (`mathema accept --intent`)."""
    key = key or getattr(ex.facts, "name", "unknown")
    path = os.path.join(verified_dir(root), f"{key}.yaml")
    spec = to_spec(ex)
    spec["identity"]["claims_fingerprint"] = claims_fingerprint(claims or [])
    if declared_intent and not spec.get("intent"):
        # the declared layer's intent is the skeleton when the
        # docstring provides none, still the declared rung
        spec["intent"] = declared_intent
        spec.setdefault("meta", {})["mathema.intent_provenance"] = "declared"
    _relativize_record_paths(spec, root)
    _annotate_dependency_freshness(spec, root)
    _apply_verdict_history(spec, key, path)
    from .acceptance import carry_acceptance, carry_intent_acceptance
    carry_acceptance(spec, key, path)
    carry_intent_acceptance(spec, key, path)
    from .locks import load_locks
    lock_entry = load_locks(root).get(key)
    if lock_entry:
        # the record reflects the lock (and the integrity checksum
        # covers the stamp), so removing the meta entry by hand is
        # detectable; .mathema/meta/locks.yaml stays the source of
        # truth because records are rebuilt every sweep
        spec["locked"] = {k: lock_entry[k]
                          for k in ("form", "at", "by") if k in lock_entry}
    accepted_concepts = set(spec.get("concepts_accepted") or [])
    if accepted_concepts:
        # an accepted tag holds the documented rung: reflected on the
        # per-concept rows and in the provenance split
        for row in spec.get("concepts") or []:
            if isinstance(row, dict) and row.get("name") in accepted_concepts:
                row["source"] = "documented"
        sources = (spec.get("meta") or {}).get("mathema.concept_sources")
        if isinstance(sources, dict):
            documented = sorted(accepted_concepts
                                & set(sum(sources.values(), [])))
            if documented:
                sources["documented"] = documented
    # deterministic claim order, so a re-adjudication never reorders rows
    # in the diff (identity and the checksum sort independently, so this is
    # purely for a clean file)
    claims = spec.get("claims")
    if isinstance(claims, list):
        claims.sort(key=lambda c: (c.get("name") or c.get("statement") or "")
                    if isinstance(c, dict) else "")
    # churn: when this record's material content (what the integrity
    # checksum covers) is unchanged from what is already on disk, keep the
    # prior lineage date and commit, so re-adjudicating an unchanged record
    # leaves the file byte-identical and produces no git diff
    new_integrity = integrity_checksum(spec)
    prior = None
    if os.path.exists(path):
        import yaml
        try:
            prior = (yaml.safe_load(open(path)) or {}).get(key)
        except Exception:
            prior = None
    prior_lineage = (prior or {}).get("lineage") or {}
    if prior is not None and \
            ((prior.get("identity") or {}).get("integrity") == new_integrity):
        if prior_lineage.get("date"):
            spec.setdefault("lineage", {})["date"] = prior_lineage["date"]
        spec.setdefault("lineage", {})["commit"] = \
            prior_lineage.get("commit", _git_commit(root))
    else:
        spec.setdefault("lineage", {})["commit"] = _git_commit(root)
    spec["identity"]["pin"] = pin_summary(spec)
    spec["identity"]["integrity"] = new_integrity
    out = write_yaml(path, {key: spec},
                     header=f"machine record; binds to form {ex.facts.form}")
    return out


def save_verified_entry(key: str, entry: dict, root: str = ".") -> str:
    """Intent:
        Write one verified-layer entry back to its file with a fresh
        integrity checksum: the single write path for a tool that
        amends a stored record (appending adjudicated rows, annotating
        provenance) rather than re-recording from a live check.

    Notes:
        The checksum covers claim names, verdicts, acceptance and the
        form hash, so an amendment touching any of those recomputes it
        honestly; everything else in the entry is written exactly as
        given.
    """
    entry.setdefault("identity", {})["integrity"] = integrity_checksum(entry)
    form = (entry.get("identity") or {}).get("form", "")
    path = os.path.join(verified_dir(root), f"{key}.yaml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return write_yaml(path, {key: entry},
                      header=f"machine record; binds to form {form}")


_REGRESSABLE = ("falsified", "unknown", "skipped")


def _dependency_state(dep: dict, verified: dict) -> str | None:
    """One function-kind dependency's freshness against the verified
    store: `current` / `stale` / `invalidated` / `unverified`, or
    `None` for a dependency that carries no form (modules, classes,
    signature callables); those have no verification to be fresh
    against."""
    form = dep.get("form")
    key = dep.get("key")
    if not form or not key:
        return None
    stored = verified.get(key)
    if stored is None:
        return "unverified"
    entry = stored.get("entry") or {}
    if any(classify_verdict(c.get("verdict") or "") == "invalidated"
           for c in entry.get("claims") or []):
        return "invalidated"
    stored_form = (entry.get("identity") or {}).get("form")
    return "current" if stored_form == form else "stale"


def dependencies_current_probe(dependencies: list, root: str = "."):
    """Adjudicate the `dependencies_current` fact for one function: a
    machine-generated derive-route claim stating that every direct
    function dependency's form hash matches its own verified record
    (and none of those records is invalidated). This is the
    memoization rung of the freshness design, a caller trusts its
    callee's `dependencies_current` instead of walking deeper, so
    transitive freshness stays one comparison per level.

    Verdicts: `proven` when every function dependency is current
    (vacuously, when there are none); `falsified` when any is stale or
    invalidated (they are the counterexample); `unknown` when none
    regressed but at least one has no verified record yet, the fact
    can't be established either way until the callee is verified."""
    from .records import Probe

    verified = load_verified(root)
    states = [(dep, _dependency_state(dep, verified)) for dep in dependencies or []]
    checked = [(dep, st) for dep, st in states if st is not None]
    note = "generated by mathema verify; adjudicated against the verified store"
    if not checked:
        return Probe("dependencies_current", "", "proven",
                     route="derive", note=note,
                     meta={"mathema.surface": "builtin"},
                     sketch="no direct function dependencies, vacuously current")
    bad = [(dep, st) for dep, st in checked if st in ("stale", "invalidated")]
    if bad:
        cx = ", ".join(f"{dep['key']} is {st}" for dep, st in bad)
        return Probe("dependencies_current", "", "falsified",
                     route="derive", note=note,
                     meta={"mathema.surface": "builtin"}, counterexample=cx,
                     sketch="a direct dependency's verified record no longer "
                            "matches its live form")
    unverified = [dep for dep, st in checked if st == "unverified"]
    if unverified:
        names = ", ".join(dep["key"] for dep in unverified)
        return Probe("dependencies_current", "", "unknown",
                     route="derive", note=note,
                     meta={"mathema.surface": "builtin"},
                     sketch=f"no verified record yet for: {names}")
    return Probe("dependencies_current", "", "proven",
                 route="derive", note=note,
                     meta={"mathema.surface": "builtin"},
                 sketch="every direct function dependency's form matches its "
                        "verified record")


def _annotate_dependency_freshness(spec: dict, root: str) -> None:
    """Intent:
        Stamp each of the record's one-deep dependencies with its
        freshness against the store: `current` (the callee's verified
        record exists and its recorded form matches the callee's live
        form), `stale` (recorded form differs, the callee changed
        since its claims were verified, so this function's claims about
        it can't be trusted either), `invalidated` (the callee's own
        record carries an invalidated claim, the regression
        propagates one level up as a freshness state, exactly the
        composition that makes one-deep dependencies enough), or
        `unverified` (no record at all). Non-function dependencies
        (modules, classes, signature callables) carry no form and get
        no freshness verdict.
    """
    deps = spec.get("dependencies") or []
    if not any(d.get("form") for d in deps):
        return
    verified = load_verified(root)
    for dep in deps:
        state = _dependency_state(dep, verified)
        if state is not None:
            dep["freshness"] = state


def _apply_verdict_history(spec: dict, key: str, path: str) -> None:
    """Intent:
        The record layer's memory: compare each claim's fresh verdict
        against the prior record at `path` and (a) stamp
        `meta["mathema.previous_verdict"]` whenever the verdict
        changed, (b) turn a supported->unsupported transition into the
        `invalidated` error state; a claim that was `proven`/`holds`
        and can no longer be established is a regression, categorically
        different from a claim that was never supported. The raw fresh
        outcome is kept in `meta["mathema.regressed_to"]`, and an
        already-`invalidated` claim that still fails stays
        `invalidated` (the error stands until the claim is re-
        supported).

    Notes:
        Runs at write time, in `record()`, because this is the one
        place that holds both the fresh adjudication and the history.
        The reasoning chain reflects the raw adjudication (built before
        this pass); the claim's own `verdict` reflects the state.
        Degrades to a plain write when the prior record can't be read.
    """
    if not os.path.exists(path):
        return
    try:
        import yaml
        with open(path) as fh:
            prior_doc = yaml.safe_load(fh) or {}
        prior_entry = prior_doc.get(key) or {}
        prior_claims = prior_entry.get("claims") or []
        prior = {c.get("name"): c.get("verdict") for c in prior_claims
                if c.get("name") and c.get("verdict")}
        prior_commit = (prior_entry.get("lineage") or {}).get("commit")
        prior_meta = {c.get("name"): c.get("meta") or {}
                      for c in prior_claims if c.get("name")}
    except Exception:
        return
    for c in spec.get("claims") or []:
        # the last-supported pointer survives every rewrite: set when a
        # supported verdict is left behind, carried forward otherwise,
        # what a historical acceptance points at ("the commit when the
        # previous version of this truth held")
        carried = prior_meta.get(c.get("name"), {}).get(
            "mathema.last_supported_commit")
        if carried:
            meta0 = dict(c.get("meta") or {})
            meta0.setdefault("mathema.last_supported_commit", carried)
            c["meta"] = meta0
        prev = prior.get(c.get("name"))
        if prev is None or prev == c.get("verdict"):
            continue
        meta = dict(c.get("meta") or {})
        meta["mathema.previous_verdict"] = prev
        if classify_verdict(prev) in SUPPORTED_VERDICTS and prior_commit:
            meta["mathema.last_supported_commit"] = prior_commit
        base_prev = classify_verdict(prev)
        base_new = classify_verdict(c["verdict"] or "")
        if base_prev in SUPPORTED_VERDICTS and base_new in _REGRESSABLE:
            meta["mathema.regressed_to"] = c["verdict"]
            c["verdict"] = "invalidated"
        elif base_prev == "invalidated" and base_new in _REGRESSABLE:
            # the standing error persists until the claim is genuinely
            # re-supported; a still-failing re-run never launders an
            # invalidation back into an ordinary failure.
            meta["mathema.regressed_to"] = c["verdict"]
            c["verdict"] = "invalidated"
        c["meta"] = meta


_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mathema"}


def _is_claim_file(dirpath: str, name: str) -> bool:
    if name in ("claimspec.yaml", "claimspec.yml"):
        return True
    if name.endswith((".claims.yaml", ".claims.yml")):
        return True
    return (os.path.basename(dirpath) == "claims"
            and name.endswith((".yaml", ".yml")))


def merge_entries(base: dict, over: dict, *,
                  on_conflict: str = "warn") -> dict:
    """Merge two entries for the same key: claims merge by claim name (the
    overlay wins per claim, new names append); every other field the
    overlay actually states wins, and a field the overlay never mentions
    (identity, in particular, when the overlay is a declared entry that
    never carries one) falls back to the base.

    One named claim cannot honestly mean two things at once, so an
    overlay replacing a same-name claim with a DIFFERENT statement is a
    real conflict the record schema says must surface, never resolve
    quietly. `on_conflict="warn"` (the default) names it; a caller whose
    precedence between the two surfaces is itself the documented
    behavior (a call-site claim overriding a suggestion, say) passes
    `on_conflict="silent"`."""
    out = dict(base)
    for k, v in over.items():
        if k == "claims" and isinstance(v, list) and isinstance(out.get(k), list):
            def cname(c):
                return c.get("name") or c.get("law") or c.get("statement")

            def cstmt(c):
                return c.get("statement") or c.get("law")
            by_name = {cname(c): c for c in out[k]}
            for c in v:
                prior = by_name.get(cname(c))
                if (on_conflict == "warn" and prior is not None
                        and cstmt(prior) and cstmt(c)
                        and cstmt(prior) != cstmt(c)):
                    import warnings
                    warnings.warn(
                        f"mathema: claim {cname(c)!r} is stated two ways "
                        f"across authoring surfaces ({cstmt(prior)!r} vs "
                        f"{cstmt(c)!r}); the overlay's version is used, "
                        f"but one named claim cannot mean two things: "
                        f"resolve it (mathema docsync, or rename one)",
                        stacklevel=2)
                by_name[cname(c)] = c
            out[k] = list(by_name.values())
        else:
            out[k] = v
    return out


# transitional alias: merge_entries was _merge_entries until the 2026-08
# refactor; slated for removal once nothing references the old name.
_merge_entries = merge_entries


def verified_dir(root: str = ".") -> str:
    """The verified layer's directory: `.mathema/verified/`, the layer
    is called what it is."""
    return os.path.join(root, ".mathema", "verified")


def load_verified(root: str = ".") -> dict:
    """The verified layer only: machine-written records
    (verified-schema.md) under .mathema/verified/, one file per
    function. This
    is the sole source of the `identity.form` hash `mathema verify` diffs
    the live code against; a declared entry never has one, so it must
    never be consulted here."""
    import yaml
    merged: dict = {}
    for machine_dir in (verified_dir(root),):
        if not os.path.isdir(machine_dir):
            continue
        for name in sorted(os.listdir(machine_dir)):
            if not name.endswith(".yaml"):
                continue
            path = os.path.join(machine_dir, name)
            data = yaml.safe_load(open(path)) or {}
            for key, entry in data.items():
                merged[key] = {"entry": entry, "source": os.path.relpath(path, root)}
    return merged


def load_declared(root: str = ".") -> dict:
    """The declared layer only: human-authored claim intent
    (declared-schema.md), *.claims.yaml, claims/*.yaml, claimspec.yaml,
    anywhere in the tree, shallow to deep, merged by claim name across
    files sharing a key (deeper file wins per claim; a file-level
    `grammar` key sets that file's default dialect). Never carries
    `identity`: a hash is a fact about checked code, not something anyone
    declares ahead of running it.

    `.mathema/` is skipped deliberately: `.mathema/declared/` is the
    materialized VIEW of the merged surfaces (docsync's output for
    people and agents), and reading it back in would make every claim
    exist in two authoritative places at once. The authoring surfaces
    are the only input."""
    import yaml
    files: list[tuple[int, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in sorted(filenames):
            if _is_claim_file(dirpath, name):
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(dirpath, root)
                depth = 0 if rel == "." else len(rel.split(os.sep))
                files.append((depth, path))

    merged: dict = {}
    for _, path in sorted(files):          # shallow first, deep last → deep wins
        data = yaml.safe_load(open(path)) or {}
        if not isinstance(data, dict):
            continue
        file_grammar = data.pop("grammar", None)
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            entry.pop("identity", None)    # a declared file never states one
            if file_grammar:
                entry.setdefault("grammar", file_grammar)
            prev = merged.get(key)
            if prev is not None:
                entry = merge_entries(prev["entry"], entry)
            merged[key] = {"entry": entry, "source": os.path.relpath(path, root)}
    return merged


def load_specs(root: str = ".") -> dict:
    """A combined, display-only view of the whole store, for `mathema
    status` and human introspection: {key: {"entry", "source", "layer"}},
    with `layer` naming whichever side last touched that key's display
    fields. Do not use this to decide what to adjudicate or whether code
    changed; those must read load_declared()'s claims and
    load_verified()'s identity.form directly, so a declared entry can
    never stand in for a verified one."""
    verified = load_verified(root)
    declared = load_declared(root)
    merged: dict = {}
    for key, info in verified.items():
        merged[key] = {"entry": info["entry"], "source": info["source"],
                       "layer": "machine"}
    for key, info in declared.items():
        entry = info["entry"]
        prev = merged.get(key)
        if prev is not None:
            entry = merge_entries(prev["entry"], entry)
        merged[key] = {"entry": entry, "source": info["source"], "layer": "human"}
    return merged


def load_claims(path: str) -> dict:
    """Parse a claims file (the authoring shape: declared-schema.md) into
    {key: [Conjecture, ...]}, ready for
    check_conjectures()/mathema.check(fn, claims=...).

    Each claim entry gives its law under `statement` (the spec's field
    name; `law` accepted as a synonym), and may set `name`, `route`
    (default "probe"; "derive" asks for a symbolic proof), `grammar`
    (defaulting to the entry's or file's grammar), and `domain`
    ({param: [lo, hi]} bounds the claim is asserted over).
    """
    import yaml


    data = yaml.safe_load(open(path)) or {}
    if not isinstance(data, dict):
        return {}
    file_grammar = data.pop("grammar", "mathema")
    out: dict = {}
    for key, entry in data.items():
        out[key] = entry_claims(entry, default_grammar=file_grammar)
    return out


def entry_claims(entry: dict, default_grammar: str = "mathema") -> list:
    """Turn one spec entry's declared claims into Conjectures. Rows with a
    `verdict` are records of past adjudication, not declarations, and are
    skipped."""
    claims = []
    for c in entry.get("claims") or []:
        law = c.get("statement") or c.get("law")
        if not law or "verdict" in c:
            continue
        claims.append(_declared_conjecture(
            c, entry.get("grammar", default_grammar)))
    return claims


def attach_recorded_pins(conjectures: list, verified_entry: dict | None) -> None:
    """Intent:
        Wire each declared claim's recorded counterexample (the
        structured `mathema.counterexample_args` a past falsification
        stored) into `Conjecture.pins`, so re-adjudication replays the
        exact point that broke it before any fresh sampling, the bug
        path's contract: the old counterexample becomes a claim that
        must now pass.
    """
    if not verified_entry:
        return
    stored = {}
    for c in verified_entry.get("claims") or []:
        args = (c.get("meta") or {}).get("mathema.counterexample_args")
        if c.get("name") and args:
            stored[c["name"]] = args
    for cj in conjectures:
        args = stored.get(cj.name)
        if args:
            cj.pins = list(cj.pins or []) + [{"args": args}]


def _chain_text(cj) -> str:
    """A chained comparison as one statement (`0 <= f(x) < 1`).
    `statement_text` renders a single relation, so a chain stored
    through it keeps only its first link and the record states a
    strictly weaker claim than the author wrote."""
    text = str(cj.links[0][0])
    for _lhs, relation, rhs in cj.links:
        text += f" {relation} {rhs}"
    return text


def _let_sections(cj) -> list:
    """The `let` bindings a statement has to carry to survive reparsing:
    a function bound to a dotted path, and a free variable's own bound.
    A free variable is not a parameter, and nothing else in the declared
    shape records that it is one; its domain entry alone reads as a
    parameter's and is then rejected as not matching the signature."""
    sections = []
    for name, ref in (cj.funcs or {}).items():
        # a live callable has no text spelling; declare()'s own `funcs`
        # field recovers its dotted path, and a self-placeholder
        # (`{"g": "g"}`) is an unresolved reference, not a binding
        if isinstance(ref, str) and ref != name:
            sections.append(f"let {name} = {ref}")
    for name in sorted(cj.free_vars or ()):
        bound = (cj.domain or {}).get(name)
        if bound is not None:
            from .domain import render_domain_bound
            sections.append(f"let {name} be {render_domain_bound(bound)}")
    return sections

def callable_ref(fn) -> "str | None":
    """Intent:
        The dotted `module.qualname` path naming a live callable, when
        that path resolves, among the modules already loaded, back to
        this very object. None for a callable no path names: a lambda, a
        nested function, or a wrapper whose copied name resolves to
        the function it wraps rather than to itself.

    Notes:
        Resolution reads `sys.modules` only and never imports, so asking
        has no side effects. A function defined in `__main__` gets no
        path: `__main__` is a different module in every later process,
        so the path would not name the same function there.
    """
    import sys

    mod = getattr(fn, "__module__", None)
    qual = getattr(fn, "__qualname__", "")
    if not mod or not qual or "<" in qual or mod == "__main__":
        return None
    obj = sys.modules.get(mod)
    for part in qual.split("."):
        obj = getattr(obj, part, None) if obj is not None else None
    return f"{mod}.{qual}" if obj is fn else None


def declare(cj) -> dict:
    """The inverse of entry_claims()'s per-claim parsing: one Conjecture
    back to declared-schema.md's claim-dict shape. This is the seam every
    claim-authoring surface funnels through before merging or
    verification, a YAML file already produces this shape directly, but a
    decorator or a docstring block, once either exists, must land here
    too, so `load_declared()`'s merge-by-name and claims_fingerprint()'s
    comparison never need to know which surface a claim came from. Also
    used for claims passed in-process (mathema.write_spec(fn, claims=[...])),
    so their fingerprint matches what an equivalent claims.yaml would
    produce."""
    from .grammar import domain_bound_to_json

    # Every section the statement does not carry is a section the round
    # trip loses, because `entry_claims` rebuilds the claim by reparsing
    # this text. `statement_text` renders only `lhs <rel> rhs`, and four
    # real losses came from that: an `assuming` premise (a conditional
    # claim came back unconditional and was refuted from a point it
    # never covered), a `let g = <path>` binding (a statement referring
    # to a `g` it never introduces), a `let c be [...]` free variable
    # (its bound lost, so probing sampled +-1e6 and falsified out of
    # domain), and the second half of a chained comparison
    # (`0 <= f(x) < 1` stored as `0 <= f(x)`, so the record proved a
    # weaker claim than the one written).
    #
    # The quantifier deliberately stays out: `domain` already carries it
    # losslessly and in its own shape, and rendering it here would both
    # duplicate it and re-type it on reparse.
    statement = _chain_text(cj) if cj.links else statement_text(
        cj.relation, cj.lhs, cj.rhs)
    if getattr(cj, "negated", False) and not statement.startswith("not "):
        statement = f"not {statement}"
    if getattr(cj, "outcome", ""):
        statement = f"{statement} => {cj.outcome}"
    sections = ([cj.assuming] if cj.assuming else []) + _let_sections(cj)
    if sections:
        statement = ", ".join(sections + [statement])
    out = {"name": cj.name, "statement": statement, "route": cj.route,
          "grammar": cj.grammar}
    if cj.source and cj.source not in ("user", "declared", "the author"):
        # provenance survives the round trip: a suggestion stays a
        # suggestion through every merge, never silently promoted to
        # an authored claim
        out["source"] = cj.source
    if cj.domain:
        out["domain"] = {p: domain_bound_to_json(b) for p, b in cj.domain.items()}
    if cj.tolerance is not None:
        out["tolerance"] = cj.tolerance
    if getattr(cj, "meta", None):
        out["meta"] = dict(cj.meta)
    if getattr(cj, "pseudo_infinity", None) is not None:
        # the operational infinity magnitude for the extreme-value
        # checks, emitted only when the author set it (an ordinary
        # bounded-domain claim never states it); applied symmetrically
        _, hi = pseudo_infinity_range(cj.pseudo_infinity)
        out["pseudo_infinity"] = hi
    if cj.funcs:
        # only a dotted "module.qualname" reference survives this round
        # trip. A live callable serializes as its own dotted reference
        # when it has an importable one (a module-level function); a
        # callable with no such path (a nested def, a lambda) makes the
        # whole map unserializable, and it is dropped, never a partial
        # map that would silently rebind a subset of the claim's names.
        refs: dict = {}
        for name, v in cj.funcs.items():
            ref = v if isinstance(v, str) else callable_ref(v)
            if ref is None:
                refs = {}
                break
            refs[name] = ref
        if refs:
            out["funcs"] = refs
    return out


# A bare identifier, scanned directly out of cj.lhs/cj.rhs's raw source
# text rather than a parsed sympy expression; render_claim_text needs
# the candidate name set before it decides whether to call
# render_law_expr at all, so a lightweight regex pass is simpler than
# parsing twice.
_IDENTIFIER = re.compile(r"[A-Za-z_]\w*")


def _ordered_real_param_names(cj, excluded: set) -> list:
    """Every real parameter name `cj` mentions, in first-occurrence
    order (`cj.lhs` then `cj.rhs`, via `re.findall` which already
    preserves match order, never coerced through a `set`), with
    `cj.domain`'s own remaining keys (already-deterministic dict order,
    for a declared-but-unused-in-text domain) appended after any not
    already found in the text. Both auto-let mechanisms below (a Greek-
    word exact match, the long-name pool) depend on this order being
    identical every time the same claim is rendered, in any process."""
    seen: list = []
    for text in (cj.lhs, cj.rhs):
        if isinstance(text, str):
            for name in _IDENTIFIER.findall(text):
                if name not in excluded and name not in seen:
                    seen.append(name)
    for name in cj.domain:
        if name not in cj.free_vars and name not in excluded and name not in seen:
            seen.append(name)
    return seen


def _is_safe_rename_symbol(symbol: str) -> bool:
    """Intent: is `symbol` safe to substitute directly into law text
    *before* `render_law_expr`'s own `ast.parse`, rather than needing
    the post-render backtick-wrap path?

    `.isidentifier()` alone isn't the real safety condition, CPython
    normalizes every identifier to NFKC at parse time (PEP 3131), so a
    string can satisfy `.isidentifier()` today and still come back a
    *different* string once `ast.parse` has touched it (`"Mₛ"`, a
    letter-category subscript, parses to a `Name` node whose id is
    `"Ms"`). A symbol that isn't NFKC-stable would render one spelling
    in the law text (already flattened by the `ast.parse`/re-emit round
    trip) and a different spelling in the `let`/domain clause (built as
    plain f-string text, never touching `ast.parse`), the same
    symbol, two spellings in one rendered line, reparsing into a
    genuinely different claim with no error raised anywhere. Requiring
    NFKC-stability in addition to `.isidentifier()` catches this before
    it happens, at the one place both the param and function paths
    already gate on `.isidentifier()`."""
    return symbol.isidentifier() and unicodedata.normalize("NFKC", symbol) == symbol


def _symbology_answers(provider, params, funcs) -> tuple[dict, dict]:
    """Intent:
        What a `symbology` provider proposes for each real parameter
        and each bound function name: `({param: symbol}, {func:
        symbol})`, with a declined name (`None`, or a hook the provider
        does not define) left out.

    Notes:
        Anything the provider raises propagates, so the caller can skip
        the provider as a whole.
    """
    symbol_for_param = getattr(provider, "symbol_for_param", None)
    symbol_for_func = getattr(provider, "symbol_for_func", None)
    param_symbols = {} if symbol_for_param is None else {
        name: symbol_for_param(name) for name in params}
    func_symbols = {} if symbol_for_func is None else {
        name: symbol_for_func(name) for name in funcs}
    return ({n: s for n, s in param_symbols.items() if s is not None},
            {n: s for n, s in func_symbols.items() if s is not None})



def _auto_renames(cj, funcs: frozenset, unicode: bool,
                  long_param_threshold: int, long_func_threshold: int,
                  canonical: bool = False):
    """`(param_renames, func_renames, suppress_glyphs)`, the first two
    are kept separate because a real parameter's original name is worth
    preserving via an explicit `let <symbol> = <name>` clause (it's the
    function's actual argument name, needed to reparse back to the same
    domain key), while a function alias's own chosen text in the claim
    isn't (it was never anything but a display choice made for this one
    claim's own `let <alias> = <target>` binding), so a long alias is
    simply replaced at that same binding site instead, with no extra
    clause.

    Both sources feeding `param_renames`, a real parameter whose name
    spells a Greek letter's English word (`greek_symbol_for_name`,
    exact match), and one longer than `long_param_threshold` handed to
    the positional pool, are unicode output only: ASCII has no
    single-letter convention for an ordinary *variable* the way `f`/
    `g`/`h` (+, in unicode, `φ`/`ψ`/`χ`) already is for a *function*, so
    an arbitrary positional letter would read as noise, not a
    convention, in ASCII text, and even in unicode, a routine English
    word is common enough below ~8 characters that a lower bar would
    catch ordinary, well-chosen names too often to be welcome. A long
    function alias, in contrast, auto-lets in *both* modes at its own
    (lower) `long_func_threshold`, since shortening it to a familiar
    function letter is the well-established convention either way.

    Both draw from one shared `taken` set seeded with every name
    already this short in the claim (an existing single-letter real
    parameter or func alias, `f` itself), so neither mechanism ever
    reassigns a symbol something else in the same claim already uses.

    `suppress_glyphs` handles a real parameter named exactly `pi`/`oo`
    (`_math_vocab._MATH_ATTRS`' keys, minus `e`, which has no distinct
    unicode glyph at all, `_print_Exp1` always prints `"e"`, so
    there's nothing to suppress). Renaming was tried here first and
    rejected: `grammar._node_to_sympy` has no concept of any one
    function's real parameter names, so it always resolves a bare
    `pi`/`oo` to the math constant regardless, by the time a claim
    reaches this printer, a genuine `pi`-named parameter and the
    constant are already the identical sympy object, indistinguishable
    at render time, so renaming can only rename *every* occurrence
    (parameter and constant alike) or none; there's no way to build a
    fresh, safe replacement *symbol* either (the obvious pick, capital
    Π, silently corrupts on reparse, normalize()'s own Σ/Π -> Sum/Prod
    substitution rewrites it before any `let`-alias parsing ever runs).
    Simplest correct fix: when `pi`/`oo` is also a real parameter, just
    suppress the glyph for that render entirely and print the plain
    word instead, exactly like ASCII already does, no `let`, no
    rename, nothing to reparse differently. The real proof machinery
    was never affected either way, symbolic/_prove.py's own
    law-to-sympy walker checks a function's real `param_names` before
    falling back to `_MATH_ATTRS`, so a genuine `pi`-named parameter is
    already proven/disproven correctly regardless of how this renders."""
    from .grammar import auto_short_names, greek_symbol_for_name, reserved_names
    from ._providers import get_provider, report_provider_failure

    # `eps`/`epsilon`/`ε` are the claim's tolerance, not parameters to
    # rename
    excluded = (funcs | {"f", "eps", "epsilon", "ε"} | set(cj.free_vars)
                | reserved_names())
    real_params = _ordered_real_param_names(cj, excluded)

    param_renames: dict = {}
    taken = set(excluded) | {n for n in real_params if len(n) == 1}
    long_params: list = []
    # domain-declared names only, not the general real_params text scan,
    # "pi" appearing bare in a formula (an integral bound, a
    # comparison target) is just the constant, not a parameter; nobody
    # writes "for pi in [0, 100]" meaning the fixed constant, so an
    # explicit domain declaration is the actual, reliable signal that
    # "pi" was meant as a genuine varying quantity here.
    declared = {n for n in cj.domain if n not in cj.free_vars}
    suppress_glyphs = frozenset({"pi", "oo"} & declared) if unicode else frozenset()

    # A "symbology" capability, if one is registered, gets first pick of a symbol
    # for every real parameter and function name, ahead of the Greek-
    # word match and the positional pool below, in both output modes
    # (the provider, not mathema, decides which of its symbols are
    # ASCII-safe). A candidate is only accepted if it isn't already
    # `taken`, so a provider can never make two names in the same claim
    # collide with each other or with an existing single-letter name.
    #
    # Every answer is collected before any is used. A provider that
    # raises from either hook is skipped for the whole render (none of
    # its answers are used, one warning names it), so the claim renders
    # exactly as it would with no provider installed.
    provider_params: dict = {}
    provider_funcs: dict = {}
    provider = None if canonical else get_provider("symbology")
    if provider is not None:
        try:
            provider_params, provider_funcs = _symbology_answers(
                provider, real_params, cj.funcs)
        except Exception as exc:
            report_provider_failure("symbology", exc)
            provider_params, provider_funcs = {}, {}
    for name in real_params:
        symbol = provider_params.get(name)
        if symbol is not None and symbol not in taken:
            param_renames[name] = symbol
            taken.add(symbol)

    if unicode:
        for name in real_params:
            if name in param_renames:
                continue
            symbol = greek_symbol_for_name(name)
            if symbol is not None:
                param_renames[name] = symbol
                taken.add(symbol)
        long_params = [n for n in real_params if n not in param_renames
                      and len(n) > long_param_threshold]

    func_renames: dict = {}
    for name in cj.funcs:
        symbol = provider_funcs.get(name)
        # a function symbol is never backtick-wrapped (it sits in a
        # call's own name position, where backticks aren't valid syntax
        # even post-render), so an unsafe candidate, including one
        # that's `.isidentifier()`-safe but not NFKC-stable, see
        # `_is_safe_rename_symbol`, is dropped rather than accepted, the
        # same guarantee auto_short_names' own pools already provide.
        if symbol is not None and _is_safe_rename_symbol(symbol) and symbol not in taken:
            func_renames[name] = symbol
            taken.add(symbol)

    # A function rename is a DISPLAY choice, and it only survives a round
    # trip where the claim has a `let <alias> = <target>` binding site for
    # the shortened name to be written back at. A bare call resolved out of
    # the target's own module scope has no such site, so renaming it in the
    # stored spelling would emit an orphan `g` that reparses to nothing and
    # rebinds to nothing. Canonical text therefore keeps real function
    # names, which is what its own contract already promises.
    long_funcs = [] if canonical else [
        n for n in cj.funcs if len(n) > long_func_threshold
        and n not in func_renames]
    pool_renames = auto_short_names(long_params, long_funcs, unicode=unicode, taken=taken)
    param_renames.update({n: pool_renames[n] for n in long_params})
    func_renames.update({n: pool_renames[n] for n in long_funcs})
    return param_renames, func_renames, suppress_glyphs


def canonical_claim_text(cj) -> str:
    """The one stored spelling of a claim: the ascii rendering with no
    display renaming (real parameter and function names, no symbology
    provider consulted), so the same claim produces the same bytes on
    every machine, whoever writes it and whatever display preferences
    or extensions they run. Any accepted grammar spelling (ascii,
    unicode, symbology-renamed) parses to the same Conjecture; this is
    the spelling mathema's own artifacts write back, and the basis
    `claims_fingerprint` hashes. Unicode output stays a display
    rendering, recomputed from the parse at read time, never stored."""
    return render_claim_text(cj, unicode=False, canonical=True)


def _strip_pinned_regions(assuming: str) -> str:
    """Intent:
        The assuming clause with every `--> <region>` pin removed, per
        conjunct: `assuming f is defined --> b != 0 and lemma --> x > 0`
        becomes `assuming f is defined and lemma`. A conjunct with no
        arrow (a plain relation premise) passes through whole.

    Notes:
        The pinned region is resolved evidence, recomputed at
        verification, not part of what the author asserted, so it must
        not participate in claim identity: a record whose pin moved
        because the code moved is stale, not re-authored.
    """
    import re as _re

    from .conjecture import _split_top_and
    text = _re.sub(r"^assuming\s+", "", assuming.strip())
    kept = [_re.sub(r"\s*(?:-->|=>|⟹).*$", "", part, flags=_re.DOTALL).strip()
            for part in _split_top_and(text)]
    return "assuming " + " and ".join(k for k in kept if k)


def fingerprint_text(cj) -> str:
    """Intent:
        The identity spelling of a claim: `canonical_claim_text` with
        every advisory `-->` region stripped from the assuming clause.
        Two claims are the same claim exactly when this string is
        equal; a claim is re-authored exactly when it changes.
    """
    from dataclasses import replace
    if cj.assuming and ("-->" in cj.assuming or "=>" in cj.assuming
                        or "⟹" in cj.assuming):
        cj = replace(cj, assuming=_strip_pinned_regions(cj.assuming))
    return canonical_claim_text(cj)


def render_claim_text(cj, *, unicode: bool | None = None,
                      long_param_threshold: int = 8,
                      long_func_threshold: int = 6,
                      canonical: bool = False) -> str:
    """The alternative to declare()'s structured-dict shape: one
    parseable string a person can copy straight back into `claim(...)`
    and get an equivalent Conjecture, domain/funcs/free_vars
    reassembled as leading `let`/`for` clauses rather than left in
    separate fields, which is what declare()'s own `statement`/`domain`/
    `funcs` split can never do alone (that split is why a claim never
    round-tripped through a verified record as one string before this
    function existed).

    `unicode` picks between two output spellings of the *same* claim
    (`≤`/`∈`/`⊂` vs `<=`/`in`/`subset`, see grammar.render_law_expr),
    neither is a fallback, both must parse back to an equivalent claim.
    Left unstated (`None`, the default), it follows the global
    `grammar.get_unicode_output()` preference; pass it explicitly to pin
    one spelling regardless of that global setting.

    Known, accepted lossiness: an *aliased* `let name = other_param`
    binding (forcing two real parameters equal) leaves no trace in
    `cj.lhs` once parsed; `m` is already fully substituted into
    `f((m1),x1,(m1),x2)` by the time a Conjecture exists. Re-rendering
    reproduces the resolved *effect* (`m1` written twice, no `let`
    needed at all), never the original alias spelling, a different
    string, the same claim. A `funcs` entry whose value is a live
    callable is spelled `let g = <module.qualname>` when `callable_ref`
    finds an importable path resolving back to it, the same reference
    declare() stores; a callable with no such path (a lambda, a nested
    function) has no text spelling and is left out, not an error, since
    the resulting claim is still valid text, just missing that one
    bound-function definition, exactly as incomplete as declare()'s own
    dict would be for the same claim.

    Auto-lets two kinds of name to a short spelling, each with its own
    synthesized `let` clause stating the substitution explicitly rather
    than leaving a reader to guess why a name changed spelling:

    - Unicode output only: a real parameter whose name spells a Greek
      letter's English name (`theta`, `alpha`, ...) auto-lets to the
      actual symbol (`θ`, `α`, ...), the same bridge a claim's own
      text already builds by hand (`let \\alpha = alpha`, see
      grammar.py's Greek-letter tests), done automatically wherever the
      name alone already says which symbol was meant. A real parameter
      longer than `long_param_threshold` characters (default 8) not
      already covered by that exact match also auto-lets, to a short,
      literature-style spelling (`grammar.auto_short_names`), `x`
      first, then a fixed pool mixing Latin and a curated set of Greek
      letters, purely positional. Both are unicode-only: ASCII has no
      single-letter convention for an ordinary *variable* the way
      `f`/`g`/`h` already is for a *function* (below), so a positional
      letter would read as noise there, not a convention, ASCII
      output always keeps a real parameter's plain, authored word.
    - Both output modes: a function-alias name longer than
      `long_func_threshold` characters (default 6) auto-lets to a short
      spelling the same way (`f`/`g`/`h`, then in unicode `φ`/`ψ`/`χ`)
     ; simply substituted at its own existing `let <alias> = <target>`
      binding site, no extra clause, since the alias text was never
      anything but a display choice made for this one claim (unlike a
      real parameter's name, which is the function's actual argument
      name and worth keeping visible via its own `let` clause).

    Separately (no `let`, no rename): a real parameter named exactly
    `pi` or `oo` suppresses that constant's usual unicode glyph
    (`π`/`∞`) for this render, printing the plain word instead; see
    `_auto_renames`'s own docstring for why suppressing beats renaming
    here."""
    from .grammar import get_unicode_output, render_domain, render_law_expr
    from ._providers import get_provider

    if unicode is None:
        unicode = get_unicode_output()
    funcs = frozenset(cj.funcs)
    param_renames, func_renames, suppress_glyphs = _auto_renames(
        cj, funcs, unicode, long_param_threshold, long_func_threshold,
        canonical=canonical)

    # Same symbology capability as _auto_renames; here it may also
    # restate the segment separator and whether an unbounded domain's
    # missing side prints explicitly (default True, matching
    # render_domain's own default). `None` from show_missing means "no
    # opinion", so it defers to the True default rather than being
    # treated as a False override.
    #
    # A separator is accepted only when it still *is* a comma once
    # surrounding whitespace is removed, so `", "` and `",\n"` are both
    # allowed and anything else falls back to the default. The claim
    # grammar splits sections on the comma (`_split_commas`): a
    # separator that is any other character renders a claim that cannot
    # be read back, which is the same round-trip hazard
    # `_is_safe_rename_symbol` guards the symbol path against.
    provider = None if canonical else get_provider("symbology")
    sep = ", "
    domain_show_missing = True
    if provider is not None:
        separator = getattr(provider, "separator", None)
        if separator is not None:
            candidate = separator()
            if isinstance(candidate, str) and candidate.strip() == ",":
                sep = candidate
        show_missing = getattr(provider, "show_missing", None)
        if show_missing is not None:
            result = show_missing(cj)
            if result is not None:
                domain_show_missing = result
    # render_law_expr's own `funcs` set gates which call-shaped names it
    # accepts as a bound function rather than rejecting them as
    # unrenderable syntax; it has to see the *renamed* spelling too,
    # since apply_renames has already rewritten any call site in the
    # text by the time this reaches it.
    renamed_funcs = frozenset(func_renames.get(name, name) for name in funcs)

    # A future symbology capability can supply an arbitrary symbol string for a real
    # parameter, not every string is safe to substitute in as-is (a
    # true Unicode digit-subscript like "σ₁" fails .isidentifier()
    # outright; "σ1"/"σₓ" pass it, since letter-category subscripts are
    # identifier-safe while digit/symbol-category ones aren't, but
    # .isidentifier() alone isn't the full safety condition either, see
    # `_is_safe_rename_symbol`). An unsafe symbol can never be
    # substituted into text *before* render_law_expr; that function's
    # own round trip is `ast.parse` then re-emit, and either backticks
    # aren't valid Python syntax at all (a non-identifier symbol fails
    # to parse immediately), or, more subtly, an identifier-safe-but-
    # NFKC-unstable symbol parses fine but silently comes back a
    # *different* string once ast.parse's own PEP 3131 normalization
    # has touched it. Either way, the substitution has to happen
    # *after* render_law_expr has already produced valid, canonical
    # text, as a plain string replace on its output, the real
    # parameter name is left untouched going *into* render_law_expr (a
    # normal, safe identifier, so parsing succeeds normally and nothing
    # about it can be flattened) and only swapped for the backtick-
    # wrapped symbol once safely out the other side. Wrapping it in
    # backticks at all round-trips correctly through grammar.py's own
    # backtick-alias mechanism, which resolves it away unchanged before
    # `for`/body parsing ever runs on a *reparse*, so this never needs
    # parse_binding or ast.parse to understand backtick syntax directly,
    # only extract_let_bindings's existing one does. A function symbol
    # is never wrapped this way; it sits in a call's own name position
    # (`g(x)`), where backticks aren't valid syntax at all even post-
    # render, so auto_short_names' own pools must always, and already
    # do, produce a function symbol that's safe by this same test.
    safe_param_renames = {n: s for n, s in param_renames.items() if _is_safe_rename_symbol(s)}
    unsafe_param_renames = {n: s for n, s in param_renames.items() if not _is_safe_rename_symbol(s)}

    def apply_safe_renames(text: str) -> str:
        for name, symbol in func_renames.items():
            text = re.sub(rf"\b{re.escape(name)}\b", symbol, text)
        for name, symbol in safe_param_renames.items():
            text = re.sub(rf"\b{re.escape(name)}\b", symbol, text)
        return text

    def apply_unsafe_backticks(text: str) -> str:
        for name, symbol in unsafe_param_renames.items():
            text = re.sub(rf"\b{re.escape(name)}\b", f"`{symbol}`", text)
        return text

    _REL_GLYPH = {"==": "=", "<=": "≤" if unicode else "<=",
                  ">=": "≥" if unicode else ">=", "!=": "≠" if unicode else "!=",
                  "~=": "≈" if unicode else "~=", "<": "<", ">": ">",
                  "=:=": "≡" if unicode else "=:="}
    lhs_text, rhs_text = apply_safe_renames(cj.lhs), apply_safe_renames(cj.rhs)
    if cj.links:
        # a chained comparison: render the full chain (first link's lhs,
        # then each link's relation and rhs), which reparses compactly
        # through split_relation_chain, the whole claim, not just the
        # first link cj.lhs/cj.rhs happen to hold
        def _term(t):
            return apply_unsafe_backticks(render_law_expr(
                apply_safe_renames(t), renamed_funcs, unicode, suppress_glyphs))
        pieces = [_term(cj.links[0][0])]
        for link_lhs, link_rel, link_rhs in cj.links:
            pieces.append(_REL_GLYPH[link_rel])
            pieces.append(_term(link_rhs))
        statement = " ".join(pieces)
    elif cj.relation == "raises":
        # no ast.parse round trip on cj.rhs (the exception name) at
        # all, and lhs here is render_law_expr's own safe output,
        # backtick substitution applies post-render either way.
        lhs = apply_unsafe_backticks(render_law_expr(lhs_text, renamed_funcs, unicode, suppress_glyphs))
        statement = f"raises({lhs}, {cj.rhs})" if cj.rhs else f"raises({lhs})"
    elif cj.relation in examine_predicates():
        # never reaches render_law_expr/ast.parse at all, a plain
        # f-string, so the backtick substitution can apply directly.
        # Unicode mode prefers the postfix reading (`x is pole safe`,
        # spaces for underscores); ascii keeps the call form.
        # normalize() folds either spelling back on reparse.
        lhs_display = apply_unsafe_backticks(lhs_text)
        # the postfix reading (`A is symmetric`) only reparses for a
        # bare-identifier subject; an expression argument (`f(A)`,
        # `A @ B`, a matrix predicate's own reach) keeps the call form
        # in both modes so it round-trips
        if unicode and lhs_display.isidentifier():
            statement = f"{lhs_display} {cj.relation.replace('_', ' ')}"
        else:
            statement = f"{cj.relation}({lhs_display})"
    else:
        lhs = apply_unsafe_backticks(render_law_expr(lhs_text, renamed_funcs, unicode, suppress_glyphs))
        rhs = apply_unsafe_backticks(render_law_expr(rhs_text, renamed_funcs, unicode, suppress_glyphs))
        statement = f"{lhs} {_REL_GLYPH[cj.relation]} {rhs}"
    if getattr(cj, "negated", False):
        # the negation is part of the claim, whatever shape the
        # statement took above
        statement = f"not {statement}"

    # let/for's own displayed symbol never reaches ast.parse individually
    # (both are plain f-string text, joined into the final claim string
    # directly), so an unsafe symbol can be backtick-wrapped right here,
    # unlike the body text above, no post-render step is needed. Must
    # use the same `_is_safe_rename_symbol` test the body text above
    # does, not bare `.isidentifier()`, otherwise an NFKC-unstable
    # symbol would render bare here (`let Mₛ = money_supply`) but
    # backtick-wrapped in the law (`` `Mₛ` ``, since the law's own
    # unsafe-symbol set already includes it), the same one-symbol-two-
    # spellings-in-one-line bug this whole fix exists to prevent, just
    # moved to a different pair of lines.
    def _display_symbol(symbol: str) -> str:
        return symbol if _is_safe_rename_symbol(symbol) else f"`{symbol}`"

    # a live callable is spelled by the importable path that resolves
    # back to it, the same reference declare() stores; one with no such
    # path has no text spelling and is left out
    scope_bound: frozenset = getattr(cj, "scope_bound", frozenset())
    func_refs = {name: (ref if isinstance(ref, str)
                        else None if name in scope_bound
                        else callable_ref(ref))
                 for name, ref in cj.funcs.items()}
    let_segments = [f"let {func_renames.get(name, name)} = {ref}"
                    for name, ref in func_refs.items()
                    if ref is not None
                    # a parse-time placeholder (a bare call name awaiting
                    # scope resolution, value == its own name) only earns
                    # a `let` when the auto-rename gave it a short alias;
                    # `let mystery = mystery` says nothing
                    and func_renames.get(name, name) != ref]
    let_segments += [f"let {_display_symbol(symbol)} = {name}"
                     for name, symbol in sorted(param_renames.items())]
    let_segments += [
        f"let {name} be "
        f"{render_domain(cj.domain[name], ascii_mode=not unicode, show_missing=domain_show_missing)}"
        for name in sorted(cj.free_vars) if name in cj.domain]
    if getattr(cj, "pseudo_infinity", None) is not None:
        # the operational infinity magnitude, in the one claim-text
        # spelling (the bars mean magnitude, applied symmetrically)
        _, pinf_hi = pseudo_infinity_range(cj.pseudo_infinity)
        let_segments.append(
            f"let |{'∞' if unicode else 'inf'}| be {pinf_hi:g}")
    membership = "∈" if unicode else "in"
    for_segments = [
        f"{_display_symbol(param_renames[name]) if name in param_renames else name} "
        f"{membership} "
        f"{render_domain(bound, ascii_mode=not unicode, show_missing=domain_show_missing)}"
        for name, bound in cj.domain.items() if name not in cj.free_vars]

    parts = []
    if cj.assuming:
        # the precondition is part of the claim; rendered output must
        # carry it (terse input, explicit output), leading the claim
        # the same way the canonical input spelling does. Unicode mode
        # displays the is_* predicate vocabulary spaced, matching the
        # predicate statements themselves.
        # already canonical (grammar._canonical_assuming spells the
        # definedness premise `f is defined`), so nothing to rewrite
        assuming_text = cj.assuming
        if unicode:
            for joined in sorted(examine_predicates()):
                assuming_text = assuming_text.replace(
                    joined, joined.replace("_", " "))
        parts.append(assuming_text)
    if let_segments:
        parts.append(sep.join(let_segments))
    if for_segments:
        parts.append(("∀ " if unicode else "for ") + sep.join(for_segments))
    if getattr(cj, "outcome", ""):
        # the outcome clause trails the statement, in the canonical
        # ascii marker; extract_outcome_clause reads any accepted
        # spelling back off raw text before every other section
        statement = f"{statement} {'⟹' if unicode else '=>'} {cj.outcome}"
    if not parts:
        return statement
    return sep.join(parts) + sep + statement
