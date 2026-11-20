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
disagreement. An annotation, or a firm number use, against uses in the
body settles it, and so does a firm use against the default: the
parameter is drawn in the settling shape, and a raise at a use against
it is a finding. An unsettled disagreement is not drawn, nor is a
parameter with no evidence at all. A claim domain, an inferred domain, a type marker
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
    #: the container a sequence is, `tuple` or `list`, when the evidence
    #: names one (`(0,) + xs`), else None
    container: "str | None" = None


@dataclass(frozen=True)
class ParameterShape:
    """Intent:
        The shape a parameter is drawn as and the evidence for it: the
        first piece in `EVIDENCE_ORDER` (`evidence`), every piece found
        (`found`), and the pieces that name another shape than the
        first (`disagree`). `evidence` is None when nothing establishes
        the shape. A disagreement one piece settles (`settled`, see
        `_settling`) draws that piece's shape, and `disagree` then holds
        the pieces against it.
    """
    param: str
    evidence: "Evidence | None"
    found: tuple = ()
    disagree: tuple = ()
    settled: bool = False

    @property
    def established(self) -> bool:
        """Intent:
            Whether the parameter may be drawn: some evidence, none of it
            disagreeing, or a disagreement it settles.
        """
        return self.evidence is not None and (not self.disagree or self.settled)

    @property
    def stated(self) -> bool:
        """Intent:
            Whether the shape rests on evidence an author stated.
        """
        return self.evidence is not None and self.evidence.source in STATED

    def as_record(self) -> dict:
        """Intent:
            The shape and its evidence as plain values for a record.
        """
        if self.evidence is None:
            return {"source": "none"}
        out = {"source": self.evidence.source, "shape": self.evidence.shape,
               "detail": self.evidence.detail}
        if self.disagree:
            out["disagree"] = [{"source": e.source, "shape": e.shape,
                                "detail": e.detail} for e in self.disagree]
        if self.settled:
            out["settled"] = True
        return out


def kind_shape(kind: "str | None") -> "str | None":
    """Intent:
        The shape a `Facts.param_kinds` kind names, None for `unknown`.
    """
    return _KIND_SHAPES.get(kind or "")


def _default_shape(value) -> "str | None":
    """Intent:
        The shape a default value states, None for any other value (None
        included).
    """
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


def drawn_container(fn, shape: "ParameterShape | None") -> "type | None":
    """Intent:
        `tuple` when a sequence parameter's shape rests on a tuple
        default, or on a use that names a tuple (`(0,) + xs`), so each
        draw of it is passed as a tuple; None otherwise.
    """
    if shape is None or shape.evidence is None \
            or shape.evidence.shape != "sequence":
        return None
    if shape.evidence.source == "default":
        return tuple if isinstance(_default_of(fn, shape.param), tuple) else None
    if any(e.container == "tuple" for e in shape.found if e.shape == "sequence"):
        return tuple
    return None


def _underlying(fn):
    """Intent:
        The plain function `fn` runs: unwrapped through its wrappers
        (`__wrapped__`), through each `functools.partial` to the
        function it binds arguments of, and for an instance of a class
        that defines `__call__`, that method bound to it.
    """
    import functools
    target = inspect.unwrap(fn)
    while isinstance(target, functools.partial):
        target = inspect.unwrap(target.func)
    if getattr(target, "__code__", None) is None \
            and inspect.isfunction(getattr(type(target), "__call__", None)):
        target = inspect.unwrap(target.__call__)
    return target


def _function_def(fn) -> "tuple[Any, int]":
    """Intent:
        `fn`'s definition parsed from its source, with the line offset
        that maps its line numbers onto the file's, or `(None, 0)` when
        the source cannot be read.
    """
    target = _underlying(fn)
    code = getattr(target, "__code__", None)
    if code is None:
        return _parsed_def(target)
    if code not in _DEFS:
        _DEFS[code] = _parsed_def(target)
    return _DEFS[code]


#: each function's parsed definition, by code object
_DEFS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _parsed_def(target) -> "tuple[Any, int]":
    """Intent:
        `_function_def` without the cache: the first function definition
        in `target`'s source, or for a lambda the one lambda in its
        source lines whose parameters are the lambda's own.
    """
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
    if getattr(target, "__name__", "") == "<lambda>":
        lambdas = [node for node in ast.walk(tree)
                   if isinstance(node, ast.Lambda)
                   and _arg_names(node.args) == _code_arg_names(target)]
        if len(lambdas) == 1:
            return lambdas[0], max(start, 1) - 1
        chosen = _lambda_by_position(target, lambdas, max(start, 1) - 1,
                                     _indent(target))
        if chosen is not None:
            return chosen, max(start, 1) - 1
    return None, 0


