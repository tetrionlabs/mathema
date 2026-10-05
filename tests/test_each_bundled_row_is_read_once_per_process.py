# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Registering the bundled library claims reads each row's statement
with the claim grammar once per process, however many questions the
registration asks of it (is it a pinned row, which region does it
state, is it the bare totality row), and installing again for another
root reads nothing twice."""
import pytest

pytest.importorskip("numpy")


def test_each_row_statement_is_parsed_once(monkeypatch):
    import mathema.conjecture as conjecture
    from mathema import compendium
    compendium._ROW_CLAIMS.clear()
    seen: list = []
    real = conjecture.claim

    def counting(text, *args, **kwargs):
        seen.append((text, kwargs.get("name")))
        return real(text, *args, **kwargs)
    monkeypatch.setattr(conjecture, "claim", counting)
    compendium.uninstall()
    compendium.register_library_claims(None)
    first = len(seen)
    assert first > 0
    assert len(set(seen)) == first, [s for s in set(seen)
                                     if seen.count(s) > 1][:5]
    compendium.uninstall()
    compendium.register_library_claims(None)
    assert len(seen) == first
