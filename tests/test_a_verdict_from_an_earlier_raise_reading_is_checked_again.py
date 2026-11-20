# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record stores the verdict of the engine that wrote it. A `proven`
read from a `raise` (a derive `raises(...)` claim, a policy read from a
guard) by an engine of an earlier soundness epoch is checked again on
the next `mathema verify`, once, even though the function did not
change: the re-check says why in the run's output, a verdict that no
longer stands moves, a verdict that still stands keeps its history,
and the rewritten record carries the current epoch, so the next run
finds it fresh. A row the earlier reading could not have decided, a
probe row that holds or is falsified, is left as it was."""
import subprocess

import yaml

from tests.test_cli_verify import _run

_FUNCS = '''def keyword_argument(x: float) -> float:
    """Rejects a negative x."""
    if x < 0:
        raise ValueError(msg="negative")
    return x


def literal_message(x: float) -> float:
    """Rejects a negative x."""
    if x < 0:
        raise ValueError("negative")
    return x


def doubled(x: float) -> float:
    """Twice x."""
    return 2 * x
'''

_CLAIMS = """funcs.keyword_argument:
  claims:
    - name: rejects
      statement: "for x in [-5, -1], raises(f(x), ValueError)"
      route: derive
funcs.literal_message:
  claims:
    - name: rejects
      statement: "for x in [-5, -1], raises(f(x), ValueError)"
      route: derive
funcs.doubled:
  claims:
    - name: grows
      statement: "for x in [0, 1], f(x) >= x"
      route: probe
    - name: shrinks
      statement: "for x in [1, 2], f(x) <= x"
      route: probe