def _lambda_by_position(target, lambdas: list, offset: int, indent: int):
    """Intent:
        The one of `lambdas` (nodes parsed from `target`'s source lines,
        `offset` lines and `indent` columns from the file's own) whose
        source span holds every source range `target`'s code records
        (an empty range, such as the one its entry carries, says
        nothing), the innermost when several do; None when none does,
        or when two are equally inner.
    """
    code = getattr(target, "__code__", None)
    try:
        spots = [(line, col) for line, end, col, end_col in code.co_positions()
                 if None not in (line, end, col, end_col)
                 and (end, end_col) > (line, col)]
    except AttributeError:
        return None
    if not spots:
        return None
    holding = []
    for node in lambdas:
        first = (node.lineno + offset, node.col_offset + indent)
        last = (node.end_lineno + offset, node.end_col_offset + indent)
        if all(first <= spot <= last for spot in spots):
            holding.append((last[0] - first[0], last[1] - first[1], node))
    if not holding:
        return None
    holding.sort(key=lambda h: h[:2])
    if len(holding) > 1 and holding[0][:2] == holding[1][:2]:
        return None
    return holding[0][2]


def _lambdas_alike(fn) -> int:
    """Intent:
        How many lambdas in a lambda's source lines take the same
        parameters as it does; 0 for any other function or when its
        source cannot be read.
    """
    target = _underlying(fn)
    if getattr(target, "__name__", "") != "<lambda>":
        return 0
    import textwrap
    try:
        lines, _start = inspect.getsourcelines(target)
        tree = ast.parse(textwrap.dedent("".join(lines)))
    except (OSError, TypeError, SyntaxError):
        return 0
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.Lambda)
               and _arg_names(node.args) == _code_arg_names(target))


def _arg_names(args) -> list:
    """Intent:
        The parameter names an `ast.arguments` declares, in order.
    """
    names = [a.arg for a in [*args.posonlyargs, *args.args]]
    if args.vararg is not None:
        names.append(args.vararg.arg)
    names += [a.arg for a in args.kwonlyargs]
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    return names


def _code_arg_names(fn) -> list:
    """Intent:
        The parameter names `fn`'s code object declares, in the order
        `_arg_names` reads them from source.
    """
    code = getattr(fn, "__code__", None)
    if code is None:
        return []
    count = code.co_argcount + code.co_kwonlyargcount \
        + bool(code.co_flags & inspect.CO_VARARGS) \
        + bool(code.co_flags & inspect.CO_VARKEYWORDS)
    names = list(code.co_varnames[:count])
    positional = code.co_argcount
    if code.co_flags & inspect.CO_VARARGS:
        star = names[positional + code.co_kwonlyargcount]
        names = [*names[:positional], star,
                 *names[positional:positional + code.co_kwonlyargcount],
                 *names[positional + code.co_kwonlyargcount + 1:]]
    return names


def _source_line(fn, line: int) -> str:
    """Intent:
        The text of `line` in `fn`'s file, stripped, or ''.
    """
    import linecache
    try:
        path = inspect.getsourcefile(_underlying(fn)) or ""
    except TypeError:
        return ""
    return linecache.getline(path, line).strip()


def _place(fn, line: int) -> str:
    """Intent:
        `file:line` for a line of `fn`'s file, the file by its base name.
    """
    import os
    try:
        path = inspect.getsourcefile(_underlying(fn)) or ""
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
        if shape == "sequence" and _read_only_for_array_attributes(fdef, p):
            # `x.shape[0]` indexes the attribute, not `x`
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
        for line, (text, made) in uses.container.get(p, ()):
            out[p].append(Evidence("body use", "sequence",
                                   f"`{text}` on line {line + offset}",
                                   container=made))
        for form, name in methods.get(p, ()):
            shape = _method_shape(form, name)
            written = f"`{p}.{name}{'()' if form != 'attr' else ''}`"
            if shape is not None:
                out[p].append(Evidence("body use", shape, written))
    if depth > 0:
        for p, ev in _passed_on(fn, fdef, params, depth).items():
            out[p].extend(ev)
    return out


