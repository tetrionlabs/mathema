# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""KOINE to the liftable Python subset.

`render(document)` writes one Python function whose body is what the
derive route's lifters read: single-name assignments, tuple unpacking,
augmented assignment, `if`/`else`, `for` over a parameter or a
`range`, a guard as `if test: raise Type(...)`, `return`. Every
operator and function is spelled by its exact Python equivalent where
one exists (`//` for `division::floor`, `math.fmod` for
`remainder::truncation`, `round` for `rounding::ties_even`) and
otherwise by a helper from `koine.functions` bound under its alias
(`div_trunc`, `round_ties_up`, `sign`), so the rendered function
computes exactly what the interpreter does.

The result carries a map from rendered lines to the source lines in
the document's `at:` spans, the external names the body calls (with
their keys), and the exception names it raises.

`namespace(rendered)` is what the rendered body's names resolve in:
`math`, the helpers under their aliases, and one exception class per
name the body raises (subclassing the same-named builtin when one
exists). `materialise(rendered, key, bindings)` executes the rendered
source in a fresh module holding that namespace and registered under
`sys.modules`, with the source placed in `linecache` under a synthetic
filename, so `inspect.getsource` reads the rendered body.
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import linecache
import math
import re
import sys
import types
from dataclasses import dataclass, field
from typing import Callable

from .aliases import alias_of
from .document import Document
from .functions import HELPER_FUNCTIONS, helpers
from .syntax import Bool, Int, Name, Real, Str, Term


class RenderError(ValueError):
    """The document has no rendering in the liftable subset."""


@dataclass
class Rendered:
    name: str
    params: list
    source: str
    tree: ast.FunctionDef
    line_map: dict = field(default_factory=dict)    # rendered line -> source line
    externals: dict = field(default_factory=dict)   # bare name -> key
    exceptions: set = field(default_factory=set)    # exception type names raised


_BINARY_OPS = {
    "operator::binary::addition": ast.Add,
    "operator::binary::subtraction": ast.Sub,
    "operator::binary::multiplication": ast.Mult,
    "operator::binary::power": ast.Pow,
    "operator::binary::division::real": ast.Div,
    "operator::binary::division::floor": ast.FloorDiv,
    "operator::binary::remainder::floor": ast.Mod,
}

_COMPARE_OPS = {
    "operator::comparison::equal": ast.Eq,
    "operator::comparison::not_equal": ast.NotEq,
    "operator::comparison::less": ast.Lt,
    "operator::comparison::less_equal": ast.LtE,
    "operator::comparison::greater": ast.Gt,
    "operator::comparison::greater_equal": ast.GtE,
}

#: operators and functions spelled as a call to a Python function; the
#: rest are spelled as a call to their helper, by its alias
CALLS = {
    "operator::binary::remainder::truncation": "math.fmod",
    "function::root::square": "math.sqrt",
    "function::exponential::natural": "math.exp",
    "function::exponential::natural_minus_one": "math.expm1",
    "function::logarithm::natural": "math.log",
    "function::logarithm::binary": "math.log2",
    "function::logarithm::decimal": "math.log10",
    "function::logarithm::natural_one_plus": "math.log1p",
    "function::trigonometric::sine": "math.sin",
    "function::trigonometric::cosine": "math.cos",
    "function::trigonometric::tangent": "math.tan",
    "function::trigonometric::arcsine": "math.asin",
    "function::trigonometric::arccosine": "math.acos",
    "function::trigonometric::arctangent": "math.atan",
    "function::trigonometric::arctangent2": "math.atan2",
    "function::hyperbolic::sine": "math.sinh",
    "function::hyperbolic::cosine": "math.cosh",
    "function::hyperbolic::tangent": "math.tanh",
    "function::rounding::floor": "math.floor",
    "function::rounding::ceiling": "math.ceil",
    "function::rounding::truncation": "math.trunc",
    "function::rounding::ties_even": "round",
    "function::order::minimum": "min",
    "function::order::maximum": "max",
    "function::magnitude::absolute": "abs",
    "function::magnitude::hypotenuse": "math.hypot",
    "function::special::gamma": "math.gamma",
    "function::special::log_gamma": "math.lgamma",
    "function::special::factorial": "math.factorial",
    "function::special::error": "math.erf",
    "function::special::error_complement": "math.erfc",
    "function::integer::gcd": "math.gcd",
}

_HELPER_PATHS = frozenset(fn.__koine__ for fn in HELPER_FUNCTIONS)


def _call_spelling(path: str) -> str | None:
    """How a rendered body calls `path`: its entry in `CALLS`, else the
    alias of the helper that computes it."""
    if path in CALLS:
        return CALLS[path]
    if path in _HELPER_PATHS:
        return alias_of(path)
    return None


