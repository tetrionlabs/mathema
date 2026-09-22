# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Human verification: the PIN credential, the gate at the acceptance
apply boundary, and the project policy.

The credential lives at user level (`XDG_CONFIG_HOME` here, a temp
directory per test), and the gate's contract is: unconfigured means the
feature is off; configured means nothing writes without a person at a
terminal, and every verified write is stamped with the credential's
key id so a later reader can see which credential signed.
"""
import getpass

import pytest
import yaml

from mathema import auth
from mathema.auth import HumanVerificationError


@pytest.fixture(autouse=True)
def user_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return tmp_path / "xdg"


@pytest.fixture
def tty(monkeypatch):
    """A controlling terminal, simulated: entered codes come from a
    list the test controls."""
    entries: list = []
    monkeypatch.setattr(auth, "_tty_available", lambda: True)
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": entries.pop(0))
    return entries


# --- the credential ---------------------------------------------------------

def test_pin_round_trip_and_permissions():
    import os
    info = auth.set_pin("4321")
    assert info["method"] == "pin" and len(info["key"]) == 6
    assert auth.verify_code("4321") is True
    assert auth.verify_code("1111") is False
    assert auth.verify_code("") is False
    assert (os.stat(auth.config_path()).st_mode & 0o777) == 0o600


def test_pin_shape_is_enforced():
    for bad in ("abc", "123", "1" * 13, "12 34"):
        with pytest.raises(HumanVerificationError):
            auth.set_pin(bad)


def test_totp_rfc6238_vectors_and_skew():
    # RFC 6238 Appendix B, SHA-1, secret "12345678901234567890":
    # T=59s -> 94287082, T=1111111109 -> 07081804
    import base64
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    rec = {"method": "totp", "secret": secret, "key": "test"}
    assert auth.verify_code("287082", record=rec, now=59)
    assert auth.verify_code("081804", record=rec, now=1111111109)
    assert not auth.verify_code("000000", record=rec, now=59)
    # one window of clock skew each way, no more
    assert auth.verify_code("287082", record=rec, now=59 + 30)
    assert not auth.verify_code("287082", record=rec, now=59 + 120)


def test_remove_and_unconfigured_gate_is_open():
    auth.set_pin("4321")
    assert auth.remove() is True
    assert auth.configured() is None
    # no credential: the gate is a no-op and the write proceeds
    assert auth.require_human("test") is None


# --- the gate ---------------------------------------------------------------

def test_gate_refuses_without_a_terminal(monkeypatch):
    auth.set_pin("4321")
    monkeypatch.setattr(auth, "_tty_available", lambda: False)
    with pytest.raises(HumanVerificationError, match="interactive terminal"):
        auth.require_human("accept --as evidence")


def test_gate_returns_the_attestation_on_a_correct_code(tty):
    info = auth.set_pin("4321")
    tty.append("4321")
    assert auth.require_human("x") == {"method": "pin", "key": info["key"]}


def test_gate_fails_after_three_wrong_codes(tty):
    auth.set_pin("4321")
    tty.extend(["1111", "2222", "3333"])
    with pytest.raises(HumanVerificationError, match="3 attempts"):
        auth.require_human("x")
    assert tty == []   # all three consumed


# --- the gate at the apply boundary, end to end -----------------------------

_FIXTURE = '''\
def settle(x: float) -> float:
    """Settlement amount.

    Claims:
        nonneg [probe]: for x in [-5, 5], f(x) >= 0
    """
    return abs(x)
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    import mathema
    src = tmp_path / "gatefix.py"
    src.write_text(_FIXTURE)
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = __import__("gatefix")
    mathema.write_spec(mod.settle, root=str(tmp_path))
    return tmp_path


def _record(project):
    path = project / ".mathema" / "verified" / "gatefix.settle.yaml"
    return yaml.safe_load(path.open())["gatefix.settle"]


def test_acceptance_is_refused_agent_shaped(project, monkeypatch):
    # a PIN is set and there is no terminal: the exact shape of an
    # agent driving the CLI or the library. Nothing is written.
    from mathema.acceptance import apply_acceptance, plan_acceptance
    auth.set_pin("4321")
    monkeypatch.setattr(auth, "_tty_available", lambda: False)
    plan = plan_acceptance(str(project), "gatefix.settle", "nonneg",
                           "evidence", by="agent")
    with pytest.raises(HumanVerificationError):
        apply_acceptance(plan)
    assert "accepted" not in [k for c in _record(project)["claims"] for k in c]


def test_acceptance_with_pin_stamps_verified_by(project, tty):
    from mathema.acceptance import apply_acceptance, plan_acceptance
    info = auth.set_pin("4321")
    tty.append("4321")
    plan = plan_acceptance(str(project), "gatefix.settle", "nonneg",
                           "evidence", by="turing")
    apply_acceptance(plan)
    claim = next(c for c in _record(project)["claims"]
                 if c["name"] == "nonneg")
    assert claim["accepted"]["verified_by"] == {"method": "pin",
                                                "key": info["key"]}
    assert claim["acceptance_history"][-1]["verified_by"]["key"] == info["key"]


def test_acceptance_without_pin_configured_still_works(project):
    # the feature is opt-in: no credential, no prompt, no stamp
    from mathema.acceptance import apply_acceptance, plan_acceptance
    plan = plan_acceptance(str(project), "gatefix.settle", "nonneg",
                           "evidence", by="turing")
    apply_acceptance(plan)
    claim = next(c for c in _record(project)["claims"]
                 if c["name"] == "nonneg")
    assert claim["accepted"]["as"] == "evidence"
    assert "verified_by" not in claim["accepted"]


def test_acceptance_restamps_integrity(project, tty):
    # the main apply branch restamps, and the checksum covers the
    # accepted block, so a later hand-strip of the sign-off trips it
    from mathema.acceptance import apply_acceptance, plan_acceptance
    from mathema.spec import integrity_checksum
    auth.set_pin("4321")
    tty.append("4321")
    plan = plan_acceptance(str(project), "gatefix.settle", "nonneg",
                           "evidence", by="turing")
    apply_acceptance(plan)
    entry = _record(project)
    assert entry["identity"]["integrity"] == integrity_checksum(entry)
    stripped = dict(entry)
    stripped["claims"] = [
        {k: v for k, v in c.items() if k != "accepted"}
        for c in entry["claims"]]
    assert integrity_checksum(stripped) != entry["identity"]["integrity"]


# --- policy -----------------------------------------------------------------

def _write_policy(root, body):
    meta = root / ".mathema" / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "policy.yaml").write_text(body)


def test_policy_requires_verification(project):
    from mathema.acceptance import apply_acceptance, plan_acceptance
    _write_policy(project, "acceptance:\n  require_verification: true\n")
    plan = plan_acceptance(str(project), "gatefix.settle", "nonneg",
                           "evidence", by="turing")
    # no credential configured: the policy refuses the unverified write
    with pytest.raises(HumanVerificationError, match="policy requires"):
        apply_acceptance(plan)


def test_policy_can_disable_the_static_pin(project, tty):
    # the enterprise ruling: methods: [totp] means a static PIN, even
    # correctly entered, does not satisfy the policy
    from mathema.acceptance import apply_acceptance, plan_acceptance
    _write_policy(project,
                  "acceptance:\n  require_verification: true\n"
                  "  methods: [totp]\n")
    auth.set_pin("4321")
    tty.append("4321")
    plan = plan_acceptance(str(project), "gatefix.settle", "nonneg",
                           "evidence", by="turing")
    with pytest.raises(HumanVerificationError, match="only totp"):
        apply_acceptance(plan)


def test_verify_fails_a_standing_unverified_acceptance(project):
    # the CI half: an acceptance written before the policy (or forged
    # into the YAML by hand) fails the sweep once the policy requires
    # verification
    from mathema.acceptance import apply_acceptance, plan_acceptance
    from mathema.verify import verify_project
    plan = plan_acceptance(str(project), "gatefix.settle", "nonneg",
                           "evidence", by="turing")
    apply_acceptance(plan)   # no credential: unverified acceptance
    _write_policy(project, "acceptance:\n  require_verification: true\n")
    out = verify_project(root=str(project))
    assert any("not human-verified" in p for p in out.problems)


def test_verify_passes_a_conforming_acceptance(project, tty):
    from mathema.acceptance import apply_acceptance, plan_acceptance
    from mathema.verify import verify_project
    info = auth.set_pin("4321")
    tty.append("4321")
    plan = plan_acceptance(str(project), "gatefix.settle", "nonneg",
                           "evidence", by="turing")
    apply_acceptance(plan)
    _write_policy(project,
                  "acceptance:\n  require_verification: true\n"
                  f"  keys: [{info['key']}]\n")
    out = verify_project(root=str(project))
    assert not any("acceptance" in p and "verified" in p
                   for p in out.problems)


def test_concepts_curation_is_gated_too(project, monkeypatch):
    # the one path that used to write with no prompt at all
    from mathema.concepts import accept_concepts
    auth.set_pin("4321")
    monkeypatch.setattr(auth, "_tty_available", lambda: False)
    with pytest.raises(HumanVerificationError):
        accept_concepts(str(project), "gatefix.settle",
                        ["symmetry"], [], by="agent")
