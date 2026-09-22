# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Structural analysis: deterministic facts read off the AST.

Everything downstream (lifting, probing, narration) consumes the Facts
record produced here. No LLM, no guessing; only what the tree shows.
"""
from __future__ import annotations

import ast
import inspect
import re
import textwrap
from dataclasses import dataclass, field
from . import identity
from . import types as _types
from .intent import parse_doc

_IO_FUNCS = {"print", "input", "open", "exec", "eval", "__import__"}
_IO_MODULES = {"os", "sys", "subprocess", "socket", "requests", "urllib",
               "shutil", "http", "sqlite3", "pickle", "json"}
_CLOCK_MODULES = {"time", "datetime"}
_RANDOM_MODULES = {"random", "secrets"}
_MATH_MODULES = {"math", "cmath", "statistics", "np", "numpy"}
_MUTATORS = {"append", "extend", "insert", "pop", "remove", "clear", "update",
             "add", "discard", "sort", "reverse", "setdefault", "write",
             "writelines", "popitem"}
_SEQ_HINTS = ("list", "sequence", "iterable", "tuple", "ndarray", "array", "set")
# a bare parameter turned into an array by one of these calls, or read
# through one of these array attributes, is sequence-like even without an
# annotation (`np.asarray(x).shape[0]`, `len(np.asarray(x))`): the array
# constructor/reshaper is the sequence signal the direct len/for/index
# checks miss when the parameter is wrapped first.
_ARRAY_CALLS = frozenset({"asarray", "array", "asanyarray", "asfarray",
                          "atleast_1d", "atleast_2d", "atleast_3d",
                          "fromiter", "ravel", "flatten", "reshape"})
# `.T` belongs here for the same reason: a transpose read off a bare
# parameter is an array operation, and without it `x.T @ A @ x` left `x`
# to the scalar-arithmetic fallback below.
_ARRAY_ATTRS = frozenset({"shape", "ndim", "size", "flat", "T"})
# the `Vec(...)`/`Mat(...)` shorthand, lowercased to match unparsed
# annotation text. Sourced from types.py so there is one definition.
_SHAPED_LIST_FACTORY_NAMES = frozenset(
    f.lower() for f in _types.SHAPED_LIST_FACTORIES)

class StateDependenceWarning(UserWarning):
    """A function reads state outside its own parameters: a global
    variable's current value, or a name with no binding at all. Real
    signal on a single function; a population sweep (verify, audit,
    describe) silences this category, because its report already
    states the same fact per row."""



@dataclass
class LoopFact:
    """One `for`/`while` loop's shape, as read off the AST: what kind of
    loop it is (`"fold"`, an accumulator updated each iteration,
    `"build"`, a list being appended to, `"filter-build"`, a guarded
    build, or a plain `"loop"` that doesn't fit either pattern), what it
    iterates, and (for a fold) the accumulator's name, its update
    expression, and its initial value. `depth` is how many enclosing
    loops this loop's own `for`/`while` header sits inside (0 = top
    level, 1 = one loop in, 2 = two loops in, ...), reasoning about a
    loop gets harder with each additional level it's nested at, not by
    a fixed amount per level, so downstream complexity scoring weights
    depth rather than treating "nested" as a single flag."""
    kind: str                 # "fold" | "build" | "filter-build" | "loop"
    item: str                 # loop variable source
    iter_src: str             # what is iterated
    acc: str | None = None    # accumulator name (fold) or built list (build)
    op_source: str | None = None   # 'acc = <expr>' update rule (fold)
    init_source: str | None = None # accumulator initialization
    guarded: bool = False     # update sits under an `if`
    depth: int = 0             # loops enclosing this one (0 = top level)


@dataclass
class Facts:
    """Everything `analyze_source()` reads off a function's AST: its
    signature and parameter/return kinds, structural shape (loops,
    comprehensions, recursion, branch count), scope (which names it
    reads from outside its own parameters), and the identity hashes
    (`form`/`sigh`) used to detect when a claim's target has changed.
    `tree` is the parsed `ast.FunctionDef` itself, kept around so later
    stages (the derive-route lifter, branch pruning) don't have to
    re-parse the source.

    Every field except `tree` is language-neutral: names, kind
    vocabularies, `LoopFact` rows, hashes and counts, all statable
    about a function in any language. `tree` is FRONTEND-PRIVATE, the
    Python frontend's own attachment, and optional: every consumer
    treats `tree is None` as a valid state (the body-lifting derive
    routes decline, everything else proceeds), which is how a Facts
    built by something other than `analyze_source` participates.
    `mathema._doc_only_facts` is the shipping precedent, including its
    NAMESPACED form hash (`"doc:<sha>"`), the shape a foreign
    frontend's `"cpp:<sha>"`/`"ts:<sha>"` follows: form hashes are
    compared only within a namespace, never across."""
    name: str
    signature: str
    params: list[str]
    param_kinds: dict[str, str]        # "sequence" | "scalar" | "int" | "bool" | "complex" | "string" | "unknown"
    returns_kind: str                  # "scalar" | "sequence" | "bool" | "none" | "unknown"
    docstring: str | None
    source: str
    effects: list[str]
    is_pure: bool | None    # None: purity could not be established (no source)
    loops: list[LoopFact]
    comprehensions: list[str]          # "map" | "filter" | "map+filter"
    recursion: bool
    branch_count: int
    call_groups: dict[str, list[str]]  # "math" | "builtin" | "external"
    max_loop_depth: int
    lines: int
    form: str
    sigh: str
    tier: int = 2                      # finalized after lifting; 0 = doc-only
    tree: ast.FunctionDef | None = field(default=None, repr=False)
    guards: dict[str, str] = field(default_factory=dict)  # param → assert|raise|clamp|none
    doc_intent: str | None = None                         # documented intent (author's claim)
    doc_intent_source: str | None = None
    # the evidence rung the intent itself earns: "documented" when the
    # docstring states an explicit `Intent:` block, "declared" when only
    # the summary line provides one (the lowest rung; a summary is a
    # bare declaration, not a deliberate intent statement), None when
    # there is no intent at all.
    doc_refs: list = field(default_factory=list)          # citations from the docstring
    doc_hints: list[str] = field(default_factory=list)    # concept hints from the docs
    doc_notes: str | None = None      # optional Notes: block, limitations/design
                                      # rationale, never scored by anything that reads it;
                                      # includes any `# note:` comment notes, deduped
    comment_notes: list = field(default_factory=list)     # structured `# note:` comments:
                                      # [{"text", "line"}], line in file numbering
    global_vars: list[str] = field(default_factory=list)       # genuine global-variable state
    global_funcs: list[str] = field(default_factory=list)      # sibling function/class/module refs
    unresolved: list[str] = field(default_factory=list)       # free names with no binding at all
    mutated_globals: list[str] = field(default_factory=list)  # module-level names this function
                                      # WRITES THROUGH (CACHE[k] = v, OBJ.field = x) rather than
                                      # merely reads, hidden state it changes, not just depends on
    finite_domains: dict = field(default_factory=dict)        # param -> [values] where the
                                      # annotation (Literal/Enum/bool) states the whole value set
    doc_concepts: list = field(default_factory=list)          # declared Concepts:/Tags: marker
                                      # tokens (normalized; both spellings are concepts)


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else None


class SourceUnavailable(RuntimeError):
    """Raised when `inspect.getsource()` can't retrieve a callable's
    source (builtins, C extensions, functions defined via exec/stdin).
    Callers fall back to a documentation-only record (see
    `mathema._doc_only_facts`) rather than treating this as fatal."""


def get_tree(fn) -> tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """The function's dedented source text and its parsed
    `ast.FunctionDef`. Raises `SourceUnavailable` if the source can't be
    retrieved at all."""
    try:
        src = textwrap.dedent(inspect.getsource(fn))
    except (OSError, TypeError) as e:
        raise SourceUnavailable(
            f"Mathema needs the source of {getattr(fn, '__name__', fn)!r} and could not "
            "retrieve it. Functions defined in a notebook, a .py file, or an IPython "
            "session all work; builtins, C extensions, and functions defined via "
            "exec/stdin do not."
        ) from e
    mod = ast.parse(src)
    fdef = next((n for n in mod.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
                None)
    if fdef is None:
        # a lambda: inspect.getsource returns the whole enclosing
        # statement, never a FunctionDef, locate the ast.Lambda and
        # synthesize the equivalent one-line function so a lambda bound
        # via funcs= (or analyzed directly) lifts like any function
        lam = next((n for n in ast.walk(mod)
                    if isinstance(n, ast.Lambda)), None)
        if lam is None:
            raise SourceUnavailable(
                f"Mathema could not find a function definition in the "
                f"source of {getattr(fn, '__name__', fn)!r}")
        fdef = ast.FunctionDef(  # type: ignore[call-arg]
            name=getattr(fn, "__name__", "<lambda>").replace("<", "_").replace(">", "_"),
            args=lam.args,
            body=[ast.Return(value=lam.body)],
            decorator_list=[], returns=None, type_params=[])
        fdef = ast.fix_missing_locations(ast.copy_location(fdef, lam))
    return src, fdef


def _read_block(doc: str, header: str) -> list[str] | None:
    """Every line of a `<header>:` docstring block: the lines after a bare
    `header:` line (case-insensitive, matched whole), up to but not
    including the first line that dedents *below the block's own first
    body line's indentation*; blank lines within the block are
    skipped, not returned, and don't end it. `None` if no such header
    exists anywhere in `doc` (distinct from `[]`, a header present with
    no following lines). Shared scanning shape every docstring block
    (`Claims:`, `Intent:`, `Domain:`, `Notes:`, ...) uses, a docstring
    can carry several of these, each found and read independently.
    Lives here (not in authoring.py, where it originated for `Claims:`)
    because analyze_source() itself needs it for `Notes:`, and this
    module sits below every other module that would otherwise need to
    import it back upward.

    Deliberately relative to the block's own body, not an absolute
    column-0 check: `ast.get_docstring()`/`inspect.getdoc()` dedent by
    the *shallowest* margin present across the whole docstring, so a
    block that's the docstring's only content (no summary line above
    it) collapses its header and body to the very same column, an
    absolute "back to column 0 means the block is over" check would
    then see the first real body line as already dedented and return an
    empty block, silently losing everything in it."""
    if not doc:
        return None
    lines = doc.splitlines()
    target = header.strip().lower()
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == target:
            start = i
            break
    if start is None:
        return None
    out: list[str] = []
    baseline = None
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if baseline is None:
            baseline = indent
        elif indent < baseline:
            break   # dedented past the block's own body: the block is over
        out.append(line)
    return out


def _parse_concepts_marker(doc: str) -> list:
    """Intent:
        The declared `Concepts:`/`Tags:` marker's tokens (both
        spellings are concepts internally): a block form read by
        `_read_block`, or the inline one-liner (`Tags: a, b`).
        Concepts win over Tags when both appear.
    """
    from .concepts import parse_concepts
    for header in ("Concepts:", "Tags:"):
        block = _read_block(doc, header)
        if block:
            return parse_concepts("\n".join(block))
        m = re.search(rf"^\s*{header[:-1]}:\s*(.+)$", doc,
                      re.IGNORECASE | re.MULTILINE)
        if m:
            return parse_concepts(m.group(1))
    return []


def _annotation_base(text: str) -> str:
    """Intent:
        An annotation's own lowercased source text reduced to the type
        that decides its kind: `annotated[float, probability]` to
        `float`, and the `vec(...)`/`mat(...)` shorthand to the `list`
        it expands to.

    Notes:
        Both spellings exist so a parameter can carry a marker, and
        neither changes what the value IS, so the wrapper must not
        decide the kind. `Annotated[float, Probability]` classified on
        its wrapper reads as "unknown"; `Vec("n")` classified on its
        wrapper falls through to whatever the surrounding arithmetic
        suggested, which for `x.T @ A @ x` is "scalar", and a parameter
        called a scalar is then sampled as one. `types.Vec` documents
        the shorthand as producing the identical markers the long form
        does, so it has to classify identically too.
    """
    if text.startswith("annotated["):
        return text[len("annotated["):].split(",", 1)[0].strip()
    if text.split("(", 1)[0].strip() in _SHAPED_LIST_FACTORY_NAMES:
        return "list"
    return text


def _param_kinds(fdef: ast.FunctionDef, params: list[str]) -> dict[str, str]:
    kinds: dict[str, str] = {}
    ann = {a.arg: ast.unparse(a.annotation).lower()
           for a in [*fdef.args.posonlyargs, *fdef.args.args, *fdef.args.kwonlyargs]
           if a.annotation is not None}
    iterated: set[str] = set()
    arithmetic: set[str] = set()
    mapping: set[str] = set()
    for node in ast.walk(fdef):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Name):
            iterated.add(node.iter.id)
        elif isinstance(node, ast.comprehension) and isinstance(node.iter, ast.Name):
            iterated.add(node.iter.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in {"len", "sum", "min", "max", "sorted", "enumerate", "reversed"}:
            for call_arg in node.args:
                if isinstance(call_arg, ast.Name):
                    iterated.add(call_arg.id)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            # a literal-string key (`params["a"]`) is named-dict-style field
            # access, not sequence indexing, symbolic.py's _bind_params()
            # can lift this (one symbol per key actually used), so it must
            # not be pre-emptively classified "sequence" here and refused
            # by lift()'s scalar-only gate before ever reaching that logic.
            # Numeric/variable/slice subscripting (`xs[0]`, `xs[i]`,
            # `xs[1:3]`) is unchanged; that's real sequence indexing.
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                mapping.add(node.value.id)   # `d["field"]`: dict-style
            else:
                iterated.add(node.value.id)
        elif (isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute)
              and node.func.attr in _ARRAY_CALLS):
            # `np.asarray(x)` / `np.array(x)` / ...: the bare-name argument
            # is being turned into an array, so it is sequence-like.
            for call_arg in node.args:
                if isinstance(call_arg, ast.Name):
                    iterated.add(call_arg.id)
        elif (isinstance(node, ast.Attribute) and node.attr in _ARRAY_ATTRS
              and isinstance(node.value, ast.Name)):
            # `x.shape` / `x.ndim` / ...: an array attribute read off a
            # bare parameter, so the parameter is array-like.
            iterated.add(node.value.id)
        elif (isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute)
              and node.func.attr in ("values", "keys", "items", "get")
              and isinstance(node.func.value, ast.Name)):
            # `d.values()` / `d.get("k")` / ...: a mapping method on a
            # bare parameter, so the parameter is a dict.
            mapping.add(node.func.value.id)
        elif isinstance(node, ast.BinOp):
            # `@` is matrix multiplication and has no scalar reading, so
            # a bare name under it is evidence of array-ness, not of
            # scalar arithmetic. Counting it as the latter is what made
            # `x.T @ A @ x` classify both operands as scalars.
            side_of = iterated if isinstance(node.op, ast.MatMult) else arithmetic
            for side in (node.left, node.right):
                if isinstance(side, ast.Name):
                    side_of.add(side.id)
    for p in params:
        a = _annotation_base(ann.get(p, ""))
        # the outer constructor decides the kind: `Literal["info",
        # "set"]` is whatever its literal values are, never a sequence,
        # even though "set" appears inside the brackets
        head = a.split("[", 1)[0].strip()
        if head == "literal":
            kinds[p] = _literal_kind(a)
        elif head in ("dict", "mapping", "mutablemapping", "ordereddict",
                      "defaultdict", "counter") or "mapping" in head:
            kinds[p] = "dict"
        elif any(h in head for h in _SEQ_HINTS):
            kinds[p] = "sequence"
        elif a.startswith("str"):
            kinds[p] = "string"
        elif a.startswith("bool"):
            kinds[p] = "bool"
        elif a.startswith("int"):
            kinds[p] = "int"
        elif a.startswith("complex"):
            kinds[p] = "complex"
        elif a.startswith(("float", "real", "number")):
            kinds[p] = "scalar"
        elif any(h in a for h in _SEQ_HINTS):
            # a container anywhere deeper in the annotation
            # (Optional[list[float]], Union[list, ...]) still reads as
            # a sequence
            kinds[p] = "sequence"
        elif p in mapping:
            kinds[p] = "dict"
        elif p in iterated:
            kinds[p] = "sequence"
        elif p in arithmetic:
            kinds[p] = "scalar"
        else:
            kinds[p] = "unknown"
    return kinds


def _literal_kind(unparsed: str) -> str:
    """Intent:
        The parameter kind of a `Literal[...]` annotation, from its
        lowercased unparsed text: all-string values -> "string",
        all-bool -> "bool", all-int -> "int", anything mixed or
        unreadable -> "unknown".
    """
    inner = unparsed.partition("[")[2].rpartition("]")[0]
    vals = [v.strip() for v in inner.split(",") if v.strip()]
    if not vals:
        return "unknown"
    if all(v[:1] in "\"'" for v in vals):
        return "string"
    if all(v in ("true", "false") for v in vals):
        return "bool"
    try:
        for v in vals:
            int(v)
        return "int"
    except ValueError:
        return "unknown"


def finite_annotation_domains(fn) -> dict:
    """The parameters whose type hint already states their entire
    meaningful value set, a `Literal[...]`'s values, an Enum's member
    values, a plain `bool`'s two points, as `{name: [values]}`. Read
    from the live annotation objects, so string forms and imports
    resolve the way the function's own module resolves them. A bool
    parameter's values are the real `False`/`True` objects, never the
    numerically-equal 0/1: code comparing with `is True` behaves
    differently under the two, so the stated set is the honest one."""
    import enum
    import inspect
    import typing as t

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return {}
    out = {}
    for p in sig.parameters.values():
        if p.annotation is inspect.Parameter.empty:
            continue
        ann = p.annotation
        if t.get_origin(ann) is t.Literal:
            out[p.name] = list(t.get_args(ann))
        elif ann is bool:
            out[p.name] = [False, True]
        elif isinstance(ann, type) and issubclass(ann, enum.Enum):
            out[p.name] = [e.value for e in ann]
    return out


def _returns_kind(fdef: ast.FunctionDef) -> str:
    if fdef.returns is not None:
        a = _annotation_base(ast.unparse(fdef.returns).lower())
        if any(h in a for h in _SEQ_HINTS):
            return "sequence"
        if a.startswith("bool"):
            return "bool"
        if a in {"none"}:
            return "none"
        if a.startswith(("float", "int", "real", "number")):
            return "scalar"
    rets = [n for n in ast.walk(fdef) if isinstance(n, ast.Return) and n.value is not None]
    if not rets:
        return "none"
    v = rets[-1].value
    if isinstance(v, (ast.ListComp, ast.List, ast.Tuple, ast.SetComp, ast.DictComp)):
        return "sequence"
    if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in {"list", "sorted", "tuple"}:
        return "sequence"
    if isinstance(v, (ast.BinOp, ast.Constant, ast.Name, ast.UnaryOp, ast.IfExp)):
        return "scalar"
    if isinstance(v, ast.Compare):
        return "bool"
    return "unknown"


def _effects(fdef: ast.FunctionDef, params: list[str]) -> list[str]:
    out: list[str] = []

    def note(msg: str) -> None:
        if msg not in out:
            out.append(msg)

    local_seqs = {t.id for n in ast.walk(fdef) if isinstance(n, ast.Assign)
                  for t in n.targets if isinstance(t, ast.Name)}
    for node in ast.walk(fdef):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            note(f"declares {' '.join(node.names)} {type(node).__name__.lower()}")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in _IO_FUNCS:
                note(f"calls {f.id}() (I/O)")
            elif isinstance(f, ast.Attribute):
                root = _root_name(f.value)
                if root in _IO_MODULES:
                    note(f"calls {root}.{f.attr} (I/O / system)")
                elif root in _RANDOM_MODULES or (root in {"np", "numpy"} and "random" in ast.unparse(f)):
                    note("uses randomness")
                elif root in _CLOCK_MODULES:
                    note("reads the clock")
                elif f.attr in _MUTATORS and root in params:
                    note(f"mutates argument '{root}'")
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, (ast.Subscript, ast.Attribute)):
                    root = _root_name(t)
                    if root in params and root not in local_seqs:
                        note(f"mutates argument '{root}'")
    return out


def _loops(fdef: ast.FunctionDef) -> list[LoopFact]:
    facts: list[LoopFact] = []
    assigned_before: dict[str, str] = {}

    def scan(stmts: list[ast.stmt], depth: int) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                    and isinstance(stmt.targets[0], ast.Name):
                assigned_before[stmt.targets[0].id] = ast.unparse(stmt)
            elif isinstance(stmt, ast.For):
                fact = _classify_for(stmt, dict(assigned_before))
                fact.depth = depth
                facts.append(fact)
                scan(stmt.body, depth + 1)
            elif isinstance(stmt, ast.While):
                facts.append(LoopFact(kind="loop", item="",
                                       iter_src="while " + ast.unparse(stmt.test),
                                       depth=depth))
                scan(stmt.body, depth + 1)
            elif isinstance(stmt, ast.If):
                scan(stmt.body, depth)
                scan(stmt.orelse, depth)

    scan(fdef.body, depth=0)
    # a comprehension IS a loop, structurally: the sum machinery reads
    # the desugared accumulator form (see symbolic._normalize), and the
    # gates that consult facts.loops must open for it. kind mirrors
    # the taxonomy _comprehensions() reports.
    for node in ast.walk(fdef):
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp,
                             ast.DictComp)):
            guarded = any(c.ifs for c in node.generators)
            facts.append(LoopFact(
                kind="filter-build" if guarded else "build",
                item=", ".join(ast.unparse(c.target)
                               for c in node.generators),
                iter_src=", ".join(ast.unparse(c.iter)
                                   for c in node.generators),
                guarded=guarded))
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == "sum" and len(node.args) == 1
              and not node.keywords
              and (isinstance(node.args[0], ast.Name)
                   or (isinstance(node.args[0], ast.Call)
                       and isinstance(node.args[0].func, ast.Name)
                       and node.args[0].func.id in ("map", "filter")))):
            # sum(xs) / sum(map(g, xs)) / sum(filter(p, xs)): an
            # implicit loop over the whole argument, desugared to the
            # explicit accumulator form by the normalize pre-pass
            facts.append(LoopFact(
                kind="filter-build" if (
                    isinstance(node.args[0], ast.Call)
                    and node.args[0].func.id == "filter") else "build",
                item="_elt", iter_src=ast.unparse(node.args[0])))
    return facts


def _classify_for(loop: ast.For, before: dict[str, str]) -> LoopFact:
    item = ast.unparse(loop.target)
    iter_src = ast.unparse(loop.iter)
    body = loop.body
    guarded = False
    if len(body) == 1 and isinstance(body[0], ast.If) and not body[0].orelse:
        guarded = True
        body = body[0].body

    for stmt in body:
        if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name) \
                and stmt.target.id in before:
            acc = stmt.target.id
            op = {"Add": "+", "Sub": "-", "Mult": "*", "Div": "/"}.get(
                type(stmt.op).__name__, "?")
            return LoopFact(kind="fold", item=item, iter_src=iter_src, acc=acc,
                            op_source=f"{acc} = {acc} {op} {ast.unparse(stmt.value)}",
                            init_source=before.get(acc), guarded=guarded)
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                and isinstance(stmt.targets[0], ast.Name):
            acc = stmt.targets[0].id
            reads = {n.id for n in ast.walk(stmt.value) if isinstance(n, ast.Name)}
            if acc in before and acc in reads:
                return LoopFact(kind="fold", item=item, iter_src=iter_src, acc=acc,
                                op_source=f"{acc} = {ast.unparse(stmt.value)}",
                                init_source=before.get(acc), guarded=guarded)
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) \
                and isinstance(stmt.value.func, ast.Attribute) \
                and stmt.value.func.attr == "append":
            root = _root_name(stmt.value.func.value)
            if root in before:
                return LoopFact(kind="filter-build" if guarded else "build",
                                item=item, iter_src=iter_src, acc=root,
                                op_source=ast.unparse(stmt.value),
                                init_source=before.get(root), guarded=guarded)
    return LoopFact(kind="loop", item=item, iter_src=iter_src, guarded=guarded)


def _comprehensions(fdef: ast.FunctionDef) -> list[str]:
    out = []
    for node in ast.walk(fdef):
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp,
                             ast.DictComp)):
            has_filter = any(c.ifs for c in node.generators)
            # a dict comprehension's element is its value expression
            elt = node.value if isinstance(node, ast.DictComp) else node.elt
            elt_is_identity = isinstance(elt, ast.Name) and any(
                isinstance(c.target, ast.Name) and c.target.id == elt.id
                for c in node.generators)
            if has_filter and elt_is_identity:
                out.append("filter")
            elif has_filter:
                out.append("map+filter")
            else:
                out.append("map")
    return out


def _max_depth(fdef: ast.FunctionDef) -> int:
    def depth(node: ast.AST, d: int) -> int:
        best = d
        for child in ast.iter_child_nodes(node):
            inc = 1 if isinstance(child, (ast.For, ast.While, ast.ListComp,
                                          ast.SetComp, ast.GeneratorExp, ast.DictComp)) else 0
            best = max(best, depth(child, d + inc))
        return best
    return depth(fdef, 0)


def _call_groups(fdef: ast.FunctionDef, name: str) -> tuple[dict[str, list[str]], bool]:
    groups: dict[str, list[str]] = {"math": [], "builtin": [], "external": []}
    recursion = False
    builtin_names = {"len", "sum", "min", "max", "abs", "round", "sorted", "range",
                     "enumerate", "zip", "reversed", "list", "tuple", "set", "dict",
                     "float", "int", "str", "bool", "map", "filter", "all", "any"}
    for node in ast.walk(fdef):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Name):
            if f.id == name:
                recursion = True
            elif f.id in builtin_names:
                if f.id not in groups["builtin"]:
                    groups["builtin"].append(f.id)
            elif f.id not in _IO_FUNCS:
                if f.id not in groups["external"]:
                    groups["external"].append(f.id)
        elif isinstance(f, ast.Attribute):
            root = _root_name(f.value)
            label = f"{root}.{f.attr}" if root else f.attr
            if root in _MATH_MODULES:
                if label not in groups["math"]:
                    groups["math"].append(label)
            elif root not in _IO_MODULES | _RANDOM_MODULES | _CLOCK_MODULES \
                    and f.attr not in _MUTATORS:
                if label not in groups["external"]:
                    groups["external"].append(label)
    return groups, recursion


def _guards(fdef: ast.FunctionDef, params: list[str]) -> dict[str, str]:
    """Enforcement posture per parameter: does the code check its own domain?
    'assert' / 'raise' reject bad input; 'clamp' coerces it; 'none' trusts it."""
    guards = {p: "none" for p in params}
    pset = set(params)

    def names_in(node: ast.AST) -> set[str]:
        return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} & pset

    for node in ast.walk(fdef):
        if isinstance(node, ast.Assert):
            for p in names_in(node.test):
                guards[p] = "assert"
        elif isinstance(node, ast.If) and any(isinstance(s, ast.Raise) for s in node.body):
            for p in names_in(node.test):
                guards[p] = "raise"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in {"min", "max"}:
            for a in node.args:
                if isinstance(a, ast.Name) and a.id in pset and guards[a.id] == "none":
                    guards[a.id] = "clamp"
    return guards


def _nested_bound_names(fdef: ast.FunctionDef) -> set:
    """Parameter and local-assignment names belonging to any function or
    lambda nested *inside* fdef, see _global_captures's own comment on
    why these get folded into the outer function's bound set rather
    than resolved in a properly scope-aware way."""

    names: set = set()
    for node in ast.walk(fdef):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not fdef:
            names.add(node.name)
            names |= set(identity.local_names(node))
        elif isinstance(node, ast.Lambda):
            args = node.args
            for a in (*args.posonlyargs, *args.args,
                     *([args.vararg] if args.vararg else []),
                     *args.kwonlyargs, *([args.kwarg] if args.kwarg else [])):
                names.add(a.arg)
    return names


def _is_definitional(value) -> bool:
    """True for a function/class/module (or a bound/builtin method or
    routine), an ordinary reference to another top-level *definition*,
    the way calling a sibling function or instantiating a sibling class
    is just normal code structure. Distinct from a genuine global
    *variable*: a claim's reliability is only as good as the value a
    global variable currently holds (the real hidden-dependency risk a
    notebook cell can silently leave behind), which calling another
    function by name has nothing to do with; these are different
    error surfaces, and conflating them under one "depends on globals"
    signal makes the genuinely risky one harder to spot."""
    import types

    return (inspect.isroutine(value) or inspect.isclass(value)
           or isinstance(value, types.ModuleType))


def _global_captures(fdef: ast.FunctionDef, fn) -> tuple[
        list[str], list[str], list[str], list[str]]:
    """Free names the function inherits from outside itself, split four
    ways: genuine global *variables* (state, see _is_definitional()),
    references to a sibling *function/class/module* (not state, not a
    risk the same way), and *unresolved* names with no binding anywhere
    at analysis time (almost always a real bug, e.g. a typo or a name
    that only exists at call time)."""
    import builtins


    # Only the executable body, deliberately; ast.walk(fdef) would also
    # reach fdef.args (parameter annotations/defaults) and fdef.returns
    # (the return annotation). A type hint is never executed as part of
    # the function's own logic (Literal["info", "linear"] on a parameter
    # references the name `Literal`, but that's metadata, not a runtime
    # dependency the function's *behavior* actually has), so it must not
    # count as a capture the way a body reference to a real global does.
    #
    # A nested def/lambda (a real closure, e.g. a small helper defined
    # inside the function being analyzed) has its own separate scope;
    # its own parameters and locals are bound *there*, not in the outer
    # function, but a flat walk can't tell the difference. Fully
    # resolving nested scopes correctly is a bigger piece of machinery
    # than this needs; folding a nested scope's own bound names into the
    # outer `bound` set instead is conservative in the direction that
    # matters here; it can only suppress a false "unresolved"/capture
    # report (a nested function's own parameter wrongly looking like an
    # outer-scope dependency), never manufacture a new false negative.
    bound = set(identity.local_names(fdef)) | {fdef.name} | _nested_bound_names(fdef)
    for stmt in fdef.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Import):
                bound |= {(a.asname or a.name.split(".")[0]) for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                bound |= {(a.asname or a.name) for a in node.names}
    known = _MATH_MODULES | _IO_MODULES | _CLOCK_MODULES | _RANDOM_MODULES
    g = getattr(fn, "__globals__", {})
    global_vars: list[str] = []
    global_funcs: list[str] = []
    unresolved: list[str] = []
    # A name written through a subscript or attribute (`CACHE[k] = v`) is
    # not rebound by the assignment, so `local_names`, which exists to
    # drive alpha-renaming, and must not change; counts it as local and
    # it never reaches the capture scan below. Recognize those writes
    # here instead: `rebound` is the set genuinely bound by a plain Name
    # store, which is what "local" means for this purpose.
    rebound = {n.id for n in ast.walk(fdef)
               if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    mutated_globals: list[str] = []
    for node in ast.walk(fdef):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        else:
            continue
        for store in targets:
            if not isinstance(store, (ast.Subscript, ast.Attribute)):
                continue
            root: ast.expr = store
            while isinstance(root, (ast.Subscript, ast.Attribute)):
                root = root.value
            if not isinstance(root, ast.Name):
                continue
            name = root.id
            if (name not in rebound and name in g
                    and not _is_definitional(g[name])
                    and name not in mutated_globals):
                mutated_globals.append(name)
    for stmt in fdef.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                n = node.id
                if n in bound or n in known or hasattr(builtins, n):
                    continue
                if n not in g:
                    if n not in unresolved:
                        unresolved.append(n)
                    continue
                target = global_funcs if _is_definitional(g[n]) else global_vars
                if n not in target:
                    target.append(n)
    if global_vars or unresolved:
        # global_funcs deliberately doesn't trigger this, referencing a
        # sibling function/class/module isn't "behavior depends on state
        # outside the function" the way a global variable's current
        # value, or a name with no binding at all, actually is.
        import warnings
        parts = []
        if global_vars:
            parts.append(f"inherits from global scope: {', '.join(global_vars)}")
        if unresolved:
            parts.append(f"UNRESOLVED names: {', '.join(unresolved)}")
        warnings.warn(f"mathema: {fdef.name} " + "; ".join(parts)
                      + "; behavior depends on state outside the function",
                      StateDependenceWarning, stacklevel=4)
    return global_vars, global_funcs, unresolved, mutated_globals


_NOTES_HEADER = "notes:"


def _parse_notes(doc: str) -> str | None:
    """The `Notes:` block's prose, joined into one string, limitations
    or design rationale an author wants recorded alongside a function's
    claims, distinct from `Intent:` (what the function computes) and
    never scored: absence is fine, this is optional context, not a
    completeness criterion."""
    lines = _read_block(doc, _NOTES_HEADER)
    if lines is None:
        return None
    text = " ".join(line.strip() for line in lines).strip()
    return text or None


_INLINE_NOTE = re.compile(r"^\s*#\s*notes?\s*:\s*(.*)$", re.IGNORECASE)
_COMMENT_LINE = re.compile(r"^\s*#\s*(.*)$")


def _parse_inline_notes(src: str) -> list[dict]:
    """Intent:
        Every `# note:` comment in a function's own source body
        (`note:`/`Notes:`/`NOTE:`, any capitalisation), each with the
        comment lines immediately following it folded in, as
        `[{"text", "line"}]` in source order. `line` is 1-based within
        `src`; `analyze_source()` rebases it to the file's own line
        numbering when it can.

    Notes:
        Comments are not part of the AST, so this scans the function's
        raw source lines rather than walking the tree. One note ends at
        the first blank line or first non-comment line after its match;
        a new `# note:` line always starts a new item, so a function
        can carry several distinct notes and every one survives.
    """
    lines = src.splitlines()
    out: list[dict] = []
    i = 0
    while i < len(lines):
        m = _INLINE_NOTE.match(lines[i])
        if m is None:
            i += 1
            continue
        collected = [m.group(1).strip()]
        start = i
        i += 1
        while i < len(lines):
            if not lines[i].strip() or _INLINE_NOTE.match(lines[i]):
                break
            fm = _COMMENT_LINE.match(lines[i])
            if fm is None:
                break
            collected.append(fm.group(1).strip())
            i += 1
        text = " ".join(c for c in collected if c).strip()
        if text:
            out.append({"text": text, "line": start + 1})
    return out


def looks_like_wrapper(facts) -> bool:
    """A documented function whose Python source is thin dispatch; external
    calls, no loops/comprehensions/lift, is a wrapper around a compiled core
    (the numpy/sklearn pattern). Its documented intent describes the core;
    its structural facts describe only the wrapper. Keep the two separate."""
    return bool(facts.doc_intent and facts.tier == 2
                and not facts.loops and not facts.comprehensions
                and facts.call_groups.get("external"))


def analyze_source(fn) -> Facts:
    """Read a function's real source and build its `Facts` record,
    the single entry point everything downstream (the derive-route
    lifter, the probe route, `mathema audit`'s population analyses)
    depends on. Raises `SourceUnavailable` if `fn`'s source can't be
    retrieved."""


    src, fdef = get_tree(fn)
    params = [a.arg for a in [*fdef.args.posonlyargs, *fdef.args.args, *fdef.args.kwonlyargs]]
    effects = _effects(fdef, params)
    groups, recursion = _call_groups(fdef, fdef.name)
    docstring_text = ast.get_docstring(fdef)
    doc = parse_doc(docstring_text)
    global_vars, global_funcs, unresolved, mutated_globals = _global_captures(fdef, fn)
    doc_notes = _parse_notes(docstring_text or "")
    doc_concepts = _parse_concepts_marker(docstring_text or "")
    # inline #tag spellings anywhere in the docstring are the terse
    # concept-authoring form ("uses the #black-scholes closed form"):
    # word-start hash followed by a letter, so numeric anchors (#1)
    # and mid-word hashes never match
    import re as _re
    for m in _re.finditer(r"(?<![\w#])#([A-Za-z][A-Za-z0-9_-]{1,40})\b",
                          docstring_text or ""):
        from .concepts import normalize_concept as _nc
        tag = _nc(m.group(1))
        if tag and tag not in doc_concepts:
            doc_concepts.append(tag)
    comment_notes = _parse_inline_notes(src)
    try:
        # rebase the notes' src-relative lines onto the file's own
        # numbering, so a note's provenance is clickable; best-effort
        # (a REPL-defined function has no file line to rebase onto).
        offset = inspect.getsourcelines(fn)[1]
        comment_notes = [{**n, "line": offset + n["line"] - 1} for n in comment_notes]
    except (OSError, TypeError):
        pass
    # the flat prose merge every reader of meta.notes already gets:
    # docstring Notes: first, then each comment note, deduped by
    # normalized text so a re-run or a docstring that already states
    # the same limitation never double-appends. Line provenance lives
    # in the structured comment_notes field, not in the prose.
    seen = set()
    if doc_notes:
        seen.add(doc_notes.strip().lower())
    for n in comment_notes:
        text = n["text"]
        key = text.strip().lower()
        if key in seen or (doc_notes and key in doc_notes.lower()):
            continue
        seen.add(key)
        doc_notes = f"{doc_notes} {text}" if doc_notes else text
    return Facts(
        name=fdef.name,
        signature=identity.signature_string(fn),
        params=params,
        param_kinds=_param_kinds(fdef, params),
        finite_domains=finite_annotation_domains(fn),
        doc_concepts=doc_concepts,
        returns_kind=_returns_kind(fdef),
        docstring=docstring_text,
        source=src,
        effects=effects,
        is_pure=not effects,
        loops=_loops(fdef),
        comprehensions=_comprehensions(fdef),
        recursion=recursion,
        branch_count=sum(1 for n in ast.walk(fdef) if isinstance(n, ast.If)),
        call_groups=groups,
        max_loop_depth=_max_depth(fdef),
        lines=len(src.strip().splitlines()),
        form=identity.form_hash(fdef),
        sigh=identity.sig_hash(fn),
        tree=fdef,
        guards=_guards(fdef, params),
        doc_intent=doc.summary or None,
        doc_intent_source=("documented" if _read_block(docstring_text or "", "intent:") is not None
                           else "declared" if doc.summary else None),
        doc_refs=doc.refs,
        doc_hints=doc.concept_hints,
        doc_notes=doc_notes,
        comment_notes=comment_notes,
        global_vars=global_vars,
        global_funcs=global_funcs,
        unresolved=unresolved,
        mutated_globals=mutated_globals,
    )


def quiet_facts(fn) -> "Facts | None":
    """`analyze_source(fn)` in population-sweep posture: analysis
    warnings suppressed (a sweep over every function in a package would
    otherwise print one global-scope/unresolved-name warning per
    affected function, drowning the report itself; the same signal is
    available as structured data via `inventory.scope_dependencies`),
    and `None` instead of `SourceUnavailable` for a function with no
    reachable source. The one shared spelling of a block that used to
    be copied at every sweep site."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return analyze_source(fn)
        except SourceUnavailable:
            return None
