# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function under a decorator defined in another module (Django's
`keep_lazy_text`, mathema's own `enforce_domain`) is read as the
function it wraps: the names its body and its claims use resolve in
the module that defines it, not the decorator's."""
import functools
import re
import warnings

from mathema import claims_decorator, enforce_domain
from mathema._signatures import module_scope
from mathema.analysis import StateDependenceWarning
from mathema.conjecture import check_conjectures, claim

_ELSEWHERE: dict = {"functools": functools}
exec(  # noqa: S102
    "def elsewhere(fn):\n"
    "    @functools.wraps(fn)\n"
    "    def wrapper(*args, **kwargs):\n"
    "        return fn(*args, **kwargs)\n"
    "    return wrapper\n",
    _ELSEWHERE,
)
elsewhere = _ELSEWHERE["elsewhere"]


@elsewhere
def tidy(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def double(x: float) -> float:
    return 2 * x


@enforce_domain()
@claims_decorator("for x in [0, 1], twice(x) == double(x)")
def twice(x: float) -> float:
    return x + x


def test_the_module_scope_is_the_wrapped_function_s():
    assert module_scope(tidy) is globals()
    assert module_scope(twice) is globals()
    assert module_scope(double) is globals()


def test_a_decorated_function_s_module_names_are_resolved():
    with warnings.catch_warnings():
        warnings.simplefilter("error", StateDependenceWarning)
        (p,) = check_conjectures(tidy, [claim('for s in {"a  b", " c"}, len(tidy(s)) <= len(s)')])
    assert p.verdict in ("proven", "holds")


def test_a_claim_on_an_enforced_function_binds_names_from_its_module():
    (p,) = check_conjectures(twice, [claim("for x in [0, 1], twice(x) == double(x)")])
    assert p.verdict in ("proven", "holds"), p.note


def test_a_callable_with_no_globals_of_its_own_has_an_empty_scope():
    import pytest
    np = pytest.importorskip("numpy")
    assert module_scope(np.mean) == {}