def _read_only_for_array_attributes(fdef, p: str) -> bool:
    """Intent:
        Whether every read of `p` in `fdef` reads an array attribute off
        it (`p.shape`, `p.ndim`, `p.size`, `p.flat`, `p.T`): evidence
        about that attribute, and not that `p` itself is a sequence.
    """
    from .analysis import _ARRAY_ATTRS
    reads = [n for n in ast.walk(fdef)
             if isinstance(n, ast.Name) and n.id == p
             and isinstance(n.ctx, ast.Load)]
    through = {id(n.value) for n in ast.walk(fdef)
               if isinstance(n, ast.Attribute) and n.attr in _ARRAY_ATTRS
               and isinstance(n.value, ast.Name) and n.value.id == p}
    return bool(reads) and all(id(n) in through for n in reads)


def _method_shape(form: str, name: str) -> "str | None":
    """Intent:
        The one shape among the built-in value types whose type has the method
        or attribute `name`, None when several or none do.
    """
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
    scope = getattr(_underlying(fn), "__globals__", None) or {}
    out: dict = {}
    pset = set(params)
    for node in ast.walk(fdef):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        callee = scope.get(node.func.id)
        if not inspect.isfunction(callee) or callee is _underlying(fn):
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
    """Intent:
        `fdef` with its parameters' annotations removed, so its kinds are the
        body's own.
    """
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
    if disagree:
        settling = _settling(found)
        if settling is not None:
            return ParameterShape(param, settling, tuple(found),
                                  _against(found, settling), settled=True)
    return ParameterShape(param, first, tuple(found), disagree)


def _against(found: list, piece: Evidence) -> tuple:
    """Intent:
        The firm pieces of `found` that name a shape `piece`'s shape
        cannot describe.
    """
    return tuple(e for e in found if e is not piece and e.firm
                 and not _compatible(piece.shape, e.shape))


def _settling(found: list) -> "Evidence | None":
    """Intent:
        The piece of evidence that settles a disagreement among `found`,
        or None: the annotation, when every piece against it is a body
        use; else a firm number use in the body, when every piece
        against it is a body use or the default; else a firm body use,
        when only the default is against it. The value is drawn in that
        piece's shape, and a raise at a use against it stands as a
        finding.
    """
    ranked = [
        *[(e, {"body use"}) for e in found if e.source == "annotation"],
        *[(e, {"body use", "default"}) for e in found
          if e.source == "body use" and e.firm and e.shape == "number"],
        *[(e, {"default"}) for e in found
          if e.source == "body use" and e.firm]]
    for piece, allowed in ranked:
        if all(e.source in allowed for e in _against(found, piece)):
            return piece
    return None


def _compatible(a: str, b: str) -> bool:
    """Intent:
        Whether evidence naming shape `b` can describe a value of shape `a`:
        the same shape, a bool among the numbers, or a use (`number`
        arithmetic, `sequence` indexing) a sequence or table also supports as
        an array.
    """
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
    """Intent:
        The shape a domain bound draws: a sequence for a space (`R^n`), else
        the bound's own values' shape, a number when it states none.
    """
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
    """Intent:
        A mathema type marker's evidence for `param`, or None.
    """
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
    """Intent:
        `param`'s default in `fn`'s signature, or `Parameter.empty`.
    """
    from ._signatures import callable_signature
    try:
        p = callable_signature(fn).parameters.get(param)
    except (TypeError, ValueError):
        return inspect.Parameter.empty
    return inspect.Parameter.empty if p is None else p.default


