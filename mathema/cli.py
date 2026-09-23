# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The mathema command line.

    mathema check pkg.mod:fn [--claim "f(-x) == -f(x)"]   # one function or
                                                          #  one claim, interactively
    mathema verify [--root .]                  # test runner: every recorded
                                               #  function whose form changed
    mathema verify --status                    # fresh/stale sweep over
                                               #  @track_claims-tagged functions
    mathema audit mypkg [mypkg.sub ...]        # population report: claimed?
                                               #  derivable? test-covered?
    mathema init mypkg [mypkg.sub ...]         # scaffold bare claim stubs
                                               #  for everything unclaimed

`check` is the interactive face: adjudicate one file, one function, or one
ad-hoc claim, the way you would from a notebook. Lenient by default.

`verify` is the test-runner face and the CI gate: it sweeps the spec
store, re-adjudicates every function whose `form` hash no longer matches
its record (new or changed code), and refreshes the machine records so the
next run has a baseline. A falsified claim fails the run in every mode,
and so does an unknown claim until a human accepts the risk
(`mathema accept --as risk`), an unadjudicated claim in an agentic
loop is indistinguishable from one that would have failed. Strict by
default: an unverifiable (skipped) claim, accepted risk, or a
silently-unenforced declared domain also fails; `--lenient` relaxes
those structural cases to informational-only, never the wrong or
undecided ones. An unresolved global name fails in every mode.

