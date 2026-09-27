# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim quantified over a language is stamped with the language
dialect, `grammar: mathema/language`, the way a matrix claim is stamped
`mathema/linalg`: the record says the claim was read with the language
vocabulary. A finite-set domain stays the base grammar, the matrix
dialect wins when both apply, and the canonical text re-parses under
the base grammar, so the stamp is informative, never load-bearing."""
import textwrap

from mathema.conjecture import check_conjectures, claim
from mathema.languages import StringLanguage, register_language, unregister_language
from mathema.spec import canonical_claim_text


def _load(tmp_path, body, name="stamp_fns"):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_language_claim_is_stamped_with_the_dialect():
    cj = claim("for s in L[letters], f(s) == s")
    assert cj.grammar == "mathema/language"


def test_a_finite_set_stays_the_base_grammar():
    assert claim('for s in {"a", "b"}, f(s) == s').grammar == "mathema"
    assert claim("for x in [0, 1], f(x) >= 0").grammar == "mathema"


def test_the_matrix_dialect_wins_when_both_apply():
    cj = claim("for A in R^(2,2), s in L[letters], det(f(A, s)) >= 0")
    assert cj.grammar == "mathema/linalg"


def test_the_canonical_text_reparses_under_the_base_grammar():
    cj = claim("for s in L[letters] \\ {\"\"}, len(f(s)) >= 1")
    again = claim(canonical_claim_text(cj))
    assert again.grammar == "mathema/language"
    assert canonical_claim_text(again) == canonical_claim_text(cj)


def test_the_record_carries_the_dialect(tmp_path):
    register_language("letters", StringLanguage("letters", char_ok=str.isalpha,
                                                pool="abcXYZ"))
    try:
        mod = _load(tmp_path, '''
            def same(s: str) -> str:
                """The text, unchanged."""
                return s
        ''')
        (p,) = check_conjectures(mod.same, [claim("for s in L[letters], f(s) == s")])
        assert p.verdict == "holds"
        assert p.grammar == "mathema/language"
    finally:
        unregister_language("letters")


def test_a_language_written_only_on_the_right_of_in_stamps_the_dialect():
    assert claim("for n in N, f(n) in L[digit]").grammar == "mathema/language"
    assert claim('for s in L[unicode], "<" not in f(s)').grammar == "mathema/language"
    assert claim("for x in [0, 2], f(x) in {1, 2}").grammar == "mathema"
    assert claim("for x in [0, 2], f(x) in [0, 1]").grammar == "mathema"
