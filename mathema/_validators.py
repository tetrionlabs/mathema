# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Reading a function as a pattern validator: a function of one text
parameter whose whole behaviour is the truth of one regular-expression
match on that parameter. Where the reading is not certain the function
is declined, with the reason: a decline loses a proof, a wrong reading
would give a false one.

A function is read only when all of this holds, each point checked on
the function object and not assumed from its source text.

1. It is a plain function object: not a lambda, a method object, a
   partial or another callable; not wrapped (`__wrapped__`); with no
   closure and no free variables; with no default argument values;
   neither a coroutine nor a generator.
2. Its source is one undecorated `def` taking exactly one positional
   parameter, and the code that source compiles to is the code the
   function runs (same instructions, names, variables and constants).
3. After an optional docstring its body is one of two shapes. A
   refusing validator: `if <test>: raise E(...)` with no `else`, then
   `return <the parameter>`, the test true exactly when the match
   fails (`not m`, `m is None`). A predicate: `return <test>`, the
   test being `bool(m)`, `m is not None`, `m is None` or `not m`.
4. The match `m` is `PAT.fullmatch(x)`, `PAT.match(x)` or
   `PAT.search(x)` with the bare parameter as its only argument,
   `re.compile(P[, flags]).fullmatch(x)`, or `re.fullmatch(P, x[,
   flags])` and its two siblings, with no keyword arguments. The text
   matched may also be `x or ''`, which is `x` for every text `x`;
   the validator then says so (`or_empty`), and a proof reads it only
   over a domain of texts.
5. Every name the body reads is resolved in the function's globals or
   the builtins and checked by identity: `PAT` is an object of the
   exact type `re.Pattern`; `re` is the standard `re` module and the
   function called is that module's own; `bool`, `repr` and `str` are
   the builtins. No such name is a parameter or assigned in the body.
   An inline pattern is a string literal (or a name bound to a `str`)
   and its flags are `re` constants joined by `|`.
6. `E` is a builtin exception class under its own name, or a plain
   exception class of the function's own package: defined in the
   function's module or in a module of the same top-level package,
   its only base a builtin exception class under its own name, its
   type `type`, and holding nothing beyond a plain class's own
   attributes (its module, its docstring), so building it is building
   that builtin exception. It is raised with no cause, built from no
   argument or from one that cannot fail on a text: a string literal,
   the parameter, `repr` or `str` of the parameter, or an f-string of
   literals, the parameter and names the function's globals bind to an
   object of exact type `str` (`constants`), each with no format
   specification.