Every command resolves its target through `mathema.targets.resolve`,
so one grammar covers dotted names, `module:function` forms, and file
paths (imported with real package context) everywhere. Exit codes:
0 clean; 1 gate failure; 2 usage, target, or authoring error; 130
interrupted.
"""
from __future__ import annotations

import argparse
import os
import sys

from .targets import TargetError, resolve, resolve_function


def _parse_domain(items: list[str]) -> dict:
    from .grammar import Interval

    out = {}
    for item in items or []:
        try:
            name, rng = item.split("=", 1)
            lo, hi = rng.split(":", 1)
            out[name] = Interval(float(lo), float(hi))
        except ValueError:
            raise SystemExit(f"mathema: bad --domain {item!r}; expected name=lo:hi")
    return out


def _validate_trials_scale(scale: float) -> None:
    if scale <= 0:
        raise SystemExit(f"mathema: --trials-scale must be > 0, got {scale!r}")


def _check_rows(args) -> list[dict]:
    from . import check
    from .authoring import retrieve
    from .records import claim_row
    from .spec import load_declared, load_verified
    from .verify import _accepted_risk, gate

    _validate_trials_scale(args.trials_scale)

    rows = []
    root = getattr(args, "root", ".")
    target = resolve(args.target, root)
    if not target.functions:
        raise TargetError(f"no functions found in {args.target}")
    verified_store = load_verified(root)
    declared_store = load_declared(root)
    for name, fn in sorted(target.functions.items()):
        rec = check(fn, claims=list(args.claim) if args.claim else None,
                    domain=_parse_domain(args.domain) or None,
                    trials_scale=args.trials_scale,
                    declared=retrieve(fn, root, store=declared_store))
        # the one gate (verify.gate): provenance population, so a
        # falsified suggestion surfaces in the printed detail (real
        # knowledge, and a reason not to adopt) but never gates;
        # pre-adoption, it is nobody's claim. Risk a human accepted on
        # this key's verified record is honored here the same as in
        # the verify sweep.
        accepted = _accepted_risk((verified_store.get(name) or {}).get("entry"))
        report = gate(rec.probes, strict=args.strict,
                      accepted_risk=accepted,
                      unresolved=rec.facts.unresolved)
        proven, holds = report.proven, report.holds
        total = (proven + holds + report.refuted + report.skipped
                 + report.unknown + report.owned)
        verified = proven + holds + report.refuted   # refutation is knowledge
        problems = report.problems
        rows.append({"name": name, "tier": rec.facts.tier,
                     "identity": {"form": rec.facts.form, "sig": rec.facts.sigh},
                     "proven": proven, "holds": holds, "refuted": report.refuted,
                     "unverifiable": report.skipped + report.owned,
                     "unknown": report.unknown,
                     "verified": verified, "total": total,
                     "coverage": f"{verified}/{total}" if total else "0/0",
                     "claims": rec.to_spec()["claims"],
                     "claim_rows": [claim_row(p, accepted_risk=accepted)
                                    for p in rec.probes],
                     "problems": problems})
    return rows


def _format_check(rows: list[dict], fmt: str) -> str:
    from . import SPEC_VERSION, __version__

    if fmt == "compact":
        # the adjudication agent shape: stance/source/gates per row,
        # counterexample present iff refuted, blocked_by iff blocked
        import json
        payload = [{"key": r["name"], "passed": not r["problems"],
                    "problems": r["problems"], "claims": r["claim_rows"]}
                   for r in rows]
        return json.dumps(payload, separators=(",", ":"))
    if fmt == "json":
        import json
        totals = {"functions": len(rows),
                  "verified": sum(r["verified"] for r in rows),
                  "total": sum(r["total"] for r in rows),
                  "failed": sum(1 for r in rows if r["problems"])}
        slim = [{k: v for k, v in r.items() if k != "claim_rows"}
                for r in rows]
        return json.dumps({"tool": "mathema", "version": __version__,
                           "CDD_spec_version": SPEC_VERSION,
                           "functions": slim, "totals": totals}, indent=1)
    if fmt == "junit":
        import xml.sax.saxutils as sx
        cases = []
        for r in rows:
            body = ""
            if r["problems"]:
                msg = sx.escape("; ".join(r["problems"]))
                body = f'<failure message="{msg}"/>'
            cases.append(f'<testcase classname="mathema.claims" '
                         f'name="{sx.escape(r["name"])} [{r["coverage"]} adjudicated]">'
                         f'{body}</testcase>')
        fails = sum(1 for r in rows if r["problems"])
        return ('<?xml version="1.0" encoding="utf-8"?>\n'
                f'<testsuite name="mathema claim coverage" tests="{len(rows)}" '
                f'failures="{fails}">' + "".join(cases) + "</testsuite>")
    if fmt == "github":
        lines = []
        for r in rows:
            if r["problems"]:
                lines.append(f'::error title=mathema claim check::{r["name"]}: '
                             + "; ".join(r["problems"]))
            else:
                lines.append(f'::notice title=mathema claim check::{r["name"]}: '
                             f'{r["coverage"]} claims adjudicated')
        lines.append(_format_check(rows, "text"))
        return "\n".join(lines)
    if fmt == "md":
        out = ["| function | tier | claims adjudicated | proven | hold | refuted "
               "| unknown | unverifiable | status |",
               "|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            status = "FAIL: " + "; ".join(r["problems"]) if r["problems"] else "ok"
            out.append(f'| `{r["name"]}` | {r["tier"]} | {r["coverage"]} '
                       f'| {r["proven"]} | {r["holds"]} | {r["refuted"]} '
                       f'| {r.get("unknown", 0)} | {r["unverifiable"]} | {status} |')
        out.append(f"\ncdd spec v{SPEC_VERSION}. refutation counts as "
                   "knowledge, never as failure.")
        return "\n".join(out)
    # text
    lines = []
    for r in rows:
        state = "FAIL" if r["problems"] else "ok"
        line = (f'{state:4} {r["name"]}: tier {r["tier"]}, claims {r["coverage"]} '
                'adjudicated ('
                + (f'{r["proven"]} proven, ' if r["proven"] else "")
                + f'{r["holds"]} hold, {r["refuted"]} refuted'
                + (f', {r.get("unknown", 0)} unknown' if r.get("unknown") else "")
                + (f', {r["unverifiable"]} unverifiable' if r["unverifiable"] else "")
                + ")")
        if r["problems"]:
            line += "  <- " + "; ".join(r["problems"])
        lines.append(line)
    return "\n".join(lines)


def cmd_check(args) -> int:
    """`mathema check`: one-off interactive verification of a single
    function (or file) against its built-in laws and any inline
    `--claim`s. Prints (or writes with `--output`) the formatted result.
    Exit code is 1 if any row had a problem (a falsified or unknown
    claim in any mode; skipped claims and unenforced domains under
    `--strict`), 0 otherwise, suitable for a pre-commit check on a
    single target."""
    rows = _check_rows(args)
    out = _format_check(rows, args.format)
    if args.output:
        with open(args.output, "w") as fh:
            fh.write(out + "\n")
    else:
        print(out)
    return 1 if any(r["problems"] for r in rows) else 0



def _emit_json(payload: dict, output: "str | None") -> None:
    """Intent:
        One JSON exit for every machine-readable verb: the envelope
        `check --format json` established, at the same indent, written
        to `--output` when given and to stdout otherwise.
    """
    import json

    from . import SPEC_VERSION, __version__
    body = {"tool": "mathema", "version": __version__,
            "CDD_spec_version": SPEC_VERSION, **payload}
    text = json.dumps(body, indent=1, default=str)
    if output:
        with open(output, "w") as fh:
            fh.write(text + "\n")
    else:
        print(text)


def cmd_verify(args) -> int:
    """The test-runner sweep, printed: `verify.verify_project` does the
    work (freshness, re-adjudication, record refresh, the one gate);
    this command renders its lines and the run summary, and exits 1 on
    any problem. The NOTE for authors: a function whose only declared
    claims live on a @claims_decorator or docstring Claims: block, with
    no prior verified record and no claims file anywhere, has no key
    the sweep can discover, the stores enumerate the population."""
    import os

    from .conjecture import GRAMMAR
    from .verify import verify_project

    _validate_trials_scale(args.trials_scale)
    root = os.path.abspath(args.root)
    if root not in sys.path:
        sys.path.insert(0, root)
    if args.status is not None:
        # the fresh/stale report, adjudicating nothing (the old
        # `mathema status` verb): a TARGET value imports first, so a
        # script's own @track_claims decorators register under their
        # real dotted keys (sys.modules keeps the module alive for the
        # registry's weakrefs)
        from . import status
        if isinstance(args.status, str):
            resolve(args.status, args.root)
        text = status(args.root)
        if getattr(args, "format", "text") == "json":
            # status is a human summary string; JSON mode carries it
            # verbatim rather than inventing a second structure for it
            _emit_json({"status": text}, getattr(args, "output", None))
            return 0
        print(text)
        return 0
    result = verify_project(args.root, all=args.all,
                            strict=args.strict,
                            trials_scale=args.trials_scale,
                            only=args.target or None)
    as_json = getattr(args, "format", "text") == "json"
    if result.nothing_declared:
        if as_json:
            _emit_json({"passed": True, "nothing_declared": True,
                        "keys": [], "problems": [],
                        "totals": {"fresh": 0, "adjudicated": 0,
                                   "problems": 0}},
                       getattr(args, "output", None))
            return 0
        if args.target:
            print(f"mathema: no such key under {args.root}: "
                  f"{', '.join(args.target)} (nothing to verify)")
            return 2
        print("mathema: nothing declared yet (no .mathema/verified or claim "
              f"files under {args.root})")
        return 0
    if as_json:
        _emit_json({
            "passed": not result.problems,
            "nothing_declared": False,
            "keys": result.keys,
            "problems": result.problems,
            "grammars_seen": sorted(result.grammars_seen),
            "grammar_verified_here": GRAMMAR,
            "totals": {"fresh": result.fresh,
                       "adjudicated": result.adjudicated,
                       "problems": len(result.problems)},
        }, getattr(args, "output", None))
        return 1 if result.problems else 0
    lines = list(result.lines)
    lines.append(f"{result.fresh} fresh (form unchanged, skipped), "
                 f"{result.adjudicated} adjudicated, "
                 f"{len(result.problems)} problem(s)")
    other_grammars = sorted(result.grammars_seen - {GRAMMAR})
    lines.append(
        f"grammars detected: "
        f"{', '.join(sorted(result.grammars_seen)) or '(none)'}; "
        f"verified by this run: {GRAMMAR}"
        + (f"; not verified here (different grammar, needs its own tool): "
           f"{', '.join(other_grammars)}" if other_grammars else ""))
    print("\n".join(lines))
    return 1 if result.problems else 0


def _typed_status(ti: dict) -> str:
    if ti["params_total"] == 0:
        return "yes" if ti["return_typed"] else "no"
    if ti["params_typed"] == ti["params_total"] and ti["return_typed"]:
        return "yes"
    if ti["params_typed"] == 0 and not ti["return_typed"]:
        return "no"
    return "partial"


def _fmt_bool(v):
    return "?" if v is None else ("yes" if v else "no")


_ANSI_GREEN, _ANSI_RED, _ANSI_AMBER, _ANSI_DIM, _ANSI_RESET, _ANSI_UNDERLINE = (
    "\x1b[32m", "\x1b[31m", "\x1b[33m", "\x1b[2m", "\x1b[0m", "\x1b[4m")

_CONDENSE_LIMIT = 3   # audit's global_vars/global_funcs/unresolved columns:
                     # show this many names in full, then "+N others", a
                     # real function (or a loosely-scoped one) can reference
                     # a dozen module globals, and a full comma list at that
                     # point stops reading as a summary and starts reading
                     # as noise


def _ellipsize(text: str, limit: int) -> str:
    """Intent:
        Cap a free-text cell: the fixed lead survives, an overlong
        tail of names becomes an ellipsis. The full text is the deriv
        report's job (--deriv-report).
    """
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _condense_names(names: list[str]) -> str:
    """Intent:
        A narrow cell for a name list: each long name ellipsized, at
        most three shown, the rest a bare +N. The full list is the
        deriv report's job (--deriv-report), not the grid's.
    """
    if not names:
        return "-"
    shown = [n if len(n) <= 14 else n[:11] + "..."
             for n in names[:_CONDENSE_LIMIT]]
    extra = len(names) - _CONDENSE_LIMIT
    return ", ".join(shown) + (f", +{extra}" if extra > 0 else "")


def _colorize_token(padded: str, raw: str, enabled: bool,
                    col: str | None = None) -> str:
    """Wrap an already-padded cell in color when its *unpadded* value is
    exactly one of the boolean-ish tokens (`yes`/`no`/`?`) audit's own
    columns use, deliberately narrow (never a whole cell/row/reason
    string) so free-text fields stay plain, uncluttered. Color wraps the
    padded text, not the other way around, so alignment is computed on
    real visible width before any (zero-width, invisible) ANSI codes are
    added, padding first, coloring second, always."""
    if not enabled:
        return padded
    if raw == "yes":
        return _ANSI_GREEN + padded + _ANSI_RESET
    if raw == "no":
        return _ANSI_RED + padded + _ANSI_RESET
    if raw == "?":
        return _ANSI_DIM + padded + _ANSI_RESET
    if raw == "-" and col == "reason":
        # the underivable group's empty reason IS the good outcome
        # (nothing blocks a derive-route proof), green, and the
        # non-empty reasons stay plain, never red
        return _ANSI_GREEN + padded + _ANSI_RESET
    if col in ("claims", "{min_expected|actual|est_applicable}") \
            and raw.startswith("{"):
        # the claim-floor flag: red under the floor, amber at or
        # above it, deliberately never green, since without a
        # corpus nobody can say the count is ENOUGH
        parts = [p.strip() for p in raw.strip("{}").split("|")]
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            if int(parts[1]) < int(parts[0]):
                return _ANSI_RED + padded + _ANSI_RESET
            return _ANSI_AMBER + padded + _ANSI_RESET
    return padded


def _render_grid(col_names: list[str], group_spans: list[int],
                 data_rows: list[list[str]], color: bool,
                 group_titles: "list[str] | None" = None) -> list[str]:
    """Column-padded, group-separated (" | " within a group, " || "
    between groups), boolean-token-colored table rendering, shared by
    every audit grid (`mathema audit`'s wide table and `--docs-only`'s
    checklist grid) so alignment/coloring logic exists in exactly one
    place. Every column is padded to the widest real value it holds
    (header included, computed from the actual data, not guessed).
    Color is a further, separate, purely additive layer on top: only
    the yes/no/? tokens get wrapped (never a whole cell/row), and only
    when `color` is true, callers gate that on `sys.stdout.isatty()`/
    `NO_COLOR` themselves, since piped/captured output (every test)
    must never see escape codes."""
    cell_rows = [row for row in data_rows if not isinstance(row, str)]
    widths = [max(len(col_names[i]), max((len(row[i]) for row in cell_rows), default=0))
             for i in range(len(col_names))]

    def render(cells: list[str], header: bool = False) -> str:
        padded = [_colorize_token(cell.ljust(widths[i]), cell, color,
                                  col=col_names[i])
                 for i, cell in enumerate(cells)]
        parts, idx = [], 0
        for span in group_spans:
            parts.append(" | ".join(padded[idx:idx + span]))
            idx += span
        line = " || ".join(parts).rstrip()
        if header and color:
            line = _ANSI_UNDERLINE + line + _ANSI_RESET
        return line

    out = []
    if group_titles is not None:
        # a title row above the columns: each group's name once, over
        # its own segment, so the columns underneath can stay short
        parts, idx = [], 0
        for span, title in zip(group_spans, group_titles):
            seg = sum(widths[idx:idx + span]) + 3 * (span - 1)
            parts.append(title.ljust(seg))
            idx += span
        title_line = " || ".join(parts).rstrip()
        if title_line:
            out.append(_ANSI_UNDERLINE + title_line + _ANSI_RESET
                       if color else title_line)
    # a plain-string entry is a section line (the tree layout's
    # module/class headings), emitted as-is between the cell rows
    return out + [render(col_names, header=True)] + [
        row if isinstance(row, str) else render(row) for row in data_rows]


def _blocked_key_color(report: dict) -> str:
    """The function's own key line, colored green/amber/red for a
    branch report by how many of its individual branches are
    resolvable (declaring a domain would make them provable) versus
    structurally blocked, a raw, mechanical fact about the branch's
    own condition shape, not a judgment call. Every other blocker is
    colored uniformly (red)."""
    if report["blocker"] == "branch":
        kinds = [b["kind"] for b in report["branches"]]
        if all(k == "resolvable" for k in kinds):
            return _ANSI_GREEN
        if any(k == "resolvable" for k in kinds):
            return _ANSI_AMBER
        return _ANSI_RED
    return _ANSI_RED



def _fmt_scope_detail(r: dict) -> list[str]:
    """Intent:
        The full, unellipsized module-state view the grid's condensed
        vars/mutates cells stand in for, with the file line each name
        is used at; one deriv-report line per relationship kind.
    """
    out = []
    for label, names in (("uses module state", r.get("global_vars")),
                         ("mutates module state", r.get("mutated_globals"))):
        if not names:
            continue
        lines_by_name = _name_use_lines(r, names)
        rendered = ", ".join(
            n + (f" (line {', '.join(map(str, lines_by_name[n]))})"
                 if lines_by_name.get(n) else "")
            for n in names)
        out.append(f"    {label}: {rendered}")
    return out


def _name_use_lines(r: dict, names: list) -> dict:
    """Intent:
        File line numbers where each named global appears in the
        function body, read off a fresh parse, deriv-report only, so
        the extra walk never taxes the plain grid.
    """
    import ast as _ast
    fn = r.get("_fn")
    if fn is None:
        return {}
    try:
        from .analysis import get_tree
        _src, tree = get_tree(fn)
        base = fn.__code__.co_firstlineno
    except Exception:
        return {}
    wanted = set(names)
    found: dict = {}
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Name) and node.id in wanted:
            found.setdefault(node.id, [])
            line = base + node.lineno - 1
            if line not in found[node.id]:
                found[node.id].append(line)
    return {k: sorted(v)[:4] for k, v in found.items()}

def _fmt_blocked_detail(key: str, report: dict, color: bool = False) -> list[str]:
    """One derivability_report() dict -> the coded detail lines the
    audit prints for an underivable function: one line per blocking
    construct, source line plus compact code, nothing else. The full
    hint text lives in the reason-code reference and in the issue
    payload (`mathema issue <key>`), not here."""
    from .diagnostics import _blocking_constructs

    def paint(word: str, code: str) -> str:
        return f"{code}{word}{_ANSI_RESET}" if color else word

    lines = [f"  {paint(f'{key}:', _blocked_key_color(report))}"]
    constructs = _blocking_constructs(report)
    if report["blocker"] == "branch":
        # resolvable branches are worth a line too; they name the
        # parameters a domain declaration would settle
        constructs = []
        for b in report["branches"]:
            if b.get("kind") == "blocked":
                code = f"branch:{b.get('code') or 'unrecognized-shape'}"
            else:
                needs = b.get("needs_domain_for") or []
                code = ("branch:needs-domain"
                        + (f"({', '.join(needs)})" if needs else ""))
            constructs.append({"line": b.get("line"), "code": code})
    for c in constructs:
        where = f"line {c['line']}" if c.get("line") else "line ?"
        lines.append(f"    {where}  {c['code']}")
    return lines


def _fmt_rollup(label: str, stats: dict) -> str:
    # Three different denominators hide under the same "X/Y" shape here,
    # and each fragment must say which, "claimed"/"derivable"/"typed"
    # count functions out of stats["n"] (every function in this group);
    # "tested" counts functions out of only those *with* coverage data
    # (a subset of stats["n"], not stats["n"] itself, a module with
    # no coverage.json entries for it at all would otherwise misread as
    # 0/n instead of "no data"); "docs" counts docstring best-practice
    # *criteria* met, summed across functions, not a function count.
    n = stats["n"]
    parts = [f"{stats['claimed']}/{n} functions claimed"]
    if stats["derivable"] is not None:
        parts.append(f"{stats['derivable']}/{n} functions derivable")
    if stats.get("unconditional") is not None:
        parts.append(f"{stats['unconditional']}/{n} lift unconditionally")
    if stats["typed"] is not None:
        parts.append(f"{stats['typed']}/{n} functions fully typed")
    if stats["tested"] is not None:
        parts.append(f"{stats['tested'][0]}/{stats['tested'][1]} functions "
                     "test-covered (of those with coverage data)")
    if stats["docs"] is not None:
        parts.append(f"{stats['docs'][0]}/{stats['docs'][1]} docstring "
                     "criteria met")
    return f"  {label}: " + ", ".join(parts)


def _warn_skipped_submodules(skipped: list) -> None:
    """Intent:
        A package walk skips any submodule that fails to import. Print
        those to stderr so a partial result (or an empty one) is never a
        silent mystery, the user sees exactly which submodules were not
        scanned and why.
    """
    for name, err in skipped:
        print(f"mathema: skipped submodule {name} (could not import: {err})",
              file=sys.stderr)


def _report_no_functions(targets, skipped: list) -> None:
    """Intent:
        Print the empty-result message with actionable hints, so "no
        functions found" is a diagnosis, not a dead end. A skipped
        submodule is the single likeliest cause and is named first.
    """
    print(f"mathema audit: no functions found under {', '.join(targets)}")
    if skipped:
        print("  the likeliest cause is above: "
              f"{len(skipped)} submodule(s) failed to import and were "
              "skipped, so any functions defined in them were never seen. "
              "Fix the import (a missing dependency, or the package not "
              "installed) and re-run.")
        return
    print("  things to check:")
    print("  1. the target is an importable dotted name (`mypkg` or "
          "`mypkg.submodule`), not a path. `mathema check` is the one that "
          "takes `file.py:function`.")
    print("  2. audit counts functions DEFINED in the target, not names "
          "imported or re-exported into it (those are attributed to the "
          "module that defines them, so audit that module or the whole "
          "package instead).")
    print("  3. a function wrapped by a decorator into a non-function object "
          "(a class instance, a partial, a jitted/vectorized callable) is "
          "not counted. Only plain functions and a class's own methods are.")


def cmd_audit(args) -> int:
    """Population-level report: every function mathema can find under
    the given targets, whether it's claimed at all (any surface), whether
    it's liftable for a *derive-route* proof specifically (probe-route
    claims are viable regardless, see inventory.purity_reason()), and,
    if a coverage.py report already exists, test-covered. Distinct
    from `check`'s per-function "claims X/Y adjudicated": this surfaces
    functions with *zero* claims, which the declared/verified store alone
    can never show.

    `--exclude` (see audit.AUDIT_ANALYSES) skips an analysis
    entirely, not just hides its column, for functions/callers that
    don't want it computed at all (a judgment-laden one like docstring
    quality, or an expensive one on a very large sweep).

    `--docs` switches the whole report to a per-function checkbox
    breakdown of just the docs criteria (the quality checklist and the
    docsync schema, both) instead of the wide table; see
    cmd_audit_docs_only()."""
    import os

    from .audit import AUDIT_ANALYSES, audit_rows, docs_only_rows
    from .inventory import suggest_coverage_command

    root = os.path.abspath(args.root)
    if root not in sys.path:
        sys.path.insert(0, root)

    if args.index:
        # the global index record (the old `mathema index` verb): every
        # discovered key with its source file/line, marked verified
        # where a record exists, written to .mathema/index.yaml
        from .audit import build_index, write_index
        index = build_index(args.target, root=args.root)
        n_funcs = sum(len(m["functions"]) for m in index["modules"])
        n_verified = sum(1 for m in index["modules"]
                         for f in m["functions"] if f["verified"])
        path = write_index(args.target, root=args.root)
        color = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
        for m in index["modules"]:
            intent = m.get("intent") or {}
            text = (intent.get("text") or "").strip() if isinstance(intent, dict) else ""
            print(f"\n{m['name']}" + (f" ({text})" if text else ""))
            cols = ["key", "span", "verified"]
            data = [[f["key"], f.get("span") or "-",
                     "yes" if f.get("verified") else "no"]
                    for f in m["functions"]]
            for line in _render_grid(cols, [len(cols)], data, color):
                print("  " + line)
        print(f"\n{len(index['modules'])} module(s), {n_funcs} function(s), "
              f"{n_verified} verified -> {path}")
        return 0

    exclude = frozenset(n for item in (args.exclude or [])
                        for n in item.split(","))
    if args.docs:
        # a dedicated, smaller sweep, nothing else is discovered or
        # computed, and audit_rows()'s flattened row shape
        # (score/applicable/conforms/errors only) has already thrown away
        # the per-criterion detail (.intent/.claims/.symbols_*) a checkbox
        # breakdown needs, so this doesn't reuse audit_rows() at all.
        rows = docs_only_rows(args.target, root=args.root,
                              mathema_docs=True)
        if not rows:
            _report_no_functions(args.target, [])
            return 0
        return _cmd_audit_docs_only(rows)

    unknown = exclude - AUDIT_ANALYSES
    if unknown:
        raise SystemExit(f"mathema audit: unknown --exclude {sorted(unknown)}; "
                         f"choose from {sorted(AUDIT_ANALYSES)}")
    compact_cols = None
    if args.compact or args.cols or getattr(args, "filter", None):
        # the speed half of column selection: analyses no chosen
        # column needs are excluded from the sweep itself
        from .audit import COMPACT_DEFAULT_COLS, exclude_for_cols
        compact_cols = ([c for item in (args.cols or [])
                         for c in item.split(",")]
                        or list(COMPACT_DEFAULT_COLS))
        derived = exclude_for_cols(compact_cols,
                                   filters=getattr(args, "filter", None))
        exclude = exclude | derived

    skipped: list = []
    rows = audit_rows(args.target, root=args.root, exclude=exclude,
                      skipped=skipped)
    _warn_skipped_submodules(skipped)
    if not rows:
        _report_no_functions(args.target, skipped)
        return 0

    if compact_cols is not None:
        # the column-oriented agent shape (also what the MCP audit tool
        # returns): column names once, shared key prefix factored out,
        # raw values with JSON null for missing, the resolved column
        # selection is echoed back in "cols"
        import json

        from .audit import compact_audit, filter_rows
        try:
            if getattr(args, "filter", None):
                rows = filter_rows(
                    rows, [t for item in args.filter
                           for t in item.split(",")])
            compact = compact_audit(rows, compact_cols)
        except ValueError as e:
            raise SystemExit(f"mathema audit: {e}")
        print(json.dumps(compact, separators=(",", ":")))
        return 0

    # Column-driven, not hand-assembled per row, and grouped, not one
    # flat list: `key` always leads (identity, not an analysis, never
    # excludable), then related columns sit together, derivability,
    # signature quality, scope hygiene, structure, testing, docs, with
    # " | " within a group and " || " between groups, so the grouping is
    # visible in the output itself, not just in this list's ordering.
    # Every column is real, structured data (never concatenated prose),
    # so a row always splits into the same field count/order regardless
    # of which analyses --exclude removes.
    from .docstring import claims_triplet
    from .reason_codes import blocked_code
    compress = not args.one_line

    def _names_cell(names):
        if compress:
            return _condense_names(names)
        return ", ".join(names) if names else "-"
    groups = [
        # floor | actual | expected: the least this shape gives you to
        # state, what it states, and what a function of this shape
        # typically carries. The last needs a corpus and reads "-".
        (None, [("claims", lambda r: claims_triplet(
            r["claim_floor"], r["n_claims"], None))]),
        # the blocker no longer implies the answer: a branch:needs-domain
        # row is blocked unconditionally and derivable all the same,
        # once a claim declares the domain that prunes the branch. So
        # the flag comes back, beside the reason it used to be inferred
        # from.
        ("derivable", [
            ("derives", lambda r: "-" if r["derivable"] is None
             else ("yes" if r["derivable"] else "no")),
            ("cx", lambda r: "?" if not r["complexity"] else str(r["complexity"]["cyclomatic"])),
            ("reason", lambda r: (_ellipsize(r["purity_reason"], 36)
                                  if compress else r["purity_reason"])
             if (r["pure"] is False and r["purity_reason"]) else "-"),
            ("code", lambda r: blocked_code(r["blocked_report"]) or "-"),
        ]),
        ("typing", [
            ("typed", lambda r: "?" if r["typing"] is None else _typed_status(r["typing"])),
            ("finite_domain", lambda r: "-" if not r["typing"] else (
                "; ".join(f"{p} in {{{', '.join(repr(v) for v in vs)}}}"
                         for p, vs in r["typing"]["finite_domains"].items()) or "-")),
        ]),
        ("scope", [
            # no boolean summary token here on purpose, a single "globals:
            # yes/no" conflated a real risk (a global *variable*'s hidden
            # state) with an ordinary sibling function/class/module
            # reference (not a risk at all), and the shared yes=green/
            # no=red colorer had the risk column backwards regardless
            # (yes should read as the bad outcome here, not the good one).
            # Three plain columns instead, same "-" when empty everything
            # else in this table already uses (structure, blocked).
            ("vars", lambda r: _names_cell(r["global_vars"])),
            # writing module state is a stronger relationship than reading
            # it: this function is why someone else's answer changed
            ("mutates", lambda r: _names_cell(r["mutated_globals"])),
            ("funcs", lambda r: _names_cell(r["global_funcs"])),
            ("unresolved", lambda r: _names_cell(r["unresolved"])),
        ]),
        ("tested", [("tested", lambda r: r["test_covered"] or "?")]),
        # a locked function's body cannot change until a human unlocks:
        # the assurance column, showing who pinned it
        ("locked", [("locked", lambda r: "-" if not r.get("locked")
                     else "yes" + (f" ({r['locked']['by']})"
                                   if r["locked"].get("by") else ""))]),
        ("docs", [
            ("quality", lambda r: "-" if not r["docs"]
             else f"{r['docs']['score']}/{r['docs']['applicable']}"),
        ]),
    ]
    if compress and not any(r["unresolved"] for r in rows):
        # a clean population doesn't pay for the column; --one-line
        # (the fully expanded table) always keeps it
        for analysis, cols in groups:
            if analysis == "scope":
                cols[:] = [c for c in cols if c[0] != "unresolved"]
    if compress and not any(r.get("locked") for r in rows):
        # same rule: a project with no locks doesn't pay for the column
        groups = [(a, c) for a, c in groups if a != "locked"]
    groups = [(analysis, cols) for analysis, cols in groups if analysis not in exclude]
    if "docsync" not in exclude:
        groups.append(("docsync", [("docsync", lambda r: "-" if not r["docsync"]
                      else f"{r['docsync']['percent']}%")]))

    # stdout.isatty() correctly reports False when piped/captured (every
    # test runs via subprocess with captured output), so color is never
    # on when a test could see the escape codes; NO_COLOR is the
    # standard opt-out convention, https://no-color.org.
    col_names = ["key", "span"] + [name for _, cols in groups for name, _ in cols]
    group_spans = [2] + [len(cols) for _, cols in groups]
    # the scope analysis reads as "globals" to a person, what state
    # outside its own parameters this function touches
    _titles = {"derivable": "derive route", "typing": "typing",
               "scope": "globals", "docs": "docs"}
    group_titles = [""] + [_titles.get(analysis or "", "")
                           for analysis, _ in groups]
    color = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    def _cells(r):
        return [fn(r) for _, cols in groups for name, fn in cols]

    if args.one_line:
        data_rows = [[r["key"], r["span"] or "-"] + _cells(r)
                     for r in rows]
    else:
        # the tree layout: one line for the module, one per enclosing
        # class, and each function indented under its own scope;
        # the key column carries only the leaf name, so the grid loses
        # the repeated dotted prefix's whole width
        data_rows = []
        seen_scopes: list = []
        root_pkg = None
        # grouped by module first, so a top-level function sorting
        # after a submodule's dotted keys can't split its module's
        # block in two
        for r in sorted(rows, key=lambda r: (r["module"] or "", r["key"])):
            module = r["module"] or ""
            qual = r["key"][len(module) + 1:] if r["key"].startswith(
                module + ".") else r["key"]
            parts = qual.split(".")
            scopes = [module] + parts[:-1]
            for depth, scope in enumerate(scopes):
                if seen_scopes[:depth + 1] != scopes[:depth + 1]:
                    if depth == 0:
                        # only the package root prints bare; every
                        # other line carries a leading dot, the
                        # nesting is a dotted-name continuation
                        # ("arbital", then ".datasets", " .OrbitSystem")
                        seg0 = scope.split(".", 1)[0]
                        if root_pkg != seg0:
                            root_pkg = seg0
                            text = scope
                        else:
                            text = scope[len(seg0):]
                    else:
                        text = "." + scope
                    data_rows.append(" " * depth + text)
                    seen_scopes = scopes[:depth + 1]
            data_rows.append([" " * len(scopes) + "." + parts[-1],
                              r["span"] or "-"] + _cells(r))
    lines = _render_grid(col_names, group_spans, data_rows, color,
                         group_titles=group_titles)

    n = len(rows)
    summary = [f"{sum(1 for r in rows if r['claimed'])}/{n} claimed"]
    n_locked = sum(1 for r in rows if r.get("locked"))
    if n_locked:
        summary.append(f"{n_locked} locked")
    if "derivable" not in exclude:
        # what the derive route can do here, given the domain the
        # signature, docstring and claims declare, the question a
        # reader is asking. `unconditional` follows it as the narrower
        # fact about the code alone, never as the headline: reporting
        # only that understated provability badly enough that a real
        # repository read 2/75 while carrying derive-route proofs.
        summary.append(f"{sum(1 for r in rows if r['derivable'])}/{n} "
                       "derivable")
        summary.append(f"{sum(1 for r in rows if r['unconditional'])}/{n} "
                       "lift unconditionally")
    if "typing" not in exclude:
        summary.append(f"{sum(1 for r in rows if _typed_status(r['typing']) == 'yes')}"
                       f"/{n} fully typed")
    if "docs" not in exclude:
        scored = [r["docs"] for r in rows if r["docs"] and r["docs"]["applicable"]]
        if scored:
            summary.append(f"{sum(d['score'] for d in scored)}/"
                           f"{sum(d['applicable'] for d in scored)} docstring "
                           "quality criteria met")
    if "tested" not in exclude:
        tested = [r["test_covered"] == "yes" for r in rows
                  if r["test_covered"] in ("yes", "no")]
        outdated = sum(1 for r in rows if r["test_covered"] == "outdated")
        if tested or outdated:
            line = f"{sum(tested)}/{len(tested)} test-covered"
            if outdated:
                line += (f" ({outdated} outdated, source changed "
                         "after the coverage report)")
            summary.append(line)
        else:
            suggestion = suggest_coverage_command(args.root)
            summary.append("no coverage.json/.coverage report found" + (
                f" (try `{suggestion}`)" if suggestion else ""))
    tagged = [r for r in rows if r["concepts"]]
    if tagged:
        distinct = {c for r in tagged for c in r["concepts"]}
        summary.append(f"{len(distinct)} concept(s) across "
                       f"{len(tagged)} function(s)")
    if "scope" not in exclude:
        # global_funcs excluded from this count, see the "scope"
        # column group above: a sibling function/class/module reference
        # isn't the "depends on hidden state" risk this line reports on.
        scoped = sum(1 for r in rows if r["global_vars"] or r["unresolved"])
        if scoped:
            summary.append(f"{scoped}/{n} depend on state outside their own "
                           "parameters (see the global_vars/unresolved columns)")
    if "docsync" not in exclude:
        scored = [r["docsync"] for r in rows if r["docsync"]]
        if scored:
            summary.append(f"mean docsync "
                           f"{round(sum(d['percent'] for d in scored) / len(scored))}%")
    lines.append("\n" + ", ".join(summary) + ".")
    if "derivable" not in exclude:
        lines.append("`derives` is what the derive route can do here, given the "
                     "domain the signature, docstring and claims declare. The "
                     "reason/code cells describe the UNCONDITIONAL lift, the "
                     "body with nothing supplied, so a branch:needs-domain row "
                     "reads blocked there and derives all the same, once a claim "
                     "declares the domain that prunes the branch. Neither is a "
                     "ceiling: a probe claim can still be written and "
                     "adjudicated for every function here.")

    blocked_rows = [r for r in rows if r["blocked_report"] is not None]
    if blocked_rows and "derivable" not in exclude and args.deriv_report:
        lines.append("\nunderivable functions:")
        for r in blocked_rows:
            lines.extend(_fmt_blocked_detail(r["key"], r["blocked_report"],
                                             color))
            lines.extend(_fmt_scope_detail(r))
        lines.append("codes explained: the reason-code reference in the "
                     "docs, or `mathema describe --issue <key>` for the full details")
    if args.deriv_report and "scope" not in exclude:
        scoped = [r for r in rows if (r["global_vars"] or r["mutated_globals"])
                  and r["blocked_report"] is None]
        if scoped:
            lines.append("\nmodule-state detail:")
            for r in scoped:
                lines.append(f"  {r['key']}:")
                lines.extend(_fmt_scope_detail(r))

    from .audit import rollup_by_module, rollup_by_target

    by_module = rollup_by_module(rows)
    if len(by_module) > 1:
        lines.append("\nby module:")
        lines.extend(_fmt_rollup(module, stats)
                     for module, stats in sorted(by_module.items()))
    by_target = rollup_by_target(rows, args.target)
    if len(by_target) > 1:
        lines.append("\nby package:")
        lines.extend(_fmt_rollup(target, stats) for target, stats in by_target.items())
    print("\n".join(lines))
    return 0


def _docs_yn(value: bool | None) -> str:
    """yes/no/`-`, like _fmt_bool(), but `None` renders `-` (not
    applicable to this function at all) rather than `?` (applicable but
    unknown), the distinction audit's docs-only grid needs since e.g.
    `documents_return` is genuinely `None` for a function that returns
    nothing, not an unresolved question mark."""
    return "-" if value is None else _fmt_bool(value)


def _cmd_audit_docs_only(rows: list[dict]) -> int:
    """`mathema audit --docs`' report: a colored grid, one row per
    function, for the loose `docs` checklist, same rendering
    (_render_grid()) as the wide `mathema audit` table, not the
    block-per-function text dump this replaced. A
    **second, independent** grid follows for the docsync
    score (docstring.docstring_sync()), printed separately, not as
    more columns appended to the same row, since it isn't "stricter
    docs" the way that would imply: it measures how well the docstring
    stays in sync with the code's own structure and its verified spec
    record, a genuinely different question from the quality checklist."""
    import os

    from .docstring import claims_triplet

    color = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    n = len(rows)

    docs_groups = [
        ("docs", [
            ("has_docstring", lambda r: _fmt_bool(r["docs"]["has_docstring"])),
            ("has_summary", lambda r: "-" if not r["docs"]["has_docstring"]
             else _fmt_bool(r["docs"]["has_summary"])),
            ("params", lambda r: "-" if not r["docs"]["params_total"]
             else f"{r['docs']['params_documented']}/{r['docs']['params_total']}"),
            ("returns", lambda r: _docs_yn(r["docs"]["documents_return"])),
            ("raises", lambda r: "-" if not r["docs"]["raises_total"]
             else f"{r['docs']['raises_documented']}/{r['docs']['raises_total']}"),
            ("quality_ratio", lambda r: f"{r['docs']['score']}/{r['docs']['applicable']}"),
            # claims and tags close the row together: neither is part
            # of the quality score the way the presence checks are
            ("claims", lambda r: "-" if not r["docs"].get("has_claims_block")
             else f"{r['docs']['claims_parsed']} parsed"),
            ("concepts/tags", lambda r: str(len(r.get("concepts") or []))
             if r.get("concepts") else "-"),
        ]),
    ]
    docs_col_names = ["key"] + [name for _, cols in docs_groups for name, _ in cols]
    docs_group_spans = [1] + [len(cols) for _, cols in docs_groups]
    docs_data_rows = [[r["key"]] + [fn(r) for _, cols in docs_groups for name, fn in cols]
                      for r in rows]
    lines = ["quality:"]
    lines.extend(_render_grid(docs_col_names, docs_group_spans, docs_data_rows, color))

    docs_scored = [r["docs"] for r in rows if r["docs"]["applicable"]]
    docs_summary = (f"{sum(d['score'] for d in docs_scored)}/"
                    f"{sum(d['applicable'] for d in docs_scored)} docstring "
                    "quality criteria met")
    lines.append("\n" + docs_summary + f" ({n} function{'s' if n != 1 else ''}).")

    sync_groups = [
        ("intent", [
            ("intent", lambda r: _fmt_bool(bool(r["sync"].parsed.intent))),
            ("notes", lambda r: "present" if r["sync"].parsed.notes else "-"),
            ("claims", lambda r: "-" if not r["sync"].parsed.claims
             else f"{len(r['sync'].parsed.claims)} parsed"),
            ("{min_expected|actual|est_applicable}", lambda r: claims_triplet(
                r['sync'].claims_floor, r['sync'].claims_actual,
                r['sync'].claims_expected)),
        ]),
        ("domain", [
            ("domain_declared", lambda r: "-" if not r["sync"].domain_declarable
             else f"{r['sync'].domain_declared}/{r['sync'].domain_declarable}"),
            ("enforced", lambda r: "-" if r["sync"].domain_enforced is None
             else _fmt_bool(r["sync"].domain_enforced)),
        ]),
        ("raises", [
            ("raises_declared", lambda r: "-" if not r["sync"].raises_total
             else f"{r['sync'].raises_covered}/{r['sync'].raises_total}"),
        ]),
        ("typing", [
            ("params_typed", lambda r: "-" if not r["sync"].params_typeable
             else f"{r['sync'].params_typed}/{r['sync'].params_typeable}"),
            ("return_typed", lambda r: "-" if r["sync"].return_typed is None
             else _fmt_bool(r["sync"].return_typed)),
        ]),
        ("callees", [
            ("callees_doc_quality", lambda r: "-" if not r["sync"].callee_funcs_total
             else f"{r['sync'].callee_funcs_documented}/{r['sync'].callee_funcs_total}"),
            # the mean of the callees' own shallow sync percentages,
            # a callee with a weak docsync shows through here
            ("callees_docsync", lambda r: "-"
             if r["sync"].callee_sync_percent is None
             else f"{r['sync'].callee_sync_percent}%"),
        ]),
        ("sync_score", [
            ("sync_score", lambda r: f"{r['sync'].percent}%"),
        ]),
    ]
    sync_col_names = ["key"] + [name for _, cols in sync_groups for name, _ in cols]
    sync_group_spans = [1] + [len(cols) for _, cols in sync_groups]
    sync_data_rows = [[r["key"]] + [fn(r) for _, cols in sync_groups for name, fn in cols]
                      for r in rows]
    sync_lines = _render_grid(sync_col_names, sync_group_spans, sync_data_rows, color)

    m_scored = [r["sync"] for r in rows if r["sync"].applicable]
    sync_summary = (f"mean docsync "
                    f"{round(sum(m.percent for m in m_scored) / len(m_scored))}% "
                    "(how much of what each function does is surfaced "
                    "as context)")
    lines.append("\ndocsync:")
    lines.extend(sync_lines)
    lines.append("\n" + sync_summary + f" ({n} function{'s' if n != 1 else ''}).")

    print("\n".join(lines))
    return 0


_RECORD_ATTR = "/.mathema/verified/**/*.yaml linguist-generated"
_GITATTRIBUTES_BLOCK = (
    "# mathema verified records are machine-generated evidence: collapse\n"
    "# them in diffs by default and keep them out of language stats. They\n"
    "# stay reviewable (expandable), and `mathema review` shows the\n"
    "# claim-level changes.\n"
    f"{_RECORD_ATTR}\n"
)
_MATHEMA_GITIGNORE = (
    "# Regenerated from the code or local-only, so not committed. The\n"
    "# verified records, meta (locks/policy), compendium and badges are the\n"
    "# evidence and config, and ARE committed.\n"
    "/declared/\n"
    "/issues/\n"
)


def _scaffold_git_files(root: str) -> list:
    """Write the git ergonomics for a tracked store, idempotently: the
    record `linguist-generated` marker into the repo's `.gitattributes`
    (appended if the file exists, created otherwise), and a
    `.mathema/.gitignore` that keeps regenerated/local-only subdirs out of
    the commit. Returns the paths written or amended; skips whatever is
    already in place."""
    import os
    written = []
    ga = os.path.join(root, ".gitattributes")
    existing = ""
    if os.path.exists(ga):
        with open(ga) as fh:
            existing = fh.read()
    if _RECORD_ATTR not in existing:
        with open(ga, "a") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write(("\n" if existing.strip() else "") + _GITATTRIBUTES_BLOCK)
        written.append(ga)
    gi = os.path.join(root, ".mathema", ".gitignore")
    if not os.path.exists(gi):
        os.makedirs(os.path.dirname(gi), exist_ok=True)
        with open(gi, "w") as fh:
            fh.write(_MATHEMA_GITIGNORE)
        written.append(gi)
    return written


# the CI gate fragments `mathema init --ci` scaffolds: the verify gate
# an adopting repository would otherwise write from scratch. Written
# only where absent, never overwritten; a scaffolded workflow is the
# adopter's file to edit from then on.
_CI_FILES = {
    "github": (".github/workflows/mathema-verify.yml", """\
