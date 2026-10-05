# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`dependencies_current` asks whether each direct callee's verified
record still matches its form. A callee installed outside the project
(the standard library, a third-party package) is not something the
project's store records unless a claims file states claims about it, so
a call into one leaves the rung settled rather than waiting forever on
a record of the library's internals. A callee inside the project still
needs its own record."""
import sys
import textwrap

import yaml


def _verify(tmp_path):
    import subprocess
    script = ("import sys; from mathema.cli import main; "
              "sys.exit(main(['verify', '--root', '.', '--lenient']))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                          capture_output=True, text=True)


def _claims(tmp_path, key):
    doc = yaml.safe_load((tmp_path / ".mathema" / "verified"
                          / f"{key}.yaml").read_text())
    return doc[key]


def test_a_function_calling_a_standard_library_function_is_current(tmp_path):
    (tmp_path / "avgs.py").write_text(textwrap.dedent('''\
        from statistics import fmean


        def avg(a: float, b: float) -> float:
            """The mean of a and b."""
            return fmean([a, b])
        '''))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "avgs.claims.yaml").write_text(textwrap.dedent('''\
        avgs.avg:
          claims:
            - name: between
              statement: "for a in [0, 1], b in [0, 1], 0 <= f(a, b) <= 1"
        '''))
    r = _verify(tmp_path)
    entry = _claims(tmp_path, "avgs.avg")
    rows = {c["name"]: c for c in entry["claims"]}
    assert rows["dependencies_current"]["verdict"] == "proven", \
        r.stdout + r.stderr
    assert "statistics.fmean" in [d.get("key") for d in entry["dependencies"]]
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_project_callee_without_a_record_still_leaves_the_rung_open(tmp_path):
    from mathema.spec import _dependency_state
    (tmp_path / "helpers.py").write_text("def h(x):\n    return x\n")
    dep = {"key": "helpers.h", "form": "abc",
           "file": str(tmp_path / "helpers.py")}
    assert _dependency_state(dep, {}, root=str(tmp_path)) == "unverified"


def test_an_installed_callee_with_a_record_is_still_compared(tmp_path):
    import statistics

    from mathema.spec import _dependency_state
    dep = {"key": "statistics.fmean", "form": "abc",
           "file": statistics.__file__}
    verified = {"statistics.fmean": {"entry": {"identity": {"form": "xyz"},
                                               "claims": []}}}
    assert _dependency_state(dep, verified, root=str(tmp_path)) == "stale"
    assert _dependency_state(dep, {}, root=str(tmp_path)) is None


def test_an_unknown_dependency_rung_names_the_callees(tmp_path):
    from mathema.spec import dependencies_current_probe
    (tmp_path / "helpers.py").write_text("def h(x):\n    return x\n")
    dep = {"key": "helpers.h", "form": "abc", "kind": "function",
           "file": str(tmp_path / "helpers.py")}
    probe = dependencies_current_probe([dep], root=str(tmp_path))
    assert probe.verdict == "unknown"
    assert "helpers.h" in probe.note
