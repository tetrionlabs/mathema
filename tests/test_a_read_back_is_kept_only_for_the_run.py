# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The reading back of a stored text is kept for one run, no longer.

How a text reads as a claim depends on more than the text: a project's
`defines:` rows, its sentinel words and the capability providers
installed all change it. Inside a run scope a text read back once is
not read again in that run; outside one, and in the next run, every
reading reads the text again, so a reading made under other
definitions is never reused.
"""
from mathema import conjecture, spec
from mathema._run_scope import run_scope


def _counting_parse(monkeypatch):
    calls = []
    real = conjecture.claim

    def counted(text, *a, **kw):
        calls.append(text)
        return real(text, *a, **kw)

    monkeypatch.setattr(conjecture, "claim", counted)
    return calls


def test_outside_a_run_each_read_back_reads_the_text(monkeypatch):
    calls = _counting_parse(monkeypatch)
    for _ in range(2):
        assert spec._reread("f(x) = 1", ("ctx",))[0] is None
    assert calls == ["f(x) = 1", "f(x) = 1"]


def test_a_reading_under_other_definitions_is_not_reused(monkeypatch):
    first = spec._reread("f(x) = 1", ("ctx",))
    assert first[0] is None

    def refuses(text, *a, **kw):
        raise conjecture.InvalidConjecture("not a claim here")

    monkeypatch.setattr(conjecture, "claim", refuses)
    later = spec._reread("f(x) = 1", ("ctx",))
    assert later[0] is not None and "not a claim here" in later[0]


def test_inside_a_run_a_text_is_read_back_once(monkeypatch):
    calls = _counting_parse(monkeypatch)
    with run_scope():
        for _ in range(3):
            assert spec._reread("f(x) = 2", ("ctx",))[0] is None
    assert calls == ["f(x) = 2"]
    with run_scope():
        spec._reread("f(x) = 2", ("ctx",))
    assert calls == ["f(x) = 2", "f(x) = 2"]
