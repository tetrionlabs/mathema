# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Reading a prior record while writing the next one, loading a claims
file and looking up a record entry all parse with the libyaml loader,
and that loader reads record text exactly as the pure-Python one does."""
import traceback

import pytest
import yaml

import mathema
from mathema.records import Probe
from mathema.spec import _SAFE_LOADER, load_claims, record

pytestmark = pytest.mark.skipif(
    _SAFE_LOADER is yaml.SafeLoader, reason="PyYAML built without libyaml")


def _square(x: float) -> float:
    """Square."""
    return x * x


def _record(root, verdict):
    return record(mathema.Record(facts=mathema.analyze(_square), probes=[
        Probe("nonneg", "f(x) >= 0", verdict, route="derive")]),
        key="t.f", root=root)


def _spy_pure_loads(monkeypatch):
    """Count every parse that goes through the pure-Python loader, apart
    from the key writer's check that a key reads back under both."""
    calls = []
    real_load = yaml.load

    def note(loader):
        names = {f.name for f in traceback.extract_stack()}
        if "_bare_key_reads_back" not in names:
            calls.append(loader)

    def load(stream, Loader=None):
        note(Loader)
        return real_load(stream, Loader=Loader)

    def safe_load(stream):
        note(yaml.SafeLoader)
        return real_load(stream, Loader=yaml.SafeLoader)

    monkeypatch.setattr(yaml, "load", load)
    monkeypatch.setattr(yaml, "safe_load", safe_load)
    return lambda: [c for c in calls if c is yaml.SafeLoader]


def test_writing_a_record_never_parses_the_prior_one_in_pure_python(
        tmp_path, monkeypatch):
    root = str(tmp_path)
    _record(root, "proven")
    pure = _spy_pure_loads(monkeypatch)
    _record(root, "unknown")
    assert pure() == []


def test_loading_a_claims_file_does_not_use_the_pure_python_loader(
        tmp_path, monkeypatch):
    path = tmp_path / "claims.yaml"
    path.write_text("f:\n  claims:\n  - name: a\n    statement: f(x) >= 0\n")
    pure = _spy_pure_loads(monkeypatch)
    assert "f" in load_claims(str(path))
    assert pure() == []


def test_a_record_entry_lookup_does_not_use_the_pure_python_loader(
        tmp_path, monkeypatch):
    from mathema.verify import _entry_at
    path = tmp_path / "r.yaml"
    path.write_text("k:\n  claims: []\n")
    pure = _spy_pure_loads(monkeypatch)
    assert _entry_at(str(path), "k") == {"claims": []}
    assert pure() == []


RECORD_TEXTS = [
    "k:\n  name: 'null'\n  a: 'no'\n  b: 'on'\n  c: '1.50'\n  d: '0x1F'\n",
    "k:\n  a: null\n  b: no\n  c: on\n  d: 1.50\n  e: 0x1F\n  f: 1e3\n"
    "  g: 2026-11-19\n  h: ~\n  i: .inf\n  j: 0o17\n  k: 010\n",
    "k:\n  s: caf\u00e9 \u03c0 \u2264 \U0001f600\n  t: \"tab\\tq\\u00e9\"\n",
    "k:\n  doc: |\n    line one\n\n    line two\n  fold: >-\n    a\n    b\n"
    "  quoted: 'it''s'\n",
    "k:\n  claims:\n  - name: a\n    tags: [x, y, [1, 2]]\n"
    "    rows:\n    - {p: 1, q: [a, b]}\n    - - 1\n      - - 2\n",
    "k:\n  base: &b {x: 1, y: [2, 3]}\n  copy: *b\n  merged:\n"
    "    <<: *b\n    z: 4\n",
    "null: 1\ntrue: 2\n'no': 3\n",
    "k: {}\nj: []\nm: ''\n",
    "",
    "- a\n- b\n",
]


@pytest.mark.parametrize("text", RECORD_TEXTS)
def test_the_c_loader_reads_record_text_as_the_pure_python_loader_does(text):
    assert yaml.load(text, Loader=_SAFE_LOADER) == yaml.load(
        text, Loader=yaml.SafeLoader)
