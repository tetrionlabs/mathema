# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema compendium update`: bring the project's compendium files in
line with how its functions call libraries.

Two kinds of change, each printed:

- A call to a library function that passes a non-default literal
  argument (`np.mean(a, axis=0)`) that no row of that function pins
  gains rows pinning it: every unpinned row of the function is copied
  with the arguments bound first (`let axis be 0, dim(a) >= 1`), named
  after the row and the pins (`is_defined@axis=0`) and noting the call
  site. Each pinned row is adjudicated against the installed library
  first and written only when it holds or is proven over its stated
  domain, its float companion included; any other verdict is reported
  with its counterexample or reason and the row is left out
  (`let axis be 1, dim(a) >= 1` is falsified, since a one-dimensional
  `a` has no axis 1). The rows go into the project's compendium file
  for the library (`claims/<library>.claims.yaml`, created with
  `compendium:` and a `versions:` range from the installed version
  when there is none). An argument that is not a literal is reported
  and not pinned.
- A row whose own `versions:` range excludes the installed library, of
  a function the project calls, that `mathema verify` recorded as
  holding or proven on the installed version, has its range widened to
  include it. A row nobody uses keeps its range.
"""
from __future__ import annotations

import os
from typing import NamedTuple

from .._signatures import callable_signature

_PINNABLE = (bool, int, float, type(None))


class CallSite(NamedTuple):
    """One call of a library function from a project function: the
    calling key, the library key, the source line, the non-default
    literal arguments it passes, and the defaulted parameters it passes
    something other than a literal, each with the reason."""
    caller: str
    key: str
    line: int
    pins: dict
    unpinned: list


def _project_functions(root: str) -> list:
    """Intent:
        `(key, fn, facts)` for every project function the stores know
        (declared or verified), library keys and library records left
        out.
    """
    import warnings

    from . import is_library_record, load_library_claims
    from .. import analyze
    from ..conjecture import _resolve_func_ref
    from ..spec import load_declared, load_verified
    library_keys = set(load_library_claims(root))
    verified = load_verified(root)
    declared = load_declared(root)
    out: list = []
    for key in sorted(set(verified) | set(declared)):
        if key in library_keys or is_library_record(
                (verified.get(key) or {}).get("entry") or {}):
            continue
        fn = _resolve_func_ref(key, root=root)
        if fn is None:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                facts = analyze(fn)
        except Exception:
            continue
        out.append((key, fn, facts))
    return out


def _render_value(value) -> str:
    """A pinned value as the claim grammar spells it."""
    return repr(value)


def _call_arguments(node, signature) -> "tuple[dict, list] | None":
    """Intent:
        The non-default literal arguments one call passes, by
        parameter, and the defaulted parameters it passes something
        else, as `(pins, unpinned)`, reading the call's positional and
        keyword arguments against the library's signature. None when
        the arguments do not bind to the signature.
    """
    import ast
    import inspect

    positional = [a for a in node.args if not isinstance(a, ast.Starred)]
    keywords = {k.arg: k.value for k in node.keywords if k.arg is not None}
    unpinned: list = []
    if len(positional) != len(node.args):
        unpinned.append(("*args", "an unpacked argument list"))
    if len(keywords) != len(node.keywords):
        unpinned.append(("**kwargs", "an unpacked keyword mapping"))
    try:
        bound = signature.bind_partial(*positional, **keywords)
    except TypeError:
        return None
    pins: dict = {}
    for name, arg in bound.arguments.items():
        param = signature.parameters[name]
        if param.default is inspect.Parameter.empty or param.kind in (
                param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        try:
            value = ast.literal_eval(arg)
        except (ValueError, TypeError, SyntaxError, MemoryError,
                RecursionError):
            unpinned.append((f"{name}={ast.unparse(arg)}",
                             "not a literal"))
            continue
        try:
            same = value is param.default or value == param.default
        except Exception:
            same = False
        if same is True:
            continue
        if not isinstance(value, _PINNABLE):
            unpinned.append((f"{name}={ast.unparse(arg)}",
                             "a pin states a number, True, False or None"))
            continue
        pins[name] = value
    return pins, unpinned


def call_sites(root: str, library_claims: dict) -> list:
    """Intent:
        Every call a project function makes to a library function some
        claims file states rows about, with the arguments it passes
        (`CallSite`), in caller order.
    """
    import ast
    import inspect

    from . import _alias_origins, _dotted_call_name
    from ..analysis import get_tree
    from ..conjecture import _resolve_func_ref
    out: list = []
    for caller, fn, facts in _project_functions(root):
        try:
            _src, fdef = get_tree(fn)
            first = inspect.getsourcelines(fn)[1]
        except Exception:
            continue
        origin = _alias_origins(fn, facts)
        for node in ast.walk(fdef):
            if not isinstance(node, ast.Call):
                continue
            name = _dotted_call_name(node)
            if name is None:
                continue
            head, dot, rest = name.partition(".")
            base = origin.get(head)
            if base is None:
                continue
            key = f"{base}.{rest}" if dot else base
            if key not in library_claims:
                continue
            target = _resolve_func_ref(key)
            try:
                signature = callable_signature(target)
            except (TypeError, ValueError):
                continue
            found = _call_arguments(node, signature)
            if found is None:
                continue
            pins, unpinned = found
            if pins or unpinned:
                out.append(CallSite(caller, key, first + node.lineno - 1,
                                    pins, unpinned))
    return out


def _pinned_row(row: dict, pins: dict, site: CallSite) -> dict:
    """One row copied with the call's arguments pinned in front."""
    lets = ", ".join(f"let {p} be {_render_value(v)}"
                     for p, v in sorted(pins.items()))
    tag = ",".join(f"{p}={_render_value(v)}" for p, v in sorted(pins.items()))
    statement = str(row.get("statement") or row.get("law") or "")
    return {"name": f"{row.get('name')}@{tag}",
            "statement": f"{lets}, {statement}",
            "note": (f"pinned for the call in {site.caller} (line "
                     f"{site.line}), which passes {tag}")}


