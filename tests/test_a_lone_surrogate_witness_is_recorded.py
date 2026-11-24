# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A falsifying argument holding a lone surrogate (a code point from
U+D800 to U+DFFF standing alone, which Python strings allow and YAML
cannot spell) is stored in the record as an escaped string under an
`escaped_str` tag, reads back as the very string it was, and replays
as the record's pinned witness. A string with no lone surrogate is
stored as itself."""
import importlib
import sys

import pytest
import yaml

from mathema.conjecture import _pinned_arg_sets, _yaml_safe_args, claim
from mathema.spec import _SAFE_LOADER, dump_yaml, load_verified

WITNESSES = [
    pytest.param("\ud800", id="lone-high"),
    pytest.param("\udc00", id="lone-low"),
    pytest.param("\U0001f600", id="astral"),
    pytest.param("a\\ud800\ud800\udfff\U0001f600\\\n\udc00\ud83d\ude00z",
                 id="mixed"),
]


@pytest.mark.parametrize("text", WITNESSES)
def test_a_witness_reads_back_as_the_string_it_was(text):
    safe = _yaml_safe_args((text, [text], {"k": text}))
    written = dump_yaml({"meta": {"mathema.counterexample_args": safe}})
    for loader in (yaml.SafeLoader, _SAFE_LOADER):
        back = yaml.load(written, Loader=loader)
        assert back["meta"]["mathema.counterexample_args"] == safe
    cj = claim("f(x, y, z) == 0")
    cj.pins = [{"args": back["meta"]["mathema.counterexample_args"]}]
    assert _pinned_arg_sets(cj, 3) == [[text, [text], {"k": text}]]


def test_the_stored_spelling_is_escaped_and_readable():
    assert _yaml_safe_args(("a\ud800\\b",)) == [{"escaped_str": "a\\uD800\\\\b"}]
    assert dump_yaml({"v": _yaml_safe_args(("a\udc00",))}) == \
        'v:\n  - escaped_str: "a\\\\uDC00"\n'


def test_a_string_without_a_lone_surrogate_is_stored_as_itself():
    for text in ("plain", "\U0001f600", "a\\uD800", ""):
        assert _yaml_safe_args((text,)) == [text]


def test_a_mapping_shaped_like_the_tag_stays_a_mapping():
    cj = claim("f(x) == 0")
    cj.pins = [{"args": [{"escaped_str": "no surrogate here"}]}]
    assert _pinned_arg_sets(cj, 1) == [[{"escaped_str": "no surrogate here"}]]


_BODY = '''\
def encoded(text: str) -> bytes:
    return text.encode("utf-8")


def double(n: int) -> int:
    return 2 * n
'''

_CLAIMS = '''\
lonesurr.encoded:
  claims:
    - name: grows
      statement: "for text in L[lone_surrogates], len(f(text)) >= len(text)"
lonesurr.double:
  claims:
    - name: twice
      statement: "for n in [0, 10] subset Z, f(n) == n + n"
'''


def _language(pool):
    from mathema.languages import StringLanguage
    return StringLanguage("lone_surrogates", char_ok=lambda c: True, pool=pool)


@pytest.fixture
def project(tmp_path, monkeypatch):
    from mathema.languages import register_language, unregister_language
    sys.modules.pop("lonesurr", None)
    importlib.invalidate_caches()
    (tmp_path / "lonesurr.py").write_text(_BODY)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "demo.claims.yaml").write_text(_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    register_language("lone_surrogates", _language("\ud800\udc00"))
    yield tmp_path
    unregister_language("lone_surrogates")
    sys.modules.pop("lonesurr", None)


def _claim_row(root, key, name):
    entry = load_verified(str(root))[key]["entry"]
    return next(c for c in entry["claims"] if c["name"] == name)


def test_a_falsification_at_a_lone_surrogate_is_recorded(project):
    from mathema.verify import verify_project
    out = verify_project(root=str(project))
    assert any("lonesurr.encoded" in p for p in out.problems), out.problems
    rows = {row["key"]: row for row in out.keys}
    assert rows["lonesurr.double"]["passed"], rows["lonesurr.double"]
    assert rows["lonesurr.encoded"]["counts"]["falsified"] >= 1
    grows = _claim_row(project, "lonesurr.encoded", "grows")
    assert grows["verdict"] == "falsified", grows
    (stored,) = grows["meta"]["mathema.counterexample_args"]
    cj = claim("f(x) == 0")
    cj.pins = [{"args": [stored]}]
    (witness,) = _pinned_arg_sets(cj, 1)[0]
    assert isinstance(witness, str) and witness
    assert all(0xD800 <= ord(ch) <= 0xDFFF for ch in witness), witness
    assert _claim_row(project, "lonesurr.double", "twice")["verdict"] == "proven"


def test_the_pinned_lone_surrogate_witness_replays(project):
    from mathema.languages import register_language
    from mathema.verify import verify_project
    verify_project(root=str(project))
    first = _claim_row(project, "lonesurr.encoded", "grows")
    register_language("lone_surrogates", _language("ab"))
    verify_project(root=str(project), all=True)
    again = _claim_row(project, "lonesurr.encoded", "grows")
    assert again["verdict"] == "falsified", again
    assert again["meta"]["mathema.counterexample_args"] == \
        first["meta"]["mathema.counterexample_args"]
