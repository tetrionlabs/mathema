# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_language_defined[s]: fuzz a string parameter over an edge-case
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


def _one(fn, law="is_language_defined(s)"):
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


def _letters():
    from mathema.languages import StringLanguage
    return StringLanguage("letters", char_ok=str.isalpha, pool="abcXYZ\u00e9",
                          outside_pool="1 -.")


def test_the_shrunk_witness_states_whether_it_is_inside_the_declared_language(tmp_path):
    from mathema.languages import register_language, unregister_language
    register_language("letters", _letters())
    try:
        mod = _load(tmp_path, '''
            def first_char(s: str) -> str:
                """First character."""
                return s[0]
        ''')
        pr = _one(mod.first_char, "for s in L[letters], is_language_defined(s)")
        assert pr.verdict == "falsified"
        assert "(inside L[letters])" in pr.counterexample
        assert "''" in pr.counterexample and "IndexError" in pr.counterexample
    finally:
        unregister_language("letters")


def test_a_value_the_claim_excludes_is_labelled_outside(tmp_path):
    from mathema.languages import register_language, unregister_language
    register_language("letters", _letters())
    try:
        mod = _load(tmp_path, '''
            def first_char(s: str) -> str:
                """First character."""
                return s[0]
        ''')
        pr = _one(mod.first_char, 'for s in L[letters] \\ {""}, is_language_defined(s)')
        assert pr.verdict == "falsified"
        assert '(outside L[letters] \\ {""})' in pr.counterexample, pr.counterexample
        assert "''" in pr.counterexample and "(inside" not in pr.counterexample
    finally:
        unregister_language("letters")


def test_shrinking_never_crosses_the_language_boundary(tmp_path):
    from mathema.languages import register_language, unregister_language
    register_language("letters", _letters())
    try:
        mod = _load(tmp_path, '''
            def digit_value(s: str) -> int:
                """The value of a leading digit; letters count as zero."""
                if s.isalpha() or s == "":
                    return 0
                return {"0": 0, "1": 1, "2": 2}[s[0]]
        ''')
        # inside the language the function is fine; outside it, a
        # non-digit crashes with an unguarded KeyError, and the shrunk
        # witness stays outside the language
        pr = _one(mod.digit_value, "for s in L[letters], is_language_defined(s)")
        assert pr.verdict == "falsified", (pr.verdict, pr.note)
        assert "(outside L[letters])" in pr.counterexample
        witness = pr.counterexample.split(" = ", 1)[1].split(" (", 1)[0]
        assert not eval(witness).isalpha()
    finally:
        unregister_language("letters")


def test_without_a_language_bound_nothing_changes(tmp_path):
    mod = _load(tmp_path, '''
        def first_char(s: str) -> str:
            """First character."""
            return s[0]
    ''')
    pr = _one(mod.first_char)
    assert pr.counterexample == ("s = '' raised IndexError on arbitrary input, "
                                 "an unguarded crash, not a declared rejection")


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
    assert "is_language_defined[text]" in names


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