# mathema verify is the CI gate over the committed .mathema/ store: it
# re-adjudicates whatever changed and gates the result. verify is
# STRICT by default, which fails a falsified claim, an open unknown
# one, AND a claim that could not be checked at all (an unreachable
# surface, an unsupported shape). Most stores have some of the last
# kind at first, so expect the first run to be red and to tell you
# exactly which claims it means. Add --lenient to report those
# unverifiable claims and accepted risk without failing, and keep
# strict for falsified and unknown, once you have decided each one is
# understood. Exit codes: 0 clean, 1 gate failure, 2 broken invocation
# or store, so a failing gate is distinguishable from a broken job
# without parsing any output.
name: mathema
on:
  push:
    branches: [main]
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      # your project must import for its claims to adjudicate; adjust
      # this line to however your project installs
      - run: pip install -e . mathema
      - run: mathema verify --root .
      # optional: the claim-level delta since the base, for a PR comment
      # - run: mathema review --format json --output review.json
"""),
    "gitlab": (".gitlab-ci.mathema.yml", """\
# mathema verify is the CI gate over the committed .mathema/ store.
# verify is STRICT by default: it fails a falsified claim, an open
# unknown one, and a claim that could not be checked at all, so expect
# the first run to be red and to name them. Add --lenient to stop the
# unverifiable ones failing the gate once each is understood.
# Include this from your own .gitlab-ci.yml:
#   include:
#     - local: .gitlab-ci.mathema.yml
mathema-verify:
  image: python:3.12
  script:
    # your project must import for its claims to adjudicate; adjust
    # the install line to however your project installs
    - pip install -e . mathema
    - mathema verify --root .