def _adjudicated(key: str, current: list, added: list, root: str,
                 library_claims: dict) -> dict:
    """Intent:
        `{row name: (verdict, why)}` for each pinned row in `added`,
        adjudicated against the installed library function beside the
        function's `current` rows (which its premises may name). A
        row's verdict is its weakest, with its float companion's
        counted: a falsified companion is a falsified row. `why` is the
        counterexample or the note. Every row is `unknown` when the
        library function does not resolve.
    """
    from . import external_premises
    from .. import check
    from ..conjecture import InvalidConjecture, _resolve_func_ref
    from ..spec import entry_claims
    fn = _resolve_func_ref(key, root=root)
    if fn is None:
        return {row["name"]: ("unknown", "the function does not resolve")
                for row in added}
    rows = [{k: v for k, v in r.items() if k != "verdict"}
            for r in current] + added
    try:
        rec = check(fn, claims=entry_claims({"claims": rows}),
                    known_premises=external_premises(
                        root, library_claims=library_claims))
    except InvalidConjecture as e:
        return {row["name"]: ("unknown", str(e)) for row in added}
    rank = {"falsified": 0, "unknown": 1, "holds": 2, "proven": 3}
    out: dict = {}
    for row in added:
        name = row["name"]
        own = [p for p in rec.probes
               if p.name == name or p.name.startswith(name + "[")]
        if not own:
            out[name] = ("unknown", "it was not adjudicated")
            continue
        worst = min(own, key=lambda p: rank.get(
            p.verdict.split(":", 1)[0], 1))
        verdict = worst.verdict.split(":", 1)[0]
        if verdict not in rank:
            verdict = "unknown"
        why = str(worst.counterexample or "") or (worst.note or "")
        out[name] = (verdict, why)
    return out