_CONSTANTS = {"constant::pi": "math.pi", "constant::e": "math.e",
              "constant::infinity": "math.inf"}

_AUGMENTED = {
    "operator::binary::addition": ast.Add,
    "operator::binary::subtraction": ast.Sub,
    "operator::binary::multiplication": ast.Mult,
    "operator::binary::division::real": ast.Div,
}

#: the Python annotation that reads back as each kind
_ANNOTATIONS = {"kind::scalar": "float", "kind::int": "int", "kind::bool": "bool",
                "kind::string": "str", "kind::sequence": "list[float]"}


def _dotted(path: str) -> ast.expr:
    parts = path.split(".")
    node: ast.expr = ast.Name(id=parts[0], ctx=ast.Load())
    for p in parts[1:]:
        node = ast.Attribute(value=node, attr=p, ctx=ast.Load())
    return node


def python_name(failure_type: str) -> str:
    """The Python identifier a failure type is raised under: the last
    segment of a qualified name such as `pkg.errors.RateError`, the
    name itself otherwise."""
    return re.split(r"::|\.", failure_type)[-1]


def _call(func: ast.expr, args, keywords=()) -> ast.Call:
    return ast.Call(func=func, args=list(args),
                    keywords=[ast.keyword(arg=k, value=v) for k, v in keywords])


def _annotation(kind) -> ast.expr | None:
    text = _ANNOTATIONS.get(kind.head) if isinstance(kind, Term) else None
    return ast.parse(text, mode="eval").body if text else None


def render(doc: Document) -> Rendered:
    """Intent:
        The document as Python source in the liftable subset, with its
        parsed `FunctionDef`, the line map, the external names to bind
        and the exception names raised.

    Raises:
        RenderError: a construct has no rendering (a `loop::each` with
            an index that does not start at 0).
    """
    ctx = _Ctx()
    body = ctx.block(doc.body)
    name = doc.name or "koine_function"
    args = [ast.arg(arg=p.args[0].id,
                    annotation=_annotation(p.args[1] if len(p.args) > 1 else None))
            for p in doc.parameters]
    returns = doc.first("returns")
    fdef = ast.FunctionDef(
        name=name, args=ast.arguments(posonlyargs=[], args=args, vararg=None, kwonlyargs=[],
                                      kw_defaults=[], kwarg=None, defaults=[]),
        body=body, decorator_list=[],
        returns=_annotation(returns.args[0]) if returns is not None and returns.args else None,
        type_params=[])
    module = ast.fix_missing_locations(ast.Module(body=[fdef], type_ignores=[]))
    source = ast.unparse(module) + "\n"
    tree = ast.parse(source).body[0]
    line_map: dict = {}
    _pair(tree.body, doc.body, line_map)
    return Rendered(name=name, params=doc.parameter_names, source=source, tree=tree,
                    line_map=line_map, externals=ctx.externals, exceptions=ctx.exceptions)


def _pair(rendered: list, statements, line_map: dict) -> None:
    """Rendered statements and document statements correspond one to
    one at every level, so their lines pair by position."""
    for r, s in zip(rendered, statements):
        span = s.get("at")
        if isinstance(span, Term) and span.args and isinstance(span.args[0], Int):
            line_map[r.lineno] = span.args[0].value
        if s.head == "statement::branch":
            _pair(r.body, s.args[1].items, line_map)
            _pair(r.orelse, s.args[2].items, line_map)
        elif s.head == "statement::loop::range":
            _pair(r.body, s.args[4].items, line_map)
        elif s.head == "statement::loop::each":
            _pair(r.body, s.args[3].items, line_map)


def _store(name: str) -> ast.Name:
    return ast.Name(id=name, ctx=ast.Store())


