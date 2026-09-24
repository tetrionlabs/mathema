# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The verified record as tamper-evident, durable evidence: a record
write is all-or-nothing, the integrity checksum covers what a claim
states and every retirement row, a checksum mismatch fails the sweep
under a `require_verification` policy, and a retirement row the policy
would never have written cannot quietly remove a claim from the gate.
Records stamped by the earlier checksum scheme keep loading and
verifying unchanged."""
import pytest
import yaml

from mathema import spec as spec_mod
from mathema.spec import write_yaml


@pytest.fixture(autouse=True)
def user_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return tmp_path / "xdg"


# --- atomic writes ----------------------------------------------------------

def test_an_interrupted_write_leaves_the_previous_record_whole(tmp_path,
                                                               monkeypatch):
    path = tmp_path / "rec.yaml"
    write_yaml(str(path), {"k": {"claims": [{"name": "a"}]}}, header="first")
    before = path.read_text()

    def interrupted(_data):
        raise KeyboardInterrupt("interrupt during the record write")

    monkeypatch.setattr(spec_mod, "dump_yaml", interrupted)
    with pytest.raises(KeyboardInterrupt):
        write_yaml(str(path), {"k": {"claims": []}}, header="second")
    assert path.read_text() == before
    # no temporary file is left beside the record
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rec.yaml"]


def test_a_failed_write_to_a_new_path_creates_nothing(tmp_path, monkeypatch):
    def failing(_data):
        raise OSError("disk full")

    monkeypatch.setattr(spec_mod, "dump_yaml", failing)
    with pytest.raises(OSError):
        write_yaml(str(tmp_path / "new.yaml"), {"k": {}})
    assert list(tmp_path.iterdir()) == []


def test_a_write_still_round_trips(tmp_path):
    path = tmp_path / "sub" / "rec.yaml"
    write_yaml(str(path), {"k": {"claims": [{"name": "a"}]}},
               header="one\ntwo")
    text = path.read_text()
    assert text.startswith("# one\n# two\n")
    assert yaml.safe_load(text) == {"k": {"claims": [{"name": "a"}]}}


# --- the integrity checksum -------------------------------------------------

_FIXTURE = '''\
def settle(x: float) -> float:
    """Settlement amount.

    Claims:
        nonneg [probe]: for x in [-5, 5], f(x) >= 0
        above_one [probe]: for x in [-5, 5], f(x) >= 1
    """
    return abs(x)
'''

_KEY = "integfix.settle"


@pytest.fixture
def project(tmp_path, monkeypatch):
    import mathema
    (tmp_path / "integfix.py").write_text(_FIXTURE)
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = __import__("integfix")
    mathema.write_spec(mod.settle, root=str(tmp_path))
    return tmp_path


def _path(project):
    return project / ".mathema" / "verified" / f"{_KEY}.yaml"


def _load(project):
    return yaml.safe_load(_path(project).read_text())[_KEY]


def _save(project, entry):
    write_yaml(str(_path(project)), {_KEY: entry})


def _policy(project):
    meta = project / ".mathema" / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "policy.yaml").write_text(
        "acceptance:\n  require_verification: true\n")


def _row(entry, name):
    return next(c for c in entry["claims"] if c.get("name") == name)


def _legacy_checksum(entry):
    """The checksum records were stamped with before statements and
    retirement rows were covered, reproduced here so a record in that
    shape can be written as the earlier code wrote it."""
    import hashlib

    def _acc(c):
        accepted = c.get("accepted")
        if not isinstance(accepted, dict):
            return ""
        vb = accepted.get("verified_by") or {}
        return (f"{accepted.get('as', '')}:{vb.get('key', '')}"
                f":{1 if accepted.get('stale') else 0}")

    rows = sorted((c.get("name") or "", c.get("verdict") or "", _acc(c))
                  for c in entry.get("claims") or [])
    basis = "|".join(f"{n}={v};{a}" for n, v, a in rows)
    basis += f"#form={(entry.get('identity') or {}).get('form', '')}"
    locked = entry.get("locked")
    if isinstance(locked, dict):
        basis += f"#locked={locked.get('form', '')}"
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def test_the_checksum_covers_what_a_claim_states(project):
    from mathema.spec import integrity_checksum
    entry = _load(project)
    stamped = integrity_checksum(entry)
    for field_name, value in (("statement", "for x in [-5, 5], f(x) >= -1"),
                              ("route", "derive"),
                              ("tolerance", 0.5),
                              ("domain", {"x": {"lo": 0.0, "hi": 1.0,
                                                "closed_lo": True,
                                                "closed_hi": True}})):
        edited = yaml.safe_load(yaml.safe_dump(entry))
        _row(edited, "nonneg")[field_name] = value
        assert integrity_checksum(edited) != stamped, field_name


def test_the_checksum_covers_the_retirement_sections(project):
    from mathema.spec import integrity_checksum
    entry = _load(project)
    stamped = integrity_checksum(entry)
    for section in ("discoveries", "historical", "superseded"):
        edited = yaml.safe_load(yaml.safe_dump(entry))
        edited[section] = [{"name": "above_one",
                            "statement": "for x in [-5, 5], f(x) >= 1"}]
        assert integrity_checksum(edited) != stamped, section


def test_an_edited_statement_trips_the_mismatch(project):
    from mathema.verify import verify_project
    entry = _load(project)
    _row(entry, "nonneg")["statement"] = "for x in [-5, 5], f(x) >= -100"
    _save(project, entry)
    out = verify_project(root=str(project))
    assert any("checksum no longer matches" in ln for ln in out.lines)


def test_a_mismatch_fails_the_sweep_under_require_verification(project):
    from mathema.verify import verify_project
    entry = _load(project)
    _row(entry, "nonneg")["verdict"] = "proven"
    _save(project, entry)
    _policy(project)
    out = verify_project(root=str(project))
    assert any("checksum no longer matches" in p for p in out.problems)
    row = next(k for k in out.keys if k["key"] == _KEY)
    assert row["passed"] is False


def test_a_mismatch_stays_advisory_without_a_policy(project):
    from mathema.verify import verify_project
    entry = _load(project)
    _row(entry, "nonneg")["verdict"] = "proven"
    _save(project, entry)
    out = verify_project(root=str(project))
    assert any("checksum no longer matches" in ln for ln in out.lines)
    assert not any("checksum" in p for p in out.problems)


def test_a_legacy_stamped_record_still_verifies_clean(project):
    # a record exactly as the earlier code stamped it: its checksum is
    # the legacy scheme's, and nothing in it was altered
    from mathema.spec import integrity_matches
    from mathema.verify import verify_project
    entry = _load(project)
    entry["identity"]["integrity"] = _legacy_checksum(entry)
    _save(project, entry)
    assert integrity_matches(_load(project)) is True
    _policy(project)
    out = verify_project(root=str(project))
    assert not any("checksum" in ln for ln in out.lines)
    assert not any("checksum" in p for p in out.problems)


def test_a_legacy_stamped_record_still_detects_an_edited_verdict(project):
    from mathema.spec import integrity_matches
    entry = _load(project)
    entry["identity"]["integrity"] = _legacy_checksum(entry)
    _row(entry, "above_one")["verdict"] = "proven"
    _save(project, entry)
    assert integrity_matches(_load(project)) is False


def test_a_re_adjudicated_legacy_record_is_restamped_in_the_new_scheme(
        project):
    from mathema.spec import integrity_checksum
    from mathema.verify import verify_project
    entry = _load(project)
    entry["identity"]["integrity"] = _legacy_checksum(entry)
    _save(project, entry)
    verify_project(root=str(project), only=[_KEY])
    after = _load(project)
    assert after["identity"]["integrity"] == integrity_checksum(after)
    assert after["identity"]["integrity"] != _legacy_checksum(after)


# --- retirement rows the gate never wrote -----------------------------------

def _forge_discovery(project, accepted=None):
    """Move the falsified claim into `discoveries` by hand and restamp the
    unkeyed checksum, the way a hand edit can."""
    from mathema.spec import integrity_checksum
    entry = _load(project)
    row = _row(entry, "above_one")
    assert row["verdict"].startswith("falsified")
    entry["claims"].remove(row)
    if accepted is not None:
        row["accepted"] = accepted
    entry.setdefault("discoveries", []).append(row)
    entry["identity"]["integrity"] = integrity_checksum(entry)
    _save(project, entry)


def test_a_forged_discovery_row_does_not_retire_a_falsified_claim(project):
    from mathema.verify import verify_project
    _forge_discovery(project)
    out = verify_project(root=str(project), only=[_KEY])
    assert any("above_one" in p and "no acceptance" in p
               for p in out.problems)
    row = next(k for k in out.keys if k["key"] == _KEY)
    assert row["passed"] is False
    assert row["counts"]["falsified"] == 1


def test_a_forged_discovery_row_fails_the_policy(project):
    from mathema.verify import verify_project
    _forge_discovery(project, accepted={"as": "discovery", "by": "someone"})
    _policy(project)
    out = verify_project(root=str(project))
    assert any("above_one" in p and "not human-verified" in p
               for p in out.problems)


def test_a_verified_discovery_satisfies_the_policy(project, monkeypatch):
    import getpass

    from mathema import auth
    from mathema.acceptance import apply_acceptance, plan_acceptance
    from mathema.verify import verify_project
    auth.set_pin("4321")
    monkeypatch.setattr(auth, "_tty_available", lambda: True)
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "4321")
    apply_acceptance(plan_acceptance(str(project), _KEY, "above_one",
                                     "discovery", by="turing"))
    _policy(project)
    out = verify_project(root=str(project))
    assert not any("human-verified" in p or "no acceptance" in p
                   for p in out.problems), out.problems


def test_a_caller_settled_after_its_callee_is_stamped_over_what_it_says(
        tmp_path, monkeypatch):
    # the caller sorts first, so its dependencies_current row is settled
    # after the callee's record exists; that settling is mathema's own
    # write and must leave the record matching its checksum
    from mathema.spec import integrity_matches
    from mathema.verify import verify_project
    (tmp_path / "callfix.py").write_text(
        "def b(x):\n    return x * x\n\n\n"
        "def a(x):\n    return b(x) + 1\n")
    (tmp_path / "callfix.claims.yaml").write_text(
        "callfix.a:\n  claims:\n    - name: pos\n"
        "      statement: 'for x in [-10, 10], a(x) >= 1'\n"
        "callfix.b:\n  claims:\n    - name: nonneg\n"
        "      statement: 'for x in [-10, 10], b(x) >= 0'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    verify_project(root=str(tmp_path))
    for key in ("callfix.a", "callfix.b"):
        path = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
        assert integrity_matches(yaml.safe_load(path.read_text())[key]), key
    _policy(tmp_path)
    out = verify_project(root=str(tmp_path))
    assert not out.problems, out.problems


# --- a record that does not read --------------------------------------------

_TWO = '''\
def one(x: float) -> float:
    return x


def two(x: float) -> float:
    return 2 * x
'''

_TWO_CLAIMS = '''\
twofix.one:
  claims:
    - name: ident
      statement: 'for x in [0, 1], f(x) == x'
twofix.two:
  claims:
    - name: dbl
      statement: 'for x in [0, 1], f(x) == 2*x'
'''

_CONFLICTED = '''\
twofix.one:
  claims:
<<<<<<< HEAD
    - name: ident
      verdict: "proven"
=======
    - name: ident
      verdict: "holds"
>>>>>>> other
'''


@pytest.mark.parametrize("body,reason", [(_CONFLICTED, "does not parse"),
                                         ("", "is empty"),
                                         ("- 1\n- 2\n", "not a mapping")])
def test_an_unreadable_record_fails_its_own_key_and_is_left_alone(
        tmp_path, monkeypatch, body, reason):
    from mathema.verify import verify_project
    (tmp_path / "twofix.py").write_text(_TWO)
    (tmp_path / "twofix.claims.yaml").write_text(_TWO_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    verify_project(root=str(tmp_path))
    broken = tmp_path / ".mathema" / "verified" / "twofix.one.yaml"
    broken.write_text(body)
    out = verify_project(root=str(tmp_path), all=True)
    assert broken.read_text() == body
    mine = [p for p in out.problems if "twofix.one" in p]
    assert mine and reason in mine[0], out.problems
    assert "twofix.one.yaml" in mine[0]
    assert not any("twofix.two" in p for p in out.problems), out.problems
    by_key = {k["key"]: k for k in out.keys}
    assert by_key["twofix.one"]["passed"] is False
    assert by_key["twofix.two"]["passed"] is True


def test_recording_over_an_unreadable_record_is_refused(tmp_path,
                                                        monkeypatch):
    import mathema
    from mathema.spec import UnreadableRecord
    (tmp_path / "twofix.py").write_text(_TWO)
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = __import__("twofix")
    mathema.write_spec(mod.one, root=str(tmp_path))
    broken = tmp_path / ".mathema" / "verified" / "twofix.one.yaml"
    broken.write_text(_CONFLICTED)
    with pytest.raises(UnreadableRecord):
        mathema.write_spec(mod.one, root=str(tmp_path))
    assert broken.read_text() == _CONFLICTED