def _project_files(root: str) -> dict:
    """Intent:
        `{library: path}` for the project's own compendium files (the
        first file per library), the bundled directory left out.
    """
    from . import _bundled_dir
    from ..spec import claims_file_paths, read_claims_file
    out: dict = {}
    for path in claims_file_paths(root, exclude=(_bundled_dir(),)):
        try:
            data = read_claims_file(path, os.path.relpath(path, root)) or {}
        except Exception:
            continue
        library = data.get("compendium")
        if isinstance(library, str):
            out.setdefault(library, path)
    return out


def _widened(spec: str, installed: str) -> str:
    """Intent:
        The range `spec` widened just enough to include `installed`: an
        upper bound at or below it moves to the next minor version, a
        lower bound above it moves down to its major.minor.
    """
    from . import _version_tuple
    have = _version_tuple(installed)
    major, minor = (list(have) + [0, 0])[:2]
    parts = []
    for part in (p.strip() for p in spec.split(",")):
        if part.startswith(">=") and have < _version_tuple(part[2:]):
            part = f">={major}.{minor}"
        elif part.startswith("<") and have >= _version_tuple(part[1:]):
            part = f"<{major}.{minor + 1}"
        parts.append(part)
    return ",".join(parts)


def _header_lines(lines: list) -> int:
    """How many of a file's first lines form its leading comment block:
    the comment lines before the first line of YAML, with the blank
    lines around and between them."""
    count = 0
    for i, line in enumerate(lines):
        if line.strip() and not line.lstrip().startswith("#"):
            break
        count = i + 1
    return count


