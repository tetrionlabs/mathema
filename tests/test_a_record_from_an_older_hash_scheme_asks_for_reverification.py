# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record written before the form hashes were last redefined (records
older than `transitions.FORM_SCHEME`) cannot be compared by form: every
form hash differs whether or not the function changed. The first verify
after upgrading re-adjudicates such a function and says so: its trigger
is `record-format`, not `form`, and a move it finds is a transition
whose cause is "recorded before 0.6.5, reverification needed", never
"this function changed". A move to a supported verdict is therefore
`strengthened`, not `fixed`, since nothing shows the function changed.
The record it writes is of the current scheme, so the function is
re-adjudicated this way once."""
import os
import shutil
import subprocess
import sys
import textwrap

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVERIFY = "recorded before 0.6.5, reverification needed"


def test_the_cause_of_a_record_format_move_asks_for_reverification():
    from mathema.transitions import cause_of
    assert cause_of(["record-format"]) == REVERIFY
    assert cause_of(["record-format", "library-version"]) == REVERIFY


def test_a_record_format_move_is_never_fixed():
    from mathema.transitions import transition
    up = transition("falsified", "proven", ["record-format"], commit=None, at="t")
    assert (up["kind"], up["cause"]) == ("strengthened", REVERIFY)
    down = transition("holds", "falsified", ["record-format"], commit=None, at="t")
    assert (down["kind"], down["cause"]) == ("regressed", REVERIFY)


def test_a_record_predates_the_scheme_by_its_schema_version():
    from mathema.transitions import FORM_SCHEME, predates_form_scheme
    assert FORM_SCHEME == "0.3.0"
    assert predates_form_scheme({"schema_version": "0.2.0"})
    assert predates_form_scheme({})
    assert not predates_form_scheme({"schema_version": "0.3.0"})
    assert not predates_form_scheme({"schema_version": "0.10.0"})


_MOD = """
def double(x: float) -> float:
    \"\"\"Doubles.\"\"\"
    return 2.0 * x
"""

_CLAIMS = """
spkg.mod.double:
  claims:
    - name: doubles
      statement: 'for x in [0,5], f(x) == 2*x'
      route: derive
"""


def _verify(root, env):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['verify', '--root', {str(root)!r}]))"],
        cwd=str(root), capture_output=True, text=True, env=env)


def _as_written_before_the_scheme(path, key):
    """The record at `path` as an older core wrote it: an earlier schema
    version, a form hash of the old scheme, and the claim falsified,
    restamped so it is not read as a hand edit."""
    from mathema.spec import integrity_checksum
    doc = yaml.safe_load(path.read_text())
    entry = doc[key]
    entry["schema_version"] = "0.2.0"
    entry["identity"]["form"] = "py:0123456789ab"
    for c in entry["claims"]:
        if c.get("name") == "doubles":
            c["verdict"] = "falsified"
    entry["identity"]["integrity"] = integrity_checksum(entry)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def test_the_first_verify_after_upgrading_asks_for_reverification(tmp_path):
    from mathema.transitions import open_transitions
    pkg = tmp_path / "spkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "c.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    shutil.rmtree(pkg / "__pycache__", ignore_errors=True)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    key = "spkg.mod.double"
    assert _verify(tmp_path, env).returncode == 0
    path = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    _as_written_before_the_scheme(path, key)

    _verify(tmp_path, env)
    entry = yaml.safe_load(path.read_text())[key]
    assert entry["meta"]["mathema.invalidated_by"] == ["record-format"]
    row = next(c for c in entry["claims"] if c["name"] == "doubles")
    assert row["verdict"] == "proven"
    (t,) = open_transitions(row["meta"])
    assert (t["from"], t["to"], t["kind"], t["cause"]) == (
        "falsified", "proven", "strengthened", REVERIFY)

    again = _verify(tmp_path, env)
    assert yaml.safe_load(path.read_text())[key]["schema_version"] == "0.3.0"
    assert "1 unchanged since the last run (not run again)" in again.stdout
