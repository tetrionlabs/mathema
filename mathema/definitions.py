# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Proofs through definition rows.

A definition row is an ordinary library claim, named `definition`
(or `definition@p=v` for a call pinning a parameter), that states
what a library function computes in the claim grammar's own words:

    pandas.Series.std:
      claims:
        - name: definition
          statement: "for a in R^n \\ {∅}, assuming dim(a) >= 2, f(a) ~= std(a, ddof=1)"

The derive route reads a function body such as `returns.mean() /
returns.std(ddof=1) * np.sqrt(252)` by resolving each library call to
its key (through the parameter's runtime type for a method, through
the module's import aliases for a function), binding the call's
arguments against the row, and rewriting the call with the row's
right-hand side. The body then reads in grammar words only, and a
claim about it is decided as mathematics: a vector claim by lowering
to sums over a sequence of symbolic length (`symbolic._seqir`), a
matrix claim by the matrix algebra (`symbolic._matrix`).

Which rows may feed a proof depends on where they come from: a row
bundled with mathema is used at once (mathema's own test suite
verifies each against the installed library); a row from a project's
claims file or a third party is used only once `mathema verify` has
recorded it `holds` or `proven` locally, or it was accepted with
`mathema accept <key> <row> --as trusted`, and feeds sampling only
until then. A row verify recorded `falsified` is never used.

A `definition` row trusted by mathema (bundled, read with the installed
library inside its `versions:` range and at or above mathema's
supported floor, `compendium.SUPPORTED_FLOORS`) or by the user
(accepted `--as trusted`) is an axiom: a proof through it stays `proven`, and its
sketch names it ("taking numpy.std as std(a, ddof=1) (axiom, bundled
with mathema, numpy 2.0 to 2.x)"). Any other row the proof uses (one
only verified by execution, or a bundled row read outside its range)
is evidence (so is a bundled row read below the supported floor, down
to its file's range): the proof is `holds`, and its sketch says how to
lift it
("accept the row as trusted: mathema accept KEY ROW --as trusted").
The record lists each row used (`meta["mathema.definitions"]`) with
its source, local status, `standing` ("axiom" or "evidence"),
`trusted_by` ("mathema" or "user"), `versions` and `installed`.
"""
from __future__ import annotations

from ._signatures import module_scope
import ast
import copy
import os
from dataclasses import dataclass, field

#: the claim name a definition row carries, alone or before `@`
DEFINITION = "definition"

#: the law transforms a claim can bind that the sequence lowering reads
_TRANSFORMS = {"mathema.f.scale_seq": "scale",
               "mathema.f.shift_seq": "shift",
               "mathema.f.reverse_seq": "reverse"}

#: builtins a body may call, read as the grammar word of the same name
_BUILTIN_WORDS = frozenset({"abs", "sum", "len", "min", "max", "float"})

#: the runtime type of a column of each table runtime type
_COLUMN_TYPES = {"pandas.DataFrame": "pandas.Series",
                 "polars.DataFrame": "polars.Series"}


def _runtime_params(facts, kinds: tuple) -> dict:
    """`{parameter: runtime type}` for each parameter whose first
    detected runtime type carries one of `kinds`."""
    return {p: found[0].adapter
            for p, found in (getattr(facts, "runtime_types", None)
                             or {}).items()
            if found and found[0].kind in kinds}


def column_read(node, tables) -> "str | None":
    """The column name when `node` reads a column of a table parameter
    in `tables`, by attribute (`df.w`) or by item (`df["w"]`), else
    None."""
    from .conjecture import _TABLE_ATTRIBUTES
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
            and node.value.id in tables and not node.attr.startswith("_") \
            and node.attr not in _TABLE_ATTRIBUTES:
        return node.attr
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
            and node.value.id in tables \
            and isinstance(node.slice, ast.Constant) \
            and isinstance(node.slice.value, str):
        return node.slice.value
    return None


class _Typing:
    """Intent:
        The runtime type of the value a body expression denotes, where
        it is a vector the definition rows read: a parameter with a
        vector or matrix runtime type, a column of a table parameter,
        a local assigned one of these, arithmetic with such an operand,
        and a method whose definition row gives a vector (`cummax`).
    """

    def __init__(self, facts, book: "RowBook | None"):
        self.runtime = _runtime_params(facts, ("vec", "mat"))
        self.tables = _runtime_params(facts, ("table",))
        self.local: dict = {}
        self.book = book

    def of(self, node) -> "str | None":
        if isinstance(node, ast.Name):
            return self.runtime.get(node.id) or self.local.get(node.id)
        if column_read(node, self.tables) is not None:
            return _COLUMN_TYPES.get(self.tables[node.value.id])
        if isinstance(node, ast.BinOp) and not isinstance(node.op,
                                                          ast.MatMult):
            found = {t for t in (self.of(node.left), self.of(node.right))
                     if t is not None}
            return next(iter(found)) if len(found) == 1 else None
        if isinstance(node, ast.UnaryOp):
            return self.of(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func,
                                                     ast.Attribute):
            rt = self.of(node.func.value)
            if rt is not None and self._gives_vector(f"{rt}.{node.func.attr}"):
                return rt
        return None

    def _gives_vector(self, key: str) -> bool:
        """Whether every usable definition row of `key` states a vector
        of the same length as its receiver."""
        from .linalg import static_rank
        if self.book is None or not self.book.states(key):
            return False
        rows = self.book.rows(key)
        return bool(rows) and all(
            static_rank(r.rhs, {p: r.ranks.get(p, 0) for p in r.params}) == 1
            and r.ranks.get(r.params[0]) == 1 for r in rows)


class Decline(Exception):
    """The body or the claim is outside what definition rows rewrite;
    the message says which construct, and names a library key with no
    usable definition row."""


@dataclass
class Row:
    """Intent:
        One usable definition row: its key and name, the statement as
        written, where it came from, its local status (`bundled`, or
        the verdict `mathema verify` recorded, or `trusted`), the
        installed library version, and its parsed parts: the names
        `f(...)` takes, the right-hand side, the pins, and the
        premises as `(lhs, relation, rhs)` source triples.
    """
    key: str
    name: str
    statement: str
    source: str
    status: str
    library: str
    params: list
    rhs: ast.expr
    pins: dict
    premises: list
    ranks: dict = field(default_factory=dict)
    standing: str = "evidence"
    trusted_by: "str | None" = None
    versions: str = "*"
    installed: str = "*"

    def use(self) -> dict:
        return {"key": self.key, "row": self.name,
                "statement": self.statement, "source": self.source,
                "status": self.status, "library": self.library,
                "standing": self.standing, "trusted_by": self.trusted_by,
                "versions": self.versions, "installed": self.installed,
                "params": list(self.params),
                "rhs": ast.unparse(self.rhs)}


@dataclass
class Inlined:
    """A function body read in grammar words over its parameters, and
    the definition rows used (with any premise each carries, as
    `(row, premises)` with the premises in terms of the body)."""
    expr: ast.expr
    uses: list = field(default_factory=list)
    premises: list = field(default_factory=list)


def is_definition_name(name: "str | None") -> bool:
    """Whether a claim name names a definition row."""
    return bool(name) and (name == DEFINITION
                           or str(name).startswith(DEFINITION + "@"))


# which rows may be used

def _canonical(statement: str) -> "str | None":
    try:
        from .conjecture import claim
        from .spec import render_claim_text
        return render_claim_text(claim(statement), unicode=False)
    except Exception:
        return None


def _local_row(root: "str | None", key: str, name: str) -> "dict | None":
    """The row `mathema verify` recorded for `key` under `name` in the
    project at `root`, or None."""
    if root is None:
        return None
    from .spec import read_verified_file, verified_dir
    path = os.path.join(verified_dir(root), f"{key}.yaml")
    if not os.path.exists(path):
        return None
    data, _ = read_verified_file(path)
    entry = (data or {}).get(key) or {}
    return next((c for c in entry.get("claims") or []
                 if isinstance(c, dict) and c.get("name") == name), None)


def _local_status(local: "dict | None", statement: str,
                  versions: "str | None" = None) -> "str | None":
    """The local verdict of a recorded row stating `statement`
    (`trusted` for an accepted testimony still tied to the row as
    written, `statement` and its `versions` range), or None when
    nothing was recorded for this statement."""
    if local is None:
        return None
    if _canonical(str(local.get("statement") or "")) != _canonical(statement):
        return None
    verdict = str(local.get("verdict") or "").split(":", 1)[0]
    accepted = local.get("accepted") or {}
    if accepted.get("as") == "trusted" and not accepted.get("stale") \
            and verdict in ("holds", "proven"):
        from .acceptance import trust_mismatch
        if trust_mismatch(accepted, statement, versions) is None:
            return "trusted"
    return verdict or None


def _installed_root() -> "str | None":
    from .compendium import _INSTALLED
    return _INSTALLED.get("root")


def row_standing(root: "str | None", key: str, row: dict,
                 bundled: bool,
                 versions: "str | None" = None) -> "tuple[str | None, str]":
    """Intent:
        `(status, reason)` for one definition row: `status` is the
        local status a usable row carries (`bundled`, `holds`,
        `proven`, `trusted`), None when the row may not feed a proof,
        and `reason` then says why.
    """
    from .compendium import OUTSIDE_VERSIONS
    meta = row.get("meta") or {}
    if meta.get(OUTSIDE_VERSIONS):
        if bundled:
            # a bundled row read outside its range is evidence, not an
            # axiom: usable, and a proof through it is capped
            return "outside", ""
        return None, (f"its versions ({meta[OUTSIDE_VERSIONS]}) exclude "
                      f"the installed library")
    statement = str(row.get("statement") or "")
    local = _local_status(_local_row(root, key, str(row.get("name"))),
                          statement,
                          str(row.get("versions") or versions or "*"))
    if local == "falsified":
        return None, "mathema verify recorded it falsified"
    if bundled:
        return (local if local in ("holds", "proven", "trusted")
                else "bundled"), ""
    if local in ("holds", "proven", "trusted"):
        return local, ""
    return None, ("it is not bundled with mathema and mathema verify has "
                  "not recorded it holds here (run mathema verify, or "
                  "accept it with --as trusted), so until then it feeds "
                  "sampling only")


def _parse_premises(text: str) -> "list | None":
    """`assuming a and b` as `(lhs, relation, rhs)` source triples, or
    None when a part is not one comparison."""
    import re
    body = re.sub(r"^\s*assuming\s+", "", text or "").strip()
    if not body:
        return []
    out = []
    for part in re.split(r"\s+and\s+", body):
        try:
            node = ast.parse(part.strip(), mode="eval").body
        except SyntaxError:
            return None
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1):
            return None
        rel = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
               ast.Gt: ">", ast.GtE: ">="}.get(type(node.ops[0]))
        if rel is None:
            return None
        out.append((node.left, rel, node.comparators[0]))
    return out


def _parse_row(key: str, row: dict) -> "tuple | None":
    """`(params, rhs, pins, premises)` of a definition row, or None
    when its statement is not the equation `f(p, ...) == <expression>`
    (a row written with `~=` states closeness within ε, not an
    equation)."""
    from .conjecture import _single_point, claim
    try:
        cj = claim(str(row.get("statement") or ""), name=row.get("name"))
    except Exception:
        return None
    if cj.relation != "==" or cj.negated or cj.links:
        return None
    try:
        lhs = ast.parse(cj.lhs, mode="eval").body
        rhs = ast.parse(cj.rhs, mode="eval").body
    except SyntaxError:
        return None

    called: dict = {}

    def f_params(node):
        # `f(a, b)`, its pins written in the call as constants
        # (`f(a, axis=1)`)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "f" \
                and all(isinstance(a, ast.Name) for a in node.args):
            values = {}
            for k in node.keywords:
                try:
                    values[k.arg] = ast.literal_eval(k.value)
                except ValueError:
                    if isinstance(k.value, ast.Name) and k.value.id == "inf":
                        values[k.arg] = float("inf")
                    else:
                        return None
            if None in values:
                return None
            called.clear()
            called.update(values)
            return [a.id for a in node.args]
        return None
    params = f_params(lhs)
    if params is None:
        params, rhs = f_params(rhs), lhs
    if params is None:
        return None
    pins = {**dict(cj.param_pins or {}), **called}
    for name in cj.free_vars or ():
        point = _single_point((cj.domain or {}).get(name))
        if point is not None:
            pins[name] = (int(point) if isinstance(point, float)
                          and point.is_integer() else point)
    premises = _parse_premises(cj.assuming or "")
    if premises is None:
        return None
    ranks = {p: len(getattr((cj.domain or {}).get(p), "dims", ()) or ())
             for p in params}
    return params, rhs, pins, premises, ranks


def _standing(row: dict, status: str, bundled: bool) -> tuple:
    """Intent:
        `(standing, trusted_by)` of a usable definition row: an
        `"axiom"` trusted by `"user"` when accepted `--as trusted`, by
        `"mathema"` when bundled and read inside its versions range;
        otherwise `"evidence"` (verified by execution, or a bundled row
        read outside its range), trusted by no one. Only a row named
        `definition` can be an axiom.
    """
    if not is_definition_name(row.get("name")):
        return "evidence", None
    if status == "trusted":
        return "axiom", "user"
    if bundled and status != "outside":
        return "axiom", "mathema"
    return "evidence", None


def _versions_words(library: str, spec: str) -> str:
    """A version range in words: `numpy 1.24 to 2.x` for `>=1.24,<3`,
    `numpy 2 and later` for `>=2`, `numpy, any version` for `*`."""
    name = library.split(" ", 1)[0]
    spec = (spec or "*").strip()
    if spec == "*":
        return f"{name}, any version"
    low = high = None
    for part in (p.strip() for p in spec.split(",")):
        if part.startswith(">="):
            low = part[2:]
        elif part.startswith("<"):
            high = part[1:]
    if high is not None and high.isdigit():
        high = f"{int(high) - 1}.x"
    elif high is not None:
        high = f"below {high}"
    if low and high:
        return f"{name} {low} to {high}"
    if low:
        return f"{name} {low} and later"
    return f"{name} {high}"


def rows_sketch(used: list, sketch: "str | None") -> "tuple[bool, str | None]":
    """Intent:
        `(capped, sketch)` for a derive proof through the definition
        rows `used` (their `Row.use()` entries): `capped` when any row
        is evidence rather than an axiom, and the proof's sketch with a
        line naming each row: an axiom as `taking numpy.std as std(a,
        ddof=1) (axiom, bundled with mathema, numpy 2.0 to 2.x)`,
        evidence with how to lift it (`accept the row as trusted:
        mathema accept KEY ROW --as trusted`).
    """
    if not used:
        return False, sketch
    lines = []
    capped = False
    for u in used:
        call = f"{u['key']} as {u.get('rhs')}"
        if u.get("standing") == "axiom":
            whose = ("accepted as trusted" if u.get("trusted_by") == "user"
                     else "bundled with mathema, "
                          + _versions_words(u.get("library", ""),
                                            _from_floor(u.get("library", ""),
                                                        u.get("versions",
                                                              "*"))))
            lines.append(f"taking {call} (axiom, {whose})")
            continue
        capped = True
        lines.append(f"taking {call} (evidence, {u['key']} {u['row']} row "
                     f"{_evidence_words(u)}); accept the row as trusted: "
                     f"mathema accept {u['key']} {u['row']} --as trusted")
    head = "; ".join(lines)
    return capped, (f"{head}; {sketch}" if sketch else head)


def _from_floor(library: str, spec: str) -> str:
    """A versions range with its start raised to the library's
    supported floor, the range a bundled row is an axiom over."""
    from .compendium import SUPPORTED_FLOORS, _version_tuple
    floor = SUPPORTED_FLOORS.get(library.split(" ", 1)[0])
    if floor is None:
        return spec
    parts = [p.strip() for p in str(spec or "*").split(",") if p.strip()]
    lows = [p for p in parts if p.startswith(">=")]
    rest = [p for p in parts if not p.startswith(">=") and p != "*"]
    low = lows[0][2:] if lows else None
    if low is None or _version_tuple(low) < _version_tuple(floor):
        low = floor
    return ",".join([f">={low}", *rest])


def _evidence_words(use: dict) -> str:
    status = use.get("status")
    if status == "below_floor":
        from .compendium import SUPPORTED_FLOORS
        name, _, installed = str(use.get("library", "")).partition(" ")
        return (f"{name} {installed} is below the supported floor "
                f"{SUPPORTED_FLOORS.get(name)}")
    if status == "outside":
        return (f"outside its versions {use.get('versions')} for "
                f"{use.get('library')}")
    return f"verified: {status}"


class RowBook:
    """Intent:
        The definition rows of the project at `root` (the project
        `compendium.install` registered when None, or the bundled files
        alone when none is), read per key on demand: `rows(key)` the
        usable ones (`Row`), `withheld(key)` why a key's rows may not
        be used, `states(key)` whether the key has any definition row.
    """

    def __init__(self, root: "str | None" = None):
        from .compendium import load_library_claims
        self.root = root if root is not None else _installed_root()
        self._library = _library_claims(self.root, load_library_claims)
        self._rows: dict = {}
        self._withheld: dict = {}
        self._unusable: dict = {}

    def states(self, key: str) -> bool:
        info = self._library.get(key)
        return info is not None and any(
            isinstance(r, dict) and is_definition_name(r.get("name"))
            for r in info["entry"].get("claims") or [])

    def rows(self, key: str) -> list:
        if key not in self._rows:
            self._read(key)
        return self._rows[key]

    def unusable(self, key: str) -> list:
        """Each definition row of `key` that may not feed a proof, as
        `<row>: <reason>`, whether or not another row may."""
        if key not in self._rows:
            self._read(key)
        return list(self._unusable.get(key) or [])

    def withheld(self, key: str) -> "str | None":
        if key not in self._rows:
            self._read(key)
        return self._withheld.get(key)

    def _read(self, key: str) -> None:
        from .compendium import _installed_version
        out: list = []
        why = None
        from .compendium import ROW_SOURCE, ROW_VERSIONS, row_is_bundled
        info = self._library.get(key)
        for row in (info or {}).get("entry", {}).get("claims") or []:
            if not isinstance(row, dict) \
                    or not is_definition_name(row.get("name")):
                continue
            # each row stands on the file it comes from: a project row
            # replacing a bundled one is the project's testimony
            meta = row.get("meta") or {}
            bundled = (row_is_bundled(row) if meta.get(ROW_SOURCE)
                       else info["bundled"])
            file_versions = meta.get(ROW_VERSIONS) or info.get("versions")
            source = meta.get(ROW_SOURCE) or info["source"]
            status, reason = row_standing(self.root, key, row, bundled,
                                          file_versions)
            if status is None:
                why = why or f"{row.get('name')}: {reason}"
                self._unusable.setdefault(key, []).append(
                    f"{row.get('name')}: {reason}")
                continue
            parsed = _parse_row(key, row)
            if parsed is None:
                if " ~= " in f" {row.get('statement') or ''} ":
                    reason = (f"definition rows are equations, and {key}'s row "
                              f"is written with ~=, so it is not used as one")
                    self._unusable.setdefault(key, []).append(
                        f"{row.get('name')}: {reason}")
                    why = why or f"{row.get('name')}: {reason}"
                    continue
                why = why or (f"{row.get('name')}: its statement is not "
                              f"f(...) == <expression>")
                continue
            params, rhs, pins, premises, ranks = parsed
            version = _installed_version(info["compendium"]) or "*"
            standing, trusted_by = _standing(row, status, bundled)
            from .compendium import below_floor
            if standing == "axiom" and trusted_by == "mathema" \
                    and below_floor(info["compendium"], version):
                status = "below_floor"
                standing, trusted_by = "evidence", None
            out.append(Row(
                key=key, name=str(row["name"]),
                statement=str(row.get("statement")), source=source,
                status=status, library=f"{info['compendium']} {version}",
                params=params, rhs=rhs, pins=pins, premises=premises,
                ranks=ranks, standing=standing, trusted_by=trusted_by,
                versions=str(row.get("versions") or file_versions or "*"),
                installed=version))
        self._rows[key] = out
        if why and not out:
            self._withheld[key] = why


_LIBRARY_CACHE: dict = {}


def _library_claims(root: "str | None", load) -> dict:
    """`load(root)`, read again only when a claims file under `root`
    (or a bundled one) has changed since the last read."""
    from .compendium import _bundled_dir
    from .spec import claims_file_paths
    paths = claims_file_paths(_bundled_dir())
    if root is not None:
        paths += claims_file_paths(root, exclude=(_bundled_dir(),))
    stamp = []
    for path in paths:
        try:
            stamp.append((path, os.path.getmtime(path)))
        except OSError:
            continue
    cached = _LIBRARY_CACHE.get(root)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    loaded = load(root)
    _LIBRARY_CACHE[root] = (stamp, loaded)
    return loaded


# reading a body through the rows

def _substitute(node: ast.expr, names: dict) -> ast.expr:
    """A copy of `node` with each bare name in `names` replaced by a
    copy of its expression."""
    class _Sub(ast.NodeTransformer):
        def visit_Name(self, n):
            if n.id in names:
                return copy.deepcopy(names[n.id])
            return n
    out = _Sub().visit(copy.deepcopy(node))
    return ast.fix_missing_locations(out)


def _literal(node):
    """The literal value of an argument, or a unique marker when it is
    not a literal."""
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return _NOT_LITERAL


_NOT_LITERAL = object()


def _match_row(key: str, rows: list, positional: list, keywords: dict):
    """Intent:
        The first row of `rows` that states the call `key(*positional,
        **keywords)` (argument source nodes), with the row's names
        bound: `(row, rhs, premises)`, the right-hand side and premises
        with each name the row's `f(...)` takes replaced by the call's
        argument. None when no row covers the call.

    Notes:
        A row covers a call when every parameter the row's `f(...)`
        takes is passed, and every other parameter is passed a literal
        equal to the row's pin for it, or else to its default; a
        parameter the call leaves out must be at the row's pin too.
    """
    import inspect

    from ._signatures import callable_signature
    from .conjecture import _resolve_func_ref
    target = _resolve_func_ref(key)
    if target is None:
        return None
    try:
        sig = callable_signature(target)
        bound = sig.bind(*positional, **keywords)
    except (TypeError, ValueError):
        return None
    passed = dict(bound.arguments)
    extra: dict = {}
    for name, param in sig.parameters.items():
        if param.kind is param.VAR_KEYWORD:
            extra = dict(passed.pop(name, None) or {})
        if param.kind is param.VAR_POSITIONAL and passed.get(name):
            return None
    for row in sorted(rows, key=lambda r: (r.name != DEFINITION, r.name)):
        if any(p not in passed for p in row.params):
            continue
        ok = True
        for name, param in sig.parameters.items():
            if name in row.params or param.kind in (param.VAR_KEYWORD,
                                                    param.VAR_POSITIONAL):
                continue
            want = row.pins.get(name, param.default)
            if want is inspect.Parameter.empty:
                ok = False
                break
            got = _literal(passed[name]) if name in passed else \
                param.default
            if got is _NOT_LITERAL or not _same_value(got, want):
                ok = False
                break
        # a keyword only **kwargs takes must be the row's pin, and a pin
        # on no named parameter must be passed
        if ok and any(p not in sig.parameters and p not in extra
                      for p in row.pins):
            ok = False
        if ok and any(name not in row.pins
                      or _literal(node) is _NOT_LITERAL
                      or not _same_value(_literal(node), row.pins[name])
                      for name, node in extra.items()):
            ok = False
        accepts = set(sig.parameters) | (set(extra) | set(row.pins)
                                         if any(p.kind is p.VAR_KEYWORD for p
                                                in sig.parameters.values())
                                         else set())
        if not ok or any(p not in accepts for p in row.pins):
            continue
        names = {p: passed[p] for p in row.params}
        premises = [(_substitute(lhs, names), rel, _substitute(rhs, names))
                    for lhs, rel, rhs in row.premises]
        return row, _substitute(row.rhs, names), premises
    return None


def _same_value(a, b) -> bool:
    if a is b:
        return True
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        return a is b or a == b and type(a) is type(b)
    try:
        return a == b
    except Exception:
        return False


def inline_body(fn, facts, book: RowBook) -> "Inlined | None":
    """Intent:
        `fn`'s body read in grammar words: its straight-line
        assignments substituted into its one `return`, each library
        call it makes rewritten with a definition row, the scalar
        functions of the lift table (`np.sqrt`) and the builtins `abs`,
        `sum`, `len`, `min`, `max` read as the grammar words of the same
        name, and `float(x)` as `x`. None when the body uses no
        definition row at all.

    Raises:
        Decline: a construct outside the rewrite, or a library call
            with no usable definition row (naming its key, and why a
            row it has is withheld).
    """
    from .analysis import _MATH_MODULES
    from ._math_vocab import _SYMPY_FUNCS
    from .compendium import _alias_origins
    fdef = getattr(facts, "tree", None)
    if fdef is None:
        raise Decline("the function has no source")
    origins = _alias_origins(fn, facts)
    scope = module_scope(fn)
    params = set(facts.params)
    typing = _Typing(facts, book)
    local: dict = {}
    inlined = Inlined(expr=ast.Constant(value=0))

    def no_row(key: str) -> Decline:
        why = book.withheld(key)
        return Decline(f"{key} has no definition row"
                       + (f" usable here ({why})" if why else ""))

    receiver_type = typing.of

    def through_row(key: str, positional: list, keywords: dict):
        rows = book.rows(key)
        found = _match_row(key, rows, positional, keywords)
        if found is None:
            if rows:
                unusable = book.unusable(key)
                raise Decline(f"{key}: no definition row states this call "
                              f"({', '.join(r.name for r in rows)} "
                              f"take other arguments"
                              + (f"; not usable here: {'; '.join(unusable)}"
                                 if unusable else "") + ")")
            raise no_row(key)
        row, rhs, premises = found
        inlined.uses.append(row)
        inlined.premises.extend((row, p) for p in premises)
        return rhs

    def dotted(node) -> "str | None":
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        parts.append(node.id)
        return ".".join(reversed(parts))

    def rewrite(node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) \
                    and not isinstance(node.value, bool):
                return ast.Constant(value=node.value)
            raise Decline(f"the constant {node.value!r} is not a number")
        if isinstance(node, ast.Name):
            if node.id in local:
                return copy.deepcopy(local[node.id])
            if node.id in params:
                return ast.Name(id=node.id, ctx=ast.Load())
            value = scope.get(node.id)
            if isinstance(value, (int, float)) and not isinstance(value,
                                                                  bool):
                return ast.Constant(value=value)
            raise Decline(f"the name {node.id!r} is not a parameter, a "
                          f"local or a numeric module constant")
        if isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
                          ast.MatMult)):
            return ast.BinOp(left=rewrite(node.left), op=node.op,
                             right=rewrite(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub,
                                                                  ast.UAdd)):
            return ast.UnaryOp(op=node.op, operand=rewrite(node.operand))
        if column_read(node, typing.tables) is not None:
            return copy.deepcopy(node)
        if isinstance(node, ast.Attribute):
            rt = receiver_type(node.value)
            if rt is None:
                raise Decline(f"{ast.unparse(node)!r}: the attribute's "
                              f"receiver has no runtime type")
            return through_row(f"{rt}.{node.attr}", [rewrite(node.value)],
                               {})
        if isinstance(node, ast.Call):
            if any(k.arg is None for k in node.keywords) or any(
                    isinstance(a, ast.Starred) for a in node.args):
                raise Decline(f"{ast.unparse(node)!r}: argument unpacking "
                              f"is outside the rewrite")
            args = [rewrite(a) for a in node.args]
            keywords = {k.arg: rewrite(k.value) if not isinstance(
                            k.value, ast.Constant) else k.value
                        for k in node.keywords}
            func = node.func
            if isinstance(func, ast.Attribute):
                rt = receiver_type(func.value)
                if rt is not None:
                    return through_row(f"{rt}.{func.attr}",
                                       [rewrite(func.value), *args],
                                       keywords)
                name = dotted(func)
                if name is None:
                    raise Decline(f"{ast.unparse(node)!r}: the call's "
                                  f"receiver has no runtime type")
                head, _, rest = name.partition(".")
                base = origins.get(head)
                if base is None:
                    raise Decline(f"{ast.unparse(node)!r}: {head!r} is not "
                                  f"an imported module")
                key = f"{base}.{rest}"
                if book.states(key):
                    return through_row(key, args, keywords)
                if head in _MATH_MODULES and rest in _SYMPY_FUNCS \
                        and not keywords:
                    return ast.Call(func=ast.Name(id=rest, ctx=ast.Load()),
                                    args=args, keywords=[])
                raise no_row(key)
            if isinstance(func, ast.Name):
                key = origins.get(func.id)
                if key is not None and "." in key:
                    if book.states(key):
                        return through_row(key, args, keywords)
                    raise no_row(key)
                if func.id in _BUILTIN_WORDS and func.id not in scope \
                        and not keywords:
                    if func.id == "float" and len(args) == 1:
                        return args[0]
                    return ast.Call(func=ast.Name(id=func.id, ctx=ast.Load()),
                                    args=args, keywords=[])
            raise Decline(f"{ast.unparse(node)!r} is outside the "
                          f"definition rewrite")
        raise Decline(f"{ast.unparse(node)!r} is outside the definition "
                      f"rewrite")

    for node in ast.walk(fdef):
        # a method or attribute of a parameter with a runtime type names
        # its library key; one with no definition row is reported by
        # that key, wherever in the body it sits
        if isinstance(node, ast.Attribute) \
                and isinstance(node.value, ast.Name) \
                and receiver_type(node.value) is not None:
            key = f"{receiver_type(node.value)}.{node.attr}"
            if not book.states(key):
                raise no_row(key)
    body = list(fdef.body)
    if body and isinstance(body[0], ast.Expr) \
            and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    result = None
    for stmt in body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                and isinstance(stmt.targets[0], ast.Name):
            target, value = stmt.targets[0].id, stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None \
                and isinstance(stmt.target, ast.Name):
            target, value = stmt.target.id, stmt.value
        elif isinstance(stmt, ast.Return) and stmt.value is not None:
            result = rewrite(stmt.value)
            break
        else:
            raise Decline(f"line {getattr(stmt, 'lineno', '?')}: "
                          f"{type(stmt).__name__} is outside the "
                          f"definition rewrite (straight-line assignments "
                          f"and one return)")
        found = receiver_type(value)
        if found is not None:
            typing.local[target] = found
        local[target] = rewrite(value)
    if result is None:
        raise Decline("the body has no return")
    if not inlined.uses:
        return None
    inlined.expr = ast.fix_missing_locations(result)
    return inlined


def inline_claim(side: str, fn, facts, inlined: Inlined,
                 premises: "list | None" = None) -> ast.expr:
    """Intent:
        One side of a claim with each call `f(...)` replaced by the
        inlined body, the call's arguments substituted for the
        parameters (positionally, then by keyword, then each unpassed
        parameter at a literal default). Each premise a used row
        carries is appended to `premises`, instantiated at that call,
        as `(row, (lhs, relation, rhs))`.

    Raises:
        Decline: a call of `f` whose arguments do not bind.
    """
    import inspect

    from ._signatures import callable_signature
    try:
        sig = callable_signature(fn)
    except (TypeError, ValueError):
        sig = None
    tree = ast.parse(side, mode="eval").body

    class _Inline(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            if not (isinstance(node.func, ast.Name) and node.func.id == "f"):
                return node
            names = list(facts.params)
            if len(node.args) > len(names):
                raise Decline(f"{ast.unparse(node)!r} passes more arguments "
                              f"than f takes")
            bound = dict(zip(names, node.args))
            for k in node.keywords:
                if k.arg not in names or k.arg in bound:
                    raise Decline(f"{ast.unparse(node)!r}: {k.arg!r} does "
                                  f"not bind")
                bound[k.arg] = k.value
            for p in names:
                if p in bound:
                    continue
                param = sig.parameters.get(p) if sig is not None else None
                if param is None or param.default is inspect.Parameter.empty \
                        or not isinstance(param.default, (int, float)) \
                        or isinstance(param.default, bool):
                    raise Decline(f"{ast.unparse(node)!r} leaves {p!r} "
                                  f"unbound")
                bound[p] = ast.Constant(value=param.default)
            if premises is not None:
                for row, (lhs, rel, rhs) in inlined.premises:
                    premises.append((row, (_substitute(lhs, bound), rel,
                                           _substitute(rhs, bound))))
            return _substitute(inlined.expr, bound)

    return ast.fix_missing_locations(_Inline().visit(tree))


def called_keys(fn, facts, root: "str | None" = None) -> set:
    """Intent:
        Every library key `fn`'s body reaches: a method or attribute
        of a value with a runtime type (`returns.std(...)` on a
        `pandas.Series` is `pandas.Series.std`, `A.T` on an array is
        `numpy.ndarray.T`, `(df.w * df.r).sum()` on a
        `pandas.DataFrame`'s columns is `pandas.Series.sum`), and a
        function called through an import alias (`np.mean` is
        `numpy.mean`).
    """
    from .compendium import _resolve_called_keys
    tree = getattr(facts, "tree", None)
    out = set(_resolve_called_keys(fn, facts))
    if tree is None:
        return out
    typing = _Typing(facts, RowBook(root))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) \
                and column_read(node, typing.tables) is None:
            rt = typing.of(node.value)
            if rt is not None:
                out.add(f"{rt}.{node.attr}")
    return out


def definition_state(fn, facts, root: "str | None" = None) -> dict:
    """Intent:
        The definition rows `fn`'s body could be read through, as a
        record stamps them for freshness: `{key: [text, ...]}` for each
        library key the body reaches that has definition rows, each
        usable row as `<name>: <status> (<library> <version>)`, or
        `withheld: <reason>` when none may be used. A row verified,
        falsified, re-stated or moved out of its library's version since
        the stamp changes it, and the record is re-adjudicated.
    """
    book = RowBook(root)
    out: dict = {}
    for key in sorted(called_keys(fn, facts, root)):
        if not book.states(key):
            continue
        rows = book.rows(key)
        out[key] = ([f"{r.name}: {r.status} ({r.library})" for r in rows]
                    or [f"withheld: {book.withheld(key)}"])
    return out


# deciding the rewritten claim

def _transform_kinds(funcs: dict) -> dict:
    """The claim's bound functions that are law transforms the
    sequence lowering reads, `{name: "scale" | "shift" | "reverse"}`."""
    out = {}
    for name, ref in (funcs or {}).items():
        dotted = ref if isinstance(ref, str) else (
            f"{getattr(ref, '__module__', '')}."
            f"{getattr(ref, '__qualname__', '')}")
        kind = _TRANSFORMS.get(dotted)
        if kind is not None:
            out[name] = kind
    return out


def _premise_text(lhs, rel, rhs) -> str:
    return f"{ast.unparse(lhs)} {rel} {ast.unparse(rhs)}"


def _stated(premise: tuple, assumption) -> bool:
    """Whether a premise `(lhs, relation, rhs)` of source nodes is one
    the claim states, compared as normalised source."""
    want = _premise_text(*premise)
    for lhs, rel, rhs in assumption or ():
        try:
            text = _premise_text(ast.parse(str(lhs), mode="eval").body, rel,
                                 ast.parse(str(rhs), mode="eval").body)
        except SyntaxError:
            continue
        if text == want:
            return True
    return False


def _uses_meta(uses: list) -> list:
    out: list = []
    for row in uses:
        entry = row.use()
        if entry not in out:
            out.append(entry)
    return out


def _rows_text(uses: list) -> str:
    """`the polars.Series.sum definition row`, or several joined."""
    names = list(dict.fromkeys(f"{r.key} {r.name}" for r in uses))
    if len(names) == 1:
        return f"the {names[0]} row"
    return "the " + ", ".join(names[:-1]) + f" and {names[-1]} rows"


def prove_through_definitions(cj, fn, facts, cj_domain: dict, assumption,
                              structures: "dict | None" = None,
                              extensive: bool = False):
    """Intent:
        Decide a claim about `fn` by rewriting its body through
        definition rows (see the module docstring). Returns a
        `ProofResult`: `proven`, `disproven` with an executed witness
        (a point where `fn` has no value inside the claim's domain), or
        `undecided`/`unliftable` with the reason; None when the route
        does not apply (a scalar function, a body using no definition
        row).
    """
    from .symbolic._proof_support import ProofResult
    if cj.relation not in ("==", "~=", "<", "<=", ">", ">=") \
            or cj.negated or cj.links or not cj.rhs:
        return None
    if getattr(facts, "tree", None) is None or facts.loops \
            or facts.branch_count or facts.recursion:
        return None
    if not any("f(" in (s or "") for s in (cj.lhs, cj.rhs)):
        return None
    arrays = any(k in ("vec", "mat") for k in facts.param_kinds.values()) \
        or any(getattr(b, "dims", ()) for b in (cj_domain or {}).values())
    if not arrays:
        return None
    try:
        book = RowBook()
        inlined = inline_body(fn, facts, book)
    except TimeoutError:
        raise
    except Decline as e:
        return ProofResult("unliftable", sketch=str(e))
    if inlined is None:
        return None
    row_premises: list = []
    try:
        lhs = inline_claim(cj.lhs, fn, facts, inlined, row_premises)
        rhs = inline_claim(cj.rhs, fn, facts, inlined, row_premises)
    except Decline as e:
        return ProofResult("unliftable", sketch=str(e))
    meta = {"mathema.derive_route": "definitions",
            "mathema.definitions": _uses_meta(inlined.uses)}
    from .symbolic import matrix_param_dims
    from .types import shapes_from_signature
    shapes = shapes_from_signature(fn)
    if matrix_param_dims(cj_domain, shapes):
        return _matrix_route(cj, facts, cj_domain, shapes, assumption,
                             structures, fn, lhs, rhs, row_premises,
                             inlined, meta)
    return _sequence_route(cj, fn, facts, cj_domain, shapes, assumption,
                           extensive, lhs, rhs, row_premises, inlined, meta)


def _matrix_route(cj, facts, cj_domain, shapes, assumption, structures, fn,
                  lhs, rhs, row_premises, inlined, meta):
    """The rewritten claim decided by the matrix algebra."""
    from .symbolic import try_prove_matrix
    from .symbolic._proof_support import ProofResult
    from .types import structures_from_signature
    vector_rows = [r for r in inlined.uses
                   if any(k == 1 for k in r.ranks.values())]
    if vector_rows:
        row = vector_rows[0]
        return ProofResult(
            "undecided", meta=dict(meta),
            sketch=f"the definition row {row.key} {row.name} is stated over "
                   f"vectors, and this claim is about matrices")
    for row, premise in row_premises:
        if not _stated(premise, assumption):
            text = _premise_text(*premise)
            return ProofResult(
                "undecided",
                sketch=f"the definition row {row.key} {row.name} holds "
                       f"where {text}, which the claim does not state "
                       f"(assuming {text})", meta=dict(meta))
    lhs_text, rhs_text = ast.unparse(lhs), ast.unparse(rhs)
    structs = dict(structures_from_signature(fn))
    for p, props in (structures or {}).items():
        structs[p] = tuple(sorted(set(structs.get(p, ())) | set(props)))
    through = (f"through {_rows_text(inlined.uses)} the "
               f"claim reads {lhs_text} {cj.relation} {rhs_text}")
    mproof = try_prove_matrix(lhs_text, rhs_text, cj.relation, facts,
                              cj_domain, shapes, structs,
                              premises=assumption)
    if mproof is not None and mproof.status == "proven":
        return ProofResult("proven", sketch=f"{through}: {mproof.sketch}",
                           meta=dict(meta))
    why = (mproof.sketch if mproof is not None and mproof.sketch
           else "the matrix algebra did not close it")
    return ProofResult("undecided", sketch=f"{through}, and {why}",
                       meta=dict(meta))


def _names_in(trees) -> set:
    """Every bare name the trees read as a value (not in call
    position)."""
    out: set = set()
    for tree in trees:
        calls = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        out |= {n.id for n in ast.walk(tree)
                if isinstance(n, ast.Name) and id(n) not in calls}
    return out


def _called_names(trees) -> set:
    return {n.func.id for tree in trees for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def _length_premise(a, b, rel: str, lengths: set):
    """`(L, least)` when `a rel b` states that the length `L` is at
    least `least` (`dim(x) >= 2`, `len(x) > 1`, `dim(x) == 3`), else
    None."""
    import math
    if rel in ("<", "<="):
        a, b = b, a
        rel = ">" if rel == "<" else ">="
    if rel not in (">", ">=", "=="):
        return None
    if a in lengths and getattr(b, "is_number", False) and b.is_real:
        least = float(b)
        least = math.floor(least) + 1 if rel == ">" else math.ceil(least)
        return a, max(int(least), 1)
    return None


def _exact_length(a, b, rel: str, lengths: set):
    """`(L, k)` when `a rel b` fixes the length `L` to the whole number
    `k` (`dim(x) == 0`, `len(x) == 3`), else None."""
    if rel != "==":
        return None
    for length, number in ((a, b), (b, a)):
        if length in lengths and getattr(number, "is_number", False) \
                and number.is_real and int(number) == number:
            return length, int(number)
    return None


def _implied_nonzero(expr, provided: list, min_length: dict,
                     bases: "dict | None" = None) -> bool:
    """Intent:
        Whether `expr != 0` follows from the lengths being at least
        `min_length` and each quantity in `provided` being nonzero:
        `expr` is nonzero by its own assumptions (a positive symbol, a
        length at least one more than the offset it is taken from), or
        its ratio to a provided quantity is.
    """
    import sympy

    from .symbolic._seqir import normalised
    shift = {L: sympy.Symbol(f"_M_{L}", integer=True, positive=True) + (k - 1)
             for L, k in min_length.items() if k > 1}

    def at_lengths(e):
        return e.xreplace(shift) if shift else e
    lengths = {ib: at_lengths(L) for ib, L in (bases or {}).items()}

    def nonzero(e) -> bool:
        if e.is_nonzero:
            return True
        return all(f.is_nonzero or (isinstance(f, sympy.Pow)
                                    and f.base.is_nonzero)
                   for f in sympy.Mul.make_args(sympy.factor_terms(e)))
    target = at_lengths(expr)
    if nonzero(normalised(target, lengths)):
        return True
    for p in provided:
        p = at_lengths(p)
        for ratio in (target / p, target ** 2 / p ** 2):
            if nonzero(normalised(ratio, lengths)):
                return True
    return False


def _columns_as_names(tree, tables: set):
    """A copy of `tree` with each column read of a table in `tables`
    (`df.w`, `df["w"]`) replaced by the name `df.w`, which the
    sequence lowering reads as a vector of its own."""
    class _Columns(ast.NodeTransformer):
        def visit_Attribute(self, node):
            name = column_read(node, tables)
            if name is not None:
                return ast.Name(id=f"{node.value.id}.{name}", ctx=ast.Load())
            return self.generic_visit(node)

        def visit_Subscript(self, node):
            name = column_read(node, tables)
            if name is not None:
                return ast.Name(id=f"{node.value.id}.{name}", ctx=ast.Load())
            return self.generic_visit(node)
    return ast.fix_missing_locations(_Columns().visit(copy.deepcopy(tree)))


def _element_bound(bound):
    """The domain one element of a vector (or one column of a table)
    is drawn from: the claim's bound on it without its axes, or None
    when the claim states none."""
    import dataclasses

    from .domain import Domain
    if isinstance(bound, Domain) and bound.dims:
        return dataclasses.replace(bound, dims=())
    return None


def _element_sign(element) -> dict:
    """The sign assumptions an element bound entails, for the
    sequence's `IndexedBase`."""
    from .domain import bound_assumptions
    if element is None:
        return {}
    kwargs = dict(bound_assumptions(element) or {})
    return {k: v for k, v in kwargs.items()
            if k in ("positive", "negative", "nonnegative", "nonpositive")}


def _element_text(element) -> str:
    """An element bound as a proof's quantifier shows it: `ℝ`, or the
    one interval every element lies in."""
    pieces = getattr(element, "pieces", ()) or ()
    if not pieces:
        return "ℝ"
    if len(pieces) == 1 and isinstance(pieces[0], (tuple, list)) \
            and not isinstance(pieces[0], frozenset):
        lo, hi = pieces[0]
        return (f"{'[' if getattr(pieces[0], 'closed_lo', True) else '('}"
                f"{lo}, {hi}"
                f"{']' if getattr(pieces[0], 'closed_hi', True) else ')'}")
    return "their declared domain"


def _over(seqs: dict, elements: dict) -> str:
    """The vectors a proof covers, grouped by the bound on their
    elements: `returns over [-0.1, 0.1]`, `w, r over [0.0, 1.0]`."""
    groups: dict = {}
    for name, (base, _length) in sorted(seqs.items()):
        groups.setdefault(_element_text(elements.get(base)), []).append(name)
    return ", ".join(f"{', '.join(names)} over {text}"
                     for text, names in groups.items())


def lengths_of(seqs: dict) -> list:
    """The distinct length symbols of the lowered sequences, in the
    order first met."""
    return list(dict.fromkeys(length for _ib, length in seqs.values()))


def _sequence_route(cj, fn, facts, cj_domain, shapes, assumption, extensive,
                    lhs, rhs, row_premises, inlined, meta):
    """The rewritten claim decided over sequences of symbolic length:
    lowered by `symbolic._seqir`, its definedness obligations checked
    against the claim's premises, and the relation decided on the
    normalised sums."""
    import sympy

    from . import linalg
    from ._timeout import (EXTENSIVE_TIMEOUT_SECONDS, FAST_TIMEOUT_SECONDS,
                           _with_timeout)
    from .domain import InvalidDomain
    from .symbolic._base import NotSymbolic
    from .symbolic._proof_support import (ProofResult, _domain_assumptions,
                                          _prove_relation)
    from .symbolic._seqir import (Bounds, Lowering, Obligations, Vec,
                                  normalised, order_by_bounds)
    claim_premises = []
    for a_lhs, rel, a_rhs in assumption or ():
        try:
            claim_premises.append((ast.parse(str(a_lhs), mode="eval").body,
                                   rel,
                                   ast.parse(str(a_rhs), mode="eval").body))
        except SyntaxError:
            return ProofResult("unliftable", sketch=f"the premise {a_lhs} "
                               f"{rel} {a_rhs} does not parse", meta=meta)
    ranks = linalg.array_ranks(cj_domain, shapes, facts.param_kinds)
    tables = {n for n, r in ranks.items() if r == "table"} \
        | {n for n, k in facts.param_kinds.items() if k == "table"}
    if tables:
        lhs, rhs = _columns_as_names(lhs, tables), _columns_as_names(rhs,
                                                                     tables)
        claim_premises = [(_columns_as_names(a, tables), rel,
                           _columns_as_names(b, tables))
                          for a, rel, b in claim_premises]
        row_premises = [(row, (_columns_as_names(a, tables), rel,
                               _columns_as_names(b, tables)))
                        for row, (a, rel, b) in row_premises]
    trees = [lhs, rhs] + [t for p in claim_premises for t in (p[0], p[2])] \
        + [t for _row, p in row_premises for t in (p[0], p[2])]
    transforms = _transform_kinds(cj.funcs)
    other = sorted((set(cj.funcs or ()) - set(transforms))
                   & _called_names(trees))
    if other:
        return ProofResult(
            "unliftable", meta=meta,
            sketch=f"the bound function(s) {', '.join(other)} are not law "
                   f"transforms the sequence lowering reads (scale_seq, "
                   f"shift_seq, reverse_seq)")
    matrix_rows = [r for r in inlined.uses
                   if any(k == 2 for k in r.ranks.values())]
    if matrix_rows:
        row = matrix_rows[0]
        return ProofResult(
            "unliftable", meta=meta,
            sketch=f"the definition row {row.key} {row.name} is stated over "
                   f"matrices, outside the sequence lowering")
    names = _names_in(trees)
    seqs: dict = {}
    lengths: dict = {}
    elements: dict = {}
    fixed_lengths: dict = {}
    for n in sorted(names):
        table = n.split(".", 1)[0] if "." in n else None
        r = 1 if table in tables else ranks.get(n)
        if r in (2, "table"):
            return ProofResult("unliftable", meta=meta,
                               sketch=f"{n} is a matrix or a table, outside "
                                      f"the sequence lowering")
        if r == 1:
            # a column's own binding (`for df.w in [0, 1]^n`) before
            # the table's (`for df in [0, 1]^n`)
            bound = cj_domain.get(n) if n in cj_domain \
                else cj_domain.get(table or n)
            dims = getattr(bound, "dims", ()) or ()
            dim = str(dims[0]) if dims else (table or n)
            length = lengths.setdefault(dim, sympy.Symbol(
                f"L_{dim}", integer=True, positive=True))
            if dim.isdigit():
                # a literal dimension (`R^0`, `R^3`) fixes the length
                fixed_lengths[length] = int(dim)
            element = _element_bound(bound)
            base = sympy.IndexedBase(n, real=True,
                                     **_element_sign(element))
            seqs[n] = (base, length)
            elements[base] = element
    scalars = {n: sympy.Symbol(n, real=True)
               for n in names - set(seqs) - set(transforms) - {"pi"}}
    try:
        _subs, context, assumed, pins = _domain_assumptions(scalars,
                                                            cj_domain)
    except InvalidDomain as e:
        return ProofResult("unliftable", meta=meta,
                           sketch=f"declared domain is not projectable: {e}")
    length_symbols = set(lengths.values())
    by_length = {}
    for n, (_ib, length) in seqs.items():
        by_length.setdefault(length, n)

    bounds = Bounds(elements)

    def lower(node, into: Obligations):
        low = Lowering(seqs, dict(assumed), transforms, bounds)
        value = low.lower(node)
        into.merge(low.obligations)
        if pins:
            value = (Vec(value.elem.subs(pins), value.length)
                     if isinstance(value, Vec) else value.subs(pins))
        return value

    empty_only = [False]

    def decide():
        required, provided = Obligations(), Obligations()
        known_lengths = dict(fixed_lengths)
        lv = lower(lhs, required)
        rv = lower(rhs, required)
        provided_nonzero: list = []
        facts_q = [] if context is None else [context]
        for p_lhs, rel, p_rhs in claim_premises:
            own = Obligations()
            try:
                a, b = lower(p_lhs, own), lower(p_rhs, own)
            except NotSymbolic:
                continue
            provided.merge(own)
            provided_nonzero.extend(e for e, _t in own.nonzero)
            if isinstance(a, Vec) or isinstance(b, Vec):
                continue
            exact = _exact_length(a, b, rel, length_symbols)
            if exact is not None:
                known_lengths[exact[0]] = exact[1]
            as_length = _length_premise(a, b, rel, length_symbols)
            if as_length is not None:
                provided.need_length(*as_length)
                continue
            gap = a - b
            if rel in (">", "<", "!="):
                provided_nonzero.append(gap)
            for side, other, above in ((a, b, rel in (">", ">=")),
                                       (b, a, rel in ("<", "<="))):
                # a quantity above a nonnegative bound, strictly above
                # zero, is nonzero (and below a nonpositive one)
                if above and other.is_number and (
                        other.is_positive or (other.is_zero
                                              and rel in (">", "<"))):
                    provided_nonzero.append(side)
            for side, other, below in ((a, b, rel in ("<", "<=")),
                                       (b, a, rel in (">", ">="))):
                if below and other.is_number and (
                        other.is_negative or (other.is_zero
                                              and rel in (">", "<"))):
                    provided_nonzero.append(side)
            if rel in ("<", "<="):
                gap = -gap
            facts_q.append(sympy.Q.positive(gap) if rel in (">", "<")
                           else sympy.Q.nonnegative(gap) if rel in (">=",
                                                                    "<=")
                           else sympy.Q.nonzero(gap) if rel == "!="
                           else sympy.Q.zero(gap))
        unstated: list = []
        for row, (p_lhs, rel, p_rhs) in row_premises:
            own = Obligations()
            a, b = lower(p_lhs, own), lower(p_rhs, own)
            as_length = None
            if not (isinstance(a, Vec) or isinstance(b, Vec)):
                as_length = _length_premise(a, b, rel, length_symbols)
            if as_length is not None:
                required.need_length(*as_length)
            elif not _stated((p_lhs, rel, p_rhs), assumption):
                unstated.append((row, _premise_text(p_lhs, rel, p_rhs)))
        unmet: list = []
        for length, least in sorted(required.min_length.items(), key=str):
            have = known_lengths.get(length,
                                     provided.min_length.get(length, 1))
            if have < least:
                unmet.append(("length", length, least, have))
        for length, fixed in sorted(known_lengths.items(), key=str):
            # a domain or premise that fixes the length at 0 names the
            # empty vector, where a division by the length has no value
            if fixed == 0 and not any(item[0] == "length" and item[1] == length
                                      for item in unmet):
                unmet.append(("length", length, 1, 0))
        for expr, text in required.nonzero:
            if not _implied_nonzero(expr, provided_nonzero,
                                    {L: max(provided.min_length.get(L, 1), k)
                                     for L, k in required.min_length.items()},
                                    {ib: L for ib, L in seqs.values()}):
                unmet.append(("nonzero", expr, text,
                              max(provided.min_length.values() or [1])))
        # only the empty vector unmet: the relation is decided for every
        # length of at least one, and the empty vector is left to sampling
        empty_only[0] = bool(unmet) and not unstated and all(
            item[0] == "length" and item[2] == 1 for item in unmet)
        if (unstated or unmet) and not empty_only[0]:
            return {"unmet": unmet, "unstated": unstated}
        if not empty_only[0]:
            shortest.update(required.min_length)
        rel = cj.relation
        if isinstance(lv, Vec) or isinstance(rv, Vec):
            if not (isinstance(lv, Vec) and isinstance(rv, Vec)) \
                    or rel not in ("==", "~=") or lv.length != rv.length:
                return {"undecided": "a vector compared with a number, or "
                                     "ordered, has no reading here"}
            diff = normalised(lv.elem - rv.elem, {ib: L for ib, L
                                                  in seqs.values()})
            return {"proven": diff == 0, "diff": diff}
        if rel in ("==", "~="):
            diff = normalised(lv - rv, {ib: L for ib, L in seqs.values()})
            return {"proven": diff == 0, "diff": diff}
        bases = {ib: L for ib, L in seqs.values()}
        q = sympy.And(*facts_q) if len(facts_q) > 1 else (
            facts_q[0] if facts_q else None)
        scalar_domain = {n: cj_domain[n] for n in assumed if n in cj_domain}
        by_bounds = order_by_bounds(
            lv, rv, rel, bounds, bases,
            {"params": assumed, "domain": scalar_domain, "q": q},
            extensive=extensive)
        if by_bounds is not None:
            status, why = by_bounds
            return {"proven": status == "proven", "bounds": True,
                    "result": ProofResult(
                        "proven" if status == "proven" else "undecided",
                        sketch=why)}
        result = _prove_relation(normalised(lv, bases), normalised(rv, bases),
                                 rel, scalar_domain, q, assumed,
                                 extensive=extensive)
        return {"proven": result.status == "proven", "result": result}

    shortest: dict = {}
    cap = EXTENSIVE_TIMEOUT_SECONDS if extensive else FAST_TIMEOUT_SECONDS
    through = f"through {_rows_text(inlined.uses)}"
    try:
        outcome = _with_timeout(decide, cap)
        if empty_only[0] and outcome.get("proven"):
            outcome = {"empty": True}
    except TimeoutError:
        return ProofResult(
            "undecided", sketch=f"{through}, the sequence lowering "
                                f"exceeded the wall-clock cap",
            meta={**meta, "mathema.timeout":
                  "extensive" if extensive else "fast"})
    except NotSymbolic as e:
        return ProofResult("unliftable", sketch=f"{through}: {e}", meta=meta)
    except Exception as e:
        return ProofResult("undecided", meta=meta,
                           sketch=f"{through}: {type(e).__name__} during "
                                  f"the lowering: {e}")
    if "unstated" in outcome:
        if outcome["unstated"]:
            row, text = outcome["unstated"][0]
            return ProofResult(
                "undecided", meta=meta,
                sketch=f"the definition row {row.key} {row.name} holds where "
                       f"{text}, which the claim does not state (assuming "
                       f"{text})")
        return _no_value(cj, fn, facts, cj_domain, assumption, outcome["unmet"],
                         by_length, through, meta)
    if "undecided" in outcome:
        return ProofResult("undecided", sketch=f"{through}: "
                           f"{outcome['undecided']}", meta=meta)
    vectors = ", ".join(sorted(seqs))
    if outcome.get("empty"):
        return ProofResult(
            "undecided", meta=meta,
            sketch=f"{through}, lowered to sums over {vectors}: the "
                   f"relation holds for every length of at least one, "
                   f"and the empty vector is left to the probe")
    if outcome.get("proven"):
        # the proof is over every length, so it covers the length a
        # binding fixes (`xs in [0, 1]^30`): the sketch keeps saying so
        # and adds the one clause every route adds for a fixed size
        fixed_at = fixed_lengths
        spans = ", ".join(
            f"{by_length.get(L, L)} of every length"
            + (f" from {shortest[L]}" if shortest.get(L, 1) > 1
               else " of at least one" if shortest.get(L) == 1 else "")
            for L in sorted(set(lengths_of(seqs)), key=str))
        at_least_one = (" of at least one"
                        if shortest and min(shortest.values()) == 1 else "")
        fixed_clause = ""
        if fixed_at:
            fixed_clause = "; the binding fixes " + " and ".join(
                f"{by_length.get(L, L)} at length {k}"
                for L, k in sorted(fixed_at.items(), key=lambda kv: str(kv[0])))
        detail = outcome.get("result")
        lemma = (f" ({detail.sketch})" if detail is not None
                 and getattr(detail, "status", None) == "proven"
                 and detail.sketch and outcome.get("bounds") else "")
        return ProofResult(
            "proven", meta=meta,
            sketch=f"{through}, lowered to sums over {vectors} at a symbolic "
                   f"length: the relation holds for every length"
                   f"{at_least_one}{lemma}{fixed_clause}",
            quantifier=(f"∀ {_over(seqs, elements)} with nothing "
                        f"missing, {spans}" if seqs else None))
    detail = outcome.get("result")
    why = (detail.sketch if detail is not None and detail.sketch else
           "the difference of the two sides does not simplify to 0")
    return ProofResult("undecided", sketch=f"{through}, lowered to sums over "
                                           f"{vectors}: {why}", meta=meta)


def _no_value(cj, fn, facts, cj_domain, assumption, unmet: list,
              by_length: dict, through: str, meta: dict):
    """Intent:
        The verdict where a rewritten claim has no value somewhere in
        its domain: a lowered denominator the premises do not keep
        nonzero, or a length the premises do not keep long enough. The
        function is executed at simple points of that region (constant
        vectors of zeros, then ones, at each short length); the first
        where the claim fails is an executed witness and the claim is
        `disproven`, otherwise it is `undecided` naming the region and
        the premise that excludes it.
    """
    import random

    from .conjecture import _resolve_bound_ref
    from .corroboration import INCONCLUSIVE, Undecided
    from .gates import _fmt_point, _point_evaluator
    from .symbolic._proof_support import ProofResult
    wheres: list = []
    remedies: list = []
    lengths_to_try: set = set()
    for item in unmet:
        if item[0] == "length":
            _k, length, least, have = item
            name = by_length.get(length, str(length))
            wheres.append(f"dim({name}) < {least}")
            remedies.append(f"dim({name}) >= {least}")
            lengths_to_try.update(range(have, least))
        else:
            _k, _expr, text, have = item
            wheres.append(f"{text} == 0")
            remedies.append(f"{text} != 0")
            lengths_to_try.update({have, have + 1})
    region = " or ".join(dict.fromkeys(wheres))
    remedy = " and ".join(dict.fromkeys(remedies))
    bound_funcs = {}
    for name, ref in (cj.funcs or {}).items():
        bound_funcs[name] = ref if callable(ref) else _resolve_bound_ref(ref)
    deps = None
    if all(v is not None for v in bound_funcs.values()):
        try:
            deps = _point_evaluator(cj, fn, facts, cj_domain, bound_funcs,
                                    assumption or [], sequences=True)
        except TimeoutError:
            raise
        except Exception:
            deps = None
    if deps is not None:
        rng = random.Random(0)
        vectors = [n for n in deps["names"] if n in by_length.values()
                   or facts.param_kinds.get(n) in ("vec", "mat", "sequence")]
        scalars = [n for n in deps["names"] if n not in vectors]
        for n in sorted(lengths_to_try):
            for value in (0.0, 1.0):
                for _attempt in range(4):
                    try:
                        point = {v: [value] * n for v in vectors}
                        point.update({s: deps["sample"](s, rng)
                                      for s in scalars})
                        if not deps["admits"](point):
                            continue
                        held = deps["evaluate"](point)
                    except TimeoutError:
                        raise
                    except Exception:
                        continue
                    if held is False:
                        detail = deps["probe_finite"](point)
                        if detail is INCONCLUSIVE \
                                or isinstance(detail, Undecided):
                            detail = None
                        shown = _fmt_point(point, deps["names"])
                        return ProofResult(
                            "disproven", meta={**meta,
                                               "mathema.witness_executed":
                                               True},
                            counterexample=(f"{shown}: {detail}" if detail
                                            else shown),
                            sketch=f"{through}, f has no value where "
                                   f"{region}, inside the claim's domain, "
                                   f"and executed there the claim fails")
                    break
    return ProofResult(
        "undecided", meta=meta,
        sketch=f"{through}, f has no value where {region}, which the claim's "
               f"domain does not exclude (state it: assuming {remedy})")