"""

_NOTE = "re-checked under soundness epoch 1"


def _project(tmp_path):
    (tmp_path / "funcs.py").write_text(_FUNCS)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "demo.claims.yaml").write_text(_CLAIMS)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _run(tmp_path)
    return tmp_path


def _path(root, key):
    return root / ".mathema" / "verified" / f"{key}.yaml"


def _entry(root, key):
    return yaml.safe_load(_path(root, key).read_text())[key]


def _rewrite(root, key, edit):
    from mathema.spec import integrity_checksum, write_yaml
    entry = _entry(root, key)
    for row in entry["claims"]:
        edit(row)
    entry["identity"]["integrity"] = integrity_checksum(entry)
    write_yaml(str(_path(root, key)), {key: entry},
               header=f"machine record; binds to form {entry['identity']['form']}")


def _row(root, key, name):
    (row,) = [c for c in _entry(root, key)["claims"] if c["name"] == name]
    return row


def _as_written_before_the_epoch(proven: bool):
    def edit(row):
        meta = row.get("meta") or {}
        meta.pop("mathema.soundness_epoch", None)
        if proven and row["name"] == "rejects":
            row["verdict"] = "proven"
            row["route"] = "derive"
            row["sketch"] = "raises ValueError under this domain"
            row.pop("note", None)
            row.pop("counterexample", None)
            meta.pop("mathema.previous_verdict", None)
            meta.pop("mathema.transitions", None)
        row["meta"] = meta
    return edit


def _lines(out, key):
    return [ln for ln in out.splitlines() if f" {key}:" in ln[:60]]


def test_a_proven_raise_from_an_earlier_epoch_is_checked_again_and_no_longer_proven(
        tmp_path):
    root = _project(tmp_path)
    _rewrite(root, "funcs.keyword_argument", _as_written_before_the_epoch(proven=True))
    run = _run(root)
    row = _row(root, "funcs.keyword_argument", "rejects")
    assert row["verdict"] != "proven", row
    from mathema.soundness_epoch import stale_rows
    assert stale_rows(_entry(root, "funcs.keyword_argument")) == [], row
    assert run.stdout.count(_NOTE) == 1, run.stdout
    (line,) = _lines(run.stdout, "funcs.keyword_argument")
    assert "fresh" not in line, line
    again = _run(root)
    (line,) = _lines(again.stdout, "funcs.keyword_argument")
    assert "fresh" in line, again.stdout
    assert _NOTE not in again.stdout, again.stdout


def test_a_proven_raise_that_still_stands_keeps_its_history_and_is_checked_once(tmp_path):
    root = _project(tmp_path)
    before = _row(root, "funcs.literal_message", "rejects")
    assert before["verdict"] == "proven", before
    _rewrite(root, "funcs.literal_message", _as_written_before_the_epoch(proven=False))
    run = _run(root)
    after = _row(root, "funcs.literal_message", "rejects")
    assert after["verdict"] == "proven", after
    assert after["meta"]["mathema.soundness_epoch"] == 1, after
    assert "mathema.previous_verdict" not in after["meta"], after
    assert after["meta"].get("mathema.transitions") == before["meta"].get(
        "mathema.transitions"), (before, after)
    assert run.stdout.count(_NOTE) == 1, run.stdout
    again = _run(root)
    (line,) = _lines(again.stdout, "funcs.literal_message")
    assert "fresh" in line, again.stdout
    assert _NOTE not in again.stdout, again.stdout


def test_a_proven_raise_stamped_with_the_current_epoch_is_not_checked_again(tmp_path):
    root = _project(tmp_path)

    def proven_at_the_current_epoch(row):
        _as_written_before_the_epoch(proven=True)(row)
        row["meta"]["mathema.soundness_epoch"] = 1
    _rewrite(root, "funcs.keyword_argument", proven_at_the_current_epoch)
    run = _run(root)
    (line,) = _lines(run.stdout, "funcs.keyword_argument")
    assert "fresh" in line, run.stdout
    assert _NOTE not in run.stdout, run.stdout
    assert _row(root, "funcs.keyword_argument", "rejects")["verdict"] == "proven"


def test_a_holds_or_falsified_row_from_the_probe_is_left_as_it_was(tmp_path):
    root = _project(tmp_path)
    verdicts = {c["name"]: c["verdict"] for c in _entry(root, "funcs.doubled")["claims"]}
    assert verdicts["grows"] == "holds" and verdicts["shrinks"] == "falsified", verdicts
    assert all("mathema.soundness_epoch" not in (c.get("meta") or {})
               for c in _entry(root, "funcs.doubled")["claims"])
    run = _run(root)
    (line,) = _lines(run.stdout, "funcs.doubled")
    assert "fresh" in line, run.stdout
    assert _NOTE not in run.stdout, run.stdout


def test_the_rows_an_earlier_raise_reading_could_have_proven_are_the_stale_ones():
    from mathema.soundness_epoch import stale_rows
    entry = {"claims": [
        {"name": "derive_raise", "statement": "for x in [-5, -1], raises(f(x), ValueError)",
         "verdict": "proven", "route": "derive"},
        {"name": "policy_raise", "statement": "absent(f, x) raises(TypeError)",
         "verdict": "proven", "route": "examine",
         "meta": {"mathema.policy": {"behaviour": "raises", "exception": "TypeError"}}},
        {"name": "is_absent_safe", "statement": "is_absent_safe(f)", "verdict": "proven",
         "route": "examine"},
        {"name": "policy_drops", "statement": "missing(f, x) drops", "verdict": "proven",
         "route": "examine", "meta": {"mathema.policy": {"behaviour": "drops"}}},
        {"name": "probe_raise", "statement": "for x in [-5, -1], raises(f(x), ValueError)",
         "verdict": "holds", "route": "probe"},
        {"name": "unknown_raise", "statement": "for x in [-5, -1], raises(f(x), ValueError)",
         "verdict": "unknown", "route": "derive"},
        {"name": "value", "statement": "for x in [0, 1], f(x) >= 0", "verdict": "proven",
         "route": "derive"},
        {"name": "stamped", "statement": "for x in [-5, -1], raises(f(x), ValueError)",
         "verdict": "proven", "route": "derive", "meta": {"mathema.soundness_epoch": 1}},
    ]}
    assert stale_rows(entry) == ["derive_raise", "policy_raise", "is_absent_safe"]