"""),
}


def _scaffold_ci(root: str, provider: str) -> int:
    """Write the named provider's verify-gate CI fragment, only where
    absent, and say what happened. A file already present is the
    adopter's own and is never touched."""
    rel, body = _CI_FILES[provider]
    path = os.path.join(root, rel)
    if os.path.exists(path):
        print(f"mathema init: CI gate already in place ({rel})")
        return 0
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        fh.write(body)
    print(f"mathema init: scaffolded the CI gate:\n  {rel}")
    if provider == "gitlab":
        print("  include it from your .gitlab-ci.yml:\n"
              "    include:\n      - local: .gitlab-ci.mathema.yml")
    return 0


# the mathema-agents skills repo: agent-facing setup (skills + per-tool
# adapters), fetched only when `mathema init --agents` explicitly asks
_AGENTS_URL = "https://github.com/tetrionlabs/mathema-agents.git"
# where each tool reads its config, and which pre-rendered subtree of the
# clone to copy there. `skills/` is vendored to the value in [0]; the pairs
# in [1] copy (clone-relative -> project-relative) the tool's own adapter
_AGENT_TOOLS = {
    "claude":   (".claude/skills", []),
    "codex":    ("skills", [("dist/AGENTS.md", "AGENTS.md")]),
    "gemini":   ("skills", [("dist/GEMINI.md", "GEMINI.md")]),
    "cursor":   ("skills", [("dist/.cursor/rules", ".cursor/rules")]),
    "copilot":  ("skills", [("dist/.github/copilot-instructions.md",
                             ".github/copilot-instructions.md")]),
    "windsurf": ("skills", [("dist/.windsurf/rules", ".windsurf/rules")]),
    "cline":    ("skills", [("dist/.clinerules", ".clinerules")]),
}
_TOOL_ALIASES = {"zed": "codex", "aider": "codex", "jules": "codex",
                 "agents": "codex", "roo": "cline"}
# a project already using a tool keeps this marker; detection lets bare
# `--agents` pick the one tool in use (order breaks ties toward none)
_AGENT_MARKERS = [(".claude", "claude"), (".cursor", "cursor"),
                  (".windsurf", "windsurf"), (".clinerules", "cline"),
                  (".github/copilot-instructions.md", "copilot"),
                  ("AGENTS.md", "codex"), ("GEMINI.md", "gemini")]
# tool -> where its adapter lives, for the manual-setup hint
_ADAPTER_HINT = [("Claude Code", "skills/ (or .claude/skills/)"),
                 ("Codex / Zed / Aider / Jules", "AGENTS.md"),
                 ("Gemini CLI", "GEMINI.md"), ("Cursor", ".cursor/rules/"),
                 ("GitHub Copilot", ".github/copilot-instructions.md"),
                 ("Windsurf", ".windsurf/rules/"), ("Cline / Roo",
                                                     ".clinerules/")]


def _detect_agent_tool(root: str) -> "str | None":
    """The single agent tool a project already uses, read off the config
    it keeps, or None when none or several match (the caller then vendors
    tool-neutrally rather than guessing)."""
    seen = []
    for marker, tool in _AGENT_MARKERS:
        if os.path.exists(os.path.join(root, marker)) and tool not in seen:
            seen.append(tool)
    return seen[0] if len(seen) == 1 else None


def _vendor_copy(src: str, dst: str, force: bool,
                 copied: list, skipped: list) -> None:
    """Copy a file, or a directory's files recursively, from `src` to
    `dst`, skipping any destination file already present unless `force`.
    Records each real path into `copied` or `skipped`."""
    import shutil
    if os.path.isdir(src):
        for name in sorted(os.listdir(src)):
            _vendor_copy(os.path.join(src, name), os.path.join(dst, name),
                         force, copied, skipped)
        return
    if os.path.exists(dst) and not force:
        skipped.append(dst)
        return
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copy2(src, dst)
    copied.append(dst)


def _agents_manual_hint(url: str) -> str:
    """The one-screen manual-setup fallback: vendor the skills and copy
    the adapter your tool reads, with the source repository named."""
    rows = "\n".join(f"    {tool:<28} {dest}" for tool, dest in _ADAPTER_HINT)
    return ("  Set them up by hand: clone the repo, copy its skills/ into "
            "your\n  project, and copy the one adapter your tool reads:\n"
            f"{rows}\n  Source: {url}")


def _agents_line_ref() -> str:
    """Intent:
        The skills ref matching this mathema's minor line, `v0.6` for
        any 0.6.x. The skills describe a tool surface (names, the
        verdict and acceptance vocabularies, the grammar, the badge
        artifacts) that moves on minors, so the repository carries one
        branch per line and the running version picks its own.
    Notes:
        Empty when the version does not read as `major.minor`, which
        leaves the caller on the default branch.
    """
    from . import __version__

    parts = str(__version__).split(".")
    if len(parts) < 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        return ""
    return f"v{parts[0]}.{parts[1]}"


def _agents_source_note(used: "str | None", fell_back: bool,
                        wanted: "str | None") -> str:
    """Intent:
        One line naming which ref the vendored skills came from, so a
        fallback is visible rather than silent: the resolved ref is
        never left for the reader to infer from the files.
    """
    from . import __version__

    if used:
        return f"{used}, matching mathema {__version__}"
    if fell_back:
        return (f"its default branch: the skills repository has no {wanted} "
                f"branch for mathema {__version__} yet, and the default "
                f"branch tracks the newest line")
    return "its default branch"


def _vendor_agents(root: str, tool_arg: str, url: "str | None",
                   ref: "str | None", force: bool) -> int:
    """Intent:
        Vendor the mathema-agents skills (and the right per-tool
        adapter) into `root`. Clones the repo shallow into a temp dir,
        copies only what the resolved tool needs, cleans up, and prints
        one clear message for the outcome. Fetch failures fall back to
        the manual hint and still exit 0: init's own scaffolding
        succeeded, and the network is a best-effort extra.
    """
    import shutil
    import tempfile

    from .fetch import REASONS, clone_repo

    url = url or os.environ.get("MATHEMA_AGENTS_URL") or _AGENTS_URL
    tool = _detect_agent_tool(root) if tool_arg == "auto" \
        else _TOOL_ALIASES.get(tool_arg, tool_arg)

    # an explicit --agents-ref is honoured exactly: a pin that cannot be
    # served is worth failing on, never worth substituting. Only the ref
    # derived from this mathema's own line falls back, because a line
    # branch may not exist yet
    pinned = ref is not None
    wanted = ref if pinned else (_agents_line_ref() or None)

    tmp = tempfile.mkdtemp(prefix="mathema-agents-")
    try:
        clone = os.path.join(tmp, "repo")
        res = clone_repo(url, clone, ref=wanted)
        used, fell_back = wanted, False
        if not res.ok and not pinned and wanted:
            clone = os.path.join(tmp, "default")
            res = clone_repo(url, clone, ref=None)
            used, fell_back = None, True
        if not res.ok:
            print(f"mathema init: could not fetch the agent skills: "
                  f"{REASONS.get(res.reason, res.reason)}.")
            if pinned:
                print(f"  ref asked for: {ref}")
            print(_agents_manual_hint(url))
            return 0
        skills_dest, adapters = _AGENT_TOOLS.get(tool, ("skills", []))
        copied: list = []
        skipped: list = []
        _vendor_copy(os.path.join(clone, "skills"),
                     os.path.join(root, skills_dest), force, copied, skipped)
        for src_rel, dst_rel in adapters:
            src = os.path.join(clone, src_rel)
            if os.path.exists(src):
                _vendor_copy(src, os.path.join(root, dst_rel), force,
                             copied, skipped)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    label = tool or "your project (tool-neutral)"
    if copied:
        rels = sorted(os.path.relpath(p, root) for p in copied)
        print(f"mathema init: vendored mathema-agents skills for {label}:\n  "
              + "\n  ".join(rels))
        print(f"  from {_agents_source_note(used, fell_back, wanted)}")
    else:
        print(f"mathema init: mathema-agents skills for {label} already in "
              "place")
    if skipped and not force:
        print(f"  ({len(skipped)} file(s) already present, left as they are; "
              "--force to overwrite)")
    if tool is None:
        print(_agents_manual_hint(url))
    return 0


