# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A vector or matrix domain (`R^n`, `R^(n*n)`, `[0, 1]^n`) survives the
declared layer with its dimensions: the claim read back is the same
claim, with the same canonical text and the same verdict, and a scalar
domain's stored form is unchanged."""
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.domain import domain_bound_to_json
from mathema.spec import canonical_claim_text, declare, entry_claims

_SPACES = [
    "for v in R^n, f(v) >= 0",
    "for v in [0, 1]^n, f(v) >= 0",
    "for A in R^(n*n), B in R^(n*n), det(A @ B) == det(A) * det(B)",
    "for A in R^(m*n), f(A) >= 0",
]


@pytest.mark.parametrize("law", _SPACES)
def test_a_space_domain_survives_the_declared_layer(law):
    cj = claim(law)
    (back,) = entry_claims({"claims": [declare(cj)]})
    assert canonical_claim_text(back) == canonical_claim_text(cj)
    assert {p: d.dims for p, d in back.domain.items()} == \
        {p: d.dims for p, d in cj.domain.items()}


def test_a_scalar_domain_stores_no_dims_key():
    (dom,) = claim("for x in R, f(x) >= 0").domain.values()
    assert "dims" not in domain_bound_to_json(dom)


def test_the_verdict_is_the_same_after_the_round_trip():
    from mathema.lexicon import EXAMPLE_FUNCTIONS, LEXICON
    matmul, _ = EXAMPLE_FUNCTIONS["matmul"]
    cj = claim(LEXICON["matrix_determinant_product"])
    (back,) = entry_claims({"claims": [declare(cj)]})
    (before,) = check_conjectures(matmul, [cj])
    (after,) = check_conjectures(matmul, [back])
    assert before.verdict == after.verdict == "proven", \
        (before.verdict, after.verdict)