Anything else (text transformed before the match, a second test, a
`try`, an attribute of an object, any other exception class) is
declined, and `read_validator` says which part stopped it.
"""
from __future__ import annotations

import ast
import builtins
import dis
import inspect
import re
import textwrap
import types
from dataclasses import dataclass
from typing import cast

MODES = ("fullmatch", "match", "search")

#: the `re` module's own functions as they are when this module is
#: first imported: what a call of `re.fullmatch` in a function under
#: reading must still be
_RE_FUNCTIONS = {name: getattr(re, name) for name in (*MODES, "compile")}
#: the types a code object's constants may have for its source to be
#: taken as the code it runs
_CONSTANT_TYPES = (str, bytes, int, float, complex, bool, type(None), type(...),
                   tuple, frozenset, types.CodeType)


@dataclass(frozen=True)
class Validator:
    """A function read as a pattern validator: the text parameter
    `param`; `accepts`, the bound method of the compiled pattern the
    function calls on it (`PAT.fullmatch`), whose truth is acceptance;
    `raises`, the exception class a refusing validator raises (None for
    a predicate); `negated`, set for a predicate that returns the
    match's failure; `or_empty`, set when the text matched is
    `<param> or ''`, which is the parameter only when it is a text; and
    `constants`, the module-level text constants the exception's
    message reads, by name."""
    param: str
    accepts: object
    raises: "type | None" = None
    negated: bool = False
    or_empty: bool = False
    constants: tuple = ()

    @property
    def pattern(self) -> "re.Pattern":
        return self.accepts.__self__  # type: ignore[attr-defined]

    @property
    def mode(self) -> str:
        return self.accepts.__name__  # type: ignore[attr-defined]

    def described(self) -> str:
        """`re.compile('[a-z]+').fullmatch`, with the flags when any."""
        flags = self.pattern.flags & ~re.UNICODE
        said = f", {re.RegexFlag(flags)!s}" if flags else ""
        return f"re.compile({self.pattern.pattern!r}{said}).{self.mode}"


class _Declined(Exception):
    """Why a function is not read as a validator."""


def _stored_names(tree: ast.AST) -> set:
    """Every name the function binds: its parameters and anything it
    assigns, imports, deletes or declares global or nonlocal."""
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
    return names


class _Reader:
    """One function's source read against the objects its names are
    bound to."""

    def __init__(self, fn, tree: ast.FunctionDef) -> None:
        self.fn = fn
        self.globals = fn.__globals__
        self.local = _stored_names(tree)
        #: set once a match is read on `<param> or ''`
        self.or_empty = False
        #: the module-level text constants a message reads, in order
        self.constants: list = []

    def _global(self, name: str):
        """The object a free name is bound to where the function itself
        resolves it: its globals, then the builtins those globals
        name, which must be the real builtins."""
        if name in self.local:
            raise _Declined(f"{name!r} is a parameter or is assigned in the function")
        if name in self.globals:
            return dict.__getitem__(self.globals, name)
        if name in vars(builtins):
            return vars(builtins)[name]
        raise _Declined(f"{name!r} is not bound where the function is defined")

    def value(self, node: ast.AST):
        """The object a name or a dotted name is bound to."""
        if isinstance(node, ast.Name):
            return self._global(node.id)
        if isinstance(node, ast.Attribute):
            owner = self.value(node.value)
            if type(owner) is not types.ModuleType:
                raise _Declined(f"{ast.unparse(node)} is not a name in a plain module")
            namespace = vars(owner)
            if "__getattr__" in namespace or node.attr not in namespace:
                raise _Declined(f"{ast.unparse(node)} is not a name the module holds "
                                f"itself (it may be computed when read)")
            return namespace[node.attr]
        raise _Declined(f"{ast.unparse(node)} is not a name")

    def _re_function(self, node: ast.AST, name: str) -> bool:
        """Whether the callee is NOT the `re` module's own function of
        that name: the object the function reaches must be the one `re`
        held when this module was imported, a function defined in `re`."""
        reached = self.value(node)
        original = _RE_FUNCTIONS[name]
        return not (reached is original and type(reached) is types.FunctionType
                    and reached.__module__ == "re")

    def _text(self, node: ast.AST) -> str:
        """A pattern written as a string literal, or a name bound to a
        string."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, (ast.Name, ast.Attribute)):
            bound = self.value(node)
            if isinstance(bound, str):
                return bound
        raise _Declined(f"the pattern {ast.unparse(node)} is not a string literal")

    def _flags(self, node: ast.AST) -> int:
        """Flags written as `re` constants joined by `|`."""
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self._flags(node.left) | self._flags(node.right)
        if isinstance(node, ast.Attribute):
            bound = self.value(node)
            if isinstance(bound, re.RegexFlag) and self.value(node.value) is re:
                return int(bound)
        raise _Declined(f"the flags {ast.unparse(node)} are not `re` constants joined by `|`")

    def _compiled(self, node: ast.AST) -> "re.Pattern":
        """The compiled pattern an expression is: a name bound to one,
        or a call of `re.compile` on a literal."""
        if isinstance(node, ast.Call):
            if self._re_function(node.func, "compile") or node.keywords \
                    or not 1 <= len(node.args) <= 2:
                raise _Declined(f"{ast.unparse(node)} is not a call of re.compile "
                                f"on a pattern and flags")
            flags = self._flags(node.args[1]) if len(node.args) == 2 else 0
            return self._compile(self._text(node.args[0]), flags)
        bound = self.value(node)
        if type(bound) is not re.Pattern:
            raise _Declined(f"{ast.unparse(node)} is not a compiled re.Pattern")
        return bound

    @staticmethod
    def _compile(pattern: str, flags: int) -> "re.Pattern":
        try:
            return re.compile(pattern, flags)
        except re.error as e:
            raise _Declined(f"the pattern {pattern!r} does not compile ({e})") from None

    def match(self, node: ast.AST, param: str):
        """The bound method `PAT.<mode>` a match expression on the bare
        parameter calls."""
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) \
                or node.func.attr not in MODES or node.keywords:
            raise _Declined(f"{ast.unparse(node)} is not a fullmatch, match or search")
        mode, owner = node.func.attr, node.func.value

        def on_param(arg: ast.AST) -> None:
            if isinstance(arg, ast.BoolOp) and isinstance(arg.op, ast.Or) \
                    and len(arg.values) == 2 and isinstance(arg.values[1], ast.Constant) \
                    and type(arg.values[1].value) is str and arg.values[1].value == "" \
                    and isinstance(arg.values[0], ast.Name) and arg.values[0].id == param:
                self.or_empty = True  # :draft
                return
            if not (isinstance(arg, ast.Name) and arg.id == param):
                raise _Declined(f"the match is on {ast.unparse(arg)}, not on the "
                                f"parameter {param!r} as passed")
        module_call = False
        if isinstance(owner, (ast.Name, ast.Attribute)):
            module_call = self.value(owner) is re
        if module_call:
            if self._re_function(node.func, mode) or not 2 <= len(node.args) <= 3:
                raise _Declined(f"{ast.unparse(node)} is not re.{mode}(pattern, text[, flags])")
            on_param(node.args[1])
            flags = self._flags(node.args[2]) if len(node.args) == 3 else 0
            compiled = self._compile(self._text(node.args[0]), flags)
        else:
            if len(node.args) != 1:
                raise _Declined(f"{ast.unparse(node)} passes a position or an end, "
                                f"so it does not match the whole parameter")
            on_param(node.args[0])
            compiled = self._compiled(owner)
        return getattr(compiled, mode)

    def test(self, node: ast.AST, param: str) -> tuple:
        """`(bound method, truth)` for a test of a match: `truth` is
        True when the expression is true exactly when the match
        succeeds (`m`, `bool(m)`, `m is not None`), False when it is
        true exactly when the match fails (`not m`, `m is None`)."""
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            method, truth = self.test(node.operand, param)
            return method, not truth
        if isinstance(node, ast.Compare) and len(node.ops) == 1 \
                and isinstance(node.ops[0], (ast.Is, ast.IsNot)) \
                and isinstance(node.comparators[0], ast.Constant) \
                and node.comparators[0].value is None:
            return self.match(node.left, param), isinstance(node.ops[0], ast.IsNot)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "bool" and len(node.args) == 1 and not node.keywords \
                and self._global("bool") is bool:
            return self.match(node.args[0], param), True
        return self.match(node, param), True

    def raised(self, node: ast.Raise, param: str) -> type:
        """The builtin exception class a `raise` statement raises, when
        building the exception cannot itself fail."""
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        if exc is None or node.cause is not None:
            raise _Declined("the raise is a re-raise or has a cause")
        if not isinstance(exc, ast.Name):
            raise _Declined(f"{ast.unparse(exc)} is not the name of a builtin exception")
        bound = self._global(exc.id)
        builtin = (isinstance(bound, type) and issubclass(bound, Exception)
                   and getattr(builtins, exc.id, None) is bound)
        if not builtin:
            plain = _plain_exception_class(bound, self.fn)
            if plain is not None:
                raise _Declined(f"{exc.id} is not the builtin exception class of that name, "  # :draft
                                f"and {plain}, so building it may do anything")
        if isinstance(node.exc, ast.Call):
            if node.exc.keywords or len(node.exc.args) > 1:
                raise _Declined("the exception is built from more than one argument")
            for arg in node.exc.args:
                self._total(arg, param)
        return cast(type, bound)

    def _total(self, node: ast.AST, param: str) -> None:
        """Declines unless evaluating `node` cannot raise for a text
        parameter: a string literal, the bare parameter, `repr` or
        `str` of the parameter, or an f-string of those."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return
        if isinstance(node, ast.Name) and node.id == param:
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in ("repr", "str") and len(node.args) == 1 \
                and not node.keywords \
                and self._global(node.func.id) is getattr(builtins, node.func.id) \
                and isinstance(node.args[0], ast.Name) and node.args[0].id == param:
            return
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    continue
                if isinstance(part, ast.FormattedValue) and part.format_spec is None \
                        and isinstance(part.value, ast.Name) and part.value.id == param:
                    continue
                if isinstance(part, ast.FormattedValue) and part.format_spec is None \
                        and isinstance(part.value, ast.Name) \
                        and type(self._global(part.value.id)) is str:  # :draft
                    if part.value.id not in self.constants:
                        self.constants.append(part.value.id)
                    continue
                raise _Declined(f"the exception's message {ast.unparse(node)} reads more "
                                f"than the parameter")
            return
        raise _Declined(f"the exception's argument {ast.unparse(node)} is more than a "
                        f"string, the parameter, or its repr or str")


#: the attributes a class statement with no body beyond a docstring
#: gives a class, on every supported Python
_PLAIN_CLASS_ATTRIBUTES = frozenset({"__module__", "__doc__", "__qualname__", "__weakref__",
                                     "__firstlineno__", "__static_attributes__"})


def _same_package(module: str, other: str) -> bool:
    """Whether two modules are one module, or modules of one top-level
    package."""
    if module == other:
        return True
    return "." in module and "." in other and module.split(".")[0] == other.split(".")[0]


def _plain_exception_class(cls, fn) -> "str | None":
    """None when `cls` is a plain exception class of `fn`'s own package
    (point 6), else what stops it, as a phrase."""
    if not isinstance(cls, type):
        return "it is not a class"
    if type(cls) is not type:
        return "its type is not type"
    module = dict.get(fn.__globals__, "__name__")
    if not (isinstance(module, str) and isinstance(cls.__dict__.get("__module__"), str)
            and _same_package(module, cls.__dict__["__module__"])):
        return "it is not defined in the function's own package"
    if len(cls.__bases__) != 1:
        return "it has more than one base"
    (base,) = cls.__bases__
    if not (isinstance(base, type) and issubclass(base, Exception)
            and getattr(builtins, base.__name__, None) is base):
        return "its base is not a builtin exception class"
    extra = sorted(set(cls.__dict__) - _PLAIN_CLASS_ATTRIBUTES)
    if extra:
        return f"it holds {', '.join(extra)}"
    held = cls.__dict__
    if not (held.get("__doc__") is None or type(held["__doc__"]) is str) \
            or ("__weakref__" in held
                and type(held["__weakref__"]) is not types.GetSetDescriptorType) \
            or held.get("__static_attributes__", ()) != () \
            or type(held.get("__firstlineno__", 0)) is not int:
        return "it holds more than a plain class does"
    return None


def _same_code(fn, source: str, name: str) -> bool:
    """Whether the function's running code is the code its source text
    compiles to: the same instructions on the same names, variables and
    constants, a jump reaching the same instruction. How a call's
    callee is pushed differs with what the enclosing module imports (an
    attribute of an imported module is loaded without the method-call
    form), so the comparison passes over that difference alone.
    Constants are compared by exact type and value, and a constant of
    any type outside the builtin constant types fails the comparison."""
    skipped = ("PUSH_NULL", "CACHE", "NOP")

    def constant(value):
        if type(value) not in _CONSTANT_TYPES:
            raise TypeError(type(value).__name__)
        if type(value) is types.CodeType:
            return "<code>"
        if type(value) in (tuple, frozenset):
            return (type(value).__name__, tuple(sorted((constant(v) for v in value),
                                                       key=repr)) if type(value) is frozenset
                    else tuple(constant(v) for v in value))
        return (type(value).__name__, repr(value))

    def shape(code) -> tuple:
        for value in code.co_consts:
            constant(value)
        kept = [step for step in dis.get_instructions(code) if step.opname not in skipped]
        index_at: dict[int, int] = {}
        for i, step in enumerate(kept):
            index_at.setdefault(step.offset, i)
        offsets = sorted(index_at)

        def reached(offset) -> int:
            later = [o for o in offsets if o >= offset]
            return index_at[later[0]] if later else len(kept)
        steps = []
        for step in kept:
            value = step.argval
            if "JUMP" in step.opname or step.opname.startswith("FOR_"):
                value = ("to", reached(value)) if isinstance(value, int) else value
            elif step.opname in ("LOAD_ATTR", "LOAD_GLOBAL", "LOAD_METHOD"):
                # the name alone: the NULL beside it, before the name on
                # some Pythons and after it on others, says how a callee
                # is pushed, not what is loaded
                value = next((part for part in step.argrepr.split(" + ")
                              if part not in ("NULL", "NULL|self")), step.argrepr)
            elif step.opname in ("LOAD_CONST", "RETURN_CONST", "KW_NAMES"):
                value = constant(value)
            steps.append(("LOAD_ATTR" if step.opname == "LOAD_METHOD" else step.opname,
                          value if isinstance(value, tuple) else repr(value)))
        return tuple(steps), code.co_varnames, code.co_freevars
    try:
        module = compile(source, "<validator source>", "exec")
        read = next((c for c in module.co_consts
                     if hasattr(c, "co_code") and c.co_name == name), None)
        return read is not None and shape(read) == shape(fn.__code__)
    except (SyntaxError, ValueError, TypeError):
        return False


def _require_a_plain_function(fn) -> None:
    """Declines unless `fn` is a plain module-level-style function whose
    behaviour its own source and globals fix: a function object, not
    wrapped, with no closure, no default values, and neither a
    coroutine nor a generator."""
    if not inspect.isfunction(fn):
        raise _Declined("it is not a plain function object")
    if type(fn.__globals__) is not dict:
        raise _Declined("its globals are not a plain dict")
    named = dict.get(fn.__globals__, "__builtins__", builtins)
    if (vars(named) if type(named) is types.ModuleType else named) is not vars(builtins):
        raise _Declined("its builtins are not the real builtins")
    if hasattr(fn, "__wrapped__"):
        raise _Declined("it wraps another function, whose source is not its own behaviour")
    code = fn.__code__
    if fn.__closure__ or code.co_freevars:
        raise _Declined("it reads names from an enclosing function, which its globals "
                        "do not hold")
    if fn.__defaults__ or fn.__kwdefaults__:
        raise _Declined("it has default argument values")
    if inspect.iscoroutinefunction(fn) or inspect.isgeneratorfunction(fn) \
            or inspect.isasyncgenfunction(fn):
        raise _Declined("it is a coroutine or a generator")
    if fn.__name__ == "<lambda>":
        raise _Declined("it is a lambda")


def _function_tree(fn) -> ast.FunctionDef:
    try:
        source = textwrap.dedent(inspect.getsource(fn))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        raise _Declined("its source is not available") from None
    _require_a_plain_function(fn)
    found = tree.body[0] if tree.body else None
    if not isinstance(found, ast.FunctionDef) or found.decorator_list or len(tree.body) != 1:
        raise _Declined("it is not a plain, undecorated function")
    if found.name != fn.__code__.co_name or not _same_code(fn, source, found.name):
        raise _Declined("its source text is not the code it runs (it was redefined, "
                        "wrapped, or its file changed)")
    return found


def _read(fn) -> Validator:
    tree = _function_tree(fn)
    args = tree.args
    if args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs or args.defaults \
            or len(args.args) != 1:
        raise _Declined("it does not take exactly one parameter")
    param = args.args[0].arg
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    reader = _Reader(fn, tree)
    if len(body) == 1 and isinstance(body[0], ast.Return) and body[0].value is not None:
        value = body[0].value
        bare = isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
        if bare:
            raise _Declined("it returns the match object, not its truth")
        method, truth = reader.test(value, param)
        return Validator(param, method, None, negated=not truth, or_empty=reader.or_empty)
    if len(body) == 2 and isinstance(body[0], ast.If) and not body[0].orelse \
            and len(body[0].body) == 1 and isinstance(body[0].body[0], ast.Raise) \
            and isinstance(body[1], ast.Return) \
            and isinstance(body[1].value, ast.Name) and body[1].value.id == param:
        method, truth = reader.test(body[0].test, param)
        if truth:
            raise _Declined("it raises when the match succeeds")
        raises = reader.raised(body[0].body[0], param)
        return Validator(param, method, raises, or_empty=reader.or_empty,
                         constants=tuple(reader.constants))
    raise _Declined("its body is more than one test of one match on the parameter")


def read_validator(fn) -> "Validator | str":
    """Intent:
        `fn` read as a pattern validator, or the reason it is not one,
        as a phrase that completes "the function is not read as a
        pattern validator: ...".
    """
    try:
        return _read(fn)
    except _Declined as e:
        return str(e)


__all__ = ["MODES", "Validator", "read_validator"]