def _leading_comment(path: str) -> "str | None":
    """The comment block at the top of a file, blank lines before it
    skipped, as a `write_yaml` header, or None."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    block = [line.strip() for line in lines[:_header_lines(lines)]]
    while block and not block[0]:
        block = block[1:]
    while block and not block[-1]:
        block = block[:-1]
    return "\n".join(line[1:].strip() for line in block) or None


def _comments_beyond_header(path: str) -> bool:
    """Whether a file carries a YAML comment below its leading comment
    block (the block a rewrite keeps as its header)."""
    from ..sync import yaml_has_comments
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return False
    return yaml_has_comments("\n".join(lines[_header_lines(lines):]))


def plan_update(root: str = ".") -> dict:
    """Intent:
        What `mathema compendium update` would change, as data:
        `{"files": {path: new file mapping}, "lines": [str]}`, one line
        per change and per argument left unpinned, reading the project
        and writing nothing.
    """
    import yaml

    from . import (_installed_version, _version_in_range, install,
                   load_library_claims, resolved_calls, row_pins)
    from ..spec import load_verified

    root = os.path.abspath(root)
    install(root)
    library_claims = load_library_claims(root)
    files = _project_files(root)
    edited: dict = {}
    lines: list = []

    def target(library: str) -> "tuple[str, dict]":
        path = files.get(library) or os.path.join(
            root, "claims", f"{library}.claims.yaml")
        if path not in edited:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    edited[path] = yaml.safe_load(fh) or {}
            else:
                installed = _installed_version(library)
                versions = ("*" if installed in (None, "*") else
                            ">=" + ".".join(installed.split(".")[:2]))
                edited[path] = {"compendium": library, "versions": versions}
        return path, edited[path]

    for site in call_sites(root, library_claims):
        for arg, why in site.unpinned:
            lines.append(f"{site.key}: the call in {site.caller} (line "
                         f"{site.line}) passes {arg}, {why}; nothing pinned "
                         f"for it")
        if not site.pins:
            continue
        rows = (library_claims[site.key]["entry"].get("claims") or [])
        path, data = target(site.key.split(".")[0])
        entry = data.get(site.key)
        current = list((entry or {}).get("claims") or []) if entry else \
            [dict(r) for r in rows]
        if any(row_pins(r) == site.pins for r in current):
            continue
        base = [r for r in current if not row_pins(r) and r.get("name")]
        if not base:
            lines.append(f"{site.key}: the call in {site.caller} passes "
                         f"{site.pins}, and the function has no rows to pin")
            continue
        added = [_pinned_row(r, site.pins, site) for r in base]
        settled = _adjudicated(site.key, current, added, root,
                               library_claims)
        kept = []
        for row in added:
            verdict, why = settled.get(row["name"], ("unknown", ""))
            if verdict in ("proven", "holds"):
                kept.append((row, verdict))
                continue
            lines.append(f"{site.key}: {row['name']} ({row['statement']}) "
                         f"not added for the call in {site.caller} (line "
                         f"{site.line}): {verdict} against the installed "
                         f"library{f', {why}' if why else ''}")
        if not kept:
            continue
        if entry is None:
            # the project's entry shadows the bundled one: carry its rows
            current = [{k: v for k, v in r.items() if k in (
                "name", "statement", "route", "note", "versions")}
                for r in current]
        data[site.key] = {**(entry or {}),
                          "claims": current + [row for row, _v in kept]}
        rel = os.path.relpath(path, root)
        for row, verdict in kept:
            lines.append(f"{site.key}: add {row['name']} ({row['statement']})"
                         f" to {rel} for the call in {site.caller} (line "
                         f"{site.line}); {verdict} against the installed "
                         f"library, recorded when mathema verify runs")

    # widen a used, locally verified row whose own range excludes the
    # installed version
    called: set = set()
    for _key, fn, facts in _project_functions(root):
        called.update(resolved_calls(fn, facts))
    verified = load_verified(root)
    for library, path in sorted(files.items()):
        installed = _installed_version(library)
        if installed in (None, "*"):
            continue
        tag = f"compendium:{library}-{'.'.join(installed.split('.')[:2])}"
        _p, data = target(library)
        for key, entry in list(data.items()):
            if not isinstance(entry, dict) or key not in called:
                continue
            recorded = {c.get("name"): c for c in
                        ((verified.get(key) or {}).get("entry") or {})
                        .get("claims") or []}
            for row in entry.get("claims") or []:
                spec = row.get("versions")
                if spec is None or _version_in_range(installed, str(spec)):
                    continue
                seen = recorded.get(row.get("name")) or {}
                if seen.get("verdict") not in ("holds", "proven") or (
                        seen.get("meta") or {}).get(
                            "mathema.compendium") != tag:
                    continue
                wider = _widened(str(spec), installed)
                row["versions"] = wider
                lines.append(f"{key}: widened {row.get('name')}'s versions "
                             f"from {spec!r} to {wider!r} ({seen['verdict']} "
                             f"on {library} {installed})")
    changed = {p: d for p, d in edited.items() if _differs(p, d)}
    return {"files": changed, "lines": lines}


def _differs(path: str, data: dict) -> bool:
    import yaml
    if not os.path.exists(path):
        return True
    with open(path, encoding="utf-8") as fh:
        return (yaml.safe_load(fh) or {}) != data


def run_update(root: str = ".", dry_run: bool = False) -> list:
    """Intent:
        Apply `plan_update` (unless `dry_run`) and return the lines to
        print: each change, each argument left unpinned, each file
        written, or `nothing to change`, and a warning for each file
        rewritten that carries YAML comments below its header, since
        only the header survives the rewrite.
    """
    from ..spec import write_yaml
    plan = plan_update(root)
    lines = list(plan["lines"])
    for path, data in sorted(plan["files"].items()):
        rel = os.path.relpath(path, os.path.abspath(root))
        if _comments_beyond_header(path):
            lines.append(
                f"WARN {rel} has YAML comments below its header, which "
                f"{'would not survive' if dry_run else 'do not survive'} "
                f"this rewrite; keep a row's annotation in its `note:` "
                f"field, which persists through every rewrite")
        if dry_run:
            lines.append(f"would write {rel} (dry run: nothing written)")
            continue
        header = _leading_comment(path) or (
            f"claims about {data.get('compendium')}'s functions for this "
            f"project")
        write_yaml(path, data, header=header)
        lines.append(f"wrote {rel}")
    if not plan["files"]:
        lines.append("nothing to change")
    return lines