def cmd_init(args) -> int:
    """Scaffold the git ergonomics for a tracked `.mathema/` store, and,
    for any targets, a bare declared entry (`claims: []`) for every
    unclaimed function under them. Additive and idempotent: the git
    files are written only where absent, and a stub never touches a
    function that already has a claim on any surface."""
    import os

    from .audit import write_stubs

    root = os.path.abspath(args.root)
    if root not in sys.path:
        sys.path.insert(0, root)
    git_written = _scaffold_git_files(root)
    if git_written:
        print("mathema init: scaffolded git files:\n  "
              + "\n  ".join(git_written))
    else:
        print("mathema init: git files already in place")
    stub_written: list = []
    if args.target:
        stub_written = write_stubs(args.target, root=args.root)
        if stub_written:
            print("mathema init: wrote stub entries to:\n  "
                  + "\n  ".join(stub_written))
        else:
            print("mathema init: no stubs needed, every discovered function "
                  "already has a claim, or none were found")
    ci_requested = getattr(args, "ci", None) is not None
    if ci_requested:
        _scaffold_ci(root, args.ci)
    if getattr(args, "agents", None) is not None:
        return _vendor_agents(root, args.agents,
                              getattr(args, "agents_url", None),
                              getattr(args, "agents_ref", None),
                              getattr(args, "force", False))
    if not git_written and not stub_written and not ci_requested:
        print("mathema init: nothing to do")
    return 0


def cmd_review(args) -> int:
    """`mathema review [<ref>]`: the claim-level delta of the verified
    store between a base git ref (default HEAD) and the working tree, the
    reviewer-facing counterpart to a raw YAML diff. `--format json` emits
    it for a CI job to post as a PR comment."""
    import os

    from .review import render, review

    root = os.path.abspath(args.root)
    result = review(root, ref=args.ref)
    if getattr(args, "format", "text") == "json":
        _emit_json(result, getattr(args, "output", None))
        return 0
    text = render(result)
    if getattr(args, "output", None):
        with open(args.output, "w") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    return 0


_TIER_BY_NUMBER = {"1": "source", "2": "normalized", "3": "structural",
                   "4": "lifted", "5": "canonical"}


def _print_describe_detail(key: str, fn, args) -> int:
    """`describe_detail()`'s result, printed as `mathema describe`'s
    single-function view: signature + identity hashes, inferred
    domains (each tagged with its source), claims (statement + LaTeX +
    verified verdict when one exists), then the tier ladder; one
    section per tier, in ladder order, `--tier` narrowing to just one
    (accepted either by name or by its 1-5 ladder position, translated
    to the real tier name here so `describe_detail()` itself only ever
    deals in names). A tier marked unavailable still prints its own
    real reason, never a silent gap."""
    from .audit import describe_detail

    tier = _TIER_BY_NUMBER.get(args.tier, args.tier)
    detail = describe_detail(key, fn, root=args.root, depth=args.depth, tier=tier)
    print(f"{key}{detail['signature']}")
    print(f"  sig_hash:  {detail['identity']['sig_hash']}")
    print(f"  form_hash: {detail['identity']['form_hash']}")
    print()
    print("Domains:")
    if detail["domains"]:
        from .grammar import render_domain_bound
        for d in detail["domains"]:
            print(f"  {d['param']}: {render_domain_bound(d['domain'])}  ({d['source']})")
    else:
        print("  (none inferred)")
    print()
    print("Claims:")
    if detail["claims"]:
        for c in detail["claims"]:
            verdict = f"  [{c['verdict']}]" if c["verdict"] else ""
            print(f"  {c['name']}: {c['statement']}{verdict}")
            print(f"    latex: {c['latex']}")
    else:
        print("  (none declared)")
    print()
    if detail.get("concepts"):
        print("Concepts: " + ", ".join(detail["concepts"]))
    if detail.get("references"):
        print("Links:")
        for r in detail["references"]:
            where = f"  {r['url']}" if r.get("url") else ""
            print(f"  [{r['via']}] {r['title']}{where}")
    if detail.get("concepts") or detail.get("references"):
        print()
    for t, r in detail["tiers"].items():
        note = "" if r["available"] else "  (not available)"
        print(f"--- {t}{note} ---")
        print(r["text"])
        print()
    return 0


def cmd_docsync(args) -> int:
    """`mathema docsync`: the sync pass over the layered store,
    materialize every authoring surface into
    the declared layer (.mathema/declared/), surface claim conflicts
    (the docstring's version offered over the declared file's), report
    docstring Claims:-block drift, and regenerate the index. The only
    docstring EDIT is the explicit --write-docstrings opt-in, which
    appends verified-but-unlisted claim names to an existing Claims:
    block; nothing ever creates a block or rewrites human prose."""
    from .sync import sync

    report = sync(args.target, root=args.root,
                  write_docstrings=args.write_docstrings)
    print(f"materialized {len(report.materialized)} declared entr"
          f"{'y' if len(report.materialized) == 1 else 'ies'} under "
          f".mathema/declared/")
    for c in report.conflicts:
        if c.get("kind") == "supersession":
            # the verified layer is the record: an authored change to
            # a verified claim is a deliberate supersession, gated by
            # its own acceptance, never auto-resolved here
            print(f"SUPERSESSION {c['key']}: claim {c['claim']!r} was "
                  f"re-authored on the {c['surface']} but is already "
                  f"verified")
            print(f"  verified: {c['verified']}")
            print(f"  authored: {c['authored']}")
            print("  the verified version keeps adjudicating; to adopt "
                  "the authored version run:")
            print(f"    mathema accept {c['key']} {c['claim']} "
                  f"--as superseded")
            continue
        print(f"CONFLICT {c['key']}: claim {c['claim']!r} differs between "
              f"the docstring and the declared file (not yet verified)")
        print(f"  [d]ocstring: {c['docstring']}")
        print(f"  [f]ile:      {c['declared']}")
        choice = "d" if args.yes else input(
            "  keep which version? [d/f/s(kip)] ").strip().lower()
        if choice == "d":
            _accept_docstring_claim(args.root, c)
            print("  declared file updated to the docstring version")
        elif choice == "f":
            print(f"  keeping the declared file's version, update the "
                  f"docstring line for {c['claim']!r} to match (or rerun "
                  f"with --write-docstrings after removing it)")
        else:
            print("  left as is; verify will keep flagging this conflict")
    for d in report.drift:
        names = ", ".join(d["names"])
        if d["kind"] == "unknown-in-docstring":
            print(f"drift {d['key']}: docstring Claims: names not in "
                  f"declared or verified: {names}")
        else:
            print(f"drift {d['key']}: claims not listed in the docstring "
                  f"Claims: block: {names}"
                  + ("" if args.write_docstrings else
                     "  (add with --write-docstrings)"))
    for k in report.docstrings_written:
        print(f"wrote missing claim names into {k}'s Claims: block")
    if report.index_path:
        print(f"index -> {report.index_path}")
    if args.report or args.write:
        import types
        for t in args.target:
            shim = types.SimpleNamespace(target=t, root=args.root,
                                         write=args.write)
            _docsync_checklist(shim)
    return 1 if (report.conflicts and not args.yes) else 0


def _accept_docstring_claim(root: str, conflict: dict) -> None:
    """Intent:
        The conflict resolution write: replace the declared file's
        statement for one claim with the docstring's version, in
        whichever claims file declares it (deepest wins, matching
        load_declared's own precedence).
    """
    import yaml

    from .spec import _is_claim_file, _SKIP_DIRS
    candidates = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            path = os.path.join(dirpath, name)
            if _is_claim_file(dirpath, name):
                candidates.append(path)
    for path in sorted(candidates,
                       key=lambda p: p.count(os.sep), reverse=True):
        doc = yaml.safe_load(open(path)) or {}
        entry = doc.get(conflict["key"])
        if not entry:
            continue
        for c in entry.get("claims") or []:
            if c.get("name") == conflict["claim"]:
                # the docstring claim's STRUCTURED shape replaces the
                # file's, statement and domain both, never a
                # rendered display string
                raw = conflict["docstring_raw"]
                c["statement"] = raw.get("statement") or raw.get("law")
                c.pop("law", None)
                if raw.get("domain"):
                    c["domain"] = raw["domain"]
                else:
                    c.pop("domain", None)
                if raw.get("route") and raw["route"] != "best":
                    # only an EXPLICIT [derive]/[probe] tag transfers;
                    # an untagged docstring line (default best) keeps
                    # the declared file's route; the conflict is
                    # about the statement, never a silent evidence
                    # downgrade
                    c["route"] = raw["route"]
                with open(path, "w") as fh:
                    yaml.safe_dump(doc, fh, sort_keys=False,
                                   allow_unicode=True)
                return


def cmd_describe(args) -> int:
    """`mathema describe <target>`: with a single target that resolves
    to exactly one function (a full dotted key, or a `target:name`
    shorthand, see `targets.resolve`), print that one function's full
    detail view (`_print_describe_detail`). Otherwise, the original
    behavior: list every function key `audit.discover()` finds under
    the given targets, each with its own rendered signature,
    deliberately lighter than `mathema audit`: no declared-claims
    lookup, no coverage report, no docstring scoring, no derivability
    computation, just discovery plus a signature."""
    import os

    from .audit import describe_rows

    root = os.path.abspath(args.root)
    if root not in sys.path:
        sys.path.insert(0, root)

    if args.issue:
        # the structured failure report (the old `mathema issue` verb):
        # build reason_codes.build_issue_record()'s payload for exactly
        # one function, print it, and offer the write under
        # .mathema/issues/. Not-written is a normal outcome (the
        # function is derivable, or the user declined), exit 0
        from .reason_codes import issue as _issue
        if len(args.target) != 1:
            raise TargetError("describe --issue takes exactly one target")
        _key, fn = resolve_function(args.target[0], args.root)
        _issue(fn, include_source=args.include_source,
               include_falsified=args.include_falsified, root=args.root)
        return 0

    targets = list(args.target)
    if len(targets) == 1:
        t = resolve(targets[0], args.root)
        if len(t.functions) == 1:
            key, fn = next(iter(t.functions.items()))
            return _print_describe_detail(key, fn, args)
        if t.module_name is not None:
            # a file-path spelling resolves to a dotted module; the
            # list mode below enumerates by dotted name
            targets = [t.module_name]

    rows = describe_rows(targets)
    if not rows:
        print(f"mathema describe: no functions found under {', '.join(args.target)}")
        return 0
    for r in rows:
        print(f"{r['key']}{r['signature']}")
    print(f"\n{len(rows)} function{'s' if len(rows) != 1 else ''} found")
    return 0


def _docsync_checklist(args) -> int:
    """`mathema docsync <target> [--write]`: the docstring side of the
    sync loop, per function. A function with a docstring gets its
    sync checklist (`docstring.docstring_sync`); one without gets a
    proposed docstring generated from its declared/verified claims and
    intent (`docstring.generate_docstring`), printed only, unless
    `--write` is passed, in which case each proposal is offered with a
    y/N prompt before `write_docstring()` inserts it. Creation only,
    never a rewrite of existing prose; exit code is always 0; this
    command measures and offers, it doesn't gate."""
    import os

    from .docstring import (docstring_sync, docstring_sync_checklist,
                            generate_docstring, write_docstring)

    root = os.path.abspath(args.root)
    if root not in sys.path:
        sys.path.insert(0, root)
    for key, fn in sorted(resolve(args.target, args.root).functions.items()):
        import inspect
        name = key.rsplit(".", 1)[-1]
        if (inspect.getdoc(fn) or "").strip():
            sync = docstring_sync(fn, root=args.root)
            print(f"{name}: docstring present, docsync {sync.percent}%")
            for line in docstring_sync_checklist(sync):
                print(f"  {line}")
            continue
        proposal = generate_docstring(fn, key=key, root=args.root)
        if proposal is None:
            print(f"{name}: no docstring, and no declared/verified intent or "
                  "claims to generate one from")
            continue
        print(f"{name}: no docstring, proposed:")
        for line in proposal.splitlines():
            print(f"    {line}")
        if args.write:
            answer = input(f"write this docstring into {name}'s source file? [y/N] ")
            if answer.strip().lower() == "y":
                path = write_docstring(fn, proposal)
                print(f"  written to {path}")
            else:
                print("  skipped")
    return 0



def _exclusive_group(claim_name: str) -> str | None:
    from .families import EXCLUSIVE_GROUPS
    base = claim_name.split("[", 1)[0]
    for group, members in EXCLUSIVE_GROUPS.items():
        if base in members:
            return group
    return None