def _annotation_words(fn, param: str) -> str:
    """Intent:
        `param`'s annotation as source text.
    """
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
    """Intent:
        `(file:line, the def line)` for `fn`'s definition, or `('<unknown>',
        '')` when its source cannot be read.
    """
    target = _underlying(fn)
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
        function's location and definition line (or that its source is
        not available), and the fix.
    """
    p = shape.param
    place, line = definition_place(fn)
    if place == "<unknown>":
        where = f"the source of {_function_name(fn)} is not available"
    else:
        where = place + (f' "{line}"' if line else "")
    first = shape.evidence
    if shape.disagree and first is not None:
        other = shape.disagree[0]
        return (f"shape of parameter {p} is not established ({where}): "
                f"{first.detail} ({_SHAPE_WORDS.get(first.shape, first.shape)}), "
                f"but {other.detail} "
                f"({_SHAPE_WORDS.get(other.shape, other.shape)}); bind {p} in "
                f"the claim, or make {_sources_text([first, *shape.disagree])} "
                f"agree")
    if place == "<unknown>":
        return (f"shape of parameter {p} is not established ({where}): "
                f"nothing in its signature says what kind of value it takes; "
                f"bind {p} in the claim (for {p} in ...), or annotate it")
    if _function_def(fn)[0] is None and _lambdas_alike(fn) > 1:
        return (f"shape of parameter {p} is not established ({where}): "
                f"the line defines more than one lambda taking these "
                f"parameters, and which one this is cannot be told; bind {p} "
                f"in the claim (for {p} in ...), or define the function with "
                f"def")
    return (f"shape of parameter {p} is not established ({where}): "
            f"no annotation, default or use in the body says what kind of "
            f"value it takes; bind {p} in the claim (for {p} in ...), or "
            f"annotate it")


def _function_name(fn) -> str:
    """Intent:
        `fn`'s qualified name, read through wrappers and partials, else
        its type's name.
    """
    target = _underlying(fn)
    return (getattr(target, "__qualname__", None)
            or getattr(target, "__name__", None) or type(fn).__name__)


def _sources_text(pieces: list) -> str:
    """Intent:
        The sources of the evidence `pieces` as a reader would name
        them, each once, joined with commas and a final "and": "its
        annotation", "its default", and each use in the body by its
        text when it has one ("its use `x[0]` on line 3").
    """
    names: list = []
    for e in pieces:
        if e.source == "annotation":
            name = "its annotation"
        elif e.source == "default":
            name = "its default"
        elif e.source == "body use" and e.detail.startswith("`"):
            name = f"its use {e.detail}"
        elif e.source == "body use" and e.detail.startswith("passed to "):
            name = f"its use {e.detail.split(',')[0]}"
        elif e.source == "body use":
            name = "its use in the body"
        else:
            name = f"its {e.source}"
        if name not in names:
            names.append(name)
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def wrong_shape_use(fn, values: dict, exc: BaseException,
                    drawn: "set | frozenset | None" = None) -> "tuple[str, int] | None":
    """Intent:
        `(param, line)` when `exc`, a TypeError or AttributeError, was
        raised by an operation in `fn`'s own body (not in a function it
        calls) that applies directly to `param`'s value, `values[param]`:
        the value indexed, sliced, iterated, measured, read for an
        attribute, called, put under an operator, used as a key or
        passed to a builtin there, the message naming the value's type,
        and `param` never rebound in the body. `drawn` names the
        parameters whose values were drawn (every one of `values` when
        None); only a drawn parameter is named. None otherwise, and
        when the message also names the type of another operand whose
        value was not drawn (a literal, a held value, a default), whose
        type then explains the raise as well.
    """
    if not isinstance(exc, (TypeError, AttributeError)):
        return None
    target = _underlying(fn)
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
    drawn = set(values) if drawn is None else set(drawn)
    frame = last.tb_frame
    runtime = {**frame.f_globals, **dict(frame.f_locals)}
    for node in ast.walk(_with_copies_read_through(fdef, list(values))):
        if not _at(node, positions, offset, fn):
            continue
        operands = _operand_nodes(node)
        names = [n for o in operands
                 if (n := _drawn_operand(o, values, drawn, runtime)) is not None]
        held = {t.__name__ for o in operands
                if _drawn_operand(o, values, drawn, runtime) is None
                and (t := _held_type(fn, o, values, runtime)) is not None}
        for name in names:
            if name in rebound:
                continue
            type_name = type(runtime[name]).__name__
            if not _names_type(message, type_name):
                continue
            if any(h != type_name and _names_type(message, h) for h in held):
                return None
            return name, line
    return None


#: the built-in types of each shape's values
_SHAPE_TYPES = {"number": (int, float, complex), "bool": (bool,),
                "string": (str,), "sequence": (list, tuple),
                "mapping": (dict,)}


def attribute_no_shape_has(shape: ParameterShape, exc: BaseException) -> bool:
    """Intent:
        Whether `exc` is an AttributeError for an attribute no built-in
        type of `shape`'s values has, while firm evidence (a literal
        use, a default, an index or a mapping read) establishes that
        shape: the value was of the shape the code states, and the
        attribute is missing from every value of it.
    """
    name = getattr(exc, "name", None)
    evidence = shape.evidence
    if not isinstance(exc, AttributeError) or not name or evidence is None:
        return False
    types = _SHAPE_TYPES.get(evidence.shape)
    if types is None or not any(e.firm and e.shape == evidence.shape
                                for e in shape.found):
        return False
    return not any(hasattr(t, name) for t in types)


def _names_type(message: str, type_name: str) -> bool:
    """Intent:
        Whether an error message names the type `type_name` as a word,
        bare, in single quotes or in double quotes.
    """
    import re
    return re.search(rf"(?<![\w.]){re.escape(type_name)}(?!\w)",
                     message) is not None


def _at(node, positions, offset: int, fn) -> bool:
    """Intent:
        Whether `node` spans exactly the source range `positions` names (file
        lines; columns of the dedented source shifted back).
    """
    lineno, end_lineno, col, end_col = positions
    if not hasattr(node, "lineno") or node.lineno + offset != lineno \
            or getattr(node, "end_lineno", None) is None \
            or node.end_lineno + offset != end_lineno:
        return False
    indent = _indent(fn)
    return (node.col_offset + indent == col
            and node.end_col_offset + indent == end_col)


def _indent(fn) -> int:
    """Intent:
        The indentation `fn`'s source carries in its file.
    """
    try:
        lines, _start = inspect.getsourcelines(_underlying(fn))
    except (OSError, TypeError):
        return 0
    first = next((ln for ln in lines if ln.strip()), "")
    return len(first) - len(first.lstrip())


def _operand_nodes(node) -> list:
    """Intent:
        The operand nodes an operation node applies to directly.
    """
    found: list = []
    if isinstance(node, ast.Name):
        found.append(node)
    elif isinstance(node, ast.Subscript):
        found += [node.value, node.slice]
    elif isinstance(node, ast.Attribute):
        found.append(node.value)
    elif isinstance(node, ast.Dict):
        found += [k for k in node.keys if k is not None]
    elif isinstance(node, ast.Set):
        found += list(node.elts)
    elif isinstance(node, ast.BinOp):
        found += [node.left, node.right]
    elif isinstance(node, ast.UnaryOp):
        found.append(node.operand)
    elif isinstance(node, ast.Compare):
        found += [node.left, *node.comparators]
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            found.append(node.func.value)
        found.append(node.func)
        found += list(node.args)
        found += [k.value for k in node.keywords]
    return found


def _direct_operands(node) -> list:
    """Intent:
        The names an operation node applies to directly.
    """
    return [n.id for n in _operand_nodes(node) if isinstance(n, ast.Name)]


_LITERAL_TYPES = {ast.List: list, ast.Tuple: tuple, ast.Dict: dict,
                  ast.Set: set, ast.JoinedStr: str, ast.ListComp: list,
                  ast.SetComp: set, ast.DictComp: dict}


def _drawn_operand(operand, values: dict, drawn: set, runtime: dict) -> "str | None":
    """Intent:
        The drawn parameter an operand is, or None: a name (or a local
        copy read through as the parameter) that the raising call's
        frame (`runtime`, its globals and locals) binds to the very
        object the parameter holds there, not to another value.
    """
    if not isinstance(operand, ast.Name) or operand.id not in values \
            or operand.id not in drawn or operand.id not in runtime:
        return None
    local = getattr(operand, "_local", operand.id)
    if local not in runtime or runtime[local] is not runtime[operand.id]:
        return None
    return operand.id


def _held_type(fn, operand, values: dict, runtime: dict) -> "type | None":
    """Intent:
        The type of an operand that is not a drawn value: a literal, a
        name the raising call's frame binds (`runtime`, its globals and
        locals), or a parameter left at its default. None for any other
        name.
    """
    if isinstance(operand, ast.Constant):
        return type(operand.value)
    if type(operand) in _LITERAL_TYPES:
        return _LITERAL_TYPES[type(operand)]
    if not isinstance(operand, ast.Name):
        return None
    local = getattr(operand, "_local", operand.id)
    if local in runtime:
        return type(runtime[local])
    if operand.id in values:
        return type(values[operand.id])
    default = _default_of(fn, operand.id)
    return None if default is inspect.Parameter.empty else type(default)


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
        loaded = {n.id for n in ast.walk(read)
                  if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                  and not getattr(n, "_copy_source", False)}
        copied = {n.id for n in ast.walk(read)
                  if getattr(n, "_copy_source", False)}
        for p, shape in out.items():
            if shape.evidence is None and p not in loaded:
                out[p] = ParameterShape(p, Evidence(
                    "not read by the body", "any",
                    "the body copies it to a local it never reads"
                    if p in copied else "the body never reads it"))
    return out


def _with_copies_read_through(fdef, params: list):
    """Intent:
        `fdef` with each read of a plain local copy of a parameter read
        as the parameter itself. A copy is a statement in the function's
        own scope that binds a local to the parameter's value (`local =
        param`, or a name of `a, local = x, param` matched by position),
        the only binding of `local` before it, the parameter
        never rebound. A read of `local` after the copy's line is read
        through unless another binding of `local` may come before it: a
        binding on an earlier line, or on the same line in another
        statement, or one anywhere in a loop around both. Only reads in the
        function's own scope are read through; a local a nested scope
        declares `nonlocal`, or assigns with `:=`, is never read
        through, nor is one a nested scope reads or binds when the
        function binds it again after the copy. The returned tree marks
        the copy's own read of the parameter (`_copy_source`) when no
        read of the local is left that is not read through, in any
        scope, and is `fdef` itself when the body makes no copy.
    """
    import copy
    from .analysis import param_uses
    rebound = param_uses(fdef, params).assigned
    read = copy.deepcopy(fdef)
    parents = _own_scope_parents(read)
    bindings: dict = {}
    copies: dict = {}
    for node in _own_scope(read):
        for local, source in _copy_pairs(node, params, rebound):
            copies.setdefault(local, []).append((node, source))
        for bound in _bound_names(node):
            bindings.setdefault(bound, []).append(node)
    mentioned, rebinding = _nested_names(read)
    spans: dict = {}
    for local, made in copies.items():
        if len(made) != 1 or local in params or local in rebinding:
            continue
        stmt, source = made[0]
        others = [b for b in bindings.get(local, ())
                  if _owner(b, parents) is not stmt]
        if any(b.lineno <= stmt.lineno for b in others):
            continue
        if others and local in mentioned:
            continue
        spans[local] = (source, stmt, others)
    if not spans:
        return fdef
    for node in list(_own_scope(read)):
        if not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)):
            continue
        span = spans.get(node.id)
        if span is None:
            continue
        source, stmt, others = span
        if node.lineno <= stmt.end_lineno \
                or any(_may_precede(b, node, parents) for b in others):
            continue
        node._local = node.id
        node.id = source.id
    unread = {n.id for n in ast.walk(read)
              if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    for local, (source, _stmt, _others) in spans.items():
        if local not in unread:
            source._copy_source = True
    return read


def _copy_pairs(node, params: list, rebound) -> list:
    """Intent:
        `[(local, param Name node), ...]` for the plain copies one
        statement makes: `local = param`, and each `local` matched by
        position to a `param` in `a, local = x, param` (a tuple or list
        of names against a tuple or list of the same length).
    """
    if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
        return []
    target, value = node.targets[0], node.value
    if isinstance(target, ast.Name):
        pairs = [(target, value)]
    elif isinstance(target, (ast.Tuple, ast.List)) \
            and isinstance(value, (ast.Tuple, ast.List)) \
            and len(target.elts) == len(value.elts) \
            and not any(isinstance(e, ast.Starred) for e in target.elts):
        pairs = list(zip(target.elts, value.elts))
    else:
        return []
    return [(t.id, v) for t, v in pairs
            if isinstance(t, ast.Name) and isinstance(v, ast.Name)
            and v.id in params and v.id not in rebound]


def _own_scope_parents(fdef) -> dict:
    """Intent:
        `{id(node): parent}` for every node `_own_scope` yields from
        `fdef`, the parent of a top-level statement being `fdef`.
    """
    out: dict = {}
    body = fdef.body if isinstance(fdef.body, list) else [fdef.body]
    stack = [(n, fdef) for n in body]
    while stack:
        node, parent = stack.pop()
        out[id(node)] = parent
        inner = (_enclosing_parts(node) if isinstance(node, _NESTED_SCOPES)
                 else list(ast.iter_child_nodes(node)))
        stack.extend((n, node) for n in inner)
    return out


def _ancestors(node, parents: dict) -> list:
    """Intent:
        The chain of nodes enclosing `node` in its own scope, nearest first,
        `node` itself included.
    """
    chain = [node]
    while id(chain[-1]) in parents:
        chain.append(parents[id(chain[-1])])
    return chain


def _owner(binding, parents: dict):
    """Intent:
        The node whose execution makes `binding` take effect: the
        nearest enclosing statement, or the `except` handler or `case`
        whose name or pattern it is.
    """
    for node in _ancestors(binding, parents):
        if isinstance(node, (ast.stmt, ast.ExceptHandler, ast.match_case)):
            return node
    return binding


def _may_precede(binding, read, parents: dict) -> bool:
    """Intent:
        Whether `binding` may take effect before `read`: it lies in a
        loop that also holds the read, or it is on an earlier line, or
        on the read's line in another statement.
    """
    loops = [n for n in _ancestors(read, parents)
             if isinstance(n, (ast.For, ast.AsyncFor, ast.While))]
    around = {id(a) for a in _ancestors(binding, parents)}
    if any(id(n) in around for n in loops):
        return True
    if binding.lineno < read.lineno:
        return True
    if binding.lineno == read.lineno:
        return _owner(binding, parents) is not _owner(read, parents)
    return False


#: the nodes that open a scope of their own inside a function
_NESTED_SCOPES = (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef,
                  ast.ClassDef, ast.ListComp, ast.SetComp, ast.DictComp,
                  ast.GeneratorExp)


def _enclosing_parts(node) -> list:
    """Intent:
        The parts of a nested scope's node evaluated in the scope around
        it: a definition's decorators and defaults, a class's
        decorators, bases and keywords, a comprehension's first
        iterable.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        args = node.args
        return [*getattr(node, "decorator_list", ()), *args.defaults,
                *[d for d in args.kw_defaults if d is not None]]
    if isinstance(node, ast.ClassDef):
        return [*node.decorator_list, *node.bases,
                *[k.value for k in node.keywords]]
    return [node.generators[0].iter]


def _own_scope(fdef):
    """Intent:
        Every node `fdef`'s own scope evaluates, in source order: its
        body, the nodes that open a nested scope, and of each of those
        only the parts evaluated around it (`_enclosing_parts`).
    """
    body = fdef.body if isinstance(fdef.body, list) else [fdef.body]
    stack = list(reversed(body))
    while stack:
        node = stack.pop()
        yield node
        inner = (_enclosing_parts(node) if isinstance(node, _NESTED_SCOPES)
                 else list(ast.iter_child_nodes(node)))
        stack.extend(reversed(inner))


def _bound_names(node) -> list:
    """Intent:
        The names one node binds in the scope that runs it: an
        assignment or deletion target, an `except ... as` name, an
        import alias, a function or class name, a pattern capture, a
        parameter.
    """
    if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
        return [node.id]
    if isinstance(node, ast.ExceptHandler) and node.name:
        return [node.name]
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return [a.asname or a.name.split(".")[0] for a in node.names]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
        return [node.name]
    if isinstance(node, ast.MatchMapping) and node.rest:
        return [node.rest]
    if isinstance(node, ast.arg):
        return [node.arg]
    return []


def _nested_names(fdef) -> "tuple[set, set]":
    """Intent:
        `(mentioned, rebinding)` over the scopes nested in `fdef`: the
        names they read or bind, and the names they may bind in `fdef`'s
        own scope (declared `nonlocal` or `global`, or the target of a
        `:=`).
    """
    mentioned: set = set()
    rebinding: set = set()
    for node in _own_scope(fdef):
        if not isinstance(node, _NESTED_SCOPES):
            continue
        for inner in ast.walk(node):
            if inner is node:
                continue
            if isinstance(inner, ast.Name):
                mentioned.add(inner.id)
            elif isinstance(inner, (ast.Nonlocal, ast.Global)):
                rebinding.update(inner.names)
            else:
                mentioned.update(_bound_names(inner))
            if isinstance(inner, ast.NamedExpr) \
                    and isinstance(inner.target, ast.Name):
                rebinding.add(inner.target.id)
    return mentioned, rebinding


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
    """Intent:
        `(file:line, the line's text)` for a line of `fn`'s file.
    """
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
