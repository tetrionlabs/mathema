# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What the shape evidence reads off a function's code: the uses that
name a kind of value, the order its sources are read in, the pieces that
disagree, and the operation a wrong-shape raise came from."""
import ast
import importlib.util
import sys
import textwrap

import pytest

from mathema._shape_evidence import callee_shape, wrong_shape_use
from mathema.analysis import _param_kinds, param_uses

SRC = '''
    import math


    def length(xs):
        return len(xs)


    def wave(x):
        return math.sin(x) + 1


    def join(s):
        return s + "!"


    def bare(x, y=2.0):
        return x


    def odd(x: float):
        return x[0]


    def through(t):
        return wave(t)


    def loud(obj):
        return obj.upper()


    def twice(s: str):
        return s * 2


    def rebinds(x):
        x = [x]
        return x[0][0]


    _STORE = {}


    def keys(k):
        return {k: 1}


    def members(k):
        return {k}


    def stored(k):
        _STORE[k] = 1
        return 1


    def fmt(x):
        return "%d items" % x


    def shout_at(x):
        prefix = "hi "
        return prefix + x


    def copied(x):
        t = x
        return t[0]
'''


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("shape") / "shape_reading_fns.py"
    path.write_text(textwrap.dedent(SRC))
    spec = importlib.util.spec_from_file_location("shape_reading_fns", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["shape_reading_fns"] = m
    spec.loader.exec_module(m)
    yield m
    sys.modules.pop("shape_reading_fns", None)


@pytest.mark.parametrize("name, param, source, shape", [
    ("length", "xs", "body use", "sequence"),
    ("wave", "x", "body use", "number"),
    ("join", "s", "body use", "string"),
    ("bare", "y", "default", "number"),
    ("through", "t", "body use", "number"),
    ("loud", "obj", "body use", "string"),
    ("odd", "x", "annotation", "number"),
])
def test_each_source_names_its_shape(mod, name, param, source, shape):
    found = callee_shape(getattr(mod, name), param, depth=1)
    assert found.evidence is not None
    assert (found.evidence.source, found.evidence.shape) == (source, shape)


def test_no_evidence_leaves_the_shape_unestablished(mod):
    found = callee_shape(mod.bare, "x")
    assert found.evidence is None and not found.established


def test_an_annotation_the_body_contradicts_disagrees(mod):
    found = callee_shape(mod.odd, "x")
    assert not found.established
    assert [e.shape for e in found.disagree] == ["sequence"]


def test_an_operator_a_string_supports_does_not_contradict_its_annotation(mod):
    found = callee_shape(mod.twice, "s")
    assert found.established and found.evidence.shape == "string"


def test_text_joined_with_a_parameter_is_not_arithmetic(mod):
    found = callee_shape(mod.join, "s")
    assert found.established and found.evidence.shape == "string"


@pytest.mark.parametrize("name, values, expected", [
    ("length", {"xs": 1.5}, ("xs", 6)),
    ("odd", {"x": 2.0}, ("x", 22)),
    ("join", {"s": 1.0}, ("s", 14)),
    ("loud", {"obj": 1.0}, ("obj", 30)),
])
def test_a_raise_at_an_operation_on_the_value_names_it(mod, name, values, expected):
    fn = getattr(mod, name)
    with pytest.raises((TypeError, AttributeError)) as info:
        fn(*values.values())
    assert wrong_shape_use(fn, values, info.value) == expected


def test_a_raise_inside_a_callee_or_after_a_rebinding_names_nothing(mod):
    with pytest.raises(TypeError) as info:
        mod.through("a")
    assert wrong_shape_use(mod.through, {"t": "a"}, info.value) is None
    with pytest.raises(TypeError) as info:
        mod.rebinds(1.0)
    assert wrong_shape_use(mod.rebinds, {"x": 1.0}, info.value) is None


def test_the_kinds_the_walk_gives_are_unchanged_by_the_extra_uses():
    fdef = ast.parse(textwrap.dedent('''
        def f(xs, d, x, s, u):
            for v in xs:
                pass
            return d["k"] + (x - 2) + (s + "!") + u * 2
    ''')).body[0]
    assert _param_kinds(fdef, ["xs", "d", "x", "s", "u"]) == {
        "xs": "sequence", "d": "dict", "x": "scalar", "s": "scalar",
        "u": "scalar"}
    uses = param_uses(fdef, ["xs", "d", "x", "s", "u"])
    assert set(uses.numeric) == {"x"} and set(uses.text) == {"s"}


@pytest.mark.parametrize("name, values", [
    ("keys", {"k": [1.0]}),
    ("members", {"k": [1.0]}),
    ("stored", {"k": [1.0]}),
    ("fmt", {"x": "a"}),
    ("shout_at", {"x": 1.0}),
])
def test_a_key_a_subscript_and_any_quoting_of_the_type_name_count(
        mod, name, values):
    fn = getattr(mod, name)
    with pytest.raises(TypeError) as info:
        fn(*values.values())
    line = info.value.__traceback__.tb_next.tb_lineno
    assert wrong_shape_use(fn, values, info.value) == ("k" if "k" in values
                                                       else "x", line)


def test_a_raise_on_a_local_copy_names_the_parameter(mod):
    with pytest.raises(TypeError) as info:
        mod.copied(1.0)
    line = info.value.__traceback__.tb_next.tb_lineno
    assert wrong_shape_use(mod.copied, {"x": 1.0}, info.value) == ("x", line)
