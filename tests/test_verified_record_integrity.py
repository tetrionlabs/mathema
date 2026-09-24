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
