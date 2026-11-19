# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The validator reader declines every function whose behaviour it
cannot be sure of from the function object, its source and its globals.
A decline loses a proof; a wrong reading would give a false one. Each
function here either is declined, or is read and then agrees with the
function itself on a set of texts."""
import functools
import importlib
import re
import sys
import textwrap

import pytest

from mathema._validators import Validator, read_validator

PAT = re.compile(r"[a-z]+")
OTHER = "context"
TEXTS = ("", "a", "abc", "A", "1", "a1", "abc\n", "ab cd", "é")


# ---- functions whose names are not what the module globals say ----------

def _closure_over_a_pattern():
    PAT = re.compile(r"[0-9]+")  # noqa: N806

    def f(s):
        if not PAT.fullmatch(s):
            raise ValueError(s)
        return s
    return f


def _closure_over_an_exception():
    ValueError = KeyError  # noqa: N806, A001

    def f(s):
        if not PAT.fullmatch(s):
            raise ValueError(s)
        return s
    return f


def _check(s):
    if not PAT.fullmatch(s):
        raise ValueError(s)
    return s


def _lowered(fn):
    @functools.wraps(fn)
    def wrapper(s):
        return fn(s.strip().lower())
    return wrapper


wrapped_without_decorator_syntax = _lowered(_check)


@_lowered
def decorated(s):
    if not PAT.fullmatch(s):
        raise ValueError(s)
    return s


# ---- raises whose exception may not be the one named --------------------

def raise_argument_indexes(s):
    if not PAT.fullmatch(s):
        raise ValueError(s[5])
    return s


class Bad(ValueError):
    def __init__(self, *args):
        raise KeyError("no")


def raise_of_a_user_exception(s):
    if not PAT.fullmatch(s):
        raise Bad(s)
    return s


def raise_argument_calls(s):
    if not PAT.fullmatch(s):
        raise ValueError(_check(s))
    return s


def raise_argument_names_another_variable(s):
    if not PAT.fullmatch(s):
        raise ValueError(f"{s} in {OTHER}")
    return s


def raise_argument_has_a_format_specification(s):
    if not PAT.fullmatch(s):
        raise ValueError(f"{s:>10}")
    return s


def raise_with_two_arguments(s):
    if not PAT.fullmatch(s):
        raise ValueError("bad", s)
    return s


def raise_with_a_cause(s):
    if not PAT.fullmatch(s):
        raise ValueError(s) from None
    return s


MyError = ValueError


def raise_through_an_alias(s):
    if not PAT.fullmatch(s):
        raise MyError(s)
    return s


# ---- shapes that are more than one test of one match --------------------

a_lambda = lambda s: bool(PAT.fullmatch(s))  # noqa: E731


def default_on_the_parameter(s="a"):
    return bool(PAT.fullmatch(s))


def default_capturing_a_pattern(s, pattern=re.compile(r"[0-9]+")):
    return bool(pattern.fullmatch(s))


class Holder:
    PAT = re.compile(r"[0-9]+")

    def method(self, s):
        return bool(PAT.fullmatch(s))

    @staticmethod
    def static(s):
        return bool(PAT.fullmatch(s))

    @property
    def prop(self):
        return bool(PAT.fullmatch("a"))


def class_attribute_pattern(s):
    return bool(Holder.PAT.fullmatch(s))


async def an_async_function(s):
    return bool(PAT.fullmatch(s))


def a_generator(s):
    yield bool(PAT.fullmatch(s))


class CallableObject:
    def __call__(self, s):
        return bool(PAT.fullmatch(s))


def keyword_argument_to_the_match(s):
    return bool(PAT.fullmatch(string=s))


def walrus_in_the_test(s):
    return bool(m := PAT.fullmatch(s)) and m is not None


def comparison_chain(s):
    return PAT.fullmatch(s) is not None is not False


def with_an_else_branch(s):
    if not PAT.fullmatch(s):
        raise ValueError(s)
    else:
        return s


def statement_before_the_return(s):
    s = s.strip()
    return bool(PAT.fullmatch(s))


def inside_a_try(s):
    try:
        return bool(PAT.fullmatch(s))
    except TypeError:
        return False


def with_a_global_statement(s):
    global OTHER
    return bool(PAT.fullmatch(s))


def code_swapped_after_definition(s):
    return bool(PAT.fullmatch(s))


def _strips_then_matches(s):
    return bool(PAT.fullmatch(s.strip()))


code_swapped_after_definition.__code__ = _strips_then_matches.__code__


DECLINED = [
    _closure_over_a_pattern(), _closure_over_an_exception(), wrapped_without_decorator_syntax,
    decorated, raise_argument_indexes, raise_of_a_user_exception, raise_argument_calls,
    raise_argument_names_another_variable, raise_argument_has_a_format_specification,
    raise_with_two_arguments, raise_with_a_cause, raise_through_an_alias, a_lambda,
    default_on_the_parameter, default_capturing_a_pattern, Holder().method, Holder.method,
    Holder.prop, class_attribute_pattern, an_async_function, a_generator,
    functools.partial(_check), CallableObject(), keyword_argument_to_the_match,
    walrus_in_the_test, comparison_chain, with_an_else_branch, statement_before_the_return,
    inside_a_try, with_a_global_statement, code_swapped_after_definition, Holder.static,
]


@pytest.mark.parametrize("fn", DECLINED, ids=[getattr(f, "__name__", type(f).__name__)
                                              + f"_{i}" for i, f in enumerate(DECLINED)])
def test_a_function_the_reader_cannot_be_sure_of_is_declined_with_a_reason(fn):
    read = read_validator(fn)
    assert isinstance(read, str) and read, read


@pytest.mark.parametrize("fn,reason", [
    (_closure_over_a_pattern(), "it reads names from an enclosing function"),
    (_closure_over_an_exception(), "it reads names from an enclosing function"),
    (wrapped_without_decorator_syntax, "it wraps another function"),
    (raise_argument_indexes, "the exception's argument s[5] is more than"),
    (raise_of_a_user_exception, "Bad is not the builtin exception class of that name"),
    (raise_through_an_alias, "MyError is not the builtin exception class of that name"),
    (default_capturing_a_pattern, "it has default argument values"),
])
def test_the_reason_names_what_stopped_the_reading(fn, reason):
    assert reason in read_validator(fn)


# ---- functions that are read, and read correctly -------------------------

LATER = re.compile(r"[0-9]+")


def pattern_rebound_later_in_the_module(s):
    return bool(LATER.fullmatch(s))


LATER = re.compile(r"[a-z]+")

if PAT is not None:
    def conditionally_defined(s):
        if PAT.fullmatch(s) is None:
            raise ValueError(f"not a word: {s!r}")
        return s


def message_from_repr(s):
    if not PAT.fullmatch(s):
        raise ValueError(repr(s))
    return s


def message_is_a_literal(s):
    if not PAT.search(s):
        raise TypeError("no letters")
    return s


def bare_exception_class(s):
    if not PAT.match(s):
        raise ValueError
    return s


READ = [pattern_rebound_later_in_the_module, conditionally_defined, message_from_repr,
        message_is_a_literal, bare_exception_class, _check]


def _agrees(read, fn, text):
    matched = read.accepts(text) is not None
    try:
        returned = fn(text)
    except Exception as e:
        return read.raises is not None and type(e) is read.raises and not matched
    if read.raises is not None:
        return matched and returned == text
    return returned is (matched != read.negated)


@pytest.mark.parametrize("fn", READ, ids=[f.__name__ for f in READ])
def test_a_function_that_is_read_behaves_as_it_was_read_on_every_text(fn):
    read = read_validator(fn)
    assert isinstance(read, Validator), read
    assert all(_agrees(read, fn, text) for text in TEXTS)


def test_a_pattern_rebound_later_is_read_as_the_object_bound_now():
    assert read_validator(pattern_rebound_later_in_the_module).pattern is LATER
    assert LATER.pattern == "[a-z]+"


# ---- a module that rebinds the names the reader checks by identity -------

_REBINDING_MODULE = '''
import re as _real_re

PAT = _real_re.compile(r"[a-z]+")
{rebinding}


def f(s):
{body}
'''

_REFUSING = "    if not PAT.fullmatch(s):\\n        raise ValueError(s)\\n    return s"
_PREDICATE = "    return bool(PAT.fullmatch(s))"
_MODULE_CALL = "    return re.fullmatch(r'[a-z]+', s) is not None"


@pytest.mark.parametrize("name,rebinding,body", [
    ("rebinds_valueerror", "ValueError = KeyError", _REFUSING),
    ("rebinds_bool", "bool = lambda m: True", _PREDICATE),
    ("rebinds_re", "import types\\nre = types.SimpleNamespace(fullmatch=lambda p, s: None)",
     _MODULE_CALL),
    ("pattern_is_a_lookalike",
     "import types\\nPAT = types.SimpleNamespace(fullmatch=lambda s: None)", _PREDICATE),
])
def test_a_module_that_rebinds_a_checked_name_is_declined(tmp_path, monkeypatch, name,
                                                          rebinding, body):
    monkeypatch.syspath_prepend(str(tmp_path))
    source = _REBINDING_MODULE.replace("{rebinding}", rebinding.replace("\\n", "\n")) \
        .replace("{body}", body.replace("\\n", "\n"))
    (tmp_path / f"{name}.py").write_text(textwrap.dedent(source))
    sys.modules.pop(name, None)
    try:
        module = importlib.import_module(name)
        read = read_validator(module.f)
        assert isinstance(read, str), read
    finally:
        sys.modules.pop(name, None)
