# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The target-resolver seam: language-tagged keys become callables.

A registered resolver turns `ts:src/ema.ts#ema` into a Target of
Python proxies; everything downstream runs unchanged. The seam is
fail-soft (a broken resolver warns and falls through), and an
unregistered tag fails with the remedy rather than the bogus
module-import error it used to produce.
"""
from dataclasses import replace

import pytest

import mathema._target_resolvers as tr
from mathema.analysis import analyze_source
from mathema.targets import Target, TargetError, resolve


def _proxy_for(key):
    def double(x: float) -> float:
        """Twice x."""
        return 2 * x

    facts = replace(analyze_source(double), tree=None,
                    form="ts:aabbccdd0011")
    double.__module__ = ""
    double.__qualname__ = key
    double.__mathema_facts__ = facts
    return double


@pytest.fixture
def registered(monkeypatch):
    """A fake `ts` resolver registered without entry-point machinery."""
    calls = []

    def resolver(target, root):
        calls.append((target, root))
        if "#missing" in target:
            return None
        return Target("function", {target: _proxy_for(target)},
                      None, root, [])

    monkeypatch.setattr(tr, "get_resolver",
                        lambda prefix, default=None:
                        resolver if prefix == "ts" else default)
    return calls


def test_a_tagged_key_resolves_through_its_resolver(registered):
    target = resolve("ts:src/ema.ts#ema", ".")
    assert target.kind == "function"
    (key,) = target.functions
    assert key == "ts:src/ema.ts#ema"
    assert registered == [("ts:src/ema.ts#ema", ".")]


def test_a_resolver_returning_none_falls_through(registered):
    # "not mine": the ordinary path then reports its ordinary error
    with pytest.raises(TargetError):
        resolve("ts:src/ema.ts#missing", ".")


def test_an_unregistered_tag_names_the_remedy():
    with pytest.raises(TargetError, match="no target resolver is registered"):
        resolve("cpp:libema.dylib#ema", ".")


def test_python_targets_are_untouched(registered):
    # a dotted key with a colon that is NOT a registered tag behaves
    # exactly as before
    target = resolve("mathema.records:stance", ".")
    assert "stance" in "".join(target.functions)


def test_a_broken_resolver_warns_and_skips(monkeypatch):
    class Boom:
        name = "ts"
        value = "broken.module:resolver"

        def load(self):
            raise RuntimeError("no")

    tr._load.cache_clear()
    monkeypatch.setattr(tr, "_discovered", lambda: {"ts": Boom()})
    try:
        with pytest.warns(UserWarning, match="failed to load"):
            assert tr.get_resolver("ts") is None
    finally:
        # monkeypatch restores _discovered itself after this block;
        # only the per-name load cache carries state across tests
        tr._load.cache_clear()


def test_injected_facts_win_over_source_analysis():
    import mathema
    proxy = _proxy_for("ts:x#f")
    facts = mathema.analyze(proxy)
    assert facts.form == "ts:aabbccdd0011"
    assert facts.tree is None


def test_track_claims_key_matches_fn_key_for_a_proxy():
    """The two key sites must agree byte-for-byte, or a proxy's
    registry key grows a leading dot."""
    import mathema
    from mathema.authoring import _fn_key
    proxy = _proxy_for("ts:src/ema.ts#ema")
    mathema.track_claims(proxy)
    assert proxy.__mathema__["key"] == _fn_key(proxy) == "ts:src/ema.ts#ema"


def test_verify_sweep_resolves_a_store_key_through_the_seam(monkeypatch):
    from mathema.conjecture import _resolve_func_ref
    proxy = _proxy_for("ts:src/ema.ts#ema")
    monkeypatch.setattr(tr, "get_resolver",
                        lambda prefix, default=None:
                        (lambda target, root:
                         Target("function", {target: proxy}, None, root, []))
                        if prefix == "ts" else default)
    fn = _resolve_func_ref("ts:src/ema.ts#ema", root=".")
    assert fn is proxy
    # untagged refs keep their exact old behaviour
    assert _resolve_func_ref("mathema.records.stance") is not None
    assert _resolve_func_ref("nodots") is None


def test_a_proxy_checks_end_to_end(registered):
    import mathema
    target = resolve("ts:src/ema.ts#ema", ".")
    (key, proxy), = target.functions.items()
    rec = mathema.check(proxy, claims=["for x in [0, 4], f(x) >= 0"])
    (p,) = [q for q in rec.probes if q.name.startswith("f_x")]
    assert p.verdict == "holds"
    assert rec.facts.form.startswith("ts:")
