# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The shape of a drawn parameter and the evidence that establishes it.

A parameter the probe route draws for has a shape: the kind of value it
is given (a number, a string, a sequence, a mapping, an instance). The
shape comes from positive evidence, read in this order:

1. the claim's own domain, or a domain inferred into it from the
   function's annotation, default or guard (`claim domain`, `inferred
   domain`);
2. a mathema type marker on the signature (`type marker`): a shape
   (`Vec`, `Mat`, `Shape`) or a bound (`Probability`, `InRange`, ...);
3. the annotation (`annotation`): `int`, `float`, `complex`, `bool`,
   `str`, the containers (`list`, `tuple`, `set`, `Sequence`, `dict`,
   `Mapping`, with or without element types), `Optional[X]` and
   `X | None` for one such `X`, `Annotated[X, ...]`, `Literal[...]`, an
   `Enum`, a dataclass, and a runtime type's own annotation (a numpy
   array, a pandas or polars Series or DataFrame);
4. the default value's type (`default`): a bool, int, float, complex,
   str, list, tuple or dict;
5. how the body uses the parameter (`body use`): indexed, sliced,
   iterated or measured with `len` (a sequence), read with a string key
   or a mapping method (a mapping), under arithmetic, an ordering
   against a number, a sign or a numeric function (a number), joined
   with or compared to a string literal (a string), or passed whole to
   another function of the same module whose parameter has evidence.

Evidence that names two different kinds for one parameter is a
disagreement, and the parameter is then not drawn; neither is one with
no evidence at all. A claim domain, an inferred domain, a type marker
and an annotation are stated evidence; a default and a body use are
read from the code.

`wrong_shape_use` reads a TypeError or AttributeError back to the
operation in the function's own body that raised it: one applied
directly to a parameter's value, whose message names that value's type.
"""
from __future__ import annotations

import ast
import inspect
import weakref
from typing import Any
from dataclasses import dataclass

#: the sources, in the order a parameter's shape is read from them
EVIDENCE_ORDER = ("claim domain", "inferred domain", "type marker",
                  "annotation", "receiver", "generated dataclass method",
                  "default", "body use", "not read by the body")
#: the sources an author states, or that a definition fixes, rather than
#: ones read from the code
STATED = frozenset({"claim domain", "inferred domain", "type marker",
                    "annotation", "receiver", "generated dataclass method"})

_KIND_SHAPES = {"scalar": "number", "int": "number", "complex": "number",
                "bool": "bool", "string": "string", "dict": "mapping",
                "sequence": "sequence", "vec": "sequence", "mat": "sequence",
                "table": "table"}

_SHAPE_WORDS = {"number": "a number", "string": "a string", "bool": "a bool",
                "sequence": "a sequence", "mapping": "a mapping",
                "table": "a table", "instance": "an instance"}


@dataclass(frozen=True)
class Evidence:
    """One piece of evidence for a parameter's shape: where it comes
    from (`source`, one of `EVIDENCE_ORDER`), the shape it names and
    what it is, as a reader would point at it (`detail`)."""
    source: str
    shape: str
    detail: str
    #: whether the evidence rules other shapes out; an operator use
    #: (`x * y`) names a number when nothing else names a shape, and is
    #: also what a string or a sequence supports
    firm: bool = True


@dataclass(frozen=True)
class ParameterShape:
    """Intent:
        The shape a parameter is drawn as and the evidence for it: the
        first piece in `EVIDENCE_ORDER` (`evidence`), every piece found
        (`found`), and the pieces that name another shape than the
        first (`disagree`). `evidence` is None when nothing establishes
        the shape.
    """
    param: str
    evidence: "Evidence | None"
    found: tuple = ()
    disagree: tuple = ()

    @property
    def established(self) -> bool:
        """Whether the parameter may be drawn: some evidence, none of
        it disagreeing."""
        return self.evidence is not None and not self.disagree

    @property
    def stated(self) -> bool:
        """Whether the shape rests on evidence an author stated."""
        return self.evidence is not None and self.evidence.source in STATED

    def as_record(self) -> dict:
        """The shape and its evidence as plain values for a record."""
        if self.evidence is None:
            return {"source": "none"}
        out = {"source": self.evidence.source, "shape": self.evidence.shape,
               "detail": self.evidence.detail}
        if self.disagree:
            out["disagree"] = [{"source": e.source, "shape": e.shape,
                                "detail": e.detail} for e in self.disagree]
        return out


def kind_shape(kind: "str | None") -> "str | None":
    """The shape a `Facts.param_kinds` kind names, None for `unknown`."""
    return _KIND_SHAPES.get(kind or "")


def _default_shape(value) -> "str | None":
    """The shape a default value states, None for any other value
    (None included)."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float, complex)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "sequence"
    if isinstance(value, dict):
        return "mapping"
    return None


def _function_def(fn) -> "tuple[Any, int]":
    """Intent:
        `fn`'s definition parsed from its source, with the line offset
        that maps its line numbers onto the file's, or `(None, 0)` when
        the source cannot be read.
    """
    target = inspect.unwrap(fn)
    code = getattr(target, "__code__", None)
    if code is None:
        return _parsed_def(target)
    if code not in _DEFS:
        _DEFS[code] = _parsed_def(target)
    return _DEFS[code]


#: each function's parsed definition, by code object
_DEFS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _parsed_def(target) -> "tuple[Any, int]":
    """`_function_def` without the cache."""
    try:
        lines, start = inspect.getsourcelines(target)
    except (OSError, TypeError):
        return None, 0
    import textwrap
    try:
        tree = ast.parse(textwrap.dedent("".join(lines)))
    except SyntaxError:
        return None, 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node, max(start, 1) - 1
    return None, 0


def _source_line(fn, line: int) -> str:
    """The text of `line` in `fn`'s file, stripped, or ''."""
    import linecache
    try:
        path = inspect.getsourcefile(inspect.unwrap(fn)) or ""
    except TypeError:
        return ""
    return linecache.getline(path, line).strip()


def _place(fn, line: int) -> str:
    """`file:line` for a line of `fn`'s file, the file by its base name."""
    import os
    try:
        path = inspect.getsourcefile(inspect.unwrap(fn)) or ""
    except TypeError:
        path = ""
    return f"{os.path.basename(path) or '<unknown>'}:{line}"


def body_evidence(fn, fdef, params: list, kinds: dict,
                  depth: int = 1, offset: int = 0) -> dict:
    """Intent:
        `{param: [Evidence, ...]}` read from how `fdef`'s body uses each
        parameter: the body's own kind (`kinds`, the `Facts.param_kinds`
        the annotation did not decide), its numeric and text uses
        (`analysis.param_uses`), the methods and attributes it reads off
        the parameter (`runtime_types._body_uses`), and, `depth` calls
        deep, the evidence of a same-module function's parameter the
        body passes it to whole.
    """
    from .analysis import param_uses
    from .runtime_types import _body_uses
    uses = param_uses(fdef, params)
    methods = _body_uses(fdef, params)
    out: dict = {p: [] for p in params}
    for p in params:
        shape = kind_shape(kinds.get(p))
        if shape == "number" and p in uses.text and p not in uses.numeric:
            # every operator use joins it with text
            shape = None
        if shape is not None:
            how = {"sequence": "the body indexes, iterates or measures it",
                   "mapping": "the body reads it as a mapping",
                   "number": "the body puts it under arithmetic"}.get(
                       shape, f"the body uses it as {_SHAPE_WORDS[shape]}")
            out[p].append(Evidence("body use", shape, how,
                                   firm=shape != "number"))
        for line, text in uses.numeric.get(p, ()):
            out[p].append(Evidence("body use", "number",
                                   f"`{text}` on line {line + offset}"))
        for line, text in uses.text.get(p, ()):
            out[p].append(Evidence("body use", "string",
                                   f"`{text}` on line {line + offset}"))
        for form, name in methods.get(p, ()):
            shape = _method_shape(form, name)
            if shape is not None:
                out[p].append(Evidence(
                    "body use", shape,
                    f"`{p}.{name}{'()' if form != 'attr' else ''}`"))
    if depth > 0:
        for p, ev in _passed_on(fn, fdef, params, depth).items():
            out[p].extend(ev)
    return out


def _method_shape(form: str, name: str) -> "str | None":
    """The one shape among the built-in value types whose type has the
    method or attribute `name`, None when several or none do."""
    if form == "@":
        return None
    having = [shape for shape, cls in (("string", str), ("sequence", list),
                                       ("mapping", dict), ("number", float))
              if hasattr(cls, name)]
    if hasattr(object, name) or len(having) != 1:
        return None
    return having[0]


def _passed_on(fn, fdef, params: list, depth: int) -> dict:
    """Intent:
        `{param: [Evidence, ...]}` for each parameter `fdef` passes whole
        to a plain Python function its module binds by name, read from
        that function's own parameter (its annotation, then its body).
    """
    scope = getattr(inspect.unwrap(fn), "__globals__", None) or {}
    out: dict = {}
    pset = set(params)
    for node in ast.walk(fdef):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        callee = scope.get(node.func.id)
        if not inspect.isfunction(callee) or callee is inspect.unwrap(fn):
            continue
        try:
            names = list(inspect.signature(callee).parameters)
        except (TypeError, ValueError):
            continue
        pairs = [(names[i], a) for i, a in enumerate(node.args)
                 if i < len(names)]
        pairs += [(k.arg, k.value) for k in node.keywords if k.arg in names]
        for target, arg in pairs:
            if not (isinstance(arg, ast.Name) and arg.id in pset):
                continue
            shape = callee_shape(callee, target, depth - 1)
            if shape.evidence is not None and shape.established:
                out.setdefault(arg.id, []).append(Evidence(
                    "body use", shape.evidence.shape,
                    f"passed to {callee.__name__}({target}), "
                    f"{shape.evidence.detail}"))
    return out


def callee_shape(fn, param: str, depth: int = 0) -> ParameterShape:
    """Intent:
        The shape of one parameter of a plain Python function, read from
        its annotation, a type marker, its default and its body (no
        claim domain applies).
    """
    from .analysis import _param_kinds, signature_kinds
    fdef, offset = _function_def(fn)
    try:
        stated = signature_kinds(fn, [param])[0]
    except Exception:
        stated = {}
    body_kinds = (_param_kinds(_without_annotations(fdef), [param])
                  if fdef is not None else {})
    return shape_of(fn, param, stated_kind=stated.get(param),
                    body=(body_evidence(fn, fdef, [param], body_kinds, depth,
                                        offset)
                          .get(param, []) if fdef is not None else []))


def _without_annotations(fdef):
    """`fdef` with its parameters' annotations removed, so its kinds are
    the body's own."""
    import copy
    bare = copy.deepcopy(fdef)
    for a in [*bare.args.posonlyargs, *bare.args.args, *bare.args.kwonlyargs]:
        a.annotation = None
    return bare


def shape_of(fn, param: str, *, bound=None, written: bool = False,
             stated_kind: "str | None" = None, receiver: "str | None" = None,
             body: "list | tuple" = ()) -> ParameterShape:
    """Intent:
        The shape of `param` from the evidence for it, in
        `EVIDENCE_ORDER`: a domain `bound` (`written` when the claim
        wrote it, else inferred into the claim's domain), a type marker
        on `fn`'s signature, the annotation's kind `stated_kind`, the
        class of a `receiver` instance, the default value, and the body
        `body` evidence. The first piece found is the shape; any later
        one naming another shape disagrees with it, except that a domain
        bound or a marker is never contradicted by a use read from the
        code.
    """
    found: list = []
    if bound is not None:
        found.append(Evidence("claim domain" if written else "inferred domain",
                              _bound_shape(bound), "bound in the claim"
                              if written else "a domain its annotation, "
                              "default or guard states"))
    marker = _marker_shape(fn, param)
    if marker is not None:
        found.append(marker)
    shape = kind_shape(stated_kind)
    if shape is not None:
        found.append(Evidence("annotation", shape,
                              f"annotated {_annotation_words(fn, param)}"))
    if receiver is not None:
        found.append(Evidence("receiver", "instance",
                              f"an instance of {receiver}"))
    default = _default_of(fn, param)
    if default is not inspect.Parameter.empty:
        shape = _default_shape(default)
        if shape is not None:
            found.append(Evidence("default", shape, f"default {default!r}"))
    found.extend(body)
    if not found:
        return ParameterShape(param, None)
    first = found[0]
    if first.source in ("claim domain", "inferred domain", "type marker",
                        "receiver"):
        return ParameterShape(param, first, tuple(found))
    disagree = tuple(e for e in found[1:]
                     if e.firm and not _compatible(first.shape, e.shape))
    return ParameterShape(param, first, tuple(found), disagree)


def _compatible(a: str, b: str) -> bool:
    """Whether evidence naming shape `b` can describe a value of shape
    `a`: the same shape, a bool among the numbers, or a use (`number`
    arithmetic, `sequence` indexing) a sequence or table also supports
    as an array."""
    if a == b or {a, b} == {"bool", "number"}:
        return True
    if a in ("sequence", "table") and b in ("number", "sequence", "mapping"):
        return True
    if a == "mapping" and b == "sequence":
        return True
    if a == "string" and b == "sequence":
        return True
    return a == "instance"


def _bound_shape(bound) -> str:
    """The shape a domain bound draws: a sequence for a space (`R^n`),
    else the bound's own values' shape, a number when it states none."""
    if getattr(bound, "dims", ()):
        return "sequence"
    base = getattr(bound, "base_type", None)
    if base == "S":
        return "string"
    if base == "L":
        return "language member"
    if isinstance(bound, frozenset):
        members = [v for v in bound if v is not None]
        if members and all(isinstance(v, str) for v in members):
            return "string"
        if members and all(isinstance(v, bool) for v in members):
            return "bool"
    return "number"


def _marker_shape(fn, param: str) -> "Evidence | None":
    """A mathema type marker's evidence for `param`, or None."""
    from .types import domain_from_signature, shapes_from_signature
    try:
        if param in (shapes_from_signature(fn, guards=False) or {}):
            return Evidence("type marker", "sequence", "a shape marker")
        if param in domain_from_signature(fn, guards=False):
            return Evidence("type marker", "number", "a bound marker")
    except Exception:
        return None
    return None


def _default_of(fn, param: str):
    """`param`'s default in `fn`'s signature, or `Parameter.empty`."""
    from ._signatures import callable_signature
    try:
        p = callable_signature(fn).parameters.get(param)
    except (TypeError, ValueError):
        return inspect.Parameter.empty
    return inspect.Parameter.empty if p is None else p.default


def _annotation_words(fn, param: str) -> str:
    """`param`'s annotation as source text."""
    from ._signatures import callable_signature
    try:
        p = callable_signature(fn).parameters.get(param)
    except (TypeError, ValueError):
        p = None
    if p is None or p.annotation is inspect.Parameter.empty:
        return "with a type"
    from ._annotation_text import annotation_text
    return annotation_text(p.annotation)


def definition_place(fn) -> "tuple[str, str]":
    """`(file:line, the def line)` for `fn`'s definition, or
    `('<unknown>', '')` when its source cannot be read."""
    target = inspect.unwrap(fn)
    try:
        _lines, start = inspect.getsourcelines(target)
    except (OSError, TypeError):
        return "<unknown>", ""
    fdef, offset = _function_def(fn)
    line = (fdef.lineno + offset) if fdef is not None else start
    return _place(fn, line), _source_line(fn, line)


def not_established_text(fn, shape: ParameterShape) -> str:
    """Intent:
        The diagnostic for a parameter that is not drawn: a title, the
        function's location and definition line, and the fix.
    """
    p = shape.param
    place, line = definition_place(fn)
    quoted = f' "{line}"' if line else ""
    if place == "<unknown>":
        name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", "f")
        return (f"shape of parameter {p} is not established (the source of "
                f"{name} is not available): nothing in its signature says "
                f"what kind of value it takes; bind {p} in the claim (for {p} "
                f"in ...), or annotate it")
    if shape.disagree:
        first = shape.evidence
        assert first is not None
        other = shape.disagree[0]
        return (f"shape of parameter {p} is not established "
                f"({place}{quoted}): {first.detail} "
                f"({_SHAPE_WORDS.get(first.shape, first.shape)}), but "
                f"{other.detail} ({_SHAPE_WORDS.get(other.shape, other.shape)}); "
                f"bind {p} in the claim, or make its annotation and its use "
                f"agree")
    return (f"shape of parameter {p} is not established ({place}{quoted}): "
            f"no annotation, default or use in the body says what kind of "
            f"value it takes; bind {p} in the claim (for {p} in ...), or "
            f"annotate it")


def wrong_shape_use(fn, values: dict, exc: BaseException) -> "tuple[str, int] | None":
    """Intent:
        `(param, line)` when `exc`, a TypeError or AttributeError, was
        raised by an operation in `fn`'s own body (not in a function it
        calls) that applies directly to `param`'s value, `values[param]`:
        the value indexed, sliced, iterated, measured, read for an
        attribute, called, put under an operator or passed to a builtin
        there, the message naming the value's type, and `param` never
        rebound in the body. None otherwise.
    """
    if not isinstance(exc, (TypeError, AttributeError)):
        return None
    target = inspect.unwrap(fn)
    code = getattr(target, "__code__", None)
    tb = exc.__traceback__
    if code is None or tb is None:
        return None
    last = None
    while tb is not None:
        last = tb
        tb = tb.tb_next
    if last is None or last.tb_frame.f_code is not code:
        return None
    try:
        positions = list(code.co_positions())[last.tb_lasti // 2]
    except (IndexError, AttributeError):
        return None
    fdef, offset = _function_def(fn)
    if fdef is None or positions[0] is None:
        return None
    from .analysis import param_uses
    rebound = param_uses(fdef, list(values)).assigned
    message = str(exc)
    line = positions[0]
    for node in ast.walk(fdef):
        if not _at(node, positions, offset, fn):
            continue
        for name in _direct_operands(node):
            if name not in values or name in rebound:
                continue
            if f"'{type(values[name]).__name__}'" in message:
                return name, line
    return None


def _at(node, positions, offset: int, fn) -> bool:
    """Whether `node` spans exactly the source range `positions` names
    (file lines; columns of the dedented source shifted back)."""
    lineno, end_lineno, col, end_col = positions
    if not hasattr(node, "lineno") or node.lineno + offset != lineno \
            or getattr(node, "end_lineno", None) is None \
            or node.end_lineno + offset != end_lineno:
        return False
    indent = _indent(fn)
    return (node.col_offset + indent == col
            and node.end_col_offset + indent == end_col)


def _indent(fn) -> int:
    """The indentation `fn`'s source carries in its file."""
    try:
        lines, _start = inspect.getsourcelines(inspect.unwrap(fn))
    except (OSError, TypeError):
        return 0
    first = next((ln for ln in lines if ln.strip()), "")
    return len(first) - len(first.lstrip())


def _direct_operands(node) -> list:
    """The parameter names an operation node applies to directly."""
    def name(n):
        return n.id if isinstance(n, ast.Name) else None
    found: list = []
    if isinstance(node, ast.Name):
        found.append(node.id)
    elif isinstance(node, (ast.Subscript, ast.Attribute)):
        found.append(name(node.value))
    elif isinstance(node, ast.BinOp):
        found += [name(node.left), name(node.right)]
    elif isinstance(node, ast.UnaryOp):
        found.append(name(node.operand))
    elif isinstance(node, ast.Compare):
        found += [name(n) for n in (node.left, *node.comparators)]
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            found.append(name(node.func.value))
        found.append(name(node.func))
        found += [name(a) for a in node.args]
        found += [name(k.value) for k in node.keywords]
    return [n for n in found if n is not None]


def parameter_shapes(fn, facts, params, cj_domain: dict,
                     written: "set | frozenset" = frozenset(),
                     receivers: "dict | None" = None) -> dict:
    """Intent:
        `{param: ParameterShape}` for each of `params` of `fn`: the
        claim's domain `cj_domain` (`written` names the parameters the
        claim itself binds), the signature's markers and annotations, the
        instances `receivers` names (`{param: class name}`), the
        defaults, and the body read from `fn`'s source.
    """
    from .analysis import _param_kinds, signature_kinds
    params = list(params)
    try:
        stated = signature_kinds(fn, params)[0]
    except Exception:
        stated = {}
    fdef, offset = _function_def(fn)
    body: dict = {}
    if fdef is not None:
        read = _with_copies_read_through(fdef, params)
        body_kinds = _param_kinds(_without_annotations(read), params)
        body = body_evidence(fn, read, params, body_kinds, 1, offset)
    for p, found in (getattr(facts, "runtime_types", None) or {}).items():
        shape = kind_shape(found[0].kind) if found else None
        if p in body and shape is not None and kind_shape(stated.get(p)) is None:
            body[p].insert(0, Evidence("body use", shape,
                                       "the body uses it as "
                                       + (found[0].adapter or "an array")))
    receivers = receivers or {}
    out = {p: shape_of(fn, p, bound=cj_domain.get(p), written=p in written,
                       stated_kind=stated.get(p),
                       receiver=receivers.get(p), body=body.get(p, ()))
           for p in params}
    if fdef is not None:
        loaded = {n.id for n in ast.walk(fdef)
                  if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        for p, shape in out.items():
            if shape.evidence is None and p not in loaded:
                out[p] = ParameterShape(p, Evidence(
                    "not read by the body", "any", "the body never reads it"))
    return out


def _with_copies_read_through(fdef, params: list):
    """Intent:
        `fdef` with each read of a plain local copy of a parameter (a
        statement `local = param`, the only binding of `local` before
        that read, `param` never rebound) read as the parameter itself,
        from the line after the copy through the line of the first
        statement that binds `local` again.
    """
    import copy
    from .analysis import param_uses
    rebound = param_uses(fdef, params).assigned
    stores: dict = {}
    copies: dict = {}
    for node in ast.walk(fdef):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and isinstance(node.value, ast.Name) \
                and node.value.id in params and node.value.id not in rebound:
            copies.setdefault(node.targets[0].id, []).append(node)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            stores.setdefault(node.id, []).append(node.lineno)
    spans: dict = {}
    for local, made in copies.items():
        if len(made) != 1 or local in params:
            continue
        line = made[0].lineno
        if any(at < line for at in stores.get(local, ())):
            continue
        later = [at for at in stores.get(local, ()) if at > line]
        spans[local] = (made[0].value.id, line, min(later) if later else None)
    if not spans:
        return fdef

    class _ReadThrough(ast.NodeTransformer):
        def visit_Name(self, node):
            span = spans.get(node.id)
            if span is None or not isinstance(node.ctx, ast.Load):
                return node
            param, start, end = span
            if node.lineno > start and (end is None or node.lineno <= end):
                return ast.copy_location(ast.Name(id=param, ctx=ast.Load()),
                                         node)
            return node

    return _ReadThrough().visit(copy.deepcopy(fdef))


def generated_ordering(fn) -> "tuple[str, type] | None":
    """Intent:
        `(other, class)` when `fn` is an ordering method (`__lt__`,
        `__le__`, `__gt__`, `__ge__`) that `dataclasses` generated for a
        class declared with `order=True`: compiled from generated source
        (`<string>`) and the very function the class binds under that
        name. Such a method compares two instances of the class field by
        field, so its second parameter `other` is an instance of the
        class. None for any other function, an override included.
    """
    name = getattr(fn, "__name__", "")
    if name not in ("__lt__", "__le__", "__gt__", "__ge__"):
        return None
    code = getattr(fn, "__code__", None)
    if code is None or code.co_filename != "<string>":
        return None
    from .runtime_types._receivers import method_receiver
    receiver = method_receiver(fn)
    if receiver is None:
        return None
    cls = receiver[1]
    params = getattr(cls, "__dataclass_params__", None)
    if params is None or not getattr(params, "order", False) \
            or cls.__dict__.get(name) is not fn:
        return None
    try:
        names = list(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        return None
    return (names[1], cls) if len(names) == 2 else None


def definition_line_text(fn, line: int) -> "tuple[str, str]":
    """`(file:line, the line's text)` for a line of `fn`'s file."""
    return _place(fn, line), _source_line(fn, line)


def element_shape_missing(fn, shape: ParameterShape) -> "str | None":
    """Intent:
        The diagnostic for a sequence parameter whose annotation names
        element types mathema does not draw (`list[Event]`,
        `list[list[float]]`, `Sequence[dict]`), when only the annotation
        establishes the shape; None otherwise, and for a sequence whose
        elements are one scalar type (`int`, `float`, `bool`, `str`,
        `complex`) or that names no element type.
    """
    evidence = shape.evidence
    if evidence is None or evidence.source != "annotation" \
            or evidence.shape != "sequence":
        return None
    import typing
    try:
        hint = typing.get_type_hints(inspect.unwrap(fn)).get(shape.param)
    except Exception:
        return None
    if hint is None:
        return None
    from .runtime_types import annotated_element
    from .types import _optional_parts
    _optional, inner = _optional_parts(hint)
    args = [a for a in typing.get_args(inner) if a is not Ellipsis]
    origin = typing.get_origin(inner)
    if not args or origin is None \
            or (getattr(origin, "__module__", "") or "").split(".")[0] == "numpy":
        return None
    if annotated_element(fn, shape.param) is not None:
        return None
    p = shape.param
    place, line = definition_place(fn)
    quoted = f' "{line}"' if line else ""
    return (f"shape of the elements of parameter {p} is not established "
            f"({place}{quoted}): {evidence.detail} names elements mathema "
            f"does not draw; bind {p} in the claim (for {p} in L[...]), "
            f"or annotate its elements as numbers or strings")