def cmd_claims(args) -> int:
    """The claim-authoring surface for one function: bare lists what
    the declared layer already states; `--suggest` renders mathema's
    standard-claim suggestions (is_pole_safe, determinism, symmetry,
    ...) with their laws, explicitly, for the user to choose from;
    `--adopt NAME` writes one chosen suggestion into the declared
    claims file, where it becomes an ordinary gated claim. Suggestions
    never live in any layer; they are inferred fresh from the
    function each time; adoption is the explicit human step."""
    import yaml

    from .spec import load_declared
    from .suggest import suggest_claims as _suggest

    _key, fn = resolve_function(args.key, args.root)
    declared = load_declared(args.root)
    entry = (declared.get(args.key) or {}).get("entry") or {}
    declared_rows = entry.get("claims") or []
    declared_names = {c.get("name") for c in declared_rows if c.get("name")}

    if not args.suggest and not args.adopt:
        if not declared_rows:
            print(f"{args.key}: no declared claims "
                  "(mathema claims --suggest lists candidates)")
            return 0
        print(f"{args.key}: {len(declared_rows)} declared claim(s)")
        for c in declared_rows:
            print(f"  - {c.get('name')}: {c.get('statement') or c.get('law')}"
                  + (f"  [route {c['route']}]" if c.get("route") else ""))
        return 0

    suggestions = _suggest(fn, key=args.key, root=args.root)
    if args.suggest and getattr(args, "format", "text") == "json":
        from .records import claim_statement
        from .families import aspect_label
        from .suggest import bound_annotation_hint
        rows = [[cj.name, claim_statement(cj).strip(),
                 cj.route, cj.name in declared_names,
                 aspect_label(cj.name)]
                for cj in suggestions]
        payload = {"key": args.key,
                   "cols": ["name", "statement", "route", "declared",
                            "aspect"],
                   "rows": rows}
        hint = bound_annotation_hint(fn)
        if hint:
            payload["hints"] = [hint]
        _emit_json(payload, getattr(args, "output", None))
        return 0
    if args.suggest:
        print(f"{args.key}: {len(suggestions)} suggested claim(s) "
              "(adopt with: mathema claims KEY --adopt NAME)")
        for cj in suggestions:
            marker = " [already declared]" if cj.name in declared_names else ""
            from .families import aspect_label
            label = aspect_label(cj.name)
            aspect_note = (f"  [aspect: {label}]" if label else "")
            from .records import claim_statement
            print(f"  - {cj.name}: {claim_statement(cj)}"
                  f"  [route {cj.route}]{marker}{aspect_note}")
        from .suggest import bound_annotation_hint
        hint = bound_annotation_hint(fn)
        if hint:
            print(f"  hint: {hint}")
        return 0

    chosen = next((cj for cj in suggestions if cj.name == args.adopt), None)
    if chosen is None:
        names = ", ".join(cj.name for cj in suggestions) or "none"
        print(f"no suggestion named {args.adopt!r} for {args.key} "
              f"(available: {names})")
        return 2
    if chosen.name in declared_names:
        print(f"{chosen.name} is already declared for {args.key}")
        return 2
    group = _exclusive_group(chosen.name)
    if group:
        clash = [n for n in declared_names
                 if _exclusive_group(n) == group]
        if clash:
            print(f"cannot adopt {chosen.name}: mutually exclusive with the "
                  f"declared {', '.join(sorted(clash))} ({group} group, "
                  "at most one member states the policy)")
            return 2
    from .records import claim_statement
    from .spec import declare
    stanza = declare(chosen)
    stanza.pop("source", None)
    path = os.path.join(args.root, "claims", "adopted.claims.yaml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc: dict = {}
    if os.path.exists(path):
        with open(path) as fh:
            doc = yaml.safe_load(fh) or {}
    doc.setdefault(args.key, {}).setdefault("claims", []).append(stanza)
    with open(path, "w") as fh:
        yaml.safe_dump(doc, fh, sort_keys=False, allow_unicode=True)
    print(f"adopted {chosen.name} into {path}: "
          f"{claim_statement(chosen)}")
    return 0



def _accept_json(args, *, kind: str, plan: "dict | None" = None,
                 applied: bool = False, written: "str | None" = None,
                 error: "str | None" = None, extra: "dict | None" = None) -> int:
    """Intent:
        One JSON envelope for every acceptance path. `plan_acceptance`
        hands back the whole live YAML document under "doc" (and a
        "claim" aliasing into it), so this serializes an explicit
        allowlist, never the plan wholesale.
    """
    if error is not None:
        _emit_json({"ok": False, "error": error, "kind": kind,
                    "key": args.key, "applied": False},
                   getattr(args, "output", None))
        return 1
    plan = plan or {}
    body = {"ok": True, "kind": kind, "key": args.key,
            "claim": plan.get("claim_name", getattr(args, "claim", None)),
            "as": plan.get("as") or getattr(args, "as_", None),
            "by": plan.get("by"), "verdict": plan.get("verdict"),
            "applied": applied, "written": written,
            "actions": list(plan.get("actions") or [])}
    for key in ("accepted", "new_verdict", "corrected_statement",
                "corrected_name", "corrected_verdict", "corrected_n"):
        if plan.get(key) is not None:
            body[key] = plan[key]
    body.update(extra or {})
    _emit_json(body, getattr(args, "output", None))
    return 0


def _accept_context(args, by: str | None) -> int:
    """Intent:
        The context acceptances: --intent (declared -> documented, the
        human rung) and --concepts/--dismiss-concepts (tag curation).
        Same prompted contract as claim acceptance.
    """
    from .acceptance import (AcceptanceError, apply_intent_acceptance,
                             apply_scope_intent_acceptance,
                             plan_intent_acceptance,
                             plan_scope_intent_acceptance)

    as_json = getattr(args, "format", "text") == "json"
    if args.intent:
        import importlib
        is_scope = args.key == "__project__"
        if not is_scope:
            try:
                importlib.import_module(args.key)
                is_scope = True     # resolves as a module: scope level
            except Exception:
                is_scope = False
        kind = "scope-intent" if is_scope else "intent"
        planner = (plan_scope_intent_acceptance if is_scope
                   else plan_intent_acceptance)
        applier = (apply_scope_intent_acceptance if is_scope
                   else apply_intent_acceptance)
        try:
            plan = planner(args.root, args.key, by=by, note=args.note)
        except AcceptanceError as e:
            if as_json:
                return _accept_json(args, kind=kind, error=str(e))
            print(f"cannot accept: {e}")
            return 1
        if as_json:
            if not args.yes:
                return _accept_json(args, kind=kind, plan=plan,
                                    applied=False)
            return _accept_json(args, kind=kind, plan=plan, applied=True,
                                written=applier(plan))
        if is_scope:
            print(f"accepting the stated intent of {args.key} as "
                  f"documented (scope level; binds to the text)")
        for action in plan["actions"]:
            print(f"  - {action}")
        if not args.yes:
            if input("write this acceptance? [y/N] ").strip().lower() \
                    not in ("y", "yes"):
                print("nothing written")
                return 1
        print(f"written: {applier(plan)}")
        if is_scope:
            return 0
    if args.concepts or args.dismiss_concepts:
        from .concepts import accept_concepts
        accepted = [c.strip() for c in (args.concepts or "").split(",")
                    if c.strip()]
        dismissed = [c.strip() for c in
                     (args.dismiss_concepts or "").split(",") if c.strip()]
        if as_json and not args.yes:
            # concepts curation writes immediately; JSON mode still
            # previews rather than acting without an explicit yes
            return _accept_json(
                args, kind="concepts", applied=False,
                extra={"concepts_accepted": accepted,
                       "concepts_dismissed": dismissed},
                plan={"actions": [
                    f"accept concepts {accepted}" if accepted else "",
                    f"dismiss concepts {dismissed}" if dismissed else ""]})
        summary = accept_concepts(args.root, args.key, accepted,
                                  dismissed, by=by)
        if as_json:
            return _accept_json(
                args, kind="concepts", applied=True, written=summary,
                extra={"concepts_accepted": accepted,
                       "concepts_dismissed": dismissed})
        print(f"written: {summary}")
    return 0


def _record_lock_stamp(root: str, key: str, entry_lock: "dict | None",
                       event: "dict | None" = None) -> None:
    """Reflect a lock change onto the verified record when one exists:
    set or drop the `locked` stamp, append the event to the record's
    lock history, restamp integrity, write back. Missing record: fine,
    the next sweep stamps it from the meta file."""
    import os

    import yaml

    from .spec import integrity_checksum, verified_dir, write_yaml
    path = os.path.join(verified_dir(root), f"{key}.yaml")
    if not os.path.exists(path):
        return
    doc = yaml.safe_load(open(path)) or {}
    entry = doc.get(key)
    if not entry:
        return
    if entry_lock is None:
        entry.pop("locked", None)
    else:
        entry["locked"] = {k: entry_lock[k]
                           for k in ("form", "at", "by") if k in entry_lock}
    if event:
        entry.setdefault("lock_history", []).append(event)
    entry.setdefault("identity", {})["integrity"] = integrity_checksum(entry)
    write_yaml(path, doc,
               header=f"machine record; binds to form "
                      f"{(entry.get('identity') or {}).get('form')}")


def cmd_lock(args) -> int:
    """`mathema lock KEY`: pin the function's form hash so `mathema
    verify` fails (and refuses to re-adjudicate) if the body changes.
    Docstring edits stay allowed; the form hash never saw them. The
    safe direction, so no prompt and agents may run it; the way back
    is `mathema unlock`, which is a human act."""
    import os

    from . import analyze
    from .acceptance import default_identity
    from .locks import lock
    root = os.path.abspath(args.root)
    if root not in sys.path:
        sys.path.insert(0, root)
    key, fn = resolve_function(args.key, args.root)
    facts = analyze(fn)
    entry = lock(args.root, key, facts.form,
                 by=default_identity(), note=args.note)
    _record_lock_stamp(args.root, key, entry)
    print(f"locked {key} at form {entry['form']}")
    print("the body can no longer change under a CDD loop; docstring "
          "edits are unaffected. A human unlocks with: "
          f"mathema unlock {key}")
    return 0


def cmd_unlock(args) -> int:
    """`mathema unlock KEY`: the human act that releases a lock.
    Deliberately has no --yes, and prompts for the PIN when one is
    configured: an agent freezes, a person thaws."""
    import datetime

    from . import auth
    from .acceptance import default_identity
    from .locks import load_locks, unlock
    entry = load_locks(args.root).get(args.key)
    if entry is None:
        print(f"{args.key} is not locked")
        return 2
    print(f"{args.key} is locked at form {entry.get('form')}"
          + (f", by {entry['by']}" if entry.get("by") else "")
          + (f", since {entry['at']}" if entry.get("at") else ""))
    if entry.get("note"):
        print(f"  note: {entry['note']}")
    answer = input("unlock it? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("still locked")
        return 1
    attestation = auth.require_human(f"unlock {args.key}")
    unlock(args.root, args.key)
    event = {"at": datetime.date.today().isoformat(), "event": "unlocked"}
    by = default_identity()
    if by:
        event["by"] = by
    if attestation:
        event["verified_by"] = dict(attestation)
    _record_lock_stamp(args.root, args.key, None, event)
    print(f"unlocked {args.key}")
    return 0


def cmd_pin(args) -> int:
    """`mathema pin`: manage the human-verification credential that
    gates acceptance (and unlock). `set` stores a memorised PIN;
    `rotate` replaces it after verifying the current one; `remove`
    deletes it (verifying first); `status` reports method and key id,
    never the secret. All interactive: the credential exists precisely
    so that a non-interactive caller cannot supply it."""
    from . import auth

    current = auth.configured()
    if args.action == "status":
        if current is None:
            print("no PIN configured; acceptance and unlock run "
                  "without human verification")
            return 0
        print(f"method {current['method']}, key {current['key']}, "
              f"set {current.get('created', 'unknown')}")
        print(f"credential file: {auth.config_path()}")
        return 0
    if args.action == "set" and current is not None:
        print(f"a credential is already set (key {current['key']}); "
              f"use `mathema pin rotate` to replace it")
        return 2
    if args.action in ("rotate", "remove"):
        if current is None:
            print("no PIN configured")
            return 2
        # replacing or removing the gate is itself gated, or an agent
        # could reset the PIN to one it knows
        auth.require_human(f"pin {args.action}")
    if args.action == "remove":
        auth.remove()
        print("credential removed; acceptance and unlock now run "
              "without human verification")
        return 0
    # set / rotate
    if args.totp:
        info = auth.set_totp()
        print("TOTP credential set (experimental). Enrol it ONCE into "
              "any authenticator app;\nthis secret is not shown again:")
        print(f"  secret: {info['secret']}")
        print(f"  {info['uri']}")
        print(f"key {info['key']}")
    else:
        pin = auth.prompt_new_pin()
        info = auth.set_pin(pin)
        print(f"PIN set (key {info['key']}). Acceptance and unlock now "
              f"prompt for it.")
    return 0


def cmd_accept(args) -> int:
    """The human decision verb: annotate one adjudicated claim with an
    acceptance (`--as evidence | risk | discovery`). Prompted, the
    exact write is printed first and nothing happens without a yes.
    Deliberately CLI-only: acceptance is a human act, never exposed to
    agent tooling or any MCP surface."""
    from .acceptance import (AcceptanceError, apply_acceptance,
                             default_identity, plan_acceptance,
                             suggest_acceptance)

    by = args.by or default_identity()
    if args.intent or args.concepts or args.dismiss_concepts:
        return _accept_context(args, by)
    as_json = getattr(args, "format", "text") == "json"
    if args.as_ == "reconciled" and getattr(args, "all_records", False):
        # batch reconcile: clear a whole merge/rebase in one human act
        from .acceptance import mismatched_records, reconcile_all
        keys = mismatched_records(args.root)
        if not keys:
            print("nothing to reconcile: every record's checksum matches")
            return 0
        print(f"reconciling {len(keys)} record(s) whose checksum no longer "
              f"matches their contents:")
        for k in keys:
            print(f"  - {k}")
        if not args.yes:
            answer = input("re-stamp all of these over their current "
                           "contents? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("nothing written")
                return 1
        done = reconcile_all(args.root, keys, by=by, note=args.note)
        print(f"reconciled {len(done)} record(s): {', '.join(done)}")
        return 0
    if not args.key:
        print("cannot accept: a key is required "
              "(or `--as reconciled --all` to clear a whole merge)")
        return 2
    # guide a newcomer who omits --as with a claim: infer the natural kind
    # from the claim's verdict and say why. The confirmation below still
    # makes it a deliberate act; the JSON path stays explicit.
    if not args.as_ and args.claim and not as_json:
        try:
            kind, verdict, reason = suggest_acceptance(args.root, args.key,
                                                       args.claim)
        except AcceptanceError as e:
            print(f"cannot accept: {e}")
            return 1
        print(f"no --as given: {args.claim} is {verdict}, so accepting as "
              f"{kind} ({reason})")
        args.as_ = kind
    if not args.as_ or (not args.claim and args.as_ != "reconciled"):
        msg = ("an acceptance needs --as, and a claim name for every kind "
               "but `--as reconciled` (which re-stamps the whole record); "
               "or use --intent / --concepts")
        if as_json:
            _accept_json(args, kind="claim", error=msg)
            return 2
        print(f"cannot accept: {msg}")
        return 2
    if getattr(args, "corrected", None) and args.as_ != "discovery":
        print("cannot accept: --corrected only accompanies --as discovery")
        return 2
    try:
        plan = plan_acceptance(args.root, args.key, args.claim, args.as_,
                               by=by, note=args.note,
                               corrected=getattr(args, "corrected", None))
    except AcceptanceError as e:
        if as_json:
            return _accept_json(args, kind="claim", error=str(e))
        print(f"cannot accept: {e}")
        return 1
    if as_json:
        # plan-only unless --yes: a client previews the change, shows
        # it to a human, then re-runs with --yes. JSON mode never
        # prompts, so a non-interactive caller can't hang on stdin.
        if not args.yes:
            return _accept_json(args, kind="claim", plan=plan,
                                applied=False)
        summary = apply_acceptance(plan)
        return _accept_json(args, kind="claim", plan=plan, applied=True,
                            written=summary)
    if args.as_ == "reconciled":
        print(f"reconciling {args.key}: re-stamp its integrity over the "
              f"current contents" + (f", by {by}" if by else ""))
    else:
        print(f"accepting {args.key} :: {args.claim} "
              f"(verdict {plan['verdict']}) as {args.as_}"
              + (f", by {by}" if by else ""))
    for action in plan["actions"]:
        print(f"  - {action}")
    if not args.yes:
        answer = input("write this acceptance? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("nothing written")
            return 1
    summary = apply_acceptance(plan)
    print(f"written: {summary}")
    if plan.get("corrected_statement"):
        print("declared-layer stanza: REPLACE the old claim in your claims "
              "file with this (the superseded claim stays retained in the "
              "record's discoveries section):")
        print(f"  - name: {plan['corrected_name']}")
        print(f"    statement: \"{plan['corrected_statement']}\"")
        print(f"    route: {plan['claim'].get('route') or 'best'}")
    return 0


def _add_gate_flags(parser, *, default_strict: bool) -> None:
    """Intent:
        The one strictness spelling: mutually exclusive
        `--strict`/`--lenient` resolving to `args.strict`, with the
        per-command default stated in the help text. check defaults
        lenient (the authoring loop iterates while claims are still
        being written); verify defaults strict (CI gates a store that
        is supposed to be settled).
    """
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--strict", dest="strict", action="store_true",
                       help="unverifiable (skipped) claims and accepted "
                            "risk fail too; falsified and "
                            "unaccepted-unknown claims fail in every mode"
                            + (" (the default here)" if default_strict
                               else ""))
    group.add_argument("--lenient", dest="strict", action="store_false",
                       help="report unverifiable claims and accepted risk "
                            "instead of failing on them"
                            + ("" if default_strict
                               else " (the default here)"))
    parser.set_defaults(strict=default_strict)


def cmd_mcp(args) -> int:
    """`mathema mcp serve`: run the MCP server (stdio transport) over
    mathema's library surface. Needs the optional extra
    (`pip install mathema[mcp]`); without it, a clean install hint and
    exit 2, never a traceback."""
    import os

    root = os.path.abspath(args.root)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from .interfaces.mcp.server import build_server
        server = build_server()
    except ImportError:
        print("mathema: the MCP interface needs the optional extra, "
              "pip install mathema[mcp]", file=sys.stderr)
        return 2
    server.run()
    return 0


def cmd_coverage(args) -> int:
    """`mathema coverage [targets]`: implementation coverage, the share
    of each function's own lines backed by evidence, unioned across a
    test run, a mathema probe/examine trial, and a derive-route proof.
    A SEPARATE pass, never part of the fast `check` loop; the probe
    source needs the optional `coverage` extra (the row says so when it
    is missing). Omit targets to cover every function the store knows
    under `--root`, the rootwide analogue of `verify`."""
    import os

    from .impl_coverage import project_coverage, remedy

    root = os.path.abspath(args.root)
    if root not in sys.path:
        sys.path.insert(0, root)
    pc = project_coverage(args.target, root=root,
                          run_tests=getattr(args, 'run_tests', False))
    if not pc.functions:
        print("no functions found")
        return 0
    for fc in pc.functions:
        srcs = "+".join(k for k in ("test", "probe", "derive")
                        if k in fc.by_source) or "-"
        line = f"{fc.percent:3d}%  {fc.key}  [{srcs}]"
        r = remedy(fc)
        if r:
            line += f"  -> {r}"
        print(line)
    print(f"\nimplementation coverage: {pc.percent}%")
    if pc.potential_percent > pc.percent:
        print(f"(up to {pc.potential_percent}% after re-running the tests)")
    return 0


def cmd_badges(args) -> int:
    """`mathema badges [targets]`: the three badges, implementation
    (code), intent (spec), and clarity (behaviour), each 0-100, rolled up
    to the repo with intent and clarity weighted by each function's
    CENTRALITY (a core function counts more than a leaf; implementation
    stays a raw line ratio). Renders them as a radar triangle whose area
    is the overall health number. Prints the triangle; with `--out [DIR]`
    also writes the four artifacts (the ASCII triangle, one shields.io
    JSON per badge, a colored SVG twin, and a JSON snapshot for CI to
    diff) to DIR, defaulting to the standard `.mathema/badges/` under
    `--root` so a README can embed `triangle.svg` by its in-repo path.
    Omit targets for the rootwide analogue of verify."""
    import os

    from .badges import render_triangle, repo_badges, write_badges

    root = os.path.abspath(args.root)
    if root not in sys.path:
        sys.path.insert(0, root)
    scores = repo_badges(args.target or None, root=root)
    print(render_triangle(scores.implementation, scores.intent,
                          scores.clarity))
    if args.out is not None:
        out_dir = (args.out if os.path.isabs(args.out)
                   else os.path.join(root, args.out))
        written, pruned = write_badges(scores, out_dir)
        print(f"\nwrote {len(written)} artifacts to {out_dir}")
        for path in pruned:
            print(f"pruned stale badge artifact: "
                  f"{os.path.relpath(path, out_dir)}")
    return 0


def cmd_compendium(args) -> int:
    """`mathema compendium export <library>`: write a partial compendium
    SKELETON for <library> from this project's verified claims, verified
    bound claims become `claims`, verified `raises(...)` become
    `raises_when`, and AST-detected nan/inf returns become `nan_when`;
    `limitations` are stubbed as TODOs. The result is declared until a
    consumer verifies or trusts it, so review and complete it before
    shipping (curate limitations, confirm the AST-guessed nan regions)."""
    import os

    from .compendium.export import write_compendium

    root = os.path.abspath(args.root)
    if root not in sys.path:
        sys.path.insert(0, root)
    path = write_compendium(args.library, root=root, out_dir=args.out)
    print(f"wrote compendium skeleton for {args.library!r} to {path}")
    print("(a partial skeleton: complete the TODOs, confirm nan_when, and "
          "verify or trust it downstream, it is declared until then)")
    return 0


def _resolve_root(value: "str | None") -> str:
    """Intent:
        The project root a command works against. An explicit --root
        is an instruction and is taken verbatim. Otherwise the root is
        DISCOVERED: the nearest ancestor holding a `.mathema/` store,
        else the enclosing git repository, else the working directory.
        Running from inside a package used to create a whole second
        store there; a store is the product, so it is found rather
        than scattered.
    """
    if value is not None:
        return os.path.abspath(value)
    here = os.path.abspath(os.getcwd())
    path = here
    while True:
        if os.path.isdir(os.path.join(path, ".mathema")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    import subprocess
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
        top = out.stdout.strip()
        if out.returncode == 0 and top and os.path.isdir(top):
            return os.path.abspath(top)
    except Exception:
        pass
    return here


def main(argv: list[str] | None = None) -> int:
    """The `mathema` CLI entry point: builds the argument parser for
    every subcommand and dispatches to the matching `cmd_*` function,
    returning its exit code (0 clean, 1 gate failure, 2 usage/target/
    authoring error, 130 interrupted). `argv=None` reads from
    `sys.argv` (the normal case); passing an explicit list is for
    testing/programmatic invocation."""
    from . import badges as _badges
    ap = argparse.ArgumentParser(prog="mathema",
                                 description="Claim-Driven Development: turn "
                                             "software intent into verifiable "
                                             "evidence.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("check", help="interactive: adjudicate one file, "
                                      "one function, or one ad-hoc claim")
    pc.add_argument("target",
                    help="what to check: a dotted name (pkg.mod, "
                         "pkg.mod.fn, pkg.mod:fn) or a file path "
                         "(file.py, file.py:fn); files are imported "
                         "with real package context, so relative "
                         "imports inside them work")
    pc.add_argument("--root", default=None,
                    help="project root to import dotted targets "
                         "relative to (default .)")
    pc.add_argument("--claim", action="append", metavar="LAW",
                    help='ad-hoc claim to adjudicate, e.g. "f(-x) == -f(x)" '
                         "(repeatable)")
    pc.add_argument("--domain", action="append", metavar="name=lo:hi",
                    help="declared parameter range (repeatable)")
    pc.add_argument("--trials-scale", type=float, default=1.0, metavar="FACTOR",
                    help="shrink the probe-route trial budget by this factor "
                         "(0 < FACTOR <= 1, e.g. 0.25) for faster dev-loop "
                         "iteration; never scales upward, and never below a "
                         "floor that still guarantees real evidence")
    pc.add_argument("--format", default="text",
                    choices=["text", "json", "junit", "github", "md",
                             "compact"],
                    help="report format: json for artifacts, compact for "
                         "one-line JSON a program reads, junit for GitLab "
                         "test reports, github for Actions annotations, md for "
                         "step summaries")
    pc.add_argument("--output", default=None, metavar="FILE",
                    help="write the report to a file instead of stdout")
    _add_gate_flags(pc, default_strict=False)
    pc.set_defaults(fn=cmd_check)

    pv = sub.add_parser("verify", help="test runner: re-adjudicate every "
                                       "recorded function whose form hash "
                                       "changed (strict by default)")
    pv.add_argument("target", nargs="*",
                    help="dotted key(s) to re-verify and re-stamp on their "
                         "own (e.g. after a merge); omit to sweep the whole "
                         "project")
    pv.add_argument("--root", default=None,
                    help="project root holding .mathema/verified and claimspec.yaml")
    pv.add_argument("--all", action="store_true",
                    help="re-adjudicate everything, ignoring form-hash freshness")
    pv.add_argument("--status", nargs="?", const=True, default=None,
                    metavar="TARGET",
                    help="report fresh/stale per @track_claims-tagged "
                         "function and adjudicate nothing (always exit "
                         "0); an optional TARGET (dotted name or file "
                         "path) is imported first so its tagged "
                         "functions register")
    pv.add_argument("--trials-scale", type=float, default=1.0, metavar="FACTOR",
                    help="shrink the probe-route trial budget by this factor "
                         "(0 < FACTOR <= 1, e.g. 0.25) for faster dev-loop "
                         "iteration; never scales upward, and never below a "
                         "floor that still guarantees real evidence")
    pv.add_argument("--format", default="text", choices=["text", "json"],
                    help="report format: json emits the sweep as data "
                         "(per-key rows in the same claim vocabulary "
                         "`check --format compact` and the MCP tools use)")
    pv.add_argument("--output", metavar="FILE",
                    help="write the report to a file instead of stdout")
    _add_gate_flags(pv, default_strict=True)
    pv.set_defaults(fn=cmd_verify)

    pcov = sub.add_parser("coverage", help="implementation coverage: the "
                          "share of each function's lines backed by a test, "
                          "a probe, or a proof")
    pcov.add_argument("target", nargs="*",
                      help="importable module/package name(s); omit to cover "
                           "every function the store knows under --root, the "
                           "rootwide analogue of verify")
    pcov.add_argument("--root", default=None,
                      help="project root holding .mathema/ and any coverage "
                           "report to merge")
    pcov.add_argument("--run-tests", action="store_true",
                      help="first re-run the project's tests under coverage to "
                           "refresh the test source (the reclaim path); needs "
                           "the coverage extra installed")
    pcov.set_defaults(fn=cmd_coverage)

    pb = sub.add_parser("badges", help="the three badges (implementation, "
                        "intent, clarity) as a radar triangle")
    pb.add_argument("target", nargs="*",
                    help="importable module/package name(s); omit for the "
                         "rootwide analogue of verify")
    pb.add_argument("--root", default=None,
                    help="project root holding .mathema/")
    pb.add_argument("--out", nargs="?", default=None,
                    const=_badges.DEFAULT_BADGE_DIR, metavar="DIR",
                    help="also write the four artifacts (ASCII triangle, "
                         "shields JSON, SVG, snapshot); bare --out writes to "
                         f"the standard {_badges.DEFAULT_BADGE_DIR}/ under "
                         "--root, or pass an explicit DIR")
    pb.set_defaults(fn=cmd_badges)

    pcomp = sub.add_parser("compendium", help="export a partial compendium "
                           "skeleton for a library from this project's "
                           "verified claims")
    pcomp.add_argument("action", choices=["export"],
                       help="export: write a compendium skeleton")
    pcomp.add_argument("library", help="the importable package name to export "
                       "verified claims for (e.g. mylib)")
    pcomp.add_argument("--root", default=None,
                       help="project root holding .mathema/verified")
    pcomp.add_argument("--out", default=None, metavar="DIR",
                       help="output directory (default compendium/<library>/)")
    pcomp.set_defaults(fn=cmd_compendium)

    pa = sub.add_parser("audit", help="population report: every function "
                                      "found under the given targets, "
                                      "claimed/pure/test-covered or not")
    pa.add_argument("target", nargs="+",
                    help="importable module, package, or module:function "
                         "name(s), e.g. mypkg (whole package, walks every "
                         "submodule), mypkg.submodule (one module), or "
                         "mypkg.submodule:my_fn (one function/method); "
                         "must already be importable, pip install -e it "
                         "first")
    pa.add_argument("--root", default=None,
                    help="project root holding claims/ and any coverage.json/.coverage")
    pa.add_argument("--exclude", action="append", metavar="ANALYSIS",
                    help="skip an analysis entirely (not just hide its column), "
                         "comma-separated or repeatable: derivable, complexity, "
                         "typing, scope, tested, docs, docsync")
    pa.add_argument("--docs", action="store_true",
                    help="skip the wide table entirely and report per-function "
                         "checkbox breakdowns of just the docs criteria (the "
                         "quality checklist and the docsync schema, both); "
                         "nothing else is computed either")
    pa.add_argument("--deriv-report", action="store_true",
                    help="the full per-function detail below the table: "
                         "underivability reasons with the reason-code "
                         "hints, and each function's complete module-state "
                         "view (the names the grid's vars/mutates cells "
                         "condense, with the file lines they appear at)")
    pa.add_argument("--one-line", action="store_true",
                    help="one row per function with the full dotted key "
                         "and no cell compression (the tree layout's "
                         "module/class nesting, name ellipses, and +N "
                         "condensing all off)")
    pa.add_argument("--index", action="store_true",
                    help="write the global index record instead of the "
                         "table: every function key with its source "
                         "file/line, marked verified where a record "
                         "exists (.mathema/index.yaml)")
    pa.add_argument("--compact", action="store_true",
                    help="column-oriented JSON instead of the grid: "
                         "{prefix, cols, rows} with column names once, "
                         "the shared key prefix factored out, and raw "
                         "values (null for missing) (aligns with MCP "
                         "tool)")
    pa.add_argument("--filter", action="append", metavar="TERM",
                    help="keep only matching rows (implies --compact): "
                         "derive_unlock classes (actionable, limitation, "
                         "N/A), claimed/unclaimed, derivable/underivable, "
                         "underclaimed (fewer claims than the function's "
                         "own floor), or col~text / ~text column matches; "
                         "comma-separated or repeatable. Same-dimension "
                         "terms OR together (actionable,limitation = "
                         "either), dimensions AND across")
    pa.add_argument("--cols", action="append", metavar="COL",
                    help="columns for --compact (implies it), "
                         "comma-separated or repeatable, e.g. "
                         "key,lines,claims,derivable,blocker,typed,tested; "
                         "blocker_hint/blocker_unlock carry the remedy in "
                         "the row itself, and claims_vs_floor puts the "
                         "claim count beside the floor; the resolved "
                         "selection is echoed back in the output's cols "
                         "field")
    pa.set_defaults(fn=cmd_audit)

    pi = sub.add_parser("init", help="scaffold the git ergonomics for a "
                                     "tracked store (.gitattributes + "
                                     ".mathema/.gitignore), and bare declared "
                                     "claim stubs for any unclaimed target")
    pi.add_argument("target", nargs="*",
                    help="importable module or package name(s), same as "
                         "audit; omit to scaffold only the git files")
    pi.add_argument("--root", default=None, help="project root to write claims/ under")
    pi.add_argument("--agents", nargs="?", const="auto", default=None,
                    metavar="TOOL",
                    choices=["auto", "claude", "codex", "gemini", "cursor",
                             "copilot", "windsurf", "cline",
                             "zed", "aider", "jules", "agents", "roo"],
                    help="also vendor the mathema-agents skills for your agent "
                         "tool (claude, codex, gemini, cursor, copilot, "
                         "windsurf, cline); bare --agents auto-detects the one "
                         "your project already uses")
    pi.add_argument("--agents-url", default=None,
                    help="git URL for the skills repo (default the public "
                         "mathema-agents; also read from MATHEMA_AGENTS_URL)")
    pi.add_argument("--agents-ref", default=None,
                    help="branch or tag of the skills repo to fetch "
                         "(default: the branch matching your mathema minor "
                         "line, e.g. v0.6, falling back to its default "
                         "branch); an explicit ref is never substituted")
    pi.add_argument("--force", action="store_true",
                    help="overwrite vendored agent files that already exist")
    pi.add_argument("--ci", nargs="?", const="github", default=None,
                    metavar="PROVIDER", choices=["github", "gitlab"],
                    help="also scaffold the verify-gate CI fragment for "
                         "PROVIDER (github, gitlab); bare --ci means github. "
                         "Written only where absent, then it is yours to edit")
    pi.set_defaults(fn=cmd_init)

    pr = sub.add_parser("review", help="the claim-level delta of the verified "
                        "store since a git ref (verdict flips, added/removed "
                        "claims, reconciles), the reviewer's view of a PR")
    pr.add_argument("ref", nargs="?", default="HEAD",
                    help="base git ref to compare the working tree against "
                         "(default HEAD)")
    pr.add_argument("--root", default=None, help="project root holding .mathema/")
    pr.add_argument("--format", default="text", choices=["text", "json"],
                    help="text (default) or json for a CI comment")
    pr.add_argument("--output", metavar="FILE",
                    help="write the report to a file instead of stdout")
    pr.set_defaults(fn=cmd_review)

    ps = sub.add_parser("docsync", help="sync the layered store: "
                        "materialize authoring surfaces into the declared "
                        "layer, surface conflicts and docstring drift, "
                        "regenerate the index")
    ps.add_argument("target", nargs="*",
                    help="importable module/package name(s); omit to sync "
                         "every function the store already knows under "
                         "--root, the rootwide analogue of `verify`")
    ps.add_argument("--root", default=None,
                    help="project root holding claims/ and .mathema/")
    ps.add_argument("--write-docstrings", action="store_true",
                    help="append verified-but-unlisted claim names to "
                         "EXISTING Claims: blocks in source docstrings, "
                         "the explicit authoring edit, never implicit")
    ps.add_argument("--yes", action="store_true",
                    help="resolve every conflict as the docstring version "
                         "without prompting")
    ps.add_argument("--report", action="store_true",
                    help="also print the per-function docstring sync "
                         "checklist (the old docsync view)")
    ps.add_argument("--write", action="store_true",
                    help="offer generated docstrings for functions that "
                         "have none (y/N per function; creation only, "
                         "never a rewrite)")
    ps.set_defaults(fn=cmd_docsync)

    pd = sub.add_parser("describe", help="list every function key found "
                                         "under the given targets, with "
                                         "its own signature")
    pd.add_argument("target", nargs="+",
                    help="importable module, package, or module:function "
                         "name(s), same convention as audit")
    pd.add_argument("--root", default=None,
                    help="project root to import targets relative to")
    pd.add_argument("--depth", type=int, default=3,
                    help="callee-inlining depth for the tier-ladder diagram "
                         "(single-function mode only; default 3)")
    pd.add_argument("--tier",
                    choices=("source", "normalized", "structural", "lifted", "canonical",
                            "1", "2", "3", "4", "5"),
                    default=None,
                    help="narrow the tier ladder to just this one tier, by "
                         "name, or by its ladder position 1-5 (1=source, "
                         "2=normalized, 3=structural, 4=lifted, 5=canonical); "
                         "single-function mode only, default shows all five")
    pd.add_argument("--issue", action="store_true",
                    help="build a structured failure report for exactly "
                         "one function and offer to write it under "
                         ".mathema/issues/ (never makes a network "
                         "request)")
    pd.add_argument("--include-source", action="store_true",
                    help="with --issue: include the function's source in "
                         "this one payload (never remembered)")
    pd.add_argument("--include-falsified", action="store_true",
                    help="with --issue: also report an undiagnosed "
                         "falsified claim, not just a skipped one")
    pd.set_defaults(fn=cmd_describe)

    pcl = sub.add_parser("claims", help="claim authoring surface: list a "
                         "function's declared claims, render mathema's "
                         "suggested standard claims, or adopt one into the "
                         "declared layer (the explicit human step; "
                         "suggestions never live in any record)")
    pcl.add_argument("key", help="module-qualified function key (funcs.ema)")
    pcl.add_argument("--suggest", action="store_true",
                     help="render the suggested standard claims with laws "
                          "and exclusivity groups")
    pcl.add_argument("--adopt", default=None, metavar="NAME",
                     help="write the named suggestion into the declared "
                          "claims file (claims/adopted.claims.yaml)")
    pcl.add_argument("--root", default=None, help="project root")
    pcl.add_argument("--format", default="text", choices=["text", "json"],
                     help="report format: json emits --suggest's rows "
                          "columnar, matching the MCP suggest_claims tool")
    pcl.add_argument("--output", metavar="FILE",
                     help="write the report to a file instead of stdout")
    pcl.set_defaults(fn=cmd_claims)

    pac = sub.add_parser("accept", help="human decision layer: accept one "
                         "adjudicated claim's evidence, own its risk, or "
                         "diagnose its falsification as a discovery (prompted; "
                         "prints the exact write first)")
    pac.add_argument("key", nargs="?", default=None,
                     help="function key (the record under .mathema/verified/); "
                          "omit only with `--as reconciled --all`")
    pac.add_argument("claim", nargs="?", default=None,
                     help="claim name inside that record (omit for "
                          "--intent / --concepts / --as reconciled)")
    pac.add_argument("--all", dest="all_records", action="store_true",
                     help="with `--as reconciled`: reconcile every record "
                          "whose checksum no longer matches, in one act "
                          "(the whole post-merge state at once)")
    pac.add_argument("--intent", action="store_true",
                     help="accept the function's STATED INTENT as "
                          "documented, the human rung; binds to the "
                          "signature, the raised-exception surface, and "
                          "the intent text (a body-only refactor keeps "
                          "it, any of those changing re-opens it)")
    pac.add_argument("--concepts", default=None, metavar="A,B",
                     help="accept concepts (tags) as documented, "
                          "comma-separated, lightweight, never gates")
    pac.add_argument("--dismiss-concepts", default=None, metavar="C,D",
                     help="dismiss suggested concepts so they never "
                          "re-suggest (recorded in the declared layer)")
    pac.add_argument("--corrected", default=None, metavar="LAW",
                     help="with --as discovery: the corrected claim to "
                          "declare in place of the falsified one, "
                          "adjudicated against the live function before "
                          "anything is written (a correction that itself "
                          "falsifies is refused); without it a sound, "
                          "holding mechanical inverse may be offered")
    pac.add_argument("--as", dest="as_", required=False, default=None,
                     choices=("evidence", "risk", "discovery", "historical",
                              "superseded", "trusted", "reconciled"),
                     help="reconciled: re-stamp a whole record's integrity "
                          "over its current contents after a merge/rebase or "
                          "a declared-claim edit (no claim name); "
                          "evidence: enough empirical support (holds); "
                          "risk: owning an unknown/skipped gap; discovery: "
                          "a falsification that was right about the code and "
                          "wrong about the claim, declares the corrected "
                          "claim. There is no accepting a bug: fix the code "
                          "and the recorded counterexample replays until the "
                          "claim proves.; historical: the code moved past this claim (signature change), keep it as history; trusted: accept a compendium row at its claimed level (testimony; `mathema verify` re-adjudicates it locally)")
    pac.add_argument("--by", default=None,
                     help="who decided (default: git config user.name)")
    pac.add_argument("--note", default=None, help="free-text rationale")
    pac.add_argument("--yes", action="store_true",
                     help="skip the confirmation prompt (for scripted use "
                          "by a human; never wire this into agent tooling)")
    pac.add_argument("--root", default=None, help="project root")
    pac.add_argument("--format", default="text", choices=["text", "json"],
                     help="report format: json emits the acceptance PLAN "
                          "and writes nothing unless --yes is also given "
                          "(so a client can preview, then commit); JSON "
                          "mode never prompts")
    pac.add_argument("--output", metavar="FILE",
                     help="write the report to a file instead of stdout")
    pac.set_defaults(fn=cmd_accept)

    ppin = sub.add_parser("pin", help="manage the human-verification "
                          "credential that gates acceptance and unlock "
                          "(a PIN a person knows and an agent does not)")
    ppin.add_argument("action", choices=["set", "rotate", "remove", "status"],
                      help="set a credential, rotate it (verifies the "
                           "current one first), remove it (also verifies), "
                           "or show method and key id")
    ppin.add_argument("--totp", action="store_true",
                      help="experimental: use authenticator-app codes "
                           "(RFC 6238) instead of a static PIN")
    ppin.set_defaults(fn=cmd_pin)

    plk = sub.add_parser("lock", help="pin a function's form hash: verify "
                         "fails if the body changes, until a human unlocks "
                         "(docstring edits stay allowed)")
    plk.add_argument("key", help="module-qualified function key, or "
                                 "module:function")
    plk.add_argument("--note", default=None,
                     help="why it is locked, kept with the lock")
    plk.add_argument("--root", default=None,
                     help="project root holding .mathema/")
    plk.set_defaults(fn=cmd_lock)

    pul = sub.add_parser("unlock", help="release a lock (a human act: "
                         "prompted, PIN-verified when one is set, "
                         "deliberately no --yes)")
    pul.add_argument("key", help="the locked function's key")
    pul.add_argument("--root", default=None,
                     help="project root holding .mathema/")
    pul.set_defaults(fn=cmd_unlock)

    pm = sub.add_parser("mcp", help="the MCP interface: serve mathema's "
                        "library surface as MCP tools (needs "
                        "`pip install mathema[mcp]`)")
    pm.add_argument("action", choices=["serve"],
                    help="serve: run the server on stdio")
    pm.add_argument("--root", default=None,
                    help="project root the tools resolve targets and "
                         "stores against")
    pm.set_defaults(fn=cmd_mcp)

    args = ap.parse_args(argv)
    if getattr(args, "root", None) is None and hasattr(args, "root"):
        args.root = _resolve_root(None)
        if os.path.abspath(args.root) != os.path.abspath(os.getcwd()):
            print(f"mathema: using project root {args.root}")
    import yaml

    from .audit import DiscoveryError
    from .auth import HumanVerificationError
    from .conjecture import InvalidConjecture
    from .locks import LockError
    try:
        return args.fn(args)
    except (DiscoveryError, TargetError, InvalidConjecture, LockError) as e:
        print(f"mathema: {e}", file=sys.stderr)
        return 2
    except HumanVerificationError as e:
        print(f"mathema: {e}", file=sys.stderr)
        return 1
    except yaml.YAMLError as e:
        print(f"mathema: malformed YAML: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"mathema: {e}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print(file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