class _Ctx:
    def __init__(self):
        self.externals: dict = {}
        self.exceptions: set = set()

    def block(self, stmts) -> list:
        out = [self.statement(s) for s in stmts]
        return out or [ast.Pass()]

    def statement(self, st: Term) -> ast.stmt:
        h, a = st.head, st.args
        if h == "statement::bind":
            return ast.Assign(targets=[_store(a[0].id)], value=self.expr(a[1]))
        if h == "statement::bind_many":
            return ast.Assign(
                targets=[ast.Tuple(elts=[_store(n.id) for n in a[0].items], ctx=ast.Store())],
                value=ast.Tuple(elts=[self.expr(v) for v in a[1].items], ctx=ast.Load()))
        if h == "statement::update":
            op = _AUGMENTED.get(a[1].head)
            if op is None:
                raise RenderError(f"no augmented assignment for {a[1].head}")
            return ast.AugAssign(target=_store(a[0].id), op=op(), value=self.expr(a[2]))
        if h == "statement::define":
            return ast.Assign(targets=[_store(a[0].id)], value=ast.Lambda(
                args=ast.arguments(posonlyargs=[], args=[ast.arg(arg=p.id) for p in a[1].items],
                                   vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None,
                                   defaults=[]),
                body=self.expr(a[2])))
        if h == "statement::branch":
            return ast.If(test=self.expr(a[0]), body=self.block(a[1].items),
                          orelse=[self.statement(s) for s in a[2].items])
        if h == "statement::loop::range":
            args = [self.expr(a[1]), self.expr(a[2])]
            if a[3].value != 1:
                args.append(ast.Constant(value=a[3].value))
            if len(args) == 2 and isinstance(a[1], Int) and a[1].value == 0:
                args = args[1:]
            return ast.For(target=_store(a[0].id),
                           iter=_call(ast.Name(id="range", ctx=ast.Load()), args),
                           body=self.block(a[4].items), orelse=[])
        if h == "statement::loop::each":
            seq = self.expr(a[1])
            if a[2].value == 1:
                seq = ast.Subscript(value=seq, slice=ast.Slice(lower=ast.Constant(value=1)),
                                    ctx=ast.Load())
            index = st.get("index")
            if index is not None:
                if a[2].value != 0:
                    raise RenderError("loop::each with an index must start at 0")
                target: ast.expr = ast.Tuple(elts=[_store(index.id), _store(a[0].id)],
                                             ctx=ast.Store())
                seq = _call(ast.Name(id="enumerate", ctx=ast.Load()), [seq])
            else:
                target = _store(a[0].id)
            return ast.For(target=target, iter=seq, body=self.block(a[3].items), orelse=[])
        if h == "statement::require":
            test = a[0]
            if isinstance(test, Term) and test.head == "operator::logic::not":
                guard = self.expr(test.args[0])
            else:
                guard = ast.UnaryOp(op=ast.Not(), operand=self.expr(test))
            return ast.If(test=guard, body=[self.raise_(a[1])], orelse=[])
        if h == "statement::fail":
            return self.raise_(a[0])
        if h == "statement::return":
            return ast.Return(value=self.expr(a[0]))
        if h == "statement::evaluate":
            return ast.Expr(value=self.expr(a[0]))
        raise RenderError(f"unknown statement {h}")

    def raise_(self, failure: Term) -> ast.Raise:
        self.exceptions.add(failure.args[0].value)
        name = python_name(failure.args[0].value)
        message = failure.get("message")
        args = [ast.Constant(value=message.value)] if isinstance(message, Str) else []
        return ast.Raise(exc=_call(ast.Name(id=name, ctx=ast.Load()), args), cause=None)

    def expr(self, node) -> ast.expr:
        if isinstance(node, Int):
            return ast.Constant(value=node.value)
        if isinstance(node, Real):
            return ast.Constant(value=float(node.text))
        if isinstance(node, (Str, Bool)):
            return ast.Constant(value=node.value)
        if isinstance(node, Name):
            return ast.Name(id=node.id, ctx=ast.Load())
        if not isinstance(node, Term):
            raise RenderError(f"not an expression: {node!r}")
        h, a = node.head, node.args
        if h in _BINARY_OPS:
            return ast.BinOp(left=self.expr(a[0]), op=_BINARY_OPS[h](), right=self.expr(a[1]))
        if h in _COMPARE_OPS:
            return ast.Compare(left=self.expr(a[0]), ops=[_COMPARE_OPS[h]()],
                               comparators=[self.expr(a[1])])
        spelling = _call_spelling(h)
        if spelling is not None:
            return _call(_dotted(spelling), [self.expr(x) for x in a])
        if h in _CONSTANTS:
            return _dotted(_CONSTANTS[h])
        if h == "operator::unary::negation":
            return ast.UnaryOp(op=ast.USub(), operand=self.expr(a[0]))
        if h == "operator::unary::identity":
            return ast.UnaryOp(op=ast.UAdd(), operand=self.expr(a[0]))
        if h == "operator::logic::not":
            return ast.UnaryOp(op=ast.Not(), operand=self.expr(a[0]))
        if h in ("operator::logic::and", "operator::logic::or"):
            op = ast.And() if h.endswith("::and") else ast.Or()
            return ast.BoolOp(op=op, values=[self.expr(x) for x in a])
        if h in ("operator::membership::in", "operator::membership::not_in"):
            member: ast.cmpop = ast.In() if h.endswith("::in") else ast.NotIn()
            return ast.Compare(left=self.expr(a[0]), ops=[member], comparators=[
                ast.Tuple(elts=[self.expr(m) for m in a[1].items], ctx=ast.Load())])
        if h == "value::absent":
            return ast.Constant(value=None)
        if h == "value::field":
            # a record travels as a mapping, so a field is a string key
            node_out: ast.expr = ast.Name(id=a[0].id, ctx=ast.Load())
            for member in a[1:]:
                node_out = ast.Subscript(value=node_out, slice=ast.Constant(value=member.id),
                                         ctx=ast.Load())
            return node_out
        if h == "value::index":
            return ast.Subscript(value=self.expr(a[0]), slice=self.expr(a[1]), ctx=ast.Load())
        if h == "value::length":
            return _call(ast.Name(id="len", ctx=ast.Load()), [self.expr(a[0])])
        if h == "value::tuple":
            return ast.Tuple(elts=[self.expr(x) for x in a], ctx=ast.Load())
        if h == "value::item":
            return ast.Subscript(value=self.expr(a[0]), slice=ast.Constant(value=a[1].value),
                                 ctx=ast.Load())
        if h == "value::conditional":
            return ast.IfExp(test=self.expr(a[0]), body=self.expr(a[1]), orelse=self.expr(a[2]))
        if h == "call::local":
            return _call(ast.Name(id=a[0].id, ctx=ast.Load()), [self.expr(x) for x in a[1:]])
        if h == "call::function":
            name = self.external(a[0].value)
            return _call(ast.Name(id=name, ctx=ast.Load()), [self.expr(x) for x in a[1:]])
        if h == "call::library":
            path = a[0].value
            self.externals.setdefault(path.split(".")[0], path.split(".")[0])
            return _call(_dotted(path), [self.expr(x) for x in a[1:]],
                         [(k, self.expr(v)) for k, v in node.named])
        raise RenderError(f"no rendering for {h}")

    def external(self, key: str) -> str:
        for name, k in self.externals.items():
            if k == key:
                return name
        base = key.rpartition("#")[2].rpartition(".")[2].rpartition(":")[2] or "callee"
        base = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base)
        if not (base[0].isalpha() or base[0] == "_"):
            base = "_" + base
        name, n = base, 1
        while name in self.externals:
            n += 1
            name = f"{base}_{n}"
        self.externals[name] = key
        return name


