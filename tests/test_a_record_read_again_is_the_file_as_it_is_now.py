# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Reading a verified record or a claims file again gives the file as it
is now, and each read is the caller's own: a file read twice unchanged
is parsed once, a rewritten one is parsed again, and changing what one
read returned leaves the next read untouched."""
import os


def test_a_rewritten_record_reads_as_rewritten(tmp_path):
    from mathema.spec import read_verified_file
    path = tmp_path / "k.yaml"
    path.write_text("k:\n  claims: []\n")
    first, _ = read_verified_file(str(path))
    path.write_text("k:\n  claims:\n    - name: grown\n")
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    second, _ = read_verified_file(str(path))
    assert first == {"k": {"claims": []}}
    assert second == {"k": {"claims": [{"name": "grown"}]}}


def test_a_read_is_the_callers_own(tmp_path):
    from mathema.spec import read_claims_file, read_verified_file
    path = tmp_path / "k.claims.yaml"
    path.write_text("k:\n  claims:\n    - name: a\n      statement: 'f(x) >= 0'\n")
    data = read_claims_file(str(path), "k.claims.yaml")
    data["k"]["claims"].clear()
    again = read_claims_file(str(path), "k.claims.yaml")
    assert [c["name"] for c in again["k"]["claims"]] == ["a"]
    record, _ = read_verified_file(str(path))
    record["k"]["claims"].append({"name": "b"})
    assert len(read_verified_file(str(path))[0]["k"]["claims"]) == 1


def test_an_unparseable_record_still_says_where(tmp_path):
    from mathema.spec import read_verified_file
    path = tmp_path / "k.yaml"
    path.write_text("k:\n<<<<<<< HEAD\n  a: [\n")
    data, reason = read_verified_file(str(path))
    assert data is None
    assert "does not parse as YAML at line" in reason
    assert "merge conflict markers" in reason
