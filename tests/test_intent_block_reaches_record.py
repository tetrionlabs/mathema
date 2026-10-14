# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A docstring whose only intent is an explicit `Intent:` block carries
that block's text as the function's intent, through `analyze` and into
the record `check` produces; a docstring with a summary line and no
block keeps the summary as its intent."""
import mathema


def implied_vol(price, spot, strike, t, r):
    """Intent:
        The volatility at which bs_call reproduces price. Never
        negative; zero at or below intrinsic.
    """
    return 0.0


def summary_only(x):
    """Twice x, always."""
    return 2 * x


_BLOCK_TEXT = ("The volatility at which bs_call reproduces price. Never "
               "negative; zero at or below intrinsic.")


def test_an_intent_block_alone_is_the_functions_intent():
    facts = mathema.analyze(implied_vol)
    assert facts.doc_intent == _BLOCK_TEXT
    assert facts.doc_intent_source == "documented"


def test_an_intent_block_alone_reaches_the_record():
    spec = mathema.check(implied_vol, claims=[]).to_spec()
    assert spec["intent"] == _BLOCK_TEXT


def test_a_summary_line_without_a_block_stays_the_intent():
    facts = mathema.analyze(summary_only)
    assert facts.doc_intent == "Twice x, always."
    assert facts.doc_intent_source == "declared"
