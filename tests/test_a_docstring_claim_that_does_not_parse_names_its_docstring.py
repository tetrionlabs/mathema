# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim in a docstring `Claims:` block that does not parse is
reported as the docstring's: `mathema.check()` raises InvalidConjecture
naming the claim, the docstring and the function, and `mathema verify`
names the docstring as where to correct it, never a claims file the
function also has."""
import pytest

import mathema
from mathema.cli import main
from mathema.conjecture import InvalidConjecture

_SOURCE = '''def discounted(price, pct):
    """Price after a discount.

    Claims:
        never_above: for price in [0, 1000], pct in [0, 100], f(price, pct) <= price
        list_domain: for pct in [[0, 10], [50]], f(100, pct) >= 0
    """
    return price - price * pct / 100
'''
_CLAIMS = """docbad.discounted:
  claims:
    - name: at_zero
      statement: "for price in [0, 10], f(price, 0) == price"
"""
_PARSER_SAYS = "isn't a recognized interval, discrete set, or named set"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "docbad.py").write_text(_SOURCE)
    (tmp_path / "docbad.claims.yaml").write_text(_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    import importlib
    import sys
    sys.modules.pop("docbad", None)
    return tmp_path, importlib.import_module("docbad")


def test_check_names_the_claim_the_docstring_and_the_function(project):
    _root, mod = project
    with pytest.raises(InvalidConjecture) as err:
        mathema.check(mod.discounted)
    text = str(err.value)
    assert "'list_domain'" in text, text
    assert "docstring" in text and "docbad.discounted" in text, text
    assert _PARSER_SAYS in text, text
    assert "claims file" not in text and ".claims.yaml" not in text, text


def test_check_with_the_retrieved_entry_names_the_docstring(project):
    root, mod = project
    with pytest.raises(InvalidConjecture) as err:
        mathema.check(mod.discounted,
                      declared=mathema.retrieve(mod.discounted, str(root)))
    text = str(err.value)
    assert "docstring" in text and "docbad.discounted" in text, text
    assert ".claims.yaml" not in text, text


def test_verify_names_the_docstring_not_the_claims_file(project, capsys):
    root, _mod = project
    rc = main(["verify", "--root", str(root)])
    out = capsys.readouterr().out
    assert rc == 2, out
    (line,) = [ln for ln in out.splitlines() if ln.startswith("FAIL docbad.discounted")]
    assert "docstring" in line and _PARSER_SAYS in line, line
    assert "docbad.claims.yaml" not in line, line
