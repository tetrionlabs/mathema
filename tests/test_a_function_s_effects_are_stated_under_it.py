# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What examining a function's source finds it does beyond returning a
value is recorded as a fact: in the record's meta and as one line under
the function in the report. An effect reachable only through an
argument the caller must pass (an `out` that defaults to None) leaves
the default call free of effects, which is what `is_state_safe` judges
and what the line says. An automatic check mathema does not run leaves
no row, and `is_state_safe` is suggested only for a function with no
side effects at its defaults."""
import textwrap

import pytest

import mathema
from mathema.suggest import suggest_claims


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _module(tmp_path, name, body):
    import importlib.util
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BODY = '''
    import os


    def logged(x: float) -> float:
        with open("app.log", "a") as fh:
            fh.write(str(x))
        return x * float(os.environ.get("SCALE", "1"))


    def total(xs: list, out=None) -> float:
        s = sum(xs)
        if out is not None:
            out.append(s)
        return s


    def double(x: float) -> float:
        return 2.0 * x
'''


def test_the_effects_line_and_meta(tmp_path):
    mod = _module(tmp_path, "effects_mod", _BODY)
    rec = mathema.check(mod.logged)
    effects = rec.meta["mathema.effects"]
    assert effects["line"] == "opens a file for writing, reads os.environ"
    assert "  effects: opens a file for writing, reads os.environ" in repr(rec)
    # the automatic battery it does not run leaves no row
    assert not any(p.name == "purity" for p in rec.probes)


def test_an_effect_only_through_a_passed_argument(tmp_path):
    mod = _module(tmp_path, "effects_mod_out", _BODY)
    rec = mathema.check(mod.total)
    line = rec.meta["mathema.effects"]["line"]
    assert line == "no side effects with default values"
    assert "out" not in line
    state = next(p for p in rec.probes if p.name == "is_state_safe")
    assert state.verdict == "proven", (state.verdict, state.sketch)


def test_a_pure_function_says_so(tmp_path):
    mod = _module(tmp_path, "effects_mod_pure", _BODY)
    rec = mathema.check(mod.double)
    assert rec.meta["mathema.effects"]["line"] == "no side effects"


def test_is_state_safe_is_suggested_only_without_default_effects(tmp_path):
    mod = _module(tmp_path, "effects_mod_suggest", _BODY)
    assert "is_state_safe" in {c.name for c in suggest_claims(mod.double)}
    assert "is_state_safe" in {c.name for c in suggest_claims(mod.total)}
    assert "is_state_safe" not in {c.name for c in suggest_claims(mod.logged)}
