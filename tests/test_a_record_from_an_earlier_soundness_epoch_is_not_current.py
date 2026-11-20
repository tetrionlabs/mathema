# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record whose form still matches the code is not current when a row
of it was proven by reading a `raise` under an earlier soundness epoch.
Every command that already judges whether a stored record is current
counts that staleness in the same judgement: `mathema verify --status`,
the record freshness docstring sync reports, and the freshness of a
callee's record a caller depends on."""
from mathema.analysis import effective_facts
from mathema.authoring import _fn_key


def rejects_negative(x: float) -> float:
    """Rejects a negative x."""
    if x < 0:
        raise ValueError("negative")
    return x


def _entry(stamp):
    meta = {} if stamp is None else {"mathema.soundness_epoch": stamp}
    return {"identity": {"form": effective_facts(rejects_negative).form},
            "claims": [{"name": "rejects",
                        "statement": "for x in [-5, -1], raises(f(x), ValueError)",
                        "verdict": "proven", "route": "derive", "meta": meta}]}


def test_docstring_sync_reports_a_record_from_an_earlier_epoch_as_stale():
    from mathema.docstring import docstring_sync
    key = _fn_key(rejects_negative)
    before = docstring_sync(rejects_negative, declared={},
                            verified={key: {"entry": _entry(None)}})
    now = docstring_sync(rejects_negative, declared={},
                         verified={key: {"entry": _entry(1)}})
    assert before.record_stale is True
    assert now.record_stale is False


def test_a_callee_record_from_an_earlier_epoch_is_not_current():
    from mathema.spec import _dependency_state
    key = _fn_key(rejects_negative)
    dep = {"key": key, "form": effective_facts(rejects_negative).form, "kind": "function"}
    assert _dependency_state(dep, {key: {"entry": _entry(None)}}) == "invalidated"
    assert _dependency_state(dep, {key: {"entry": _entry(1)}}) == "current"


def test_status_reports_a_record_from_an_earlier_epoch_as_stale(monkeypatch):
    import mathema
    from mathema import spec
    key = _fn_key(rejects_negative)
    monkeypatch.setattr(mathema, "tagged", lambda: {key: rejects_negative})
    for stamp, word in ((None, "stale"), (1, "fresh")):
        monkeypatch.setattr(spec, "load_verified",
                            lambda root, s=stamp: {key: {"entry": _entry(s),
                                                         "source": "verified"}})
        line = next(ln for ln in mathema.status().splitlines() if key in ln)
        assert word in line, line