MODULE_PREFIX = "mathema.koine._rendered."


def exception_class(name: str, module: str) -> type:
    """The exception class a failure type `name` is raised as: the
    builtin itself when `name` is a builtin exception's name, else a
    class called `name` living in `module` and subclassing the builtin
    its last segment names, or `Exception` when none does. A qualified
    name such as `pkg.errors.RateError` keeps the whole name as the
    class's name and is bound under its last segment."""
    base = getattr(builtins, python_name(name), None)
    if not (isinstance(base, type) and issubclass(base, BaseException)):
        base = Exception
    elif python_name(name) == name:
        return base
    return type(name, (base,), {"__module__": module})


def namespace(rendered: Rendered, module: str = MODULE_PREFIX + "scope") -> dict:
    """Intent:
        The names the rendered body reads besides its parameters and
        external calls: `math`, every helper under its alias, and one
        exception class per failure type the body raises, made in
        `module`.
    """
    out: dict = {"math": math}
    out.update(helpers())
    for name in sorted(rendered.exceptions):
        out[python_name(name)] = exception_class(name, module)
    return out


def materialise(rendered: Rendered, key: str | None = None,
                bindings: dict[str, Callable] | None = None) -> Callable:
    """Intent:
        The rendered function, defined in a module of its own so every
        source-reading path sees the rendered body and its raise names
        resolve on the function's module.

    Raises:
        NameError: an external name in `rendered.externals` has no
            binding.
    """
    digest = hashlib.sha256(rendered.source.encode()).hexdigest()[:12]
    modname = MODULE_PREFIX + digest
    filename = f"<koine {key or rendered.name} {digest}>"
    module = types.ModuleType(modname)
    module.__file__ = filename
    scope = module.__dict__
    scope.update(namespace(rendered, modname))
    bindings = bindings or {}
    for name in rendered.externals:
        if name not in bindings:
            raise NameError(f"no binding for external {name!r} ({rendered.externals[name]})")
        scope[name] = bindings[name]
    lines = rendered.source.splitlines(keepends=True)
    linecache.cache[filename] = (len(rendered.source), None, lines, filename)
    sys.modules[modname] = module
    exec(compile(rendered.source, filename, "exec"), scope)
    fn = scope[rendered.name]
    fn.__module__ = modname
    if key:
        fn.__mathema_key__ = key
    return fn
