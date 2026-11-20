# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The stored text of a claim is refused when it does not read back.

`canonical_claim_text` reads its own output back before handing it
over. When the text reads as a different claim (another string literal
value, another relation) or does not read at all, it raises
`CanonicalTextError`, an `InvalidConjecture` naming the claim and the
text, so no record is written under a wrong statement. `verify`
reports that claim on its own and checks the function's other claims.
"""
import os
import subprocess
import sys
import textwrap

import pytest
import yaml

from mathema import grammar
from mathema.conjecture import CanonicalTextError, InvalidConjecture, claim
from mathema.spec import canonical_claim_text

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _swap_quotes(text: str) -> str:
    """The old whole-text quoting, which pairs the quotes of two
    literals wrongly."""
    return grammar._legacy_double_quoted(text)


def test_text_reading_back_as_another_claim_is_refused(monkeypatch):
    monkeypatch.setattr(grammar, "_double_quoted", _swap_quotes)
    with pytest.raises(CanonicalTextError) as caught:
        canonical_claim_text(claim("f(x, '}\"', 's') == 1"))
    assert isinstance(caught.value, InvalidConjecture)
    assert "f(x, '}\"\", \"s') = 1" in str(caught.value), str(caught.value)


def test_text_that_does_not_read_is_refused(monkeypatch):
    monkeypatch.setattr(grammar, "_double_quoted", _swap_quotes)
    with pytest.raises(CanonicalTextError):
        canonical_claim_text(claim("f(x, 'a\"b\\'c') == 1"))


def test_text_stating_another_relation_is_refused(monkeypatch):
    from mathema import spec
    real = spec.render_claim_text

    def flipped(cj, **kw):
        return real(cj, **kw).replace(" <= ", " >= ")

    monkeypatch.setattr(spec, "render_claim_text", flipped)
    with pytest.raises(CanonicalTextError):
        canonical_claim_text(claim("f(x) <= g(x)"))


def test_text_spelling_a_number_another_way_is_not_refused():
    text = canonical_claim_text(claim("for x in [1, 2], f(x) <= x * 1e308 * 10"))
    assert "f(x) <=" in text


def test_text_that_reads_back_is_returned():
    assert canonical_claim_text(claim("f(x, '}\"', 's') == 1")) \
        == "f(x, '}\"', \"s\") = 1"


_MOD = '''
def tag(x: str, body: str = "", t: str = "") -> int:
    """The length of `t`."""
    return len(t)
'''

_CLAIMS = r"""
rbpkg.mod.tag:
  claims:
    - name: two_literals
      statement: "for x in {\"a\"}, f(x, '}\"', t='s') == 1"
    - name: plain
      statement: 'for x in {"a"}, f(x, t="ab") == 2'
"""


def test_verify_reports_the_refused_claim_and_checks_the_rest(tmp_path):
    pkg = tmp_path / "rbpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "r.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    run = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema import grammar; "
         "grammar._double_quoted = grammar._legacy_double_quoted; "
         "from mathema.cli import main; "
         f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}]))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert run.returncode != 0, run.stdout + run.stderr
    assert "Traceback" not in run.stderr, run.stderr
    assert "two_literals" in run.stdout and "does not read back" in run.stdout, run.stdout
    assert "no record was written for it" in run.stdout, run.stdout
    record = tmp_path / ".mathema" / "verified" / "rbpkg.mod.tag.yaml"
    rows = {r["name"]: r for r in yaml.safe_load(record.read_text())["rbpkg.mod.tag"]["claims"]}
    assert "two_literals" not in rows
    assert rows["plain"]["verdict"] in ("proven", "holds"), rows["plain"]


def _verify_with_the_old_quoting(tmp_path):
    pkg = tmp_path / "rbpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "r.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    run = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema import grammar; "
         "grammar._double_quoted = grammar._legacy_double_quoted; "
         "from mathema.cli import main; "
         f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}]))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    return run


def test_verify_says_a_refused_claim_is_a_defect_in_mathema(tmp_path):
    run = _verify_with_the_old_quoting(tmp_path)
    lines = [ln for ln in run.stdout.splitlines() if "two_literals" in ln]
    assert len(lines) == 1, run.stdout
    assert "defect in mathema's rendering" in lines[0], lines[0]
    assert "not checked" in lines[0], lines[0]
    assert "correct it there" not in lines[0], lines[0]
    assert run.returncode == 1, run.stdout + run.stderr
