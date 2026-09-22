# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The surface/author provenance split.

The authoring surface rides `meta['mathema.surface']` as a clean
sentinel (never the old `mathema.claim_source: "the author"` literal),
and is load-bearing in gating exactly as before. The author identity
(the model, harness, or git username that proposed the claim) is a
separate, optional fact: absent unless stated, sourced from the claim's
own authored statement or the `MATHEMA_CLAIM_SOURCE` environment, and
rendered as `authored.by`, never on a surface mathema itself generated.
"""
import sys

import mathema
from mathema.records import row_source
from mathema.spec import authored_block, to_spec
from mathema.verify import _volunteered

_SRC = '''\
def clamp(x: float) -> float:
    """Clamp negatives to zero.

    Claims:
        nonneg [probe]: for x in [-5, 5], f(x) >= 0
    """
    return x if x > 0 else 0.0
'''


def _spec(tmp_path):
    (tmp_path / "clamp_fixture.py").write_text(_SRC)
    sys.path.insert(0, str(tmp_path))
    try:
        mod = __import__("clamp_fixture")
    finally:
        sys.path.remove(str(tmp_path))
    return to_spec(mathema.check(mod.clamp))


# --- the surface rides its own honest key -----------------------------------

def test_surface_key_replaces_claim_source(tmp_path):
    row = next(c for c in _spec(tmp_path)["claims"] if c["name"] == "nonneg")
    meta = row.get("meta") or {}
    assert meta.get("mathema.surface") == "docstring"
    assert "mathema.claim_source" not in meta       # the old key is retired


def test_row_source_reads_the_surface_key():
    # the clean tokens, and the pre-rename spellings still read forward
    assert row_source({"mathema.surface": "declared"}) == "declared"
    assert row_source({"mathema.surface": "decorator"}) == "decorator"
    assert row_source({"mathema.surface": "the author"}) == "declared"
    assert row_source({"mathema.surface": "author"}) == "decorator"


def test_suggested_claim_still_never_gates():
    # the surface split must not weaken the one load-bearing gate: a
    # suggestion mathema volunteered is reported but never gates
    assert _volunteered({"mathema.surface": "mathema"}, "") is True
    assert _volunteered({"mathema.surface": "docstring"}, "") is False
    assert _volunteered({}, "conjectured by mathema: try nonneg") is True


# --- the author is a separate, optional fact --------------------------------

def test_author_absent_without_env(monkeypatch):
    monkeypatch.delenv("MATHEMA_CLAIM_SOURCE", raising=False)
    block = authored_block({"mathema.surface": "docstring"})
    assert block["surface"] == "docstring"
    assert "by" not in block


def test_author_from_env_lands_in_authored_by(monkeypatch):
    monkeypatch.setenv("MATHEMA_CLAIM_SOURCE", "claude-opus")
    block = authored_block({"mathema.surface": "docstring"})
    assert block["by"] == "claude-opus"


def test_no_env_author_on_mathema_generated_surfaces(monkeypatch):
    # a builtin/suggested/compendium row is authored by mathema, not by
    # the agent that happened to run the verification
    monkeypatch.setenv("MATHEMA_CLAIM_SOURCE", "claude-opus")
    for sentinel in ("mathema", "builtin", "compendium"):
        assert "by" not in authored_block({"mathema.surface": sentinel}), sentinel


def test_declared_authored_by_wins_over_env(monkeypatch):
    # an explicit authored statement is the author's own word; the
    # environment fallback never overwrites it
    monkeypatch.setenv("MATHEMA_CLAIM_SOURCE", "harness")
    block = authored_block({"mathema.surface": "docstring",
                            "mathema.authored": {"by": "a-human"}})
    assert block["by"] == "a-human"
