# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_arbitrary_input_safe[s]: fuzz a string parameter over an edge-case
corpus, and when an ACCIDENTAL exception (a crash the function did not
guard) fires, shrink the input to a minimal witness and falsify on the
probe:minimal_example route. A deliberate rejection (a guarded raise, a
ValueError) or a clean return holds."""
import textwrap


def _load(tmp_path, body, name="m"):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(fn, law="is_arbitrary_input_safe(s)"):
    from mathema.conjecture import check_conjectures, claim
    (pr,) = check_conjectures(fn, [claim(law, route="best")])
    return pr


def test_an_unguarded_crash_falsifies_with_a_minimal_witness(tmp_path):
    mod = _load(tmp_path, '''
        def first_char(s: str) -> str:
            """First character."""
            return s[0]
    ''')
    pr = _one(mod.first_char)
    assert pr.verdict == "falsified"
    assert pr.route == "probe:minimal_example"
    # the empty string is the minimal trigger for s[0]
    assert "''" in pr.counterexample and "IndexError" in pr.counterexample


def test_a_guarded_rejection_holds(tmp_path):
    mod = _load(tmp_path, '''
        def guarded(s: str) -> str:
            """Rejects empty input deliberately."""
            if not s:
                raise ValueError("empty")
            return s[0]
    ''')
    pr = _one(mod.guarded)
    assert pr.verdict == "holds"
    assert pr.route == "probe:minimal_example"


def test_a_total_function_holds(tmp_path):
    mod = _load(tmp_path, '''
        def length(s: str) -> int:
            """Always defined."""
            return len(s)
    ''')
    assert _one(mod.length).verdict == "holds"


def test_a_deliberate_valueerror_is_not_a_crash(tmp_path):
    # a ValueError is deliberate validation, never an accidental crash,
    # so int(text) raising ValueError on non-numeric text holds
    mod = _load(tmp_path, '''
        def to_int(s: str) -> int:
            """Parse an int."""
            return int(s)
    ''')
    assert _one(mod.to_int).verdict == "holds"


def test_suggested_for_a_bare_string_parameter(tmp_path):
    from mathema.suggest import suggest_claims
    mod = _load(tmp_path, '''
        def parse(text: str) -> int:
            """Parse."""
            return int(text)
    ''')
    names = {c.name for c in suggest_claims(mod.parse)}
    assert "is_arbitrary_input_safe[text]" in names


def test_the_minimal_example_is_actually_minimal(tmp_path):
    # a crash triggered only by a long input shrinks to the shortest
    # string that still triggers it
    mod = _load(tmp_path, '''
        def long_only(s: str) -> str:
            """Indexes position 3, so anything shorter is fine but the
            corpus long string crashes at [3] only past length 3... it
            actually crashes for len < 4."""
            return s[3]
    ''')
    pr = _one(mod.long_only)
    assert pr.verdict == "falsified"
    # the minimal witness triggering IndexError at [3] is a string of
    # length < 4 (the shortest the shrinker can reach that still fails)
    import re
    m = re.search(r"s = '([^']*)'", pr.counterexample)
    assert m is not None and len(m.group(1)) < 4
