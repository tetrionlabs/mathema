# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `Sum`/`Prod` binds its index over the summand. When the index has
the same name as a parameter of `f`, the summand's occurrences are the
bound index, never the parameter, whatever the parameter's annotation,
so `Sum(f(i), i, 1, n)` for `f(i) = 2*i` is `n*(n + 1)`, not `2*i*n`.
A false closed form is falsified with a witness executed against the
function: the finite sum at a concrete bound, computed by calling `f`
at every index."""
import pytest

from mathema.conjecture import check_conjectures, claim


def summand(i: float) -> float:
    return 2.0 * i


def summand_int(i: int) -> int:
    return 2 * i


def factor(k: float) -> float:
    return k


def _probe(fn, law, route="derive"):
    (probe,) = check_conjectures(fn, [claim(law, route=route)])
    return probe


@pytest.mark.parametrize("fn", [summand, summand_int])
@pytest.mark.parametrize("law", [
    "let n be [1, 20] subset Z, Sum(f(i), i, 1, n) == n*(n + 1)",
    "let n be [1, 20] subset Z, Sum(f(i))_{i=1}^n == n*(n + 1)",
])
def test_the_closed_form_of_a_sum_over_the_parameter_name_is_proven(fn, law):
    probe = _probe(fn, law)
    assert probe.verdict == "proven", (probe.verdict, probe.note)
    assert probe.route == "derive"


def test_a_product_binds_its_index_the_same_way():
    probe = _probe(factor, "let n be [1, 10] subset Z, Prod(f(k), k, 1, n) == factorial(n)")
    assert probe.verdict == "proven", (probe.verdict, probe.note)


@pytest.mark.parametrize("fn", [summand, summand_int])
@pytest.mark.parametrize("law", [
    "let n be [1, 20] subset Z, Sum(f(i), i, 1, n) == n*(n + 2)",
    "let n be [1, 20] subset Z, Sum(f(i))_{i=1}^n == n*(n + 2)",
])
def test_a_false_closed_form_is_falsified_with_an_executed_witness(fn, law):
    probe = _probe(fn, law)
    assert probe.verdict == "falsified", (probe.verdict, probe.note)
    assert probe.meta.get("mathema.corroboration") == "reproduced"
    assert probe.counterexample and "n=" in probe.counterexample


def test_a_bound_index_is_not_a_sampled_coordinate_of_the_witness():
    probe = _probe(summand, "let n be [1, 20] subset Z, Sum(f(i), i, 1, n) == n*(n + 2)")
    assert "i=" not in probe.counterexample


def test_a_sum_the_code_disagrees_with_at_one_bound_only_is_falsified():
    def spiky(i: float) -> float:
        return 2.0 * i + (1.0 if i == 7 else 0.0)
    probe = _probe(spiky, "let n be [1, 20] subset Z, Sum(f(i), i, 1, n) == n*(n + 1)")
    assert probe.verdict == "falsified", (probe.verdict, probe.note)
    assert probe.meta.get("mathema.corroboration") == "reproduced"


def test_an_executed_sum_visits_every_index_in_order():
    from mathema._indexed import indexed_total
    seen = []
    assert indexed_total("Sum", lambda k: seen.append(k) or k, 1, 4) == 10
    assert seen == [1, 2, 3, 4]
    assert indexed_total("Prod", lambda k: k, 1, 5) == 120


def test_an_empty_range_is_the_identity_of_its_form():
    from mathema._indexed import indexed_total
    assert indexed_total("Sum", lambda k: 1 / 0, 3, 2) == 0
    assert indexed_total("Prod", lambda k: 1 / 0, 3, 2) == 1


@pytest.mark.parametrize("lo, hi", [(1, 2.5), (5, 2), (True, 3), (0, float("inf"))])
def test_a_range_with_no_executed_meaning_is_refused(lo, hi):
    from mathema._indexed import indexed_total
    with pytest.raises(ValueError):
        indexed_total("Sum", lambda k: k, lo, hi)
